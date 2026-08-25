"""Тесты для движка аудита poh_backlog.audit."""
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import poh_backlog.rules.hygiene  # noqa: F401
import poh_backlog.rules.phases  # noqa: F401
from poh_backlog.audit import findings_to_dicts, run_audit
from poh_backlog.catalog import load_catalog
from poh_backlog.model import BacklogItem
from poh_backlog.profile import load_profile
from poh_backlog.suppress import Suppression

ROOT = Path(__file__).parent.parent
NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)
CATALOG = load_catalog(ROOT / "poh_backlog" / "data" / "catalog.yaml")
PROFILE = load_profile(ROOT / "poh_backlog" / "data" / "thresholds.yaml")
LONG = " ".join(["слово"] * 25)


def stale_story():
    return BacklogItem.from_dict({
        "id": "S-1", "type": "story", "title": "t", "status": "open",
        "description": LONG, "parent": "E-1", "estimate": 3.0, "labels": ["mvp"],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": (NOW - timedelta(days=200)).isoformat(),
    })


def epic():
    return BacklogItem.from_dict({
        "id": "E-1", "type": "epic", "title": "e", "status": "open",
        "description": LONG,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": NOW.isoformat(),
        "extra": {"business_metric": "m", "due_date": "2026-10-01",
                  "how_to_demo": "d", "limitations": ["l"]},
    })


def test_audit_produces_findings_for_stale_story():
    result = run_audit([epic(), stale_story()], CATALOG, PROFILE, NOW, [])
    rule_ids = {f.rule_id for f in result.findings}
    assert "HYG-STALE-001" in rule_ids


def test_judgment_rules_are_skipped_and_reported():
    result = run_audit([epic(), stale_story()], CATALOG, PROFILE, NOW, [])
    assert set(result.skipped_rules) == {"PHS-MVP-003", "PHS-LIMIT-004", "PHS-SUP-006"}
    assert all(not f.rule_id.startswith("PHS-MVP") for f in result.findings)


def test_suppressed_finding_is_removed_and_counted():
    sup = [Suppression("HYG-STALE-001", "S-1", None)]
    result = run_audit([epic(), stale_story()], CATALOG, PROFILE, NOW, sup)
    assert result.suppressed == 1
    assert all(f.rule_id != "HYG-STALE-001" for f in result.findings)


def test_findings_sorted_by_item_then_rule():
    result = run_audit([epic(), stale_story()], CATALOG, PROFILE, NOW, [])
    keys = [(f.item_id, f.rule_id) for f in result.findings]
    assert keys == sorted(keys)


def test_findings_to_dicts_is_json_ready():
    result = run_audit([epic(), stale_story()], CATALOG, PROFILE, NOW, [])
    dicts = findings_to_dicts(result.findings)
    assert set(dicts[0]) == {"rule_id", "item_id", "bucket", "severity",
                             "message", "evidence"}


def test_drift_rule_is_excluded_from_run_and_not_reported_as_skipped():
    """PHS-DRIFT-008 считается на диффе снимков (задача вне этой ветки).

    Движок аудита не должен ни выполнять его на одном снимке, ни числить
    пропущенным — пропуск подразумевал бы, что правило детерминировано,
    но просто ещё не реализовано, а это не так: оно реализовано в другом
    месте (poh_backlog.diff) и не относится к прогону по одному снимку.
    """
    result = run_audit([epic(), stale_story()], CATALOG, PROFILE, NOW, [])
    assert "PHS-DRIFT-008" not in result.skipped_rules
    assert all(f.rule_id != "PHS-DRIFT-008" for f in result.findings)


def test_importing_only_audit_module_registers_all_deterministic_rules():
    """Импорт одного poh_backlog.audit обязан заполнить реестр RULES.

    Брифовская реализация audit.py не импортирует модули правил и полагается
    на то, что RULES наполнится как побочный эффект чужого импорта. В проде
    (CLI) ничего кроме audit.py правила не импортирует, поэтому RULES
    остался бы пуст, каждое правило считалось бы пропущенным и находок не
    было бы никогда. Тесты в этом файле сами импортируют
    poh_backlog.rules.hygiene/phases в начале модуля, так что баг незаметен
    при обычном запуске pytest — RULES к моменту вызова run_audit уже полон
    из-за этих импортов. Единственный надёжный способ проверить факт
    импорта внутри самого audit.py — запустить чистый процесс, где
    единственный импорт из пакета poh_backlog — это `import poh_backlog.audit`.
    """
    script = (
        "import poh_backlog.audit\n"
        "from poh_backlog.rules import RULES\n"
        "expected = {\n"
        "    'HYG-STALE-001', 'HYG-DESC-002', 'HYG-EST-003', 'HYG-ORPHAN-004',\n"
        "    'PHS-TAG-001', 'PHS-EPIC-002', 'PHS-GROW-005', 'PHS-SUP-007',\n"
        "}\n"
        "actual = set(RULES)\n"
        "assert actual == expected, f'{sorted(actual)} != {sorted(expected)}'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
