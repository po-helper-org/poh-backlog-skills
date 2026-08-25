"""Движок аудита: прогон зарегистрированных правил по элементам."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from poh_backlog.catalog import RuleSpec
from poh_backlog.context import build_context
from poh_backlog.model import BacklogItem, Finding
from poh_backlog.profile import Profile
from poh_backlog.rules import RULES
from poh_backlog.suppress import Suppression, is_suppressed

# Импорт ради побочного эффекта: модули регистрируют свои функции в RULES
# через декоратор @rule при импорте. Без этих импортов RULES наполняется
# только если кто-то другой (например, тестовый модуль) успел импортировать
# poh_backlog.rules.hygiene/phases раньше — в проде (CLI) это не гарантировано,
# и тогда каждое правило считалось бы пропущенным, а находок не было бы
# никогда. Поэтому линтер не должен удалять эти импорты как "неиспользуемые":
# они используются ради регистрации, а не ради имён модулей.
import poh_backlog.rules.hygiene  # noqa: F401
import poh_backlog.rules.phases  # noqa: F401

# Правила, считающиеся на диффе снимков, а не по одному снимку.
# Их считает poh_backlog.diff, движок аудита их не трогает и не числит пропущенными.
DIFF_RULES = ("PHS-DRIFT-008",)


@dataclass(frozen=True)
class AuditResult:
    findings: list[Finding]
    skipped_rules: list[str]
    suppressed: int


def run_audit(
    items: list[BacklogItem],
    catalog: dict[str, RuleSpec],
    profile: Profile,
    now: datetime,
    suppressions: list[Suppression],
) -> AuditResult:
    ctx = build_context(items, profile, now)
    today = now.date()
    raw: list[Finding] = []
    skipped: list[str] = []

    for rule_id, spec in catalog.items():
        if rule_id in DIFF_RULES:
            continue
        if spec.kind == "judgment" or rule_id not in RULES:
            skipped.append(rule_id)
            continue
        fn = RULES[rule_id]
        for item in items:
            raw.extend(fn(item, ctx))

    kept = [f for f in raw if not is_suppressed(f, suppressions, today)]
    kept.sort(key=lambda f: (f.item_id, f.rule_id))
    return AuditResult(
        findings=kept,
        skipped_rules=sorted(skipped),
        suppressed=len(raw) - len(kept),
    )


def findings_to_dicts(findings: list[Finding]) -> list[dict]:
    return [asdict(f) for f in findings]
