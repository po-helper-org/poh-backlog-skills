from datetime import datetime, timedelta, timezone

import poh_backlog.rules.hygiene  # noqa: F401  регистрация правил
from poh_backlog.context import build_context
from poh_backlog.model import BacklogItem
from poh_backlog.profile import Profile
from poh_backlog.rules import RULES

NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)
PROFILE = Profile({
    "staleness": {"story_days": 60, "bug_days": 30},
    "description": {"min_words": 20},
    "phases": {"support_label": "support"},
})
LONG_TEXT = " ".join(["слово"] * 25)


def item(id_, **over):
    raw = {
        "id": id_, "type": "story", "title": id_, "status": "open",
        "description": LONG_TEXT,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": (NOW - timedelta(days=1)).isoformat(),
        "parent": "E-1", "estimate": 3.0, "labels": ["mvp"],
    }
    raw.update(over)
    return BacklogItem.from_dict(raw)


def ctx(items):
    return build_context(items, PROFILE, NOW)


def test_stale_story_flagged_after_threshold():
    old = item("S-1", updated_at=(NOW - timedelta(days=61)).isoformat())
    findings = RULES["HYG-STALE-001"](old, ctx([old]))
    assert len(findings) == 1
    assert findings[0].bucket == "close"
    assert findings[0].evidence["days_since_update"] == 61


def test_stale_bug_uses_bug_threshold():
    bug = item("B-1", type="bug", updated_at=(NOW - timedelta(days=31)).isoformat())
    assert RULES["HYG-STALE-001"](bug, ctx([bug]))


def test_fresh_and_closed_items_not_flagged():
    fresh = item("S-2")
    closed = item("S-3", status="closed",
                  updated_at=(NOW - timedelta(days=400)).isoformat())
    assert RULES["HYG-STALE-001"](fresh, ctx([fresh])) == []
    assert RULES["HYG-STALE-001"](closed, ctx([closed])) == []


def test_short_description_flagged():
    short = item("S-4", description="слишком коротко")
    findings = RULES["HYG-DESC-002"](short, ctx([short]))
    assert len(findings) == 1
    assert findings[0].bucket == "update"
    assert findings[0].evidence["word_count"] == 2


def test_long_description_not_flagged():
    assert RULES["HYG-DESC-002"](item("S-5"), ctx([item("S-5")])) == []


def test_missing_estimate_flagged_only_for_open_story():
    no_est = item("S-6", estimate=None)
    epic = item("E-9", type="epic", estimate=None)
    assert len(RULES["HYG-EST-003"](no_est, ctx([no_est]))) == 1
    assert RULES["HYG-EST-003"](epic, ctx([epic])) == []


def test_orphan_story_flagged():
    orphan = item("S-7", parent=None)
    findings = RULES["HYG-ORPHAN-004"](orphan, ctx([orphan]))
    assert len(findings) == 1
    assert findings[0].bucket == "link"


def test_initiative_without_parent_not_orphan():
    top = item("I-1", type="initiative", parent=None)
    assert RULES["HYG-ORPHAN-004"](top, ctx([top])) == []
