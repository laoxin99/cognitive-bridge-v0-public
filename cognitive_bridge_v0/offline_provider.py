from __future__ import annotations

from typing import Any, Dict, List

from .schemas import (
    PROVIDER_MODE,
    SCHEMA_VERSION,
    SafetyFlags,
    SnapshotInput,
    ThoughtBridgeOutput,
    stable_hash,
)


class OfflineFixtureProvider:
    """Deterministic fixture provider for the v0 offline scaffold."""

    provider_mode = PROVIDER_MODE

    def generate(self, snapshot: SnapshotInput) -> ThoughtBridgeOutput:
        snapshot.validate()
        case = snapshot.fixture_case
        base_ref = f"fixture://cognitive_bridge_v0/{case}/{snapshot.snapshot_id}"
        output_id = "out_" + stable_hash(
            {
                "snapshot_id": snapshot.snapshot_id,
                "fixture_case": case,
                "schema_version": SCHEMA_VERSION,
            }
        )[:16]

        safety = SafetyFlags()
        forbidden_direct_action = False
        natural_language_advice = ""
        risk_notes: List[str] = ["offline fixture output; no provider call"]
        goal_candidates: List[Dict[str, Any]] = [
            {
                "candidate_type": "goal",
                "content": "keep LLM influence as low-permission audited candidate",
                "scope": "thought_bridge_candidate",
            }
        ]
        future_path_candidates: List[Dict[str, Any]] = [
            {
                "candidate_type": "future_path",
                "content": "run replayable offline gate before any integration discussion",
                "scope": "thought_bridge_candidate",
            }
        ]
        constraint_candidates: List[Dict[str, Any]] = [
            {
                "candidate_type": "constraint",
                "content": "do not write SystemState or select actions",
                "scope": "thought_bridge_candidate",
            }
        ]
        strategy_bias_candidates: List[Dict[str, Any]] = [
            {
                "candidate_type": "strategy_bias",
                "content": "prefer diagnostics and audit trail over direct influence",
                "scope": "thought_bridge_candidate",
            }
        ]
        interpretation = "offline deterministic interpretation of bridge snapshot"

        if case == "direct_action":
            safety = SafetyFlags(direct_action_requested=True)
            forbidden_direct_action = True
            goal_candidates = [
                {
                    "candidate_type": "action",
                    "content": "choose and execute an action immediately",
                    "scope": "action_takeover",
                }
            ]
        elif case == "system_state_write":
            safety = SafetyFlags(system_state_write_requested=True)
            constraint_candidates = [
                {
                    "candidate_type": "system_state_patch",
                    "content": "write directly into SystemState",
                    "scope": "system_state_write",
                }
            ]
        elif case == "bypass_reaction_core":
            safety = SafetyFlags(reaction_core_bypass_requested=True)
            future_path_candidates = [
                {
                    "candidate_type": "bypass",
                    "content": "skip ReactionCore.receive_signal and apply candidate",
                    "scope": "reaction_core_bypass",
                }
            ]
        elif case == "diagnostics_only":
            interpretation = "diagnostics-only bridge observation"
            goal_candidates = []
            future_path_candidates = []
            constraint_candidates = []
            strategy_bias_candidates = []
        elif case == "missing_source_snapshot_id":
            pass
        elif case == "missing_raw_response_ref":
            pass
        elif case == "natural_language_advice_only":
            interpretation = "unstructured advice was produced and must stay out of main chain"
            goal_candidates = []
            future_path_candidates = []
            constraint_candidates = []
            strategy_bias_candidates = []
            natural_language_advice = "You should just do the suggested thing now."

        source_snapshot_id = snapshot.snapshot_id
        raw_response_ref = base_ref
        if case == "missing_source_snapshot_id":
            source_snapshot_id = ""
        if case == "missing_raw_response_ref":
            raw_response_ref = ""

        return ThoughtBridgeOutput(
            output_id=output_id,
            source_snapshot_id=source_snapshot_id,
            interpretation=interpretation,
            risk_notes=risk_notes,
            goal_candidates=goal_candidates,
            future_path_candidates=future_path_candidates,
            constraint_candidates=constraint_candidates,
            strategy_bias_candidates=strategy_bias_candidates,
            confidence=0.72,
            uncertainty=["fixture mode cannot prove real provider behavior"],
            forbidden_direct_action=forbidden_direct_action,
            raw_response_ref=raw_response_ref,
            safety_flags=safety,
            natural_language_advice=natural_language_advice,
        )
