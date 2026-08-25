from datetime import datetime, timezone
from pathlib import Path

import poh_backlog.rules.hygiene  # noqa: F401
import poh_backlog.rules.phases  # noqa: F401
from poh_backlog.catalog import load_catalog
from poh_backlog.diff import take_snapshot
from poh_backlog.model import BacklogItem
from poh_backlog.profile import load_profile
from poh_backlog.verify import (STATUSES, render_verify_md, verdicts_to_dicts,
                                verify_actions)

ROOT = Path(__file__).parent.parent
CATALOG = load_catalog(ROOT / "poh_backlog" / "data" / "catalog.yaml")
PROFILE = load_profile(ROOT / "poh_backlog" / "data" / "thresholds.yaml")
NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)
LONG = " ".join(["слово"] * 25)


def item(id_="S-1", labels=(), estimate=3.0, description=LONG,
         updated="2026-08-25T00:00:00+00:00", parent="E-1"):
    return BacklogItem.from_dict({
        "id": id_, "type": "story", "title": id_, "status": "open",
        "description": description, "labels": list(labels), "estimate": estimate,
        "parent": parent, "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": updated,
    })


def approved(rule_id="HYG-EST-003", item_id="S-1", op="update_field"):
    return [{
        "action_key": "a" * 16, "rule_id": rule_id, "item_id": item_id,
        "bucket": "update", "op": op, "rationale": "тест",
        "expected_effect": CATALOG[rule_id].expected_effect,
        "trace_label": f"poh:{rule_id}", "promised_from": None,
    }]


def test_statuses_constant():
    assert STATUSES == ("done", "no_effect", "not_applied")


def test_done_when_trace_present_and_finding_gone():
    after = [item(labels=("poh:HYG-EST-003", "mvp"), estimate=5.0)]
    result = verify_actions(approved(), after, CATALOG, PROFILE, NOW, None)
    assert [v.status for v in result.verdicts] == ["done"]
    assert result.fidelity == 1.0


def test_no_effect_when_trace_present_but_finding_remains():
    after = [item(labels=("poh:HYG-EST-003", "mvp"), estimate=None)]
    result = verify_actions(approved(), after, CATALOG, PROFILE, NOW, None)
    assert [v.status for v in result.verdicts] == ["no_effect"]
    assert result.fidelity == 0.0


def test_not_applied_when_trace_absent():
    after = [item(labels=("mvp",), estimate=5.0)]
    result = verify_actions(approved(), after, CATALOG, PROFILE, NOW, None)
    assert [v.status for v in result.verdicts] == ["not_applied"]


def test_not_applied_when_item_vanished():
    result = verify_actions(approved(), [], CATALOG, PROFILE, NOW, None)
    assert result.verdicts[0].status == "not_applied"
    assert "не найден" in result.verdicts[0].note


def test_no_effect_note_is_honest_when_rule_has_no_implementation():
    # PHS-MVP-003 — правило-суждение, его никто не регистрирует в RULES.
    # Перепрогнать нечем, поэтому вердикт не должен утверждать, что находка
    # проверена и сохранилась: это было бы неправдой.
    after = [item(labels=("poh:PHS-MVP-003", "mvp"))]
    result = verify_actions(approved(rule_id="PHS-MVP-003"), after, CATALOG,
                            PROFILE, NOW, None)
    assert result.verdicts[0].status == "no_effect"
    assert "не исполняется в этом срезе" in result.verdicts[0].note
    assert "сохраняется" not in result.verdicts[0].note


def test_no_effect_note_stays_honest_when_rule_reruns_and_finding_survives():
    after = [item(labels=("poh:HYG-EST-003", "mvp"), estimate=None)]
    result = verify_actions(approved(), after, CATALOG, PROFILE, NOW, None)
    assert result.verdicts[0].status == "no_effect"
    assert result.verdicts[0].note == "След есть, но находка сохраняется: результата нет"


def test_trace_label_mode_needs_only_the_label():
    # HYG-STALE-001 работает в режиме trace_label: находка может остаться,
    # но метка есть — значит действие исполнено.
    old = item(updated="2026-01-01T00:00:00+00:00",
               labels=("poh:HYG-STALE-001", "mvp"))
    result = verify_actions(approved(rule_id="HYG-STALE-001", op="propose_close"),
                            [old], CATALOG, PROFILE, NOW, None)
    assert result.verdicts[0].status == "done"


