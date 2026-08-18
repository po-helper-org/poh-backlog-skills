"""Реестр реализаций правил: rule_id -> функция."""
from __future__ import annotations

from typing import Callable

from poh_backlog.model import AuditContext, BacklogItem, Finding

RuleFn = Callable[[BacklogItem, AuditContext], list[Finding]]

RULES: dict[str, RuleFn] = {}


def rule(rule_id: str) -> Callable[[RuleFn], RuleFn]:
    def decorator(fn: RuleFn) -> RuleFn:
        if rule_id in RULES:
            raise RuntimeError(f"Правило уже зарегистрировано: {rule_id}")
        RULES[rule_id] = fn
        return fn

    return decorator
