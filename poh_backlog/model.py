"""Каноническая модель элемента беклога и производные типы."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

PHASE_TAGS = ("mvp", "grow")


@dataclass(frozen=True)
class BacklogItem:
    id: str
    type: str
    title: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime
    labels: tuple[str, ...]
    parent: str | None
    estimate: float | None
    extra: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "BacklogItem":
        return cls(
            id=raw["id"],
            type=raw["type"],
            title=raw["title"],
            description=raw.get("description") or "",
            status=raw["status"],
            created_at=datetime.fromisoformat(raw["created_at"]),
            updated_at=datetime.fromisoformat(raw["updated_at"]),
            labels=tuple(raw.get("labels") or ()),
            parent=raw.get("parent"),
            estimate=raw.get("estimate"),
            extra=dict(raw.get("extra") or {}),
        )

    @property
    def phase_tags(self) -> tuple[str, ...]:
        return tuple(label for label in self.labels if label in PHASE_TAGS)

    @property
    def is_open(self) -> bool:
        return self.status == "open"


@dataclass(frozen=True)
class Finding:
    rule_id: str
    item_id: str
    bucket: str
    severity: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditContext:
    items: dict[str, BacklogItem]
    children: dict[str, list[str]]
    profile: Any
    now: datetime
