"""CRM connector supporting Sandbox SQLite and Live HubSpot REST API."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from backoffice_agent.database import Database, utc_now_iso
from backoffice_agent.settings import Settings, get_settings


class CRMConnector:
    """Manages leads, quotes, and follow-up tasks (HubSpot live or SQLite sandbox)."""

    def __init__(self, db: Database, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    @property
    def is_live(self) -> bool:
        return self.settings.crm_mode.lower() == "live" and self.settings.app_mode.lower() == "live"

    def _hubspot_headers(self) -> dict[str, str]:
        if not self.settings.hubspot_access_token:
            raise RuntimeError("HUBSPOT_ACCESS_TOKEN is required in live CRM mode.")
        return {
            "Authorization": f"Bearer {self.settings.hubspot_access_token}",
            "Content-Type": "application/json",
        }

    def list_leads(self) -> list[dict[str, Any]]:
        if self.is_live:
            resp = httpx.get(
                "https://api.hubapi.com/crm/v3/objects/contacts?limit=50",
                headers=self._hubspot_headers(),
                timeout=15.0,
            )
            resp.raise_for_status()
            return resp.json().get("results", [])

        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM sandbox_leads ORDER BY id").fetchall()
            return [dict(r) for r in rows]

    def get_lead(self, lead_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sandbox_leads WHERE id = ? OR LOWER(contact_name) LIKE ? OR LOWER(company) LIKE ?",
                (lead_id, f"%{lead_id.lower()}%", f"%{lead_id.lower()}%"),
            ).fetchone()
            return dict(row) if row else None

    def update_lead(
        self,
        lead_id: str,
        *,
        stage: str | None = None,
        note: str | None = None,
        mark_contacted: bool = False,
    ) -> dict[str, Any]:
        if self.is_live:
            props: dict[str, Any] = {}
            if stage:
                props["lifecyclestage"] = stage
            resp = httpx.patch(
                f"https://api.hubapi.com/crm/v3/objects/contacts/{lead_id}",
                headers=self._hubspot_headers(),
                json={"properties": props},
                timeout=15.0,
            )
            resp.raise_for_status()
            return resp.json()

        lead = self.get_lead(lead_id)
        if not lead:
            raise ValueError(f"Lead '{lead_id}' not found in CRM.")

        new_stage = stage or lead["stage"]
        new_notes = f"{lead['notes']} | {note}".strip(" |") if note else lead["notes"]
        last_contacted = utc_now_iso()[:10] if mark_contacted else lead["last_contacted"]

        with self.db.connect() as conn:
            conn.execute(
                "UPDATE sandbox_leads SET stage = ?, notes = ?, last_contacted = ? WHERE id = ?",
                (new_stage, new_notes, last_contacted, lead["id"]),
            )
        return self.get_lead(lead["id"]) or lead

    # --- Quotes ---
    def create_quote(
        self,
        *,
        lead_id: str,
        contact_name: str,
        company: str,
        items_summary: str,
        subtotal: float,
        discount_pct: float,
        total: float,
        quote_text: str,
    ) -> dict[str, Any]:
        quote_id = f"QT-2026-{str(uuid.uuid4().int)[:4]}"
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO sandbox_quotes
                (id, lead_id, contact_name, company, items_summary, subtotal, discount_pct, total, status, quote_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?)
                """,
                (quote_id, lead_id, contact_name, company, items_summary, subtotal, discount_pct, total, quote_text),
            )
        return self.get_quote(quote_id)  # type: ignore[return-value]

    def get_quote(self, quote_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            if quote_id.upper() == "LATEST":
                row = conn.execute(
                    "SELECT * FROM sandbox_quotes ORDER BY rowid DESC LIMIT 1"
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM sandbox_quotes WHERE id = ?", (quote_id,)
                ).fetchone()
            return dict(row) if row else None

    def list_quotes(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM sandbox_quotes ORDER BY rowid DESC").fetchall()
            return [dict(r) for r in rows]

    def mark_quote_sent(self, quote_id: str) -> dict[str, Any]:
        quote = self.get_quote(quote_id)
        if not quote:
            raise ValueError(f"Quote '{quote_id}' not found.")
        with self.db.connect() as conn:
            conn.execute("UPDATE sandbox_quotes SET status = 'sent' WHERE id = ?", (quote["id"],))
        return self.get_quote(quote["id"])  # type: ignore[return-value]

    # --- Follow-ups ---
    def create_followup(self, *, lead_id: str, owner: str, due_date: str, topic: str) -> dict[str, Any]:
        followup_id = f"FUP-{str(uuid.uuid4().int)[:4]}"
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO sandbox_followups (id, lead_id, owner, due_date, topic, status)
                VALUES (?, ?, ?, ?, ?, 'scheduled')
                """,
                (followup_id, lead_id, owner, due_date, topic),
            )
            row = conn.execute(
                "SELECT * FROM sandbox_followups WHERE id = ?", (followup_id,)
            ).fetchone()
            return dict(row)

    def list_followups(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM sandbox_followups ORDER BY rowid DESC").fetchall()
            return [dict(r) for r in rows]
