"""Operational services: customer CRUD, SLA automation, workload routing and data quality."""
from datetime import datetime, timezone
import hashlib, hmac, os, secrets

STATUSES = ["New", "Triaged", "Assigned", "In Progress", "Waiting for Customer", "Resolved", "Closed", "Reopened", "Escalated"]
ROLES = ["Administrator", "Agent", "Analyst", "Requester"]

def now_iso():
    return datetime.now().replace(microsecond=0).isoformat()

def _audit(conn, actor, action, entity_type, entity_id, details=""):
    conn.execute("INSERT INTO AuditLog(actor,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?)",
                 (actor, action, entity_type, str(entity_id), details, now_iso()))

def ensure_extensions(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS AppUser(
      user_id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
      salt TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('Administrator','Agent','Analyst','Requester')),
      display_name TEXT NOT NULL, agent_id TEXT, active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS AuditLog(
      audit_id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT NOT NULL, action TEXT NOT NULL,
      entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_audit_created ON AuditLog(created_at);
    CREATE TABLE IF NOT EXISTS Notification(
      notification_id TEXT PRIMARY KEY, event_key TEXT NOT NULL, complaint_id TEXT,
      recipient_type TEXT NOT NULL, recipient_id TEXT NOT NULL, channel TEXT NOT NULL,
      subject TEXT NOT NULL, body TEXT NOT NULL, delivery_status TEXT NOT NULL,
      created_at TEXT NOT NULL, sent_at TEXT, error_text TEXT,
      UNIQUE(event_key, recipient_type, recipient_id, channel)
    );
    CREATE INDEX IF NOT EXISTS ix_notification_recipient ON Notification(recipient_type,recipient_id,created_at);
    CREATE TABLE IF NOT EXISTS AutomationEvent(
      event_key TEXT PRIMARY KEY, event_type TEXT NOT NULL, complaint_id TEXT,
      processed_at TEXT NOT NULL, details TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS AutomationHeartbeat(
      worker_name TEXT PRIMARY KEY, last_seen_at TEXT NOT NULL, last_result TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS AutomationSetting(
      setting_key TEXT PRIMARY KEY, setting_value TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_assignment_current ON Assignment(is_current,agent_id);
    CREATE INDEX IF NOT EXISTS ix_sla_due ON SLAClock(clock_status,resolution_due_at);
    ''')
    # One-time migration baseline: do not send emails for the thousands of historical
    # sample complaints already present in the bundled academic database.
    baseline = conn.execute("SELECT 1 FROM AutomationSetting WHERE setting_key='initial_backfill_done'").fetchone()
    if not baseline:
        stamp = now_iso()
        conn.execute("INSERT OR IGNORE INTO AutomationEvent(event_key,event_type,complaint_id,processed_at,details) SELECT 'complaint-registered:'||complaint_id,'BASELINE',complaint_id,?,'Existing record before automation was enabled' FROM Complaint", (stamp,))
        conn.execute("INSERT OR IGNORE INTO AutomationEvent(event_key,event_type,complaint_id,processed_at,details) SELECT 'customer-message-reply:'||message_id,'BASELINE',complaint_id,?,'Existing message before automation was enabled' FROM ComplaintMessage WHERE sender_type='Customer'", (stamp,))
        conn.execute("INSERT OR IGNORE INTO AutomationEvent(event_key,event_type,complaint_id,processed_at,details) SELECT 'agent-message-notification:'||message_id,'BASELINE',complaint_id,?,'Existing agent message before automation was enabled' FROM ComplaintMessage WHERE sender_type='Agent'", (stamp,))
        conn.execute("INSERT OR IGNORE INTO AutomationEvent(event_key,event_type,complaint_id,processed_at,details) SELECT 'assignment-event:'||assignment_id,'BASELINE',complaint_id,?,'Existing assignment before automation was enabled' FROM Assignment", (stamp,))
        conn.execute("INSERT OR IGNORE INTO AutomationEvent(event_key,event_type,complaint_id,processed_at,details) SELECT 'sla-event:'||sla_event_id,'BASELINE',complaint_id,?,'Existing SLA event before automation was enabled' FROM SLAEvent", (stamp,))
        conn.execute("INSERT OR IGNORE INTO AutomationEvent(event_key,event_type,complaint_id,processed_at,details) SELECT 'resolution:'||event_id,'BASELINE',complaint_id,?,'Existing resolution before automation was enabled' FROM StatusEvent WHERE to_status='Resolved'", (stamp,))
        conn.execute("INSERT INTO AutomationSetting(setting_key,setting_value) VALUES('initial_backfill_done',?)", (stamp,))
    columns = {r[1] for r in conn.execute("PRAGMA table_info(AppUser)").fetchall()}
    if "customer_id" not in columns:
        conn.execute("ALTER TABLE AppUser ADD COLUMN customer_id TEXT")
    # Create safe local demo accounts once. Change these credentials before any real deployment.
    defaults = [("admin", "Admin@123", "Administrator", "System Administrator"),
                ("agent", "Agent@123", "Agent", "Demo Support Agent"),
                ("analyst", "Analyst@123", "Analyst", "Operations Analyst"),
                ("requester", "Request@123", "Requester", "Demo Requester")]
    for username, password, role, display in defaults:
        if not conn.execute("SELECT 1 FROM AppUser WHERE username=?", (username,)).fetchone():
            salt = secrets.token_hex(16)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180000).hex()
            conn.execute("INSERT INTO AppUser(user_id,username,password_hash,salt,role,display_name,agent_id,active,created_at) VALUES(?,?,?,?,?,?,NULL,1,?)",
                         (f"USR-{username.upper()}", username, digest, salt, role, display, now_iso()))
    first_agent = conn.execute("SELECT agent_id FROM Agent WHERE active=1 ORDER BY agent_id LIMIT 1").fetchone()
    if first_agent:
        conn.execute("UPDATE AppUser SET agent_id=? WHERE username='agent' AND agent_id IS NULL", (first_agent[0],))
    first_customer = conn.execute("SELECT customer_id FROM Customer ORDER BY customer_id LIMIT 1").fetchone()
    if first_customer:
        conn.execute("UPDATE AppUser SET customer_id=? WHERE username='requester' AND customer_id IS NULL", (first_customer[0],))
    conn.commit()

def authenticate(conn, username, password):
    row = conn.execute("SELECT * FROM AppUser WHERE username=? AND active=1", (username.strip(),)).fetchone()
    if not row: return None
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), row["salt"].encode(), 180000).hex()
    if not hmac.compare_digest(digest, row["password_hash"]): return None
    return {"username": row["username"], "role": row["role"], "display_name": row["display_name"], "agent_id": row["agent_id"], "customer_id": row["customer_id"]}

def create_customer(conn, full_name, email, phone, city, vulnerable=False, actor="Administrator"):
    if not full_name.strip() or not email.strip() or "@" not in email:
        raise ValueError("Enter a customer name and a valid email address.")
    cid = "CUS-" + secrets.token_hex(5).upper()
    conn.execute("INSERT INTO Customer(customer_id,full_name,email,phone,city,vulnerable_customer,created_at) VALUES(?,?,?,?,?,?,?)",
                 (cid, full_name.strip(), email.strip().lower(), phone.strip(), city.strip(), int(vulnerable), now_iso()))
    _audit(conn, actor, "CREATE", "Customer", cid, email)
    conn.commit(); return cid

def update_customer(conn, customer_id, full_name, email, phone, city, vulnerable=False, actor="Administrator"):
    if not full_name.strip() or "@" not in email:
        raise ValueError("Enter a customer name and valid email address.")
    conn.execute("UPDATE Customer SET full_name=?,email=?,phone=?,city=?,vulnerable_customer=? WHERE customer_id=?",
                 (full_name.strip(), email.strip().lower(), phone.strip(), city.strip(), int(vulnerable), customer_id))
    _audit(conn, actor, "UPDATE", "Customer", customer_id, "Customer profile updated")
    conn.commit()

def assign_least_loaded(conn, complaint_id, team_id, actor="System"):
    agents = conn.execute('''SELECT a.agent_id, COUNT(c.complaint_id) workload
        FROM Agent a LEFT JOIN Assignment x ON x.agent_id=a.agent_id AND x.is_current=1
        LEFT JOIN Complaint c ON c.complaint_id=x.complaint_id AND c.current_status NOT IN ('Resolved','Closed')
        WHERE a.team_id=? AND a.active=1 GROUP BY a.agent_id ORDER BY workload,a.agent_id''', (team_id,)).fetchall()
    if not agents: return None
    chosen = agents[0]["agent_id"]
    conn.execute("UPDATE Assignment SET is_current=0 WHERE complaint_id=? AND is_current=1", (complaint_id,))
    n = conn.execute("SELECT COUNT(*) FROM Assignment WHERE complaint_id=?", (complaint_id,)).fetchone()[0] + 1
    conn.execute("INSERT INTO Assignment VALUES(?,?,?,?,?,?,?,1)",
                 (f"ASN-{complaint_id}-{n:03d}", complaint_id, team_id, chosen, now_iso(), actor,
                  f"Least-loaded active agent; workload={agents[0]['workload']}"))
    _audit(conn, actor, "ASSIGN", "Complaint", complaint_id, f"Assigned to {chosen}")
    conn.commit(); return chosen

def evaluate_slas(conn, actor="System"):
    """Evaluate open clocks; mark breaches and escalate complaints once, safely and idempotently."""
    now = datetime.now()
    baseline = conn.execute("SELECT setting_value FROM AutomationSetting WHERE setting_key='initial_backfill_done'").fetchone()
    monitoring_start = baseline[0] if baseline else "0001-01-01T00:00:00"
    rows = conn.execute("""SELECT s.*,c.current_status,c.priority_level FROM SLAClock s
        JOIN Complaint c USING(complaint_id) WHERE s.clock_status IN ('Active','Breached','Escalated')
        AND c.current_status NOT IN ('Resolved','Closed') AND c.created_at>=?""", (monitoring_start,)).fetchall()
    breached = escalated = 0
    for row in rows:
        due = datetime.fromisoformat(row["resolution_due_at"])
        response_due = datetime.fromisoformat(row["response_due_at"])
        response_missed = ((row["first_response_at"] is None and now > response_due) or
                           (row["first_response_at"] is not None and datetime.fromisoformat(row["first_response_at"]) > response_due))
        resolution_missed = now > due
        if response_missed or resolution_missed:
            if row["clock_status"] == "Active":
                conn.execute("UPDATE SLAClock SET clock_status='Breached' WHERE sla_id=?", (row["sla_id"],))
                conn.execute("INSERT INTO SLAEvent VALUES(?,?,?,?,?)", (f"SE-{row['complaint_id']}-BREACH-{now.strftime('%Y%m%d%H%M%S')}", row["complaint_id"], "Breached", now_iso(), "Automated SLA evaluation"))
                _audit(conn, actor, "SLA_BREACH", "Complaint", row["complaint_id"], "Response or resolution deadline exceeded")
                breached += 1
            if row["current_status"] not in ("Escalated", "Resolved", "Closed"):
                old = row["current_status"]
                conn.execute("UPDATE Complaint SET current_status='Escalated',updated_at=? WHERE complaint_id=?", (now_iso(), row["complaint_id"]))
                n = conn.execute("SELECT COUNT(*) FROM StatusEvent WHERE complaint_id=?", (row["complaint_id"],)).fetchone()[0] + 1
                conn.execute("INSERT INTO StatusEvent VALUES(?,?,?,?,?,?,?)", (f"EV-{row['complaint_id']}-{n:03d}", row["complaint_id"], old, "Escalated", now_iso(), actor, "Automatic escalation: SLA deadline exceeded"))
                conn.execute("UPDATE SLAClock SET clock_status='Escalated' WHERE sla_id=?", (row["sla_id"],))
                escalation_event = f"SE-{row['complaint_id']}-ESC-AUTO-{now.strftime('%Y%m%d%H%M%S')}"
                conn.execute("INSERT OR IGNORE INTO SLAEvent VALUES(?,?,?,?,?)", (escalation_event, row["complaint_id"], "Escalated", now_iso(), "Automatic escalation after SLA breach"))
                _audit(conn, actor, "AUTO_ESCALATION", "Complaint", row["complaint_id"], "Automatically escalated after SLA breach")
                escalated += 1
    conn.commit()
    return {"breached": breached, "escalated": escalated}

def run_data_quality(conn, actor="System"):
    """Run live checks and upsert detected issues without overwriting ground-truth labels."""
    checks = []
    dupes = conn.execute('''SELECT customer_id, lower(trim(description)) description_key, COUNT(*) n,
        MIN(complaint_id) complaint_id FROM Complaint GROUP BY customer_id,lower(trim(description)) HAVING COUNT(*)>1''').fetchall()
    for r in dupes: checks.append((r["complaint_id"], "Potential duplicate", f"{r['n']} similar complaints for one customer"))
    missing = conn.execute("SELECT complaint_id FROM Complaint WHERE customer_id IS NULL OR trim(description)='' OR category_id IS NULL").fetchall()
    for r in missing: checks.append((r["complaint_id"], "Missing required data", "Customer, description, or category is missing"))
    bad_sla = conn.execute('''SELECT s.complaint_id FROM SLAClock s JOIN Complaint c USING(complaint_id) WHERE s.response_due_at>s.resolution_due_at
        OR (s.resolved_at IS NOT NULL AND s.resolved_at<c.created_at)''').fetchall()
    for r in bad_sla: checks.append((r["complaint_id"], "SLA chronology", "SLA timestamps require review"))
    for cid, kind, desc in checks:
        exists = conn.execute("SELECT issue_id FROM AnomalyIssue WHERE complaint_id=? AND issue_type=?", (cid, kind)).fetchone()
        if exists:
            conn.execute("UPDATE AnomalyIssue SET detected=1,detected_at=? WHERE issue_id=?", (now_iso(), exists[0]))
        else:
            iid = "ANM-" + secrets.token_hex(5).upper()
            conn.execute("INSERT INTO AnomalyIssue(issue_id,complaint_id,issue_type,ground_truth_label,description,detected,detected_at) VALUES(?,?,?,?,?,1,?)",
                         (iid, cid, kind, "Live detection", desc, now_iso()))
    _audit(conn, actor, "DATA_QUALITY_SCAN", "System", "all", f"{len(checks)} issue(s) found")
    conn.commit(); return len(checks)

def record_first_response(conn, complaint_id, actor="Agent"):
    now = now_iso()
    current = conn.execute("SELECT first_response_at FROM SLAClock WHERE complaint_id=?", (complaint_id,)).fetchone()
    if current and current["first_response_at"] is None:
        conn.execute("UPDATE SLAClock SET first_response_at=? WHERE complaint_id=?", (now, complaint_id))
        event_no = conn.execute("SELECT COUNT(*) FROM SLAEvent WHERE complaint_id=?", (complaint_id,)).fetchone()[0] + 1
        conn.execute("INSERT INTO SLAEvent VALUES(?,?,?,?,?)", (f"SE-{complaint_id}-RESP-{event_no:03d}", complaint_id, "First response", now, actor))
        _audit(conn, actor, "FIRST_RESPONSE", "Complaint", complaint_id, "First response recorded")
    conn.commit()


def create_user(conn, username, password, role, display_name, actor="Administrator"):
    if len(password) < 10: raise ValueError("Password must contain at least 10 characters.")
    if role not in ROLES: raise ValueError("Invalid role.")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180000).hex()
    uid = "USR-" + secrets.token_hex(5).upper()
    conn.execute("INSERT INTO AppUser(user_id,username,password_hash,salt,role,display_name,created_at) VALUES(?,?,?,?,?,?,?)",
                 (uid, username.strip(), digest, salt, role, display_name.strip(), now_iso()))
    _audit(conn, actor, "CREATE_USER", "AppUser", uid, f"{username}; {role}")
    conn.commit(); return uid
