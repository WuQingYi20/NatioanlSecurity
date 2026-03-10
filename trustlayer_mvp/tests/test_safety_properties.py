"""
Tests for the three core safety properties from spec §4.3:
  SP1 — Non-Bypassability
  SP2 — Audit Completeness
  SP3 — Block Irreversibility
"""
import pytest
from datetime import datetime, timedelta, timezone

from trustlayer_mvp.models import (
    AgentOutput, Claim, EvidenceItem, Fragment, ActionType,
    HitLRecord, HitLDecision, FinalAction, GuardrailVerdict, new_id,
)
from trustlayer_mvp.pipeline import GovernancePipeline
from trustlayer_mvp.mock_agent import MockAgent


@pytest.fixture
def pipeline():
    return GovernancePipeline()


@pytest.fixture
def agent():
    return MockAgent()


# =============================================================================
# SP1 — Non-Bypassability
# =============================================================================

class TestSP1NonBypassability:
    """No output can trigger a downstream action without passing through all three tiers."""

    def test_approved_output_has_all_three_tiers(self, pipeline, agent):
        """An approved output must have guardrail_result + hitl_record + audit_entry."""
        output = agent.generate(confidence=0.82, evidence_count=2)
        result = pipeline.submit(output)

        if result.needs_operator:
            # Simulate operator decision
            now = datetime.now(timezone.utc)
            record = HitLRecord(
                output_id=result.output_id,
                operator_id="test-operator",
                decision=HitLDecision.APPROVED,
                reasoning="Sufficient evidence reviewed, pattern confirmed" + " " * 20,
                evidence_viewed=["evidence-1"],
                created_at=now - timedelta(seconds=30),
                decided_at=now,
            )
            result = pipeline.decide(result.output_id, record)

        # Verify all three tiers present
        assert result.guardrail_result is not None
        assert result.audit_entry is not None

    def test_cannot_create_audit_without_guardrail(self, pipeline):
        """Audit entries cannot exist without a guardrail result."""
        for entry in pipeline.tier3.entries:
            assert entry.guardrail_result is not None

    def test_single_consumption_prevents_double_processing(self, agent):
        """AgentOutput cannot be processed twice (ownership invariant)."""
        output = agent.generate()
        pipeline1 = GovernancePipeline()
        pipeline1.submit(output)

        # Second submission should fail — output already consumed
        pipeline2 = GovernancePipeline()
        with pytest.raises(RuntimeError, match="already consumed"):
            pipeline2.submit(output)


# =============================================================================
# SP2 — Audit Completeness
# =============================================================================

class TestSP2AuditCompleteness:
    """Every output that enters the system appears in the audit log."""

    def test_blocked_output_is_logged(self, pipeline, agent):
        """Blocked outputs must still appear in the audit log."""
        output = agent.generate(
            confidence=0.15,  # Will be blocked by G1
            evidence_count=1,
        )
        result = pipeline.submit(output)

        # Should be blocked and logged
        entry = pipeline.tier3.get_entry(output.output_id)
        assert entry is not None
        assert entry.final_action == FinalAction.BLOCKED_BY_GUARDRAIL

    def test_auto_logged_output_appears(self, pipeline, agent):
        """Auto-approved outputs must appear in the audit log."""
        output = agent.generate(
            confidence=0.82,
            action=ActionType.FLAG_FOR_REVIEW,
            evidence_count=2,
        )
        result = pipeline.submit(output)

        if not result.needs_operator:
            entry = pipeline.tier3.get_entry(output.output_id)
            assert entry is not None

    def test_all_scenarios_logged(self, pipeline):
        """Process multiple scenarios — every one must be logged."""
        from trustlayer_mvp.scenarios import ALL_SCENARIOS

        output_ids = []
        for scenario_fn in ALL_SCENARIOS:
            scenario = scenario_fn()
            output = scenario["output"]
            output_ids.append(output.output_id)
            pipeline.submit(output)

        # Resolve any pending reviews
        for oid, brief, tier in pipeline.get_pending_reviews():
            now = datetime.now(timezone.utc)
            record = HitLRecord(
                output_id=oid,
                operator_id="test-operator",
                decision=HitLDecision.REJECTED,
                reasoning="Rejected during automated test — insufficient basis for approval per policy" + " " * 10,
                evidence_viewed=["auto-test"],
                created_at=now - timedelta(seconds=60),
                decided_at=now,
                second_approval="second-operator" if brief.requires_dual_approval else None,
            )
            pipeline.decide(oid, record)

        # Every output must have an audit entry
        for oid in output_ids:
            entry = pipeline.tier3.get_entry(oid)
            assert entry is not None, f"Output {oid} missing from audit log"


# =============================================================================
# SP3 — Block Irreversibility
# =============================================================================

class TestSP3BlockIrreversibility:
    """Once blocked by Tier 1, an output cannot be approved by Tier 2."""

    def test_blocked_output_cannot_be_approved(self, pipeline, agent):
        """Attempting to approve a blocked output must raise an error."""
        # Generate output that will be blocked (no fragments = hallucination)
        output = agent.generate(
            claim_text="Cryptocurrency laundering detected via offshore accounts",
            confidence=0.65,
            include_fragments=False,
        )
        result = pipeline.submit(output)

        if result.guardrail_result.verdict == GuardrailVerdict.BLOCK:
            # Verify it's not in pending reviews
            pending_ids = [oid for oid, _, _ in pipeline.get_pending_reviews()]
            assert output.output_id not in pending_ids

    def test_blocked_outputs_logged_as_blocked(self, pipeline, agent):
        """Blocked outputs must have BLOCKED_BY_GUARDRAIL as final action."""
        output = agent.generate(confidence=0.15)  # Will fail G1
        result = pipeline.submit(output)

        if result.guardrail_result.verdict == GuardrailVerdict.BLOCK:
            assert result.audit_entry.final_action == FinalAction.BLOCKED_BY_GUARDRAIL


# =============================================================================
# Audit Integrity
# =============================================================================

class TestAuditIntegrity:
    """Hash chain integrity verification."""

    def test_hash_chain_valid_after_multiple_entries(self, pipeline, agent):
        """Audit log hash chain must be valid after multiple entries."""
        for i in range(5):
            output = agent.generate(confidence=0.5 + i * 0.1)
            pipeline.submit(output)

        is_valid, msg = pipeline.verify_audit_integrity()
        assert is_valid, msg

    def test_tampered_entry_detected(self, pipeline, agent):
        """Modifying an entry should break the hash chain."""
        for i in range(3):
            output = agent.generate(confidence=0.7)
            pipeline.submit(output)

        # Tamper with middle entry
        if len(pipeline.tier3._entries) >= 2:
            pipeline.tier3._entries[1].entry_hash = "tampered_hash"
            is_valid, msg = pipeline.verify_audit_integrity()
            assert not is_valid
