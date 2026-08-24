from datetime import date

from poh_backlog.model import Finding
from poh_backlog.suppress import is_suppressed, load_suppressions

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
