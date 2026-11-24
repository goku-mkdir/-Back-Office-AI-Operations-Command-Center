"""Email connector supporting Sandbox logging and Live Gmail/SMTP dispatch."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from backoffice_agent.database import Database
from backoffice_agent.settings import Settings, get_settings


class EmailConnector:
    """Sends external emails via SMTP (live mode) or records them in SQLite (sandbox mode)."""

    def __init__(self, db: Database, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    @property
    def is_live(self) -> bool:
        return self.settings.email_mode.lower() == "live" and self.settings.app_mode.lower() == "live"

    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.is_live:
            if not (self.settings.smtp_username and self.settings.smtp_password):
                raise RuntimeError("SMTP_USERNAME and SMTP_PASSWORD must be set in .env for live email mode.")
            msg = EmailMessage()
            msg["From"] = self.settings.email_from_address
            msg["To"] = to_email
            msg["Subject"] = subject
            msg.set_content(body)
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15) as server:
                server.starttls()
                server.login(self.settings.smtp_username, self.settings.smtp_password)
                server.send_message(msg)
            msg_id = self.db.record_outbound_message(
                channel="email",
                recipient=to_email,
                subject=subject,
                body=body,
                mode="live",
                metadata=metadata,
            )
            return {"sent": True, "mode": "live", "message_id": msg_id, "to": to_email, "subject": subject}

        msg_id = self.db.record_outbound_message(
            channel="email",
            recipient=to_email,
            subject=subject,
            body=body,
            mode="sandbox",
            metadata=metadata,
        )
        return {
            "sent": True,
            "mode": "sandbox",
            "message_id": msg_id,
            "to": to_email,
            "subject": subject,
            "preview": body[:200],
        }
