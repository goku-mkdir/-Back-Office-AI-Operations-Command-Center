"""Unit tests for YAML approval policy engine, dynamic config edits, and audit trail."""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from backoffice_agent.approval import ApprovalPolicyEngine
from backoffice_agent.audit import AuditLogger
from backoffice_agent.connectors.slack_connector import SlackConnector
from backoffice_agent.database import Database
from backoffice_agent.settings import PROJECT_ROOT, ConfigManager, Settings


def _isolated_config_manager(tmp_path: Path) -> ConfigManager:
    cfg_dir = tmp_path / "config"
    shutil.copytree(PROJECT_ROOT / "config", cfg_dir)
    return ConfigManager(cfg_dir)


def test_global_guardrails_block_external_email_money_and_contracts(tmp_path: Path) -> None:
    cfg = _isolated_config_manager(tmp_path)
    engine = ApprovalPolicyEngine(cfg)

    assert engine.evaluate("send_offer_letter", {"candidate_id": "CAND-101"}).requires_approval is True
    assert engine.evaluate("send_invoice", {"invoice_id": "INV-1"}).requires_approval is True
    assert engine.evaluate("disburse_expense", {"expense_id": "EXP-501"}).requires_approval is True
    assert engine.evaluate("send_quote", {"quote_id": "QT-1"}).requires_approval is True
    assert engine.evaluate("send_nurture_email", {"lead_id": "LEAD-301"}).requires_approval is True

    # Low-risk internal actions run autonomously
    assert engine.evaluate("screen_resume", {"candidate_id": "CAND-101"}).requires_approval is False
    assert engine.evaluate("compile_monthly_summary", {"month": "2026-11"}).requires_approval is False
    assert engine.evaluate("update_crm_lead", {"lead_id": "LEAD-301"}).requires_approval is False


def test_conditional_thresholds_reflect_live_yaml_changes(tmp_path: Path) -> None:
    cfg = _isolated_config_manager(tmp_path)
    engine = ApprovalPolicyEngine(cfg)

    # Default expense threshold is 250 SGD
    assert engine.evaluate("reconcile_expense", {"amount": 145.0}).requires_approval is False
    assert engine.evaluate("reconcile_expense", {"amount": 680.0}).requires_approval is True

    # Default quote discount limit is 10%
    assert engine.evaluate("prepare_quote", {"discount_pct": 8.0}).requires_approval is False
    assert engine.evaluate("prepare_quote", {"discount_pct": 15.0}).requires_approval is True

    # Update YAML without touching code -> lower expense max to 100 SGD
    rules = cfg.load_rules()
    rules["thresholds"]["expense_auto_reconcile_max"] = 100.0
    cfg.save_rules_raw(yaml.safe_dump(rules, sort_keys=False))

    assert engine.evaluate("reconcile_expense", {"amount": 145.0}).requires_approval is True


def test_searchable_audit_log_and_slack_alert_dispatch(tmp_path: Path) -> None:
    cfg = _isolated_config_manager(tmp_path)
    db = Database(tmp_path / "test_audit.db")
    settings = Settings(APP_MODE="sandbox", DATABASE_PATH=str(tmp_path / "test_audit.db"))
    slack = SlackConnector(db, settings)
    audit = AuditLogger(db, cfg, alert_sink=slack)

    audit.log_event(
        run_id="RUN-1",
        thread_id="THR-1",
        domain="accounting",
        action_name="send_invoice",
        actor="agent",
        event_type="approval_requested",
        risk_level="high",
        status="pending",
        summary="Paused send_invoice for INV-2026-002",
        payload={"invoice_id": "INV-2026-002"},
    )

    results = audit.search(domain="accounting", query="INV-2026-002")
    assert len(results) == 1
    assert results[0]["action_name"] == "send_invoice"

    slack_msgs = db.list_outbound_messages(channel="slack")
    assert len(slack_msgs) == 1
    assert "#ops-approvals" in slack_msgs[0]["recipient"]
