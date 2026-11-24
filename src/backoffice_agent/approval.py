"""Policy engine evaluating YAML task rules and approval thresholds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backoffice_agent.settings import ConfigManager


@dataclass(frozen=True)
class ApprovalDecision:
    """Result of evaluating an action against YAML guardrails and thresholds."""

    action_name: str
    domain: str
    risk_level: str
    requires_approval: bool
    reason: str
    approver_role: str
    trigger_category: str | None = None


class ApprovalPolicyEngine:
    """Evaluates whether an agent action can run autonomously or must pause for sign-off.

    Reads `config/agent_rules.yaml` dynamically so non-developers can update thresholds
    and approval toggles from the dashboard without touching Python code.
    """

    def __init__(self, config_manager: ConfigManager | None = None) -> None:
        self.config_manager = config_manager or ConfigManager()

    def evaluate(self, action_name: str, args: dict[str, Any]) -> ApprovalDecision:
        rules = self.config_manager.load_rules()
        actions = rules.get("actions", {})
        thresholds = rules.get("thresholds", {})
        global_triggers = rules.get("global_approval_triggers", {})
        currency = rules.get("currency", "SGD")

        action_cfg = actions.get(action_name)
        if not action_cfg:
            # Fail-safe default: unknown actions always pause for human approval
            return ApprovalDecision(
                action_name=action_name,
                domain="unknown",
                risk_level="high",
                requires_approval=True,
                reason=f"Action '{action_name}' is not listed in agent_rules.yaml (fail-safe gate).",
                approver_role="Operations Admin",
                trigger_category="unknown_action",
            )

        domain = str(action_cfg.get("domain", "general"))
        risk_level = str(action_cfg.get("risk_level", "medium"))
        approver_role = str(action_cfg.get("approver_role", "Operations Manager"))
        category = action_cfg.get("category")
        require_setting = action_cfg.get("require_approval", False)

        # 1. Global hard guardrails (outbound money, contracts/offers, external emails)
        if category and global_triggers.get(category, False):
            return ApprovalDecision(
                action_name=action_name,
                domain=domain,
                risk_level="high",
                requires_approval=True,
                reason=f"Global guardrail triggered: '{category}' actions require human sign-off before execution.",
                approver_role=approver_role,
                trigger_category=category,
            )

        # 2. Explicit boolean approval requirement
        if require_setting is True:
            return ApprovalDecision(
                action_name=action_name,
                domain=domain,
                risk_level=risk_level,
                requires_approval=True,
                reason=f"Policy requires {approver_role} approval for '{action_name}'.",
                approver_role=approver_role,
                trigger_category=category,
            )

        # 3. Conditional threshold checks
        if require_setting == "conditional":
            condition = action_cfg.get("condition", "")
            if condition == "expense_threshold":
                amount = float(args.get("amount", 0.0) or 0.0)
                max_auto = float(thresholds.get("expense_auto_reconcile_max", 250.0))
                if amount > max_auto:
                    return ApprovalDecision(
                        action_name=action_name,
                        domain=domain,
                        risk_level="high",
                        requires_approval=True,
                        reason=(
                            f"Expense amount {currency} {amount:,.2f} exceeds auto-reconcile "
                            f"threshold of {currency} {max_auto:,.2f}."
                        ),
                        approver_role=approver_role,
                        trigger_category="expense_threshold",
                    )
                return ApprovalDecision(
                    action_name=action_name,
                    domain=domain,
                    risk_level="low",
                    requires_approval=False,
                    reason=(
                        f"Expense amount {currency} {amount:,.2f} is within auto-reconcile "
                        f"limit ({currency} {max_auto:,.2f})."
                    ),
                    approver_role=approver_role,
                )

            if condition == "quote_discount":
                discount_pct = float(args.get("discount_pct", 0.0) or 0.0)
                max_discount = float(thresholds.get("quote_max_auto_discount_pct", 10.0))
                if discount_pct > max_discount:
                    return ApprovalDecision(
                        action_name=action_name,
                        domain=domain,
                        risk_level="high",
                        requires_approval=True,
                        reason=(
                            f"Requested quote discount {discount_pct:.1f}% exceeds automatic "
                            f"limit of {max_discount:.1f}%."
                        ),
                        approver_role=approver_role,
                        trigger_category="quote_discount",
                    )
                return ApprovalDecision(
                    action_name=action_name,
                    domain=domain,
                    risk_level="low",
                    requires_approval=False,
                    reason=(
                        f"Quote discount {discount_pct:.1f}% is within automatic "
                        f"limit ({max_discount:.1f}%)."
                    ),
                    approver_role=approver_role,
                )

            if condition == "compensation_change":
                is_comp_change = bool(args.get("salary") is not None or args.get("title"))
                if is_comp_change:
                    return ApprovalDecision(
                        action_name=action_name,
                        domain=domain,
                        risk_level="high",
                        requires_approval=True,
                        reason="Updating employee compensation or job title requires HR Manager approval.",
                        approver_role=approver_role,
                        trigger_category="compensation_change",
                    )
                return ApprovalDecision(
                    action_name=action_name,
                    domain=domain,
                    risk_level="low",
                    requires_approval=False,
                    reason="Non-compensation employee file update allowed autonomously.",
                    approver_role=approver_role,
                )

        # 4. Low-risk autonomous execution permitted
        return ApprovalDecision(
            action_name=action_name,
            domain=domain,
            risk_level=risk_level,
            requires_approval=False,
            reason=f"Action '{action_name}' is approved for autonomous execution.",
            approver_role=approver_role,
        )
