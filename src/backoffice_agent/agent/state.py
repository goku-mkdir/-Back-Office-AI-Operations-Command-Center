"""LangGraph agent state schema."""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    thread_id: str
    user_request: str
    domain: str
    reasoning: str
    planned_steps: list[dict[str, Any]]
    current_index: int
    current_action: dict[str, Any]
    current_policy: dict[str, Any]
    pending_approval_id: str | None
    approved_override: bool
    decided_by: str
    step_results: list[dict[str, Any]]
    status: str
    final_response: str
