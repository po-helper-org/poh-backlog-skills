from datetime import datetime, timezone

from poh_backlog.model import BacklogItem


RAW = {
    "id": "GH-412",
    "type": "story",
    "title": "Импорт CSV",
    "description": "Пользователь загружает файл",
    "status": "open",
    "created_at": "2026-01-10T10:00:00+00:00",
    "updated_at": "2026-03-01T12:30:00+00:00",
    "labels": ["mvp", "backend"],
    "parent": "GH-400",
    "estimate": 3.0,
    "extra": {"how_to_demo": None},
}


def test_from_dict_parses_all_fields():
    item = BacklogItem.from_dict(RAW)
    assert item.id == "GH-412"
    assert item.type == "story"
    assert item.labels == ("mvp", "backend")
    assert item.parent == "GH-400"
    assert item.estimate == 3.0
    assert item.created_at == datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc)
    assert item.updated_at == datetime(2026, 3, 1, 12, 30, tzinfo=timezone.utc)


def test_missing_optional_fields_default():
    item = BacklogItem.from_dict({
        "id": "GH-1",
        "type": "story",
        "title": "t",
        "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    assert item.description == ""
    assert item.labels == ()
    assert item.parent is None
    assert item.estimate is None
    assert item.extra == {}


def test_phase_tags_returns_only_phase_labels():
    item = BacklogItem.from_dict({**RAW, "labels": ["mvp", "grow", "backend"]})
    assert item.phase_tags == ("mvp", "grow")


def test_phase_tags_for_returns_only_labels_from_given_names():
    item = BacklogItem.from_dict({**RAW, "labels": ["этап-mvp", "backend", "grow"]})
    assert item.phase_tags_for(("этап-mvp", "этап-grow")) == ("этап-mvp",)
    assert item.phase_tags_for(("нет-такого",)) == ()


def test_is_open():
    assert BacklogItem.from_dict(RAW).is_open is True
    assert BacklogItem.from_dict({**RAW, "status": "closed"}).is_open is False
