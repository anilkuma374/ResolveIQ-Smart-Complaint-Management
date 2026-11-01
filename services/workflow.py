from datetime import datetime, timedelta
from services.rules import classify, determine_priority, team_for_category, sla_deadlines
from services.operations import now_iso, assign_least_loaded, _audit, record_first_response

TRANSITIONS = {
    "New": {"Triaged", "Assigned", "Escalated"},
    "Triaged": {"Assigned", "In Progress", "Escalated"},
    "Assigned": {"In Progress", "Waiting for Customer", "Escalated"},
    "In Progress": {"Waiting for Customer", "Resolved", "Escalated"},
    "Waiting for Customer": {"In Progress", "Resolved", "Escalated"},
    "Resolved": {"Closed", "Reopened"}, "Closed": {"Reopened"},
    "Reopened": {"Triaged", "Assigned", "In Progress", "Escalated"},
    "Escalated": {"Assigned", "In Progress", "Resolved"}
}

def create_complaint(conn, customer_id, order_id, product_id, channel, description, sentiment=-0.25, actor="Requester"):
    if not description or not description.strip(): raise ValueError("Complaint description is required.")
    if channel not in ("Email", "Phone", "Web", "Mobile App", "Social Media", "Support Portal"):
        raise ValueError("Unsupported complaint channel.")
    if not conn.execute("SELECT 1 FROM Customer WHERE customer_id=?", (customer_id,)).fetchone():
        raise ValueError("Select a valid customer.")
    if order_id:
        order = conn.execute('SELECT product_id,order_total,customer_id FROM "Order" WHERE order_id=?', (order_id,)).fetchone()
        if not order or order["customer_id"] != customer_id: raise ValueError("The selected order does not belong to this customer.")
        product_id = order["product_id"]; value = float(order["order_total"])
    else: value = 0.0
    vulnerable = bool(conn.execute("SELECT vulnerable_customer FROM Customer WHERE customer_id=?", (customer_id,)).fetchone()[0])
    category, severity = classify(description)
    recurrence = 1 + conn.execute('''SELECT COUNT(*) FROM Complaint c JOIN Category k USING(category_id)
        WHERE c.customer_id=? AND k.category_name=?''', (customer_id, category)).fetchone()[0]
    priority = determine_priority(category, severity, float(sentiment), value, recurrence, vulnerable)
    now = now_iso(); year = datetime.now().year
    n = conn.execute("SELECT COUNT(*) FROM Complaint WHERE complaint_id LIKE ?", (f"CMP-{year}-%",)).fetchone()[0] + 1
    cid = f"CMP-{year}-{n:06d}"
    cat = conn.execute("SELECT category_id,default_team FROM Category WHERE category_name=?", (category,)).fetchone()
    if not cat: raise ValueError(f"Category '{category}' is missing from the database.")
    conn.execute('''INSERT INTO Complaint(complaint_id,customer_id,order_id,product_id,channel,description,category_id,severity,
        sentiment_score,order_value,recurrence_count,priority_level,current_status,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (cid, customer_id, order_id or None, product_id, channel, description.strip(), cat["category_id"], severity,
         float(sentiment), value, recurrence, priority, "New", now, now))
    response_due, resolution_due = sla_deadlines(now, priority)
    conn.execute('''INSERT INTO SLAClock(sla_id,complaint_id,response_due_at,resolution_due_at,clock_status,paused_minutes)
        VALUES(?,?,?,?,?,0)''', (f"SLA-{cid}", cid, response_due, resolution_due, "Active"))
    conn.execute("INSERT INTO StatusEvent VALUES(?,?,?,?,?,?,?)", (f"EV-{cid}-001", cid, None, "New", now, actor, "Complaint created"))
    team = conn.execute("SELECT team_id FROM Team WHERE team_name=?", (cat["default_team"],)).fetchone()
    if team:
        assign_least_loaded(conn, cid, team[0], "System")
    _audit(conn, actor, "CREATE", "Complaint", cid, f"{category}; {priority}; {channel}")
    conn.commit(); return cid

def add_message(conn, complaint_id, sender_type, message_text, channel="Support Portal", visible=True, sender_id=None):
    if not message_text or not message_text.strip(): raise ValueError("Message cannot be empty.")
    if not conn.execute("SELECT 1 FROM Complaint WHERE complaint_id=?", (complaint_id,)).fetchone(): raise ValueError("Complaint not found.")
    n = conn.execute("SELECT COUNT(*) FROM ComplaintMessage WHERE complaint_id=?", (complaint_id,)).fetchone()[0] + 1
    mid = f"MSG-{complaint_id}-{n:03d}"; now = now_iso()
    conn.execute("INSERT INTO ComplaintMessage VALUES (?,?,?,?,?,?,?,?)",
                 (mid, complaint_id, sender_type, sender_id, channel, message_text.strip(), now, int(visible)))
    # Internal notes are not customer responses and must not stop the response SLA clock.
    if sender_type == "Agent" and visible:
        record_first_response(conn, complaint_id, sender_id or "Agent")
    _audit(conn, sender_id or sender_type, "ADD_MESSAGE", "Complaint", complaint_id, f"{sender_type} message")
    conn.commit(); return mid

def change_status(conn, complaint_id, new_status, actor="Operations", note="Status updated"):
    row = conn.execute("SELECT current_status FROM Complaint WHERE complaint_id=?", (complaint_id,)).fetchone()
    if not row: raise ValueError("Complaint not found")
    old = row[0]
    if new_status not in TRANSITIONS.get(old, set()): raise ValueError(f"Invalid transition: {old} -> {new_status}")
    now = now_iso(); n = conn.execute("SELECT COUNT(*) FROM StatusEvent WHERE complaint_id=?", (complaint_id,)).fetchone()[0] + 1
    conn.execute("INSERT INTO StatusEvent VALUES(?,?,?,?,?,?,?)", (f"EV-{complaint_id}-{n:03d}", complaint_id, old, new_status, now, actor, note))
    conn.execute("UPDATE Complaint SET current_status=?,updated_at=? WHERE complaint_id=?", (new_status, now, complaint_id))
    sla = conn.execute("SELECT * FROM SLAClock WHERE complaint_id=?", (complaint_id,)).fetchone()
    if sla and new_status == "Waiting for Customer" and sla["clock_status"] in ("Active", "Breached"):
        conn.execute("UPDATE SLAClock SET clock_status='Paused',pause_started_at=? WHERE complaint_id=?", (now, complaint_id))
        conn.execute("INSERT INTO SLAEvent VALUES(?,?,?,?,?)", (f"SE-{complaint_id}-PAUSE-{n}", complaint_id, "Paused", now, "Waiting for customer"))
    elif sla and old == "Waiting for Customer" and new_status != "Waiting for Customer" and sla["clock_status"] == "Paused":
        start = datetime.fromisoformat(sla["pause_started_at"] or now); end = datetime.fromisoformat(now)
        mins = max(0, int((end-start).total_seconds()/60))
        response_due = (datetime.fromisoformat(sla["response_due_at"]) + timedelta(minutes=mins)).isoformat(timespec="seconds")
        resolution_due = (datetime.fromisoformat(sla["resolution_due_at"]) + timedelta(minutes=mins)).isoformat(timespec="seconds")
        conn.execute("UPDATE SLAClock SET clock_status='Active',paused_minutes=paused_minutes+?,pause_started_at=NULL,resumed_at=?,response_due_at=?,resolution_due_at=? WHERE complaint_id=?",
                     (mins, now, response_due, resolution_due, complaint_id))
        conn.execute("INSERT INTO SLAEvent VALUES(?,?,?,?,?)", (f"SE-{complaint_id}-RESUME-{n}", complaint_id, "Resumed", now, f"Paused for {mins} minutes"))
    if new_status == "Resolved":
        conn.execute("UPDATE SLAClock SET resolved_at=?,clock_status='Completed' WHERE complaint_id=?", (now, complaint_id))
        conn.execute("INSERT INTO SLAEvent VALUES(?,?,?,?,?)", (f"SE-{complaint_id}-DONE-{n}", complaint_id, "Completed", now, "Resolved"))
        if not conn.execute("SELECT 1 FROM Resolution WHERE complaint_id=?", (complaint_id,)).fetchone():
            conn.execute("INSERT INTO Resolution(resolution_id,complaint_id,resolution_type,resolution_notes,refund_amount,resolved_at,resolved_by) VALUES(?,?,?,?,?,?,?)",
                         (f"RES-{complaint_id}", complaint_id, "Operational resolution", note or "Resolved", 0, now, actor))
        else:
            conn.execute("UPDATE Resolution SET resolution_notes=?,resolved_at=?,resolved_by=? WHERE complaint_id=?",
                         (note or "Resolved", now, actor, complaint_id))
    elif new_status == "Escalated":
        conn.execute("UPDATE SLAClock SET clock_status='Escalated' WHERE complaint_id=?", (complaint_id,))
        conn.execute("INSERT INTO SLAEvent VALUES(?,?,?,?,?)", (f"SE-{complaint_id}-ESC-{n}", complaint_id, "Escalated", now, note or "Manual escalation"))
    elif new_status == "Reopened":
        from services.rules import sla_deadlines
        complaint = conn.execute("SELECT priority_level FROM Complaint WHERE complaint_id=?", (complaint_id,)).fetchone()
        _, new_due = sla_deadlines(now, complaint["priority_level"])
        conn.execute("UPDATE SLAClock SET resolved_at=NULL,clock_status='Active',resolution_due_at=?,pause_started_at=NULL WHERE complaint_id=?", (new_due, complaint_id))
        conn.execute("INSERT INTO SLAEvent VALUES(?,?,?,?,?)", (f"SE-{complaint_id}-REOPEN-{n}", complaint_id, "Reopened", now, "Resolution clock restarted"))
    _audit(conn, actor, "STATUS_CHANGE", "Complaint", complaint_id, f"{old} -> {new_status}: {note}")
    conn.commit()
