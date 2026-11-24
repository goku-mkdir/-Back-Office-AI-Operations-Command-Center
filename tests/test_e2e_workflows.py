"""End-to-end integration tests for HR, Accounting, Sales, HITL interrupts, and FastAPI."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import httpx

from backoffice_agent.agent.graph import BackOfficeAgentRuntime
from backoffice_agent.api.app import create_app
from backoffice_agent.database import Database
from backoffice_agent.settings import PROJECT_ROOT, ConfigManager, Settings


def _make_runtime(tmp_path: Path) -> BackOfficeAgentRuntime:
    cfg_dir = tmp_path / "config"
    shutil.copytree(PROJECT_ROOT / "config", cfg_dir)
    db_path = tmp_path / "e2e.db"
    settings = Settings(
        APP_MODE="sandbox",
        LLM_PROVIDER="mock",
        DATABASE_PATH=str(db_path),
        CONFIG_DIR=str(cfg_dir),
    )
    return BackOfficeAgentRuntime(
        settings=settings,
        db=Database(db_path),
        config_manager=ConfigManager(cfg_dir),
    )


def test_hr_end_to_end_autonomous_and_hitl_approval(tmp_path: Path) -> None:
    rt = _make_runtime(tmp_path)

    # Low-risk policy Q&A runs fully autonomously
    qa = rt.run_request("Answer annual leave and hybrid work policy for EMP-001")
    assert qa["status"] == "completed"
    assert qa["domain"] == "hr"
    assert qa["pending_approval"] is None

    # Multi-step HR workflow: screen_resume + draft_offer_letter run auto, send_offer_letter HALTS
    run = rt.run_request(
        "Screen resume for CAND-101, draft offer letter at SGD 125000, and send offer email."
    )
    assert run["status"] == "awaiting_approval"
    assert [s["action_name"] for s in run["steps"]] == ["screen_resume", "draft_offer_letter"]
    assert run["pending_approval"]["action_name"] == "send_offer_letter"

    # Verify NO external email has been sent yet while halted
    assert len(rt.db.list_outbound_messages(channel="email")) == 0

    # Approve and resume LangGraph thread
    resumed = rt.resolve_approval(
        approval_id=run["pending_approval"]["approval_id"],
        approved=True,
        decided_by="Sarah Lim",
        note="Approved offer.",
    )
    assert resumed["status"] == "completed"
    assert len(rt.db.list_outbound_messages(channel="email")) == 1
    assert rt.hris.get_candidate("CAND-101")["status"] == "offer_sent"


def test_accounting_end_to_end_and_threshold_rejection(tmp_path: Path) -> None:
    rt = _make_runtime(tmp_path)

    # Low expense (145 SGD <= 250) runs auto; chase overdue invoice HALTS; monthly summary finishes after resume
    run = rt.run_request(
        "Reconcile expense EXP-501, compile monthly summary, and chase overdue invoice INV-2026-002."
    )
    assert run["status"] == "awaiting_approval"
    assert [s["action_name"] for s in run["steps"]] == ["reconcile_expense"]
    assert run["pending_approval"]["action_name"] == "chase_overdue_invoices"
    assert rt.accounting.get_expense("EXP-501")["status"] == "reconciled"

    resumed = rt.resolve_approval(
        approval_id=run["pending_approval"]["approval_id"],
        approved=True,
        decided_by="Priya Nair",
    )
    assert resumed["status"] == "completed"
    assert [s["action_name"] for s in resumed["steps"]] == [
        "reconcile_expense",
        "chase_overdue_invoices",
        "compile_monthly_summary",
    ]
    assert len(rt.db.list_outbound_messages(channel="email")) == 1

    # High expense (EXP-502 = 680 SGD > 250) MUST halt and stay submitted if rejected
    high_run = rt.run_request("Reconcile expense EXP-502")
    assert high_run["status"] == "awaiting_approval"
    assert high_run["pending_approval"]["action_name"] == "reconcile_expense"

    rejected = rt.resolve_approval(
        approval_id=high_run["pending_approval"]["approval_id"],
        approved=False,
        decided_by="Priya Nair",
        note="Receipt unclear",
    )
    assert rejected["status"] == "rejected"
    assert rt.accounting.get_expense("EXP-502")["status"] == "submitted"


def test_sales_end_to_end_quote_and_followup(tmp_path: Path) -> None:
    rt = _make_runtime(tmp_path)

    run = rt.run_request(
        "Update CRM lead LEAD-302 to qualified, prepare quote for SGD 24000 with 8% discount, "
        "schedule follow-up, and send quote externally."
    )
    assert run["status"] == "awaiting_approval"
    assert [s["action_name"] for s in run["steps"]] == [
        "update_crm_lead",
        "prepare_quote",
    ]
    assert run["pending_approval"]["action_name"] == "send_quote"

    resumed = rt.resolve_approval(
        approval_id=run["pending_approval"]["approval_id"],
        approved=True,
        decided_by="Marcus Chua",
    )
    assert resumed["status"] == "completed"
    assert [s["action_name"] for s in resumed["steps"]] == [
        "update_crm_lead",
        "prepare_quote",
        "send_quote",
        "schedule_followup",
    ]
    assert len(rt.crm.list_followups()) == 1
    assert len(rt.db.list_outbound_messages(channel="email")) == 1
    assert rt.crm.list_quotes()[0]["status"] == "sent"


def test_fastapi_endpoints_full_lifecycle(tmp_path: Path) -> None:
    rt = _make_runtime(tmp_path)
    app = create_app(runtime=rt, settings=rt.settings)

    async def _run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            health = await client.get("/health")
            assert health.status_code == 200
            assert health.json()["status"] == "ok"

            # Trigger HITL via API
            run_resp = await client.post(
                "/agent/run",
                json={"request": "Draft and send nurture email for early-stage lead LEAD-301"},
            )
            assert run_resp.status_code == 200
            data = run_resp.json()
            assert data["status"] == "awaiting_approval"
            approval_id = data["pending_approval"]["approval_id"]

            # Confirm pending approval visible
            pending = (await client.get("/approvals", params={"status": "pending"})).json()["approvals"]
            assert any(a["id"] == approval_id for a in pending)

            # Approve via API
            dec = await client.post(
                f"/approvals/{approval_id}/decision",
                json={"approved": True, "decided_by": "Sales Lead", "note": "Good to send"},
            )
            assert dec.status_code == 200
            assert dec.json()["status"] == "completed"

            # Verify searchable audit trail
            audit = (await client.get("/audit", params={"domain": "sales", "query": "LEAD-301"})).json()
            assert audit["count"] >= 3

            # Verify config read
            rules = await client.get("/config/rules")
            assert rules.status_code == 200
            assert "expense_auto_reconcile_max" in rules.json()["raw"]

    asyncio.run(_run())
