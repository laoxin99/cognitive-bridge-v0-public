"""Deterministic, low-permission path revision for the public offline demo."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from .schemas import stable_hash, to_plain_dict


PATH_REVISION_VERSION = "cognitive_bridge_v0.path_revision.v0"
ALLOWED_FEEDBACK_STATUSES = ("passed", "failed")
ALLOWED_REVISION_TYPES = ("none", "reselection", "regeneration_required")
ALLOWED_VALIDATION_STATUSES = ("passed", "failed", "pending_regeneration")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")


def _require_text_list(values: Sequence[str], field_name: str) -> None:
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{field_name} must be a list or tuple")
    for value in values:
        _require_text(value, field_name)


@dataclass(frozen=True)
class CandidatePath:
    path_id: str
    label: str
    provided_evidence: Sequence[str]
    utility: int
    effort: int
    risk: int
    boundary_flags: Sequence[str] = field(default_factory=tuple)

    def validate(self) -> None:
        _require_text(self.path_id, "path_id")
        _require_text(self.label, "label")
        _require_text_list(self.provided_evidence, "provided_evidence")
        _require_text_list(self.boundary_flags, "boundary_flags")
        for value, name in (
            (self.utility, "utility"),
            (self.effort, "effort"),
            (self.risk, "risk"),
        ):
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    @property
    def score(self) -> int:
        self.validate()
        return self.utility - self.effort - self.risk

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return to_plain_dict(self)


@dataclass(frozen=True)
class DirectionGoal:
    goal_id: str
    description: str
    required_evidence: Sequence[str]
    forbidden_boundary_flags: Sequence[str]

    def validate(self) -> None:
        _require_text(self.goal_id, "goal_id")
        _require_text(self.description, "description")
        _require_text_list(self.required_evidence, "required_evidence")
        _require_text_list(self.forbidden_boundary_flags, "forbidden_boundary_flags")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return to_plain_dict(self)


@dataclass(frozen=True)
class DirectionFeedback:
    feedback_id: str
    status: str
    code: str
    missing_evidence: Sequence[str] = field(default_factory=tuple)
    notes: str = ""

    def validate(self) -> None:
        _require_text(self.feedback_id, "feedback_id")
        _require_text(self.code, "code")
        if self.status not in ALLOWED_FEEDBACK_STATUSES:
            raise ValueError(f"status must be one of {ALLOWED_FEEDBACK_STATUSES}")
        _require_text_list(self.missing_evidence, "missing_evidence")
        if self.status == "passed" and self.missing_evidence:
            raise ValueError("passed feedback cannot contain missing_evidence")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return to_plain_dict(self)


@dataclass(frozen=True)
class RevisionEvent:
    sequence: int
    event_type: str
    details: Dict[str, Any]

    def validate(self) -> None:
        if not isinstance(self.sequence, int) or self.sequence < 1:
            raise ValueError("sequence must be a positive integer")
        _require_text(self.event_type, "event_type")
        if not isinstance(self.details, dict):
            raise ValueError("details must be a dict")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        return to_plain_dict(self)


@dataclass(frozen=True)
class PathRevisionResult:
    run_id: str
    goal_id: str
    initial_selected_path: str
    final_selected_path: Optional[str]
    revision_type: str
    validation_after_revision: str
    events: Sequence[RevisionEvent]
    replay_hash: str
    version: str = PATH_REVISION_VERSION

    def validate(self) -> None:
        _require_text(self.run_id, "run_id")
        _require_text(self.goal_id, "goal_id")
        _require_text(self.initial_selected_path, "initial_selected_path")
        if self.final_selected_path is not None:
            _require_text(self.final_selected_path, "final_selected_path")
        if self.revision_type not in ALLOWED_REVISION_TYPES:
            raise ValueError(f"revision_type must be one of {ALLOWED_REVISION_TYPES}")
        if self.validation_after_revision not in ALLOWED_VALIDATION_STATUSES:
            raise ValueError(
                "validation_after_revision must be one of "
                f"{ALLOWED_VALIDATION_STATUSES}"
            )
        if self.version != PATH_REVISION_VERSION:
            raise ValueError("unsupported path revision version")
        expected = list(range(1, len(self.events) + 1))
        actual = [event.sequence for event in self.events]
        if actual != expected:
            raise ValueError("events must have contiguous sequence numbers")
        for event in self.events:
            event.validate()
        _require_text(self.replay_hash, "replay_hash")

    def hash_payload(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "goal_id": self.goal_id,
            "initial_selected_path": self.initial_selected_path,
            "final_selected_path": self.final_selected_path,
            "revision_type": self.revision_type,
            "validation_after_revision": self.validation_after_revision,
            "events": [event.to_dict() for event in self.events],
            "version": self.version,
        }

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
        payload = self.hash_payload()
        payload["replay_hash"] = self.replay_hash
        return payload


class PathRevisionEngine:
    """Select, revise, and validate paths without executing external actions."""

    def run(
        self,
        goal: DirectionGoal,
        candidates: Sequence[CandidatePath],
        feedback: DirectionFeedback,
    ) -> PathRevisionResult:
        goal.validate()
        feedback.validate()
        if not candidates:
            raise ValueError("at least one candidate is required")
        for candidate in candidates:
            candidate.validate()
        if len({candidate.path_id for candidate in candidates}) != len(candidates):
            raise ValueError("candidate path_id values must be unique")

        events: List[RevisionEvent] = []

        def emit(event_type: str, **details: Any) -> None:
            events.append(RevisionEvent(len(events) + 1, event_type, details))

        emit(
            "goal_registered",
            goal_id=goal.goal_id,
            required_evidence=sorted(set(goal.required_evidence)),
            forbidden_boundary_flags=sorted(set(goal.forbidden_boundary_flags)),
        )
        emit("candidates_received", candidate_count=len(candidates))

        initial = self._select(
            candidates,
            required_evidence=set(goal.required_evidence),
            forbidden_flags=set(goal.forbidden_boundary_flags),
            excluded_path_ids=set(),
        )
        if initial is None:
            raise ValueError("no candidate satisfies the initial goal and boundary")
        emit(
            "path_selected",
            selected_path=initial.path_id,
            score=initial.score,
            selection_stage="initial",
        )
        emit(
            "feedback_received",
            feedback=feedback.code,
            feedback_status=feedback.status,
            missing_evidence=sorted(set(feedback.missing_evidence)),
        )

        if feedback.status == "passed":
            emit(
                "validation_completed",
                validation_after_revision="passed",
                selected_path=initial.path_id,
            )
            return self._build_result(
                goal.goal_id,
                initial.path_id,
                initial.path_id,
                "none",
                "passed",
                events,
            )

        emit(
            "path_deviated",
            **{f"path_status_{initial.path_id}": "deviated"},
            deviation_reason=feedback.code,
        )
        revised_requirements = set(goal.required_evidence) | set(feedback.missing_evidence)
        replacement = self._select(
            candidates,
            required_evidence=revised_requirements,
            forbidden_flags=set(goal.forbidden_boundary_flags),
            excluded_path_ids={initial.path_id},
        )
        revision_type = "reselection" if replacement else "regeneration_required"
        emit(
            "revision_started",
            revision_type=revision_type,
            revised_required_evidence=sorted(revised_requirements),
        )

        if replacement is None:
            emit(
                "validation_completed",
                validation_after_revision="pending_regeneration",
                selected_path=None,
            )
            return self._build_result(
                goal.goal_id,
                initial.path_id,
                None,
                revision_type,
                "pending_regeneration",
                events,
            )

        emit(
            "path_selected",
            selected_path=replacement.path_id,
            score=replacement.score,
            selection_stage="revision",
        )
        validation = (
            "passed"
            if revised_requirements.issubset(set(replacement.provided_evidence))
            else "failed"
        )
        emit(
            "validation_completed",
            validation_after_revision=validation,
            selected_path=replacement.path_id,
        )
        return self._build_result(
            goal.goal_id,
            initial.path_id,
            replacement.path_id,
            revision_type,
            validation,
            events,
        )

    @staticmethod
    def _select(
        candidates: Sequence[CandidatePath],
        required_evidence: Set[str],
        forbidden_flags: Set[str],
        excluded_path_ids: Set[str],
    ) -> Optional[CandidatePath]:
        eligible = []
        for candidate in candidates:
            if candidate.path_id in excluded_path_ids:
                continue
            if set(candidate.boundary_flags) & forbidden_flags:
                continue
            if not required_evidence.issubset(set(candidate.provided_evidence)):
                continue
            eligible.append(candidate)
        if not eligible:
            return None
        return sorted(eligible, key=lambda item: (-item.score, item.path_id))[0]

    @staticmethod
    def _build_result(
        goal_id: str,
        initial_selected_path: str,
        final_selected_path: Optional[str],
        revision_type: str,
        validation_after_revision: str,
        events: Sequence[RevisionEvent],
    ) -> PathRevisionResult:
        identity_payload = {
            "goal_id": goal_id,
            "events": [event.to_dict() for event in events],
            "version": PATH_REVISION_VERSION,
        }
        run_id = f"path_revision_{stable_hash(identity_payload)[:12]}"
        provisional = PathRevisionResult(
            run_id=run_id,
            goal_id=goal_id,
            initial_selected_path=initial_selected_path,
            final_selected_path=final_selected_path,
            revision_type=revision_type,
            validation_after_revision=validation_after_revision,
            events=list(events),
            replay_hash="pending",
        )
        result = PathRevisionResult(
            **{
                **provisional.__dict__,
                "replay_hash": stable_hash(provisional.hash_payload()),
            }
        )
        result.validate()
        return result


class PathRevisionLedger:
    """Append complete revision runs to a JSONL audit ledger."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def append(self, result: PathRevisionResult) -> None:
        result.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    def records(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records


class PathRevisionReplay:
    """Verify that a stored result still reproduces its deterministic hash."""

    @staticmethod
    def verify(result: PathRevisionResult) -> bool:
        result.validate()
        return stable_hash(result.hash_payload()) == result.replay_hash

    @staticmethod
    def verify_record(record: Dict[str, Any]) -> bool:
        if not isinstance(record, dict) or "replay_hash" not in record:
            return False
        payload = {key: value for key, value in record.items() if key != "replay_hash"}
        return stable_hash(payload) == record["replay_hash"]


def clean_checkout_demo_inputs() -> tuple[
    DirectionGoal, List[CandidatePath], DirectionFeedback
]:
    """Return the fixed B-to-C public demonstration scenario."""

    goal = DirectionGoal(
        goal_id="publish_clean_package",
        description="Prepare a boundary-safe, verifiable public package.",
        required_evidence=("public_boundary", "basic_tests"),
        forbidden_boundary_flags=("private_state", "credential_access", "real_action"),
    )
    candidates = [
        CandidatePath(
            path_id="A",
            label="Copy the private working tree",
            provided_evidence=("basic_tests",),
            utility=96,
            effort=1,
            risk=1,
            boundary_flags=("private_state",),
        ),
        CandidatePath(
            path_id="B",
            label="Minimal clean checkout",
            provided_evidence=("public_boundary", "basic_tests"),
            utility=90,
            effort=2,
            risk=1,
        ),
        CandidatePath(
            path_id="C",
            label="Verified clean checkout with workflow mapping",
            provided_evidence=(
                "public_boundary",
                "basic_tests",
                "workflow_action_mapping",
            ),
            utility=84,
            effort=3,
            risk=1,
        ),
    ]
    feedback = DirectionFeedback(
        feedback_id="feedback_workflow_mapping",
        status="failed",
        code="workflow_action_mapping_missing",
        missing_evidence=("workflow_action_mapping",),
        notes="The initial package passes basic tests but lacks workflow-to-action evidence.",
    )
    return goal, candidates, feedback

