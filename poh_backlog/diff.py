"""Снимки состояния, дифф между прогонами и дрейф фаз."""
from __future__ import annotations

from dataclasses import dataclass, field

from poh_backlog.model import BacklogItem, Finding
from poh_backlog.profile import Profile

TRACKED = ("updated_at", "status", "labels", "estimate", "parent")
DRIFT_MARKER = "[phase-change]"


def take_snapshot(items: list[BacklogItem]) -> dict:
    return {"items": {
        item.id: {
            "updated_at": item.updated_at.isoformat(),
            "status": item.status,
            "labels": list(item.labels),
            "estimate": item.estimate,
            "parent": item.parent,
            # Служебное поле для PHS-DRIFT-008: было ли в описании
            # обоснование [phase-change] на момент этого снимка. Не входит
            # в TRACKED — это внутренняя бухгалтерия правила дрейфа фаз, а
            # не отслеживаемое пользователем поле.
            "phase_change_marker_present": DRIFT_MARKER in item.description,
        }
        for item in items
    }}


@dataclass(frozen=True)
class DiffReport:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: dict[str, dict] = field(default_factory=dict)


def diff_snapshots(prev: dict | None, curr: dict) -> DiffReport:
    prev_items = (prev or {}).get("items", {})
    curr_items = curr.get("items", {})
    added = sorted(set(curr_items) - set(prev_items))
    removed = sorted(set(prev_items) - set(curr_items))
    changed: dict[str, dict] = {}
    for item_id in sorted(set(prev_items) & set(curr_items)):
        delta = {
            key: {"from": prev_items[item_id][key], "to": curr_items[item_id][key]}
            for key in TRACKED
            if prev_items[item_id].get(key) != curr_items[item_id].get(key)
        }
        if delta:
            changed[item_id] = delta
    return DiffReport(added=added, removed=removed, changed=changed)


def detect_phase_drift(prev: dict | None, items: list[BacklogItem],
                       profile: Profile) -> list[Finding]:
    prev_items = (prev or {}).get("items", {})
    mvp = profile.get("phases.mvp_tag")
    grow = profile.get("phases.grow_tag")
    findings: list[Finding] = []
    for item in items:
        before = prev_items.get(item.id)
        if before is None:
            continue
        was_grow = grow in before.get("labels", [])
        now_mvp = mvp in item.labels
        if not (was_grow and now_mvp):
            continue
        # Маркер оправдывает только тот перенос, который он сопровождал:
        # находка гасится, только если маркер появился именно сейчас — его
        # не было в предыдущем снимке. Если он уже стоял там, он обосновывал
        # более ранний перенос и не спасает от текущей находки. Снимок,
        # сделанный до появления этого ключа, ключа не содержит — тогда
        # `.get(..., False)` трактует отсутствие ключа как "маркера не было",
        # что сохраняет обратную совместимость со старыми снимками.
        marker_now = DRIFT_MARKER in item.description
        marker_before = before.get("phase_change_marker_present", False)
        if marker_now and not marker_before:
            continue
        findings.append(Finding(
            rule_id="PHS-DRIFT-008",
            item_id=item.id,
            bucket="update",
            severity="high",
            message="История переведена из grow в mvp без обоснования",
            evidence={"from": grow, "to": mvp},
        ))
    return findings


def render_report_md(diff: DiffReport, findings_now: int, findings_prev: int) -> str:
    lines = [
        "# Изменения с прошлого прогона",
        "",
        f"- Добавлено: {len(diff.added)}",
        f"- Удалено: {len(diff.removed)}",
        f"- Изменено: {len(diff.changed)}",
        f"- Находок: {findings_prev} -> {findings_now}",
        "",
    ]
    if diff.changed:
        lines.append("## Изменённые элементы")
        lines.append("")
        for item_id, delta in diff.changed.items():
            fields = ", ".join(sorted(delta))
            lines.append(f"- `{item_id}` — поля: {fields}")
        lines.append("")
    return "\n".join(lines)
