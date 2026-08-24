"""Детерминированные правила гигиены: HYG-*."""
from __future__ import annotations

from poh_backlog.model import AuditContext, BacklogItem, Finding
from poh_backlog.rules import rule
from poh_backlog.text import ru_plural

ESTIMATED_TYPES = ("story", "bug", "task")
PARENTED_TYPES = ("story", "bug", "task")


@rule("HYG-STALE-001")
def stale(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if not item.is_open:
        return []
    key = "staleness.bug_days" if item.type == "bug" else "staleness.story_days"
    limit = ctx.profile.get(key)
    days = (ctx.now - item.updated_at).days
    if days < limit:
        return []
    return [Finding(
        rule_id="HYG-STALE-001",
        item_id=item.id,
        bucket="close",
        severity="medium",
        message=f"Нет активности {days} дней при пороге {limit}",
        evidence={"days_since_update": days, "threshold_days": limit},
    )]


@rule("HYG-DESC-002")
def short_description(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if not item.is_open:
        return []
    limit = ctx.profile.get("description.min_words")
    words = len(item.description.split())
    if words >= limit:
        return []
    word_form = ru_plural(words, "слова", "слова", "слов")
    return [Finding(
        rule_id="HYG-DESC-002",
        item_id=item.id,
        bucket="update",
        severity="medium",
        message=f"Описание из {words} {word_form} при пороге {limit}",
        evidence={"word_count": words, "threshold_words": limit},
    )]


@rule("HYG-EST-003")
def missing_estimate(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if not item.is_open or item.type not in ESTIMATED_TYPES:
        return []
    if item.estimate is not None:
        return []
    return [Finding(
        rule_id="HYG-EST-003",
        item_id=item.id,
        bucket="update",
        severity="low",
        message="Нет оценки: элемент не проходит Definition of Ready",
        evidence={},
    )]


@rule("HYG-ORPHAN-004")
def orphan(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if not item.is_open or item.type not in PARENTED_TYPES:
        return []
    if item.parent is not None:
        return []
    return [Finding(
        rule_id="HYG-ORPHAN-004",
        item_id=item.id,
        bucket="link",
        severity="medium",
        message="Нет родителя: элемент выпадает из иерархии и планирования",
        evidence={},
    )]
