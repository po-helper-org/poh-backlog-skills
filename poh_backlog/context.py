"""Сборка контекста аудита и предикаты типов элементов."""
from __future__ import annotations

from datetime import datetime

from poh_backlog.model import AuditContext, BacklogItem
from poh_backlog.profile import Profile


def build_context(items: list[BacklogItem], profile: Profile, now: datetime) -> AuditContext:
    by_id = {item.id: item for item in items}
    children: dict[str, list[str]] = {item.id: [] for item in items}
    for item in items:
        if item.parent and item.parent in children:
            children[item.parent].append(item.id)
    return AuditContext(items=by_id, children=children, profile=profile, now=now)


def is_support_epic(item: BacklogItem, profile: Profile) -> bool:
    return item.type == "epic" and profile.get("phases.support_label") in item.labels


def is_feature_epic(item: BacklogItem, profile: Profile) -> bool:
    return item.type == "epic" and not is_support_epic(item, profile)
