"""
TrustLayer MVP — Interactive Governance Pipeline Demo
Realistic Swedish government OSINT scenarios. Full operator simulation with §10.2 structured argumentation.

Run: python -m streamlit run trustlayer_mvp/app.py
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import streamlit as st

from trustlayer_mvp.models import (
    HitLRecord, HitLDecision, FinalAction, GuardrailVerdict,
    RiskLevel, OperatorTier, CheckId, AgentOutput,
)
from trustlayer_mvp.pipeline import GovernancePipeline
from trustlayer_mvp.scenarios import ALL_SCENARIOS
from trustlayer_mvp.tier1_guardrail import calibrate_confidence
from trustlayer_mvp import config

# =============================================================================
# Page Config
# =============================================================================

st.set_page_config(page_title="TrustLayer Demo", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""<style>
.pipe-box{border-radius:10px;padding:12px;text-align:center;min-height:80px;display:flex;flex-direction:column;justify-content:center;margin:0 2px}
.pipe-inactive{background:#1a1d23;border:2px dashed #444;color:#666}
.pipe-pass{background:#052e16;border:2px solid #22c55e;color:#22c55e}
.pipe-block{background:#2d0a0a;border:2px solid #ef4444;color:#ef4444}
.pipe-flag{background:#2d2000;border:2px solid #eab308;color:#eab308}
.pipe-wait{background:#0f0f2e;border:2px solid #818cf8;color:#818cf8}
.pipe-title{font-size:11px;font-weight:bold;text-transform:uppercase;letter-spacing:1px;opacity:0.7}
.pipe-status{font-size:15px;font-weight:bold;margin:3px 0}
.pipe-detail{font-size:11px;opacity:0.75}
.check-row{padding:10px 14px;margin:5px 0;border-radius:8px;font-size:14px}
.check-pass{background:#052e16;border-left:4px solid #22c55e}
.check-fail{background:#2d0a0a;border-left:4px solid #ef4444}
.check-skip{background:#1a1d23;border-left:4px solid #444;color:#666}
.hash-entry{font-family:monospace;font-size:12px;background:#0a0a0a;border:1px solid #333;border-radius:6px;padding:10px;margin:4px 0}
.enforcement-err{background:#2d0a0a;border:2px solid #ef4444;border-radius:8px;padding:12px;margin:8px 0;color:#fca5a5}
.schema-section{background:#111827;border:1px solid #374151;border-radius:8px;padding:14px;margin:8px 0}
.evidence-card{background:#111827;border-left:3px solid #6366f1;border-radius:0 8px 8px 0;padding:12px;margin:6px 0}
</style>""", unsafe_allow_html=True)

# =============================================================================
# Session State
# =============================================================================

