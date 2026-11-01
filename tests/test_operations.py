import sqlite3
from database.db import initialize
from services.operations import authenticate, create_customer, evaluate_slas
from services.workflow import create_complaint, change_status


def make_db(tmp_path):
    conn = initialize(tmp_path / "test.db")
    conn.execute("INSERT INTO Team VALUES('T-BILL','Billing')")
    conn.execute("INSERT INTO Agent VALUES('A-1','Agent One','T-BILL',1)")
    conn.execute("INSERT INTO Category VALUES('CAT-PAY','Payment','Payment issue','Billing')")
    conn.execute("INSERT INTO Customer VALUES('CUS-1','Test Customer','test@example.com','123','Hyderabad',0,'2026-01-01T00:00:00')")
    conn.commit()
    return conn


def test_demo_authentication(tmp_path):
    conn = initialize(tmp_path / "auth.db")
    assert authenticate(conn, "admin", "Admin@123")["role"] == "Administrator"
    assert authenticate(conn, "admin", "wrong") is None
    conn.close()


def test_complaint_creation_and_auto_assignment(tmp_path):
    conn = make_db(tmp_path)
    cid = create_complaint(conn, "CUS-1", None, None, "Web", "I was charged twice for my payment", -0.7)
    assert conn.execute("SELECT current_status FROM Complaint WHERE complaint_id=?", (cid,)).fetchone()[0] == "New"
    assert conn.execute("SELECT agent_id FROM Assignment WHERE complaint_id=? AND is_current=1", (cid,)).fetchone()[0] == "A-1"
    assert conn.execute("SELECT clock_status FROM SLAClock WHERE complaint_id=?", (cid,)).fetchone()[0] == "Active"
    conn.close()


def test_sla_pause_resume_and_auto_escalation(tmp_path):
    conn = make_db(tmp_path)
    cid = create_complaint(conn, "CUS-1", None, None, "Web", "Payment charged twice", -0.5)
    change_status(conn, cid, "Triaged", "tester", "triage")
    change_status(conn, cid, "Assigned", "tester", "assign")
    change_status(conn, cid, "Waiting for Customer", "tester", "awaiting details")
    assert conn.execute("SELECT clock_status FROM SLAClock WHERE complaint_id=?", (cid,)).fetchone()[0] == "Paused"
    change_status(conn, cid, "In Progress", "tester", "customer replied")
    assert conn.execute("SELECT clock_status FROM SLAClock WHERE complaint_id=?", (cid,)).fetchone()[0] == "Active"
    conn.execute("UPDATE SLAClock SET resolution_due_at='2000-01-01T00:00:00',response_due_at='2000-01-01T00:00:00' WHERE complaint_id=?", (cid,))
    conn.commit()
    result = evaluate_slas(conn)
    assert result["escalated"] == 1
    assert conn.execute("SELECT current_status FROM Complaint WHERE complaint_id=?", (cid,)).fetchone()[0] == "Escalated"
    conn.close()


def test_automation_acknowledges_new_complaint_once(tmp_path):
    from services.automation import run_automation_cycle
    conn = make_db(tmp_path)
    cid = create_complaint(conn, "CUS-1", None, None, "Web", "Payment charged twice", -0.5)
    first = run_automation_cycle(conn)
    second = run_automation_cycle(conn)
    assert first["new_complaints"] == 1
    assert second["new_complaints"] == 0
    messages = conn.execute("SELECT COUNT(*) FROM ComplaintMessage WHERE complaint_id=? AND sender_type='System'", (cid,)).fetchone()[0]
    assert messages == 1
    assert conn.execute("SELECT COUNT(*) FROM Notification WHERE complaint_id=? AND channel='In-App'", (cid,)).fetchone()[0] >= 1
    conn.close()


def test_customer_reply_gets_safe_automated_ack_and_agent_alert(tmp_path):
    from services.automation import run_automation_cycle
    from services.workflow import add_message
    conn = make_db(tmp_path)
    cid = create_complaint(conn, "CUS-1", None, None, "Web", "Payment charged twice", -0.5)
    run_automation_cycle(conn)  # registration + assignment notifications
    add_message(conn, cid, "Customer", "I still need help with this charge", sender_id="requester")
    result = run_automation_cycle(conn)
    assert result["customer_replies"] == 1
    text = conn.execute("SELECT message_text FROM ComplaintMessage WHERE complaint_id=? AND sender_type='System' ORDER BY created_at DESC,rowid DESC LIMIT 1", (cid,)).fetchone()[0]
    assert "Do not share card numbers" in text
    assert conn.execute("SELECT 1 FROM Notification WHERE complaint_id=? AND subject LIKE 'New customer reply%'", (cid,)).fetchone()
    conn.close()


