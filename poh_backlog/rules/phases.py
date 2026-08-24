"""Инварианты модели фаз по одному снимку: PHS-* кроме дрейфа."""
from __future__ import annotations

from poh_backlog.context import is_feature_epic, is_support_epic
from poh_backlog.model import AuditContext, BacklogItem, Finding
from poh_backlog.rules import rule

PHASED_TYPES = ("story", "bug", "task")


@rule("PHS-TAG-001")
def exactly_one_phase_tag(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if not item.is_open or item.type not in PHASED_TYPES or item.parent is None:
        return []
    parent = ctx.items.get(item.parent)
    if parent is None or not is_feature_epic(parent, ctx.profile):
        return []
    tags = list(item.phase_tags)
    if len(tags) == 1:
        return []
    return [Finding(
        rule_id="PHS-TAG-001",
        item_id=item.id,
        bucket="update",
        severity="high",
        message=f"Тегов фазы {len(tags)} вместо одного: {tags or 'нет ни одного'}",
        evidence={"phase_tags": tags, "epic": parent.id},
    )]


@rule("PHS-EPIC-002")
def feature_epic_required_fields(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if not is_feature_epic(item, ctx.profile):
        return []
    required = ctx.profile.get("phases.required_epic_fields")
    missing = [name for name in required if not item.extra.get(name)]
    if not missing:
        return []
    return [Finding(
        rule_id="PHS-EPIC-002",
        item_id=item.id,
        bucket="update",
        severity="high",
        message="Эпик фичи не готов к старту, нет атрибутов: " + ", ".join(missing),
        evidence={"missing": missing},
    )]


@rule("PHS-GROW-005")
def closed_epic_with_open_grow(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if item.is_open or not is_feature_epic(item, ctx.profile):
        return []
    grow_tag = ctx.profile.get("phases.grow_tag")
    open_grow = [
        child_id for child_id in ctx.children.get(item.id, [])
        if ctx.items[child_id].is_open and grow_tag in ctx.items[child_id].labels
    ]
    if not open_grow:
        return []
    return [Finding(
        rule_id="PHS-GROW-005",
        item_id=item.id,
        bucket="update",
        severity="high",
        message=f"Эпик закрыт при {len(open_grow)} открытых Grow-историях",
        evidence={"open_grow": open_grow},
    )]


@rule("PHS-SUP-007")
def one_support_epic_per_initiative(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if item.type != "initiative" or not item.is_open:
        return []
    support = [
        child_id for child_id in ctx.children.get(item.id, [])
        if is_support_epic(ctx.items[child_id], ctx.profile)
    ]
    if len(support) == 1:
        return []
    return [Finding(
        rule_id="PHS-SUP-007",
        item_id=item.id,
        bucket="link",
        severity="high",
        message=f"Support-эпиков у инициативы {len(support)}, должен быть ровно один",
        evidence={"support_epics": support},
    )]
