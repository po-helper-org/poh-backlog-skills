"""Каноническая модель элемента беклога и производные типы."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

PHASE_TAGS = ("mvp", "grow")


def ensure_aware(value: datetime) -> datetime:
    """Приводит наивный (без часового пояса) datetime к aware, трактуя его
    как UTC.

    Единая точка нормализации границы: и `--now` из CLI, и `created_at`/
    `updated_at` из items.json могут прийти наивными — `--now` по умолчанию
    aware, но человек может передать своё значение без смещения, а
    `schemas/backlog-item.schema.json` типизирует отметки времени как
    обычные строки и ничего не гарантирует про смещение. Дальше по
    конвейеру эти datetime вычитаются друг из друга (например,
    `ctx.now - item.updated_at` в HYG-STALE-001), а вычитание naive из
    aware — это TypeError, а не тихая ошибка. Нормализуя здесь, весь
    остальной код работает с aware datetime и не должен знать про этот
    случай.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


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
            created_at=ensure_aware(datetime.fromisoformat(raw["created_at"])),
            updated_at=ensure_aware(datetime.fromisoformat(raw["updated_at"])),
            labels=tuple(raw.get("labels") or ()),
            parent=raw.get("parent"),
            estimate=raw.get("estimate"),
            extra=dict(raw.get("extra") or {}),
        )

    def phase_tags_for(self, names: tuple[str, ...]) -> tuple[str, ...]:
        """Возвращает метки элемента, входящие в переданный набор имён тегов
        фазы, сохраняя порядок меток. Правила должны вызывать этот метод
        с именами тегов из профиля команды (`phases.mvp_tag`, `phases.grow_tag`),
        а не полагаться на дефолтные названия."""
        return tuple(label for label in self.labels if label in names)

    @property
    def phase_tags(self) -> tuple[str, ...]:
        """Метки фазы по умолчанию (`PHASE_TAGS` = "mvp"/"grow"). Это
        соглашение о названии по умолчанию: правила, учитывающие профиль
        команды, обязаны передавать имена тегов из профиля явно через
        `phase_tags_for`, а не полагаться на этот дефолт."""
        return self.phase_tags_for(PHASE_TAGS)

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
