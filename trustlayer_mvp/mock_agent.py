"""
Mock AI agent that generates configurable AgentOutputs for demonstration.
Spec §14 Phase 5: "Mock agent generating configurable AgentOutputs"
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .models import (
    AgentOutput, Claim, EvidenceItem, Fragment, ActionType, new_id,
)


class MockAgent:
    """Generates AgentOutputs for testing the governance pipeline."""

    def __init__(self, agent_id: str = "mock-agent-001"):
        self.agent_id = agent_id

    def generate(
        self,
        claim_text: str = "Evidence suggests suspicious financial activity",
        confidence: float = 0.75,
        action: ActionType = ActionType.FLAG_FOR_REVIEW,
        evidence_count: int = 2,
        include_fragments: bool = True,
        subject_ref: str = "",
        alternative_hypothesis: str = "Normal business activity misidentified as suspicious",
    ) -> AgentOutput:
        """Generate a configurable AgentOutput."""
        if not subject_ref:
            subject_ref = hashlib.sha256(f"subject-{new_id()}".encode()).hexdigest()[:16]

        evidence = []
        for i in range(evidence_count):
            evidence.append(EvidenceItem(
                item_id=new_id(),
                source_id=f"source-{i+1}",
                source_reliability=0.6 + (i * 0.1),
                content_summary=f"Evidence item {i+1}: supporting data from source-{i+1}",
                content_hash=hashlib.sha256(f"content-{i}".encode()).hexdigest(),
                legal_basis="Authorised under operational mandate",
            ))

        fragments = []
        if include_fragments:
            # Create fragments that anchor the claim text
            words = claim_text.split()
            for i in range(0, len(words), 3):
                chunk = " ".join(words[i:i+3])
                fragments.append(Fragment(
                    value=chunk,
                    source_id=f"source-{(i // 3) + 1}",
                    start_position=i,
                ))

        claim = Claim(
            text=claim_text,
            supporting_evidence=[e.item_id for e in evidence],
            reasoning_chain=[
                "Step 1: Identified pattern in transaction data",
                "Step 2: Cross-referenced with known threat indicators",
                "Step 3: Assessed probability of threat scenario",
            ],
            falsification_conditions=[
                "If transaction pattern is seasonal business norm",
                "If flagged entity has legitimate reason for activity",
            ],
            alternative_hypothesis=alternative_hypothesis,
        )

        return AgentOutput(
            output_id=new_id(),
            agent_id=self.agent_id,
            subject_ref=subject_ref,
            claim=claim,
            evidence=evidence,
            raw_fragments=fragments,
            agent_confidence=confidence,
            action_requested=action,
        )
