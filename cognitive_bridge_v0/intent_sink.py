from __future__ import annotations

from typing import Optional

from .schemas import CandidateLedgerEntry, IntentSinkResult, SCHEMA_VERSION, stable_hash, utc_now


class IntentSink:
    """Translate accepted ledger entries into low-permission candidates only."""

    def translate(self, entry: CandidateLedgerEntry) -> Optional[IntentSinkResult]:
        entry.validate()
        if entry.ledger_status != "accepted":
            return None
        sink_type = entry.accepted_sink
        sink_id = "sink_" + stable_hash(
            {
                "candidate_id": entry.candidate_id,
                "accepted_sink": sink_type,
                "schema_version": SCHEMA_VERSION,
            }
        )[:16]
        result = IntentSinkResult(
            sink_id=sink_id,
            source_candidate_id=entry.candidate_id,
            sink_type=sink_type,
            permission_level="low",
            payload={
                "candidate": entry.parsed_candidate,
                "source": "candidate_ledger",
                "permission": "low",
            },
            created_at=utc_now(),
            action_generated=False,
            system_state_write_requested=False,
            notes="low-permission candidate only",
        )
        result.validate()
        return result
