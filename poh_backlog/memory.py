"""Память: артефакты state/ и штаб Backlog.md.

Штаб хранит указатель и статус, содержимое живёт в state/. Доску можно потерять:
она пересобирается из артефактов.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

STAGES = ("audit", "diff", "plan", "approve", "apply", "verify", "snapshot")


def _dump_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def write_state(root: Path, run_id: str, snapshot: dict, findings: list[dict],
                plan: dict, applied: list[str]) -> Path:
    state_dir = Path(root) / run_id
    state_dir.mkdir(parents=True, exist_ok=True)
    _dump_json(state_dir / "items.snapshot.json", snapshot)
    _dump_json(state_dir / "findings.json", findings)
    _dump_json(state_dir / "plan.json", plan)
    _dump_json(state_dir / "applied.json", applied)
    return state_dir


def load_latest_snapshot(root: Path) -> dict | None:
    root = Path(root)
    if not root.exists():
        return None
    runs = sorted(p for p in root.iterdir() if (p / "items.snapshot.json").exists())
    if not runs:
        return None
    return json.loads((runs[-1] / "items.snapshot.json").read_text(encoding="utf-8"))


def load_latest_findings_count(root: Path) -> int:
    root = Path(root)
    if not root.exists():
        return 0
    runs = sorted(p for p in root.iterdir() if (p / "findings.json").exists())
    if not runs:
        return 0
    return len(json.loads((runs[-1] / "findings.json").read_text(encoding="utf-8")))


def backlog_create_argv(run_id: str, state_dir: Path) -> list[str]:
    argv = [
        "backlog", "task", "create", f"Гигиена беклога, прогон {run_id}",
        "-l", "hygiene", "-s", "In Progress",
        "-d", f"Артефакт: {state_dir}",
    ]
    for stage in STAGES:
        argv.extend(["--ac", stage])
    return argv


def backlog_check_ac_argv(task_id: str, stage: str) -> list[str]:
    if stage not in STAGES:
        raise ValueError(f"Неизвестная стадия: {stage}")
    return ["backlog", "task", "edit", task_id, "--check-ac",
            str(STAGES.index(stage) + 1)]


def append_decisions(path: Path, entries: list[dict]) -> None:
    path = Path(path)
    existing = []
    if path.exists():
        existing = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    existing.extend(entries)
    path.write_text(
        yaml.safe_dump(existing, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
