"""Подавления: отклонённое человеком не возвращается каждый прогон."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from poh_backlog.model import Finding


@dataclass(frozen=True)
class Suppression:
    rule_id: str
    item_id: str
    until: date | None  # None означает forever


def load_suppressions(path: Path) -> list[Suppression]:
    path = Path(path)
    if not path.exists():
        return []
    entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    result: list[Suppression] = []
    for entry in entries:
        if entry.get("verdict") != "rejected":
            continue
        raw_until = entry.get("suppress_until", "forever")
        until = None if raw_until in (None, "forever") else _as_date(raw_until)
        result.append(Suppression(entry["rule_id"], entry["item"], until))
    return result


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def is_suppressed(finding: Finding, suppressions: list[Suppression], today: date) -> bool:
    for sup in suppressions:
        if sup.rule_id != finding.rule_id or sup.item_id != finding.item_id:
            continue
        if sup.until is None or today < sup.until:
            return True
    return False
