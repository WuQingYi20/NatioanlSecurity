"""
Core data structures for TrustLayer MVP.
Translates the Rust types from spec §5.2 into Python dataclasses.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Optional


# =============================================================================
# § PRIMITIVE ID TYPES
# =============================================================================

def new_id() -> str:
    return str(uuid.uuid4())


# =============================================================================
# § ENUMS
# =============================================================================

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def __lt__(self, other):
        order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
        return order.index(self) < order.index(other)

    def __le__(self, other):
        return self == other or self < other


class ActionType(Enum):
    FLAG_FOR_REVIEW = "flag_for_review"
    ALERT_OPERATOR = "alert_operator"
    ESCALATE_TO_SENIOR = "escalate_to_senior"
    ESCALATE_TO_LEGAL = "escalate_to_legal"
    REFER_TO_INVESTIGATOR = "refer_to_investigator"


class GuardrailVerdict(Enum):
    PASS = "pass"
    FLAG = "flag"
    BLOCK = "block"
    QUARANTINE = "quarantine"


class HitLDecision(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    DEFERRED = "deferred"


class FinalAction(Enum):
    ACTION_TAKEN = "action_taken"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    DEFERRED = "deferred"
    BLOCKED_BY_GUARDRAIL = "blocked_by_guardrail"
    AUTO_ESCALATED = "auto_escalated"


class OperatorTier(Enum):
    AUTO_LOG = "auto_log"
    TIER1_OPERATOR = "tier1_operator"
    TIER2_OPERATOR = "tier2_operator"
    SENIOR_OPERATOR = "senior_operator"
    OVERSIGHT_BODY = "oversight_body"
    AUDIT_ONLY = "audit_only"
    AUDIT_WITH_ESCALATION = "audit_with_escalation"


class VerdictClass(Enum):
    PASS = "pass"
    FLAGGED = "flagged"
    BLOCKED = "blocked"


class CheckId(Enum):
    G1_CONFIDENCE = "G1_confidence"
    G2_SCOPE = "G2_scope"
    G3_ANTI_HALLUCINATION = "G3_anti_hallucination"
    G4_EVIDENCE_SUFFICIENCY = "G4_evidence_sufficiency"
    G5_DISPROPORTION = "G5_disproportion"
    G6_RISK_ASSESSMENT = "G6_risk_assessment"


# =============================================================================
# § DATA STRUCTURES
# =============================================================================

@dataclass
class Fragment:
    value: str
    source_id: str
    start_position: int = 0


@dataclass
class EvidenceItem:
    item_id: str = field(default_factory=new_id)
    source_id: str = ""
    source_reliability: float = 0.5
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    content_summary: str = ""
    content_hash: str = ""
    legal_basis: str = ""


@dataclass
class Claim:
    text: str = ""
    supporting_evidence: list[str] = field(default_factory=list)
    reasoning_chain: list[str] = field(default_factory=list)
    falsification_conditions: list[str] = field(default_factory=list)
    alternative_hypothesis: str = ""


@dataclass
class AgentOutput:
    """Raw output from the AI agent pipeline.
    Does NOT contain risk_level — assessed independently by Tier 1.
    In Python, we enforce single-consumption via a flag (Rust uses ownership).
    """
    output_id: str = field(default_factory=new_id)
    agent_id: str = "agent-default"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    subject_ref: str = ""  # Pseudonymised subject reference
    claim: Claim = field(default_factory=Claim)
    evidence: list[EvidenceItem] = field(default_factory=list)
    raw_fragments: list[Fragment] = field(default_factory=list)
    agent_confidence: float = 0.5
    action_requested: ActionType = ActionType.FLAG_FOR_REVIEW

    # Python enforcement of single-consumption (Rust does this via ownership)
    _consumed: bool = field(default=False, repr=False)

    def mark_consumed(self):
        if self._consumed:
            raise RuntimeError(
                "AgentOutput already consumed — single-consumption invariant violated. "
                "In Rust, this is enforced at compile time via ownership."
            )
        self._consumed = True


@dataclass
class CheckResult:
    check_id: CheckId
    passed: bool
    reason: str = ""
    is_hard_fail: bool = False


@dataclass
class GuardrailResult:
    output_id: str
    verdict: GuardrailVerdict
    verdict_reasons: list[str] = field(default_factory=list)
    assessed_risk_level: RiskLevel = RiskLevel.LOW
    confidence_calibrated: float = 0.0
    checks_passed: list[CheckId] = field(default_factory=list)
    checks_failed: list[tuple[CheckId, str]] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class UncertaintyBundle:
    point_estimate: float = 0.0
    confidence_interval: tuple[float, float] = (0.0, 1.0)
    epistemic_uncertainty: str = "Unknown model limitations"
    aleatoric_uncertainty: str = "Noise in data sources"
    key_assumptions: list[str] = field(default_factory=list)
    critical_evidence_items: list[str] = field(default_factory=list)


@dataclass
class ActionOption:
    action: FinalAction
    label: str
    legal_basis: str = ""
    requires_reasoning: bool = False
    risk_level: RiskLevel = RiskLevel.LOW


@dataclass
class OperatorBrief:
    """Designed to defeat automation bias through structure.
    Sections are ordered: evidence first, conclusion last.
    """
    output_id: str
    subject_pseudonym: str

    # SECTION 1: Evidence (shown first)
    evidence_items: list[EvidenceItem] = field(default_factory=list)

    # SECTION 2: Uncertainty (shown second)
    assessment: UncertaintyBundle = field(default_factory=UncertaintyBundle)

    # SECTION 3: Alternative hypothesis (shown third)
    alternative_explanation: str = ""

    # SECTION 4: AI conclusion (shown last)
    ai_conclusion: str = ""

    # SECTION 5: Action options
    available_actions: list[ActionOption] = field(default_factory=list)

    # Governance metadata
    legal_basis: str = ""
    requires_dual_approval: bool = False
    assessed_risk_level: RiskLevel = RiskLevel.LOW
    review_deadline: Optional[datetime] = None
    operator_tier: OperatorTier = OperatorTier.TIER1_OPERATOR


@dataclass
class HitLRecord:
    output_id: str
    operator_id: str = "operator-default"
    decision: HitLDecision = HitLDecision.REJECTED
    reasoning: str = ""
    evidence_viewed: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    decided_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    second_approval: Optional[str] = None
    final_action: FinalAction = FinalAction.REJECTED

    def elapsed_seconds(self) -> float:
        return (self.decided_at - self.created_at).total_seconds()

    def has_second_approval(self) -> bool:
        return self.second_approval is not None


@dataclass
class AgentOutputDigest:
    hash_hex: str
    algorithm: str = "sha3-256"
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def compute(output: AgentOutput) -> AgentOutputDigest:
        canonical = f"{output.output_id}|{output.agent_id}|{output.claim.text}|{output.agent_confidence}"
        h = hashlib.sha3_256(canonical.encode()).hexdigest()
        return AgentOutputDigest(hash_hex=h)

    def verify(self, output: AgentOutput) -> bool:
        recomputed = self.compute(output)
        return recomputed.hash_hex == self.hash_hex


@dataclass
class AuditEntry:
    entry_id: str = field(default_factory=new_id)
    output_id: str = ""
    agent_output_digest: Optional[AgentOutputDigest] = None
    guardrail_result: Optional[GuardrailResult] = None
    hitl_record: Optional[HitLRecord] = None
    final_action: FinalAction = FinalAction.BLOCKED_BY_GUARDRAIL
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Hash chain for integrity (simulates Trillian Merkle tree)
    previous_hash: str = ""
    entry_hash: str = ""

    def compute_hash(self, previous_hash: str = "") -> str:
        data = f"{self.entry_id}|{self.output_id}|{self.final_action.value}|{self.timestamp.isoformat()}|{previous_hash}"
        return hashlib.sha256(data.encode()).hexdigest()
