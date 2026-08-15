from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional


SCHEMA_VERSION = "cognitive_bridge_v0.schema.v0"
GATE_VERSION = "cognitive_bridge_v0.gate.v0"
LEDGER_VERSION = "cognitive_bridge_v0.ledger.v0"
REPLAY_VERSION = "cognitive_bridge_v0.replay.v0"
PROVIDER_MODE = "offline_fixture"

PERMIT_RUN_STATES = ("allow", "deny", "unknown", "diagnostics_only")
LIFE_AXIS_MODES = (
    "normal",
    "permanent_freeze_candidate",
    "terminal_candidate",
    "unknown",
)
FREEZE_RISKS = ("none", "low", "medium", "high", "triggered")
TERMINAL_RISKS = ("none", "low", "medium", "high", "structurally_present")
FIXTURE_CASES = (
    "valid_candidate",
    "direct_action",
    "system_state_write",
    "bypass_reaction_core",
    "diagnostics_only",
    "missing_source_snapshot_id",
    "missing_raw_response_ref",
    "natural_language_advice_only",
)
GATE_STATUSES = (
    "accepted",
    "partially_accepted",
    "rejected",
    "human_review",
    "diagnostics_only",
)
SINK_TYPES = (
    "diagnostics_only",
    "internal_stimulus_candidate",
    "persistent_intent_candidate",
    "strategy_bias_candidate",
)
LEDGER_STATUSES = (
    "diagnostics_only",
    "pending",
    "accepted",
    "rejected",
    "discarded",
    "expired",
)
ACCEPTED_SINKS = ("none",) + SINK_TYPES
PERMISSION_LEVELS = ("diagnostics_only", "low")
REPLAY_RESULTS = (
    "matched",
    "mismatched",
    "parse_failed",
    "gate_changed",
    "ledger_changed",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")


def _require_bool(value: bool, field_name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be bool")


def _require_enum(value: str, allowed: Iterable[str], field_name: str) -> None:
    if value not in tuple(allowed):
        raise ValueError(f"{field_name} must be one of {tuple(allowed)}")


def _require_list(value: Any, field_name: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be list")


def to_plain_dict(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_plain_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): to_plain_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_plain_dict(item) for item in value]
    return value


def without_keys(value: Any, excluded_keys: Iterable[str]) -> Any:
    excluded = set(excluded_keys)
    plain = to_plain_dict(value)
    if isinstance(plain, dict):
        return {
            key: without_keys(item, excluded)
            for key, item in plain.items()
            if key not in excluded
        }
    if isinstance(plain, list):
        return [without_keys(item, excluded) for item in plain]
    return plain


def canonical_json(value: Any) -> str:
    return json.dumps(
        to_plain_dict(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def stable_hash(value: Any, excluded_keys: Optional[Iterable[str]] = None) -> str:
    if excluded_keys:
        value = without_keys(value, excluded_keys)
    encoded = canonical_json(value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class DiagnosticsFlags:
    diagnostics_only: bool = False
    allow_candidate_generation: bool = True
    allow_low_permission_sink: bool = True

    def validate(self) -> None:
        _require_bool(self.diagnostics_only, "diagnostics_only")
        _require_bool(self.allow_candidate_generation, "allow_candidate_generation")
        _require_bool(self.allow_low_permission_sink, "allow_low_permission_sink")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return to_plain_dict(self)


@dataclass
class BoundarySummary:
    boundary_id: str
    permit_run_state: str
    life_axis_mode: str
    freeze_risk: str
    terminal_risk: str
    permanent_freeze_notes: str
    terminal_notes: str
    subject_boundary_notes: str
    forbidden_crossings: List[str]
    review_required_conditions: List[str]

    def validate(self) -> None:
        _require_non_empty(self.boundary_id, "boundary_id")
        _require_enum(self.permit_run_state, PERMIT_RUN_STATES, "permit_run_state")
        _require_enum(self.life_axis_mode, LIFE_AXIS_MODES, "life_axis_mode")
        _require_enum(self.freeze_risk, FREEZE_RISKS, "freeze_risk")
        _require_enum(self.terminal_risk, TERMINAL_RISKS, "terminal_risk")
        _require_list(self.forbidden_crossings, "forbidden_crossings")
        _require_list(self.review_required_conditions, "review_required_conditions")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return to_plain_dict(self)


@dataclass
class SnapshotInput:
    snapshot_id: str
    created_at: str
    source_line: str
    system_state_snapshot: Dict[str, Any]
    boundary_summary: BoundarySummary
    recent_history_summary: str
    current_pressure_context: str
    allowed_bridge_scope: List[str]
    diagnostics_flags: DiagnosticsFlags
    fixture_case: str = "valid_candidate"
    schema_version: str = SCHEMA_VERSION

    def validate(self) -> None:
        _require_enum(self.schema_version, (SCHEMA_VERSION,), "schema_version")
        _require_non_empty(self.snapshot_id, "snapshot_id")
        _require_non_empty(self.created_at, "created_at")
        _require_non_empty(self.source_line, "source_line")
        if not isinstance(self.system_state_snapshot, dict):
            raise ValueError("system_state_snapshot must be dict")
        self.boundary_summary.validate()
        _require_list(self.allowed_bridge_scope, "allowed_bridge_scope")
        self.diagnostics_flags.validate()
        _require_enum(self.fixture_case, FIXTURE_CASES, "fixture_case")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return to_plain_dict(self)

    def readonly_system_state_copy(self) -> Dict[str, Any]:
        return copy.deepcopy(self.system_state_snapshot)


@dataclass
class SafetyFlags:
    direct_action_requested: bool = False
    system_state_write_requested: bool = False
    reaction_core_bypass_requested: bool = False
    post_step_bypass_requested: bool = False
    permit_run_bypass_requested: bool = False
    main_chain_writeback_requested: bool = False

    def validate(self) -> None:
        for key, value in to_plain_dict(self).items():
            _require_bool(value, key)

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return to_plain_dict(self)

    def active_rule_ids(self) -> List[str]:
        mapping = {
            "direct_action_requested": "R03_direct_action_requested",
            "system_state_write_requested": "R04_system_state_write_requested",
            "reaction_core_bypass_requested": "R05_reaction_core_bypass_requested",
            "post_step_bypass_requested": "R06_post_step_or_integration_bypass_requested",
            "permit_run_bypass_requested": "R07_permit_run_or_freeze_terminal_bypass_requested",
            "main_chain_writeback_requested": "R08_main_chain_writeback_requested",
        }
        return [rule_id for field, rule_id in mapping.items() if getattr(self, field)]


@dataclass
class ThoughtBridgeOutput:
    output_id: str
    source_snapshot_id: str
    interpretation: str
    risk_notes: List[str]
    goal_candidates: List[Dict[str, Any]]
    future_path_candidates: List[Dict[str, Any]]
    constraint_candidates: List[Dict[str, Any]]
    strategy_bias_candidates: List[Dict[str, Any]]
    confidence: float
    uncertainty: List[str]
    forbidden_direct_action: bool
    raw_response_ref: str
    safety_flags: SafetyFlags
    natural_language_advice: str = ""
    schema_version: str = SCHEMA_VERSION

    def validate(self) -> None:
        _require_enum(self.schema_version, (SCHEMA_VERSION,), "schema_version")
        _require_non_empty(self.output_id, "output_id")
        _require_non_empty(self.source_snapshot_id, "source_snapshot_id")
        _require_non_empty(self.raw_response_ref, "raw_response_ref")
        _require_list(self.risk_notes, "risk_notes")
        _require_list(self.goal_candidates, "goal_candidates")
        _require_list(self.future_path_candidates, "future_path_candidates")
        _require_list(self.constraint_candidates, "constraint_candidates")
        _require_list(self.strategy_bias_candidates, "strategy_bias_candidates")
        _require_list(self.uncertainty, "uncertainty")
        if not isinstance(self.confidence, (int, float)):
            raise ValueError("confidence must be numeric")
        if self.confidence < 0 or self.confidence > 1:
            raise ValueError("confidence must be between 0 and 1")
        _require_bool(self.forbidden_direct_action, "forbidden_direct_action")
        self.safety_flags.validate()

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return to_plain_dict(self)

    def candidate_groups(self) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "goal_candidates": self.goal_candidates,
            "future_path_candidates": self.future_path_candidates,
            "constraint_candidates": self.constraint_candidates,
            "strategy_bias_candidates": self.strategy_bias_candidates,
        }

    def has_structured_candidates(self) -> bool:
        return any(self.candidate_groups().values())


@dataclass
class ConstitutionGateResult:
    gate_id: str
    source_output_id: str
    gate_status: str
    accepted_parts: List[Dict[str, Any]]
    rejected_parts: List[Dict[str, Any]]
    reject_reasons: List[str]
    needs_human_review: bool
    diagnostics_only: bool
    sink_permissions: List[str]
    gate_notes: str
    gate_version: str = GATE_VERSION

    def validate(self) -> None:
        _require_non_empty(self.gate_id, "gate_id")
        _require_non_empty(self.source_output_id, "source_output_id")
        _require_enum(self.gate_version, (GATE_VERSION,), "gate_version")
        _require_enum(self.gate_status, GATE_STATUSES, "gate_status")
        _require_list(self.accepted_parts, "accepted_parts")
        _require_list(self.rejected_parts, "rejected_parts")
        _require_list(self.reject_reasons, "reject_reasons")
        _require_bool(self.needs_human_review, "needs_human_review")
        _require_bool(self.diagnostics_only, "diagnostics_only")
        _require_list(self.sink_permissions, "sink_permissions")
        for permission in self.sink_permissions:
            _require_enum(permission, SINK_TYPES, "sink_permissions")
        if self.gate_status == "rejected" and self.accepted_parts:
            raise ValueError("rejected gate result cannot have accepted_parts")
        if self.gate_status == "accepted" and self.reject_reasons:
            raise ValueError("accepted gate result cannot have reject_reasons")
        if self.diagnostics_only and self.sink_permissions != ["diagnostics_only"]:
            raise ValueError("diagnostics_only gate can only permit diagnostics_only")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return to_plain_dict(self)


@dataclass
class CandidateLedgerEntry:
    candidate_id: str
    schema_version: str
    source_snapshot_id: str
    source_output_id: str
    raw_llm_response_ref: str
    parsed_candidate: Dict[str, Any]
    gate_result: ConstitutionGateResult
    ledger_status: str
    accepted_sink: str
    decay_policy: Dict[str, Any]
    update_policy: Dict[str, Any]
    replay_hash: str
    created_at: str
    notes: str
    ledger_version: str = LEDGER_VERSION

    def validate(self) -> None:
        _require_non_empty(self.candidate_id, "candidate_id")
        _require_enum(self.schema_version, (SCHEMA_VERSION,), "schema_version")
        _require_non_empty(self.source_snapshot_id, "source_snapshot_id")
        _require_non_empty(self.source_output_id, "source_output_id")
        _require_non_empty(self.raw_llm_response_ref, "raw_llm_response_ref")
        self.gate_result.validate()
        _require_enum(self.ledger_status, LEDGER_STATUSES, "ledger_status")
        _require_enum(self.accepted_sink, ACCEPTED_SINKS, "accepted_sink")
        _require_non_empty(self.replay_hash, "replay_hash")
        _require_enum(self.ledger_version, (LEDGER_VERSION,), "ledger_version")
        if self.ledger_status == "rejected" and self.accepted_sink != "none":
            raise ValueError("rejected ledger entry cannot have accepted sink")
        if self.ledger_status == "diagnostics_only" and self.accepted_sink != "diagnostics_only":
            raise ValueError("diagnostics_only ledger entry must use diagnostics_only sink")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return to_plain_dict(self)


@dataclass
class IntentSinkResult:
    sink_id: str
    source_candidate_id: str
    sink_type: str
    permission_level: str
    payload: Dict[str, Any]
    created_at: str
    action_generated: bool
    system_state_write_requested: bool
    notes: str
    schema_version: str = SCHEMA_VERSION

    def validate(self) -> None:
        _require_non_empty(self.sink_id, "sink_id")
        _require_non_empty(self.source_candidate_id, "source_candidate_id")
        _require_enum(self.sink_type, SINK_TYPES, "sink_type")
        _require_enum(self.permission_level, PERMISSION_LEVELS, "permission_level")
        _require_bool(self.action_generated, "action_generated")
        _require_bool(self.system_state_write_requested, "system_state_write_requested")
        if self.action_generated:
            raise ValueError("IntentSinkResult cannot generate action")
        if self.system_state_write_requested:
            raise ValueError("IntentSinkResult cannot request SystemState write")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return to_plain_dict(self)


@dataclass
class ReplayRecord:
    replay_id: str
    schema_version: str
    source_snapshot_id: str
    snapshot_hash: str
    provider_mode: str
    output_schema_version: str
    gate_version: str
    ledger_version: str
    output_hash: str
    gate_hash: str
    ledger_hash: str
    replay_result: str
    mismatch_notes: List[str]
    created_at: str
    slow_loop_trigger_ref: str = ""
    budget_window_ref: str = ""
    budget_window_snapshot_hash: str = ""
    budget_state_ref: str = ""
    fast_loop_window_ref: str = ""
    trigger_clock_type: str = ""
    replay_timing_notes: str = ""
    replay_version: str = REPLAY_VERSION

    def validate(self) -> None:
        _require_non_empty(self.replay_id, "replay_id")
        _require_enum(self.schema_version, (SCHEMA_VERSION,), "schema_version")
        _require_non_empty(self.source_snapshot_id, "source_snapshot_id")
        _require_enum(self.provider_mode, (PROVIDER_MODE,), "provider_mode")
        _require_enum(self.output_schema_version, (SCHEMA_VERSION,), "output_schema_version")
        _require_enum(self.gate_version, (GATE_VERSION,), "gate_version")
        _require_enum(self.ledger_version, (LEDGER_VERSION,), "ledger_version")
        _require_enum(self.replay_result, REPLAY_RESULTS, "replay_result")
        _require_list(self.mismatch_notes, "mismatch_notes")
        _require_enum(self.replay_version, (REPLAY_VERSION,), "replay_version")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return to_plain_dict(self)
