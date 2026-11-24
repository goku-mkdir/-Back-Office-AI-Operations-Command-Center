# Standard Operating Procedure (SOP) & Hand-Over Guide

**System:** Back-Office AI Agent (HR, Accounting, Sales)  
**Version:** 1.0  
**Audience:** Operations Managers, HR/Finance/Sales Approvers, Internal Engineering Team

---

## 1. Operational Model: Autonomous vs. Human-in-the-Loop (HITL)

The agent operates under a strict **two-tier risk policy** defined in `config/agent_rules.yaml`:

1. **Autonomous (Low-Risk, Repeatable Internal Tasks)**
   - Runs end-to-end without interrupting the team.
   - Examples: screening incoming résumés, answering HR leave/policy questions, updating CRM notes/stages, drafting offers/invoices/quotes, reconciling expenses within policy threshold (`<= 250 SGD`), compiling monthly summaries, scheduling internal follow-ups.
2. **Approval-Gated (High-Risk / External / Money Movement)**
   - The LangGraph execution graph **halts immediately** via `interrupt()` before the action executes.
   - An approval record is persisted in SQLite and an alert is posted to Slack (`#ops-approvals`).
   - Triggers (configurable in YAML):
     - Any **external email** leaving the organization (`send_invoice`, `chase_overdue_invoices`, `send_nurture_email`, `send_offer_letter`, `send_quote`)
     - Any **outbound money movement** (`disburse_expense`) or expense above threshold (`> 250 SGD`)
     - Any **contract / offer / commercial quote** sent externally or exceeding max auto-discount (`> 10%`)
     - Any **employee compensation or title change** in HRIS

---

## 2. Daily Operations: Reviewing & Approving Actions

### Option A — Streamlit Control Plane (Recommended)
1. Open the **🚦 Approval Queue** tab (`http://<host>:8501`).
2. Expand any `🟡 PENDING` request to inspect:
   - Triggered policy rule & approver role
   - Exact recipient, amount, and payload preview
3. Enter your name/role and an optional note.
4. Click **✅ Approve & Resume Agent** to execute the action and complete the workflow, or **❌ Reject & Block Action** to stop it safely.

### Option B — Slack Interactive Approvals
- Point your Slack App's Interactivity Request URL to `https://<api-host>/slack/actions`.
- Clicking Approve/Reject in `#ops-approvals` calls the same `resolve_approval()` flow and writes to the audit trail.

### Searching the Audit Trail
- Open the **📜 Searchable Audit Trail** tab or query `GET /audit?domain=accounting&query=INV-2026`.
- Every autonomous execution, approval request, sign-off decision, rejection, and error is timestamped with actor, risk level, input payload, and output result.
- Click **⬇️ Export Audit Trail (CSV)** for monthly compliance reviews.

---

## 3. Updating Rules, Thresholds & Prompts (No Code Changes)

Non-technical ops leads can retrain behavior at any time:
1. Open **⚙️ Rules & Prompts (YAML)** in the dashboard (or edit `config/agent_rules.yaml` and `config/prompts.yaml` directly).
2. Common adjustments:
   - Raise/lower `thresholds.expense_auto_reconcile_max` (default `250.00` SGD)
   - Raise/lower `thresholds.quote_max_auto_discount_pct` (default `10.0`%)
   - Flip any action's `require_approval` between `false`, `true`, or `"conditional"`
   - Update email/offer/quote wording in `config/prompts.yaml`
   - Update HR handbook policies in `data/hr_policies.md`
3. Save — changes take effect immediately on the next agent run (no restart required).

---

## 4. Switching from Sandbox to Live Production Integrations

All secrets live exclusively in `.env` (never hard-coded). Copy `.env.example` to `.env`:

1. **LLM Provider** (`LLM_PROVIDER`):
   - `openai` → set `OPENAI_API_KEY`, `LLM_MODEL=gpt-4o-mini` (or `gpt-4.1`), `pip install -e ".[openai]"`
   - `gemini` → set `GOOGLE_API_KEY`, `LLM_MODEL=gemini-2.0-flash`, `pip install -e ".[gemini]"`
   - `anthropic` → set `ANTHROPIC_API_KEY`, `LLM_MODEL=claude-3-5-sonnet-latest`, `pip install -e ".[anthropic]"`
