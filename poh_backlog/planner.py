"""Планировщик: findings в корзины действий с ручным апрувом."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

from poh_backlog.catalog import ACTIONS as ALLOWED_OPS
from poh_backlog.catalog import RuleSpec
from poh_backlog.model import BacklogItem, Finding

RUN_ID_MARK = re.compile(r"^<!--\s*run_id:\s*(\S+)\s*-->\s*$", re.MULTILINE)

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
BUCKET_TITLES = {
    "close": "Закрыть",
    "merge": "Объединить",
    "update": "Дозаполнить",
    "split": "Расщепить",
    "link": "Перелинковать",
    "no-action": "Без действий",
}

# Префикс машинного следа. Каждое исполненное действие оставляет на элементе
# метку poh:<rule_id>: в канонической модели комментариев нет, поэтому
# доказательством факта применения служит метка, а не текст комментария.
TRACE_PREFIX = "poh:"


def trace_label(rule_id: str) -> str:
    """Метка, которую host-агент обязан поставить, исполнив действие."""
    return f"{TRACE_PREFIX}{rule_id}"


@dataclass(frozen=True)
class Action:
    action_key: str
    rule_id: str
    item_id: str
    bucket: str
    op: str
    rationale: str
    expected_effect: str | None
    trace_label: str = ""
    # Прогон, в котором действие уже утверждали, если оно вернулось как
    # неисполненное. None означает, что действие пришло из свежей находки.
    promised_from: str | None = None


@dataclass(frozen=True)
class Plan:
    actions: list[Action] = field(default_factory=list)
    deferred: list[Action] = field(default_factory=list)
    # Заполняются cli.cmd_run уже после build_plan (через dataclasses.replace):
    # build_plan не знает, из какого запуска CLI он вызван. run_id и shadow
    # прогона, породившего этот план, попадают в plan.json, чтобы approve
    # не мог с ним разойтись: shadow нельзя обойти, забыв флаг на стороне
    # approve, а run_id позволяет обнаружить, что plan.md был перезаписан
    # более новым прогоном, пока галочки в нём относились к старому.
    run_id: str | None = None
    shadow: bool = False


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
            trace_label=trace_label(finding.rule_id),
        ))

    actions.sort(key=lambda a: (
        SEVERITY_ORDER.get(catalog[a.rule_id].severity, 9), a.item_id, a.rule_id))
    return Plan(actions=actions[:max_actions], deferred=actions[max_actions:])


def promised_actions(verdicts: list[dict], catalog: dict[str, RuleSpec],
                     items: dict[str, BacklogItem], run_id: str) -> list[Action]:
    """Действия, которые человек утвердил, а host не довёл до эффекта.

    Возвращаются в план следующего прогона с пустой галочкой: одно
    утверждение не может действовать вечно, поэтому нужно новое решение.
    Ключ пересчитывается по текущему состоянию элемента — старый ключ
    относился к той ревизии, которой уже нет.
    """
    result: list[Action] = []
    for verdict in verdicts:
        if verdict.get("status") == "done":
            continue
        rule_id = verdict["rule_id"]
        item_id = verdict["item_id"]
        spec = catalog.get(rule_id)
        if spec is None:
            continue
        item = items.get(item_id)
        revision = item.updated_at.isoformat() if item else "unknown"
        # Исходная причина, по которой действие вообще предложили (см. finding
        # 4 финального ревью): она должна дойти до человека вместе с заметкой
        # verify о том, почему подтверждение не засчиталось, а не вместо неё.
        # Старые verdicts.json без поля rationale деградируют на дефолт, а не
        # падают.
        original = verdict.get("rationale") or "Утверждено ранее, но не исполнено"
        note = verdict.get("note")
        rationale = f"{original} — {note}" if note else original
        result.append(Action(
            action_key=_action_key(rule_id, item_id, revision),
            rule_id=rule_id,
            item_id=item_id,
            bucket=spec.bucket,
            op=spec.action,
            rationale=rationale,
            expected_effect=spec.expected_effect,
            trace_label=trace_label(rule_id),
            promised_from=run_id,
        ))
    return result


def read_run_id(plan_md: str) -> str | None:
    """Читает машиночитаемую метку прогона, которую пишет `render_plan_md`.

    Используется `cli.cmd_approve`, чтобы сверить, к какому прогону
    относится `plan.md`, с run_id, записанным в `plan.json`: если файлы
    разошлись (например, `plan.md` перезаписан более новым `run`, пока
    старый `plan.json` ещё лежит рядом), апрув обязан отказаться, а не
    молча принять решения, снятые с чужого плана.
    """
    match = RUN_ID_MARK.search(plan_md)
    return match.group(1) if match else None


def render_plan_md(plan: Plan, run_id: str) -> str:
    lines = [
        f"# План наведения порядка, прогон {run_id}",
        f"<!-- run_id: {run_id} -->",
        "",
        "У каждого действия три состояния, а не два:",
        "поставьте `[x]` — действие утверждено и уйдёт в `approved.json`;",
        "поставьте `[-]` — действие отклонено навсегда и уйдёт в",
        "`decisions.yaml` как подавление; оставьте `[ ]` нетронутым — решения",
        "нет, действие не исполняется и не подавляется, а вернётся в план",
        "следующего прогона.",
        "",
        f"Всего действий: {len(plan.actions)}",
        f"Отложено до следующего прогона: {len(plan.deferred)}",
        "",
    ]
    promised = [a for a in plan.actions if a.promised_from is not None]
    fresh = [a for a in plan.actions if a.promised_from is None]

    if promised:
        lines.append(f"## Обещано, не сделано ({len(promised)})")
        lines.append("")
        lines.append(
            "Эти действия человек уже утверждал, но эффекта не случилось. "
            "Утверждение не действует вечно — нужно новое решение."
        )
        lines.append("")
        for action in promised:
            lines.append(
                f"- [ ] `{action.action_key}` **{action.rule_id}** "
                f"{action.item_id} — {action.op} — утверждено в прогоне "
                f"{action.promised_from} — {_single_line(action.rationale)}"
            )
        lines.append("")

    by_bucket: dict[str, list[Action]] = {}
    for action in fresh:
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
        "run_id": plan.run_id,
        "shadow": plan.shadow,
    }
