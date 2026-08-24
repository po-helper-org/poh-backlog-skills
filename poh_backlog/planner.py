"""Планировщик: findings в корзины действий с ручным апрувом."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

from poh_backlog.catalog import ACTIONS as ALLOWED_OPS
from poh_backlog.catalog import RuleSpec
from poh_backlog.model import BacklogItem, Finding

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
BUCKET_TITLES = {
    "close": "Закрыть",
    "merge": "Объединить",
    "update": "Дозаполнить",
    "split": "Расщепить",
    "link": "Перелинковать",
    "no-action": "Без действий",
}


@dataclass(frozen=True)
class Action:
    action_key: str
    rule_id: str
    item_id: str
    bucket: str
    op: str
    rationale: str
    expected_effect: str | None


@dataclass(frozen=True)
class Plan:
    actions: list[Action] = field(default_factory=list)
    deferred: list[Action] = field(default_factory=list)


def _action_key(rule_id: str, item_id: str, revision: str) -> str:
    digest = hashlib.sha256(f"{rule_id}|{item_id}|{revision}".encode("utf-8"))
    return digest.hexdigest()[:16]


def _single_line(text: str) -> str:
    """Схлопывает любые пробельные последовательности (включая переносы строк)
    в единичный пробел и обрезает края.

    Это чисто визуальная нормализация для рендера строки чекбокса в plan.md:
    исходное значение (например, `Action.rationale`) не меняется, меняется
    только то, что попадает в текст `plan.md`. Без этого перенос строки или
    последовательность вида `- [ ] ` внутри rationale могла бы разорвать
    действие на отдельную строку, которая выглядит как ещё один чекбокс, но не
    несёт валидного `action_key`.
    """
    return re.sub(r"\s+", " ", text).strip()


def build_plan(findings: list[Finding], catalog: dict[str, RuleSpec],
               items: dict[str, BacklogItem], max_actions: int) -> Plan:
    actions: list[Action] = []
    for finding in findings:
        spec = catalog[finding.rule_id]
        if spec.action not in ALLOWED_OPS:
            raise ValueError(f"{spec.id}: недопустимая операция {spec.action}")
        item = items.get(finding.item_id)
        revision = item.updated_at.isoformat() if item else "unknown"
        actions.append(Action(
            action_key=_action_key(finding.rule_id, finding.item_id, revision),
            rule_id=finding.rule_id,
            item_id=finding.item_id,
            bucket=finding.bucket,
            op=spec.action,
            rationale=finding.message,
            expected_effect=spec.expected_effect,
        ))

    actions.sort(key=lambda a: (
        SEVERITY_ORDER.get(catalog[a.rule_id].severity, 9), a.item_id, a.rule_id))
    return Plan(actions=actions[:max_actions], deferred=actions[max_actions:])


def render_plan_md(plan: Plan, run_id: str) -> str:
    lines = [
        f"# План наведения порядка, прогон {run_id}",
        "",
        "Снятая галочка означает отказ: действие не исполняется и попадает в",
        "`decisions.yaml` как отклонённое. Отмеченные действия исполняет host-агент.",
        "",
        f"Всего действий: {len(plan.actions)}",
        f"Отложено до следующего прогона: {len(plan.deferred)}",
        "",
    ]
    by_bucket: dict[str, list[Action]] = {}
    for action in plan.actions:
        by_bucket.setdefault(action.bucket, []).append(action)

    for bucket, bucket_actions in by_bucket.items():
        lines.append(f"## {BUCKET_TITLES.get(bucket, bucket)} ({len(bucket_actions)})")
        lines.append("")
        for action in bucket_actions:
            lines.append(
                f"- [ ] `{action.action_key}` **{action.rule_id}** "
                f"{action.item_id} — {action.op} — {_single_line(action.rationale)}"
            )
        lines.append("")

    if plan.deferred:
        lines.append("## Отложено потолком max_actions_per_run")
        lines.append("")
        for action in plan.deferred:
            lines.append(f"- `{action.item_id}` — {action.rule_id} — {action.op}")
        lines.append("")
    return "\n".join(lines)


def plan_to_dict(plan: Plan) -> dict:
    return {
        "actions": [asdict(a) for a in plan.actions],
        "deferred": [asdict(a) for a in plan.deferred],
    }
