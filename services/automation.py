"""Idempotent background automation for complaint acknowledgements, notifications and SLAs.

Run with: python -m services.automation_worker
Email is optional; without SMTP settings, all updates remain in the in-app conversation
and Notification centre.
"""
from __future__ import annotations

from datetime import datetime
from email.message import EmailMessage
import os
import smtplib
import secrets

from services.operations import now_iso, evaluate_slas, _audit
from services.workflow import add_message


def _event_done(conn, event_key: str) -> bool:
    return conn.execute("SELECT 1 FROM AutomationEvent WHERE event_key=?", (event_key,)).fetchone() is not None


def _mark_event(conn, event_key: str, event_type: str, complaint_id: str | None, details: str = ""):
    conn.execute("INSERT OR IGNORE INTO AutomationEvent(event_key,event_type,complaint_id,processed_at,details) VALUES(?,?,?,?,?)",
                 (event_key, event_type, complaint_id, now_iso(), details))
    conn.commit()


def _smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))


def _send_email(to_address: str, subject: str, body: str):
    host = os.getenv("SMTP_HOST")
    sender = os.getenv("SMTP_FROM")
    if not host or not sender:
        return "Not configured", None
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_address
    msg.set_content(body)
    port = int(os.getenv("SMTP_PORT", "587"))
    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            if os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes"):
                server.starttls()
            username, password = os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD")
            if username:
                server.login(username, password or "")
            server.send_message(msg)
        return "Sent", None
    except Exception as exc:  # keep the in-app notification even if email fails
        return "Failed", str(exc)[:500]


