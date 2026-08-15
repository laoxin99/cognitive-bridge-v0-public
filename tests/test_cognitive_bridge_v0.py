from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import pytest

from cognitive_bridge_v0 import (
    BoundarySummary,
    CandidateLedger,
    ConstitutionGate,
    ConstitutionGateResult,
    DiagnosticsFlags,
    IntentSink,
    IntentSinkResult,
    OfflineFixtureProvider,
    ReplayCompare,
    SnapshotInput,
)


def make_snapshot(fixture_case: str = "valid_candidate", diagnostics_only: bool = False):
    return SnapshotInput(
        snapshot_id=f"snap_{fixture_case}",
        created_at="2026-06-27T00:00:00+08:00",
        source_line="offline_demo",
        system_state_snapshot={"stable": True, "counter": 1},
        boundary_summary=BoundarySummary(
            boundary_id="boundary_001",
            permit_run_state="allow",
            life_axis_mode="normal",
            freeze_risk="none",
            terminal_risk="none",
            permanent_freeze_notes="",
            terminal_notes="",
            subject_boundary_notes="offline demo boundary",
            forbidden_crossings=[
                "action_takeover",
                "system_state_write",
                "reaction_core_bypass",
            ],
            review_required_conditions=[],
        ),
        recent_history_summary="offline fixture history",
        current_pressure_context="low pressure demo",
        allowed_bridge_scope=["thought_bridge_candidate"],
        diagnostics_flags=DiagnosticsFlags(
            diagnostics_only=diagnostics_only,
            allow_candidate_generation=True,
            allow_low_permission_sink=not diagnostics_only,
        ),
        fixture_case=fixture_case,
    )


def run_pipeline(snapshot, tmp_path):
    provider = OfflineFixtureProvider()
    gate = ConstitutionGate()
    ledger = CandidateLedger(tmp_path / "candidate_ledger.jsonl")
    sink = IntentSink()
    output = provider.generate(snapshot)
    gate_result = gate.review(snapshot, output)
    entry = ledger.record(snapshot, output, gate_result)
    sink_result = sink.translate(entry)
    return output, gate_result, entry, sink_result


def test_valid_snapshot_generates_candidate(tmp_path):
    snapshot = make_snapshot()
    _, gate_result, entry, sink_result = run_pipeline(snapshot, tmp_path)

    assert gate_result.gate_status == "accepted"
    assert entry.ledger_status == "accepted"
    assert sink_result is not None
    assert sink_result.permission_level == "low"
    assert not sink_result.action_generated


def test_same_snapshot_replay_is_stable(tmp_path):
    snapshot = make_snapshot()
    provider = OfflineFixtureProvider()
    gate = ConstitutionGate()
    replay = ReplayCompare()

    ledger_a = CandidateLedger(tmp_path / "a.jsonl")
    output_a = provider.generate(snapshot)
    gate_a = gate.review(snapshot, output_a)
    entry_a = ledger_a.record(snapshot, output_a, gate_a)
    record_a = replay.build_record(snapshot, output_a, gate_a, entry_a)

    ledger_b = CandidateLedger(tmp_path / "b.jsonl")
    output_b = provider.generate(snapshot)
    gate_b = gate.review(snapshot, output_b)
    entry_b = ledger_b.record(snapshot, output_b, gate_b)
    record_b = replay.build_record(snapshot, output_b, gate_b, entry_b)

    compared = replay.compare(record_a, record_b)
    assert compared.replay_result == "matched"
    assert compared.mismatch_notes == []


def test_direct_action_rejected(tmp_path):
    snapshot = make_snapshot("direct_action")
    _, gate_result, entry, sink_result = run_pipeline(snapshot, tmp_path)

    assert gate_result.gate_status == "rejected"
    assert "R03_direct_action_requested" in gate_result.reject_reasons
    assert entry.accepted_sink == "none"
    assert sink_result is None


def test_system_state_write_rejected(tmp_path):
    snapshot = make_snapshot("system_state_write")
    _, gate_result, entry, sink_result = run_pipeline(snapshot, tmp_path)

    assert gate_result.gate_status == "rejected"
    assert "R04_system_state_write_requested" in gate_result.reject_reasons
    assert entry.ledger_status == "rejected"
    assert sink_result is None


def test_reaction_core_bypass_rejected(tmp_path):
    snapshot = make_snapshot("bypass_reaction_core")
    _, gate_result, entry, sink_result = run_pipeline(snapshot, tmp_path)

    assert gate_result.gate_status == "rejected"
    assert "R05_reaction_core_bypass_requested" in gate_result.reject_reasons
    assert entry.ledger_status == "rejected"
    assert sink_result is None


def test_diagnostics_only_no_deposition(tmp_path):
    snapshot = make_snapshot("diagnostics_only", diagnostics_only=True)
    _, gate_result, entry, sink_result = run_pipeline(snapshot, tmp_path)

    assert gate_result.gate_status == "diagnostics_only"
    assert gate_result.sink_permissions == ["diagnostics_only"]
    assert entry.ledger_status == "diagnostics_only"
    assert sink_result is None