def test_correlation_survives_changed_updated_at():
    # action_key в approved.json посчитан по старому updated_at; элемент с тех
    # пор изменился. Сверка идёт по паре (rule_id, item_id), поэтому вердикт
    # всё равно находится.
    after = [item(labels=("poh:HYG-EST-003", "mvp"), estimate=5.0,
                  updated="2026-08-26T12:00:00+00:00")]
    result = verify_actions(approved(), after, CATALOG, PROFILE, NOW, None)
    assert result.verdicts[0].status == "done"


def test_collateral_lists_only_untargeted_changes():
    before = take_snapshot([item("S-1"), item("S-2"), item("S-3")])
    after = [item("S-1", labels=("poh:HYG-EST-003",), estimate=5.0),
             item("S-2", estimate=9.0),
             item("S-3")]
    result = verify_actions(approved(), after, CATALOG, PROFILE, NOW, before)
    assert result.collateral == ["S-2"]


def test_collateral_empty_without_previous_snapshot():
    after = [item(labels=("poh:HYG-EST-003",), estimate=5.0)]
    result = verify_actions(approved(), after, CATALOG, PROFILE, NOW, None)
    assert result.collateral == []


def test_fidelity_on_mixed_verdicts():
    actions = approved() + approved(item_id="S-2")
    after = [item("S-1", labels=("poh:HYG-EST-003",), estimate=5.0),
             item("S-2", estimate=None)]
    result = verify_actions(actions, after, CATALOG, PROFILE, NOW, None)
    assert result.fidelity == 0.5


def test_fidelity_is_zero_without_actions():
    result = verify_actions([], [item()], CATALOG, PROFILE, NOW, None)
    assert result.fidelity == 0.0
    assert result.verdicts == []


def test_verdicts_to_dicts_is_json_ready():
    after = [item(labels=("poh:HYG-EST-003",), estimate=5.0)]
    result = verify_actions(approved(), after, CATALOG, PROFILE, NOW, None)
    entry = verdicts_to_dicts(result.verdicts)[0]
    assert set(entry) == {"action_key", "rule_id", "item_id", "op", "status", "note"}


def test_verify_md_contains_counts_and_collateral():
    before = take_snapshot([item("S-1"), item("S-2")])
    after = [item("S-1", labels=("poh:HYG-EST-003",), estimate=5.0),
             item("S-2", estimate=9.0)]
    result = verify_actions(approved(), after, CATALOG, PROFILE, NOW, before)
    text = render_verify_md(result, run_id="2026-08-26-01")
    assert "2026-08-26-01" in text
    assert "Достоверность исполнения: 100%" in text
    assert "S-2" in text


def test_collateral_checked_flag_true_with_previous_snapshot():
    before = take_snapshot([item("S-1")])
    after = [item("S-1", labels=("poh:HYG-EST-003",), estimate=5.0)]
    result = verify_actions(approved(), after, CATALOG, PROFILE, NOW, before)
    assert result.collateral_checked is True


def test_collateral_checked_flag_false_without_previous_snapshot():
    after = [item("S-1", labels=("poh:HYG-EST-003",), estimate=5.0)]
    result = verify_actions(approved(), after, CATALOG, PROFILE, NOW, None)
    assert result.collateral_checked is False


def test_verify_md_keeps_current_wording_when_collateral_checked_and_clean():
    before = take_snapshot([item("S-1")])
    after = [item("S-1", labels=("poh:HYG-EST-003",), estimate=5.0)]
    result = verify_actions(approved(), after, CATALOG, PROFILE, NOW, before)
    text = render_verify_md(result, run_id="2026-08-26-01")
    assert "Изменений вне списка целей не обнаружено." in text


def test_verify_md_reports_skipped_collateral_check_without_snapshot():
    after = [item("S-1", labels=("poh:HYG-EST-003",), estimate=5.0)]
    result = verify_actions(approved(), after, CATALOG, PROFILE, NOW, None)
    text = render_verify_md(result, run_id="2026-08-26-01")
    assert "не обнаружено" not in text
    assert "снимок" in text.lower() and "пропущен" in text.lower()
