from pathlib import Path

from dataclasses import replace

from poh_backlog.catalog import load_catalog
from poh_backlog.model import BacklogItem, Finding
from poh_backlog.planner import (ALLOWED_OPS, build_plan, plan_to_dict,
                                 read_run_id, render_plan_md, trace_label)

CATALOG = load_catalog(Path(__file__).parent.parent / "poh_backlog" / "data" / "catalog.yaml")


def item(id_, updated="2026-08-01T00:00:00+00:00"):
    return BacklogItem.from_dict({
        "id": id_, "type": "story", "title": f"Заголовок {id_}", "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": updated,
    })


def finding(rule_id="HYG-STALE-001", item_id="S-1", severity="medium",
            message="Нет активности 200 дней"):
    return Finding(rule_id=rule_id, item_id=item_id, bucket="close",
                   severity=severity, message=message, evidence={})


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
    plan = replace(plan, run_id="2026-08-18-01", shadow=True)
    data = plan_to_dict(plan)
    assert set(data) == {"actions", "deferred", "run_id", "shadow"}
    assert data["run_id"] == "2026-08-18-01"
    assert data["shadow"] is True
    assert set(data["actions"][0]) == {"action_key", "rule_id", "item_id", "bucket",
                                       "op", "rationale", "expected_effect", "trace_label",
                                       "promised_from"}


def test_plan_run_id_and_shadow_default_to_undecided_shape():
    # build_plan сам не знает про run_id/shadow конкретного запуска CLI —
    # это дописывает cli.cmd_run уже после построения плана. Дефолты должны
    # оставаться безопасными, если кто-то создаст Plan напрямую.
    plan = build_plan([finding()], CATALOG, {"S-1": item("S-1")}, max_actions=50)
    assert plan.run_id is None
    assert plan.shadow is False


def test_render_plan_md_header_explains_three_states_in_russian():
    plan = build_plan([finding()], CATALOG, {"S-1": item("S-1")}, max_actions=50)
    text = render_plan_md(plan, run_id="2026-08-18-01")
    assert "[x]" in text
    assert "[-]" in text
    assert "Снятая галочка означает отказ" not in text


def test_render_plan_md_embeds_machine_readable_run_id():
    plan = build_plan([finding()], CATALOG, {"S-1": item("S-1")}, max_actions=50)
    text = render_plan_md(plan, run_id="2026-08-18-01")
    assert read_run_id(text) == "2026-08-18-01"


def test_read_run_id_is_none_when_marker_absent():
    assert read_run_id("# план без маркера\n\n- [ ] `abc` X\n") is None


def _checkbox_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("- [ ] ")]


def test_rationale_with_embedded_newline_renders_as_single_line():
    findings = [finding(message="Первая строка\nВторая строка", item_id="S-1"),
                finding(rule_id="PHS-TAG-001", message="Обычный текст", item_id="S-2")]
    items = {"S-1": item("S-1"), "S-2": item("S-2")}
    plan = build_plan(findings, CATALOG, items, max_actions=50)
    text = render_plan_md(plan, run_id="2026-08-18-01")
    assert "Первая строка\nВторая строка" not in text
    assert "Первая строка Вторая строка" in text
    assert len(_checkbox_lines(text)) == len(plan.actions)


def test_rationale_with_checkbox_like_text_produces_no_extra_checkbox_line():
    findings = [finding(message="см. предыдущий пункт\n- [ ] нет активности", item_id="S-1")]
    items = {"S-1": item("S-1")}
    plan = build_plan(findings, CATALOG, items, max_actions=50)
    text = render_plan_md(plan, run_id="2026-08-18-01")
    assert len(_checkbox_lines(text)) == len(plan.actions)


def test_plan_to_dict_keeps_original_rationale_with_newline():
    findings = [finding(message="Первая строка\nВторая строка", item_id="S-1")]
    items = {"S-1": item("S-1")}
    plan = build_plan(findings, CATALOG, items, max_actions=50)
    data = plan_to_dict(plan)
    assert data["actions"][0]["rationale"] == "Первая строка\nВторая строка"


def test_deferred_section_lists_each_deferred_item_and_rule():
    findings = [finding(item_id=f"S-{i}") for i in range(5)]
    items = {f"S-{i}": item(f"S-{i}") for i in range(5)}
    plan = build_plan(findings, CATALOG, items, max_actions=2)
    text = render_plan_md(plan, run_id="2026-08-18-01")
    assert len(plan.deferred) >= 2
    for action in plan.deferred:
        assert action.item_id in text
        assert action.rule_id in text


def test_trace_label_format():
    assert trace_label("HYG-STALE-001") == "poh:HYG-STALE-001"


def test_action_carries_trace_label():
    plan = build_plan([finding()], CATALOG, {"S-1": item("S-1")}, max_actions=50)
    assert plan.actions[0].trace_label == "poh:HYG-STALE-001"


def test_action_promised_from_defaults_to_none():
    plan = build_plan([finding()], CATALOG, {"S-1": item("S-1")}, max_actions=50)
    assert plan.actions[0].promised_from is None


def test_plan_to_dict_includes_new_fields():
    plan = build_plan([finding()], CATALOG, {"S-1": item("S-1")}, max_actions=50)
    entry = plan_to_dict(plan)["actions"][0]
    assert entry["trace_label"] == "poh:HYG-STALE-001"
    assert entry["promised_from"] is None
