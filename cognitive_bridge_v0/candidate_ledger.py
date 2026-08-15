from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from .schemas import (
    LEDGER_VERSION,
    SCHEMA_VERSION,
    CandidateLedgerEntry,
    ConstitutionGateResult,
    SnapshotInput,
    ThoughtBridgeOutput,
    stable_hash,
    to_plain_dict,
    utc_now,
)


class CandidateLedger:
    """Append-only isolated ledger for bridge candidates."""

    ledger_version = LEDGER_VERSION

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else None
        self.entries: List[CandidateLedgerEntry] = []
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        snapshot: SnapshotInput,
        output: ThoughtBridgeOutput,
        gate_result: ConstitutionGateResult,
    ) -> CandidateLedgerEntry:
        status = self._ledger_status(gate_result)
        accepted_sink = self._accepted_sink(gate_result)
        parsed_candidate = {
            "accepted_parts": gate_result.accepted_parts,
            "rejected_parts": gate_result.rejected_parts,
            "interpretation": output.interpretation,
        }
        candidate_id = "cand_" + stable_hash(
            {
                "source_snapshot_id": snapshot.snapshot_id,
                "source_output_id": output.output_id,
                "gate_id": gate_result.gate_id,
                "ledger_version": self.ledger_version,
            }
        )[:16]
        entry = CandidateLedgerEntry(
            candidate_id=candidate_id,
            schema_version=SCHEMA_VERSION,
            source_snapshot_id=snapshot.snapshot_id,
            source_output_id=output.output_id,
            raw_llm_response_ref=output.raw_response_ref or "missing_raw_response_ref",
            parsed_candidate=parsed_candidate,
            gate_result=gate_result,
            ledger_status=status,
            accepted_sink=accepted_sink,
            decay_policy={"mode": "manual_or_replay_only", "expires_after": None},
            update_policy={"mode": "append_only_no_overwrite"},
            replay_hash="pending",
            created_at=utc_now(),
            notes="isolated offline ledger entry",
        )
        replay_hash = stable_hash(
            entry,
            excluded_keys={"created_at", "replay_hash"},
        )
        entry.replay_hash = replay_hash
        entry.validate()
        self.entries.append(entry)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(to_plain_dict(entry), ensure_ascii=False, sort_keys=True))
                handle.write("\n")
        return entry

    def _ledger_status(self, gate_result: ConstitutionGateResult) -> str:
        if gate_result.gate_status == "accepted":
            return "accepted"
        if gate_result.gate_status == "diagnostics_only":
            return "diagnostics_only"
        if gate_result.gate_status == "human_review":
            return "pending"
        return "rejected"

    def _accepted_sink(self, gate_result: ConstitutionGateResult) -> str:
        if gate_result.gate_status == "accepted":
            if "persistent_intent_candidate" in gate_result.sink_permissions:
                return "persistent_intent_candidate"
            return gate_result.sink_permissions[0]
        if gate_result.gate_status == "diagnostics_only":
            return "diagnostics_only"
        return "none"
