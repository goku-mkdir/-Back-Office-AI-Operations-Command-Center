"""Sales Operations tool implementations (CRM hygiene, lead nurturing, quotes, follow-ups)."""

from __future__ import annotations

from typing import Any

from backoffice_agent.connectors import CRMConnector, EmailConnector, SlackConnector
from backoffice_agent.settings import ConfigManager


class SalesTools:
    """Implements autonomous CRM/drafting tasks and HITL-gated external outreach & quotes."""

    def __init__(
        self,
        crm: CRMConnector,
        email: EmailConnector,
        slack: SlackConnector,
        config_manager: ConfigManager,
    ) -> None:
        self.crm = crm
        self.email = email
        self.slack = slack
        self.config_manager = config_manager

    def update_crm_lead(
        self,
        lead_id: str = "LEAD-301",
        stage: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        updated = self.crm.update_lead(lead_id, stage=stage, note=note)
        return {
            "lead": updated,
            "summary": f"Updated CRM lead {updated['id']} ({updated['contact_name']} @ {updated['company']}) -> stage='{updated['stage']}'.",
        }

    def draft_nurture_email(
        self,
        lead_id: str = "LEAD-301",
        topic: str = "Back-office AI automation",
    ) -> dict[str, Any]:
        lead = self.crm.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead '{lead_id}' not found.")

        rules = self.config_manager.load_rules()
        prompts = self.config_manager.load_prompts()
        template = prompts["domains"]["sales"]["nurture_email_template"]
        body = template.format(
            contact_name=lead["contact_name"],
            company_name=lead["company"],
            organization=rules.get("organization", "Acme Operations Pte Ltd"),
            topic=topic,
        )
        self.crm.update_lead(lead["id"], note=f"Drafted nurture email on '{topic}'.")
        return {
            "lead_id": lead["id"],
            "contact_name": lead["contact_name"],
            "to_email": lead["email"],
            "subject": f"Quick idea for {lead['company']} — {topic}",
            "body": body,
            "summary": f"Drafted nurture email for {lead['contact_name']} ({lead['company']}).",
        }

    def send_nurture_email(
        self,
        lead_id: str = "LEAD-301",
        topic: str = "Back-office AI automation",
    ) -> dict[str, Any]:
        draft = self.draft_nurture_email(lead_id=lead_id, topic=topic)
        email_res = self.email.send_email(
            to_email=draft["to_email"],
            subject=draft["subject"],
            body=draft["body"],
            metadata={"domain": "sales", "lead_id": draft["lead_id"], "action": "send_nurture_email"},
        )
        self.crm.update_lead(draft["lead_id"], mark_contacted=True, note="Nurture email sent externally.")
        return {
            "lead_id": draft["lead_id"],
            "to_email": draft["to_email"],
            "email_delivery": email_res,
            "summary": f"Sent nurture email to {draft['contact_name']} <{draft['to_email']}>.",
        }

    def prepare_quote(
        self,
        lead_id: str = "LEAD-302",
        items_summary: str = "Back-Office AI Agent Annual License (25 seats) + Onboarding",
        subtotal: float = 24000.0,
        discount_pct: float = 5.0,
    ) -> dict[str, Any]:
        lead = self.crm.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead '{lead_id}' not found.")

        rules = self.config_manager.load_rules()
        prompts = self.config_manager.load_prompts()
        currency = rules.get("currency", "SGD")

        subtotal_f = float(subtotal)
        discount_f = float(discount_pct)
        discount_amount = round(subtotal_f * (discount_f / 100.0), 2)
        total = round(subtotal_f - discount_amount, 2)

        temp_quote_text = prompts["domains"]["sales"]["quote_template"].format(
            quote_id="PENDING-ID",
            contact_name=lead["contact_name"],
            company_name=lead["company"],
            items_summary=items_summary,
            currency=currency,
            subtotal=subtotal_f,
            discount_pct=discount_f,
            discount_amount=discount_amount,
            total=total,
        )
        quote = self.crm.create_quote(
            lead_id=lead["id"],
            contact_name=lead["contact_name"],
            company=lead["company"],
            items_summary=items_summary,
            subtotal=subtotal_f,
            discount_pct=discount_f,
            total=total,
            quote_text=temp_quote_text,
        )
        final_text = temp_quote_text.replace("PENDING-ID", quote["id"])
        with self.crm.db.connect() as conn:
            conn.execute("UPDATE sandbox_quotes SET quote_text = ? WHERE id = ?", (final_text, quote["id"]))
        quote["quote_text"] = final_text

        self.crm.update_lead(lead["id"], stage="proposal", note=f"Prepared quote {quote['id']} ({currency} {total:,.2f}).")
        return {
            "quote": quote,
            "summary": f"Prepared quote {quote['id']} for {lead['company']}: {currency} {total:,.2f} ({discount_f:.1f}% discount).",
        }

    def send_quote(self, quote_id: str = "LATEST") -> dict[str, Any]:
        quote = self.crm.get_quote(quote_id)
        if not quote:
            raise ValueError(f"Quote '{quote_id}' not found.")
        lead = self.crm.get_lead(quote["lead_id"])
        to_email = lead["email"] if lead else "prospect@example.com"

        email_res = self.email.send_email(
            to_email=to_email,
            subject=f"Commercial Quote {quote['id']} — {quote['company']}",
            body=quote["quote_text"],
            metadata={"domain": "sales", "quote_id": quote["id"], "total": quote["total"]},
        )
        updated = self.crm.mark_quote_sent(quote["id"])
        if lead:
            self.crm.update_lead(lead["id"], mark_contacted=True, note=f"Quote {updated['id']} sent externally.")
        return {
            "quote": updated,
            "to_email": to_email,
            "email_delivery": email_res,
            "summary": f"Sent quote {updated['id']} ({updated['total']:,.2f}) externally to {updated['contact_name']} <{to_email}>.",
        }

    def schedule_followup(
        self,
        lead_id: str = "LEAD-301",
        due_date: str = "2026-12-01",
        topic: str = "Follow up on proposal & next steps",
    ) -> dict[str, Any]:
        lead = self.crm.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead '{lead_id}' not found.")

        fup = self.crm.create_followup(
            lead_id=lead["id"],
            owner=lead["owner"],
            due_date=due_date,
            topic=topic,
        )
        return {
            "followup": fup,
            "summary": f"Scheduled follow-up {fup['id']} for {lead['contact_name']} ({lead['company']}) on {due_date} (owner: {lead['owner']}).",
        }
