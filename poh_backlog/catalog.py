"""Каталог правил: чтение YAML-данных и валидация."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

BUCKETS = ("close", "merge", "update", "split", "link", "no-action")
KINDS = ("deterministic", "judgment")
MATURITIES = ("experimental", "advisory", "trusted")
ACTIONS = (
    "propose_close",
    "propose_merge",
    "update_field",
    "relink",
    "split",
    "comment",
)
SEVERITIES = ("low", "medium", "high")


class CatalogError(Exception):
    """Битая запись каталога."""


@dataclass(frozen=True)
class RuleSpec:
    id: str
    title: str
    bucket: str
    kind: str
    severity: str
    threshold: str | None
    action: str
    maturity: str
    expected_effect: str | None


def _spec(entry: dict[str, Any]) -> RuleSpec:
    try:
        spec = RuleSpec(
            id=entry["id"],
            title=entry["title"],
            bucket=entry["bucket"],
            kind=entry["kind"],
            severity=entry["severity"],
            threshold=entry.get("threshold"),
            action=entry["action"],
            maturity=entry["maturity"],
            expected_effect=entry.get("expected_effect"),
        )
    except KeyError as exc:
        raise CatalogError(f"В записи каталога нет обязательного поля: {exc}") from exc
    if spec.bucket not in BUCKETS:
        raise CatalogError(f"{spec.id}: недопустимая корзина {spec.bucket}")
    if spec.kind not in KINDS:
        raise CatalogError(f"{spec.id}: недопустимый вид {spec.kind}")
    if spec.maturity not in MATURITIES:
        raise CatalogError(f"{spec.id}: недопустимая зрелость {spec.maturity}")
    if spec.action not in ACTIONS:
        raise CatalogError(f"{spec.id}: недопустимое действие {spec.action}")
    if spec.severity not in SEVERITIES:
        raise CatalogError(f"{spec.id}: недопустимая серьёзность {spec.severity}")
    return spec


def load_catalog(path: Path) -> dict[str, RuleSpec]:
    entries = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    if not isinstance(entries, list):
        raise CatalogError(
            "Каталог правил должен быть списком записей, "
            f"получен {type(entries).__name__}"
        )
    catalog: dict[str, RuleSpec] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise CatalogError(
                "Каждая запись каталога должна быть отображением (mapping), "
                f"получен {type(entry).__name__}: {entry!r}"
            )
        spec = _spec(entry)
        if spec.id in catalog:
            raise CatalogError(f"Дублирующийся идентификатор правила: {spec.id}")
        catalog[spec.id] = spec
    return catalog