2. **Gradual Connector Rollout**:
   - Set `APP_MODE=live`, then enable connectors one at a time:
     - `EMAIL_MODE=live` (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`)
     - `SLACK_MODE=live` (`SLACK_BOT_TOKEN` or `SLACK_WEBHOOK_URL`)
     - `HRIS_MODE=live` (`BAMBOOHR_SUBDOMAIN`, `BAMBOOHR_API_KEY`)
     - `ACCOUNTING_MODE=live` (`XERO_ACCESS_TOKEN`, `XERO_TENANT_ID`)
     - `CRM_MODE=live` (`HUBSPOT_ACCESS_TOKEN`)

---

## 5. Extending the Agent with a New Tool (Developer Guide)

1. Implement the tool method in `src/backoffice_agent/tools/<domain>_tools.py`.
2. Register the handler in `ToolRegistry._handlers` inside `src/backoffice_agent/tools/registry.py` (and add a preview enricher in `enrich_args_for_policy` if it can trigger approvals).
3. Add the action policy entry under `actions:` in `config/agent_rules.yaml`.
4. Add unit + end-to-end test coverage in `tests/`.

---

## 6. Cloud Infrastructure Requirements (Up-Front Outline)

To deploy this agent in production, the client only needs:
- **Compute:** 1 small container host (2 vCPU, 2–4 GB RAM) — e.g., AWS ECS Fargate / EC2, GCP Cloud Run, Render, or Railway using the included `Dockerfile` & `docker-compose.yml`.
- **Database:** Persistent volume for SQLite (small teams) or managed PostgreSQL (multi-replica scale) + LangGraph PostgresSaver checkpointer.
- **Secrets Manager:** AWS Secrets Manager / GCP Secret Manager / Render Env Vars for `.env` keys.
- **Networking:** HTTPS reverse proxy (Nginx / ALB / Cloudflare) exposing port `8000` (API/Slack webhooks) and port `8501` (internal VPN/SSO-protected Control Plane).

---

## 7. Hand-Over Video Walkthrough Script (5 Minutes)

Use this script when recording the client hand-over Loom/OBS video:

1. **0:00–0:45 — Architecture & Guardrails Overview**
   - Show the Control Plane sidebar (active LLM, connectors, pending approvals badge).
   - Explain the core safety promise: low-risk internal tasks run automatically; money out, contracts, and external emails always halt.
2. **0:45–1:45 — HR End-to-End Flow + HITL**
   - Click **HR End-to-End Demo** → Run Agent.
   - Show `screen_resume` and `draft_offer_letter` completing autonomously, then halting on `send_offer_letter`.
   - Switch to **Approval Queue**, inspect candidate email/offer payload, click **Approve & Resume Agent**.
3. **1:45–2:45 — Accounting End-to-End Flow + Threshold Demo**
   - Click **Accounting End-to-End Demo** → `reconcile_expense` (145 SGD <= 250 SGD) and `compile_monthly_summary` run automatically; `chase_overdue_invoices` halts.
   - Show **High Expense Threshold (>250 SGD)** pausing on `EXP-502` (680 SGD) and demonstrate clicking **Reject & Block Action**.
4. **2:45–3:45 — Sales End-to-End Flow**
   - Click **Sales End-to-End Demo** → CRM update, quote generation (8% discount <= 10%), and follow-up scheduling run automatically; `send_quote` halts for Sales Director approval.
5. **3:45–4:30 — No-Code YAML Configuration**
   - Open **Rules & Prompts (YAML)**, adjust `expense_auto_reconcile_max` or edit an email template, save live without restarting.
6. **4:30–5:00 — Searchable Audit Trail & Stack Explorer**
   - Filter audit trail by domain/event type, export CSV, and inspect updated records & outbound email/Slack logs in **Connected Stack Explorer**.
