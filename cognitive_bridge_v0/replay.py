from __future__ import annotations

from .schemas import (
    GATE_VERSION,
    LEDGER_VERSION,
    PROVIDER_MODE,
    REPLAY_VERSION,
    SCHEMA_VERSION,
    CandidateLedgerEntry,
    ConstitutionGateResult,
    ReplayRecord,
    SnapshotInput,
    ThoughtBridgeOutput,
    stable_hash,
    utc_now,
)


class ReplayCompare:
    """Canonical hash based replay comparison for offline fixture runs."""

    runtime_excluded_keys = {
        "created_at",
        "replay_id",
        "gate_id",
        "candidate_id",
        "sink_id",
    }

    def build_record(
        self,
        snapshot: SnapshotInput,
        output: ThoughtBridgeOutput,
        gate_result: ConstitutionGateResult,
        ledger_entry: CandidateLedgerEntry,
        replay_result: str = "matched",
    ) -> ReplayRecord:
        snapshot.validate()
        output.validate()
        gate_result.validate()
        ledger_entry.validate()
        snapshot_hash = stable_hash(snapshot, excluded_keys={"created_at"})
        output_hash = stable_hash(output, excluded_keys=self.runtime_excluded_keys)
        gate_hash = stable_hash(gate_result, excluded_keys=self.runtime_excluded_keys)
        ledger_hash = stable_hash(ledger_entry, excluded_keys=self.runtime_excluded_keys)
        replay_id = "replay_" + stable_hash(
            {
                "snapshot_hash": snapshot_hash,
                "output_hash": output_hash,
                "gate_hash": gate_hash,
                "ledger_hash": ledger_hash,
                "replay_version": REPLAY_VERSION,
            }
        )[:16]
        record = ReplayRecord(
            replay_id=replay_id,
            schema_version=SCHEMA_VERSION,
            source_snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot_hash,
            provider_mode=PROVIDER_MODE,
            output_schema_version=SCHEMA_VERSION,
            gate_version=GATE_VERSION,
            ledger_version=LEDGER_VERSION,
            output_hash=output_hash,
            gate_hash=gate_hash,
            ledger_hash=ledger_hash,
            replay_result=replay_result,
            mismatch_notes=[] if replay_result == "matched" else ["hash mismatch"],
            created_at=utc_now(),
        )
        record.validate()
        return record

    def compare(self, first: ReplayRecord, second: ReplayRecord) -> ReplayRecord:
        first.validate()
        second.validate()
        mismatch_notes = []
        result = "matched"
        if first.snapshot_hash != second.snapshot_hash:
            result = "mismatched"
            mismatch_notes.append("snapshot_hash")
        if first.output_hash != second.output_hash:
            result = "mismatched"
            mismatch_notes.append("output_hash")
        if first.gate_hash != second.gate_hash:
            result = "gate_changed"
            mismatch_notes.append("gate_hash")
        if first.ledger_hash != second.ledger_hash:
            result = "ledger_changed"
            mismatch_notes.append("ledger_hash")
        compared = ReplayRecord(
            replay_id="replay_compare_" + stable_hash(
                {
                    "first": first.replay_id,
                    "second": second.replay_id,
                    "result": result,
                    "mismatch_notes": mismatch_notes,
                }
            )[:16],
            schema_version=SCHEMA_VERSION,
            source_snapshot_id=first.source_snapshot_id,
            snapshot_hash=first.snapshot_hash,
            provider_mode=PROVIDER_MODE,
            output_schema_version=SCHEMA_VERSION,
            gate_version=GATE_VERSION,
            ledger_version=LEDGER_VERSION,
            output_hash=first.output_hash,
            gate_hash=first.gate_hash,
            ledger_hash=first.ledger_hash,
            replay_result=result,
            mismatch_notes=mismatch_notes,
            created_at=utc_now(),
        )
        compared.validate()
        return compared
