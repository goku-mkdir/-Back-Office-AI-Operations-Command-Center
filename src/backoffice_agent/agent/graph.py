"""LangGraph StateGraph implementing autonomous execution with Human-in-the-Loop interrupts."""

from __future__ import annotations

import uuid
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from backoffice_agent.agent.state import AgentState
from backoffice_agent.approval import ApprovalPolicyEngine
from backoffice_agent.audit import AuditLogger
from backoffice_agent.connectors import (
    AccountingConnector,
    CRMConnector,
    EmailConnector,
    HRISConnector,
    SlackConnector,
)
from backoffice_agent.database import Database
from backoffice_agent.llm import BackOfficeLLM
from backoffice_agent.settings import ConfigManager, Settings, get_settings
from backoffice_agent.tools import ToolRegistry


class BackOfficeAgentRuntime:
    """Orchestrates the single multi-domain LangGraph agent + persistent SQLite approvals/audit."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        db: Database | None = None,
        config_manager: ConfigManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.config_manager = config_manager or ConfigManager(self.settings.config_path)
        self.db = db or Database(self.settings.db_file)

        # Connectors
        self.email = EmailConnector(self.db, self.settings)
        self.slack = SlackConnector(self.db, self.settings)
        self.hris = HRISConnector(self.db, self.settings)
        self.accounting = AccountingConnector(self.db, self.settings)
        self.crm = CRMConnector(self.db, self.settings)

        # Core governance & intelligence
        self.policy_engine = ApprovalPolicyEngine(self.config_manager)
        self.audit = AuditLogger(self.db, self.config_manager, alert_sink=self.slack)
        self.llm = BackOfficeLLM(self.settings, self.config_manager)
        self.tools = ToolRegistry(
            hris=self.hris,
            accounting=self.accounting,
            crm=self.crm,
            email=self.email,
            slack=self.slack,
            config_manager=self.config_manager,
            settings=self.settings,
        )

        # LangGraph checkpointer & compiled StateGraph
        self.checkpointer = MemorySaver()
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        builder = StateGraph(AgentState)

        builder.add_node("plan", self._plan_node)
        builder.add_node("evaluate_step", self._evaluate_step_node)
        builder.add_node("approval_gate", self._approval_gate_node)
        builder.add_node("execute_step", self._execute_step_node)
        builder.add_node("finalize", self._finalize_node)

        builder.add_edge(START, "plan")
        builder.add_edge("plan", "evaluate_step")
        builder.add_conditional_edges(
            "evaluate_step",
            self._route_after_evaluate,
            {
                "approval_gate": "approval_gate",
                "execute_step": "execute_step",
                "finalize": "finalize",
            },
        )
        builder.add_conditional_edges(
            "approval_gate",
            self._route_after_approval,
            {
                "execute_step": "execute_step",
                "evaluate_step": "evaluate_step",
            },
        )
        builder.add_edge("execute_step", "evaluate_step")
        builder.add_edge("finalize", END)

        return builder.compile(checkpointer=self.checkpointer)

    # ------------------------------------------------------------------
    # Graph Nodes
    # ------------------------------------------------------------------
    def _plan_node(self, state: AgentState) -> dict[str, Any]:
        plan = self.llm.plan_request(state["user_request"], self.tools.descriptions())
        steps = [
            {"action_name": s.action_name, "args": s.args, "rationale": s.rationale}
            for s in plan.steps
        ]
        self.db.upsert_run(
            run_id=state["run_id"],
            thread_id=state["thread_id"],
            user_request=state["user_request"],
            domain=plan.domain,
            status="running",
            steps=[],
        )
        return {
            "domain": plan.domain,
            "reasoning": plan.reasoning,
            "planned_steps": steps,
            "current_index": 0,
            "step_results": [],
            "approved_override": False,
            "pending_approval_id": None,
            "decided_by": "",
            "status": "running",
        }

    def _evaluate_step_node(self, state: AgentState) -> dict[str, Any]:
        idx = state.get("current_index", 0)
        planned = state.get("planned_steps", [])
        if idx >= len(planned):
            return {"current_action": {}, "current_policy": {}}

        raw_step = planned[idx]
        action_name = raw_step["action_name"]
        enriched_args, preview_summary = self.tools.enrich_args_for_policy(
            action_name, raw_step.get("args", {})
        )
        decision = self.policy_engine.evaluate(action_name, enriched_args)
        return {
            "current_action": {
                "action_name": action_name,
                "args": enriched_args,
                "rationale": raw_step.get("rationale", ""),
                "preview_summary": preview_summary,
            },
            "current_policy": {
                "domain": decision.domain,
                "risk_level": decision.risk_level,
                "requires_approval": decision.requires_approval,
                "reason": decision.reason,
                "approver_role": decision.approver_role,
                "trigger_category": decision.trigger_category,
            },
            "approved_override": False,
            "pending_approval_id": None,
        }

    def _route_after_evaluate(self, state: AgentState) -> str:
        idx = state.get("current_index", 0)
        planned = state.get("planned_steps", [])
        if idx >= len(planned):
            return "finalize"
        if state.get("current_policy", {}).get("requires_approval", True):
            return "approval_gate"
        return "execute_step"

    def _approval_gate_node(self, state: AgentState) -> dict[str, Any]:
        action = state["current_action"]
        policy = state["current_policy"]
        run_id = state["run_id"]
        thread_id = state["thread_id"]

        # Reuse an existing pending approval for this thread+action if interrupt replays node
        existing_pending = [
            req
            for req in self.db.list_approval_requests(status="pending")
            if req["thread_id"] == thread_id and req["action_name"] == action["action_name"]
        ]
        if existing_pending:
            approval_record = existing_pending[0]
            approval_id = approval_record["id"]
        else:
            approval_id = f"APR-{uuid.uuid4().hex[:8].upper()}"
            approval_record = self.db.create_approval_request(
                approval_id=approval_id,
                thread_id=thread_id,
                run_id=run_id,
                domain=policy["domain"],
                action_name=action["action_name"],
                risk_level=policy["risk_level"],
                approver_role=policy["approver_role"],
                reason=policy["reason"],
                summary=action["preview_summary"],
                payload=action["args"],
            )
            self.audit.log_event(
                run_id=run_id,
                thread_id=thread_id,
                domain=policy["domain"],
                action_name=action["action_name"],
                actor="agent",
                event_type="approval_requested",
                risk_level=policy["risk_level"],
                status="pending",
                summary=f"Paused for {policy['approver_role']} approval ({approval_id}): {action['preview_summary']}",
                payload={"approval_id": approval_id, "reason": policy["reason"], "args": action["args"]},
            )
            paused_steps = list(state.get("step_results", [])) + [
                {
                    "action_name": action["action_name"],
                    "status": "awaiting_approval",
                    "approval_id": approval_id,
                    "risk_level": policy["risk_level"],
                    "approver_role": policy["approver_role"],
                    "reason": policy["reason"],
                    "summary": action["preview_summary"],
                }
            ]
            self.db.upsert_run(
                run_id=run_id,
                thread_id=thread_id,
                user_request=state["user_request"],
                domain=state["domain"],
                status="awaiting_approval",
                steps=paused_steps,
                final_response=f"Halted on '{action['action_name']}' pending approval ({approval_id}).",
            )

        # ---- TRUE LANGGRAPH HUMAN-IN-THE-LOOP INTERRUPT ----
        human_decision = interrupt(
            {
                "approval_id": approval_id,
                "action_name": action["action_name"],
                "domain": policy["domain"],
                "risk_level": policy["risk_level"],
                "approver_role": policy["approver_role"],
                "reason": policy["reason"],
                "summary": action["preview_summary"],
                "payload": action["args"],
            }
        )

        approved = bool(human_decision.get("approved", False))
        decided_by = str(human_decision.get("decided_by", "human_approver"))
        note = str(human_decision.get("note", ""))

        if approved:
            self.audit.log_event(
                run_id=run_id,
                thread_id=thread_id,
                domain=policy["domain"],
                action_name=action["action_name"],
                actor=decided_by,
                event_type="approval_granted",
                risk_level=policy["risk_level"],
                status="approved",
                summary=f"Approved ({approval_id}) by {decided_by}: {action['preview_summary']}",
                payload={"approval_id": approval_id, "note": note},
            )
            return {
                "approved_override": True,
                "pending_approval_id": approval_id,
                "decided_by": decided_by,
                "status": "running",
            }

        # Rejected by human
        self.db.update_approval_decision(
            approval_id=approval_id,
            status="rejected",
            decided_by=decided_by,
            decision_note=note,
            execution_result={"executed": False, "reason": "Rejected by approver"},
        )
        self.audit.log_event(
            run_id=run_id,
            thread_id=thread_id,
            domain=policy["domain"],
            action_name=action["action_name"],
            actor=decided_by,
            event_type="approval_rejected",
            risk_level=policy["risk_level"],
            status="rejected",
            summary=f"Rejected ({approval_id}) by {decided_by}: {action['preview_summary']}",
            payload={"approval_id": approval_id, "note": note},
        )
        updated_results = list(state.get("step_results", [])) + [
            {
                "action_name": action["action_name"],
                "status": "rejected",
                "approval_id": approval_id,
                "risk_level": policy["risk_level"],
                "decided_by": decided_by,
                "summary": f"Action blocked by {decided_by}. {note}".strip(),
            }
        ]
        return {
            "approved_override": False,
            "pending_approval_id": None,
            "step_results": updated_results,
            "current_index": state.get("current_index", 0) + 1,
            "status": "rejected",
        }

    def _route_after_approval(self, state: AgentState) -> str:
        if state.get("approved_override"):
            return "execute_step"
        return "evaluate_step"

    def _execute_step_node(self, state: AgentState) -> dict[str, Any]:
        action = state["current_action"]
        policy = state["current_policy"]
        run_id = state["run_id"]
        thread_id = state["thread_id"]
        was_approved = bool(state.get("approved_override", False))
        approval_id = state.get("pending_approval_id")
        decided_by = state.get("decided_by", "")

        try:
            result = self.tools.execute(action["action_name"], action["args"])
            summary = str(result.get("summary", action["preview_summary"]))
            event_type = "resumed_execution" if was_approved else "autonomous_execution"
            actor = f"agent (approved by {decided_by})" if was_approved else "agent"

            if was_approved and approval_id:
                self.db.update_approval_decision(
                    approval_id=approval_id,
                    status="approved",
                    decided_by=decided_by,
                    execution_result=result,
                )

            self.audit.log_event(
                run_id=run_id,
                thread_id=thread_id,
                domain=policy["domain"],
                action_name=action["action_name"],
                actor=actor,
                event_type=event_type,
                risk_level=policy["risk_level"],
                status="completed",
                summary=summary,
                payload=action["args"],
                result=result,
            )

            step_entry = {
                "action_name": action["action_name"],
                "status": "completed",
                "mode": "approved_human_in_loop" if was_approved else "autonomous",
                "risk_level": policy["risk_level"],
                "approval_id": approval_id,
                "summary": summary,
                "result": result,
            }
        except Exception as exc:
            self.audit.log_event(
                run_id=run_id,
                thread_id=thread_id,
                domain=policy.get("domain", state.get("domain", "general")),
                action_name=action["action_name"],
                actor="agent",
                event_type="error",
                risk_level=policy.get("risk_level", "medium"),
                status="failed",
                summary=f"Error executing {action['action_name']}: {exc}",
                payload=action.get("args", {}),
            )
            step_entry = {
                "action_name": action["action_name"],
                "status": "failed",
                "risk_level": policy.get("risk_level", "medium"),
                "summary": str(exc),
            }

        updated_results = list(state.get("step_results", [])) + [step_entry]
        self.db.upsert_run(
            run_id=run_id,
            thread_id=thread_id,
            user_request=state["user_request"],
            domain=state["domain"],
            status="running",
            steps=updated_results,
        )
        return {
            "step_results": updated_results,
            "current_index": state.get("current_index", 0) + 1,
            "approved_override": False,
            "pending_approval_id": None,
        }

    def _finalize_node(self, state: AgentState) -> dict[str, Any]:
        step_results = state.get("step_results", [])
        final_text = self.llm.summarize_run(
            state["user_request"], state.get("domain", "general"), step_results
        )
        has_rejected = any(s.get("status") == "rejected" for s in step_results)
        has_failed = any(s.get("status") == "failed" for s in step_results)
        final_status = "failed" if has_failed else ("rejected" if has_rejected else "completed")

        self.db.upsert_run(
            run_id=state["run_id"],
            thread_id=state["thread_id"],
            user_request=state["user_request"],
            domain=state.get("domain", "general"),
            status=final_status,
            steps=step_results,
            final_response=final_text,
        )
        return {"status": final_status, "final_response": final_text}

    # ------------------------------------------------------------------
    # Public Runtime API
    # ------------------------------------------------------------------
    def run_request(self, user_request: str) -> dict[str, Any]:
        """Execute a natural-language back-office task; halts cleanly if HITL is required."""
        run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
        thread_id = f"THR-{uuid.uuid4().hex[:8].upper()}"
        config = {"configurable": {"thread_id": thread_id}}

        output = self.graph.invoke(
            {
                "run_id": run_id,
                "thread_id": thread_id,
                "user_request": user_request,
            },
            config=config,
        )
        return self._format_graph_output(run_id, thread_id, output)

    def resolve_approval(
        self,
        *,
        approval_id: str,
        approved: bool,
        decided_by: str = "ops_manager",
        note: str = "",
    ) -> dict[str, Any]:
        """Approve or reject a halted action and resume the paused LangGraph thread."""
        req = self.db.get_approval_request(approval_id)
        if not req:
            raise ValueError(f"Approval request '{approval_id}' not found.")
        if req["status"] != "pending":
            raise ValueError(f"Approval request '{approval_id}' is already '{req['status']}'.")

        thread_id = req["thread_id"]
        run_id = req["run_id"]
        config = {"configurable": {"thread_id": thread_id}}

        # Check if the LangGraph thread is still live in the checkpointer
        snapshot = self.graph.get_state(config)
        if snapshot and snapshot.next:
            output = self.graph.invoke(
                Command(resume={"approved": approved, "decided_by": decided_by, "note": note}),
                config=config,
            )
            return self._format_graph_output(run_id, thread_id, output)

        # Fallback if the server restarted after pausing (persisted SQLite recovery)
        if not approved:
            updated = self.db.update_approval_decision(
                approval_id=approval_id,
                status="rejected",
                decided_by=decided_by,
                decision_note=note,
                execution_result={"executed": False, "reason": "Rejected by approver"},
            )
            self.audit.log_event(
                run_id=run_id,
                thread_id=thread_id,
                domain=req["domain"],
                action_name=req["action_name"],
                actor=decided_by,
                event_type="approval_rejected",
                risk_level=req["risk_level"],
                status="rejected",
                summary=f"Rejected ({approval_id}) by {decided_by}: {req['summary']}",
                payload={"approval_id": approval_id, "note": note},
            )
            return {"run_id": run_id, "thread_id": thread_id, "status": "rejected", "approval": updated}

        result = self.tools.execute(req["action_name"], req["payload"])
        updated = self.db.update_approval_decision(
            approval_id=approval_id,
            status="approved",
            decided_by=decided_by,
            decision_note=note,
            execution_result=result,
        )
        self.audit.log_event(
            run_id=run_id,
            thread_id=thread_id,
            domain=req["domain"],
            action_name=req["action_name"],
            actor=f"agent (approved by {decided_by})",
            event_type="resumed_execution",
            risk_level=req["risk_level"],
            status="completed",
            summary=str(result.get("summary", req["summary"])),
            payload=req["payload"],
            result=result,
        )
        return {
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "completed",
            "approval": updated,
            "result": result,
        }

    def _format_graph_output(
        self, run_id: str, thread_id: str, output: dict[str, Any]
    ) -> dict[str, Any]:
        interrupts = output.get("__interrupt__")
        if interrupts:
            intr_payload = interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]
            return {
                "run_id": run_id,
                "thread_id": thread_id,
                "domain": output.get("domain", intr_payload.get("domain", "general")),
                "status": "awaiting_approval",
                "steps": output.get("step_results", []),
                "pending_approval": intr_payload,
                "final_response": (
                    f"Paused on `{intr_payload['action_name']}` ({intr_payload['approval_id']}) — "
                    f"awaiting {intr_payload['approver_role']} sign-off: {intr_payload['reason']}"
                ),
            }

        return {
            "run_id": run_id,
            "thread_id": thread_id,
            "domain": output.get("domain", "general"),
            "status": output.get("status", "completed"),
            "steps": output.get("step_results", []),
            "pending_approval": None,
            "final_response": output.get("final_response", ""),
        }
