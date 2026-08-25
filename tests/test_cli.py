import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

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
    # Регрессия B1: план никем не открытый (все действия нетронуты — не
    # утверждены и не отклонены явно) не должен порождать ни одного
    # постоянного подавления в decisions.yaml. Раньше `approve` трактовал
    # каждое нетронутое действие как отказ и глушил его навсегда.
    run_cli(workspace, "--shadow")
    plan = json.loads((workspace / "out" / "plan.json").read_text(encoding="utf-8"))
    total_actions = len(plan["actions"])
    assert total_actions > 0

    code = main(["approve", "--out", str(workspace / "out"),
                 "--decisions", str(workspace / "decisions.yaml")])
    assert code == 0
    out_text = capsys.readouterr().out
    assert "Утверждено: 0" in out_text
    assert "Отклонено: 0" in out_text
    assert f"Не решено: {total_actions}" in out_text

    decisions_path = workspace / "decisions.yaml"
    assert decisions_path.exists()
    entries = yaml.safe_load(decisions_path.read_text(encoding="utf-8"))
    assert (entries or []) == []


def test_approve_picks_checked_action(workspace, capsys):
    run_cli(workspace)
    plan_md = workspace / "out" / "plan.md"
    text = plan_md.read_text(encoding="utf-8").replace("- [ ] ", "- [x] ", 1)
    plan_md.write_text(text, encoding="utf-8")
    main(["approve", "--out", str(workspace / "out"),
          "--decisions", str(workspace / "decisions.yaml")])
    assert "Утверждено: 1" in capsys.readouterr().out
    actions = json.loads((workspace / "out" / "approved.json").read_text(encoding="utf-8"))
    assert len(actions) == 1


def test_approve_suppresses_only_explicitly_rejected_action(workspace, capsys):
    # Регрессия B1: снятие галочки (нетронутый чекбокс) — это не отказ.
    # Только явный маркер `- [-]` должен уходить в decisions.yaml.
    run_cli(workspace)
    plan_md = workspace / "out" / "plan.md"
    lines = plan_md.read_text(encoding="utf-8").splitlines()
    checkbox_lines = [i for i, line in enumerate(lines) if line.startswith("- [ ] ")]
    assert len(checkbox_lines) >= 2
    lines[checkbox_lines[0]] = lines[checkbox_lines[0]].replace("- [ ] ", "- [-] ", 1)
    plan_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    code = main(["approve", "--out", str(workspace / "out"),
                 "--decisions", str(workspace / "decisions.yaml")])
    assert code == 0
    out_text = capsys.readouterr().out
    assert "Отклонено: 1" in out_text

    entries = yaml.safe_load((workspace / "decisions.yaml").read_text(encoding="utf-8"))
    assert len(entries) == 1
    assert entries[0]["verdict"] == "rejected"


def test_shadow_flag_persists_to_plan_json(workspace):
    run_cli(workspace, "--shadow")
    plan = json.loads((workspace / "out" / "plan.json").read_text(encoding="utf-8"))
    assert plan["shadow"] is True


def test_non_shadow_run_persists_shadow_false(workspace):
    run_cli(workspace)
    plan = json.loads((workspace / "out" / "plan.json").read_text(encoding="utf-8"))
    assert plan["shadow"] is False


def test_approve_ignores_ticks_made_on_a_shadow_run_plan(workspace, capsys):
    # Регрессия B2: shadow — это флаг прогона, а не CLI-параметра approve.
    # Человек не должен суметь утвердить план прогона, сделанного в
    # shadow-режиме, поставив галочки в plan.md вручную — approve обязан
    # прочитать shadow из plan.json, к которому он привязан, и отказаться
    # утверждать что-либо.
    run_cli(workspace, "--shadow")
    plan_md = workspace / "out" / "plan.md"
    text = plan_md.read_text(encoding="utf-8").replace("- [ ] ", "- [x] ", 1)
    plan_md.write_text(text, encoding="utf-8")

    code = main(["approve", "--out", str(workspace / "out"),
                 "--decisions", str(workspace / "decisions.yaml")])
    assert code == 0
    out_text = capsys.readouterr().out
    assert "Утверждено: 0" in out_text

    approved = json.loads((workspace / "out" / "approved.json").read_text(encoding="utf-8"))
    assert approved == []


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
    run_cli(workspace)
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


