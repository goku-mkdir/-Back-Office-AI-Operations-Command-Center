"""Accounting Operations tool implementations (invoicing, expenses, overdue AR, summaries)."""

from __future__ import annotations

from typing import Any

from backoffice_agent.connectors import AccountingConnector, EmailConnector, SlackConnector
from backoffice_agent.settings import ConfigManager


class AccountingTools:
    """Implements autonomous accounting chores and HITL-gated outbound money / invoice actions."""

    def __init__(
        self,
        accounting: AccountingConnector,
        email: EmailConnector,
        slack: SlackConnector,
        config_manager: ConfigManager,
    ) -> None:
        self.accounting = accounting
        self.email = email
        self.slack = slack
        self.config_manager = config_manager

    def generate_invoice(
        self,
        customer_name: str = "Merlion Logistics Pte Ltd",
        customer_email: str = "ap@merlionlogistics.sg",
        description: str = "Monthly Automation Retainer",
        amount: float = 4500.0,
        due_date: str = "2026-12-24",
    ) -> dict[str, Any]:
        rules = self.config_manager.load_rules()
        currency = rules.get("currency", "SGD")
        inv = self.accounting.create_draft_invoice(
            customer_name=customer_name,
            customer_email=customer_email,
            description=description,
            amount=float(amount),
            due_date=due_date,
            currency=currency,
        )
        return {
            "invoice": inv,
            "summary": f"Generated draft invoice {inv['id']} for {customer_name} ({currency} {float(amount):,.2f}, due {due_date}).",
        }

    def send_invoice(self, invoice_id: str = "LATEST") -> dict[str, Any]:
        inv = self.accounting.get_invoice(invoice_id)
        if not inv:
            raise ValueError(f"Invoice '{invoice_id}' not found.")

        body = (
            f"Dear {inv['customer_name']},\n\n"
            f"Please find attached Invoice {inv['id']} for {inv['currency']} {inv['amount']:,.2f}.\n"
            f"Description: {inv['description']}\n"
            f"Due Date: {inv['due_date']}\n\n"
            f"Thank you for your business."
        )
        email_res = self.email.send_email(
            to_email=inv["customer_email"],
            subject=f"Invoice {inv['id']} — {inv['currency']} {inv['amount']:,.2f}",
            body=body,
            metadata={"domain": "accounting", "invoice_id": inv["id"], "amount": inv["amount"]},
        )
        updated = self.accounting.mark_invoice_sent(inv["id"])
        return {
            "invoice": updated,
            "email_delivery": email_res,
            "summary": f"Sent invoice {updated['id']} ({updated['currency']} {updated['amount']:,.2f}) to {updated['customer_email']}.",
        }

    def reconcile_expense(self, expense_id: str = "EXP-501", amount: float | None = None) -> dict[str, Any]:
        exp = self.accounting.get_expense(expense_id)
        if not exp:
            raise ValueError(f"Expense '{expense_id}' not found.")

        note = f"Receipt {exp['receipt_ref']} verified against {exp['category']} ledger ({exp['currency']} {exp['amount']:,.2f})."
        updated = self.accounting.update_expense_status(exp["id"], status="reconciled", note=note)
        return {
            "expense": updated,
            "summary": f"Reconciled expense {updated['id']} ({updated['vendor']}, {updated['currency']} {updated['amount']:,.2f}) for {updated['employee_name']}.",
        }

    def disburse_expense(self, expense_id: str = "EXP-501") -> dict[str, Any]:
        exp = self.accounting.get_expense(expense_id)
        if not exp:
            raise ValueError(f"Expense '{expense_id}' not found.")

        updated = self.accounting.update_expense_status(
            exp["id"],
            status="paid",
            note=f"Approved reimbursement payout of {exp['currency']} {exp['amount']:,.2f} initiated.",
        )
        self.slack.post_message(
            channel="#ops-audit-alerts",
            text=f"Payout executed: {updated['id']} — {updated['currency']} {updated['amount']:,.2f} to {updated['employee_name']}.",
            metadata={"expense_id": updated["id"], "amount": updated["amount"]},
        )
        return {
            "expense": updated,
            "summary": f"Disbursed {updated['currency']} {updated['amount']:,.2f} reimbursement for {updated['id']} to {updated['employee_name']}.",
        }

    def chase_overdue_invoices(self, invoice_id: str = "INV-2026-002") -> dict[str, Any]:
        inv = self.accounting.get_invoice(invoice_id)
        if not inv:
            overdue = self.accounting.list_invoices(status="overdue")
            if not overdue:
                return {"sent": False, "summary": "No overdue invoices found."}
            inv = overdue[0]

        rules = self.config_manager.load_rules()
        prompts = self.config_manager.load_prompts()
        template = prompts["domains"]["accounting"]["overdue_reminder_template"]
        body = template.format(
            invoice_id=inv["id"],
            currency=inv["currency"],
            amount=float(inv["amount"]),
            customer_name=inv["customer_name"],
            due_date=inv["due_date"],
            days_overdue=14,
            organization=rules.get("organization", "Acme Operations Pte Ltd"),
        )
        email_res = self.email.send_email(
            to_email=inv["customer_email"],
            subject=f"Payment Reminder — Overdue Invoice {inv['id']} ({inv['currency']} {inv['amount']:,.2f})",
            body=body,
            metadata={"domain": "accounting", "invoice_id": inv["id"], "action": "chase_overdue_invoices"},
        )
        return {
            "invoice_id": inv["id"],
            "customer_name": inv["customer_name"],
            "to_email": inv["customer_email"],
            "amount": inv["amount"],
            "email_delivery": email_res,
            "summary": f"Sent overdue payment reminder for {inv['id']} ({inv['currency']} {inv['amount']:,.2f}) to {inv['customer_email']}.",
        }

    def compile_monthly_summary(self, month: str = "2026-11") -> dict[str, Any]:
        invoices = self.accounting.list_invoices()
        expenses = self.accounting.list_expenses()
        rules = self.config_manager.load_rules()
        currency = rules.get("currency", "SGD")

        total_invoiced = sum(float(i["amount"]) for i in invoices)
        paid_total = sum(float(i["amount"]) for i in invoices if i["status"] == "paid")
        overdue_total = sum(float(i["amount"]) for i in invoices if i["status"] == "overdue")
        overdue_count = sum(1 for i in invoices if i["status"] == "overdue")
        total_expenses = sum(float(e["amount"]) for e in expenses)

        report_text = (
            f"Monthly Financial Summary ({month})\n"
            f"- Total Invoiced: {currency} {total_invoiced:,.2f} ({len(invoices)} invoices)\n"
            f"- Collected (Paid): {currency} {paid_total:,.2f}\n"
            f"- Overdue AR: {currency} {overdue_total:,.2f} ({overdue_count} overdue)\n"
            f"- Total Logged Expenses: {currency} {total_expenses:,.2f} ({len(expenses)} claims)\n"
            f"- Net Cash Position (Collected - Expenses): {currency} {paid_total - total_expenses:,.2f}"
        )
        slack_res = self.slack.post_message(
            channel="#finance-ops",
            text=report_text,
            metadata={"domain": "accounting", "month": month},
        )
        return {
            "month": month,
            "currency": currency,
            "total_invoiced": total_invoiced,
            "paid_total": paid_total,
            "overdue_total": overdue_total,
            "overdue_count": overdue_count,
            "total_expenses": total_expenses,
            "report": report_text,
            "slack_delivery": slack_res,
            "summary": f"Compiled {month} summary (Invoiced {currency} {total_invoiced:,.2f}, Overdue {currency} {overdue_total:,.2f}, Expenses {currency} {total_expenses:,.2f}) and posted to #finance-ops.",
        }
