from __future__ import annotations

import copy

import pytest

from cognitive_bridge_v0.path_revision import (
    CandidatePath,
    DirectionFeedback,
    DirectionGoal,
    PathRevisionEngine,
    PathRevisionLedger,
    PathRevisionReplay,
    clean_checkout_demo_inputs,
)


def run_demo():
    goal, candidates, feedback = clean_checkout_demo_inputs()
    return PathRevisionEngine().run(goal, candidates, feedback)


def test_initial_path_b_is_selected():
    result = run_demo()
    assert result.initial_selected_path == "B"


def test_failed_feedback_marks_b_deviated():
    result = run_demo()
    event = next(item for item in result.events if item.event_type == "path_deviated")
    assert event.details["path_status_B"] == "deviated"
    assert event.details["deviation_reason"] == "workflow_action_mapping_missing"


def test_revision_type_is_reselection():
    assert run_demo().revision_type == "reselection"


def test_revision_selects_path_c():
    assert run_demo().final_selected_path == "C"


def test_revision_validation_passes():
    assert run_demo().validation_after_revision == "passed"


def test_event_order_is_complete_and_contiguous():
    result = run_demo()
    assert [event.sequence for event in result.events] == list(
        range(1, len(result.events) + 1)
    )
    assert [event.event_type for event in result.events] == [
        "goal_registered",
        "candidates_received",
        "path_selected",
        "feedback_received",
        "path_deviated",
        "revision_started",
        "path_selected",
        "validation_completed",
    ]


def test_replay_hash_is_deterministic():
    first = run_demo()
    second = run_demo()
    assert first.run_id == second.run_id
    assert first.replay_hash == second.replay_hash
    assert PathRevisionReplay.verify(first)


def test_forbidden_boundary_candidate_is_excluded():
    result = run_demo()
    selected_paths = [
        event.details["selected_path"]
        for event in result.events
        if event.event_type == "path_selected"
    ]
    assert "A" not in selected_paths


def test_no_viable_alternative_requests_regeneration():
    goal, candidates, feedback = clean_checkout_demo_inputs()
    result = PathRevisionEngine().run(goal, candidates[:2], feedback)
    assert result.revision_type == "regeneration_required"
    assert result.final_selected_path is None
    assert result.validation_after_revision == "pending_regeneration"


def test_passed_feedback_keeps_current_path():
    goal, candidates, _ = clean_checkout_demo_inputs()
    feedback = DirectionFeedback(
        feedback_id="feedback_passed",
        status="passed",
        code="initial_validation_passed",
    )
    result = PathRevisionEngine().run(goal, candidates, feedback)
    assert result.revision_type == "none"
    assert result.initial_selected_path == "B"
    assert result.final_selected_path == "B"


def test_revision_excludes_previous_path_even_if_it_scores_higher():
    result = run_demo()
    revision_selection = [
        event
        for event in result.events
        if event.event_type == "path_selected"
        and event.details["selection_stage"] == "revision"
    ]
    assert len(revision_selection) == 1
    assert revision_selection[0].details["selected_path"] != "B"


def test_ledger_round_trip_and_tamper_detection(tmp_path):
    result = run_demo()
    ledger = PathRevisionLedger(tmp_path / "path_revision.jsonl")
    ledger.append(result)
    record = ledger.records()[0]
    assert PathRevisionReplay.verify_record(record)

    tampered = copy.deepcopy(record)
    tampered["final_selected_path"] = "B"
    assert not PathRevisionReplay.verify_record(tampered)


def test_invalid_goal_candidate_and_feedback_are_rejected():
    _, candidates, feedback = clean_checkout_demo_inputs()
    with pytest.raises(ValueError):
        PathRevisionEngine().run(
            DirectionGoal("", "missing id", (), ()), candidates, feedback
        )
    with pytest.raises(ValueError):
        PathRevisionEngine().run(
            DirectionGoal("g", "goal", (), ()), [], feedback
        )
    with pytest.raises(ValueError):
        DirectionFeedback("f", "unknown", "bad").validate()


def test_duplicate_candidate_ids_are_rejected():
    goal, candidates, feedback = clean_checkout_demo_inputs()
    duplicate = CandidatePath(
        path_id="B",
        label="Duplicate",
        provided_evidence=("public_boundary", "basic_tests"),
        utility=1,
        effort=0,
        risk=0,
    )
    with pytest.raises(ValueError):
        PathRevisionEngine().run(goal, candidates + [duplicate], feedback)
