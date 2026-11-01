# Data Dictionary

All IDs are immutable text primary keys. Timestamps use ISO-8601 in this synthetic prototype; production should store UTC.

| Entity | Important fields | Type / validation |
|---|---|---|
| Customer | customer_id, full_name, email, phone, city, vulnerable_customer, created_at | PK `CUS-000001`; email unique; flag 0/1; synthetic-only |
| Product | product_id, product_name, product_type, unit_price, safety_sensitive, active | PK; price >= 0; flags 0/1 |
| Order | order_id, customer_id, product_id, order_date, quantity, order_total, order_status | PK `ORD-2026-000001`; FKs Customer/Product; quantity > 0; total >= 0 |
| Complaint | complaint_id, customer_id, order_id, product_id, channel, description, category_id, severity, sentiment_score, order_value, recurrence_count, priority_level, current_status, created_at, updated_at | PK `CMP-2026-000001`; optional FKs support labelled intake exceptions; sentiment -1..1; recurrence >= 1 |
| ComplaintMessage | message_id, complaint_id, sender_type, sender_id, channel, message_text, created_at, is_customer_visible | PK `MSG-<complaint-id>-001`; FK Complaint; sender Customer/Agent/System; visibility 0/1 |
| Category | category_id, category_name, description, default_team | PK; category_name unique; 10 controlled categories |
| PriorityRule | rule_id, rule_name, condition_key, condition_value, priority_level, precedence, effective_from, effective_to, active | PK; priority Critical/High/Medium/Low; lower precedence number runs first |
| Assignment | assignment_id, complaint_id, team_id, agent_id, assigned_at, assigned_by, reason, is_current | PK; FKs Complaint/Team/Agent; history retained; current flag 0/1 |
| SLAClock | sla_id, complaint_id, response_due_at, resolution_due_at, first_response_at, resolved_at, clock_status, paused_minutes, pause_started_at, resumed_at | PK `SLA-<complaint-id>`; unique FK Complaint; pause duration minutes >= 0 |
| Resolution | resolution_id, complaint_id, resolution_type, resolution_notes, refund_amount, resolved_at, resolved_by | PK `RES-<complaint-id>`; unique FK Complaint; refund >= 0 |
| Survey | survey_id, complaint_id, sent_at, response_at, satisfaction_score, comments | PK; unique FK Complaint; score 1..5 |
| Team / Agent | team_id, team_name / agent_id, agent_name, team_id, active | Supporting routing entities; Agent FK Team |
| StatusEvent / SLAEvent | event IDs, complaint_id, event type/status, timestamps, actor, notes | Append-only event history; FK Complaint |
| AnomalyIssue | issue_id, complaint_id, issue_type, ground_truth_label, description, detected, detected_at | Labelled exception register; FK Complaint |

## Relationships and cardinality
- Customer 1:N Order; Customer 1:N Complaint (customer reference is nullable only for the explicit missing-customer exception).
- Product 1:N Order and Product 1:N Complaint.
- Order 1:N Complaint; Category 1:N Complaint.
- Complaint 1:N ComplaintMessage, Assignment, StatusEvent, SLAEvent and AnomalyIssue.
- Complaint 1:1 SLAClock; Complaint 0:1 Resolution; Complaint 0:1 Survey.
- Team 1:N Agent and Team 1:N Assignment; Agent 1:N Assignment.
- Optional relationships: Complaint may have no order/product/customer while intake is being verified.