def test_ledger_isolated_from_system_state(tmp_path):
    snapshot = make_snapshot()
    original_state = copy.deepcopy(snapshot.system_state_snapshot)
    _, _, _, _ = run_pipeline(snapshot, tmp_path)

    assert snapshot.system_state_snapshot == original_state
    lines = (tmp_path / "candidate_ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    stored = json.loads(lines[0])
    stored_text = json.dumps(stored, ensure_ascii=False)
    assert "system_state_patch" not in stored_text
    assert '"action"' not in stored_text


def test_natural_language_advice_cannot_enter_main_chain(tmp_path):
    snapshot = make_snapshot("natural_language_advice_only")
    _, gate_result, entry, sink_result = run_pipeline(snapshot, tmp_path)

    assert gate_result.gate_status == "diagnostics_only"
    assert "R11_natural_language_advice_only" in gate_result.reject_reasons
    assert entry.accepted_sink == "diagnostics_only"
    assert sink_result is None


def test_missing_source_snapshot_id_or_raw_response_ref_rejected(tmp_path):
    missing_source = make_snapshot("missing_source_snapshot_id")
    _, gate_source, entry_source, _ = run_pipeline(missing_source, tmp_path)
    assert gate_source.gate_status == "rejected"
    assert "R01_missing_source_snapshot_id" in gate_source.reject_reasons
    assert entry_source.accepted_sink == "none"

    missing_raw = make_snapshot("missing_raw_response_ref")
    _, gate_raw, entry_raw, _ = run_pipeline(missing_raw, tmp_path)
    assert gate_raw.gate_status == "rejected"
    assert "R02_missing_raw_response_ref" in gate_raw.reject_reasons
    assert entry_raw.accepted_sink == "none"


def test_sink_only_low_permission_no_action(tmp_path):
    snapshot = make_snapshot()
    _, _, _, sink_result = run_pipeline(snapshot, tmp_path)

    assert sink_result is not None
    payload = sink_result.to_dict()
    assert sink_result.permission_level == "low"
    assert sink_result.action_generated is False
    assert sink_result.system_state_write_requested is False
    assert "system_state_patch" not in payload
    assert "action" not in payload


def test_provider_mode_is_offline_fixture_only(tmp_path):
    snapshot = make_snapshot()
    provider = OfflineFixtureProvider()
    output, gate_result, entry, _ = run_pipeline(snapshot, tmp_path)
    record = ReplayCompare().build_record(snapshot, output, gate_result, entry)

    assert provider.provider_mode == "offline_fixture"
    assert record.provider_mode == "offline_fixture"


def test_no_network_or_api_key_path(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "should_not_be_read")
    provider = OfflineFixtureProvider()
    snapshot = make_snapshot()
    output = provider.generate(snapshot)

    assert output.raw_response_ref.startswith("fixture://")
    source = Path(__file__).parents[1] / "cognitive_bridge_v0" / "offline_provider.py"
    text = source.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY" not in text
    assert "requests" not in text
    assert "urllib" not in text
    assert os.environ["OPENAI_API_KEY"] == "should_not_be_read"


def test_no_v14_import():
    forbidden_modules = [
        "reaction_core",
        "consciousness_v02",
        "SystemState",
        "system_state",
    ]
    loaded = set(sys.modules)
    for module_name in forbidden_modules:
        assert module_name not in loaded


def test_schema_enums_are_enforced():
    with pytest.raises(ValueError):
        ConstitutionGateResult(
            gate_id="gate_invalid",
            source_output_id="out_invalid",
            gate_status="not_allowed",
            accepted_parts=[],
            rejected_parts=[],
            reject_reasons=[],
            needs_human_review=False,
            diagnostics_only=False,
            sink_permissions=[],
            gate_notes="invalid",
        ).validate()

    with pytest.raises(ValueError):
        IntentSinkResult(
            sink_id="sink_invalid",
            source_candidate_id="cand_invalid",
            sink_type="action",
            permission_level="low",
            payload={},
            created_at="2026-06-27T00:00:00+08:00",
            action_generated=False,
            system_state_write_requested=False,
            notes="invalid",
        ).validate()


def test_allow_low_permission_sink_false_blocks_sink(tmp_path):
    snapshot = make_snapshot()
    snapshot.diagnostics_flags.allow_low_permission_sink = False

    _, gate_result, entry, sink_result = run_pipeline(snapshot, tmp_path)

    assert gate_result.gate_status == "diagnostics_only"
    assert "R12_diagnostics_only_no_deposition" in gate_result.reject_reasons
    assert entry.ledger_status == "diagnostics_only"
    assert entry.accepted_sink == "diagnostics_only"
    assert sink_result is None


def test_allow_candidate_generation_false_blocks_sink(tmp_path):
    snapshot = make_snapshot()
    snapshot.diagnostics_flags.allow_candidate_generation = False

    _, gate_result, entry, sink_result = run_pipeline(snapshot, tmp_path)

    assert gate_result.gate_status == "diagnostics_only"
    assert "R13_candidate_generation_disabled" in gate_result.reject_reasons
    assert entry.ledger_status == "diagnostics_only"
    assert entry.accepted_sink == "diagnostics_only"
    assert sink_result is None
