from poh_backlog.diff import (DiffReport, detect_phase_drift, diff_snapshots,
                              render_report_md, take_snapshot)
from poh_backlog.model import BacklogItem
from poh_backlog.profile import Profile

PROFILE = Profile({"phases": {"mvp_tag": "mvp", "grow_tag": "grow",
                              "support_label": "support"}})


def item(id_, labels=(), estimate=1.0, updated="2026-08-01T00:00:00+00:00",
         description="d"):
    return BacklogItem.from_dict({
        "id": id_, "type": "story", "title": id_, "status": "open",
        "description": description, "labels": list(labels), "estimate": estimate,
        "parent": "E-1", "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": updated,
    })


def test_snapshot_records_labels_estimate_and_updated_at():
    snap = take_snapshot([item("S-1", labels=("mvp",))])
    assert snap["items"]["S-1"]["labels"] == ["mvp"]
    assert snap["items"]["S-1"]["estimate"] == 1.0
    assert snap["items"]["S-1"]["updated_at"] == "2026-08-01T00:00:00+00:00"


def test_diff_detects_added_removed_changed():
    prev = take_snapshot([item("S-1"), item("S-2")])
    curr = take_snapshot([item("S-1", estimate=5.0), item("S-3")])
    report = diff_snapshots(prev, curr)
    assert report.added == ["S-3"]
    assert report.removed == ["S-2"]
    assert report.changed["S-1"]["estimate"] == {"from": 1.0, "to": 5.0}


def test_diff_against_no_previous_snapshot_marks_everything_added():
    curr = take_snapshot([item("S-1")])
    report = diff_snapshots(None, curr)
    assert report.added == ["S-1"]
    assert report.removed == []
    assert report.changed == {}


def test_grow_to_mvp_without_comment_marker_flagged():
    prev = take_snapshot([item("S-1", labels=("grow",))])
    now_items = [item("S-1", labels=("mvp",))]
    findings = detect_phase_drift(prev, now_items, PROFILE)
    assert len(findings) == 1
    assert findings[0].rule_id == "PHS-DRIFT-008"
    assert findings[0].evidence == {"from": "grow", "to": "mvp"}


def test_grow_to_mvp_with_marker_in_description_not_flagged():
    prev = take_snapshot([item("S-1", labels=("grow",))])
    now_items = [item("S-1", labels=("mvp",),
                      description="Перенос в MVP: [phase-change] нужен для HowToDemo")]
    assert detect_phase_drift(prev, now_items, PROFILE) == []


def test_mvp_to_grow_not_flagged():
    prev = take_snapshot([item("S-1", labels=("mvp",))])
    now_items = [item("S-1", labels=("grow",))]
    assert detect_phase_drift(prev, now_items, PROFILE) == []


def test_report_md_contains_counts():
    report = DiffReport(added=["S-3"], removed=["S-2"], changed={"S-1": {}})
    text = render_report_md(report, findings_now=7, findings_prev=9)
    assert "Добавлено: 1" in text
    assert "Удалено: 1" in text
    assert "Изменено: 1" in text
    assert "9 -> 7" in text