def test_sla_breach_creates_customer_and_agent_notifications(tmp_path):
    from services.automation import run_automation_cycle
    conn = make_db(tmp_path)
    cid = create_complaint(conn, "CUS-1", None, None, "Web", "Payment charged twice", -0.5)
    run_automation_cycle(conn)
    conn.execute("UPDATE SLAClock SET response_due_at='2000-01-01T00:00:00',resolution_due_at='2000-01-01T00:00:00' WHERE complaint_id=?", (cid,))
    conn.commit()
    result = run_automation_cycle(conn)
    assert result["sla_breaches"] == 1
    assert result["escalations"] == 1
    assert conn.execute("SELECT 1 FROM Notification WHERE complaint_id=? AND subject LIKE 'SLA deadline breached%'", (cid,)).fetchone()
    assert conn.execute("SELECT 1 FROM Notification WHERE complaint_id=? AND subject LIKE 'Complaint escalated%'", (cid,)).fetchone()
    conn.close()


def test_agent_reply_notifies_customer_without_duplicate_chat_message(tmp_path):
    from services.automation import run_automation_cycle
    from services.workflow import add_message
    conn = make_db(tmp_path)
    cid = create_complaint(conn, "CUS-1", None, None, "Web", "Payment charged twice", -0.5)
    run_automation_cycle(conn)
    before = conn.execute("SELECT COUNT(*) FROM ComplaintMessage WHERE complaint_id=?", (cid,)).fetchone()[0]
    add_message(conn, cid, "Agent", "I have reviewed your transaction", sender_id="agent-one", visible=True)
    result = run_automation_cycle(conn)
    after = conn.execute("SELECT COUNT(*) FROM ComplaintMessage WHERE complaint_id=?", (cid,)).fetchone()[0]
    assert result["agent_replies_notified"] == 1
    assert after == before + 1
    assert conn.execute("SELECT 1 FROM Notification WHERE complaint_id=? AND subject='Your support agent replied'", (cid,)).fetchone()
    conn.close()


def test_resolution_notification_is_created_once(tmp_path):
    from services.automation import run_automation_cycle
    conn = make_db(tmp_path)
    cid = create_complaint(conn, "CUS-1", None, None, "Web", "Payment charged twice", -0.5)
    run_automation_cycle(conn)
    change_status(conn, cid, "Triaged", "tester", "triage")
    change_status(conn, cid, "Assigned", "tester", "assigned")
    change_status(conn, cid, "In Progress", "tester", "working")
    change_status(conn, cid, "Resolved", "tester", "issue corrected")
    first = run_automation_cycle(conn)
    second = run_automation_cycle(conn)
    assert first["resolution_notifications"] == 1
    assert second["resolution_notifications"] == 0
    assert conn.execute("SELECT 1 FROM Notification WHERE complaint_id=? AND subject='Complaint resolution update'", (cid,)).fetchone()
    conn.close()


def test_internal_agent_note_does_not_stop_response_sla(tmp_path):
    from services.workflow import add_message
    conn = make_db(tmp_path)
    cid = create_complaint(conn, "CUS-1", None, None, "Web", "Payment charged twice", -0.5)
    add_message(conn, cid, "Agent", "Internal investigation note", visible=False, sender_id="A-1")
    assert conn.execute(
        "SELECT first_response_at FROM SLAClock WHERE complaint_id=?", (cid,)
    ).fetchone()[0] is None
    add_message(conn, cid, "Agent", "Customer-visible update", visible=True, sender_id="A-1")
    assert conn.execute(
        "SELECT first_response_at FROM SLAClock WHERE complaint_id=?", (cid,)
    ).fetchone()[0] is not None
    conn.close()


def test_sla_escalation_is_idempotent(tmp_path):
    conn = make_db(tmp_path)
    cid = create_complaint(conn, "CUS-1", None, None, "Web", "Payment charged twice", -0.5)
    conn.execute(
        "UPDATE SLAClock SET response_due_at='2000-01-01T00:00:00',resolution_due_at='2000-01-01T00:00:00' WHERE complaint_id=?",
        (cid,),
    )
    conn.commit()
    first = evaluate_slas(conn)
    second = evaluate_slas(conn)
    assert first["escalated"] == 1
    assert second == {"breached": 0, "escalated": 0}
    conn.close()
