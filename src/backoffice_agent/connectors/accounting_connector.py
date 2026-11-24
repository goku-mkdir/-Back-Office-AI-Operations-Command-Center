"""Accounting connector supporting Sandbox SQLite and Live Xero REST API."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from backoffice_agent.database import Database, utc_now_iso
from backoffice_agent.settings import Settings, get_settings


class AccountingConnector:
    """Manages invoices, expenses, and financial summaries (Xero live or SQLite sandbox)."""

    def __init__(self, db: Database, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    @property
    def is_live(self) -> bool:
        return self.settings.accounting_mode.lower() == "live" and self.settings.app_mode.lower() == "live"

    def _xero_headers(self) -> dict[str, str]:
        if not (self.settings.xero_access_token and self.settings.xero_tenant_id):
            raise RuntimeError("XERO_ACCESS_TOKEN and XERO_TENANT_ID are required in live accounting mode.")
        return {
            "Authorization": f"Bearer {self.settings.xero_access_token}",
            "Xero-tenant-id": self.settings.xero_tenant_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # --- Invoices ---
    def list_invoices(self, status: str | None = None) -> list[dict[str, Any]]:
        if self.is_live:
            resp = httpx.get(
                "https://api.xero.com/api.xro/2.0/Invoices",
                headers=self._xero_headers(),
                timeout=15.0,
            )
            resp.raise_for_status()
            return resp.json().get("Invoices", [])

        with self.db.connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM sandbox_invoices WHERE status = ? ORDER BY id DESC", (status,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM sandbox_invoices ORDER BY id DESC").fetchall()
            return [dict(r) for r in rows]

    def get_invoice(self, invoice_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            if invoice_id.upper() == "LATEST":
                row = conn.execute(
                    "SELECT * FROM sandbox_invoices ORDER BY rowid DESC LIMIT 1"
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM sandbox_invoices WHERE id = ?", (invoice_id,)
                ).fetchone()
            return dict(row) if row else None

    def create_draft_invoice(
        self,
        *,
        customer_name: str,
        customer_email: str,
        description: str,
        amount: float,
        due_date: str,
        currency: str = "SGD",
    ) -> dict[str, Any]:
        inv_id = f"INV-2026-{str(uuid.uuid4().int)[:4]}"
        if self.is_live:
            payload = {
                "Type": "ACCREC",
                "Contact": {"Name": customer_name, "EmailAddress": customer_email},
                "DueDate": due_date,
                "LineItems": [{"Description": description, "Quantity": 1, "UnitAmount": amount}],
                "Status": "DRAFT",
            }
            resp = httpx.post(
                "https://api.xero.com/api.xro/2.0/Invoices",
                headers=self._xero_headers(),
                json={"Invoices": [payload]},
                timeout=15.0,
            )
            resp.raise_for_status()
            return resp.json().get("Invoices", [payload])[0]

        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO sandbox_invoices
                (id, customer_name, customer_email, description, amount, currency, due_date, status, sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', '')
                """,
                (inv_id, customer_name, customer_email, description, float(amount), currency, due_date),
            )
        return self.get_invoice(inv_id)  # type: ignore[return-value]

    def mark_invoice_sent(self, invoice_id: str) -> dict[str, Any]:
        inv = self.get_invoice(invoice_id)
        if not inv:
            raise ValueError(f"Invoice '{invoice_id}' not found.")
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE sandbox_invoices SET status = 'sent', sent_at = ? WHERE id = ?",
                (utc_now_iso(), inv["id"]),
            )
        return self.get_invoice(inv["id"])  # type: ignore[return-value]

    # --- Expenses ---
    def list_expenses(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM sandbox_expenses ORDER BY id").fetchall()
            return [dict(r) for r in rows]

    def get_expense(self, expense_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sandbox_expenses WHERE id = ?", (expense_id,)
            ).fetchone()
            return dict(row) if row else None

    def update_expense_status(self, expense_id: str, status: str, note: str = "") -> dict[str, Any]:
        exp = self.get_expense(expense_id)
        if not exp:
            raise ValueError(f"Expense '{expense_id}' not found.")
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE sandbox_expenses SET status = ?, reconciled_note = ? WHERE id = ?",
                (status, note or exp["reconciled_note"], exp["id"]),
            )
        return self.get_expense(exp["id"])  # type: ignore[return-value]
