"""HR Operations tool implementations (screening, policy Q&A, offers, HRIS files)."""

from __future__ import annotations

from typing import Any

from backoffice_agent.connectors import EmailConnector, HRISConnector, SlackConnector
from backoffice_agent.settings import ConfigManager, Settings, get_settings


class HRTools:
    """Implements low-risk autonomous HR tasks and approval-gated external offer delivery."""

    def __init__(
        self,
        hris: HRISConnector,
        email: EmailConnector,
        slack: SlackConnector,
        config_manager: ConfigManager,
        settings: Settings | None = None,
    ) -> None:
        self.hris = hris
        self.email = email
        self.slack = slack
        self.config_manager = config_manager
        self.settings = settings or get_settings()

    def screen_resume(self, candidate_id: str = "CAND-101") -> dict[str, Any]:
        cand = self.hris.get_candidate(candidate_id)
        if not cand:
            raise ValueError(f"Candidate '{candidate_id}' not found.")

        resume_lower = cand["resume_text"].lower()
        rubric_keywords = ["python", "fastapi", "langgraph", "langchain", "sql", "aws", "docker", "automation", "xero", "hubspot"]
        matched = [kw for kw in rubric_keywords if kw in resume_lower]
        score = min(100, 45 + len(matched) * 8)
        recommendation = "Strong Shortlist" if score >= 80 else ("Review" if score >= 65 else "Hold")
        notes = f"Matched {len(matched)} core skills ({', '.join(matched)}). Score: {score}/100 ({recommendation})."

        updated = self.hris.update_candidate(
            cand["id"],
            score=score,
            status="shortlisted" if score >= 75 else "screened",
            screening_notes=notes,
        )
        return {
            "candidate_id": updated["id"],
            "candidate_name": updated["name"],
            "role": updated["role_applied"],
            "score": score,
            "recommendation": recommendation,
            "matched_skills": matched,
            "summary": f"Screened {updated['name']} ({updated['id']}) for {updated['role_applied']}: {score}/100 — {recommendation}.",
        }

    def answer_hr_policy(self, question: str, employee_id: str = "EMP-001") -> dict[str, Any]:
        policy_path = self.settings.hr_policy_file
        policy_text = policy_path.read_text(encoding="utf-8") if policy_path.exists() else ""
        emp = self.hris.get_employee(employee_id)

        q_lower = question.lower()
        relevant_sections: list[str] = []
        for section in policy_text.split("## "):
            s_lower = section.lower()
            if (
                ("leave" in q_lower and ("annual leave" in s_lower or "medical" in s_lower or "parental" in s_lower))
                or (("remote" in q_lower or "hybrid" in q_lower or "wfh" in q_lower) and "remote" in s_lower)
                or (("expense" in q_lower or "reimburse" in q_lower) and "expense" in s_lower)
                or ("sick" in q_lower and "medical" in s_lower)
            ):
                relevant_sections.append("## " + section.strip())

        if not relevant_sections and policy_text:
            relevant_sections.append(policy_text[:500].strip())

        balance_note = ""
        if emp:
            balance_note = (
                f" Employee {emp['name']} ({emp['id']}) currently has "
                f"{emp['annual_leave_balance']} annual leave days and "
                f"{emp['sick_leave_balance']} sick leave days remaining."
            )

        answer = "\n\n".join(relevant_sections) + (f"\n\n{balance_note.strip()}" if balance_note else "")
        return {
            "employee_id": emp["id"] if emp else employee_id,
            "question": question,
            "answer": answer.strip(),
            "summary": f"Answered HR policy inquiry for {emp['name'] if emp else employee_id}.{balance_note}",
        }

    def draft_offer_letter(
        self,
        candidate_id: str = "CAND-101",
        salary: float = 120000.0,
        start_date: str = "2027-01-04",
    ) -> dict[str, Any]:
        cand = self.hris.get_candidate(candidate_id)
        if not cand:
            raise ValueError(f"Candidate '{candidate_id}' not found.")

        rules = self.config_manager.load_rules()
        prompts = self.config_manager.load_prompts()
        template = prompts["domains"]["hr"]["offer_letter_template"]
        offer_text = template.format(
            candidate_name=cand["name"],
            role_title=cand["role_applied"],
            organization=rules.get("organization", "Acme Operations Pte Ltd"),
            start_date=start_date,
            currency=rules.get("currency", "SGD"),
            salary=float(salary),
        )
        updated = self.hris.update_candidate(cand["id"], status="offer_drafted", offer_draft=offer_text)
        return {
            "candidate_id": updated["id"],
            "candidate_name": updated["name"],
            "candidate_email": updated["email"],
            "salary": float(salary),
            "start_date": start_date,
            "offer_text": offer_text,
            "summary": f"Drafted offer letter for {updated['name']} ({updated['role_applied']}) at {rules.get('currency', 'SGD')} {float(salary):,.2f}/yr.",
        }

    def send_offer_letter(self, candidate_id: str = "CAND-101") -> dict[str, Any]:
        cand = self.hris.get_candidate(candidate_id)
        if not cand:
            raise ValueError(f"Candidate '{candidate_id}' not found.")

        offer_body = cand["offer_draft"]
        if not offer_body:
            drafted = self.draft_offer_letter(candidate_id=cand["id"])
            offer_body = drafted["offer_text"]

        email_res = self.email.send_email(
            to_email=cand["email"],
            subject=f"Offer of Employment — {cand['role_applied']}",
            body=offer_body,
            metadata={"domain": "hr", "candidate_id": cand["id"], "action": "send_offer_letter"},
        )
        self.hris.update_candidate(cand["id"], status="offer_sent")
        return {
            "candidate_id": cand["id"],
            "candidate_name": cand["name"],
            "to_email": cand["email"],
            "email_delivery": email_res,
            "summary": f"Sent offer letter externally to {cand['name']} <{cand['email']}> (mode={email_res['mode']}).",
        }

    def update_employee_file(
        self,
        employee_id: str = "EMP-001",
        title: str | None = None,
        salary: float | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        updated = self.hris.update_employee(employee_id, title=title, salary=salary, notes=notes)
        return {
            "employee": updated,
            "summary": f"Updated HRIS record for {updated.get('name', employee_id)} ({updated.get('id', employee_id)}).",
        }