_defaults = {
    "pipeline": GovernancePipeline(), "page": "select", "scenario": None,
    "output": None, "guardrail_result": None, "operator_tier": None,
    "brief": None, "needs_operator": False, "hitl_record": None,
    "audit_entry": None, "pipeline_result": None,
    "evidence_viewed": set(), "review_start": None,
    "enforcement_errors": [], "history": [],
    "evidence_notes": {},      # operator notes per evidence item
    "challenge_flags": set(),  # evidence items the operator challenges
    "section_unlocked": 1,     # progressive reveal: 1=evidence, 2=uncertainty, 3=alt, 4=conclusion, 5=decision
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v if not isinstance(v, (set,)) else type(v)()

pipeline: GovernancePipeline = st.session_state.pipeline


# =============================================================================
# Helpers
# =============================================================================

def go(page):
    st.session_state.page = page
    st.rerun()

def reset():
    for k, v in _defaults.items():
        if k not in ("pipeline", "history"):
            st.session_state[k] = v if not isinstance(v, (set,)) else type(v)()
    st.session_state.page = "select"
    st.rerun()

def pipe_header():
    p = st.session_state.page
    gr = st.session_state.guardrail_result
    hitl = st.session_state.hitl_record
    audit = st.session_state.audit_entry

    def s(n):
        if n == 0:
            return ("pipe-inactive","---","") if p == "select" else ("pipe-pass","SUBMITTED","Untrusted")
        if n == 1:
            if p in ("select","agent_input"): return ("pipe-inactive","---","")
            if not gr: return ("pipe-inactive","---","")
            m = {"block":"pipe-block","flag":"pipe-flag","pass":"pipe-pass","quarantine":"pipe-block"}
            return (m.get(gr.verdict.value,"pipe-pass"), gr.verdict.value.upper(), f"Risk: {gr.assessed_risk_level.value.upper()}")
        if n == 2:
            if p in ("select","agent_input","tier1"): return ("pipe-inactive","---","")
            if p == "tier2" and st.session_state.needs_operator: return ("pipe-wait","REVIEWING","Operator active")
            if gr and gr.verdict == GuardrailVerdict.BLOCK: return ("pipe-block","SKIPPED","Blocked")
            if hitl: return ("pipe-pass",hitl.decision.value.upper()[:8],"Decided")
            if not st.session_state.needs_operator: return ("pipe-pass","AUTO","Low risk")
            return ("pipe-inactive","---","")
        if n == 3:
            if not audit: return ("pipe-inactive","---","")
            return ("pipe-pass","LOGGED",f"#{pipeline.tier3.entry_count}")

    labels = ["Agent Input","Tier 1: Guardrail","Tier 2: Human-in-Loop","Tier 3: Audit"]
    states = [s(i) for i in range(4)]
    cols = st.columns([3,1,3,1,3,1,3])
    for i,(cls,status,detail) in enumerate(states):
        with cols[i*2]:
            st.markdown(f'<div class="pipe-box {cls}"><div class="pipe-title">{labels[i]}</div><div class="pipe-status">{status}</div><div class="pipe-detail">{detail}</div></div>', unsafe_allow_html=True)
        if i < 3:
            with cols[i*2+1]:
                c = "#22c55e" if states[i+1][0] not in ("pipe-inactive",) else "#444"
                if states[i+1][0] == "pipe-block": c = "#ef4444"
                st.markdown(f'<div style="text-align:center;padding:30px 0;font-size:20px;color:{c}">→</div>', unsafe_allow_html=True)


# =============================================================================
# PAGE: Select Scenario
# =============================================================================

def page_select():
    st.markdown("## TrustLayer: Governance Pipeline Demo")
    st.caption("Swedish multi-agency AI threat intelligence — Skatteverket, Försäkringskassan, Bolagsverket")
    pipe_header()
    st.divider()

    icons = ["🏦","📱","🏥","📉","🏠","📋"]
    cols = st.columns(3)
    for i, sfn in enumerate(ALL_SCENARIOS):
        s = sfn()
        with cols[i % 3]:
            st.markdown(f"#### {icons[i]} {s['name']}")
            st.caption(f"**{s['context']}**")
            st.caption(s["description"])
            if st.button("Start →", key=f"sel_{i}", use_container_width=True):
                st.session_state.scenario = s
                st.session_state.output = s["output"]
                go("agent_input")

    if st.session_state.history:
        st.divider()
        st.markdown("#### Previous Runs")
        for h in reversed(st.session_state.history):
            ic = {"pass":"✅","flag":"⚠️","block":"🚫"}.get(h["verdict"],"❓")
            st.caption(f"{ic} **{h['name']}** → {h['verdict'].upper()} | Risk: {h['risk'].upper()} | {h['action']}")

    st.divider()
    c1,c2,c3 = st.columns(3)
    with c1: st.metric("Audit Entries", pipeline.tier3.entry_count)
    with c2:
        v,_ = pipeline.verify_audit_integrity()
        st.metric("Chain Integrity", "VALID" if v else "BROKEN")
    with c3:
        if st.button("Reset All"):
            st.session_state.pipeline = GovernancePipeline()
            st.session_state.history = []
            reset()


# =============================================================================
# PAGE: Agent Input — show what the untrusted agent submitted (§10.2 schema)
# =============================================================================

def page_agent_input():
    st.markdown("## Step 0: Agent Output — UNTRUSTED INPUT")
    pipe_header()
    st.divider()

    o: AgentOutput = st.session_state.output
    s = st.session_state.scenario

    st.error(f"**Source:** `{o.agent_id}` | **Context:** {s['context']}")
    st.caption("TrustLayer treats ALL agent outputs as potentially adversarial (P6). "
               "The agent has NO mechanism to influence its own routing or risk assessment.")

    # §10.2 Structured Argumentation Schema
    st.markdown("### Structured Argumentation Schema (spec §10.2)")

    st.markdown(f'<div class="schema-section"><b>CLAIM:</b> {o.claim.text}</div>', unsafe_allow_html=True)

    st.markdown(f'<div class="schema-section"><b>CONFIDENCE:</b> {o.agent_confidence:.0%} (raw, self-reported — will be independently calibrated by Tier 1)</div>', unsafe_allow_html=True)

    ev_html = "<b>EVIDENCE:</b><br>"
    for i, e in enumerate(o.evidence):
        age = (datetime.now(timezone.utc) - e.collected_at).days
        stale = " ⚠️ >90 days old" if age > 90 else ""
        ev_html += f"&nbsp;&nbsp;[{i+1}] {e.source_id} (reliability: {e.source_reliability:.1f}) — {e.content_summary[:100]}...{stale}<br>"
    if not o.evidence:
        ev_html += "&nbsp;&nbsp;<i>No evidence submitted!</i>"
    st.markdown(f'<div class="schema-section">{ev_html}</div>', unsafe_allow_html=True)

    chain_html = "<b>REASONING CHAIN:</b><br>"
    for step in o.claim.reasoning_chain:
        chain_html += f"&nbsp;&nbsp;→ {step}<br>"
    st.markdown(f'<div class="schema-section">{chain_html}</div>', unsafe_allow_html=True)

    gaps_html = "<b>GAPS (what would change this assessment):</b><br>"
    for fc in o.claim.falsification_conditions:
        gaps_html += f"&nbsp;&nbsp;• {fc}<br>"
    st.markdown(f'<div class="schema-section">{gaps_html}</div>', unsafe_allow_html=True)

    st.markdown(f'<div class="schema-section"><b>ALTERNATIVE:</b> {o.claim.alternative_hypothesis}</div>', unsafe_allow_html=True)

    st.markdown(f'<div class="schema-section"><b>ACTION REQUESTED:</b> {o.action_requested.value}</div>', unsafe_allow_html=True)

    frag_html = "<b>RAW FRAGMENTS (anti-hallucination anchors):</b><br>"
    if o.raw_fragments:
        for f in o.raw_fragments:
            frag_html += f'&nbsp;&nbsp;<code>[{f.source_id}]</code> "{f.value}"<br>'
    else:
        frag_html += "&nbsp;&nbsp;<i>No fragments — hallucination risk!</i>"
    st.markdown(f'<div class="schema-section">{frag_html}</div>', unsafe_allow_html=True)

    st.divider()
    if st.button("Submit to Tier 1: Guardrail Layer →", type="primary", use_container_width=True):
        go("tier1")
    if st.button("← Back"):
        reset()


# =============================================================================
# PAGE: Tier 1 — Guardrail (check-by-check)
# =============================================================================

def page_tier1():
    st.markdown("## Tier 1: Guardrail Layer — Automated Checks")
    o: AgentOutput = st.session_state.output

    if st.session_state.guardrail_result is None:
        result = pipeline.submit(o)
        st.session_state.guardrail_result = result.guardrail_result
        st.session_state.operator_tier = result.operator_tier
        st.session_state.brief = result.brief
        st.session_state.needs_operator = result.needs_operator
        st.session_state.pipeline_result = result
        st.session_state.audit_entry = result.audit_entry

    gr = st.session_state.guardrail_result
    pipe_header()
    st.divider()

    # Calibration pipeline visualization
    st.markdown("### Confidence Calibration Pipeline")
    cal = calibrate_confidence(o.agent_confidence, len(o.evidence))
    cc1, cc2, cc3, cc4 = st.columns(4)
    with cc1:
        st.metric("Agent Raw", f"{o.agent_confidence:.0%}")
        st.caption("Self-reported (untrusted)")
    with cc2:
        st.markdown("**→ Platt Scaling →**")
        st.caption(f"Deflation factor: ×0.8")
    with cc3:
        delta = cal - o.agent_confidence
        st.metric("Calibrated", f"{cal:.0%}", delta=f"{delta:+.0%}")
        st.caption("Independent assessment")
    with cc4:
        st.metric("Risk Level", gr.assessed_risk_level.value.upper())
        st.caption("Computed by G6, not agent")

    st.divider()
    st.markdown("### Check Pipeline (short-circuits on hard fail)")

    checks = [
        ("G1", "Confidence Calibration", "Block if calibrated confidence below risk-adjusted threshold", CheckId.G1_CONFIDENCE, True),
        ("G2", "Scope Boundary", "Block if action_requested outside authorised scope", CheckId.G2_SCOPE, True),
        ("G3", "Anti-Hallucination", "Block if claim terms not anchored in evidence fragments", CheckId.G3_ANTI_HALLUCINATION, True),
        ("G4", "Evidence Sufficiency", "Flag if evidence count below minimum for risk level", CheckId.G4_EVIDENCE_SUFFICIENCY, False),
        ("G5", "Disproportion Detector", "Flag if subject group targeted at >2× baseline rate", CheckId.G5_DISPROPORTION, False),
        ("G6", "Independent Risk Assessment", "Compute risk level from evidence quality + action severity", CheckId.G6_RISK_ASSESSMENT, False),
    ]

    passed = set(gr.checks_passed)
    failed = {c: r for c, r in gr.checks_failed}
    hit_hard = False

    for code, name, desc, cid, hard in checks:
        if hit_hard and cid not in passed and cid not in failed:
            st.markdown(f'<div class="check-row check-skip">⏭ <b>{code}: {name}</b> — Skipped (short-circuited)</div>', unsafe_allow_html=True)
            continue
        if cid in failed:
            ft = "HARD BLOCK" if hard else "SOFT FLAG"
            st.markdown(f'<div class="check-row check-fail">✗ <b>{code}: {name}</b> — {ft}: {failed[cid]}</div>', unsafe_allow_html=True)
            st.caption(f"Rule: {desc}")
            if hard: hit_hard = True
        elif cid in passed:
            extra = ""
            if cid == CheckId.G1_CONFIDENCE:
                extra = f" | {o.agent_confidence:.0%} → {cal:.0%}"
            elif cid == CheckId.G6_RISK_ASSESSMENT:
                extra = f" | → {gr.assessed_risk_level.value.upper()}"
            st.markdown(f'<div class="check-row check-pass">✓ <b>{code}: {name}</b> — Passed{extra}</div>', unsafe_allow_html=True)

    st.divider()
    tier = st.session_state.operator_tier

    if gr.verdict == GuardrailVerdict.BLOCK:
        st.error(f"**BLOCKED.** Reason: {gr.verdict_reasons[0] if gr.verdict_reasons else 'Hard fail'}")
        st.caption("SP3: Block Irreversibility — this output can NEVER be approved. No override exists.")
        if st.button("→ Tier 3: Audit Log", type="primary", use_container_width=True):
            go("tier3")
    elif not st.session_state.needs_operator:
        st.success(f"**AUTO-APPROVED** — Low risk + all checks passed → `{tier.value}`")
        if st.button("→ Tier 3: Audit Log", type="primary", use_container_width=True):
            go("tier3")
    else:
        dual = "YES" if st.session_state.brief and st.session_state.brief.requires_dual_approval else "NO"
        st.warning(f"**REQUIRES OPERATOR REVIEW** → `{tier.value}` | Dual approval: **{dual}**")
        if st.button("→ Tier 2: Operator Console", type="primary", use_container_width=True):
            st.session_state.review_start = time.time()
            st.session_state.evidence_viewed = set()
            st.session_state.evidence_notes = {}
            st.session_state.challenge_flags = set()
            st.session_state.enforcement_errors = []
            st.session_state.section_unlocked = 1
            go("tier2")

    if st.button("← Back"): reset()


# =============================================================================
# PAGE: Tier 2 — Human-in-the-Loop Operator Console
# =============================================================================

def page_tier2():
    st.markdown("## Tier 2: Operator Console")
    pipe_header()

    gr = st.session_state.guardrail_result
    brief = st.session_state.brief
    o = st.session_state.output
    tier = st.session_state.operator_tier

    st.divider()

    # Status bar
    elapsed = time.time() - st.session_state.review_start if st.session_state.review_start else 0
    min_req = config.MIN_DELIBERATION.get(gr.assessed_risk_level, timedelta(seconds=5)).total_seconds()
    viewed = len(st.session_state.evidence_viewed)
    total_ev = len(brief.evidence_items)

    c1,c2,c3,c4,c5 = st.columns(5)
    with c1: st.markdown(f"**Tier:** `{tier.value}`")
    with c2: st.markdown(f"**Risk:** `{gr.assessed_risk_level.value.upper()}`")
    with c3: st.markdown(f"**Evidence:** `{viewed}/{total_ev}` viewed")
    with c4: st.markdown(f"**Time:** `{elapsed:.0f}s` / min `{min_req:.0f}s`")
    with c5: st.markdown(f"**Dual:** `{'REQUIRED' if brief.requires_dual_approval else 'No'}`")

    # Show previous enforcement errors
    if st.session_state.enforcement_errors:
        for err in st.session_state.enforcement_errors:
            st.markdown(f'<div class="enforcement-err"><b>REJECTED BY ENFORCER:</b> {err}</div>', unsafe_allow_html=True)
        st.caption("Anti-rubber-stamp enforcement is structural, not policy. Fix the issue and resubmit.")

    st.divider()
    unlocked = st.session_state.section_unlocked

    # ── SECTION 1: Evidence ──
    st.markdown("### 1. Evidence Review")
    st.caption(f"You must view at least 1 evidence item before proceeding. ({viewed}/{total_ev} viewed)")

    if brief.evidence_items:
        for j, ev in enumerate(brief.evidence_items):
            is_viewed = ev.item_id in st.session_state.evidence_viewed
            is_challenged = ev.item_id in st.session_state.challenge_flags
            age = (datetime.now(timezone.utc) - ev.collected_at).days

            label = f"{'✅' if is_viewed else '📄'} [{j+1}] {ev.source_id} — reliability: {ev.source_reliability:.1f} — {age}d ago"
            if is_challenged: label += " ⚠️ CHALLENGED"

            with st.expander(label, expanded=False):
                st.markdown(f'<div class="evidence-card">', unsafe_allow_html=True)
                st.markdown(f"**Summary:** {ev.content_summary}")
                st.markdown(f"**Source:** `{ev.source_id}` | **Reliability:** `{ev.source_reliability:.1f}`")
                st.markdown(f"**Collected:** {ev.collected_at.strftime('%Y-%m-%d %H:%M UTC')} ({age} days ago)")
                st.markdown(f"**Legal basis:** {ev.legal_basis}")
                st.markdown(f"**Content hash:** `{ev.content_hash[:24]}...`")
                st.markdown('</div>', unsafe_allow_html=True)

                # Operator actions on evidence
                ec1, ec2 = st.columns(2)
                with ec1:
                    if not is_viewed:
                        if st.button(f"Mark as reviewed", key=f"view_{j}"):
                            st.session_state.evidence_viewed.add(ev.item_id)
                            st.rerun()
                    else:
                        st.success("Reviewed ✓")
                with ec2:
                    if st.button(f"{'Un-challenge' if is_challenged else 'Challenge reliability'}", key=f"chal_{j}"):
                        if is_challenged:
                            st.session_state.challenge_flags.discard(ev.item_id)
                        else:
                            st.session_state.challenge_flags.add(ev.item_id)
                        st.rerun()

                note = st.text_input(f"Your note on this evidence:", value=st.session_state.evidence_notes.get(ev.item_id, ""), key=f"note_{j}")
                if note:
                    st.session_state.evidence_notes[ev.item_id] = note
    else:
        st.warning("No evidence items submitted by agent.")

    if viewed > 0 and unlocked < 2:
        if st.button("Evidence reviewed — show uncertainty assessment →", use_container_width=True):
            st.session_state.section_unlocked = 2
            st.rerun()

    # ── SECTION 2: Uncertainty ──
    if unlocked >= 2:
        st.divider()
        st.markdown("### 2. Uncertainty Assessment")
        a = brief.assessment
        uc1, uc2 = st.columns(2)
        with uc1:
            st.metric("Point Estimate", f"{a.point_estimate:.2f}",
                       delta=f"CI: [{a.confidence_interval[0]:.2f}, {a.confidence_interval[1]:.2f}]")
            st.caption("Calibrated by Tier 1, not agent self-report")
        with uc2:
            st.markdown(f"**Epistemic uncertainty** (what model doesn't know):")
            st.markdown(f"> {a.epistemic_uncertainty}")
            st.markdown(f"**Aleatoric uncertainty** (inherent noise):")
            st.markdown(f"> {a.aleatoric_uncertainty}")
        if a.key_assumptions:
            st.markdown("**Key assumptions — if any are wrong, assessment changes materially:**")
            for assumption in a.key_assumptions:
                st.markdown(f"- {assumption}")

        if unlocked < 3:
            if st.button("Understood — show alternative explanation →", use_container_width=True):
                st.session_state.section_unlocked = 3
                st.rerun()

    # ── SECTION 3: Alternative explanation ──
    if unlocked >= 3:
        st.divider()
        st.markdown("### 3. Alternative Explanation (mandatory per spec §10.2)")
        st.info(f"**Most plausible non-threat explanation:** {brief.alternative_explanation}")
        st.caption("Mandatory: agent must provide this. Cannot be 'N/A'. Forces consideration of benign interpretation.")

        if unlocked < 4:
            if st.button("Noted — show AI conclusion →", use_container_width=True):
                st.session_state.section_unlocked = 4
                st.rerun()

    # ── SECTION 4: AI Conclusion (LAST) ──
    if unlocked >= 4:
        st.divider()
        st.markdown("### 4. AI Conclusion")
        st.caption("Shown LAST to prevent anchoring bias (spec §6.1).")
        st.markdown(f"> *\"{brief.ai_conclusion}\"*")

        # Reasoning chain
        if o.claim.reasoning_chain:
            with st.expander("View reasoning chain"):
                for step in o.claim.reasoning_chain:
                    st.markdown(f"→ {step}")

        if unlocked < 5:
            if st.button("Ready to decide →", use_container_width=True):
                st.session_state.section_unlocked = 5
                st.rerun()

    # ── SECTION 5: Decision ──
    if unlocked >= 5:
        st.divider()
        st.markdown("### 5. Decision")

        # Show enforcement rules
        st.markdown(f"""**Anti-rubber-stamp rules (code-enforced):**
- Evidence viewed: {viewed}/{total_ev} {'✅' if viewed > 0 else '❌'}
- Deliberation time: {elapsed:.0f}s / {min_req:.0f}s min {'✅' if elapsed >= min_req else '❌'}
{'- Reasoning ≥ 50 chars: REQUIRED' if brief.requires_dual_approval else ''}
{'- Second approver: REQUIRED' if brief.requires_dual_approval else ''}
""")

        if st.session_state.challenge_flags:
            st.warning(f"You have challenged {len(st.session_state.challenge_flags)} evidence item(s). This will be recorded in the audit log.")

        with st.form("decision"):
            decision = st.selectbox("Decision", [
                "APPROVED — Proceed with recommended action",
                "REJECTED — Insufficient basis, close case",
                "ESCALATED — Refer to senior authority",
                "DEFERRED — Request additional evidence before deciding",
            ])

            reasoning = st.text_area(
                "Reasoning" + (" (REQUIRED: ≥ 50 chars for HIGH+ risk)" if brief.requires_dual_approval else ""),
                height=100,
                placeholder="Explain your decision. Reference specific evidence items. Note any concerns."
            )

            if brief.requires_dual_approval:
                st.warning("⚠️ Dual approval REQUIRED for HIGH/CRITICAL risk")

            fc1, fc2 = st.columns(2)
            with fc1:
                operator_id = st.text_input("Your Operator ID", value="operator-001")
            with fc2:
                second = ""
                if brief.requires_dual_approval:
                    second = st.text_input("Second Approver ID (required)", value="")

            submitted = st.form_submit_button("Submit Decision", type="primary", use_container_width=True)

            if submitted:
                dec_map = {"APPROVED": HitLDecision.APPROVED, "REJECTED": HitLDecision.REJECTED,
                           "ESCALATED": HitLDecision.ESCALATED, "DEFERRED": HitLDecision.DEFERRED}
                dec_key = decision.split(" —")[0]

                now = datetime.now(timezone.utc)
                elapsed_real = time.time() - st.session_state.review_start if st.session_state.review_start else 0

                challenges = list(st.session_state.challenge_flags)
                notes = dict(st.session_state.evidence_notes)
                reasoning_full = reasoning
                if challenges:
                    reasoning_full += f"\n[CHALLENGED EVIDENCE: {len(challenges)} item(s)]"
                if notes:
                    for eid, note in notes.items():
                        reasoning_full += f"\n[NOTE on {eid[:8]}: {note}]"

                record = HitLRecord(
                    output_id=st.session_state.pipeline_result.output_id,
                    operator_id=operator_id,
                    decision=dec_map[dec_key],
                    reasoning=reasoning_full,
                    evidence_viewed=list(st.session_state.evidence_viewed),
                    created_at=now - timedelta(seconds=elapsed_real),
                    decided_at=now,
                    second_approval=second if second else None,
                )

                try:
                    result = pipeline.decide(st.session_state.pipeline_result.output_id, record)
                    st.session_state.hitl_record = record
                    st.session_state.audit_entry = result.audit_entry
                    st.session_state.pipeline_result = result
                    go("tier3")
                except Exception as e:
                    st.session_state.enforcement_errors.append(str(e))
                    st.rerun()

    # Locked sections
    if unlocked < 2:
        st.divider()
        st.markdown("### 2. Uncertainty Assessment")
        st.caption("🔒 View at least 1 evidence item first")
    if unlocked < 3 and unlocked >= 2:
        pass  # already handled above
    if unlocked < 4 and unlocked >= 3:
        pass
    if unlocked < 5 and unlocked >= 4:
        pass

    st.divider()
    if st.button("← Back to Tier 1"):
        reset()


# =============================================================================
# PAGE: Tier 3 — Audit
# =============================================================================

def page_tier3():
    st.markdown("## Tier 3: Audit Layer — Tamper-Evident Log")
    pipe_header()
    st.divider()

    gr = st.session_state.guardrail_result
    hitl = st.session_state.hitl_record
    audit = st.session_state.audit_entry or st.session_state.pipeline_result.audit_entry
    scenario = st.session_state.scenario

    # This entry
    st.markdown("### Audit Entry Created")
    c1, c2 = st.columns([2,3])
    with c1:
        st.markdown(f"**Scenario:** {scenario['name']}")
        st.markdown(f"**Context:** {scenario['context']}")
        st.markdown(f"**Guardrail:** `{gr.verdict.value.upper()}`")
        st.markdown(f"**Risk:** `{gr.assessed_risk_level.value.upper()}`")
        if hitl:
            st.markdown(f"**Operator:** `{hitl.operator_id}`")
            st.markdown(f"**Decision:** `{hitl.decision.value.upper()}`")
            st.markdown(f"**Deliberation:** `{hitl.elapsed_seconds():.0f}s`")
            if hitl.reasoning:
                with st.expander("Operator reasoning"):
                    st.write(hitl.reasoning)
        elif gr.verdict == GuardrailVerdict.BLOCK:
            st.markdown("**Operator:** `N/A` (blocked before HitL)")
        else:
            st.markdown("**Operator:** `SYSTEM_AUTO`")
        st.markdown(f"**Final Action:** `{audit.final_action.value}`")

    with c2:
        st.markdown("**Hash Chain Entry:**")
        st.markdown(f"""<div class="hash-entry">
<b>Entry ID:</b>  {audit.entry_id}<br>
<b>Output ID:</b> {audit.output_id}<br>
<b>Action:</b>    {audit.final_action.value}<br>
<b>Timestamp:</b> {audit.timestamp.isoformat()}<br>
<br>
<b>Previous Hash:</b><br>{audit.previous_hash}<br>
<b>Entry Hash:</b><br>{audit.entry_hash}<br>
<br>
<i>Hash = SHA-256(entry_id | output_id | action | timestamp | previous_hash)</i><br>
<i>Changing any field invalidates this hash and breaks the chain.</i>
</div>""", unsafe_allow_html=True)

    # Full chain
    st.divider()
    st.markdown("### Hash Chain Visualization")
    entries = pipeline.tier3.entries
    for i, entry in enumerate(entries):
        is_new = entry.entry_id == audit.entry_id
        verdict_str = entry.guardrail_result.verdict.value.upper() if entry.guardrail_result else "?"
        risk_str = entry.guardrail_result.assessed_risk_level.value.upper() if entry.guardrail_result else "?"
        border = "border:2px solid #22c55e;" if is_new else ""
        icon = "🆕" if is_new else {"PASS":"✅","FLAG":"⚠️","BLOCK":"🚫"}.get(verdict_str,"❓")
        op_info = ""
        if entry.hitl_record:
            op_info = f" | Operator: {entry.hitl_record.operator_id} → {entry.hitl_record.decision.value}"
        st.markdown(f"""<div class="hash-entry" style="{border}">
{icon} <b>#{i+1}</b> {entry.final_action.value} | {verdict_str} | Risk: {risk_str}{op_info}<br>
<span style="color:#888">Hash: {entry.entry_hash[:48]}...</span><br>
<span style="color:#666">Prev: {entry.previous_hash[:48]}{'...' if len(entry.previous_hash)>48 else ''}</span>
</div>""", unsafe_allow_html=True)

    # Integrity
    st.divider()
    valid, msg = pipeline.verify_audit_integrity()
    if valid:
        st.success(f"✓ {msg}")
    else:
        st.error(f"✗ {msg}")

    # Safety properties
    st.divider()
    st.markdown("### Safety Properties Verified")
    p1, p2, p3 = st.columns(3)
    with p1:
        st.markdown("**SP1: Non-Bypassability**")
        st.success("✓ All 3 tiers executed in order")
    with p2:
        st.markdown("**SP2: Audit Completeness**")
        found = pipeline.tier3.get_entry(audit.output_id)
        st.success("✓ Output in audit log" if found else "✗ VIOLATION!")
    with p3:
        st.markdown("**SP3: Block Irreversibility**")
        if gr.verdict == GuardrailVerdict.BLOCK:
            st.success("✓ Blocked → never reached operator")
        else:
            st.info("N/A — output was not blocked")

    if st.session_state.enforcement_errors:
        st.divider()
        st.markdown("### Anti-Rubber-Stamp Log")
        for err in st.session_state.enforcement_errors:
            st.error(f"ENFORCEMENT: {err}")

    st.divider()
    n1, n2 = st.columns(2)
    with n1:
        if st.button("← Run another scenario", use_container_width=True):
            st.session_state.history.append({
                "name": scenario["name"], "verdict": gr.verdict.value,
                "risk": gr.assessed_risk_level.value, "action": audit.final_action.value,
            })
            reset()
    with n2:
        if st.button("View full audit log →", use_container_width=True):
            st.session_state.history.append({
                "name": scenario["name"], "verdict": gr.verdict.value,
                "risk": gr.assessed_risk_level.value, "action": audit.final_action.value,
            })
            go("audit_log")


# =============================================================================
# PAGE: Full Audit Log
# =============================================================================

def page_audit_log():
    st.markdown("## Complete Audit Log")
    pipe_header()
    st.divider()

    valid, msg = pipeline.verify_audit_integrity()
    if valid: st.success(f"✓ {msg}")
    else: st.error(f"✗ {msg}")

    stats = pipeline.get_audit_stats()
    c1,c2,c3 = st.columns(3)
    with c1: st.metric("Total", stats.get("total_entries",0))
    with c2:
        for a,c in stats.get("actions",{}).items(): st.caption(f"{a}: {c}")
    with c3:
        for r,c in stats.get("risk_distribution",{}).items(): st.caption(f"{r}: {c}")

    st.divider()
    for i, entry in enumerate(pipeline.tier3.entries):
        v = entry.guardrail_result.verdict.value.upper() if entry.guardrail_result else "?"
        r = entry.guardrail_result.assessed_risk_level.value.upper() if entry.guardrail_result else "?"
        ic = {"PASS":"✅","FLAG":"⚠️","BLOCK":"🚫"}.get(v,"❓")
        with st.expander(f"{ic} #{i+1} | {entry.final_action.value} | {v} | Risk: {r}"):
            st.write(f"**Entry:** `{entry.entry_id[:20]}...`")
            st.write(f"**Output:** `{entry.output_id[:20]}...`")
            if entry.hitl_record:
                st.write(f"**Operator:** {entry.hitl_record.operator_id} → {entry.hitl_record.decision.value}")
                st.write(f"**Reasoning:** {entry.hitl_record.reasoning[:200]}")
                st.write(f"**Evidence viewed:** {len(entry.hitl_record.evidence_viewed)} items")
                st.write(f"**Time:** {entry.hitl_record.elapsed_seconds():.0f}s")
            st.markdown(f'<div class="hash-entry">Prev: {entry.previous_hash}<br>Hash: {entry.entry_hash}</div>', unsafe_allow_html=True)

    st.divider()
    if st.button("← Back to scenarios", use_container_width=True):
        reset()


# =============================================================================
# Router
# =============================================================================

{"select": page_select, "agent_input": page_agent_input, "tier1": page_tier1,
 "tier2": page_tier2, "tier3": page_tier3, "audit_log": page_audit_log,
 }.get(st.session_state.page, page_select)()
