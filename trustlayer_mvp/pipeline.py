"""
End-to-end governance pipeline (spec §3.3, §9).
Enforces SP1 (Non-Bypassability) and SP2 (Audit Completeness) by construction.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    AgentOutput, GuardrailResult, GuardrailVerdict,
    HitLRecord, HitLDecision, FinalAction, AuditEntry,
    OperatorBrief, OperatorTier, AgentOutputDigest,
)
from .tier1_guardrail import GuardrailLayer
from .tier2_hitl import HitLLayer
from .tier3_audit import AuditLayer


class PipelineResult:
    """Result of processing an AgentOutput through the full governance pipeline."""

    def __init__(
        self,
        output_id: str,
        guardrail_result: GuardrailResult,
        operator_tier: OperatorTier,
        brief: OperatorBrief | None,
        hitl_record: HitLRecord | None,
        audit_entry: AuditEntry,
        needs_operator: bool,
    ):
        self.output_id = output_id
        self.guardrail_result = guardrail_result
        self.operator_tier = operator_tier
        self.brief = brief
        self.hitl_record = hitl_record
        self.audit_entry = audit_entry
        self.needs_operator = needs_operator


class GovernancePipeline:
    """Three-tier governance pipeline.

    Linear ownership transfer:
      AgentOutput -> GuardrailLayer -> HitLLayer -> AuditLayer
    No output can reach downstream actions without passing all three tiers (SP1).
    Every output is logged regardless of outcome (SP2).
    """

    def __init__(self):
        self.tier1 = GuardrailLayer()
        self.tier2 = HitLLayer()
        self.tier3 = AuditLayer()
        # Pending reviews: output_id -> (AgentOutput ref, GuardrailResult, Brief, OperatorTier)
        self._pending: dict[str, tuple[AgentOutput, GuardrailResult, OperatorBrief, OperatorTier]] = {}

    def submit(self, output: AgentOutput) -> PipelineResult:
        """Submit an AgentOutput to the governance pipeline.

        Phase 1: Tier 1 (Guardrail) — always runs
        Phase 2: Tier 2 routing — determines if operator review needed
        Phase 3: Depending on routing:
          - AUTO_LOG: auto-approve and log
          - AUDIT_ONLY/AUDIT_WITH_ESCALATION: block and log
          - Other: queue for operator review (returns needs_operator=True)
        """
        # Compute digest before guardrail consumes the output
        digest = AgentOutputDigest.compute(output)

        # === TIER 1: Guardrail evaluation ===
        guardrail_result = self.tier1.evaluate(output)

        # === TIER 2: Route ===
        tier = self.tier2.router.route(guardrail_result)

        # Case 1: Blocked — goes directly to audit, no operator action
        if self.tier2.is_audit_only(tier):
            # SP3: Blocked outputs CANNOT be approved
            audit_entry = self.tier3.log(
                guardrail_result=guardrail_result,
                hitl_record=None,
                final_action=FinalAction.BLOCKED_BY_GUARDRAIL,
                agent_output_digest=digest,
            )
            return PipelineResult(
                output_id=output.output_id,
                guardrail_result=guardrail_result,
                operator_tier=tier,
                brief=None,
                hitl_record=None,
                audit_entry=audit_entry,
                needs_operator=False,
            )

        # Build brief for operator
        brief = self.tier2.brief_builder.build(output, guardrail_result, tier)

        # Case 2: Auto-log (Low risk + Pass)
        if self.tier2.is_auto_log(tier):
            auto_record = HitLRecord(
                output_id=output.output_id,
                operator_id="SYSTEM_AUTO",
                decision=HitLDecision.APPROVED,
                reasoning="Auto-approved: Low risk, all checks passed",
                evidence_viewed=["auto"],
                final_action=FinalAction.ACTION_TAKEN,
            )
            audit_entry = self.tier3.log(
                guardrail_result=guardrail_result,
                hitl_record=auto_record,
                final_action=FinalAction.ACTION_TAKEN,
                agent_output_digest=digest,
            )
            return PipelineResult(
                output_id=output.output_id,
                guardrail_result=guardrail_result,
                operator_tier=tier,
                brief=brief,
                hitl_record=auto_record,
                audit_entry=audit_entry,
                needs_operator=False,
            )

        # Case 3: Needs operator review
        self._pending[output.output_id] = (output, guardrail_result, brief, tier)
        # Return with needs_operator=True — no audit entry yet (will be created on decision)
        return PipelineResult(
            output_id=output.output_id,
            guardrail_result=guardrail_result,
            operator_tier=tier,
            brief=brief,
            hitl_record=None,
            audit_entry=None,  # type: ignore
            needs_operator=True,
        )

    def decide(self, output_id: str, record: HitLRecord) -> PipelineResult:
        """Submit operator decision for a pending review.

        Validates decision against enforcement rules, then logs to audit.
        """
        if output_id not in self._pending:
            raise ValueError(f"No pending review for output_id={output_id}")

        output, guardrail_result, brief, tier = self._pending[output_id]

        # SP3: Cannot approve a blocked output
        if guardrail_result.verdict == GuardrailVerdict.BLOCK:
            raise RuntimeError(
                "SP3 violation attempt: cannot approve a blocked output. "
                "Block Irreversibility is enforced."
            )

        # Validate operator engagement (anti-rubber-stamp)
        self.tier2.validate_decision(record, brief)

        # Map decision to final action
        final_action = self._map_decision(record.decision)
        record.final_action = final_action

        # === TIER 3: Audit ===
        digest = AgentOutputDigest.compute(output)
        audit_entry = self.tier3.log(
            guardrail_result=guardrail_result,
            hitl_record=record,
            final_action=final_action,
            agent_output_digest=digest,
        )

        del self._pending[output_id]

        return PipelineResult(
            output_id=output_id,
            guardrail_result=guardrail_result,
            operator_tier=tier,
            brief=brief,
            hitl_record=record,
            audit_entry=audit_entry,
            needs_operator=False,
        )

    def get_pending_reviews(self) -> list[tuple[str, OperatorBrief, OperatorTier]]:
        """Get all outputs pending operator review."""
        return [
            (oid, brief, tier)
            for oid, (_, _, brief, tier) in self._pending.items()
        ]

    def get_audit_stats(self) -> dict:
        return self.tier3.get_statistics()

    def verify_audit_integrity(self) -> tuple[bool, str]:
        return self.tier3.verify_integrity()

    def _map_decision(self, decision: HitLDecision) -> FinalAction:
        mapping = {
            HitLDecision.APPROVED: FinalAction.ACTION_TAKEN,
            HitLDecision.REJECTED: FinalAction.REJECTED,
            HitLDecision.ESCALATED: FinalAction.ESCALATED,
            HitLDecision.DEFERRED: FinalAction.DEFERRED,
        }
        return mapping.get(decision, FinalAction.REJECTED)
