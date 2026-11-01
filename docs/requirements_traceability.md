# Problem Requirement Traceability

| Requirement | Implementation | Application area |
|---|---|---|
| Customer management | Create, edit, list, and view customer complaint history | Customer Directory |
| Complaint registration | Validated intake form linked to customer and optional order | Register Complaint |
| Order management | List and create customer orders; link orders to complaints | Products & Orders / Register Complaint |
| Product management | Product catalogue and product creation | Products & Orders |
| Complaint categorization | Deterministic keyword classification | Complaint intake / `services/rules.py` |
| Priority assignment | Severity, sentiment, order value, recurrence and vulnerable-customer rules | Complaint intake / `services/rules.py` |
| Agent assignment | Least-loaded active agent within category team | Complaint intake / `services/operations.py` |
| Status tracking | Validated state transitions and event history | Complaint Workbench |
| SLA monitoring | Response and resolution deadlines, pause/resume and breach state | SLA & Escalations |
| Escalation management | Deadline breaches automatically escalate eligible open cases on evaluation | SLA & Escalations / Overview |
| Communication management | Customer-visible or internal messages and conversation history | Complaint Workbench |
| Anomaly detection | Explainable duplicate, missing-field and chronology checks | Data Quality |
| Dashboard and reports | KPIs, charts, team workload, agent snapshot and CSV exports | Overview / Reports & Analytics |
| Security / access | Password-hash authentication and role-based navigation | Sign in / Administration |
| Auditability | AuditLog records for important actions | Administration |

## Acceptance test summary

Run `python -m pytest -q` for the automated unit/workflow tests and `python scripts/validate_data.py` for seeded-database integrity checks. The validator expects two deliberately injected chronology exceptions and confirms that they are labelled.