def test_run_gates_suppressed_drift_finding_out_of_findings_and_plan(tmp_path):
    # Регрессия B3: находки дрейфа фаз (`detect_phase_drift`) склеивались с
    # находками аудита ПОСЛЕ гейта подавления, так что ранее отклонённый
    # PHS-DRIFT-008 возвращался как новый на каждом прогоне.
    items_path = tmp_path / "items.json"
    decisions_path = tmp_path / "decisions.yaml"
    out = tmp_path / "out"
    state = tmp_path / "state"

    def write_items(labels):
        items_path.write_text(json.dumps([{
            "id": "S-1", "type": "story", "title": "История",
            "description": "Не очень длинное описание истории про перенос фазы",
            "status": "open",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-08-20T00:00:00+00:00",
            "labels": labels, "estimate": 3.0, "parent": None,
        }], ensure_ascii=False), encoding="utf-8")

    write_items(["grow"])
    code = main(["run", "--items", str(items_path), "--state", str(state),
                 "--out", str(out), "--run-id", "run-1",
                 "--now", "2026-08-20T00:00:00+00:00",
                 "--decisions", str(decisions_path), "--shadow"])
    assert code == 0

    # Человек уже отклонил этот дрейф фазы для S-1 раньше.
    decisions_path.write_text(yaml.safe_dump([{
        "rule_id": "PHS-DRIFT-008", "item": "S-1", "verdict": "rejected",
        "reason": "тест", "suppress_until": "forever",
    }], allow_unicode=True), encoding="utf-8")

    write_items(["mvp"])
    code = main(["run", "--items", str(items_path), "--state", str(state),
                 "--out", str(out), "--run-id", "run-2",
                 "--now", "2026-08-21T00:00:00+00:00",
                 "--decisions", str(decisions_path), "--shadow"])
    assert code == 0

    findings = json.loads((out / "findings.json").read_text(encoding="utf-8"))
    assert "PHS-DRIFT-008" not in {f["rule_id"] for f in findings}

    plan = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    assert all(a["rule_id"] != "PHS-DRIFT-008" for a in plan["actions"])


def test_approve_refuses_when_plan_md_run_id_disagrees_with_plan_json(workspace, capsys):
    # Регрессия B4: plan.md и plan.json ничем не связаны — если plan.md
    # оказался от другого прогона (например, был перезаписан позже), approve
    # не должен молча принимать отметки, сделанные не для этого plan.json.
    run_cli(workspace)
    plan_md = workspace / "out" / "plan.md"
    text = plan_md.read_text(encoding="utf-8")
    desynced = text.replace("2026-08-18-01", "2026-08-18-99")
    assert desynced != text
    plan_md.write_text(desynced, encoding="utf-8")

    code = main(["approve", "--out", str(workspace / "out"),
                 "--decisions", str(workspace / "decisions.yaml")])
    assert code == 2
    err = capsys.readouterr().err
    assert "2026-08-18-01" in err
    assert "2026-08-18-99" in err


def test_run_refuses_to_overwrite_plan_md_with_pending_decisions(workspace, capsys):
    # Регрессия B4: ночной cron, вызывающий `run` в тот же --out, не должен
    # молча затирать галочки, которые PO успел проставить днём.
    run_cli(workspace)
    plan_md = workspace / "out" / "plan.md"
    original = plan_md.read_text(encoding="utf-8")
    ticked = original.replace("- [ ] ", "- [x] ", 1)
    assert ticked != original
    plan_md.write_text(ticked, encoding="utf-8")

    code = run_cli(workspace)
    assert code == 2
    err = capsys.readouterr().err
    assert str(plan_md) in err
    assert plan_md.read_text(encoding="utf-8") == ticked


