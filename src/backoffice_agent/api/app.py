"""FastAPI backend exposing the Back-Office Agent, HITL Approvals, Config, and Audit Trail."""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Query
from pydantic import BaseModel, Field

from backoffice_agent.agent.graph import BackOfficeAgentRuntime
from backoffice_agent.settings import Settings, get_settings


class AgentRunRequest(BaseModel):
    request: str = Field(..., min_length=3, description="Natural-language back-office task.")


class ApprovalDecisionRequest(BaseModel):
    approved: bool = Field(..., description="True to approve & resume; False to reject.")
    decided_by: str = Field(default="Operations Manager", description="Name/email of reviewer.")
    note: str = Field(default="", description="Optional approval/rejection rationale.")


class RawYamlUpdate(BaseModel):
    content: str = Field(..., min_length=5, description="Full YAML document content.")


def create_app(runtime: BackOfficeAgentRuntime | None = None, settings: Settings | None = None) -> FastAPI:
    """Application factory so tests and production can inject isolated runtimes."""
    app_settings = settings or get_settings()

    app = FastAPI(
        title="Back-Office AI Agent API",
        version="1.0.0",
        description="Single AI agent automating HR, Accounting, and Sales with Human-in-the-Loop approvals.",
    )
    app.state.runtime = runtime

    def get_runtime() -> BackOfficeAgentRuntime:
        if app.state.runtime is None:
            app.state.runtime = BackOfficeAgentRuntime(settings=app_settings)
        return app.state.runtime

    @app.get("/health")
    def health() -> dict[str, Any]:
        rt = get_runtime()
        return {
            "status": "ok",
            "app_mode": app_settings.app_mode,
            "llm_provider": app_settings.llm_provider,
            "connectors": {
                "email": "live" if rt.email.is_live else "sandbox",
                "slack": "live" if rt.slack.is_live else "sandbox",
                "hris": "live" if rt.hris.is_live else "sandbox",
                "accounting": "live" if rt.accounting.is_live else "sandbox",
                "crm": "live" if rt.crm.is_live else "sandbox",
            },
            "pending_approvals": len(rt.db.list_approval_requests(status="pending")),
        }

    # --- Agent Execution ---
    @app.post("/agent/run")
    def run_agent(body: AgentRunRequest) -> dict[str, Any]:
        try:
            return get_runtime().run_request(body.request)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/agent/runs")
    def list_runs(limit: int = Query(default=30, ge=1, le=200)) -> dict[str, Any]:
        return {"runs": get_runtime().db.list_runs(limit=limit)}

    # --- Human-in-the-Loop Approvals ---
    @app.get("/approvals")
    def list_approvals(
        status: str | None = Query(default=None, description="Filter by pending|approved|rejected"),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        return {"approvals": get_runtime().db.list_approval_requests(status=status, limit=limit)}

    @app.post("/approvals/{approval_id}/decision")
    def decide_approval(approval_id: str, body: ApprovalDecisionRequest) -> dict[str, Any]:
        try:
            return get_runtime().resolve_approval(
                approval_id=approval_id,
                approved=body.approved,
                decided_by=body.decided_by,
                note=body.note,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/slack/actions")
    def slack_interactive_action(payload: str = Form(...)) -> dict[str, Any]:
        """Webhook endpoint for Slack interactive Approve/Reject buttons."""
        try:
            data = json.loads(payload)
            action = (data.get("actions") or [{}])[0]
            action_id = action.get("action_id", "")
            approval_id = action.get("value", "")
            user_name = (data.get("user") or {}).get("username", "slack_user")
            approved = action_id == "approve_action"
            result = get_runtime().resolve_approval(
                approval_id=approval_id,
                approved=approved,
                decided_by=f"slack:{user_name}",
                note="Resolved via Slack interactive message.",
            )
            return {"ok": True, "result": result}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid Slack action payload: {exc}") from exc

    # --- Searchable Audit Trail ---
    @app.get("/audit")
    def search_audit(
        domain: str | None = Query(default=None),
        event_type: str | None = Query(default=None),
        status: str | None = Query(default=None),
        action_name: str | None = Query(default=None),
        run_id: str | None = Query(default=None),
        query: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        logs = get_runtime().audit.search(
            domain=domain or None,
            event_type=event_type or None,
            status=status or None,
            action_name=action_name or None,
            run_id=run_id or None,
            query=query or None,
            limit=limit,
        )
        return {"count": len(logs), "logs": logs}

    # --- Live YAML Config Endpoints ---
    @app.get("/config/rules")
    def get_rules() -> dict[str, Any]:
        rt = get_runtime()
        return {
            "raw": rt.config_manager.load_rules_raw(),
            "parsed": rt.config_manager.load_rules(),
        }

    @app.put("/config/rules")
    def update_rules(body: RawYamlUpdate) -> dict[str, Any]:
        try:
            parsed = get_runtime().config_manager.save_rules_raw(body.content)
            return {"saved": True, "parsed": parsed}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/config/prompts")
    def get_prompts() -> dict[str, Any]:
        rt = get_runtime()
        return {
            "raw": rt.config_manager.load_prompts_raw(),
            "parsed": rt.config_manager.load_prompts(),
        }

    @app.put("/config/prompts")
    def update_prompts(body: RawYamlUpdate) -> dict[str, Any]:
        try:
            parsed = get_runtime().config_manager.save_prompts_raw(body.content)
            return {"saved": True, "parsed": parsed}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # --- Live Stack / Sandbox State Explorer & Executive Metrics ---
    @app.get("/metrics")
    def executive_metrics() -> dict[str, Any]:
        rt = get_runtime()
        runs = rt.db.list_runs(limit=500)
        approvals = rt.db.list_approval_requests(limit=500)
        logs = rt.audit.search(limit=500)
        invoices = rt.accounting.list_invoices()
        expenses = rt.accounting.list_expenses()
        leads = rt.crm.list_leads()
        candidates = rt.hris.list_candidates()
        outbound = rt.db.list_outbound_messages(limit=200)

        auto_execs = sum(1 for l in logs if l["event_type"] == "autonomous_execution")
        resumed_execs = sum(1 for l in logs if l["event_type"] == "resumed_execution")
        rejected_execs = sum(1 for l in logs if l["event_type"] == "approval_rejected")
        total_actions = auto_execs + resumed_execs + rejected_execs
        auto_rate = round((auto_execs / total_actions) * 100, 1) if total_actions else 100.0

        return {
            "total_runs": len(runs),
            "pending_approvals": sum(1 for a in approvals if a["status"] == "pending"),
            "approved_count": sum(1 for a in approvals if a["status"] == "approved"),
            "rejected_count": sum(1 for a in approvals if a["status"] == "rejected"),
            "autonomous_actions": auto_execs,
            "hitl_executed_actions": resumed_execs,
            "blocked_actions": rejected_execs,
            "autonomy_rate_pct": auto_rate,
            "estimated_minutes_saved": auto_execs * 12 + resumed_execs * 8,
            "ar_paid_sgd": sum(float(i["amount"]) for i in invoices if i["status"] == "paid"),
            "ar_sent_sgd": sum(float(i["amount"]) for i in invoices if i["status"] == "sent"),
            "ar_overdue_sgd": sum(float(i["amount"]) for i in invoices if i["status"] == "overdue"),
            "ar_draft_sgd": sum(float(i["amount"]) for i in invoices if i["status"] == "draft"),
            "expenses_total_sgd": sum(float(e["amount"]) for e in expenses),
            "pipeline_total_sgd": sum(float(l["estimated_value"]) for l in leads),
            "active_candidates": len(candidates),
            "emails_sent": sum(1 for m in outbound if m["channel"] == "email"),
            "slack_alerts": sum(1 for m in outbound if m["channel"] == "slack"),
        }

    @app.post("/sandbox/reset")
    def reset_sandbox() -> dict[str, Any]:
        rt = get_runtime()
        rt.db.reset_sandbox()
        # Reset in-memory LangGraph checkpointer cleanly
        from langgraph.checkpoint.memory import MemorySaver

        rt.checkpointer = MemorySaver()
        rt.graph = rt._build_graph()
        return {"reset": True, "message": "Sandbox data, audit trail, and approval queue reset cleanly."}

    @app.get("/sandbox/overview")
    def sandbox_overview() -> dict[str, Any]:
        rt = get_runtime()
        return {
            "employees": rt.hris.list_employees(),
            "candidates": rt.hris.list_candidates(),
            "invoices": rt.accounting.list_invoices(),
            "expenses": rt.accounting.list_expenses(),
            "leads": rt.crm.list_leads(),
            "quotes": rt.crm.list_quotes(),
            "followups": rt.crm.list_followups(),
            "outbound_messages": rt.db.list_outbound_messages(limit=50),
        }

    return app


app = create_app()