def _notification(conn, event_key: str, complaint_id: str | None, recipient_type: str,
                  recipient_id: str, channel: str, subject: str, body: str):
    existing = conn.execute("SELECT notification_id FROM Notification WHERE event_key=? AND recipient_type=? AND recipient_id=? AND channel=?",
                            (event_key, recipient_type, recipient_id, channel)).fetchone()
    if existing:
        return existing[0]
    nid = "NTF-" + secrets.token_hex(6).upper()
    status, error, sent_at = "Delivered", None, now_iso()
    if channel == "Email":
        status, error = _send_email(recipient_id, subject, body)
        sent_at = now_iso() if status == "Sent" else None
    conn.execute("""INSERT INTO Notification(notification_id,event_key,complaint_id,recipient_type,recipient_id,
        channel,subject,body,delivery_status,created_at,sent_at,error_text)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (nid,event_key,complaint_id,recipient_type,recipient_id,channel,subject,body,status,now_iso(),sent_at,error))
    conn.commit()
    return nid


def _customer(conn, complaint_id):
    return conn.execute("""SELECT cu.customer_id,cu.full_name,cu.email,c.complaint_id,c.current_status,
        k.category_name,c.priority_level FROM Complaint c JOIN Customer cu USING(customer_id)
        LEFT JOIN Category k USING(category_id) WHERE c.complaint_id=?""", (complaint_id,)).fetchone()


def notify_customer(conn, complaint_id: str, event_key: str, subject: str, body: str,
                    add_to_conversation: bool = True):
    if _event_done(conn, event_key):
        return False
    customer = _customer(conn, complaint_id)
    if not customer:
        return False
    if add_to_conversation:
        add_message(conn, complaint_id, "System", body, channel="Support Portal", visible=True,
                    sender_id="ResolveIQ Automation")
    _notification(conn,event_key,complaint_id,"Customer",customer["customer_id"],"In-App",subject,body)
    if customer["email"]:
        _notification(conn,event_key,complaint_id,"Customer",customer["email"],"Email",subject,body)
    _mark_event(conn,event_key,"CUSTOMER_NOTIFICATION",complaint_id,subject)
    return True


def notify_agent(conn, complaint_id: str, event_key: str, subject: str, body: str):
    assignment = conn.execute("""SELECT x.agent_id,a.agent_name FROM Assignment x JOIN Agent a USING(agent_id)
        WHERE x.complaint_id=? AND x.is_current=1 ORDER BY x.assigned_at DESC LIMIT 1""", (complaint_id,)).fetchone()
    if assignment:
        _notification(conn,event_key,complaint_id,"Agent",assignment["agent_id"],"In-App",subject,body)
        users = conn.execute("SELECT username FROM AppUser WHERE role='Agent' AND agent_id=? AND active=1", (assignment["agent_id"],)).fetchall()
        for user in users:
            _notification(conn,event_key,complaint_id,"User",user["username"],"In-App",subject,body)
    else:
        admins = conn.execute("SELECT username FROM AppUser WHERE role='Administrator' AND active=1").fetchall()
        for admin in admins:
            _notification(conn,event_key,complaint_id,"User",admin["username"],"In-App",subject,body)


def _safe_guidance(category: str | None) -> str:
    """Conservative first-line guidance; never claims that a refund/repair was executed."""
    guidance = {
        "Product Safety": "For safety, stop using the product. If it is safe to do so, disconnect it from power. If there is smoke, fire, electric shock or immediate danger, move away and contact local emergency services. A specialist has been alerted.",
        "Product Defect": "Please stop using the product if it appears unsafe. Keep the order details and, if possible, a photo or short description of the fault ready for the support agent.",
        "Delivery": "Please keep your order number available. Our logistics team will verify the latest shipment status and advise on the next step.",
        "Payment": "Please check whether the transaction is pending or completed with your bank. Do not share card numbers, passwords or one-time passcodes in this chat. Our billing team will review the charge.",
        "Refund": "Your refund request has been recorded. Refund eligibility and payment processing require a support-team review; no refund has been issued automatically.",
        "Account": "For your security, never share your password or one-time passcode. Our support team will help verify the account issue through the approved account-recovery process.",
        "Warranty": "Please keep your purchase date and product serial number available so the support team can check warranty eligibility.",
    }
    return guidance.get(category or "", "A support specialist has received your message and will review the details. If you have an order number or relevant evidence, please add it to this complaint.")


def process_new_complaints(conn):
    rows = conn.execute("SELECT c.complaint_id FROM Complaint c WHERE NOT EXISTS (SELECT 1 FROM AutomationEvent e WHERE e.event_key='complaint-registered:'||c.complaint_id) ORDER BY c.created_at").fetchall()
    count = 0
    for row in rows:
        cid = row["complaint_id"]
        event_key = f"complaint-registered:{cid}"
        if _event_done(conn,event_key):
            continue
        data = _customer(conn,cid)
        if not data:
            continue
        assigned = conn.execute("SELECT a.agent_name,a.agent_id,t.team_name FROM Assignment x JOIN Agent a USING(agent_id) JOIN Team t USING(team_id) WHERE x.complaint_id=? AND x.is_current=1", (cid,)).fetchone()
        assignment_text = f" It has been assigned to {assigned['agent_name']} ({assigned['team_name']})." if assigned else " Our team is arranging an available agent."
        body = (f"Hello {data['full_name']}, we have registered your complaint {cid}. "
                f"Category: {data['category_name'] or 'Review required'}; priority: {data['priority_level']}; "
                f"current status: {data['current_status']}.{assignment_text} "
                f"First-line guidance: {_safe_guidance(data['category_name'])} "
                "This is an acknowledgement, not a confirmation that the issue is resolved. You can reply in the customer portal.")
        notify_customer(conn,cid,event_key,"Complaint registration confirmation",body)
        count += 1
    return count


def process_assignment_notifications(conn):
    rows = conn.execute("""SELECT x.assignment_id,x.complaint_id,x.agent_id,a.agent_name,c.priority_level,k.category_name
        FROM Assignment x JOIN Agent a USING(agent_id) JOIN Complaint c USING(complaint_id)
        LEFT JOIN Category k USING(category_id) WHERE x.is_current=1""").fetchall()
    count = 0
    for row in rows:
        key = f"assignment-event:{row['assignment_id']}"
        if _event_done(conn,key):
            continue
        body = f"Complaint {row['complaint_id']} has been assigned to you. Priority: {row['priority_level']}; category: {row['category_name']}."
        notify_agent(conn,row["complaint_id"],key,f"Complaint assigned: {row['complaint_id']}",body)
        _mark_event(conn,key,"AGENT_ASSIGNMENT",row["complaint_id"],row["agent_id"])
        count += 1
    return count


def process_customer_messages(conn):
    rows = conn.execute("""SELECT m.message_id,m.complaint_id,m.message_text,cu.full_name,k.category_name
        FROM ComplaintMessage m JOIN Complaint c USING(complaint_id) JOIN Customer cu USING(customer_id)
        LEFT JOIN Category k USING(category_id) WHERE m.sender_type='Customer'
        AND NOT EXISTS (SELECT 1 FROM AutomationEvent e WHERE e.event_key='customer-message-reply:'||m.message_id)
        ORDER BY m.created_at""").fetchall()
    count = 0
    for row in rows:
        key = f"customer-message-reply:{row['message_id']}"
        if _event_done(conn,key):
            continue
        guidance = _safe_guidance(row["category_name"])
        body = (f"Hello {row['full_name']}, thank you for your update on complaint {row['complaint_id']}. "
                f"{guidance} This is an automated first response; an agent remains responsible for confirming the resolution.")
        notify_customer(conn,row["complaint_id"],key,"We received your complaint update",body)
        notify_agent(conn,row["complaint_id"],f"agent-reply:{row['message_id']}",
                     f"New customer reply: {row['complaint_id']}",
                     f"A customer added a new message to {row['complaint_id']}: {row['message_text'][:400]}")
        count += 1
    return count


def process_agent_messages(conn):
    """Notify customers when an agent posts a customer-visible reply."""
    rows = conn.execute("""SELECT m.message_id,m.complaint_id,m.message_text FROM ComplaintMessage m
        WHERE m.sender_type='Agent' AND m.is_customer_visible=1
        AND NOT EXISTS (SELECT 1 FROM AutomationEvent e WHERE e.event_key='agent-message-notification:'||m.message_id)
        ORDER BY m.created_at""").fetchall()
    count = 0
    for row in rows:
        key = f"agent-message-notification:{row['message_id']}"
        notify_customer(conn,row["complaint_id"],key,"Your support agent replied",
                        f"A support agent replied to complaint {row['complaint_id']}: {row['message_text']}",
                        add_to_conversation=False)
        count += 1
    return count


def process_sla_events(conn):
    rows = conn.execute("SELECT sla_event_id,complaint_id,event_type,details FROM SLAEvent WHERE event_type IN ('Breached','Escalated') ORDER BY event_at").fetchall()
    count = 0
    for row in rows:
        key = f"sla-event:{row['sla_event_id']}"
        if _event_done(conn,key):
            continue
        if row["event_type"] == "Breached":
            subject = f"SLA deadline breached: {row['complaint_id']}"
            body = f"Your complaint {row['complaint_id']} has exceeded its service response or resolution deadline. The support team has been notified and is reviewing it."
            notify_customer(conn,row["complaint_id"],key,subject,body)
            notify_agent(conn,row["complaint_id"],f"agent-{key}",subject,
                         f"SLA breach detected for {row['complaint_id']}. Please review this case immediately.")
        else:
            subject = f"Complaint escalated: {row['complaint_id']}"
            body = f"Your complaint {row['complaint_id']} has been automatically escalated because its SLA deadline was exceeded. A senior support team has been notified."
            notify_customer(conn,row["complaint_id"],key,subject,body)
            admins = conn.execute("SELECT username FROM AppUser WHERE role='Administrator' AND active=1").fetchall()
            for admin in admins:
                _notification(conn,key,row["complaint_id"],"User",admin["username"],"In-App",subject,body)
        _mark_event(conn,key,row["event_type"],row["complaint_id"],row["details"])
        count += 1
    return count


def process_resolutions(conn):
    rows = conn.execute("SELECT event_id,complaint_id FROM StatusEvent WHERE to_status='Resolved' ORDER BY changed_at").fetchall()
    count = 0
    for row in rows:
        key = f"resolution:{row['event_id']}"
        if _event_done(conn,key):
            continue
        resolution = conn.execute("SELECT resolution_notes FROM Resolution WHERE complaint_id=?", (row["complaint_id"],)).fetchone()
        notes = resolution[0] if resolution else "The support team has marked the complaint as resolved."
        body = f"Your complaint {row['complaint_id']} has been marked as resolved. Resolution notes: {notes}. If the issue persists, please reply to this complaint to request a review."
        notify_customer(conn,row["complaint_id"],key,"Complaint resolution update",body)
        count += 1
    return count


def retry_pending_emails(conn):
    """Retry email rows that previously failed or were skipped before SMTP was configured."""
    if not _smtp_configured():
        return 0
    rows = conn.execute("SELECT notification_id,recipient_id,subject,body FROM Notification WHERE channel='Email' AND delivery_status IN ('Failed','Not configured') ORDER BY created_at LIMIT 100").fetchall()
    sent = 0
    for row in rows:
        status, error = _send_email(row["recipient_id"], row["subject"], row["body"])
        conn.execute("UPDATE Notification SET delivery_status=?,sent_at=?,error_text=? WHERE notification_id=?",
                     (status, now_iso() if status == "Sent" else None, error, row["notification_id"]))
        sent += int(status == "Sent")
    conn.commit()
    return sent


def run_automation_cycle(conn):
    """Run all automation once. Safe to call repeatedly; event keys prevent duplicate actions."""
    result = {}
    result["new_complaints"] = process_new_complaints(conn)
    result["assignments"] = process_assignment_notifications(conn)
    result["customer_replies"] = process_customer_messages(conn)
    result["agent_replies_notified"] = process_agent_messages(conn)
    sla = evaluate_slas(conn,"ResolveIQ Automation")
    result["sla_breaches"] = sla["breached"]
    result["escalations"] = sla["escalated"]
    result["sla_notifications"] = process_sla_events(conn)
    result["resolution_notifications"] = process_resolutions(conn)
    result["email_retries_sent"] = retry_pending_emails(conn)
    total = sum(result.values())
    conn.execute("INSERT INTO AutomationHeartbeat(worker_name,last_seen_at,last_result) VALUES('ResolveIQ Automation',?,?) ON CONFLICT(worker_name) DO UPDATE SET last_seen_at=excluded.last_seen_at,last_result=excluded.last_result",
                 (now_iso(),str(result)))
    conn.commit()
    return result
