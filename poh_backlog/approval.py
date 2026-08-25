"""Гейт апрува: три состояния действия, а не два.

Молчание — это "не решено", а не отказ. Из трёх отметок, которые может нести
строка чекбокса в `plan.md`, только явные несут решение:

- `- [x]` — утверждено человеком, действие уходит в `approved.json`;
- `- [-]` — явно отклонено человеком, действие уходит в `decisions.yaml` как
  постоянное подавление;
- `- [ ]` — нетронуто: решения не было, действие не подавляется и не
  исполняется, а просто возвращается в план следующего прогона.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from poh_backlog.planner import Action, Plan

CHECKED = re.compile(r"^\s*-\s*\[[xX]\]\s*`([0-9a-f]{16})`", re.MULTILINE)
REJECTED = re.compile(r"^\s*-\s*\[-\]\s*`([0-9a-f]{16})`", re.MULTILINE)


@dataclass(frozen=True)
class ApprovalResult:
    approved: list[Action] = field(default_factory=list)
    rejected: list[Action] = field(default_factory=list)
    undecided: list[Action] = field(default_factory=list)


def read_approvals(plan_md: str) -> set[str]:
    return set(CHECKED.findall(plan_md))


def read_rejections(plan_md: str) -> set[str]:
    return set(REJECTED.findall(plan_md))


def has_decisions(plan_md: str) -> bool:
    """Есть ли в `plan_md` хоть одна проставленная отметка — галочка или
    явный отказ. Используется, чтобы не дать `run` затереть план, в
    который человек уже внёс решения."""
    return bool(CHECKED.search(plan_md) or REJECTED.search(plan_md))


def split_by_approval(plan: Plan, plan_md: str, shadow: bool) -> ApprovalResult:
    if shadow:
        # Shadow-режим существует, чтобы копить размеченные данные бесплатно,
        # а не чтобы запрещать план целиком: он не решает ничего сам —
        # каждое действие остаётся не решённым, независимо от того, что
        # проставлено в plan_md.
        return ApprovalResult(approved=[], rejected=[], undecided=list(plan.actions))
    approved_keys = read_approvals(plan_md)
    rejected_keys = read_rejections(plan_md)
    approved = [a for a in plan.actions if a.action_key in approved_keys]
    rejected = [a for a in plan.actions if a.action_key in rejected_keys]
    undecided = [a for a in plan.actions
                if a.action_key not in approved_keys and a.action_key not in rejected_keys]
    return ApprovalResult(approved=approved, rejected=rejected, undecided=undecided)


def rejections_to_decisions(rejected: list[Action], reason: str) -> list[dict]:
    return [{
        "rule_id": action.rule_id,
        "item": action.item_id,
        "verdict": "rejected",
        "reason": reason,
        "suppress_until": "forever",
    } for action in rejected]
