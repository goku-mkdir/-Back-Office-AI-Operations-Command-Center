"""Slack connector supporting Sandbox logging and Live Webhook / Bot API messaging."""

from __future__ import annotations

from typing import Any

import httpx

from backoffice_agent.database import Database
from backoffice_agent.settings import Settings, get_settings


class SlackConnector:
    """Posts operational alerts and approval requests to Slack (live or sandbox)."""

    def __init__(self, db: Database, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    @property
    def is_live(self) -> bool:
        return self.settings.slack_mode.lower() == "live" and self.settings.app_mode.lower() == "live"

    def post_message(
        self,
        channel: str,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.is_live:
            if self.settings.slack_bot_token:
                resp = httpx.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {self.settings.slack_bot_token}"},
                    json={"channel": channel, "text": text},
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    raise RuntimeError(f"Slack API error: {data.get('error')}")
            elif self.settings.slack_webhook_url:
                resp = httpx.post(
                    self.settings.slack_webhook_url,
                    json={"text": f"[{channel}] {text}"},
                    timeout=10.0,
                )
                resp.raise_for_status()
            else:
                raise RuntimeError("Configure SLACK_BOT_TOKEN or SLACK_WEBHOOK_URL for live Slack mode.")

            msg_id = self.db.record_outbound_message(
                channel="slack",
                recipient=channel,
                subject="Slack Message",
                body=text,
                mode="live",
                metadata=metadata,
            )
            return {"posted": True, "mode": "live", "message_id": msg_id, "channel": channel}

        msg_id = self.db.record_outbound_message(
            channel="slack",
            recipient=channel,
            subject="Slack Message",
            body=text,
            mode="sandbox",
            metadata=metadata,
        )
        return {"posted": True, "mode": "sandbox", "message_id": msg_id, "channel": channel}
