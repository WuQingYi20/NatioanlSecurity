"""
Tier 3 — Audit Layer (spec §7)
Append-only audit log with SHA-256 hash chain (simulates Trillian Merkle tree).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    AuditEntry, GuardrailResult, HitLRecord, FinalAction,
    AgentOutputDigest, new_id,
)


class AuditLayer:
    """Append-only audit log with hash chain integrity.
    Simulates Trillian's Merkle tree for MVP purposes.
    """

    def __init__(self):
        self._entries: list[AuditEntry] = []
        self._last_hash: str = "0" * 64  # Genesis hash

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def log(
        self,
        guardrail_result: GuardrailResult,
        hitl_record: HitLRecord | None,
        final_action: FinalAction,
        agent_output_digest: AgentOutputDigest | None = None,
    ) -> AuditEntry:
        """Create and append an audit entry. Every output gets logged regardless of outcome.
        This enforces SP2 (Audit Completeness).
        """
        entry = AuditEntry(
            entry_id=new_id(),
            output_id=guardrail_result.output_id,
            agent_output_digest=agent_output_digest,
            guardrail_result=guardrail_result,
            hitl_record=hitl_record,
            final_action=final_action,
            timestamp=datetime.now(timezone.utc),
            previous_hash=self._last_hash,
        )

        # Compute hash chain (simulates Trillian Merkle tree leaf)
        entry.entry_hash = entry.compute_hash(self._last_hash)
        self._last_hash = entry.entry_hash

        self._entries.append(entry)
        return entry

    def verify_integrity(self) -> tuple[bool, str]:
        """Verify the hash chain from genesis to latest entry.
        Returns (is_valid, message).
        """
        if not self._entries:
            return True, "Audit log is empty — trivially consistent"

        expected_hash = "0" * 64  # Genesis
        for i, entry in enumerate(self._entries):
            if entry.previous_hash != expected_hash:
                return False, f"Chain broken at entry {i}: expected prev_hash={expected_hash[:16]}..., got {entry.previous_hash[:16]}..."

            recomputed = entry.compute_hash(expected_hash)
            if entry.entry_hash != recomputed:
                return False, f"Tampered entry at index {i}: hash mismatch"

            expected_hash = entry.entry_hash

        return True, f"Hash chain verified: {len(self._entries)} entries, integrity OK"

    def get_entry(self, output_id: str) -> AuditEntry | None:
        for entry in self._entries:
            if entry.output_id == output_id:
                return entry
        return None

    def get_statistics(self) -> dict:
        """Aggregate statistics for public reporting (spec §7.1 — public access tier)."""
        total = len(self._entries)
        if total == 0:
            return {"total": 0}

        actions = {}
        risk_levels = {}
        for entry in self._entries:
            action = entry.final_action.value
            actions[action] = actions.get(action, 0) + 1

            if entry.guardrail_result:
                risk = entry.guardrail_result.assessed_risk_level.value
                risk_levels[risk] = risk_levels.get(risk, 0) + 1

        return {
            "total_entries": total,
            "actions": actions,
            "risk_distribution": risk_levels,
            "integrity_verified": self.verify_integrity()[0],
        }

    def export_json(self, filepath: str | Path) -> None:
        """Export audit log for external verification."""
        data = []
        for entry in self._entries:
            data.append({
                "entry_id": entry.entry_id,
                "output_id": entry.output_id,
                "final_action": entry.final_action.value,
                "timestamp": entry.timestamp.isoformat(),
                "previous_hash": entry.previous_hash,
                "entry_hash": entry.entry_hash,
                "risk_level": entry.guardrail_result.assessed_risk_level.value if entry.guardrail_result else None,
                "verdict": entry.guardrail_result.verdict.value if entry.guardrail_result else None,
            })
        Path(filepath).write_text(json.dumps(data, indent=2))
