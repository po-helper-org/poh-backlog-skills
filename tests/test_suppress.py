from datetime import date

import pytest

from poh_backlog.model import Finding
from poh_backlog.suppress import (DecisionsError, Suppression, is_pair_suppressed,
                                  is_suppressed, load_suppressions)

TODAY = date(2026, 8, 18)


def finding(rule_id="HYG-STALE-001", item_id="GH-412"):
    return Finding(rule_id=rule_id, item_id=item_id, bucket="close",
                   severity="medium", message="m", evidence={})


def write(tmp_path, text):
    path = tmp_path / "decisions.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file_gives_empty_list(tmp_path):
    assert load_suppressions(tmp_path / "nope.yaml") == []


def test_forever_suppression_blocks(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-412\n"
                 "  verdict: rejected\n  reason: живая\n  suppress_until: forever\n")
    sup = load_suppressions(path)
    assert is_suppressed(finding(), sup, TODAY) is True


def test_dated_suppression_expires(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-412\n"
                 "  verdict: rejected\n  reason: ждём релиз\n  suppress_until: 2026-08-01\n")
    sup = load_suppressions(path)
    assert is_suppressed(finding(), sup, TODAY) is False
    assert is_suppressed(finding(), sup, date(2026, 7, 1)) is True


def test_accepted_verdict_does_not_suppress(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-412\n"
                 "  verdict: accepted\n  reason: ок\n  suppress_until: forever\n")
    assert load_suppressions(path) == []


def test_other_item_not_suppressed(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-999\n"
                 "  verdict: rejected\n  reason: r\n  suppress_until: forever\n")
    sup = load_suppressions(path)
    assert is_suppressed(finding(), sup, TODAY) is False


# --- граница даты истечения: named day включена в подавление ---

def test_day_before_until_is_suppressed(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-412\n"
                 "  verdict: rejected\n  reason: r\n  suppress_until: 2026-12-01\n")
    sup = load_suppressions(path)
    assert is_suppressed(finding(), sup, date(2026, 11, 30)) is True


def test_named_day_itself_is_suppressed(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-412\n"
                 "  verdict: rejected\n  reason: r\n  suppress_until: 2026-12-01\n")
    sup = load_suppressions(path)
    assert is_suppressed(finding(), sup, date(2026, 12, 1)) is True


def test_day_after_until_is_not_suppressed(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-412\n"
                 "  verdict: rejected\n  reason: r\n  suppress_until: 2026-12-01\n")
    sup = load_suppressions(path)
    assert is_suppressed(finding(), sup, date(2026, 12, 2)) is False


# --- некорректный decisions.yaml падает громко, с понятным сообщением ---

def test_invalid_yaml_syntax_raises_decisions_error(tmp_path):
    path = write(tmp_path, "- rule_id: HYG-STALE-001\n  item: [unclosed\n")
    with pytest.raises(DecisionsError) as exc_info:
        load_suppressions(path)
    assert str(path) in str(exc_info.value)
    assert exc_info.value.__cause__ is not None


def test_top_level_mapping_raises_decisions_error(tmp_path):
    path = write(tmp_path,
                 "rule_id: HYG-STALE-001\nitem: GH-412\nverdict: rejected\n")
    with pytest.raises(DecisionsError) as exc_info:
        load_suppressions(path)
    assert str(path) in str(exc_info.value)


def test_entry_missing_rule_id_raises_decisions_error(tmp_path):
    path = write(tmp_path,
                 "- item: GH-412\n  verdict: rejected\n  suppress_until: forever\n")
    with pytest.raises(DecisionsError) as exc_info:
        load_suppressions(path)
    message = str(exc_info.value)
    assert str(path) in message
    assert "1" in message


def test_entry_missing_item_raises_decisions_error(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  verdict: rejected\n  suppress_until: forever\n")
    with pytest.raises(DecisionsError) as exc_info:
        load_suppressions(path)
    message = str(exc_info.value)
    assert str(path) in message
    assert "1" in message


def test_invalid_suppress_until_raises_decisions_error(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-412\n"
                 "  verdict: rejected\n  suppress_until: не дата\n")
    with pytest.raises(DecisionsError) as exc_info:
        load_suppressions(path)
    message = str(exc_info.value)
    assert str(path) in message
    assert "не дата" in message


def test_second_entry_index_reported_when_first_is_valid(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-412\n  verdict: rejected\n"
                 "  suppress_until: forever\n"
                 "- item: GH-999\n  verdict: rejected\n  suppress_until: forever\n")
    with pytest.raises(DecisionsError) as exc_info:
        load_suppressions(path)
    assert "2" in str(exc_info.value)


# --- поведение, которое уже было правильным, но не было закреплено тестами ---

def test_empty_file_yields_empty_list(tmp_path):
    path = write(tmp_path, "")
    assert load_suppressions(path) == []


def test_missing_suppress_until_defaults_to_forever(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-412\n  verdict: rejected\n  reason: r\n")
    sup = load_suppressions(path)
    assert is_suppressed(finding(), sup, date(2099, 1, 1)) is True


# --- is_pair_suppressed — единственная реализация гейта, is_suppressed
# лишь оборачивает её данными из Finding (см. finding 1 финального ревью) ---

def test_is_pair_suppressed_matches_forever_suppression(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-412\n"
                 "  verdict: rejected\n  reason: r\n  suppress_until: forever\n")
    sup = load_suppressions(path)
    assert is_pair_suppressed("HYG-STALE-001", "GH-412", sup, TODAY) is True


def test_is_pair_suppressed_respects_dated_expiry(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-412\n"
                 "  verdict: rejected\n  reason: r\n  suppress_until: 2026-08-01\n")
    sup = load_suppressions(path)
    assert is_pair_suppressed("HYG-STALE-001", "GH-412", sup, TODAY) is False
    assert is_pair_suppressed("HYG-STALE-001", "GH-412", sup, date(2026, 7, 1)) is True


def test_is_pair_suppressed_does_not_match_other_item():
    sup = [Suppression("HYG-STALE-001", "GH-412", None)]
    assert is_pair_suppressed("HYG-STALE-001", "GH-999", sup, TODAY) is False


def test_is_suppressed_delegates_to_is_pair_suppressed(tmp_path):
    # is_suppressed не должен быть второй, отдельной реализацией гейта:
    # находка и голая пара (rule_id, item_id) обязаны подавляться одинаково.
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-412\n"
                 "  verdict: rejected\n  reason: r\n  suppress_until: forever\n")
    sup = load_suppressions(path)
    assert is_suppressed(finding(), sup, TODAY) == \
        is_pair_suppressed("HYG-STALE-001", "GH-412", sup, TODAY)
