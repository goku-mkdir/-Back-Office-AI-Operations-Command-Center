"""HRIS connector supporting Sandbox SQLite and Live BambooHR REST API."""

from __future__ import annotations

from typing import Any

import httpx

from backoffice_agent.database import Database
from backoffice_agent.settings import Settings, get_settings


class HRISConnector:
    """Manages employee records and candidate pipelines (BambooHR live or SQLite sandbox)."""

    def __init__(self, db: Database, settings: Settings | None = None) -> None:
        self.db = db
        self.settings = settings or get_settings()

    @property
    def is_live(self) -> bool:
        return self.settings.hris_mode.lower() == "live" and self.settings.app_mode.lower() == "live"

    def _bamboohr_url(self, path: str) -> str:
        if not (self.settings.bamboohr_subdomain and self.settings.bamboohr_api_key):
            raise RuntimeError("BAMBOOHR_SUBDOMAIN and BAMBOOHR_API_KEY are required in live HRIS mode.")
        return f"https://api.bamboohr.com/api/gateway.php/{self.settings.bamboohr_subdomain}/v1/{path.lstrip('/')}"

    def list_employees(self) -> list[dict[str, Any]]:
        if self.is_live:
            resp = httpx.get(
                self._bamboohr_url("employees/directory"),
                auth=(self.settings.bamboohr_api_key, "x"),
                headers={"Accept": "application/json"},
                timeout=15.0,
            )
            resp.raise_for_status()
            return resp.json().get("employees", [])

        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM sandbox_employees ORDER BY id").fetchall()
            return [dict(r) for r in rows]

    def get_employee(self, employee_id: str) -> dict[str, Any] | None:
        if self.is_live:
            resp = httpx.get(
                self._bamboohr_url(f"employees/{employee_id}/?fields=displayName,workEmail,department,jobTitle"),
                auth=(self.settings.bamboohr_api_key, "x"),
                headers={"Accept": "application/json"},
                timeout=15.0,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sandbox_employees WHERE id = ? OR LOWER(name) LIKE ?",
                (employee_id, f"%{employee_id.lower()}%"),
            ).fetchone()
            return dict(row) if row else None

    def update_employee(
        self,
        employee_id: str,
        *,
        title: str | None = None,
        salary: float | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        if self.is_live:
            payload: dict[str, Any] = {}
            if title:
                payload["jobTitle"] = title
            if salary is not None:
                payload["payRate"] = str(salary)
            resp = httpx.post(
                self._bamboohr_url(f"employees/{employee_id}"),
                auth=(self.settings.bamboohr_api_key, "x"),
                json=payload,
                timeout=15.0,
            )
            resp.raise_for_status()
            return {"updated": True, "mode": "live", "employee_id": employee_id, "changes": payload}

        emp = self.get_employee(employee_id)
        if not emp:
            raise ValueError(f"Employee '{employee_id}' not found in HRIS.")

        new_title = title if title is not None else emp["title"]
        new_salary = float(salary) if salary is not None else emp["salary"]
        new_notes = f"{emp['notes']} | {notes}".strip(" |") if notes else emp["notes"]

        with self.db.connect() as conn:
            conn.execute(
                "UPDATE sandbox_employees SET title = ?, salary = ?, notes = ? WHERE id = ?",
                (new_title, new_salary, new_notes, emp["id"]),
            )
        return self.get_employee(emp["id"]) or emp

    # --- Candidate Pipeline ---
    def list_candidates(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM sandbox_candidates ORDER BY id").fetchall()
            return [dict(r) for r in rows]

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sandbox_candidates WHERE id = ? OR LOWER(name) LIKE ?",
                (candidate_id, f"%{candidate_id.lower()}%"),
            ).fetchone()
            return dict(row) if row else None

    def update_candidate(
        self,
        candidate_id: str,
        *,
        score: int | None = None,
        status: str | None = None,
        screening_notes: str | None = None,
        offer_draft: str | None = None,
    ) -> dict[str, Any]:
        cand = self.get_candidate(candidate_id)
        if not cand:
            raise ValueError(f"Candidate '{candidate_id}' not found.")

        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE sandbox_candidates
                SET score = ?, status = ?, screening_notes = ?, offer_draft = ?
                WHERE id = ?
                """,
                (
                    score if score is not None else cand["score"],
                    status if status is not None else cand["status"],
                    screening_notes if screening_notes is not None else cand["screening_notes"],
                    offer_draft if offer_draft is not None else cand["offer_draft"],
                    cand["id"],
                ),
            )
        return self.get_candidate(cand["id"]) or cand
