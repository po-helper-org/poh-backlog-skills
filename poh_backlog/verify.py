"""Проверка исполнения: случилось ли утверждённое и дало ли эффект.

Сверка идёт по паре (rule_id, item_id), а не по action_key: ключ содержит
updated_at элемента, а исполнение действия почти всегда его меняет, поэтому
ключ из approved.json не переживает цикл «применили — проверяем».
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

# Импорт ради регистрации правил в реестре RULES: режим finding_gone
# перепрогоняет правило по свежим данным, а без этих импортов реестр пуст.
import poh_backlog.rules.hygiene  # noqa: F401
import poh_backlog.rules.phases  # noqa: F401
from poh_backlog.catalog import RuleSpec
from poh_backlog.context import build_context
from poh_backlog.diff import diff_snapshots, take_snapshot
from poh_backlog.model import BacklogItem
from poh_backlog.planner import trace_label
from poh_backlog.profile import Profile
from poh_backlog.rules import RULES

STATUSES = ("done", "no_effect", "not_applied")


@dataclass(frozen=True)
class Verdict:
    action_key: str
    rule_id: str
    item_id: str
    op: str
    status: str
    note: str
    # Исходное обоснование действия (Action.rationale из approved.json), а не
    # заметка о проверке: без него promised_actions вынужден подменять
    # причину, по которой действие вообще предложили, служебной строкой
    # verify — «утверждено в прогоне r1 — Нет следа исполнения: ...» вместо
    # изначального «Нет оценки: элемент не проходит Definition of Ready».
    rationale: str = ""


@dataclass(frozen=True)
class VerifyResult:
    verdicts: list[Verdict] = field(default_factory=list)
    collateral: list[str] = field(default_factory=list)
    fidelity: float = 0.0
    # Была ли вообще выполнена сверка побочного урона: без снимка «до»
    # сравнивать не с чем, и пустой result.collateral в этом случае значит
    # не «ничего лишнего не изменилось», а «сравнение не проводилось».
    collateral_checked: bool = False


NOTE_EFFECT_CONFIRMED = "Действие исполнено, эффект подтверждён"
NOTE_FINDING_SURVIVES = "След есть, но находка сохраняется: результата нет"
NOTE_RULE_NOT_EXECUTED = (
    "Правило не исполняется в этом срезе, поэтому эффект проверить нечем"
)


def _effect_reached(rule_id: str, item: BacklogItem, ctx, mode: str) -> tuple[bool, str]:
    """Возвращает (эффект подтверждён, пояснение для итоговой заметки).

    Пояснение различает две причины, по которым эффект не подтверждён:
    правило перепрогнали и находка сохранилась — или перепрогнать было
    нечем, и об исполнении вообще ничего не известно.
    """
    if mode == "trace_label":
        # Метка уже проверена вызывающим: для этого режима она и есть эффект.
        return True, NOTE_EFFECT_CONFIRMED
    fn = RULES.get(rule_id)
    if fn is None:
        # Правило объявлено в каталоге, но реализации нет (например,
        # правило-суждение). Перепрогнать нечем, поэтому нельзя утверждать
        # ни что эффект достигнут, ни что находка проверена и сохранилась.
        return False, NOTE_RULE_NOT_EXECUTED
    findings = fn(item, ctx)
    if len(findings) == 0:
        return True, NOTE_EFFECT_CONFIRMED
    return False, NOTE_FINDING_SURVIVES


def verify_actions(approved: list[dict], items: list[BacklogItem],
                   catalog: dict[str, RuleSpec], profile: Profile,
                   now: datetime, prev_snapshot: dict | None) -> VerifyResult:
    ctx = build_context(items, profile, now)
    by_id = ctx.items
    verdicts: list[Verdict] = []

    for entry in approved:
        rule_id = entry["rule_id"]
        item_id = entry["item_id"]
        label = entry.get("trace_label") or trace_label(rule_id)
        item = by_id.get(item_id)
        rationale = entry.get("rationale", "")

        if item is None:
            verdicts.append(Verdict(
                action_key=entry["action_key"], rule_id=rule_id, item_id=item_id,
                op=entry["op"], status="not_applied",
                note="Элемент не найден в свежем срезе беклога",
                rationale=rationale,
            ))
            continue

        if label not in item.labels:
            verdicts.append(Verdict(
                action_key=entry["action_key"], rule_id=rule_id, item_id=item_id,
                op=entry["op"], status="not_applied",
                note=f"Нет следа исполнения: метка {label} отсутствует",
                rationale=rationale,
            ))
            continue

        mode = catalog[rule_id].expected_effect
        reached, note = _effect_reached(rule_id, item, ctx, mode)
        verdicts.append(Verdict(
            action_key=entry["action_key"], rule_id=rule_id, item_id=item_id,
            op=entry["op"], status="done" if reached else "no_effect",
            note=note, rationale=rationale,
        ))

    targets = {entry["item_id"] for entry in approved}
    collateral: list[str] = []
    if prev_snapshot is not None:
        changed = diff_snapshots(prev_snapshot, take_snapshot(items)).changed
        collateral = sorted(set(changed) - targets)

    done = sum(1 for v in verdicts if v.status == "done")
    fidelity = done / len(verdicts) if verdicts else 0.0
    return VerifyResult(verdicts=verdicts, collateral=collateral,
                        fidelity=fidelity,
                        collateral_checked=prev_snapshot is not None)


def verdicts_to_dicts(verdicts: list[Verdict]) -> list[dict]:
    return [asdict(v) for v in verdicts]


STATUS_TITLES = {
    "done": "Исполнено и сработало",
    "no_effect": "Исполнено, но эффекта нет",
    "not_applied": "Не исполнено",
}


def render_verify_md(result: VerifyResult, run_id: str) -> str:
    percent = round(result.fidelity * 100)
    lines = [
        f"# Проверка исполнения, прогон {run_id}",
        "",
        f"Действий проверено: {len(result.verdicts)}",
        f"Достоверность исполнения: {percent}%",
        "",
    ]
    for status in STATUSES:
        group = [v for v in result.verdicts if v.status == status]
        if not group:
            continue
        lines.append(f"## {STATUS_TITLES[status]} ({len(group)})")
        lines.append("")
        for verdict in group:
            lines.append(
                f"- **{verdict.rule_id}** {verdict.item_id} — "
                f"{verdict.op} — {verdict.note}"
            )
        lines.append("")

    lines.append(f"## Изменено вне плана ({len(result.collateral)})")
    lines.append("")
    if not result.collateral_checked:
        lines.append(
            "Снимок «до» не найден: сравнение с текущим срезом беклога "
            "пропущено, этот раздел ничего не доказывает."
        )
    elif result.collateral:
        lines.append(
            "Эти элементы изменились, не будучи целями утверждённых действий. "
            "Беклог живёт своей жизнью, поэтому это предупреждение, а не ошибка."
        )
        lines.append("")
        for item_id in result.collateral:
            lines.append(f"- `{item_id}`")
    else:
        lines.append("Изменений вне списка целей не обнаружено.")
    lines.append("")
    return "\n".join(lines)
