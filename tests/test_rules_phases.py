from datetime import datetime, timezone

import poh_backlog.rules.phases  # noqa: F401  регистрация правил
from poh_backlog.context import build_context
from poh_backlog.model import BacklogItem
from poh_backlog.profile import Profile
from poh_backlog.rules import RULES

NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)
PROFILE = Profile({"phases": {
    "mvp_tag": "mvp", "grow_tag": "grow", "support_label": "support",
    "required_epic_fields": ["business_metric", "due_date", "how_to_demo", "limitations"],
}})
FULL_EPIC_EXTRA = {
    "business_metric": "конверсия импорта +10%",
    "due_date": "2026-10-01",
    "how_to_demo": "Загрузить CSV на 100 строк и увидеть таблицу",
    "limitations": ["без валидации кодировок", "только UTF-8"],
}


def item(id_, type_="story", status="open", parent=None, labels=(), extra=None):
    return BacklogItem.from_dict({
        "id": id_, "type": type_, "title": id_, "status": status,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
        "parent": parent, "labels": list(labels), "extra": extra or {},
    })


def ctx(items):
    return build_context(items, PROFILE, NOW)


def test_story_in_feature_epic_without_phase_tag_flagged():
    epic = item("E-1", "epic", extra=FULL_EPIC_EXTRA)
    story = item("S-1", parent="E-1")
    findings = RULES["PHS-TAG-001"](story, ctx([epic, story]))
    assert len(findings) == 1
    assert findings[0].evidence["phase_tags"] == []


def test_story_with_both_tags_flagged():
    epic = item("E-1", "epic", extra=FULL_EPIC_EXTRA)
    story = item("S-1", parent="E-1", labels=("mvp", "grow"))
    findings = RULES["PHS-TAG-001"](story, ctx([epic, story]))
    assert len(findings) == 1
    assert findings[0].evidence["phase_tags"] == ["mvp", "grow"]


def test_story_with_one_tag_clean():
    epic = item("E-1", "epic", extra=FULL_EPIC_EXTRA)
    story = item("S-1", parent="E-1", labels=("mvp",))
    assert RULES["PHS-TAG-001"](story, ctx([epic, story])) == []


def test_story_in_support_epic_not_required_to_have_phase_tag():
    support = item("E-2", "epic", labels=("support",))
    story = item("S-2", parent="E-2")
    assert RULES["PHS-TAG-001"](story, ctx([support, story])) == []


def test_feature_epic_missing_fields_flagged():
    epic = item("E-1", "epic", extra={"business_metric": "x"})
    findings = RULES["PHS-EPIC-002"](epic, ctx([epic]))
    assert len(findings) == 1
    assert findings[0].evidence["missing"] == ["due_date", "how_to_demo", "limitations"]


def test_complete_feature_epic_clean():
    epic = item("E-1", "epic", extra=FULL_EPIC_EXTRA)
    assert RULES["PHS-EPIC-002"](epic, ctx([epic])) == []


def test_support_epic_exempt_from_required_fields():
    support = item("E-2", "epic", labels=("support",))
    assert RULES["PHS-EPIC-002"](support, ctx([support])) == []


def test_closed_epic_with_open_grow_children_flagged():
    epic = item("E-1", "epic", status="closed", extra=FULL_EPIC_EXTRA)
    grow = item("S-1", parent="E-1", labels=("grow",))
    findings = RULES["PHS-GROW-005"](epic, ctx([epic, grow]))
    assert len(findings) == 1
    assert findings[0].evidence["open_grow"] == ["S-1"]


def test_closed_epic_without_open_grow_clean():
    epic = item("E-1", "epic", status="closed", extra=FULL_EPIC_EXTRA)
    done = item("S-1", parent="E-1", status="closed", labels=("grow",))
    assert RULES["PHS-GROW-005"](epic, ctx([epic, done])) == []


def test_initiative_without_support_epic_flagged():
    initiative = item("I-1", "initiative")
    feature = item("E-1", "epic", parent="I-1", extra=FULL_EPIC_EXTRA)
    findings = RULES["PHS-SUP-007"](initiative, ctx([initiative, feature]))
    assert len(findings) == 1
    assert findings[0].evidence["support_epics"] == []


def test_initiative_with_two_support_epics_flagged():
    initiative = item("I-1", "initiative")
    s1 = item("E-1", "epic", parent="I-1", labels=("support",))
    s2 = item("E-2", "epic", parent="I-1", labels=("support",))
    findings = RULES["PHS-SUP-007"](initiative, ctx([initiative, s1, s2]))
    assert findings[0].evidence["support_epics"] == ["E-1", "E-2"]


def test_initiative_with_exactly_one_support_epic_clean():
    initiative = item("I-1", "initiative")
    support = item("E-1", "epic", parent="I-1", labels=("support",))
    assert RULES["PHS-SUP-007"](initiative, ctx([initiative, support])) == []
