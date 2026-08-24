import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from poh_backlog.cli import main

ROOT = Path(__file__).parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "items.json"


@pytest.fixture()
def workspace(tmp_path):
    shutil.copy(FIXTURE, tmp_path / "items.json")
    return tmp_path


def run_cli(workspace, *extra):
    argv = ["run", "--items", str(workspace / "items.json"),
            "--state", str(workspace / "state"),
            "--out", str(workspace / "out"),
            "--run-id", "2026-08-18-01",
            "--now", "2026-08-18T00:00:00+00:00"]
    return main(argv + list(extra))


def test_run_writes_all_artifacts(workspace):
    assert run_cli(workspace, "--shadow") == 0
    out = workspace / "out"
    assert (out / "findings.json").exists()
    assert (out / "report.md").exists()
    assert (out / "plan.md").exists()
    assert (out / "plan.json").exists()
    assert (workspace / "state" / "2026-08-18-01" / "items.snapshot.json").exists()


def test_run_finds_known_defects_in_fixture(workspace):
    run_cli(workspace, "--shadow")
    findings = json.loads((workspace / "out" / "findings.json").read_text(encoding="utf-8"))
    rule_ids = {f["rule_id"] for f in findings}
    assert "HYG-STALE-001" in rule_ids   # S-1 не трогали с января
    assert "HYG-DESC-002" in rule_ids    # S-2 описание из одного слова
    assert "HYG-EST-003" in rule_ids     # S-2 без оценки
    assert "PHS-TAG-001" in rule_ids     # S-2 без тега фазы
    assert "PHS-EPIC-002" in rule_ids    # E-1 без due_date, how_to_demo, limitations
    assert "PHS-SUP-007" in rule_ids     # у I-1 нет Support-эпика


def test_shadow_run_reports_zero_approved(workspace, capsys):
    run_cli(workspace, "--shadow")
    assert "Утверждено: 0" in capsys.readouterr().out


def test_second_run_is_idempotent_on_action_keys(workspace):
    run_cli(workspace, "--shadow")
    first = (workspace / "out" / "plan.json").read_text(encoding="utf-8")
    run_cli(workspace, "--shadow")
    assert (workspace / "out" / "plan.json").read_text(encoding="utf-8") == first


def test_approve_without_checkboxes_yields_no_actions(workspace, capsys):
    run_cli(workspace, "--shadow")
    code = main(["approve", "--out", str(workspace / "out"),
                 "--decisions", str(workspace / "decisions.yaml")])
    assert code == 0
    assert "Утверждено: 0" in capsys.readouterr().out
    assert (workspace / "decisions.yaml").exists()


def test_approve_picks_checked_action(workspace, capsys):
    run_cli(workspace, "--shadow")
    plan_md = workspace / "out" / "plan.md"
    text = plan_md.read_text(encoding="utf-8").replace("- [ ] ", "- [x] ", 1)
    plan_md.write_text(text, encoding="utf-8")
    main(["approve", "--out", str(workspace / "out"),
          "--decisions", str(workspace / "decisions.yaml")])
    assert "Утверждено: 1" in capsys.readouterr().out
    actions = json.loads((workspace / "out" / "approved.json").read_text(encoding="utf-8"))
    assert len(actions) == 1


def test_module_invocation_runs_main_and_shows_subcommands():
    # Регрессия: `python3 -m poh_backlog.cli` без `if __name__ == "__main__"`
    # молча выходит с кодом 0, ничего не делая. Человек без установленного
    # пакета первым делом попробует `-m`, а не консольный скрипт.
    result = subprocess.run(
        [sys.executable, "-m", "poh_backlog.cli", "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "run" in result.stdout
    assert "approve" in result.stdout


def test_findings_and_plan_json_end_with_trailing_newline(workspace):
    run_cli(workspace, "--shadow")
    out = workspace / "out"
    for name in ("findings.json", "plan.json"):
        assert (out / name).read_text(encoding="utf-8").endswith("\n")


def test_approved_json_ends_with_trailing_newline(workspace):
    run_cli(workspace, "--shadow")
    plan_md = workspace / "out" / "plan.md"
    text = plan_md.read_text(encoding="utf-8").replace("- [ ] ", "- [x] ", 1)
    plan_md.write_text(text, encoding="utf-8")
    main(["approve", "--out", str(workspace / "out"),
          "--decisions", str(workspace / "decisions.yaml")])
    approved = workspace / "out" / "approved.json"
    assert approved.read_text(encoding="utf-8").endswith("\n")


def test_corrupted_previous_snapshot_exits_with_code_2(workspace, capsys):
    # Первый прогон создаёт снимок в state/, который следующий прогон читает
    # как baseline для диффа.
    run_cli(workspace, "--shadow")
    snapshot_path = workspace / "state" / "2026-08-18-01" / "items.snapshot.json"
    snapshot_path.write_text("это не json", encoding="utf-8")

    argv = ["run", "--items", str(workspace / "items.json"),
            "--state", str(workspace / "state"),
            "--out", str(workspace / "out"),
            "--run-id", "2026-08-18-02",
            "--now", "2026-08-18T00:00:00+00:00", "--shadow"]
    code = main(argv)

    assert code == 2
    err = capsys.readouterr().err
    assert str(snapshot_path) in err
