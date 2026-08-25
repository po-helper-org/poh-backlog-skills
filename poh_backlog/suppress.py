"""Подавления: отклонённое человеком не возвращается каждый прогон."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from poh_backlog.model import Finding


class DecisionsError(Exception):
    """Ошибка в человеко-редактируемом decisions.yaml.

    decisions.yaml правится руками, поэтому опечатки и некорректные значения —
    реалистичный, а не гипотетический случай. Любая такая ошибка должна
    останавливать прогон понятным сообщением на русском, а не тонуть в
    сыром traceback'е и не приводить к молчаливому пропуску записи: пропущенное
    подавление означает, что отклонённая находка вернётся в отчёт как новая,
    и агент снова превратится в источник шума.
    """


@dataclass(frozen=True)
class Suppression:
    rule_id: str
    item_id: str
    until: date | None  # None означает forever; иначе — последний день, когда подавление ещё действует (включительно)


def load_suppressions(path: Path) -> list[Suppression]:
    path = Path(path)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DecisionsError(
            f"decisions.yaml повреждён (некорректный YAML): {path}"
        ) from exc
    entries = raw or []
    if not isinstance(entries, list):
        raise DecisionsError(
            f"decisions.yaml должен быть списком записей, а не {type(entries).__name__}: {path}"
        )
    result: list[Suppression] = []
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise DecisionsError(
                f"decisions.yaml: запись №{position} должна быть словарём, а не "
                f"{type(entry).__name__} ({path})"
            )
        if entry.get("verdict") != "rejected":
            continue
        if "rule_id" not in entry or "item" not in entry:
            raise DecisionsError(
                f"decisions.yaml: запись №{position} не содержит обязательных полей "
                f"rule_id и item ({path})"
            )
        raw_until = entry.get("suppress_until", "forever")
        until = None if raw_until in (None, "forever") else _as_date(raw_until, position, path)
        result.append(Suppression(entry["rule_id"], entry["item"], until))
    return result


def _as_date(value, position: int, path: Path) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise DecisionsError(
            f"decisions.yaml: запись №{position} содержит некорректный suppress_until "
            f"({value!r}); ожидается 'forever' или дата в формате ISO (YYYY-MM-DD) ({path})"
        ) from exc


def is_pair_suppressed(rule_id: str, item_id: str, suppressions: list[Suppression],
                       today: date) -> bool:
    """Подавлена ли пара (rule_id, item_id) на указанную дату.

    Единственная реализация гейта подавления. И свежая находка (через
    `is_suppressed`), и вернувшееся, но не сделанное обещание обязаны
    проходить именно через эту функцию — иначе у отклонённого навсегда
    появляется второй, непроверяемый вход обратно в план.

    Подавление с датой действует включительно по названный день: если
    человек написал `suppress_until: 2026-12-01`, пара остаётся подавленной
    весь этот день и возвращается только начиная со следующего.
    """
    for sup in suppressions:
        if sup.rule_id != rule_id or sup.item_id != item_id:
            continue
        if sup.until is None or today <= sup.until:
            return True
    return False


def is_suppressed(finding: Finding, suppressions: list[Suppression], today: date) -> bool:
    """Подавлена ли находка на указанную дату.

    Тонкая обёртка над `is_pair_suppressed`: находка — лишь один из двух
    источников пар (rule_id, item_id), которым может грозить подавление;
    второй — вернувшиеся обещания (см. `poh_backlog.cli.cmd_run`).
    """
    return is_pair_suppressed(finding.rule_id, finding.item_id, suppressions, today)
