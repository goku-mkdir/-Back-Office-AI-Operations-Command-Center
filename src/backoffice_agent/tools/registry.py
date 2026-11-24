"""Unified Tool Registry mapping action names to handlers and argument enrichers."""

from __future__ import annotations

from typing import Any, Callable

from backoffice_agent.connectors import (
    AccountingConnector,
    CRMConnector,
    EmailConnector,
    HRISConnector,
    SlackConnector,
)
from backoffice_agent.settings import ConfigManager, Settings
from backoffice_agent.tools.accounting_tools import AccountingTools
from backoffice_agent.tools.hr_tools import HRTools
from backoffice_agent.tools.sales_tools import SalesTools


class ToolRegistry:
    """Central registry of all HR, Accounting, and Sales tools with pre-gate enrichment."""

    def __init__(
        self,
        *,
        hris: HRISConnector,
        accounting: AccountingConnector,
        crm: CRMConnector,
        email: EmailConnector,
        slack: SlackConnector,
        config_manager: ConfigManager,
        settings: Settings,
    ) -> None:
        self.hris = hris
        self.accounting = accounting
        self.crm = crm
        self.email = email
        self.slack = slack
        self.config_manager = config_manager

        self.hr = HRTools(hris, email, slack, config_manager, settings)
        self.acct = AccountingTools(accounting, email, slack, config_manager)
        self.sales = SalesTools(crm, email, slack, config_manager)

        self._handlers: dict[str, Callable[..., dict[str, Any]]] = {
            # HR
            "screen_resume": self.hr.screen_resume,
            "answer_hr_policy": self.hr.answer_hr_policy,
            "draft_offer_letter": self.hr.draft_offer_letter,
            "send_offer_letter": self.hr.send_offer_letter,
            "update_employee_file": self.hr.update_employee_file,
            # Accounting
            "generate_invoice": self.acct.generate_invoice,
            "send_invoice": self.acct.send_invoice,
            "reconcile_expense": self.acct.reconcile_expense,
            "disburse_expense": self.acct.disburse_expense,
            "chase_overdue_invoices": self.acct.chase_overdue_invoices,
            "compile_monthly_summary": self.acct.compile_monthly_summary,
            # Sales
            "update_crm_lead": self.sales.update_crm_lead,
            "draft_nurture_email": self.sales.draft_nurture_email,
            "send_nurture_email": self.sales.send_nurture_email,
            "prepare_quote": self.sales.prepare_quote,
            "send_quote": self.sales.send_quote,
            "schedule_followup": self.sales.schedule_followup,
        }

    def descriptions(self) -> dict[str, str]:
        rules = self.config_manager.load_rules()
        actions = rules.get("actions", {})
        return {
            name: str(actions.get(name, {}).get("description", name))
            for name in self._handlers
        }

    def enrich_args_for_policy(self, action_name: str, args: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """Populate live amounts, recipients, and human-readable previews before policy checks."""
        enriched = dict(args)

        if action_name in ("reconcile_expense", "disburse_expense"):
            exp_id = str(enriched.get("expense_id", "EXP-501"))
            exp = self.accounting.get_expense(exp_id)
            if exp:
                enriched["expense_id"] = exp["id"]
                enriched["amount"] = float(exp["amount"])
                enriched["preview"] = {
                    "employee": exp["employee_name"],
                    "vendor": exp["vendor"],
                    "amount": f"{exp['currency']} {exp['amount']:,.2f}",
                    "category": exp["category"],
                }
                return enriched, f"{action_name} for {exp['id']} ({exp['vendor']}, {exp['currency']} {exp['amount']:,.2f})"

        if action_name == "send_invoice":
            inv_id = str(enriched.get("invoice_id", "LATEST"))
            inv = self.accounting.get_invoice(inv_id)
            if inv:
                enriched["invoice_id"] = inv["id"]
                enriched["amount"] = float(inv["amount"])
                enriched["preview"] = {
                    "invoice_id": inv["id"],
                    "to_email": inv["customer_email"],
                    "customer": inv["customer_name"],
                    "amount": f"{inv['currency']} {inv['amount']:,.2f}",
                }
                return enriched, f"Send invoice {inv['id']} ({inv['currency']} {inv['amount']:,.2f}) to {inv['customer_email']}"

        if action_name == "chase_overdue_invoices":
            inv_id = str(enriched.get("invoice_id", "INV-2026-002"))
            inv = self.accounting.get_invoice(inv_id)
            if inv:
                enriched["invoice_id"] = inv["id"]
                enriched["preview"] = {
                    "invoice_id": inv["id"],
                    "to_email": inv["customer_email"],
                    "customer": inv["customer_name"],
                    "amount": f"{inv['currency']} {inv['amount']:,.2f}",
                }
                return enriched, f"Send overdue reminder for {inv['id']} ({inv['currency']} {inv['amount']:,.2f}) to {inv['customer_email']}"

        if action_name == "send_offer_letter":
            cand_id = str(enriched.get("candidate_id", "CAND-101"))
            cand = self.hris.get_candidate(cand_id)
            if cand:
                enriched["candidate_id"] = cand["id"]
                enriched["preview"] = {
                    "candidate": cand["name"],
                    "to_email": cand["email"],
                    "role": cand["role_applied"],
                }
                return enriched, f"Send employment offer letter externally to {cand['name']} <{cand['email']}>"

        if action_name == "send_nurture_email":
            lead_id = str(enriched.get("lead_id", "LEAD-301"))
            lead = self.crm.get_lead(lead_id)
            if lead:
                enriched["lead_id"] = lead["id"]
                enriched["preview"] = {
                    "contact": lead["contact_name"],
                    "company": lead["company"],
                    "to_email": lead["email"],
                }
                return enriched, f"Send external nurture email to {lead['contact_name']} <{lead['email']}>"

        if action_name == "send_quote":
            quote_id = str(enriched.get("quote_id", "LATEST"))
            quote = self.crm.get_quote(quote_id)
            if quote:
                lead = self.crm.get_lead(quote["lead_id"])
                enriched["quote_id"] = quote["id"]
                enriched["preview"] = {
                    "quote_id": quote["id"],
                    "company": quote["company"],
                    "to_email": lead["email"] if lead else "prospect@example.com",
                    "total": f"SGD {quote['total']:,.2f}",
                }
                return enriched, f"Send commercial quote {quote['id']} (SGD {quote['total']:,.2f}) externally to {quote['company']}"

        if action_name == "prepare_quote":
            return enriched, f"Prepare quote for {enriched.get('lead_id')} ({enriched.get('discount_pct', 0)}% discount)"

        return enriched, f"Execute {action_name} with args {enriched}"

    def execute(self, action_name: str, args: dict[str, Any]) -> dict[str, Any]:
        handler = self._handlers.get(action_name)
        if not handler:
            raise ValueError(f"Unknown action: {action_name}")
        # Strip preview-only / policy-enrichment metadata keys not accepted by handler
        clean_args = {k: v for k, v in args.items() if k != "preview"}
        if action_name == "send_invoice":
            clean_args.pop("amount", None)
        if action_name == "disburse_expense":
            clean_args.pop("amount", None)
        return handler(**clean_args)
