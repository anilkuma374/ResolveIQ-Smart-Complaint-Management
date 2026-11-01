# ResolveIQ — Smart Complaint Management System

ResolveIQ is a Streamlit-based customer complaint operations prototype built with Python, SQLite, Pandas and Plotly. It demonstrates an end-to-end complaint lifecycle: customer intake, rule-based classification, priority calculation, agent assignment, SLA tracking, escalation, customer communication, operational reporting and data-quality checks.

> **Demo scope:** This repository contains synthetic demonstration data and local demo accounts. It is a portfolio/interview prototype, not a production customer-data platform. See [Prototype limitations](#prototype-limitations) before deployment.

## 1. Requirements

- Windows 10/11 (PowerShell) or another Python-supported operating system.
- Python 3.10 or newer. Python 3.11 is recommended.
- Internet access for the first dependency installation.
- About 500 MB of free disk space is recommended for the virtual environment and sample database.

Check Python from PowerShell:

```powershell
py --version
```

If `py` is not recognised, install Python from https://www.python.org/downloads/ and select **Add python.exe to PATH** during installation. Reopen PowerShell after installation.

## 2. Install on Windows (PowerShell)

1. Extract the ZIP file (right-click → **Extract All**).
2. Open the folder that directly contains `app.py`, `requirements.txt`, `database`, `services` and `tests`. This is the `smart_complaint_management_system` folder, which may be nested inside another folder with the ZIP's name.
3. In File Explorer, click the folder address bar, type `powershell`, and press Enter. PowerShell opens in that folder.
4. Run the following commands one at a time:

```powershell
# If you extracted the ZIP, the project is inside a nested folder. Move into it:
cd .\smart_complaint_management_system

# Confirm that you are in the project root (both must print True)
Test-Path .\app.py
Test-Path .\requirements.txt

# Create the virtual environment
py -3 -m venv .venv

# Allow scripts for this PowerShell window only, then activate
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1

# Install dependencies (the prompt should now start with "(.venv)")
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `cd` reports that the path does not exist, you are already inside it (or one level too deep): run `Get-ChildItem` to see the folders, then `cd` into the one that contains `app.py`. If either `Test-Path` returns `False`, you are in the wrong folder.

If the `py` launcher is unavailable but `python --version` works, use `python -m venv .venv` instead of `py -3 -m venv .venv`.

If a previous attempt left a broken `.venv` folder, delete it (`Remove-Item -Recurse -Force .venv`) and repeat step 4.

## 3. Run the application

The ZIP includes a populated SQLite database at `data/complaints.db`. You do **not** need to regenerate the sample data for the first run.

### Option A — Run manually (recommended)

Open **two PowerShell windows**, both in the project root (the folder containing `app.py`).

**Window 1 — Streamlit interface:**

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m streamlit run app.py
```

**Window 2 — Background automation worker:**

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m services.automation_worker --interval 30
```

Window 2 should print `ResolveIQ automation worker started; polling every 30 seconds.` Keep both windows open. Press `Ctrl+C` in each window to stop it.

This project sets `headless = true` in `.streamlit/config.toml`, so Streamlit **does not open the browser automatically**. Open **http://localhost:8501** yourself once Window 1 prints the "Local URL".

### Option B — Windows launcher

From the project root, in PowerShell:

```powershell
.\run_resolveiq.bat
```

or double-click `run_resolveiq.bat` in File Explorer. The launcher uses the Python inside `.venv` (so complete Section 2 first), starts the worker in a separate command window, and runs Streamlit in the current window. Then open **http://localhost:8501** in your browser. Keep both windows open.

## 4. Demo accounts

| Role | Username | Password |
|---|---|---|
| Administrator | `admin` | `Admin@123` |
| Agent | `agent` | `Agent@123` |
| Analyst | `analyst` | `Analyst@123` |
| Requester | `requester` | `Request@123` |

Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes. These fixed credentials are for a local demonstration only. Do not use them for a public deployment.

## 5. Verify the project

Run these commands from the project root with the virtual environment activated:

```powershell
# Run the automated test suite
python -m pytest -q

# Validate the bundled database and synthetic dataset
python scripts/validate_data.py

# Check Python syntax without starting the UI
python -m compileall -q app.py config.py database services scripts tests
```

A successful test run ends with `13 passed`. The data validator prints a JSON report; every check should show `"passed": true`.

## 6. Main capabilities

- Customer and complaint registration.
- Rule-based complaint categorisation and severity detection.
- Priority calculation using category, sentiment, order value, recurrence and vulnerable-customer flag.
- Least-loaded active-agent assignment within the category's default team.
- Controlled complaint status transitions and an auditable event history.
- Response and resolution SLA clocks, including pause/resume while waiting for the customer.
- Background SLA breach detection and automatic escalation.
- Idempotent registration acknowledgements, assignment alerts, customer-reply acknowledgements, agent-reply notifications and resolution updates.
- In-app notifications and optional SMTP email delivery with retry handling.
- Requester self-service complaint tracking and customer-visible conversation history.
- Operations dashboard, complaint workbench, SLA centre, reports and CSV exports.
- Live data-quality checks and a reference data dictionary.

## 7. Optional email configuration

In-app notifications work without email configuration. To enable SMTP email:

1. Copy `.env.example` to `.env` in the project root.
2. Enter the SMTP host, port, sender address and credentials in `.env`.
3. Restart the automation worker (it reads `.env` at startup and sends the emails).

Never commit `.env` or share its credentials. Email delivery depends on the SMTP provider allowing the configured account to send mail. See `docs/automation_and_communication.md` for details.

## 8. Sample data

The bundled database contains synthetic demonstration records. To intentionally rebuild the sample dataset, first stop the app and worker, then back up `data/complaints.db` and run:

```powershell
python scripts/generate_data.py --seed 20261022 --scale 1.0
python scripts/validate_data.py
```

Use `--scale 0.1` for a smaller dataset. **Dataset generation replaces the generated database and exports.** Do not run it if you need to preserve changes made during a demo.

## 9. Troubleshooting

**`python` or `py` is not recognised**
- Install Python 3.10+ and enable the PATH option, then reopen PowerShell.
- Try `python --version` and `py --version` to see which launcher is available.

**PowerShell says script execution is disabled**
- Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that PowerShell window, then activate the environment again.

**`No module named streamlit` (or another dependency)**
- Confirm that `(.venv)` appears in the terminal prompt. If not, run `.\.venv\Scripts\Activate.ps1`.
- Run `python -m pip install -r requirements.txt` from the project root.
- If you started the app with the `.bat` file, make sure Section 2 was completed so `.venv` exists.

**The browser does not open**
- This is expected (`headless = true`). Open http://localhost:8501 manually.

**`can't open file app.py` or the database is not found**
- You are in the wrong folder. Run `Get-ChildItem` and `cd` into the folder that contains `app.py`.

**The interface opens but automation does not run**
- Start the worker in the second terminal and keep it open.
- Check the worker terminal for errors and the app sidebar for the last heartbeat time.
- The worker needs access to the same project folder and `data/complaints.db`.

**Port 8501 is already in use**
- Start Streamlit on another port: `python -m streamlit run app.py --server.port 8502`.

## 10. Project structure

- `app.py` — Streamlit interface and role-based navigation.
- `config.py` — project paths and database location.
- `database/schema.sql`, `database/db.py` — SQLite schema, indexes, connection and initialization.
- `services/rules.py` — category, severity, priority and SLA rules.
- `services/workflow.py` — complaint creation, messages and status transitions.
- `services/operations.py` — authentication, customer operations, assignment, SLA evaluation and data-quality checks.
- `services/automation.py` — background event processing and notifications.
- `services/automation_worker.py` — standalone polling worker.
- `scripts/generate_data.py` — deterministic synthetic data generator.
- `scripts/validate_data.py` — database and data-integrity checks.
- `tests/` — automated unit and workflow tests.
- `docs/` — business rules, data dictionary, traceability and communication notes.

## Prototype limitations

- The background worker runs only while its process and host computer remain running. For always-on operation, deploy it as a supervised service.
- Classification and first-line guidance are deterministic keyword/rule-based logic, not a trained machine-learning model or generative AI system.
- Email is optional and requires valid SMTP credentials. Without SMTP, notifications remain in the application.
- SLA targets are illustrative elapsed-hour targets, not contractual service commitments. A production implementation needs agreed business calendars, holidays and timezone-aware UTC timestamps.
- The sample database contains synthetic records. Production requires privacy review, access-control testing, secure secret management, backups, monitoring, retention policies, deployment hardening and load testing.
- Integrations with external email inboxes, WhatsApp, websites or CRM platforms are not included unless separately configured and implemented.
