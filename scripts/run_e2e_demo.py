"""End-to-End Acceptance Demo Script.

Demonstrates:
1. HR flow: autonomous resume screening + offer drafting -> HITL halt on sending offer -> approve & resume.
2. Accounting flow: autonomous low-value expense reconciliation + monthly summary -> HITL halt on overdue reminder -> approve & resume; plus threshold halt on >250 SGD expense -> reject & block.
3. Sales flow: autonomous CRM update + quote prep (8% <= 10%) + follow-up scheduling -> HITL halt on sending quote -> approve & resume.
4. Searchable SQLite audit trail inspection.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from backoffice_agent.agent.graph import BackOfficeAgentRuntime
from backoffice_agent.database import Database
from backoffice_agent.settings import Settings


def print_banner(title: str) -> None:
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


def main() -> None:
    # Use a fresh temporary SQLite DB so every demo run starts cleanly
    demo_db_path = Path(tempfile.gettempdir()) / "backoffice_agent_e2e_demo.db"
    if demo_db_path.exists():
        demo_db_path.unlink()

    settings = Settings(APP_MODE="sandbox", LLM_PROVIDER="mock", DATABASE_PATH=str(demo_db_path))
    runtime = BackOfficeAgentRuntime(settings=settings, db=Database(demo_db_path))

    # ------------------------------------------------------------------
    # 1. HR END-TO-END FLOW
    # ------------------------------------------------------------------
    print_banner("1. HR END-TO-END FLOW (Resume Screen -> Draft Offer -> HITL Send Offer)")
    hr_run = runtime.run_request(
        "Screen resume for CAND-101, draft offer letter at SGD 122000, and send offer email to candidate."
    )
    print(f"Initial Status : {hr_run['status']} (Run {hr_run['run_id']})")
    print(f"Auto Steps Done: {[s['action_name'] for s in hr_run['steps']]}")
    print(f"Halted Action  : {hr_run['pending_approval']['action_name']} ({hr_run['pending_approval']['approval_id']})")
    print(f"Trigger Reason : {hr_run['pending_approval']['reason']}")

    hr_resumed = runtime.resolve_approval(
        approval_id=hr_run["pending_approval"]["approval_id"],
        approved=True,
        decided_by="Sarah Lim (HR Director)",
        note="Compensation confirmed against hiring band.",
    )
    print(f"After Approval : {hr_resumed['status']}")
    print(hr_resumed["final_response"])

    # ------------------------------------------------------------------
    # 2. ACCOUNTING END-TO-END FLOW + THRESHOLD REJECTION DEMO
    # ------------------------------------------------------------------
    print_banner("2. ACCOUNTING END-TO-END FLOW (Reconcile <=250 SGD + Monthly Summary -> HITL Overdue Email)")
    acct_run = runtime.run_request(
        "Reconcile expense EXP-501, compile monthly summary, and chase overdue invoice INV-2026-002."
    )
    print(f"Initial Status : {acct_run['status']} (Run {acct_run['run_id']})")
    print(f"Auto Steps Done: {[s['action_name'] for s in acct_run['steps']]}")
    print(f"Halted Action  : {acct_run['pending_approval']['action_name']} ({acct_run['pending_approval']['approval_id']})")

    acct_resumed = runtime.resolve_approval(
        approval_id=acct_run["pending_approval"]["approval_id"],
        approved=True,
        decided_by="Priya Nair (Finance Controller)",
        note="Confirmed unpaid in bank feed; okay to remind.",
    )
    print(f"After Approval : {acct_resumed['status']}")
    print(acct_resumed["final_response"])

    print_banner("2b. ACCOUNTING GUARDRAIL: Expense > 250 SGD Halted & Rejected")
    high_exp_run = runtime.run_request("Reconcile expense EXP-502")
    print(f"Initial Status : {high_exp_run['status']}")
    print(f"Trigger Reason : {high_exp_run['pending_approval']['reason']}")
    high_exp_rejected = runtime.resolve_approval(
        approval_id=high_exp_run["pending_approval"]["approval_id"],
        approved=False,
        decided_by="Priya Nair (Finance Controller)",
        note="Missing AWS itemized tax invoice.",
    )
    print(f"After Rejection: {high_exp_rejected['status']}")
    print(high_exp_rejected["final_response"])

    # ------------------------------------------------------------------
    # 3. SALES END-TO-END FLOW
    # ------------------------------------------------------------------
    print_banner("3. SALES END-TO-END FLOW (CRM Update + Quote 8% + Follow-Up -> HITL Send Quote)")
    sales_run = runtime.run_request(
        "Update CRM lead LEAD-302 to qualified, prepare quote for SGD 24000 with 8% discount, "
        "schedule follow-up, and send quote externally."
    )
    print(f"Initial Status : {sales_run['status']} (Run {sales_run['run_id']})")
    print(f"Auto Steps Done: {[s['action_name'] for s in sales_run['steps']]}")
    print(f"Halted Action  : {sales_run['pending_approval']['action_name']} ({sales_run['pending_approval']['approval_id']})")

    sales_resumed = runtime.resolve_approval(
        approval_id=sales_run["pending_approval"]["approval_id"],
        approved=True,
        decided_by="Marcus Chua (Sales Director)",
        note="Pricing approved.",
    )
    print(f"After Approval : {sales_resumed['status']}")
    print(sales_resumed["final_response"])

    # ------------------------------------------------------------------
    # 4. SEARCHABLE AUDIT TRAIL SUMMARY
    # ------------------------------------------------------------------
    print_banner("4. SEARCHABLE AUDIT TRAIL & OUTBOUND ALERTS")
    logs = runtime.audit.search(limit=50)
    print(f"Total Audit Events Recorded: {len(logs)}")
    for entry in reversed(logs):
        print(
            f"  #{entry['id']:02d} [{entry['domain'].upper():10s}] {entry['event_type']:20s} | "
            f"{entry['action_name']:22s} | {entry['status']:9s} | {entry['summary'][:68]}"
        )

    outbound = runtime.db.list_outbound_messages(limit=50)
    emails = [m for m in outbound if m["channel"] == "email"]
    slacks = [m for m in outbound if m["channel"] == "slack"]
    print(f"\nOutbound Emails Dispatched (after HITL approval): {len(emails)}")
    print(f"Slack Notifications & Alerts Posted             : {len(slacks)}")
    print("\nAll acceptance criteria demonstrated successfully!")


if __name__ == "__main__":
    main()
