"""Executive Interactive Operations Dashboard for the Back-Office AI Agent.

Features:
- Executive KPI Overview with interactive Altair analytics charts
- Live Agent Command Center with visual step timeline & inline HITL Approve/Reject
- Approval Queue + live simulated Slack & Outbound Email Inbox
- Interactive No-Code Policy Matrix (switches/sliders) + Live YAML Studio
- Searchable Audit Trail (CSV export) & Connected Stack Explorer
"""

from __future__ import annotations

import html
import os
from typing import Any

import altair as alt
import httpx
import pandas as pd
import streamlit as st
import yaml

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="OpsPilot AI — Back-Office Operations Command Center",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# CUSTOM MODERN SAAS STYLING
# =============================================================================
st.markdown(
    """
    <style>
    /* Global Polish */
    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 2.5rem;
        max-width: 1440px;
    }
    /* Hero Header */
    .hero-banner {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 55%, #1d4ed8 100%);
        border-radius: 16px;
        padding: 1.4rem 1.8rem;
        color: #f8fafc;
        margin-bottom: 1.2rem;
        border: 1px solid rgba(148, 163, 184, 0.25);
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.16);
    }
    .hero-title {
        font-size: 1.65rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin: 0;
        color: #ffffff;
    }
    .hero-sub {
        font-size: 0.94rem;
        color: #cbd5e1;
        margin-top: 0.35rem;
        margin-bottom: 0;
    }
    .status-pill {
        display: inline-block;
        padding: 0.2rem 0.65rem;
        border-radius: 999px;
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.03em;
        text-transform: uppercase;
        margin-right: 0.4rem;
    }
    .pill-green { background: rgba(16, 185, 129, 0.18); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.4); }
    .pill-amber { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.45); }
    .pill-red   { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(248, 113, 113, 0.45); }
    .pill-blue  { background: rgba(59, 130, 246, 0.2); color: #93c5fd; border: 1px solid rgba(147, 197, 253, 0.4); }

    /* KPI Metric Cards */
    .kpi-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 14px;
        padding: 1.05rem 1.2rem;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
        border-top: 4px solid #2563eb;
        height: 100%;
    }
    .kpi-card.amber { border-top-color: #f59e0b; }
    .kpi-card.green { border-top-color: #10b981; }
    .kpi-card.purple { border-top-color: #7c3aed; }
    .kpi-card.rose { border-top-color: #e11d48; }
    .kpi-label {
        font-size: 0.76rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #64748b;
        margin-bottom: 0.3rem;
    }
    .kpi-value {
        font-size: 1.75rem;
        font-weight: 800;
        color: #0f172a;
        line-height: 1.15;
    }
    .kpi-delta {
        font-size: 0.8rem;
        color: #475569;
        margin-top: 0.35rem;
    }

    /* Execution Stepper Cards */
    .step-card {
        border-radius: 12px;
        padding: 0.85rem 1.05rem;
        margin-bottom: 0.6rem;
        border: 1px solid #e2e8f0;
        background: #f8fafc;
    }
    .step-card.done { border-left: 5px solid #10b981; background: #f0fdf4; }
    .step-card.paused { border-left: 5px solid #f59e0b; background: #fffbeb; }
    .step-card.rejected { border-left: 5px solid #ef4444; background: #fef2f2; }
    .step-title {
        font-weight: 700;
        font-size: 0.95rem;
        color: #0f172a;
    }
    .step-body {
        font-size: 0.86rem;
        color: #334155;
        margin-top: 0.25rem;
    }

    /* Slack & Email Simulator Cards */
    .slack-card {
        background: #1a1d21;
        color: #e2e8f0;
        border-radius: 12px;
        padding: 0.9rem 1.05rem;
        margin-bottom: 0.65rem;
        border-left: 4px solid #36c5f0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }
    .slack-meta {
        font-size: 0.78rem;
        color: #94a3b8;
        margin-bottom: 0.3rem;
    }
    .slack-channel {
        color: #38bdf8;
        font-weight: 700;
    }
    .email-card {
        background: #ffffff;
        color: #0f172a;
        border: 1px solid #cbd5e1;
        border-left: 4px solid #2563eb;
        border-radius: 12px;
        padding: 0.95rem 1.1rem;
        margin-bottom: 0.7rem;
        box-shadow: 0 2px 6px rgba(15, 23, 42, 0.04);
    }
    .email-header {
        font-size: 0.82rem;
        color: #475569;
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 0.45rem;
        margin-bottom: 0.55rem;
    }
    .email-body {
        font-size: 0.86rem;
        white-space: pre-wrap;
        color: #1e293b;
        line-height: 1.45;
    }

    /* Dark-mode friendly overrides when Streamlit dark theme is active */
    @media (prefers-color-scheme: dark) {
        .kpi-card { background: #1e293b; border-color: #334155; }
        .kpi-value { color: #f8fafc; }
        .kpi-label { color: #94a3b8; }
        .kpi-delta { color: #cbd5e1; }
        .step-card { background: #1e293b; border-color: #334155; }
        .step-card.done { background: rgba(16, 185, 129, 0.12); }
        .step-card.paused { background: rgba(245, 158, 11, 0.12); }
        .step-card.rejected { background: rgba(239, 68, 68, 0.12); }
        .step-title { color: #f8fafc; }
        .step-body { color: #cbd5e1; }
        .email-card { background: #1e293b; border-color: #334155; color: #f8fafc; }
        .email-header { color: #94a3b8; border-bottom-color: #334155; }
        .email-body { color: #e2e8f0; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# API CLIENT HELPERS
# =============================================================================
def api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    resp = httpx.get(f"{API_BASE_URL}{path}", params=params, timeout=20.0)
    resp.raise_for_status()
    return resp.json()


def api_post(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    resp = httpx.post(f"{API_BASE_URL}{path}", json=payload or {}, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def api_put(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = httpx.put(f"{API_BASE_URL}{path}", json=payload, timeout=20.0)
    resp.raise_for_status()
    return resp.json()


def render_kpi(title: str, value: str, delta: str, accent: str = "") -> None:
    st.markdown(
        f"""
        <div class="kpi-card {accent}">
            <div class="kpi-label">{html.escape(title)}</div>
            <div class="kpi-value">{html.escape(value)}</div>
            <div class="kpi-delta">{html.escape(delta)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_approval_action_card(req: dict[str, Any], key_prefix: str) -> None:
    """Renders a sleek, human-readable approval card with inline Approve / Reject buttons."""
    payload = req.get("payload", {})
    preview = payload.get("preview", {})
    risk = str(req.get("risk_level", "high")).upper()
    domain = str(req.get("domain", "")).upper()

    with st.container(border=True):
        h1, h2 = st.columns([3, 1])
        h1.markdown(
            f"#### ⏸️ `{req['action_name']}` &nbsp; "
            f"<span class='status-pill pill-blue'>{domain}</span>"
            f"<span class='status-pill pill-red'>{risk} RISK</span>",
            unsafe_allow_html=True,
        )
        h2.markdown(f"<div style='text-align:right;font-size:0.82rem;color:#64748b;'>ID: <b>{req['id']}</b><br>{req['created_at']}</div>", unsafe_allow_html=True)

        st.markdown(f"**Action Summary:** {req['summary']}")
        st.warning(f"**Policy Guardrail Triggered ({req['approver_role']} required):** {req['reason']}")

        if preview:
            cols = st.columns(min(len(preview), 4))
            for idx, (k, v) in enumerate(preview.items()):
                cols[idx % len(cols)].metric(k.replace("_", " ").title(), str(v))
        else:
            with st.expander("View Action Parameters"):
                st.json(payload)

        if req["status"] == "pending":
            c_rev, c_note = st.columns([1, 2])
            reviewer = c_rev.text_input("Approver Name", value=req["approver_role"], key=f"{key_prefix}_rev_{req['id']}")
            note = c_note.text_input("Sign-Off Note", placeholder="e.g., Confirmed against budget / approved to send", key=f"{key_prefix}_note_{req['id']}")

            b1, b2, _ = st.columns([1.2, 1.2, 2])
            if b1.button("✅ Approve & Resume Agent", key=f"{key_prefix}_app_{req['id']}", type="primary", use_container_width=True):
                res = api_post(
                    f"/approvals/{req['id']}/decision",
                    {"approved": True, "decided_by": reviewer, "note": note},
                )
                st.session_state["last_run"] = res
                st.toast(f"Approved {req['id']} — LangGraph resumed!", icon="✅")
                st.rerun()
            if b2.button("❌ Reject & Block", key=f"{key_prefix}_rej_{req['id']}", use_container_width=True):
                res = api_post(
                    f"/approvals/{req['id']}/decision",
                    {"approved": False, "decided_by": reviewer, "note": note or "Blocked by reviewer"},
                )
                st.session_state["last_run"] = res
                st.toast(f"Blocked {req['id']} safely.", icon="🛑")
                st.rerun()
        else:
            pill = "pill-green" if req["status"] == "approved" else "pill-red"
            st.markdown(
                f"<span class='status-pill {pill}'>{req['status'].upper()}</span> "
                f"by **{req['decided_by']}** — _{req['decision_note'] or 'No note'}_",
                unsafe_allow_html=True,
            )


# =============================================================================
# FETCH LIVE DATA
# =============================================================================
try:
    health = api_get("/health")
    metrics = api_get("/metrics")
    overview = api_get("/sandbox/overview")
    all_approvals = api_get("/approvals", params={"limit": 100})["approvals"]
    pending_approvals = [a for a in all_approvals if a["status"] == "pending"]
    recent_logs = api_get("/audit", params={"limit": 200})["logs"]
except Exception as exc:
    st.error(
        f"Cannot connect to Back-Office Agent API at `{API_BASE_URL}`.\n\n"
        f"Start the API with: `uvicorn backoffice_agent.api.app:app --port 8000`\n\nDetails: `{exc}`"
    )
    st.stop()


# =============================================================================
# SIDEBAR — SYSTEM TELEMETRY & 1-CLICK DEMO CONTROLS
# =============================================================================
with st.sidebar:
    st.markdown("## ⚡ OpsPilot AI")
    st.caption("Autonomous Back-Office Agent • HITL Governed")

    st.markdown(
        f"<span class='status-pill pill-green'>API ONLINE</span>"
        f"<span class='status-pill pill-blue'>{health['app_mode'].upper()}</span>",
        unsafe_allow_html=True,
    )
    st.markdown("")

    st.markdown("### 🔌 Connected Stack")
    connector_icons = {
        "email": "✉️ Gmail / SMTP",
        "slack": "💬 Slack Alerts",
        "hris": "🧑‍💼 BambooHR",
        "accounting": "💰 Xero Ledger",
        "crm": "📈 HubSpot CRM",
    }
    for key, label in connector_icons.items():
        mode = health["connectors"].get(key, "sandbox")
        dot = "🟢" if mode == "live" else "🔵"
        st.markdown(f"{dot} **{label}** — `{mode}`")

    st.markdown(f"🧠 **LLM Engine:** `{health['llm_provider']}`")
    st.divider()

    st.markdown("### 🎬 Client Demo Controls")
    if st.button("🚀 Populate Live Demo Activity", use_container_width=True, type="primary"):
        demo_prompts = [
            "Answer annual leave and hybrid work policy for EMP-001",
            "Screen resume for CAND-101, draft offer letter at SGD 122000, and send offer email to candidate.",
            "Reconcile expense EXP-501, compile monthly summary, and chase overdue invoice INV-2026-002.",
            "Update CRM lead LEAD-302 to qualified, prepare quote for SGD 24000 with 8% discount, schedule follow-up, and send quote externally.",
        ]
        with st.spinner("Running HR, Accounting & Sales workflows..."):
            for p in demo_prompts:
                st.session_state["last_run"] = api_post("/agent/run", {"request": p})
        st.toast("Populated all 3 domains + 3 live HITL approval prompts!", icon="🚀")
        st.rerun()

    if st.button("🔄 Reset Sandbox Data", use_container_width=True):
        api_post("/sandbox/reset")
        st.session_state.pop("last_run", None)
        st.toast("Sandbox reset to fresh initial state.", icon="🔄")
        st.rerun()

    if st.button("↻ Refresh Dashboard", use_container_width=True):
        st.rerun()


# =============================================================================
# HERO HEADER
# =============================================================================
pending_badge = (
    f"<span class='status-pill pill-amber'>⏳ {len(pending_approvals)} Awaiting Sign-Off</span>"
    if pending_approvals
    else "<span class='status-pill pill-green'>✓ All Clear — 0 Pending</span>"
)
st.markdown(
    f"""
    <div class="hero-banner">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.6rem;">
            <div>
                <p class="hero-title">⚡ Back-Office AI Operations Command Center</p>
                <p class="hero-sub">Single LangGraph agent managing <b>HR</b>, <b>Accounting</b> &amp; <b>Sales</b> autonomously — halting on outbound money, contracts, and external emails.</p>
            </div>
            <div>
                {pending_badge}
                <span class="status-pill pill-blue">Audit Events: {len(recent_logs)}</span>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# =============================================================================
# MAIN NAVIGATION TABS
# =============================================================================
tab_home, tab_console, tab_approvals, tab_policy, tab_audit = st.tabs(
    [
        "📊 Executive Overview",
        "🤖 Agent Command Center",
        f"🚦 Approvals & Comms ({len(pending_approvals)})",
        "⚙️ Policy Matrix & YAML",
        "📜 Audit Trail & Stack",
    ]
)

# =============================================================================
# TAB 1: EXECUTIVE OVERVIEW (KPIs + INTERACTIVE CHARTS + INLINE SIGN-OFF)
# =============================================================================
with tab_home:
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        render_kpi(
            "Autonomy Rate",
            f"{metrics['autonomy_rate_pct']}%",
            f"{metrics['autonomous_actions']} auto • {metrics['hitl_executed_actions']} HITL",
            "green",
        )
    with k2:
        render_kpi(
            "Pending Sign-Offs",
            str(metrics["pending_approvals"]),
            f"{metrics['approved_count']} approved • {metrics['rejected_count']} blocked",
            "amber" if metrics["pending_approvals"] else "green",
        )
    with k3:
        render_kpi(
            "Overdue AR",
            f"SGD {metrics['ar_overdue_sgd']:,.0f}",
            f"Collected: SGD {metrics['ar_paid_sgd']:,.0f}",
            "rose",
        )
    with k4:
        render_kpi(
            "Active Sales Pipeline",
            f"SGD {metrics['pipeline_total_sgd']:,.0f}",
            f"{len(overview['leads'])} leads • {len(overview['quotes'])} quotes",
            "purple",
        )
    with k5:
        render_kpi(
            "Team Time Saved",
            f"{metrics['estimated_minutes_saved']} min",
            f"{metrics['emails_sent']} emails • {metrics['slack_alerts']} Slack alerts",
            "",
        )

    st.markdown("")

    # Inline urgent approvals banner right on the home dashboard
    if pending_approvals:
        st.subheader(f"🚦 Action Required — {len(pending_approvals)} High-Risk Action(s) Halted for Sign-Off")
        for req in pending_approvals[:3]:
            render_approval_action_card(req, key_prefix="home")
        if len(pending_approvals) > 3:
            st.caption(f"+ {len(pending_approvals) - 3} more pending in the Approvals & Comms tab.")
        st.divider()
    elif metrics["total_runs"] == 0:
        st.info(
            "👋 **Ready to demo?** Click **🚀 Populate Live Demo Activity** in the left sidebar to run HR, Accounting, and Sales end-to-end workflows and populate live charts + HITL sign-off cards in one click!"
        )

    # Interactive Charts Row
    ch1, ch2, ch3 = st.columns(3)

    with ch1:
        st.markdown("#### 🎯 Agent Governance by Domain")
        if recent_logs:
            event_map = {
                "autonomous_execution": "Autonomous",
                "resumed_execution": "HITL Approved",
                "approval_requested": "Paused (Gate)",
                "approval_rejected": "Blocked",
            }
            rows = [
                {"Domain": l["domain"].upper(), "Outcome": event_map[l["event_type"]]}
                for l in recent_logs
                if l["event_type"] in event_map
            ]
            if rows:
                df_gov = pd.DataFrame(rows).groupby(["Domain", "Outcome"]).size().reset_index(name="Count")
                chart_gov = (
                    alt.Chart(df_gov)
                    .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
                    .encode(
                        x=alt.X("Domain:N", title=""),
                        y=alt.Y("Count:Q", title="Actions"),
                        color=alt.Color(
                            "Outcome:N",
                            scale=alt.Scale(
                                domain=["Autonomous", "HITL Approved", "Paused (Gate)", "Blocked"],
                                range=["#10b981", "#2563eb", "#f59e0b", "#ef4444"],
                            ),
                            legend=alt.Legend(orient="bottom"),
                        ),
                        tooltip=["Domain", "Outcome", "Count"],
                    )
                    .properties(height=260)
                )
                st.altair_chart(chart_gov, use_container_width=True)
            else:
                st.caption("Run workflows to see governance metrics.")
        else:
            st.caption("No agent runs yet — click **Populate Live Demo Activity** in the sidebar.")

    with ch2:
        st.markdown("#### 💰 Accounts Receivable Health (SGD)")
        ar_df = pd.DataFrame(
            [
                {"Status": "Paid", "Amount": metrics["ar_paid_sgd"]},
                {"Status": "Sent", "Amount": metrics["ar_sent_sgd"]},
                {"Status": "Overdue", "Amount": metrics["ar_overdue_sgd"]},
                {"Status": "Draft", "Amount": metrics["ar_draft_sgd"]},
            ]
        )
        ar_df = ar_df[ar_df["Amount"] > 0]
        chart_ar = (
            alt.Chart(ar_df)
            .mark_arc(innerRadius=52, outerRadius=95)
            .encode(
                theta=alt.Theta("Amount:Q"),
                color=alt.Color(
                    "Status:N",
                    scale=alt.Scale(
                        domain=["Paid", "Sent", "Overdue", "Draft"],
                        range=["#10b981", "#3b82f6", "#ef4444", "#94a3b8"],
                    ),
                    legend=alt.Legend(orient="bottom"),
                ),
                tooltip=["Status", alt.Tooltip("Amount:Q", format=",.2f", title="SGD")],
            )
            .properties(height=260)
        )
        st.altair_chart(chart_ar, use_container_width=True)

    with ch3:
        st.markdown("#### 📈 Sales Pipeline by Stage (SGD)")
        if overview["leads"]:
            df_pipe = (
                pd.DataFrame(overview["leads"])
                .groupby("stage", as_index=False)["estimated_value"]
                .sum()
                .rename(columns={"stage": "Stage", "estimated_value": "Value"})
            )
            chart_pipe = (
                alt.Chart(df_pipe)
                .mark_bar(cornerRadiusEnd=6, color="#7c3aed")
                .encode(
                    y=alt.Y("Stage:N", sort="-x", title=""),
                    x=alt.X("Value:Q", title="Estimated Value (SGD)"),
                    tooltip=["Stage", alt.Tooltip("Value:Q", format=",.2f", title="SGD")],
                )
                .properties(height=260)
            )
            st.altair_chart(chart_pipe, use_container_width=True)

    # Recent Live Activity Feed
    st.markdown("#### ⚡ Live Operations Activity Feed")
    if recent_logs:
        feed_df = pd.DataFrame(
            [
                {
                    "Time": r["timestamp"].replace("T", " ").replace("Z", ""),
                    "Domain": r["domain"].upper(),
                    "Action": r["action_name"],
                    "Event": r["event_type"],
                    "Risk": r["risk_level"].upper(),
                    "Status": r["status"].upper(),
                    "Actor": r["actor"],
                    "Summary": r["summary"],
                }
                for r in recent_logs[:12]
            ]
        )
        st.dataframe(feed_df, use_container_width=True, hide_index=True)
    else:
        st.caption("Activity events will stream here automatically as the agent runs.")


# =============================================================================
# TAB 2: AGENT COMMAND CENTER (VISUAL PIPELINE + INLINE HITL)
# =============================================================================
with tab_console:
    st.subheader("Interactive Back-Office Agent Command Center")
    st.caption("Launch a multi-step HR, Accounting, or Sales workflow — watch autonomous steps complete instantly while high-risk actions halt at the LangGraph policy gate.")

    # Domain Quick-Launch Cards
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        with st.container(border=True):
            st.markdown("##### 🧑‍💼 HR Operations")
            if st.button("Screen CAND-101 + Draft & Send Offer", use_container_width=True):
                st.session_state["cmd_input"] = (
                    "Screen resume for CAND-101, draft offer letter at SGD 122000, and send offer email to candidate."
                )
            if st.button("Answer Leave & Hybrid Policy (Auto)", use_container_width=True):
                st.session_state["cmd_input"] = "Answer annual leave and hybrid work policy for EMP-001."
            if st.button("Promote EMP-001 Salary (Conditional Gate)", use_container_width=True):
                st.session_state["cmd_input"] = "Update employee EMP-001 salary to SGD 130000 and promote title."

    with sc2:
        with st.container(border=True):
            st.markdown("##### 💰 Accounting Operations")
            if st.button("Reconcile EXP-501 + Summary + Chase Overdue", use_container_width=True):
                st.session_state["cmd_input"] = (
                    "Reconcile expense EXP-501, compile monthly summary, and chase overdue invoice INV-2026-002."
                )
            if st.button("Reconcile High Expense EXP-502 (>250 SGD)", use_container_width=True):
                st.session_state["cmd_input"] = "Reconcile expense EXP-502 and disburse reimbursement."
            if st.button("Generate & Send New Invoice (SGD 5,200)", use_container_width=True):
                st.session_state["cmd_input"] = "Generate invoice for SGD 5200 and send invoice email to customer."

    with sc3:
        with st.container(border=True):
            st.markdown("##### 📈 Sales Operations")
            if st.button("Update LEAD-302 + Quote 8% + Follow-Up + Send", use_container_width=True):
                st.session_state["cmd_input"] = (
                    "Update CRM lead LEAD-302 to qualified, prepare quote for SGD 24000 with 8% discount, "
                    "schedule follow-up, and send quote externally."
                )
            if st.button("High Discount Quote 18% (>10% Threshold)", use_container_width=True):
                st.session_state["cmd_input"] = "Prepare quote for LEAD-301 at SGD 18000 with 18% discount."
            if st.button("Draft & Send Lead Nurture Email (HITL)", use_container_width=True):
                st.session_state["cmd_input"] = "Draft and send nurture email for early-stage lead LEAD-301."

    st.markdown("")
    with st.form("agent_command_form", clear_on_submit=False):
        cmd_text = st.text_area(
            "Agent Instruction",
            value=st.session_state.get("cmd_input", ""),
            height=80,
            placeholder="Describe any HR, Accounting, or Sales task...",
        )
        run_clicked = st.form_submit_button("▶️ Execute Agent Workflow", type="primary")
        if run_clicked and cmd_text.strip():
            with st.spinner("LangGraph agent planning, evaluating policies, and executing..."):
                st.session_state["last_run"] = api_post("/agent/run", {"request": cmd_text.strip()})
            st.rerun()

    # Visual Execution Trace + Inline Approval Sign-Off
    if "last_run" in st.session_state:
        run = st.session_state["last_run"]
        status = run.get("status", "completed")
        domain = str(run.get("domain", "general")).upper()

        st.divider()
        st.markdown(f"### 🔎 Execution Trace — `{run['run_id']}` ({domain})")

        steps = run.get("steps", [])
        for idx, step in enumerate(steps, start=1):
            st_status = step.get("status", "completed")
            css_cls = "done" if st_status == "completed" else ("rejected" if st_status == "rejected" else "paused")
            icon = "✅" if st_status == "completed" else ("❌" if st_status == "rejected" else "⏸️")
            mode_tag = "HITL APPROVED" if step.get("mode") == "approved_human_in_loop" else "AUTONOMOUS"
            pill_cls = "pill-blue" if mode_tag == "HITL APPROVED" else "pill-green"
            if st_status == "rejected":
                mode_tag, pill_cls = "BLOCKED", "pill-red"

            st.markdown(
                f"""
                <div class="step-card {css_cls}">
                    <div class="step-title">
                        {icon} Step {idx}: <code>{html.escape(step.get('action_name', ''))}</code>
                        &nbsp;<span class="status-pill {pill_cls}">{mode_tag}</span>
                    </div>
                    <div class="step-body">{html.escape(str(step.get('summary', '')))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Pretty document preview if offer/quote/report/answer was generated
            res_obj = step.get("result", {}) if isinstance(step.get("result"), dict) else {}
            doc_text = (
                res_obj.get("offer_text")
                or (res_obj.get("quote", {}) or {}).get("quote_text")
                or res_obj.get("report")
                or res_obj.get("answer")
                or res_obj.get("body")
            )
            if doc_text:
                with st.expander(f"📄 View Generated Document / Output ({step.get('action_name')})"):
                    st.code(str(doc_text), language="markdown")

        # If halted, render the live inline HITL approval card right here!
        if status == "awaiting_approval" and run.get("pending_approval"):
            apr_id = run["pending_approval"]["approval_id"]
            matching = [a for a in all_approvals if a["id"] == apr_id]
            if matching:
                render_approval_action_card(matching[0], key_prefix="inline")
        elif status == "completed":
            st.success("Workflow completed end-to-end and recorded in the audit trail.")


# =============================================================================
# TAB 3: APPROVAL QUEUE + LIVE SLACK & OUTBOUND EMAIL SIMULATOR
# =============================================================================
with tab_approvals:
    left_col, right_col = st.columns([1.25, 1])

    with left_col:
        st.subheader("🚦 Human-in-the-Loop Sign-Off Queue")
        f_status = st.segmented_control(
            "Filter Queue",
            options=["pending", "approved", "rejected", "all"],
            default="pending",
        )
        filtered = all_approvals if f_status == "all" else [a for a in all_approvals if a["status"] == f_status]
        if not filtered:
            st.info(f"No `{f_status}` approval requests right now.")
        else:
            for req in filtered:
                render_approval_action_card(req, key_prefix="queue")

    with right_col:
        st.subheader("📡 Live Slack & Outbound Email Feed")
        st.caption("Real-time view of every Slack alert and approved external email leaving the system.")
        outbound = overview.get("outbound_messages", [])
        slack_msgs = [m for m in outbound if m["channel"] == "slack"]
        email_msgs = [m for m in outbound if m["channel"] == "email"]

        sub_slack, sub_email = st.tabs([f"💬 Slack ({len(slack_msgs)})", f"✉️ Sent Emails ({len(email_msgs)})"])

        with sub_slack:
            if not slack_msgs:
                st.caption("No Slack alerts dispatched yet.")
            for m in slack_msgs[:12]:
                st.markdown(
                    f"""
                    <div class="slack-card">
                        <div class="slack-meta"><span class="slack-channel">{html.escape(m['recipient'])}</span> • {html.escape(m['timestamp'])} • mode: <code>{html.escape(m['mode'])}</code></div>
                        <div style="font-size:0.86rem;white-space:pre-wrap;">{html.escape(m['body'])}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with sub_email:
            if not email_msgs:
                st.caption("No external emails sent yet (all external emails halt until approved!).")
            for m in email_msgs[:12]:
                st.markdown(
                    f"""
                    <div class="email-card">
                        <div class="email-header">
                            <b>To:</b> {html.escape(m['recipient'])}<br>
                            <b>Subject:</b> {html.escape(m['subject'])}<br>
                            <span style="font-size:0.75rem;color:#64748b;">Sent {html.escape(m['timestamp'])} • mode: {html.escape(m['mode'])}</span>
                        </div>
                        <div class="email-body">{html.escape(m['body'])}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# =============================================================================
# TAB 4: INTERACTIVE POLICY MATRIX & LIVE YAML STUDIO
# =============================================================================
with tab_policy:
    st.subheader("⚙️ No-Code Governance Matrix & Threshold Controls")
    st.caption("Edit monetary limits, global guardrails, and per-action approval rules live — changes write straight to `config/agent_rules.yaml` with zero code changes or restarts.")

    rules_resp = api_get("/config/rules")
    prompts_resp = api_get("/config/prompts")
    parsed_rules = rules_resp["parsed"]
    thresholds = parsed_rules.get("thresholds", {})
    triggers = parsed_rules.get("global_approval_triggers", {})
    actions_cfg = parsed_rules.get("actions", {})

    with st.container(border=True):
        st.markdown("#### 🛡️ Global Guardrails & Thresholds")
        g1, g2, g3 = st.columns(3)
        t_email = g1.toggle("Gate ALL External Emails", value=bool(triggers.get("external_email", True)))
        t_money = g2.toggle("Gate ALL Outbound Money", value=bool(triggers.get("outbound_money", True)))
        t_contract = g3.toggle("Gate ALL Contracts & Offers", value=bool(triggers.get("contract_or_offer", True)))

        s1, s2 = st.columns(2)
        exp_limit = s1.slider(
            "Auto-Reconcile Expense Threshold (SGD)",
            min_value=0,
            max_value=1500,
            value=int(float(thresholds.get("expense_auto_reconcile_max", 250))),
            step=25,
            help="Expenses above this amount automatically pause for Finance Controller approval.",
        )
        disc_limit = s2.slider(
            "Max Auto-Approved Quote Discount (%)",
            min_value=0,
            max_value=30,
            value=int(float(thresholds.get("quote_max_auto_discount_pct", 10))),
            step=1,
            help="Quotes with discounts higher than this % pause for Sales Director approval.",
        )

    st.markdown("#### 📋 Per-Action Approval Policy Matrix")
    updated_actions = dict(actions_cfg)
    for dom in ["hr", "accounting", "sales"]:
        with st.expander(f"{'🧑‍💼 HR' if dom=='hr' else ('💰 Accounting' if dom=='accounting' else '📈 Sales')} Actions", expanded=True):
            for act_name, cfg in actions_cfg.items():
                if cfg.get("domain") != dom:
                    continue
                c_name, c_mode, c_role = st.columns([2.2, 1.3, 1.3])
                c_name.markdown(f"**`{act_name}`**  \n<span style='font-size:0.8rem;color:#64748b;'>{cfg.get('description', '')}</span>", unsafe_allow_html=True)

                cur_req = cfg.get("require_approval", False)
                mode_label = "Conditional" if cur_req == "conditional" else ("Require Approval" if cur_req is True else "Autonomous")
                options = ["Autonomous", "Conditional", "Require Approval"]
                new_mode = c_mode.selectbox(
                    "Policy",
                    options=options,
                    index=options.index(mode_label),
                    key=f"pol_{act_name}",
                    label_visibility="collapsed",
                )
                new_role = c_role.text_input(
                    "Approver",
                    value=str(cfg.get("approver_role", "Operations Manager")),
                    key=f"role_{act_name}",
                    label_visibility="collapsed",
                )
                act_copy = dict(cfg)
                act_copy["require_approval"] = (
                    "conditional" if new_mode == "Conditional" else (True if new_mode == "Require Approval" else False)
                )
                act_copy["approver_role"] = new_role
                updated_actions[act_name] = act_copy

    if st.button("💾 Save Policy Matrix to YAML", type="primary"):
        parsed_rules["global_approval_triggers"]["external_email"] = t_email
        parsed_rules["global_approval_triggers"]["outbound_money"] = t_money
        parsed_rules["global_approval_triggers"]["contract_or_offer"] = t_contract
        parsed_rules["thresholds"]["expense_auto_reconcile_max"] = float(exp_limit)
        parsed_rules["thresholds"]["quote_max_auto_discount_pct"] = float(disc_limit)
        parsed_rules["actions"] = updated_actions
        api_put("/config/rules", {"content": yaml.safe_dump(parsed_rules, sort_keys=False)})
        st.toast("Saved config/agent_rules.yaml — live immediately!", icon="💾")
        st.rerun()

    st.divider()
    with st.expander("📝 Advanced Live YAML Studio (`agent_rules.yaml` & `prompts.yaml`)"):
        y1, y2 = st.columns(2)
        with y1:
            raw_r = st.text_area("config/agent_rules.yaml", value=rules_resp["raw"], height=380, key="raw_rules")
            if st.button("Save Raw Rules YAML"):
                api_put("/config/rules", {"content": raw_r})
                st.success("Rules YAML validated and saved!")
                st.rerun()
        with y2:
            raw_p = st.text_area("config/prompts.yaml", value=prompts_resp["raw"], height=380, key="raw_prompts")
            if st.button("Save Raw Prompts YAML"):
                api_put("/config/prompts", {"content": raw_p})
                st.success("Prompts YAML validated and saved!")
                st.rerun()


# =============================================================================
# TAB 5: SEARCHABLE AUDIT TRAIL & CONNECTED STACK EXPLORER
# =============================================================================
with tab_audit:
    sub_audit, sub_hr, sub_acct, sub_crm = st.tabs(
        ["📜 Searchable Audit Trail", "🧑‍💼 HRIS Data", "💰 Accounting Ledger", "📈 Sales CRM"]
    )

    with sub_audit:
        fc1, fc2, fc3, fc4 = st.columns([2, 1, 1.2, 1])
        q = fc1.text_input("Full-text Search", placeholder="Search ID, email, candidate, invoice...")
        dom_f = fc2.selectbox("Domain", ["", "hr", "accounting", "sales"])
        evt_f = fc3.selectbox(
            "Event Type",
            ["", "autonomous_execution", "approval_requested", "approval_granted", "approval_rejected", "resumed_execution", "error"],
        )
        stat_f = fc4.selectbox("Status", ["", "completed", "pending", "approved", "rejected", "failed"])

        filtered_logs = api_get(
            "/audit",
            params={
                "query": q or None,
                "domain": dom_f or None,
                "event_type": evt_f or None,
                "status": stat_f or None,
                "limit": 250,
            },
        )["logs"]

        st.caption(f"Matched **{len(filtered_logs)}** audit trail records.")
        if filtered_logs:
            df_audit = pd.DataFrame(
                [
                    {
                        "ID": r["id"],
                        "Timestamp": r["timestamp"],
                        "Run": r["run_id"],
                        "Domain": r["domain"].upper(),
                        "Action": r["action_name"],
                        "Event": r["event_type"],
                        "Risk": r["risk_level"].upper(),
                        "Status": r["status"].upper(),
                        "Actor": r["actor"],
                        "Summary": r["summary"],
                    }
                    for r in filtered_logs
                ]
            )
            st.dataframe(df_audit, use_container_width=True, hide_index=True)

            dl_col, insp_col = st.columns([1, 2])
            dl_col.download_button(
                "⬇️ Export Audit CSV",
                data=df_audit.to_csv(index=False).encode("utf-8"),
                file_name="backoffice_audit_trail.csv",
                mime="text/csv",
                use_container_width=True,
            )
            selected_id = insp_col.selectbox(
                "Inspect Full Event Payload / Result",
                options=[r["id"] for r in filtered_logs],
                format_func=lambda eid: f"Event #{eid} — {next((x['action_name'] + ' (' + x['event_type'] + ')' for x in filtered_logs if x['id'] == eid), '')}",
            )
            chosen = next((x for x in filtered_logs if x["id"] == selected_id), None)
            if chosen:
                p1, p2 = st.columns(2)
                p1.json(chosen.get("payload", {}))
                p2.json(chosen.get("result", {}))
        else:
            st.info("No audit records match your filter.")

    with sub_hr:
        st.markdown("#### Employees Directory (HRIS)")
        st.dataframe(pd.DataFrame(overview["employees"]), use_container_width=True, hide_index=True)
        st.markdown("#### Incoming Candidates & Offer Pipeline")
        st.dataframe(pd.DataFrame(overview["candidates"]), use_container_width=True, hide_index=True)

    with sub_acct:
        st.markdown("#### Invoices (Accounts Receivable)")
        st.dataframe(pd.DataFrame(overview["invoices"]), use_container_width=True, hide_index=True)
        st.markdown("#### Employee Expense Claims")
        st.dataframe(pd.DataFrame(overview["expenses"]), use_container_width=True, hide_index=True)

    with sub_crm:
        st.markdown("#### Sales Leads (CRM)")
        st.dataframe(pd.DataFrame(overview["leads"]), use_container_width=True, hide_index=True)
        c_q, c_f = st.columns(2)
        with c_q:
            st.markdown("#### Commercial Quotes")
            if overview["quotes"]:
                st.dataframe(pd.DataFrame(overview["quotes"]).drop(columns=["quote_text"], errors="ignore"), use_container_width=True, hide_index=True)
            else:
                st.caption("No quotes prepared yet.")
        with c_f:
            st.markdown("#### Scheduled Follow-Ups")
            if overview["followups"]:
                st.dataframe(pd.DataFrame(overview["followups"]), use_container_width=True, hide_index=True)
            else:
                st.caption("No follow-ups scheduled yet.")
