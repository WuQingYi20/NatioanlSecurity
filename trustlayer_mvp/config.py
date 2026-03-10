"""
Guardrail configuration — thresholds, routing tables, enforcement parameters.
In production, this would be validated by Z3 before deployment (spec §5.5).
"""
from datetime import timedelta

from .models import (
    RiskLevel, VerdictClass, OperatorTier, ActionType, ActionOption, FinalAction,
)


# Confidence thresholds per risk level (monotonically increasing — Z3 would verify)
CONFIDENCE_THRESHOLDS = {
    RiskLevel.LOW: 0.3,
    RiskLevel.MEDIUM: 0.5,
    RiskLevel.HIGH: 0.7,
    RiskLevel.CRITICAL: 0.85,
}

# Minimum evidence items per risk level
MIN_EVIDENCE_COUNT = {
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 5,
}

# Anti-hallucination: max ratio of unanchored claim terms
MAX_UNANCHORED_RATIO = 0.3

# Allowed action types (scope check G2)
ALLOWED_ACTIONS = {
    ActionType.FLAG_FOR_REVIEW,
    ActionType.ALERT_OPERATOR,
    ActionType.ESCALATE_TO_SENIOR,
    ActionType.ESCALATE_TO_LEGAL,
    ActionType.REFER_TO_INVESTIGATOR,
}

# Routing table: (RiskLevel, VerdictClass) -> OperatorTier
# Spec §6.2 — fail-safe: unknown combinations escalate to SeniorOperator
ROUTING_TABLE: dict[tuple[RiskLevel, VerdictClass], OperatorTier] = {
    # Low risk
    (RiskLevel.LOW, VerdictClass.PASS): OperatorTier.AUTO_LOG,
    (RiskLevel.LOW, VerdictClass.FLAGGED): OperatorTier.TIER1_OPERATOR,
    (RiskLevel.LOW, VerdictClass.BLOCKED): OperatorTier.AUDIT_ONLY,
    # Medium risk
    (RiskLevel.MEDIUM, VerdictClass.PASS): OperatorTier.TIER1_OPERATOR,
    (RiskLevel.MEDIUM, VerdictClass.FLAGGED): OperatorTier.TIER2_OPERATOR,
    (RiskLevel.MEDIUM, VerdictClass.BLOCKED): OperatorTier.AUDIT_ONLY,
    # High risk
    (RiskLevel.HIGH, VerdictClass.PASS): OperatorTier.TIER2_OPERATOR,
    (RiskLevel.HIGH, VerdictClass.FLAGGED): OperatorTier.SENIOR_OPERATOR,
    (RiskLevel.HIGH, VerdictClass.BLOCKED): OperatorTier.AUDIT_WITH_ESCALATION,
    # Critical risk
    (RiskLevel.CRITICAL, VerdictClass.PASS): OperatorTier.SENIOR_OPERATOR,
    (RiskLevel.CRITICAL, VerdictClass.FLAGGED): OperatorTier.OVERSIGHT_BODY,
    (RiskLevel.CRITICAL, VerdictClass.BLOCKED): OperatorTier.AUDIT_WITH_ESCALATION,
}

# Minimum deliberation time per risk level (anti-rubber-stamp)
MIN_DELIBERATION = {
    RiskLevel.LOW: timedelta(seconds=5),
    RiskLevel.MEDIUM: timedelta(seconds=15),
    RiskLevel.HIGH: timedelta(seconds=30),
    RiskLevel.CRITICAL: timedelta(seconds=60),
}

# Minimum reasoning length for high-stakes decisions
MIN_REASONING_LENGTH = 50

# Standard action options presented to operators
def get_action_options(risk_level: RiskLevel) -> list[ActionOption]:
    options = [
        ActionOption(
            action=FinalAction.ACTION_TAKEN,
            label="Approve recommended action",
            legal_basis="Authorised by operational mandate",
            requires_reasoning=risk_level >= RiskLevel.HIGH,
            risk_level=risk_level,
        ),
        ActionOption(
            action=FinalAction.REJECTED,
            label="Reject — insufficient basis",
            legal_basis="N/A",
            requires_reasoning=False,
            risk_level=risk_level,
        ),
        ActionOption(
            action=FinalAction.ESCALATED,
            label="Escalate to senior authority",
            legal_basis="Escalation protocol",
            requires_reasoning=True,
            risk_level=risk_level,
        ),
        ActionOption(
            action=FinalAction.DEFERRED,
            label="Defer — request more evidence",
            legal_basis="N/A",
            requires_reasoning=True,
            risk_level=risk_level,
        ),
    ]
    return options
