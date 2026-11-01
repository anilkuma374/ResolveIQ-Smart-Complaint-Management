# ResolveIQ background automation and customer communication

## What runs every 30 seconds

Run `python -m services.automation_worker --interval 30` in a separate terminal. The worker loops independently of Streamlit and:

1. Finds newly registered complaints and posts a customer-visible registration acknowledgement.
2. Notifies the currently assigned agent in the in-app notification centre.
3. Finds new customer messages, posts a safe category-specific first response and alerts the assigned agent.
4. Notifies customers when an agent posts a customer-visible reply (internal notes are not sent to customers).
5. Evaluates response and resolution SLA deadlines.
5. Changes overdue eligible complaints to `Escalated`, records status/SLA/audit events and notifies the customer and administrators/assigned team.
6. Detects newly resolved complaints and sends a resolution update.
7. Retries email notifications that failed or were skipped before SMTP was configured.

The worker is idempotent: `AutomationEvent` stores processed event keys, and notification rows have a uniqueness constraint so polling the same records does not create repeated acknowledgements or alerts. On first initialization, the worker marks the bundled historical sample records as baseline so it does not send thousands of notifications or escalate old sample complaints. SLA monitoring applies to complaints created after that baseline time.

## Customer reply and conversation history

Requester accounts linked to a `Customer` record can open **My Complaints**, view customer-visible conversation history and submit a reply. Agent responses and automated system messages are stored in `ComplaintMessage`. Internal notes should be saved with `is_customer_visible=0`.

## Email delivery (optional)

In-app messages and notifications work without an email account. To enable real outbound email:

1. Copy `.env.example` to `.env` in the project root.
2. Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, and `SMTP_USE_TLS`.
3. For Gmail, use an app password (not the normal account password) and ensure account 2-step verification is enabled.
4. Stop and restart the automation worker so it loads the new settings.

Email delivery status is stored in `Notification`. If SMTP is not configured, email rows are marked `Not configured` and retried after SMTP settings are added. If delivery fails, the error is stored and retried on later worker cycles.

## Important safety boundary

Automated responses are acknowledgements and conservative first-line guidance. They do not issue refunds, replace products, repair devices, change account credentials, or mark a complaint resolved. Those actions require an authorized agent and a successful action in the relevant business system. Product-safety responses advise the customer to stop using an unsafe product and contact emergency services if there is immediate danger. A case is only marked resolved by an authorized workflow action.

## SLA behavior

The worker evaluates the stored response and resolution deadlines every 30 seconds. It does not run while the worker process is stopped or the computer is asleep. The prototype uses the existing elapsed-hour SLA targets and local naive timestamps; production deployment should use timezone-aware UTC timestamps, business calendars, durable process supervision and monitoring.

## Start the application on Windows

Recommended: double-click `run_resolveiq.bat` from the extracted project folder. It opens the automation worker in a separate terminal and runs Streamlit in the current terminal.

Or use two PowerShell windows, both opened in the project folder:

Terminal 1:

```powershell
python -m services.automation_worker --interval 30
```

Terminal 2:

```powershell
python -m streamlit run app.py
```

Keep both windows open. Closing the worker terminal stops background automation; closing the Streamlit terminal stops the web application.
