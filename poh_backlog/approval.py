"""Гейт апрува: только отмеченные галочкой действия подлежат исполнению."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from poh_backlog.planner import Action, Plan

CHECKED = re.compile(r"^\s*-\s*\[[xX]\]\s*`([0-9a-f]{16})`", re.MULTILINE)


@dataclass(frozen=True)
class ApprovalResult:
    approved: list[Action] = field(default_factory=list)
    rejected: list[Action] = field(default_factory=list)


def read_approvals(plan_md: str) -> set[str]:
    return set(CHECKED.findall(plan_md))


def split_by_approval(plan: Plan, plan_md: str, shadow: bool) -> ApprovalResult:
    if shadow:
        return ApprovalResult(approved=[], rejected=list(plan.actions))
    keys = read_approvals(plan_md)
    approved = [a for a in plan.actions if a.action_key in keys]
    rejected = [a for a in plan.actions if a.action_key not in keys]
    return ApprovalResult(approved=approved, rejected=rejected)


def rejections_to_decisions(rejected: list[Action], reason: str) -> list[dict]:
    return [{
        "rule_id": action.rule_id,
        "item": action.item_id,
        "verdict": "rejected",
        "reason": reason,
        "suppress_until": "forever",
    } for action in rejected]
