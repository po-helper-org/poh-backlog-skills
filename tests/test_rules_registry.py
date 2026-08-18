"""Тесты для реестра правил poh_backlog.rules."""
import pytest

from poh_backlog.model import AuditContext, BacklogItem, Finding
from poh_backlog.rules import RULES, rule


@pytest.fixture
def rules_snapshot():
    """Снимает состояние RULES перед тестом и восстанавливает его после.

    Позволяет тестам безопасно регистрировать тестовые правила без
    загрязнения глобального реестра для других тестов.
    """
    original_rules = dict(RULES)
    yield
    # Восстанавливаем состояние
    RULES.clear()
    RULES.update(original_rules)


def test_rule_decorator_registers_function_under_fresh_id(rules_snapshot):
    """Проверяет регистрацию функции под новым id.

    Декоратор должен:
    - поместить функцию в RULES под переданным rule_id
    - вернуть исходную функцию без изменений (не оборачивать)
    """

    def test_rule_fn(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
        return []

    # Функция для сравнения идентичности
    original_fn = test_rule_fn

    # Применяем декоратор
    decorated = rule("TEST-DUMMY-001")(test_rule_fn)

    # Функция не была обёрнута
    assert decorated is original_fn

    # Функция зарегистрирована в RULES
    assert "TEST-DUMMY-001" in RULES
    assert RULES["TEST-DUMMY-001"] is original_fn


def test_rule_decorator_raises_on_duplicate_id(rules_snapshot):
    """Проверяет, что повторная регистрация одного id выбрасывает RuntimeError.

    При попытке зарегистрировать вторую функцию под уже занятым rule_id
    должно быть выброшено RuntimeError.
    """

    def first_fn(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
        return []

    def second_fn(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
        return []

    # Регистрируем первую функцию
    rule("TEST-DUMMY-002")(first_fn)

    # Попытка регистрации второй функции под тем же id должна выбросить исключение
    with pytest.raises(RuntimeError, match="Правило уже зарегистрировано"):
        rule("TEST-DUMMY-002")(second_fn)
