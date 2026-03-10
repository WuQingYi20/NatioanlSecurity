"""
Tier 2 — Human-in-the-Loop Layer (spec §6)
Routing, brief construction, and anti-rubber-stamp enforcement.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    AgentOutput, GuardrailResult, GuardrailVerdict, RiskLevel,
    VerdictClass, OperatorTier, OperatorBrief, UncertaintyBundle,
    HitLRecord, HitLDecision, FinalAction, AgentOutputDigest,
)
from . import config


# =============================================================================
# § ROUTING (spec §6.2)
# =============================================================================

class HitLRouter:
    """Routes outputs to the appropriate operator tier based on risk and verdict."""

    def route(self, result: GuardrailResult) -> OperatorTier:
        verdict_class = self._classify_verdict(result.verdict)
        key = (result.assessed_risk_level, verdict_class)
        # Fail-safe: unknown combinations escalate to SeniorOperator
        return config.ROUTING_TABLE.get(key, OperatorTier.SENIOR_OPERATOR)

    def _classify_verdict(self, verdict: GuardrailVerdict) -> VerdictClass:
        if verdict == GuardrailVerdict.PASS:
            return VerdictClass.PASS
        elif verdict == GuardrailVerdict.FLAG:
            return VerdictClass.FLAGGED
        else:  # BLOCK or QUARANTINE
            return VerdictClass.BLOCKED


# =============================================================================
# § BRIEF CONSTRUCTION (spec §6.3)
# =============================================================================

class BriefBuilder:
    """Constructs the OperatorBrief with evidence-first presentation order."""

    def build(
        self,
        output: AgentOutput,
        guardrail_result: GuardrailResult,
        operator_tier: OperatorTier,
    ) -> OperatorBrief:
        risk = guardrail_result.assessed_risk_level
        requires_dual = risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)

        assessment = UncertaintyBundle(
            point_estimate=guardrail_result.confidence_calibrated,
            confidence_interval=(
                max(0, guardrail_result.confidence_calibrated - 0.15),
                min(1, guardrail_result.confidence_calibrated + 0.15),
            ),
            epistemic_uncertainty="Model may not generalise to novel threat patterns",
            aleatoric_uncertainty="OSINT sources have inherent noise and bias",
            key_assumptions=output.claim.falsification_conditions or ["No assumptions stated"],
            critical_evidence_items=[e.item_id for e in output.evidence[:3]],
        )

        return OperatorBrief(
            output_id=output.output_id,
            subject_pseudonym=output.subject_ref or "REDACTED",
            evidence_items=output.evidence,
            assessment=assessment,
            alternative_explanation=output.claim.alternative_hypothesis or "No alternative provided by agent",
            ai_conclusion=output.claim.text,
            available_actions=config.get_action_options(risk),
            legal_basis=output.evidence[0].legal_basis if output.evidence else "Not specified",
            requires_dual_approval=requires_dual,
            assessed_risk_level=risk,
            operator_tier=operator_tier,
        )


# =============================================================================
# § ANTI-RUBBER-STAMP ENFORCEMENT (spec §6.4)
# =============================================================================

class EnforcementError(Exception):
    pass


class NoEvidenceOpenedError(EnforcementError):
    pass


class DecisionTooFastError(EnforcementError):
    def __init__(self, elapsed: float, required: float):
        self.elapsed = elapsed
        self.required = required
        super().__init__(
            f"Decision too fast: {elapsed:.1f}s elapsed, {required:.1f}s required"
        )


class InsufficientReasoningError(EnforcementError):
    pass


class DualApprovalRequiredError(EnforcementError):
    pass


class HitLEnforcer:
    """Validates that operator decisions meet engagement requirements.
    Defeats automation bias through structural enforcement, not policy.
    """

    def validate(self, record: HitLRecord, brief: OperatorBrief) -> None:
        """Raises EnforcementError if any rule is violated."""
        # Rule 1: At least one evidence item must have been viewed
        if not record.evidence_viewed:
            raise NoEvidenceOpenedError(
                "Operator must view at least one evidence item before deciding"
            )

        # Rule 2: Minimum deliberation time
        min_time = config.MIN_DELIBERATION.get(
            brief.assessed_risk_level
        )
        if min_time and record.elapsed_seconds() < min_time.total_seconds():
            raise DecisionTooFastError(
                elapsed=record.elapsed_seconds(),
                required=min_time.total_seconds(),
            )

        # Rule 3: High-stakes decisions require written reasoning
        if brief.requires_dual_approval and len(record.reasoning) < config.MIN_REASONING_LENGTH:
            raise InsufficientReasoningError(
                f"Reasoning must be at least {config.MIN_REASONING_LENGTH} chars for high-risk decisions"
            )

        # Rule 4: Dual approval for High+ risk
        if brief.requires_dual_approval and not record.has_second_approval():
            raise DualApprovalRequiredError(
                "Dual approval required for High/Critical risk decisions"
            )


# =============================================================================
# § HITL LAYER
# =============================================================================

class HitLLayer:
    """Orchestrates the Human-in-the-Loop review process."""

    def __init__(self):
        self.router = HitLRouter()
        self.brief_builder = BriefBuilder()
        self.enforcer = HitLEnforcer()

    def prepare_review(
        self, output: AgentOutput, guardrail_result: GuardrailResult
    ) -> tuple[OperatorBrief, OperatorTier]:
        """Route and build brief for operator review."""
        tier = self.router.route(guardrail_result)
        brief = self.brief_builder.build(output, guardrail_result, tier)
        return brief, tier

    def validate_decision(self, record: HitLRecord, brief: OperatorBrief) -> None:
        """Validate that the operator's decision meets requirements.
        Raises EnforcementError on violation.
        """
        self.enforcer.validate(record, brief)

    def is_auto_log(self, tier: OperatorTier) -> bool:
        """Returns True if this output can be auto-logged without operator review."""
        return tier == OperatorTier.AUTO_LOG

    def is_audit_only(self, tier: OperatorTier) -> bool:
        """Returns True if this is a blocked output (audit only, no operator action)."""
        return tier in (OperatorTier.AUDIT_ONLY, OperatorTier.AUDIT_WITH_ESCALATION)
