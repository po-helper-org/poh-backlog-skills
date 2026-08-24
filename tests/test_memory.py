import json
from pathlib import Path

import pytest
import yaml

from poh_backlog.memory import (STAGES, StateError, append_decisions,
                                backlog_check_ac_argv, backlog_create_argv,
                                load_latest_findings_count, load_latest_snapshot,
                                write_state)
from poh_backlog.suppress import DecisionsError


def test_stages_match_spec():
    assert STAGES == ("audit", "diff", "plan", "approve", "apply", "verify",
                      "snapshot")


def test_write_state_creates_four_files(tmp_path):
    state_dir = write_state(tmp_path, "2026-08-18-01",
                            snapshot={"items": {}}, findings=[], plan={"actions": []},
                            applied=[])
    assert (state_dir / "items.snapshot.json").exists()
    assert (state_dir / "findings.json").exists()
    assert (state_dir / "plan.json").exists()
    assert json.loads((state_dir / "applied.json").read_text(encoding="utf-8")) == []


def test_load_latest_snapshot_returns_newest_run(tmp_path):
    write_state(tmp_path, "2026-08-17-01", {"items": {"A": {}}}, [], {}, [])
    write_state(tmp_path, "2026-08-18-01", {"items": {"B": {}}}, [], {}, [])
    assert load_latest_snapshot(tmp_path) == {"items": {"B": {}}}


def test_load_latest_snapshot_without_runs_returns_none(tmp_path):
    assert load_latest_snapshot(tmp_path) is None


def test_load_latest_findings_count(tmp_path):
    assert load_latest_findings_count(tmp_path) == 0
    write_state(tmp_path, "2026-08-17-01", {"items": {}},
                [{"rule_id": "A"}, {"rule_id": "B"}], {}, [])
    write_state(tmp_path, "2026-08-18-01", {"items": {}}, [{"rule_id": "C"}], {}, [])
    assert load_latest_findings_count(tmp_path) == 1


def test_backlog_create_argv_has_label_status_and_all_stages(tmp_path):
    argv = backlog_create_argv("2026-08-18-01", tmp_path / "state" / "2026-08-18-01")
    assert argv[:3] == ["backlog", "task", "create"]
    assert "-l" in argv and "hygiene" in argv
    assert argv[argv.index("-s") + 1] == "In Progress"
    assert argv.count("--ac") == len(STAGES)


def test_backlog_check_ac_argv_uses_one_based_stage_index():
    argv = backlog_check_ac_argv("task-7", "plan")
    # "plan" — третья стадия в STAGES (индекс 2), --check-ac ждёт 1-based номер.
    assert argv == ["backlog", "task", "edit", "task-7", "--check-ac",
                    str(STAGES.index("plan") + 1)]


def test_append_decisions_merges_into_existing_file(tmp_path):
    path = tmp_path / "decisions.yaml"
    append_decisions(path, [{"rule_id": "A", "item": "S-1", "verdict": "rejected",
                             "reason": "r", "suppress_until": "forever"}])
    append_decisions(path, [{"rule_id": "B", "item": "S-2", "verdict": "rejected",
                             "reason": "r", "suppress_until": "forever"}])
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert [e["rule_id"] for e in entries] == ["A", "B"]


def test_load_latest_snapshot_raises_state_error_on_corrupted_file(tmp_path):
    state_dir = write_state(tmp_path, "2026-08-18-01", {"items": {}}, [], {}, [])
    (state_dir / "items.snapshot.json").write_text("{не json", encoding="utf-8")
    with pytest.raises(StateError) as excinfo:
        load_latest_snapshot(tmp_path)
    assert str(state_dir / "items.snapshot.json") in str(excinfo.value)


