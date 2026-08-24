from pathlib import Path

from poh_backlog.catalog import load_catalog
from poh_backlog.model import BacklogItem, Finding
from poh_backlog.planner import (ALLOWED_OPS, build_plan, plan_to_dict,
                                 render_plan_md)

CATALOG = load_catalog(Path(__file__).parent.parent / "rules" / "catalog.yaml")


def item(id_, updated="2026-08-01T00:00:00+00:00"):
    return BacklogItem.from_dict({
        "id": id_, "type": "story", "title": f"Заголовок {id_}", "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": updated,
    })


def finding(rule_id="HYG-STALE-001", item_id="S-1", severity="medium"):
    return Finding(rule_id=rule_id, item_id=item_id, bucket="close",
                   severity=severity, message="Нет активности 200 дней", evidence={})


def test_action_key_is_stable_for_same_revision():
    items = {"S-1": item("S-1")}
    first = build_plan([finding()], CATALOG, items, max_actions=50)
    second = build_plan([finding()], CATALOG, items, max_actions=50)
    assert first.actions[0].action_key == second.actions[0].action_key


def test_action_key_changes_when_item_revision_changes():
    a = build_plan([finding()], CATALOG, {"S-1": item("S-1")}, max_actions=50)
    b = build_plan([finding()], CATALOG,
                   {"S-1": item("S-1", updated="2026-08-02T00:00:00+00:00")},
                   max_actions=50)
    assert a.actions[0].action_key != b.actions[0].action_key


def test_op_comes_from_catalog_and_is_allowed():
    plan = build_plan([finding()], CATALOG, {"S-1": item("S-1")}, max_actions=50)
    assert plan.actions[0].op == "propose_close"
    assert plan.actions[0].op in ALLOWED_OPS


def test_high_severity_sorted_first():
    findings = [finding(severity="low", item_id="S-1"),
                finding(rule_id="PHS-TAG-001", severity="high", item_id="S-2")]
    items = {"S-1": item("S-1"), "S-2": item("S-2")}
    plan = build_plan(findings, CATALOG, items, max_actions=50)
    assert plan.actions[0].item_id == "S-2"


def test_cap_moves_rest_to_deferred():
    findings = [finding(item_id=f"S-{i}") for i in range(5)]
    items = {f"S-{i}": item(f"S-{i}") for i in range(5)}
    plan = build_plan(findings, CATALOG, items, max_actions=2)
    assert len(plan.actions) == 2
    assert len(plan.deferred) == 3


def test_plan_md_lists_checkboxes_and_deferred_explicitly():
    findings = [finding(item_id=f"S-{i}") for i in range(3)]
    items = {f"S-{i}": item(f"S-{i}") for i in range(3)}
    plan = build_plan(findings, CATALOG, items, max_actions=2)
    text = render_plan_md(plan, run_id="2026-08-18-01")
    assert text.count("- [ ] ") == 2
    assert "Отложено до следующего прогона: 1" in text
    assert plan.actions[0].action_key in text


def test_plan_to_dict_round_trips_keys():
    plan = build_plan([finding()], CATALOG, {"S-1": item("S-1")}, max_actions=50)
    data = plan_to_dict(plan)
    assert set(data) == {"actions", "deferred"}
    assert set(data["actions"][0]) == {"action_key", "rule_id", "item_id", "bucket",
                                       "op", "rationale", "expected_effect"}
