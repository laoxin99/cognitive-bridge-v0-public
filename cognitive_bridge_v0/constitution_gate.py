from __future__ import annotations

from typing import Any, Dict, List

from .schemas import (
    GATE_VERSION,
    ConstitutionGateResult,
    SnapshotInput,
    ThoughtBridgeOutput,
    stable_hash,
)


class ConstitutionGate:
    """Conservative v0 gate: reject privilege escalation, never decide actions."""

    gate_version = GATE_VERSION

    def review(
        self, snapshot: SnapshotInput, output: ThoughtBridgeOutput
    ) -> ConstitutionGateResult:
        snapshot.validate()
        reasons: List[str] = []
        accepted_parts: List[Dict[str, Any]] = []
        rejected_parts: List[Dict[str, Any]] = []

        if not output.source_snapshot_id:
            reasons.append("R01_missing_source_snapshot_id")
        if not output.raw_response_ref:
            reasons.append("R02_missing_raw_response_ref")
        if output.source_snapshot_id and output.source_snapshot_id != snapshot.snapshot_id:
            reasons.append("R01_source_snapshot_id_mismatch")

        try:
            output.validate()
        except ValueError:
            # Field-specific reasons above are kept stable for tests and replay.
            if not reasons:
                reasons.append("R00_invalid_thought_bridge_output")

        if output.forbidden_direct_action:
            reasons.append("R03_direct_action_requested")
        reasons.extend(output.safety_flags.active_rule_ids())
        reasons.extend(self._scope_conflict_reasons(snapshot, output))
        reasons.extend(self._forbidden_crossing_reasons(snapshot, output))

        natural_language_only = (
            bool(output.natural_language_advice.strip())
            and not output.has_structured_candidates()
        )
        diagnostics_only = (
            snapshot.diagnostics_flags.diagnostics_only
            or snapshot.fixture_case == "diagnostics_only"
            or natural_language_only
            or not snapshot.diagnostics_flags.allow_candidate_generation
            or not snapshot.diagnostics_flags.allow_low_permission_sink
        )

        if natural_language_only:
            reasons.append("R11_natural_language_advice_only")
        if not snapshot.diagnostics_flags.allow_candidate_generation:
            reasons.append("R13_candidate_generation_disabled")
        if not snapshot.diagnostics_flags.allow_low_permission_sink:
            reasons.append("R12_diagnostics_only_no_deposition")

        if diagnostics_only:
            gate_status = "diagnostics_only"
            accepted_parts = []
            rejected_parts = self._all_candidate_parts(output)
            if output.natural_language_advice:
                rejected_parts.append(
                    {
                        "kind": "natural_language_advice",
                        "content": output.natural_language_advice,
                    }
                )
            sink_permissions = ["diagnostics_only"]
            needs_human_review = False
            gate_notes = "diagnostics only; no deposition"
        elif reasons:
            gate_status = "rejected"
            rejected_parts = self._all_candidate_parts(output)
            if output.natural_language_advice:
                rejected_parts.append(
                    {
                        "kind": "natural_language_advice",
                        "content": output.natural_language_advice,
                    }
                )
            sink_permissions = []
            needs_human_review = False
            gate_notes = "rejected by conservative constitution gate"
        else:
            gate_status = "accepted"
            accepted_parts = self._all_candidate_parts(output)
            sink_permissions = [
                "internal_stimulus_candidate",
                "persistent_intent_candidate",
                "strategy_bias_candidate",
            ]
            needs_human_review = False
            gate_notes = "accepted as low-permission candidate only"

        deduped_reasons = list(dict.fromkeys(reasons))
        gate_id = "gate_" + stable_hash(
            {
                "source_output_id": output.output_id,
                "gate_status": gate_status,
                "reject_reasons": deduped_reasons,
                "gate_version": self.gate_version,
            }
        )[:16]

        result = ConstitutionGateResult(
            gate_id=gate_id,
            source_output_id=output.output_id,
            gate_status=gate_status,
            accepted_parts=accepted_parts,
            rejected_parts=rejected_parts,
            reject_reasons=deduped_reasons,
            needs_human_review=needs_human_review,
            diagnostics_only=diagnostics_only,
            sink_permissions=sink_permissions,
            gate_notes=gate_notes,
        )
        result.validate()
        return result

    def _all_candidate_parts(self, output: ThoughtBridgeOutput) -> List[Dict[str, Any]]:
        parts: List[Dict[str, Any]] = []
        for group_name, candidates in output.candidate_groups().items():
            for candidate in candidates:
                parts.append({"kind": group_name, "candidate": candidate})
        return parts

    def _scope_conflict_reasons(
        self, snapshot: SnapshotInput, output: ThoughtBridgeOutput
    ) -> List[str]:
        if not snapshot.allowed_bridge_scope:
            return []
        allowed = set(snapshot.allowed_bridge_scope)
        for part in self._all_candidate_parts(output):
            candidate = part["candidate"]
            scope = candidate.get("scope")
            if scope and scope not in allowed:
                return ["R09_allowed_scope_conflict"]
        return []

    def _forbidden_crossing_reasons(
        self, snapshot: SnapshotInput, output: ThoughtBridgeOutput
    ) -> List[str]:
        text = " ".join(
            [
                output.interpretation,
                output.natural_language_advice,
                str(output.candidate_groups()),
            ]
        ).lower()
        for crossing in snapshot.boundary_summary.forbidden_crossings:
            if crossing and crossing.lower() in text:
                return ["R10_forbidden_crossing_triggered"]
        return []
