"""Память: артефакты state/ и штаб Backlog.md.

Штаб хранит указатель и статус, содержимое живёт в state/. Доску можно потерять:
она пересобирается из артефактов.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import yaml

from poh_backlog.suppress import DecisionsError

STAGES = ("audit", "diff", "plan", "approve", "apply", "verify", "snapshot")


class StateError(Exception):
    """Ошибка чтения артефактов последнего прогона в state/.

    Файлы в state/<run-id>/ пишутся атомарно, но процесс мог быть убит до
    того, как атомарная запись вообще началась (например, при ручной правке
    файла), либо файл может быть повреждён внешним вмешательством. В любом
    из этих случаев нельзя молча откатиться на более старый прогон: устаревший
    снапшот даст неверный diff, а тихое использование не того baseline хуже,
    чем явная остановка с понятным сообщением.
    """


def _atomic_write(path: Path, text: str) -> None:
    """Пишет текст атомарно: во временный файл рядом, затем `os.replace`.

    Так процесс, убитый на середине записи, оставляет либо старый файл, либо
    новый — но никогда не половину нового: замена файла — атомарная операция
    на уровне файловой системы.
    """
    path = Path(path)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.",
                                    suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(text)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _dump_json(path: Path, payload) -> None:
    _atomic_write(Path(path), json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def write_state(root: Path, run_id: str, snapshot: dict, findings: list[dict],
                plan: dict, applied: list[str]) -> Path:
    state_dir = Path(root) / run_id
    state_dir.mkdir(parents=True, exist_ok=True)
    _dump_json(state_dir / "items.snapshot.json", snapshot)
    _dump_json(state_dir / "findings.json", findings)
    _dump_json(state_dir / "plan.json", plan)
    _dump_json(state_dir / "applied.json", applied)
    return state_dir


def _load_latest_json(root: Path, filename: str):
    """Возвращает (путь, распарсенное содержимое) файла `filename` из
    последнего прогона, либо None, если прогонов с таким файлом нет.

    Поднимает StateError, если файл последнего прогона не читается или не
    парсится — молчаливый откат на более старый прогон здесь недопустим.
    """
    root = Path(root)
    if not root.exists():
        return None
    runs = sorted(p for p in root.iterdir() if (p / filename).exists())
    if not runs:
        return None
    latest = runs[-1] / filename
    try:
        text = latest.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise StateError(
            f"не удалось прочитать файл последнего прогона: {latest}"
        ) from exc
    try:
        return latest, json.loads(text)
    except json.JSONDecodeError as exc:
        raise StateError(
            f"файл последнего прогона повреждён (некорректный JSON): {latest}"
        ) from exc


def load_latest_snapshot(root: Path) -> dict | None:
    result = _load_latest_json(root, "items.snapshot.json")
    if result is None:
        return None
    _, payload = result
    return payload


def load_latest_findings_count(root: Path) -> int:
    result = _load_latest_json(root, "findings.json")
    if result is None:
        return 0
    _, payload = result
    return len(payload)


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
    """Дописывает записи в decisions.yaml, читаемый poh_backlog.suppress.

    decisions.yaml правится руками, поэтому опечатки и повреждённый YAML —
    реалистичный случай (см. poh_backlog.suppress.DecisionsError). Запись
    выполняется атомарно, чтобы убитый на середине процесс не оставил
    decisions.yaml в полусохранённом состоянии, из-за которого следующий
    прогон не сможет прочитать уже принятые решения.
    """
    path = Path(path)
    existing: list = []
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
            raw = yaml.safe_load(text)
        except (OSError, UnicodeDecodeError) as exc:
            raise DecisionsError(
                f"не удалось прочитать decisions.yaml: {path}"
            ) from exc
        except yaml.YAMLError as exc:
            raise DecisionsError(
                f"decisions.yaml повреждён (некорректный YAML): {path}"
            ) from exc
        if raw is None:
            existing = []
        elif isinstance(raw, list):
            existing = raw
        else:
            raise DecisionsError(
                f"decisions.yaml должен быть списком записей, а не "
                f"{type(raw).__name__}: {path}"
            )
    existing.extend(entries)
    _atomic_write(path, yaml.safe_dump(existing, allow_unicode=True, sort_keys=False))