def test_run_freely_overwrites_an_untouched_plan_md(workspace):
    # Симметричный случай: план, который никто не открывал, не содержит
    # решений — его можно перезаписывать свободно (нужно для идемпотентных
    # повторных прогонов и cron).
    run_cli(workspace)
    code = run_cli(workspace)
    assert code == 0


def test_run_accepts_now_without_timezone_offset(workspace):
    # Регрессия B5: --now по умолчанию делается aware (astimezone()), поэтому
    # именно тот, кто явно передал свой --now без смещения, получал сырой
    # TypeError на первом же правиле, вычитающем ctx.now из aware updated_at.
    argv = ["run", "--items", str(workspace / "items.json"),
            "--state", str(workspace / "state"),
            "--out", str(workspace / "out"),
            "--run-id", "2026-08-18-01",
            "--now", "2026-08-18", "--shadow"]
    assert main(argv) == 0


def test_module_invocation_finds_default_catalog_without_repo_root_data_dirs(tmp_path):
    # Регрессия B6: PACKAGE_ROOT в cli.py считался как
    # Path(__file__).resolve().parent.parent, а rules/, prompts/, mappings/ и
    # schemas/ лежали в корне репозитория — вне пакета poh_backlog. Обычная
    # (не editable) установка копирует в site-packages/ только сам пакет;
    # каталоги с данными, лежащие рядом с ним в репозитории, туда не попадают
    # вообще. Эмулируем именно такую установку: копируем ИЗОЛИРОВАННО только
    # каталог poh_backlog/ (без rules/, prompts/, mappings/, schemas/
    # репозитория) в отдельное место и запускаем `-m poh_backlog.cli` оттуда,
    # с cwd во временном каталоге, где тоже ничего из репозитория нет. Если
    # дефолтные пути всё ещё считаются от родителя пакета, файла с данными
    # там не будет и команда упадёт.
    site_packages = tmp_path / "site-packages"
    shutil.copytree(ROOT / "poh_backlog", site_packages / "poh_backlog",
                    ignore=shutil.ignore_patterns("__pycache__"))

    workdir = tmp_path / "cwd"
    workdir.mkdir()
    items_path = workdir / "items.json"
    items_path.write_text(json.dumps([{
        "id": "S-1", "type": "story", "title": "История",
        "description": "Достаточно длинное описание истории для проверки пути",
        "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-08-10T00:00:00+00:00",
        "labels": ["mvp"], "estimate": 3.0, "parent": None,
    }], ensure_ascii=False), encoding="utf-8")

    env = {**os.environ, "PYTHONPATH": str(site_packages)}
    result = subprocess.run(
        [sys.executable, "-m", "poh_backlog.cli", "run",
         "--items", "items.json", "--state", "state", "--out", "out",
         "--run-id", "run-1", "--now", "2026-08-18T00:00:00+00:00", "--shadow"],
        cwd=workdir, env=env, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (workdir / "out" / "findings.json").exists()
    assert (workdir / "out" / "plan.json").exists()


def test_run_accepts_naive_timestamps_in_items_json(tmp_path):
    # Регрессия B5: schemas/backlog-item.schema.json типизирует created_at и
    # updated_at как обычные строки, ничего не нормализуя. Хост-агент вполне
    # может положить в items.json наивные (без смещения) отметки времени.
    items_path = tmp_path / "items.json"
    items_path.write_text(json.dumps([{
        "id": "S-1", "type": "story", "title": "История",
        "description": "Не очень длинное описание истории про наивные даты",
        "status": "open",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-08-10T00:00:00",
        "labels": ["mvp"], "estimate": 3.0, "parent": None,
    }], ensure_ascii=False), encoding="utf-8")
    code = main(["run", "--items", str(items_path),
                 "--state", str(tmp_path / "state"),
                 "--out", str(tmp_path / "out"),
                 "--run-id", "run-1",
                 "--now", "2026-08-18T00:00:00+00:00", "--shadow"])
    assert code == 0
