PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS Customer (
 customer_id TEXT PRIMARY KEY, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 phone TEXT NOT NULL, city TEXT NOT NULL, vulnerable_customer INTEGER NOT NULL DEFAULT 0 CHECK(vulnerable_customer IN(0,1)),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS Product (
 product_id TEXT PRIMARY KEY, product_name TEXT NOT NULL, product_type TEXT NOT NULL,
 unit_price REAL NOT NULL CHECK(unit_price>=0), safety_sensitive INTEGER NOT NULL DEFAULT 0 CHECK(safety_sensitive IN(0,1)),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1))
);
CREATE TABLE IF NOT EXISTS "Order" (
 order_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES Customer(customer_id),
 product_id TEXT NOT NULL REFERENCES Product(product_id), order_date TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity>0), order_total REAL NOT NULL CHECK(order_total>=0),
 order_status TEXT NOT NULL CHECK(order_status IN('Placed','Shipped','Delivered','Cancelled','Returned'))
);
CREATE TABLE IF NOT EXISTS Category (
 category_id TEXT PRIMARY KEY, category_name TEXT NOT NULL UNIQUE, description TEXT NOT NULL, default_team TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS PriorityRule (
 rule_id TEXT PRIMARY KEY, rule_name TEXT NOT NULL, condition_key TEXT NOT NULL, condition_value TEXT NOT NULL,
 priority_level TEXT NOT NULL CHECK(priority_level IN('Critical','High','Medium','Low')),
 precedence INTEGER NOT NULL, effective_from TEXT NOT NULL, effective_to TEXT, active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS Team (team_id TEXT PRIMARY KEY, team_name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS Agent (
 agent_id TEXT PRIMARY KEY, agent_name TEXT NOT NULL, team_id TEXT NOT NULL REFERENCES Team(team_id),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1))
);
CREATE TABLE IF NOT EXISTS Complaint (
 complaint_id TEXT PRIMARY KEY, customer_id TEXT REFERENCES Customer(customer_id),
 order_id TEXT REFERENCES "Order"(order_id), product_id TEXT REFERENCES Product(product_id),
 channel TEXT NOT NULL CHECK(channel IN('Email','Phone','Web','Mobile App','Social Media','Support Portal')),
 description TEXT NOT NULL, category_id TEXT REFERENCES Category(category_id),
 severity TEXT NOT NULL CHECK(severity IN('Critical','High','Moderate','Low')),
 sentiment_score REAL NOT NULL CHECK(sentiment_score BETWEEN -1 AND 1), order_value REAL NOT NULL DEFAULT 0,
 recurrence_count INTEGER NOT NULL DEFAULT 1 CHECK(recurrence_count>=1),
 priority_level TEXT NOT NULL CHECK(priority_level IN('Critical','High','Medium','Low')),
 current_status TEXT NOT NULL CHECK(current_status IN('New','Triaged','Assigned','In Progress','Waiting for Customer','Resolved','Closed','Reopened','Escalated')),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ComplaintMessage (
 message_id TEXT PRIMARY KEY, complaint_id TEXT NOT NULL REFERENCES Complaint(complaint_id),
 sender_type TEXT NOT NULL CHECK(sender_type IN('Customer','Agent','System')), sender_id TEXT,
 channel TEXT NOT NULL, message_text TEXT NOT NULL, created_at TEXT NOT NULL,
 is_customer_visible INTEGER NOT NULL DEFAULT 1 CHECK(is_customer_visible IN(0,1))
);
CREATE TABLE IF NOT EXISTS Assignment (
 assignment_id TEXT PRIMARY KEY, complaint_id TEXT NOT NULL REFERENCES Complaint(complaint_id),
 team_id TEXT NOT NULL REFERENCES Team(team_id), agent_id TEXT NOT NULL REFERENCES Agent(agent_id),
 assigned_at TEXT NOT NULL, assigned_by TEXT NOT NULL, reason TEXT NOT NULL,
 is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN(0,1))
);
CREATE TABLE IF NOT EXISTS SLAClock (
 sla_id TEXT PRIMARY KEY, complaint_id TEXT NOT NULL UNIQUE REFERENCES Complaint(complaint_id),
 response_due_at TEXT NOT NULL, resolution_due_at TEXT NOT NULL, first_response_at TEXT,
 resolved_at TEXT, clock_status TEXT NOT NULL CHECK(clock_status IN('Active','Paused','Completed','Breached','Escalated')),
 paused_minutes INTEGER NOT NULL DEFAULT 0, pause_started_at TEXT, resumed_at TEXT
);
CREATE TABLE IF NOT EXISTS Resolution (
 resolution_id TEXT PRIMARY KEY, complaint_id TEXT NOT NULL UNIQUE REFERENCES Complaint(complaint_id),
 resolution_type TEXT NOT NULL, resolution_notes TEXT NOT NULL, refund_amount REAL NOT NULL DEFAULT 0 CHECK(refund_amount>=0),
 resolved_at TEXT NOT NULL, resolved_by TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS Survey (
 survey_id TEXT PRIMARY KEY, complaint_id TEXT NOT NULL UNIQUE REFERENCES Complaint(complaint_id),
 sent_at TEXT NOT NULL, response_at TEXT, satisfaction_score INTEGER CHECK(satisfaction_score BETWEEN 1 AND 5), comments TEXT
);
CREATE TABLE IF NOT EXISTS StatusEvent (
 event_id TEXT PRIMARY KEY, complaint_id TEXT NOT NULL REFERENCES Complaint(complaint_id),
 from_status TEXT, to_status TEXT NOT NULL, changed_at TEXT NOT NULL, changed_by TEXT NOT NULL, note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS SLAEvent (
 sla_event_id TEXT PRIMARY KEY, complaint_id TEXT NOT NULL REFERENCES Complaint(complaint_id),
 event_type TEXT NOT NULL, event_at TEXT NOT NULL, details TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS AnomalyIssue (
 issue_id TEXT PRIMARY KEY, complaint_id TEXT NOT NULL REFERENCES Complaint(complaint_id),
 issue_type TEXT NOT NULL, ground_truth_label TEXT NOT NULL, description TEXT NOT NULL,
 detected INTEGER NOT NULL DEFAULT 0 CHECK(detected IN(0,1)), detected_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_complaint_status ON Complaint(current_status);
CREATE INDEX IF NOT EXISTS ix_complaint_priority ON Complaint(priority_level);
CREATE INDEX IF NOT EXISTS ix_message_complaint ON ComplaintMessage(complaint_id);
CREATE INDEX IF NOT EXISTS ix_complaint_customer ON Complaint(customer_id,created_at);
CREATE INDEX IF NOT EXISTS ix_complaint_category ON Complaint(category_id,created_at);
CREATE INDEX IF NOT EXISTS ix_complaint_created ON Complaint(created_at);
CREATE INDEX IF NOT EXISTS ix_assignment_agent_current ON Assignment(agent_id,is_current);
CREATE INDEX IF NOT EXISTS ix_status_event_case ON StatusEvent(complaint_id,changed_at);
CREATE INDEX IF NOT EXISTS ix_sla_status_due ON SLAClock(clock_status,resolution_due_at);
-- Composite indexes for the most common operational queue and history lookups.
CREATE INDEX IF NOT EXISTS ix_complaint_queue ON Complaint(current_status,priority_level,created_at);
CREATE INDEX IF NOT EXISTS ix_message_case_created ON ComplaintMessage(complaint_id,created_at);
CREATE INDEX IF NOT EXISTS ix_status_case_created ON StatusEvent(complaint_id,changed_at);

