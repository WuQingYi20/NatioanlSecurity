"""
Tier 1 — Guardrail Layer (spec §5)
Automated checks on AgentOutput. Produces GuardrailResult with independently-assessed RiskLevel.
The agent is treated as UNTRUSTED — risk level is never self-reported.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .models import (
    AgentOutput, GuardrailResult, GuardrailVerdict, RiskLevel,
    CheckId, CheckResult, ActionType,
)
from . import config


class GuardrailCheck(ABC):
    """Base class for guardrail checks (spec §5.4 GuardrailCheck trait)."""

    @abstractmethod
    def check_id(self) -> CheckId: ...

    @abstractmethod
    def check(self, output: AgentOutput) -> CheckResult: ...

    @abstractmethod
    def is_hard_fail(self) -> bool: ...


class G1ConfidenceCalibration(GuardrailCheck):
    """Re-calibrate agent's self-reported confidence using simplified Platt scaling."""

    def check_id(self) -> CheckId:
        return CheckId.G1_CONFIDENCE

    def is_hard_fail(self) -> bool:
        return True

    def check(self, output: AgentOutput) -> CheckResult:
        # Simplified calibration: apply a deflation factor
        # In production: Platt scaling trained on historical ground truth
        calibrated = output.agent_confidence * 0.8

        # For MVP, use a global threshold; production would use risk-adaptive thresholds
        threshold = 0.2
        if calibrated < threshold:
            return CheckResult(
                check_id=self.check_id(),
                passed=False,
                reason=f"Calibrated confidence {calibrated:.2f} below threshold {threshold}",
                is_hard_fail=True,
            )
        return CheckResult(check_id=self.check_id(), passed=True)


class G2ScopeBoundaryCheck(GuardrailCheck):
    """Verify action_requested is within authorised scope."""

    def check_id(self) -> CheckId:
        return CheckId.G2_SCOPE

    def is_hard_fail(self) -> bool:
        return True

    def check(self, output: AgentOutput) -> CheckResult:
        if output.action_requested not in config.ALLOWED_ACTIONS:
            return CheckResult(
                check_id=self.check_id(),
                passed=False,
                reason=f"Action {output.action_requested.value} is out of scope",
                is_hard_fail=True,
            )
        return CheckResult(check_id=self.check_id(), passed=True)


class G3AntiHallucinationCheck(GuardrailCheck):
    """Every factual claim must be anchored in raw_fragments."""

    def check_id(self) -> CheckId:
        return CheckId.G3_ANTI_HALLUCINATION

    def is_hard_fail(self) -> bool:
        return True

    def check(self, output: AgentOutput) -> CheckResult:
        if not output.claim.text:
            return CheckResult(
                check_id=self.check_id(), passed=False,
                reason="Empty claim text", is_hard_fail=True,
            )

        # Simplified: check that key terms in the claim appear in fragments
        claim_words = set(output.claim.text.lower().split())
        # Remove common stop words for a fairer check
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on",
                      "at", "to", "for", "of", "and", "or", "that", "this", "with",
                      "has", "have", "been", "be", "not", "no", "but", "from", "by"}
        claim_words -= stop_words

        if not claim_words:
            return CheckResult(check_id=self.check_id(), passed=True)

        fragment_words = set()
        for frag in output.raw_fragments:
            fragment_words.update(frag.value.lower().split())

        if not fragment_words:
            return CheckResult(
                check_id=self.check_id(), passed=False,
                reason="No fragments provided to anchor claims", is_hard_fail=True,
            )

        unanchored = claim_words - fragment_words
        ratio = len(unanchored) / len(claim_words) if claim_words else 0

        if ratio > config.MAX_UNANCHORED_RATIO:
            return CheckResult(
                check_id=self.check_id(), passed=False,
                reason=f"Hallucination risk: {ratio:.0%} of claim terms unanchored in fragments",
                is_hard_fail=True,
            )
        return CheckResult(check_id=self.check_id(), passed=True)


class G4EvidenceSufficiencyCheck(GuardrailCheck):
    """Minimum evidence items required. Flag (not Block) on borderline."""

    def check_id(self) -> CheckId:
        return CheckId.G4_EVIDENCE_SUFFICIENCY

    def is_hard_fail(self) -> bool:
        return False  # Soft fail — flags, doesn't block

    def check(self, output: AgentOutput) -> CheckResult:
        count = len(output.evidence)
        # Use LOW threshold for initial check; risk assessment (G6) will re-evaluate
        min_required = config.MIN_EVIDENCE_COUNT[RiskLevel.LOW]
        if count < min_required:
            return CheckResult(
                check_id=self.check_id(), passed=False,
                reason=f"Only {count} evidence items; minimum {min_required} required",
                is_hard_fail=False,
            )
        return CheckResult(check_id=self.check_id(), passed=True)


