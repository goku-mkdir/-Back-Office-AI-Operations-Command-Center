# Back-Office AI Agent (HR • Accounting • Sales)

A single controllable, audit-ready AI agent built with **Python, LangGraph, FastAPI, Streamlit, and SQLite** that automates routine back-office chores across **HR, Accounting, and Sales** while enforcing strict **Human-in-the-Loop (HITL) approval gates** whenever money moves, a contract/offer is sent, or an external email leaves the organization.

---

## Key Capabilities & Deliverables

| Deliverable | Implementation |
|---|---|
| **1. Deployed Multi-Domain Agent** | Single LangGraph `StateGraph` agent (`src/backoffice_agent/agent/graph.py`) with pluggable connectors for Email (Gmail/SMTP), Slack, HRIS (BambooHR), Accounting (Xero), and CRM (HubSpot). Works out-of-the-box in realistic `sandbox` mode and flips to `live` via `.env`. |
| **2. No-Code Config & Thresholds** | Editable YAML rules (`config/agent_rules.yaml`) and prompts (`config/prompts.yaml`) plus a live Streamlit configuration editor — change approval thresholds, discount limits, or email copy without touching Python code. |
| **3. Searchable Audit Trail & Alerts** | Every autonomous step, approval request, sign-off decision, and resumed execution is logged to SQLite (`audit_logs`) with full-text search, CSV export, and automatic Slack alerts (`#ops-approvals`, `#ops-audit-alerts`). |
| **4. Hand-Over SOP & Video Script** | Complete written SOP, extension guide, cloud requirements, and 5-minute Loom walkthrough script in `docs/SOP_AND_HANDOVER.md`. |

---

## Architecture

```
User / Slack / Webhook / Streamlit UI
                 │
                 ▼
         FastAPI Backend (src/backoffice_agent/api/app.py)
                 │
                 ▼
    LangGraph StateGraph Agent (MemorySaver + interrupt())
      ┌──────────┴──────────┐
      ▼                     ▼
  Planner (LLM)       ApprovalPolicyEngine ◄── config/agent_rules.yaml
  Mock/OpenAI/        (Global guardrails +     config/prompts.yaml
  Gemini/Anthropic     monetary/discount limits)
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
     Low-Risk Autonomous            High-Risk HITL Gate
     Executes Immediately      Halts graph via interrupt()
              │                Creates SQLite approval + Slack alert
              │                Resumes ONLY via Approve / Reject
              ▼                           │
      Pluggable Connectors ◄──────────────┘ (if Approved)
   (Email, Slack, BambooHR, Xero, HubSpot)
              │
              ▼
     SQLite Audit Trail & Alerts
```

---

## Domain Workflows Covered

- **HR**
  - `screen_resume` *(autonomous)* — Scores incoming candidate résumés against role rubrics and updates HRIS status.
  - `answer_hr_policy` *(autonomous)* — Answers leave/hybrid/policy questions using `data/hr_policies.md` + employee leave balances.
  - `draft_offer_letter` *(autonomous)* — Generates offer letter from editable YAML template.
  - `send_offer_letter` *(HITL gated)* — Halts for **HR Director** approval before emailing offer externally.
  - `update_employee_file` *(conditional)* — Autonomous for notes/contact updates; gated for salary or title changes.

- **Accounting**
  - `generate_invoice` *(autonomous)* — Creates draft invoice in accounting platform.
  - `send_invoice` *(HITL gated)* — Halts for **Finance Controller** sign-off before sending externally.
  - `reconcile_expense` *(conditional)* — Autonomous if `amount <= expense_auto_reconcile_max` (default `250 SGD`); pauses above threshold.
  - `disburse_expense` *(HITL gated)* — Any outbound reimbursement payout halts for **Finance Controller** approval.
  - `chase_overdue_invoices` *(HITL gated)* — Halts before emailing external overdue payment reminder.
  - `compile_monthly_summary` *(autonomous)* — Aggregates revenue, expenses, and overdue AR and posts internally to `#finance-ops`.

- **Sales**
  - `update_crm_lead` *(autonomous)* — Updates CRM stage and call notes.
  - `draft_nurture_email` *(autonomous)* — Drafts personalized outreach email.
  - `send_nurture_email` *(HITL gated)* — Halts for **Sales Manager** sign-off before sending externally.
  - `prepare_quote` *(conditional)* — Autonomous if `discount_pct <= quote_max_auto_discount_pct` (default `10%`); pauses above threshold.
  - `send_quote` *(HITL gated)* — Halts for **Sales Director** approval before sending commercial quote externally.
  - `schedule_followup` *(autonomous)* — Schedules internal CRM follow-up task.

---

## Quick Start (Zero API Keys Required)

### 1. Setup Virtual Environment & Dependencies
```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
pip install -e .
cp .env.example .env
```

### 2. Run the End-to-End Acceptance Demo (CLI)
Proves HR, Accounting, and Sales end-to-end flows + HITL halt/approve/reject + searchable audit trail:
```bash
python scripts/run_e2e_demo.py
```

### 3. Run the FastAPI Server + Streamlit Control Plane
Open two terminals:
```bash
# Terminal 1 — FastAPI backend
uvicorn backoffice_agent.api.app:app --reload --port 8000

# Terminal 2 — Streamlit Config, Approval & Audit Dashboard
streamlit run src/backoffice_agent/dashboard/app.py --server.port 8501
```
Then open:
- **Control Plane Dashboard:** http://127.0.0.1:8501
- **OpenAPI / Swagger Docs:** http://127.0.0.1:8000/docs

### 4. Run Automated Tests
```bash
pytest -v
```

### 5. Switching to Live LLM & Live Business Software
Update `.env` (never commit `.env` to git):
- Set `LLM_PROVIDER=openai` (or `gemini` / `anthropic`) and install the matching package (`pip install -e ".[openai]"`).
- Set `APP_MODE=live` and toggle individual connectors (`EMAIL_MODE=live`, `SLACK_MODE=live`, `HRIS_MODE=live`, `ACCOUNTING_MODE=live`, `CRM_MODE=live`) along with their API tokens.

See `docs/SOP_AND_HANDOVER.md` for full operational SOP, cloud deployment requirements, and hand-over video script.
