from pathlib import Path

import pytest

from poh_backlog.catalog import BUCKETS, CatalogError, load_catalog

CATALOG = Path(__file__).parent.parent / "rules" / "catalog.yaml"

EXPECTED_IDS = {
    "HYG-STALE-001", "HYG-DESC-002", "HYG-EST-003", "HYG-ORPHAN-004",
    "PHS-TAG-001", "PHS-EPIC-002", "PHS-MVP-003", "PHS-LIMIT-004",
    "PHS-GROW-005", "PHS-SUP-006", "PHS-SUP-007", "PHS-DRIFT-008",
}


def test_catalog_contains_all_spec_rules():
    catalog = load_catalog(CATALOG)
    assert set(catalog) == EXPECTED_IDS


def test_every_rule_has_valid_bucket_and_starts_experimental():
    catalog = load_catalog(CATALOG)
    for spec in catalog.values():
        assert spec.bucket in BUCKETS, spec.id
        assert spec.maturity == "experimental", spec.id


def test_judgment_rules_marked():
    catalog = load_catalog(CATALOG)
    judgment = {rid for rid, spec in catalog.items() if spec.kind == "judgment"}
    assert judgment == {"PHS-MVP-003", "PHS-LIMIT-004", "PHS-SUP-006"}


def test_invalid_bucket_raises(tmp_path):
    bad = tmp_path / "catalog.yaml"
    bad.write_text(
        "- id: X-1\n  title: t\n  bucket: nuke\n  kind: deterministic\n"
        "  severity: low\n  action: comment\n  maturity: experimental\n",
        encoding="utf-8",
    )
    with pytest.raises(CatalogError):
        load_catalog(bad)


def test_duplicate_id_raises(tmp_path):
    bad = tmp_path / "catalog.yaml"
    entry = ("- id: X-1\n  title: t\n  bucket: update\n  kind: deterministic\n"
             "  severity: low\n  action: comment\n  maturity: experimental\n")
    bad.write_text(entry * 2, encoding="utf-8")
    with pytest.raises(CatalogError):
        load_catalog(bad)
