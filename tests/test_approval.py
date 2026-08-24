from pathlib import Path

from poh_backlog.approval import (read_approvals, rejections_to_decisions,
                                  split_by_approval)
from poh_backlog.catalog import load_catalog
from poh_backlog.model import BacklogItem, Finding
from poh_backlog.planner import build_plan, render_plan_md

CATALOG = load_catalog(Path(__file__).parent.parent / "rules" / "catalog.yaml")


def item(id_):
    return BacklogItem.from_dict({
        "id": id_, "type": "story", "title": id_, "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
    })


def sample_plan():
    findings = [
        Finding("HYG-STALE-001", "S-1", "close", "medium", "стухло", {}),
        Finding("HYG-STALE-001", "S-2", "close", "medium", "стухло", {}),
    ]
    items = {"S-1": item("S-1"), "S-2": item("S-2")}
    return build_plan(findings, CATALOG, items, max_actions=50)


def test_read_approvals_picks_checked_keys_only():
    text = ("- [x] `aaaa1111bbbb2222` **HYG-STALE-001** S-1 — propose_close — m\n"
            "- [ ] `cccc3333dddd4444` **HYG-STALE-001** S-2 — propose_close — m\n")
    assert read_approvals(text) == {"aaaa1111bbbb2222"}


def test_read_approvals_accepts_uppercase_marker():
    text = "- [X] `aaaa1111bbbb2222` **HYG-STALE-001** S-1 — propose_close — m\n"
    assert read_approvals(text) == {"aaaa1111bbbb2222"}


def test_split_by_approval_separates_actions():
    plan = sample_plan()
    approved_key = plan.actions[0].action_key
    text = render_plan_md(plan, "run-1").replace(
        f"- [ ] `{approved_key}`", f"- [x] `{approved_key}`")
    result = split_by_approval(plan, text, shadow=False)
    assert [a.action_key for a in result.approved] == [approved_key]
    assert len(result.rejected) == 1


def test_shadow_mode_approves_nothing():
    plan = sample_plan()
    text = render_plan_md(plan, "run-1").replace("- [ ] ", "- [x] ")
    result = split_by_approval(plan, text, shadow=True)
    assert result.approved == []
    assert len(result.rejected) == 2


def test_rejections_become_decision_entries():
    plan = sample_plan()
    entries = rejections_to_decisions(plan.actions, reason="снято человеком")
    assert entries[0]["verdict"] == "rejected"
    assert entries[0]["reason"] == "снято человеком"
    assert entries[0]["suppress_until"] == "forever"
    assert entries[0]["rule_id"] == "HYG-STALE-001"