def test_load_latest_findings_count_raises_state_error_on_corrupted_file(tmp_path):
    state_dir = write_state(tmp_path, "2026-08-18-01", {"items": {}}, [], {}, [])
    (state_dir / "findings.json").write_text("{не json", encoding="utf-8")
    with pytest.raises(StateError) as excinfo:
        load_latest_findings_count(tmp_path)
    assert str(state_dir / "findings.json") in str(excinfo.value)


def test_append_decisions_raises_decisions_error_on_malformed_yaml(tmp_path):
    path = tmp_path / "decisions.yaml"
    path.write_text("- rule_id: [это не закрытая скобка\n", encoding="utf-8")
    with pytest.raises(DecisionsError) as excinfo:
        append_decisions(path, [{"rule_id": "A", "item": "S-1",
                                 "verdict": "rejected", "reason": "r",
                                 "suppress_until": "forever"}])
    assert str(path) in str(excinfo.value)


def test_append_decisions_raises_decisions_error_when_content_is_not_a_list(tmp_path):
    path = tmp_path / "decisions.yaml"
    path.write_text("rule_id: A\nitem: S-1\n", encoding="utf-8")
    with pytest.raises(DecisionsError) as excinfo:
        append_decisions(path, [{"rule_id": "B", "item": "S-2",
                                 "verdict": "rejected", "reason": "r",
                                 "suppress_until": "forever"}])
    assert str(path) in str(excinfo.value)


def test_write_state_leaves_no_temporary_files(tmp_path):
    state_dir = write_state(tmp_path, "2026-08-18-01", {"items": {}}, [], {}, [])
    assert sorted(p.name for p in state_dir.iterdir()) == [
        "applied.json", "findings.json", "items.snapshot.json", "plan.json",
    ]


def test_append_decisions_twice_round_trips_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "decisions.yaml"
    append_decisions(path, [{"rule_id": "A", "item": "S-1", "verdict": "rejected",
                             "reason": "r", "suppress_until": "forever"}])
    append_decisions(path, [{"rule_id": "B", "item": "S-2", "verdict": "rejected",
                             "reason": "r", "suppress_until": "forever"}])
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert [e["rule_id"] for e in entries] == ["A", "B"]
    assert [p.name for p in path.parent.iterdir()] == ["decisions.yaml"]


def test_load_latest_snapshot_raises_state_error_on_invalid_utf8(tmp_path):
    state_dir = write_state(tmp_path, "2026-08-18-01", {"items": {}}, [], {}, [])
    (state_dir / "items.snapshot.json").write_bytes(b"\xff\xfe")
    with pytest.raises(StateError) as excinfo:
        load_latest_snapshot(tmp_path)
    assert str(state_dir / "items.snapshot.json") in str(excinfo.value)


def test_load_latest_findings_count_raises_state_error_on_invalid_utf8(tmp_path):
    state_dir = write_state(tmp_path, "2026-08-18-01", {"items": {}}, [], {}, [])
    (state_dir / "findings.json").write_bytes(b"\xff\xfe")
    with pytest.raises(StateError) as excinfo:
        load_latest_findings_count(tmp_path)
    assert str(state_dir / "findings.json") in str(excinfo.value)


def test_append_decisions_raises_decisions_error_on_invalid_utf8(tmp_path):
    path = tmp_path / "decisions.yaml"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(DecisionsError) as excinfo:
        append_decisions(path, [{"rule_id": "A", "item": "S-1",
                                 "verdict": "rejected", "reason": "r",
                                 "suppress_until": "forever"}])
    assert str(path) in str(excinfo.value)


def test_append_decisions_raises_decisions_error_when_content_is_falsy_scalar(tmp_path):
    path = tmp_path / "decisions.yaml"
    path.write_text("0\n", encoding="utf-8")
    with pytest.raises(DecisionsError) as excinfo:
        append_decisions(path, [{"rule_id": "A", "item": "S-1",
                                 "verdict": "rejected", "reason": "r",
                                 "suppress_until": "forever"}])
    assert str(path) in str(excinfo.value)