class G5DisproportionDetector(GuardrailCheck):
    """Statistical check for disproportionate targeting. Simplified for MVP."""

    def check_id(self) -> CheckId:
        return CheckId.G5_DISPROPORTION

    def is_hard_fail(self) -> bool:
        return False  # Flag for moderate; block only at extreme levels

    def check(self, output: AgentOutput) -> CheckResult:
        # MVP: always passes. Production would check against 90-day baseline.
        return CheckResult(check_id=self.check_id(), passed=True)


class G6IndependentRiskAssessment(GuardrailCheck):
    """Compute risk level independently from evidence quality and action severity."""

    def check_id(self) -> CheckId:
        return CheckId.G6_RISK_ASSESSMENT

    def is_hard_fail(self) -> bool:
        return False

    def check(self, output: AgentOutput) -> CheckResult:
        # Always passes — risk assessment is computed, not pass/fail
        return CheckResult(check_id=self.check_id(), passed=True)


def assess_risk_independently(output: AgentOutput, calibrated_confidence: float) -> RiskLevel:
    """Compute risk level from evidence and action severity. Agent has NO influence."""
    score = 0

    # Factor 1: Action severity
    severity_scores = {
        ActionType.FLAG_FOR_REVIEW: 1,
        ActionType.ALERT_OPERATOR: 2,
        ActionType.ESCALATE_TO_SENIOR: 3,
        ActionType.ESCALATE_TO_LEGAL: 4,
        ActionType.REFER_TO_INVESTIGATOR: 4,
    }
    score += severity_scores.get(output.action_requested, 2)

    # Factor 2: Evidence count (more evidence = higher complexity = higher risk)
    if len(output.evidence) >= 5:
        score += 2
    elif len(output.evidence) >= 3:
        score += 1

    # Factor 3: Low calibrated confidence on severe action = higher risk
    if calibrated_confidence < 0.5 and score >= 3:
        score += 2

    # Map to risk level
    if score <= 2:
        return RiskLevel.LOW
    elif score <= 4:
        return RiskLevel.MEDIUM
    elif score <= 6:
        return RiskLevel.HIGH
    else:
        return RiskLevel.CRITICAL


def calibrate_confidence(agent_confidence: float, evidence_count: int) -> float:
    """Simplified Platt scaling. Production: trained on historical ground truth."""
    # Deflate overconfident agents; boost if lots of evidence
    calibrated = agent_confidence * 0.8
    if evidence_count >= 3:
        calibrated = min(1.0, calibrated + 0.05)
    return round(calibrated, 4)


class GuardrailLayer:
    """Tier 1 pipeline — runs all 6 checks, produces GuardrailResult."""

    def __init__(self):
        self.checks: list[GuardrailCheck] = [
            G1ConfidenceCalibration(),
            G2ScopeBoundaryCheck(),
            G3AntiHallucinationCheck(),
            G4EvidenceSufficiencyCheck(),
            G5DisproportionDetector(),
            G6IndependentRiskAssessment(),
        ]

    def evaluate(self, output: AgentOutput) -> GuardrailResult:
        """Evaluate AgentOutput through all guardrail checks.
        Consumes the output (marks it) — enforces single-consumption.
        Fail-closed: any exception is treated as Block (spec §3.1 P3).
        """
        output.mark_consumed()

        passed_checks: list[CheckId] = []
        failed_checks: list[tuple[CheckId, str]] = []
        hard_blocked: str | None = None

        for check in self.checks:
            try:
                result = check.check(output)
            except Exception as e:
                # Fail-closed: panics/exceptions treated as Block
                result = CheckResult(
                    check_id=check.check_id(),
                    passed=False,
                    reason=f"Check raised exception (fail-closed): {e}",
                    is_hard_fail=True,
                )

            if result.passed:
                passed_checks.append(result.check_id)
            else:
                failed_checks.append((result.check_id, result.reason))
                if result.is_hard_fail and hard_blocked is None:
                    hard_blocked = result.reason
                    break  # Short-circuit on hard fail

        # Determine verdict
        if hard_blocked:
            verdict = GuardrailVerdict.BLOCK
            reasons = [hard_blocked]
        elif failed_checks:
            verdict = GuardrailVerdict.FLAG
            reasons = [r for _, r in failed_checks]
        else:
            verdict = GuardrailVerdict.PASS
            reasons = []

        # Compute calibrated confidence and independent risk
        calibrated = calibrate_confidence(output.agent_confidence, len(output.evidence))
        assessed_risk = assess_risk_independently(output, calibrated)

        return GuardrailResult(
            output_id=output.output_id,
            verdict=verdict,
            verdict_reasons=reasons,
            assessed_risk_level=assessed_risk,
            confidence_calibrated=calibrated,
            checks_passed=passed_checks,
            checks_failed=failed_checks,
        )
