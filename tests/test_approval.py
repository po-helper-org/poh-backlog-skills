from pathlib import Path

from poh_backlog.approval import (has_decisions, read_approvals,
                                  read_rejections, rejections_to_decisions,
                                  split_by_approval)
from poh_backlog.catalog import load_catalog
from poh_backlog.model import BacklogItem, Finding
from poh_backlog.planner import build_plan, render_plan_md

CATALOG = load_catalog(Path(__file__).parent.parent / "poh_backlog" / "data" / "catalog.yaml")


def item(id_):
    return BacklogItem.from_dict({
        "id": id_, "type": "story", "title": id_, "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
    })


def sample_plan(n=2):
    findings = [Finding("HYG-STALE-001", f"S-{i}", "close", "medium", "стухло", {})
                for i in range(1, n + 1)]
    items = {f"S-{i}": item(f"S-{i}") for i in range(1, n + 1)}
    return build_plan(findings, CATALOG, items, max_actions=50)


def test_read_approvals_picks_checked_keys_only():
    text = ("- [x] `aaaa1111bbbb2222` **HYG-STALE-001** S-1 — propose_close — m\n"
            "- [ ] `cccc3333dddd4444` **HYG-STALE-001** S-2 — propose_close — m\n")
    assert read_approvals(text) == {"aaaa1111bbbb2222"}


def test_read_approvals_accepts_uppercase_marker():
    text = "- [X] `aaaa1111bbbb2222` **HYG-STALE-001** S-1 — propose_close — m\n"
    assert read_approvals(text) == {"aaaa1111bbbb2222"}


def test_read_rejections_picks_dash_marker_only():
    text = ("- [-] `aaaa1111bbbb2222` **HYG-STALE-001** S-1 — propose_close — m\n"
            "- [ ] `cccc3333dddd4444` **HYG-STALE-001** S-2 — propose_close — m\n"
            "- [x] `eeee5555ffff6666` **HYG-STALE-001** S-3 — propose_close — m\n")
    assert read_rejections(text) == {"aaaa1111bbbb2222"}


def test_has_decisions_false_for_untouched_plan():
    plan = sample_plan()
    text = render_plan_md(plan, "run-1")
    assert has_decisions(text) is False


def test_has_decisions_true_for_a_single_tick_or_reject():
    plan = sample_plan()
    key = plan.actions[0].action_key
    ticked = render_plan_md(plan, "run-1").replace(f"- [ ] `{key}`", f"- [x] `{key}`")
    rejected = render_plan_md(plan, "run-1").replace(f"- [ ] `{key}`", f"- [-] `{key}`")
    assert has_decisions(ticked) is True
    assert has_decisions(rejected) is True


def test_split_by_approval_leaves_untouched_action_undecided():
    plan = sample_plan()
    approved_key = plan.actions[0].action_key
    text = render_plan_md(plan, "run-1").replace(
        f"- [ ] `{approved_key}`", f"- [x] `{approved_key}`")
    result = split_by_approval(plan, text, shadow=False)
    assert [a.action_key for a in result.approved] == [approved_key]
    assert result.rejected == []
    assert len(result.undecided) == 1


def test_split_by_approval_flags_explicit_rejection():
    plan = sample_plan(3)
    approved_key = plan.actions[0].action_key
    rejected_key = plan.actions[1].action_key
    undecided_key = plan.actions[2].action_key
    text = render_plan_md(plan, "run-1")
    text = text.replace(f"- [ ] `{approved_key}`", f"- [x] `{approved_key}`")
    text = text.replace(f"- [ ] `{rejected_key}`", f"- [-] `{rejected_key}`")
    result = split_by_approval(plan, text, shadow=False)
    assert [a.action_key for a in result.approved] == [approved_key]
    assert [a.action_key for a in result.rejected] == [rejected_key]
    assert [a.action_key for a in result.undecided] == [undecided_key]


def test_shadow_mode_decides_nothing():
    # Режим shadow существует, чтобы копить размеченные данные бесплатно, не
    # запрещая план целиком: раньше (баг) он трактовал каждое действие как
    # отклонённое навсегда, что было противоположно цели shadow-режима.
    plan = sample_plan()
    text = render_plan_md(plan, "run-1").replace("- [ ] ", "- [x] ")
    result = split_by_approval(plan, text, shadow=True)
    assert result.approved == []
    assert result.rejected == []
    assert len(result.undecided) == 2


def test_rejections_become_decision_entries():
    plan = sample_plan()
    entries = rejections_to_decisions(plan.actions, reason="снято человеком")
    assert entries[0]["verdict"] == "rejected"
    assert entries[0]["reason"] == "снято человеком"
    assert entries[0]["suppress_until"] == "forever"
    assert entries[0]["rule_id"] == "HYG-STALE-001"
