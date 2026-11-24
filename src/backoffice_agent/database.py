"""SQLite persistence for audit trail, approval queue, agent runs, and sandbox records."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Database:
    """Thread-safe SQLite wrapper backing audit logs, approvals, and sandbox data."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        self._seed_sandbox_data()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    user_request TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    status TEXT NOT NULL,
                    steps_json TEXT NOT NULL DEFAULT '[]',
                    final_response TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS approval_requests (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    action_name TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    approver_role TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    decided_by TEXT DEFAULT '',
                    decision_note TEXT DEFAULT '',
                    execution_result_json TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    action_name TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}'
                );

                -- Sandbox HRIS tables
                CREATE TABLE IF NOT EXISTS sandbox_employees (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    department TEXT NOT NULL,
                    title TEXT NOT NULL,
                    salary REAL NOT NULL,
                    annual_leave_balance INTEGER NOT NULL,
                    sick_leave_balance INTEGER NOT NULL,
                    manager TEXT NOT NULL,
                    notes TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS sandbox_candidates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    role_applied TEXT NOT NULL,
                    resume_text TEXT NOT NULL,
                    score INTEGER DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'new',
                    screening_notes TEXT DEFAULT '',
                    offer_draft TEXT DEFAULT ''
                );

                -- Sandbox Accounting tables
                CREATE TABLE IF NOT EXISTS sandbox_invoices (
                    id TEXT PRIMARY KEY,
                    customer_name TEXT NOT NULL,
                    customer_email TEXT NOT NULL,
                    description TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'SGD',
                    due_date TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    sent_at TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS sandbox_expenses (
                    id TEXT PRIMARY KEY,
                    employee_name TEXT NOT NULL,
                    employee_email TEXT NOT NULL,
                    category TEXT NOT NULL,
                    vendor TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'SGD',
                    receipt_ref TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'submitted',
                    reconciled_note TEXT DEFAULT ''
                );

                -- Sandbox CRM tables
                CREATE TABLE IF NOT EXISTS sandbox_leads (
                    id TEXT PRIMARY KEY,
                    contact_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    company TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    estimated_value REAL NOT NULL,
                    owner TEXT NOT NULL,
                    notes TEXT DEFAULT '',
                    last_contacted TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS sandbox_quotes (
                    id TEXT PRIMARY KEY,
                    lead_id TEXT NOT NULL,
                    contact_name TEXT NOT NULL,
                    company TEXT NOT NULL,
                    items_summary TEXT NOT NULL,
                    subtotal REAL NOT NULL,
                    discount_pct REAL NOT NULL,
                    total REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    quote_text TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sandbox_followups (
                    id TEXT PRIMARY KEY,
                    lead_id TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'scheduled'
                );

                -- Outbound comms log (Emails & Slack alerts in sandbox mode)
                CREATE TABLE IF NOT EXISTS sandbox_outbound_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    subject TEXT DEFAULT '',
                    body TEXT NOT NULL,
                    mode TEXT NOT NULL DEFAULT 'sandbox',
                    metadata_json TEXT DEFAULT '{}'
                );
                """
            )

    def _seed_sandbox_data(self) -> None:
        with self.connect() as conn:
            emp_count = conn.execute("SELECT COUNT(*) FROM sandbox_employees").fetchone()[0]
            if emp_count == 0:
                conn.executemany(
                    """
                    INSERT INTO sandbox_employees
                    (id, name, email, department, title, salary, annual_leave_balance, sick_leave_balance, manager, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        ("EMP-001", "Wei Lin Tan", "weilin@acmeops.sg", "Engineering", "Senior Software Engineer", 115000.0, 12, 14, "Sarah Lim", "Hybrid schedule Tue-Thu"),
                        ("EMP-002", "Priya Nair", "priya@acmeops.sg", "Finance", "Finance Controller", 128000.0, 15, 13, "David Koh", "Primary finance approver"),
                        ("EMP-003", "Daniel Tan", "daniel@acmeops.sg", "Sales", "Account Executive", 92000.0, 9, 14, "Marcus Chua", "APAC mid-market coverage"),
                        ("EMP-004", "Sarah Lim", "sarah@acmeops.sg", "People Ops", "HR Director", 132000.0, 16, 14, "David Koh", "Primary HR approver"),
                    ],
                )

            cand_count = conn.execute("SELECT COUNT(*) FROM sandbox_candidates").fetchone()[0]
            if cand_count == 0:
                conn.executemany(
                    """
                    INSERT INTO sandbox_candidates
                    (id, name, email, role_applied, resume_text, score, status, screening_notes, offer_draft)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            "CAND-101",
                            "Aisha Rahman",
                            "aisha.rahman@example.com",
                            "Senior Python AI Engineer",
                            "6 years Python, FastAPI, LangGraph, LangChain, AWS, SQL, Docker, built production HR and finance automation agents.",
                            0,
                            "new",
                            "",
                            "",
                        ),
                        (
                            "CAND-102",
                            "Kevin Ong",
                            "kevin.ong@example.com",
                            "Operations Analyst",
                            "3 years Excel, Xero reconciliation, HubSpot reporting, customer invoicing.",
                            0,
                            "new",
                            "",
                            "",
                        ),
                    ],
                )

            inv_count = conn.execute("SELECT COUNT(*) FROM sandbox_invoices").fetchone()[0]
            if inv_count == 0:
                conn.executemany(
                    """
                    INSERT INTO sandbox_invoices
                    (id, customer_name, customer_email, description, amount, currency, due_date, status, sent_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        ("INV-2026-001", "Merlion Logistics Pte Ltd", "ap@merlionlogistics.sg", "Monthly Automation Retainer - Oct", 4800.00, "SGD", "2026-10-31", "paid", "2026-10-01T09:00:00Z"),
                        ("INV-2026-002", "HarbourTech Solutions", "billing@harbourtech.sg", "Workflow Implementation Phase 1", 7500.00, "SGD", "2026-11-05", "overdue", "2026-10-20T09:00:00Z"),
                        ("INV-2026-003", "Raffles Retail Group", "finance@rafflesretail.sg", "CRM Integration & Support", 3200.00, "SGD", "2026-11-10", "overdue", "2026-10-25T10:00:00Z"),
                        ("INV-2026-004", "Sentosa Cloud Pte Ltd", "accounts@sentosacloud.sg", "Q4 Advisory Retainer", 5500.00, "SGD", "2026-12-10", "sent", "2026-11-12T10:00:00Z"),
                    ],
                )

            exp_count = conn.execute("SELECT COUNT(*) FROM sandbox_expenses").fetchone()[0]
            if exp_count == 0:
                conn.executemany(
                    """
                    INSERT INTO sandbox_expenses
                    (id, employee_name, employee_email, category, vendor, amount, currency, receipt_ref, status, reconciled_note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        ("EXP-501", "Daniel Tan", "daniel@acmeops.sg", "Client Meal", "Lau Pa Sat Bistro", 145.00, "SGD", "RCPT-8821", "submitted", ""),
                        ("EXP-502", "Wei Lin Tan", "weilin@acmeops.sg", "Cloud Infrastructure", "AWS Singapore", 680.00, "SGD", "RCPT-8822", "submitted", ""),
                        ("EXP-503", "Sarah Lim", "sarah@acmeops.sg", "Software Subscription", "Notion Labs", 180.00, "SGD", "RCPT-8810", "reconciled", "Auto-matched against statement"),
                    ],
                )

            lead_count = conn.execute("SELECT COUNT(*) FROM sandbox_leads").fetchone()[0]
            if lead_count == 0:
                conn.executemany(
                    """
                    INSERT INTO sandbox_leads
                    (id, contact_name, email, company, stage, estimated_value, owner, notes, last_contacted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        ("LEAD-301", "Chloe Goh", "chloe.goh@pacificfin.sg", "Pacific FinTech Pte Ltd", "discovery", 18000.00, "Daniel Tan", "Interested in automating finance & HR back-office workflows.", "2026-11-18"),
                        ("LEAD-302", "Rajesh Menon", "rajesh@kestrelmfg.sg", "Kestrel Manufacturing", "qualified", 24000.00, "Daniel Tan", "Requested quote for 25-seat deployment with Xero + HubSpot.", "2026-11-20"),
                        ("LEAD-303", "Mei Ling Zhou", "meiling@orchardhealth.sg", "Orchard Health Clinic", "new", 12000.00, "Daniel Tan", "Inbound demo request via website.", "2026-11-22"),
                    ],
                )

    def reset_sandbox(self) -> None:
        """Clear runtime tables and re-seed clean demo data for client presentations."""
        tables = [
            "agent_runs",
            "approval_requests",
            "audit_logs",
            "sandbox_employees",
            "sandbox_candidates",
            "sandbox_invoices",
            "sandbox_expenses",
            "sandbox_leads",
            "sandbox_quotes",
            "sandbox_followups",
            "sandbox_outbound_messages",
        ]
        with self.connect() as conn:
            for tbl in tables:
                conn.execute(f"DELETE FROM {tbl}")
        self._seed_sandbox_data()

    # --- Helpers for Agent Runs ---
    def upsert_run(
        self,
        *,
        run_id: str,
        thread_id: str,
        user_request: str,
        domain: str,
        status: str,
        steps: list[dict[str, Any]],
        final_response: str = "",
    ) -> None:
        now = utc_now_iso()
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE agent_runs
                    SET updated_at = ?, domain = ?, status = ?, steps_json = ?, final_response = ?
                    WHERE id = ?
                    """,
                    (now, domain, status, json.dumps(steps), final_response, run_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO agent_runs
                    (id, thread_id, created_at, updated_at, user_request, domain, status, steps_json, final_response)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, thread_id, now, now, user_request, domain, status, json.dumps(steps), final_response),
                )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM agent_runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["steps"] = json.loads(d.pop("steps_json"))
            return d

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            out = []
            for row in rows:
                d = dict(row)
                d["steps"] = json.loads(d.pop("steps_json"))
                out.append(d)
            return out

    # --- Helpers for Approval Requests ---
    def create_approval_request(
        self,
        *,
        approval_id: str,
        thread_id: str,
        run_id: str,
        domain: str,
        action_name: str,
        risk_level: str,
        approver_role: str,
        reason: str,
        summary: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO approval_requests
                (id, created_at, updated_at, thread_id, run_id, domain, action_name, risk_level,
                 approver_role, reason, summary, payload_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    approval_id,
                    now,
                    now,
                    thread_id,
                    run_id,
                    domain,
                    action_name,
                    risk_level,
                    approver_role,
                    reason,
                    summary,
                    json.dumps(payload),
                ),
            )
        return self.get_approval_request(approval_id)  # type: ignore[return-value]

    def get_approval_request(self, approval_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM approval_requests WHERE id = ?", (approval_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            d["payload"] = json.loads(d.pop("payload_json"))
            d["execution_result"] = json.loads(d.pop("execution_result_json") or "{}")
            return d

    def list_approval_requests(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM approval_requests WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM approval_requests ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            out = []
            for row in rows:
                d = dict(row)
                d["payload"] = json.loads(d.pop("payload_json"))
                d["execution_result"] = json.loads(d.pop("execution_result_json") or "{}")
                out.append(d)
            return out

    def update_approval_decision(
        self,
        *,
        approval_id: str,
        status: str,
        decided_by: str,
        decision_note: str = "",
        execution_result: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE approval_requests
                SET status = ?, updated_at = ?, decided_by = ?, decision_note = ?, execution_result_json = ?
                WHERE id = ?
                """,
                (
                    status,
                    now,
                    decided_by,
                    decision_note,
                    json.dumps(execution_result or {}),
                    approval_id,
                ),
            )
        return self.get_approval_request(approval_id)

    # --- Helpers for Sandbox Outbound Comms ---
    def record_outbound_message(
        self,
        *,
        channel: str,
        recipient: str,
        subject: str,
        body: str,
        mode: str = "sandbox",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO sandbox_outbound_messages
                (timestamp, channel, recipient, subject, body, mode, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (utc_now_iso(), channel, recipient, subject, body, mode, json.dumps(metadata or {})),
            )
            return int(cur.lastrowid)

    def list_outbound_messages(self, channel: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if channel:
                rows = conn.execute(
                    "SELECT * FROM sandbox_outbound_messages WHERE channel = ? ORDER BY id DESC LIMIT ?",
                    (channel, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM sandbox_outbound_messages ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["metadata"] = json.loads(d.pop("metadata_json") or "{}")
                out.append(d)
            return out
