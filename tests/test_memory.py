import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from poh_backlog.memory import (STAGES, StateError, append_decisions,
                                backlog_check_ac_argv, backlog_create_argv,
                                carry_forward_verdicts, load_latest_findings_count,
                                load_latest_snapshot, load_latest_verdicts,
                                write_state, write_verdicts)
from poh_backlog.suppress import DecisionsError, Suppression


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


def test_write_verdicts_adds_files_to_existing_run(tmp_path):
    write_state(tmp_path, "r1", {"items": {}}, [], {}, [])
    state_dir = write_verdicts(tmp_path, "r1",
                               [{"action_key": "k", "status": "done"}], ["k"])
    assert json.loads((state_dir / "verdicts.json").read_text(encoding="utf-8")) \
        == [{"action_key": "k", "status": "done"}]
    assert json.loads((state_dir / "applied.json").read_text(encoding="utf-8")) \
        == ["k"]


def test_write_verdicts_creates_run_dir_when_absent(tmp_path):
    state_dir = write_verdicts(tmp_path, "r9", [], [])
    assert state_dir.is_dir()


def test_load_latest_verdicts_returns_newest_run_and_its_id(tmp_path):
    write_verdicts(tmp_path, "2026-08-25-01", [{"status": "done"}], [])
    write_verdicts(tmp_path, "2026-08-26-01", [{"status": "not_applied"}], [])
    assert load_latest_verdicts(tmp_path) == (
        "2026-08-26-01", [{"status": "not_applied"}])


def test_load_latest_verdicts_without_runs_returns_empty(tmp_path):
    assert load_latest_verdicts(tmp_path) == (None, [])


def test_load_latest_verdicts_ignores_runs_without_verdicts(tmp_path):
    write_verdicts(tmp_path, "2026-08-25-01", [{"status": "done"}], [])
    write_state(tmp_path, "2026-08-26-01", {"items": {}}, [], {}, [])
    assert load_latest_verdicts(tmp_path) == ("2026-08-25-01", [{"status": "done"}])


def test_broken_verdicts_file_raises_state_error(tmp_path):
    state_dir = write_verdicts(tmp_path, "r1", [], [])
    (state_dir / "verdicts.json").write_text("{не json", encoding="utf-8")
    with pytest.raises(StateError) as exc:
        load_latest_verdicts(tmp_path)
    assert "verdicts.json" in str(exc.value)


# --- carry_forward_verdicts: журнал обещаний накопительный, а не снимок ---
# Финальное ревью, находка 2 (критическая): verdicts.json прошлого прогона
# терялся целиком, если в этом прогоне approved.json пуст (никто ничего не
# утвердил). Обещание должно умереть только от done, явного отказа [-]
# (подавления) или подавления по сроку — но не от пустого файла.

TODAY = date(2026, 8, 19)


def _verdict(rule_id="HYG-EST-003", item_id="S-1", status="not_applied"):
    return {"action_key": "a" * 16, "rule_id": rule_id, "item_id": item_id,
           "op": "update_field", "status": status, "note": "тест",
           "rationale": "тест"}


def test_carry_forward_keeps_unresolved_pair_not_covered_by_approved():
    previous = [_verdict()]
    carried = carry_forward_verdicts(previous, approved=[], suppressions=[],
                                     today=TODAY)
    assert carried == previous


def test_carry_forward_drops_pair_covered_by_this_run_approved():
    previous = [_verdict()]
    approved = [{"rule_id": "HYG-EST-003", "item_id": "S-1"}]
    carried = carry_forward_verdicts(previous, approved, suppressions=[], today=TODAY)
    assert carried == []


def test_carry_forward_drops_done_verdicts():
    previous = [_verdict(status="done")]
    carried = carry_forward_verdicts(previous, approved=[], suppressions=[],
                                     today=TODAY)
    assert carried == []


def test_carry_forward_drops_suppressed_pair():
    previous = [_verdict()]
    suppressions = [Suppression("HYG-EST-003", "S-1", None)]
    carried = carry_forward_verdicts(previous, approved=[],
                                     suppressions=suppressions, today=TODAY)
    assert carried == []


def test_carry_forward_ignores_expired_dated_suppression():
    previous = [_verdict()]
    suppressions = [Suppression("HYG-EST-003", "S-1", date(2026, 1, 1))]
    carried = carry_forward_verdicts(previous, approved=[],
                                     suppressions=suppressions, today=TODAY)
    assert carried == previous


def test_carry_forward_keeps_unrelated_pairs_untouched():
    previous = [_verdict(item_id="S-1"), _verdict(item_id="S-2")]
    approved = [{"rule_id": "HYG-EST-003", "item_id": "S-1"}]
    carried = carry_forward_verdicts(previous, approved, suppressions=[], today=TODAY)
    assert [v["item_id"] for v in carried] == ["S-2"]
