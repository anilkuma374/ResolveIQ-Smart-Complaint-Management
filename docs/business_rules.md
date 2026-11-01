# Business Rules

## Classification
Keyword-based deterministic rules classify safety, defect, refund, payment, delivery, warranty, account, cancellation and service issues; unmatched text becomes Other. Safety terms have first precedence. This is explainable rules-based classification, not a trained machine-learning model.

## Priority
Priority precedence: (1) safety or Critical severity => Critical; (2) recurrence >= 3 => High or Critical for very negative sentiment; (3) vulnerable synthetic customer plus negative sentiment => High; (4) High severity or high-value order plus negative sentiment => High; (5) very negative sentiment => High; (6) moderate severity, recurrence=2 or order value >= 25,000 => Medium; otherwise Low. Safety always overrides other factors.

## Illustrative elapsed-hour SLA targets
| Priority | First response | Resolution |
|---|---:|---:|
| Critical | 15 minutes | 4 hours |
| High | 1 hour | 24 hours |
| Medium | 4 hours | 72 hours |
| Low | 8 hours | 120 hours |

Targets are configurable business assumptions, not supplied contractual commitments. The prototype does not yet apply business calendars or holidays. The SLA clock pauses in Waiting for Customer; on resume, paused minutes are added to response and resolution deadlines. A missed response or resolution target marks the clock breached and moves an eligible complaint to Escalated during the next SLA evaluation.

## Assignment
Category maps to its configured default team. Among active agents in that team, the agent with the smallest number of currently open assigned complaints is selected. Reassignment closes the prior current assignment and creates a new Assignment event.

## Lifecycle
Status changes are validated against an allowed transition map in `services/workflow.py`. Every accepted change appends StatusEvent and an audit entry. Resolving a complaint completes its SLA clock and creates a Resolution record. Reopened cases preserve previous history.

## Authentication and roles
Local demo accounts use salted PBKDF2-HMAC-SHA256 password hashes. Roles are Administrator, Agent, Analyst and Requester. The requester account is linked to a single seeded customer; the agent account is linked to a seeded agent. This is a demonstration access layer, not a substitute for enterprise SSO, MFA, hardened sessions or a production authorization review.

## Data quality
The live scanner checks for repeated normalized complaint descriptions for the same customer, missing customer/description/category values, and invalid SLA/resolution chronology. Existing generator labels remain distinct from live scan results.

## Edge cases
The generator injects six labelled scenarios: complaint without customer, resolution before complaint, incorrect SLA pause chronology, unlinked repeat issue, critical safety issue assigned to Customer Care, and survey before closure. `ground_truth.csv/json` is separate from input features.
