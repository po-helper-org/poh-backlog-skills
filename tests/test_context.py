from datetime import datetime, timezone

from poh_backlog.context import build_context, is_feature_epic, is_support_epic
from poh_backlog.model import BacklogItem
from poh_backlog.profile import Profile

NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)
PROFILE = Profile({"phases": {"support_label": "support"}})


def item(id_, type_="story", parent=None, labels=()):
    return BacklogItem.from_dict({
        "id": id_, "type": type_, "title": id_, "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "parent": parent, "labels": list(labels),
    })


def test_build_context_indexes_items_and_children():
    items = [item("I-1", "initiative"), item("E-1", "epic", parent="I-1"),
             item("S-1", parent="E-1"), item("S-2", parent="E-1")]
    ctx = build_context(items, PROFILE, NOW)
    assert set(ctx.items) == {"I-1", "E-1", "S-1", "S-2"}
    assert ctx.children["E-1"] == ["S-1", "S-2"]
    assert ctx.children["I-1"] == ["E-1"]
    assert ctx.children["S-1"] == []
    assert ctx.now == NOW


def test_feature_epic_versus_support_epic():
    feature = item("E-1", "epic")
    support = item("E-2", "epic", labels=("support",))
    story = item("S-1")
    assert is_feature_epic(feature, PROFILE) is True
    assert is_feature_epic(support, PROFILE) is False
    assert is_feature_epic(story, PROFILE) is False
    assert is_support_epic(support, PROFILE) is True
    assert is_support_epic(feature, PROFILE) is False


def test_dangling_parent_reference():
    """Проверяет, что элемент с несуществующим родителем не вызывает исключение.

    Элемент, чей parent указывает на несуществующий id, должен:
    - остаться в items
    - получить пустой список детей в children
    - не создавать запись для несуществующего parent в children
    """
    # Элемент со ссылкой на несуществующий parent
    story_with_missing_parent = item("S-1", parent="MISSING-PARENT")
    ctx = build_context([story_with_missing_parent], PROFILE, NOW)

    # (a) build_context не выбросил исключение
    assert True

    # (b) элемент присутствует в ctx.items
    assert "S-1" in ctx.items
    assert ctx.items["S-1"].id == "S-1"

    # (c) ctx.children содержит пустой список для элемента
    assert ctx.children["S-1"] == []

    # (d) ключ для несуществующего parent не был создан в ctx.children
    assert "MISSING-PARENT" not in ctx.children
