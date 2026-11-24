"""Searchable SQLite audit trail and Slack/webhook alert dispatcher."""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from backoffice_agent.database import Database, utc_now_iso
from backoffice_agent.settings import ConfigManager

logger = logging.getLogger("backoffice_agent.audit")


class AlertSink(Protocol):
    def post_message(self, channel: str, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


class AuditLogger:
    """Records every autonomous step, approval request, decision, and alert in SQLite."""

    def __init__(
        self,
        db: Database,
        config_manager: ConfigManager | None = None,
        alert_sink: AlertSink | None = None,
    ) -> None:
        self.db = db
        self.config_manager = config_manager or ConfigManager()
        self.alert_sink = alert_sink

    def log_event(
        self,
        *,
        run_id: str,
        thread_id: str,
        domain: str,
        action_name: str,
        actor: str,
        event_type: str,
        risk_level: str,
        status: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
    ) -> int:
        ts = utc_now_iso()
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO audit_logs
                (timestamp, run_id, thread_id, domain, action_name, actor, event_type,
                 risk_level, status, summary, payload_json, result_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    run_id,
                    thread_id,
                    domain,
                    action_name,
                    actor,
                    event_type,
                    risk_level,
                    status,
                    summary,
                    json.dumps(payload or {}, default=str),
                    json.dumps(result or {}, default=str),
                ),
            )
            audit_id = int(cur.lastrowid)

        logger.info("[%s] [%s/%s] %s - %s (%s)", event_type, domain, action_name, summary, status, actor)
        self._maybe_dispatch_alert(
            event_type=event_type,
            domain=domain,
            action_name=action_name,
            risk_level=risk_level,
            status=status,
            summary=summary,
            payload=payload or {},
        )
        return audit_id

    def _maybe_dispatch_alert(
        self,
        *,
        event_type: str,
        domain: str,
        action_name: str,
        risk_level: str,
        status: str,
        summary: str,
        payload: dict[str, Any],
    ) -> None:
        if self.alert_sink is None:
            return
        rules = self.config_manager.load_rules()
        alert_cfg = rules.get("alerting", {})

        should_alert = (
            (event_type == "approval_requested" and alert_cfg.get("notify_slack_on_approval_request", True))
            or (
                event_type == "resumed_execution"
                and risk_level == "high"
                and alert_cfg.get("notify_slack_on_high_risk_execution", True)
            )
            or (event_type == "error" and alert_cfg.get("notify_slack_on_error", True))
        )
        if not should_alert:
            return

        channel = (
            "#ops-approvals" if event_type == "approval_requested" else "#ops-audit-alerts"
        )
        text = (
            f"[{event_type.upper()}] Domain={domain.upper()} | Action=`{action_name}` | "
            f"Risk={risk_level.upper()} | Status={status}\nSummary: {summary}"
        )
        try:
            self.alert_sink.post_message(channel=channel, text=text, metadata={"event_type": event_type, **payload})
        except Exception as exc:  # pragma: no cover - alert failures must not crash main flow
            logger.warning("Failed to dispatch Slack alert: %s", exc)

    def search(
        self,
        *,
        domain: str | None = None,
        event_type: str | None = None,
        status: str | None = None,
        action_name: str | None = None,
        run_id: str | None = None,
        query: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []

        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if action_name:
            clauses.append("action_name = ?")
            params.append(action_name)
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if query:
            like = f"%{query}%"
            clauses.append(
                "(summary LIKE ? OR action_name LIKE ? OR payload_json LIKE ? OR result_json LIKE ?)"
            )
            params.extend([like, like, like, like])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM audit_logs {where_sql} ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with self.db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            out: list[dict[str, Any]] = []
            for r in rows:
                d = dict(r)
                d["payload"] = json.loads(d.pop("payload_json") or "{}")
                d["result"] = json.loads(d.pop("result_json") or "{}")
                out.append(d)
            return out
