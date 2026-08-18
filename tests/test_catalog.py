from pathlib import Path

import pytest
import yaml

from poh_backlog.catalog import ACTIONS, BUCKETS, SEVERITIES, CatalogError, load_catalog

REPO_ROOT = Path(__file__).parent.parent
CATALOG = REPO_ROOT / "rules" / "catalog.yaml"

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


def test_actions_constant_has_exactly_the_allowed_values_in_order():
    assert ACTIONS == (
        "propose_close",
        "propose_merge",
        "update_field",
        "relink",
        "split",
        "comment",
    )


def test_severities_constant_has_exactly_the_allowed_values_in_order():
    assert SEVERITIES == ("low", "medium", "high")


def test_every_rule_has_valid_action_and_severity():
    catalog = load_catalog(CATALOG)
    for spec in catalog.values():
        assert spec.action in ACTIONS, spec.id
        assert spec.severity in SEVERITIES, spec.id


def test_invalid_action_raises(tmp_path):
    bad = tmp_path / "catalog.yaml"
    bad.write_text(
        "- id: X-1\n  title: t\n  bucket: update\n  kind: deterministic\n"
        "  severity: low\n  action: delete\n  maturity: experimental\n",
        encoding="utf-8",
    )
    with pytest.raises(CatalogError):
        load_catalog(bad)


def test_invalid_severity_raises(tmp_path):
    bad = tmp_path / "catalog.yaml"
    bad.write_text(
        "- id: X-1\n  title: t\n  bucket: update\n  kind: deterministic\n"
        "  severity: critical\n  action: comment\n  maturity: experimental\n",
        encoding="utf-8",
    )
    with pytest.raises(CatalogError):
        load_catalog(bad)


def test_judgment_rules_have_existing_prompt_files_and_others_do_not():
    raw = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    for entry in raw:
        if entry["kind"] == "judgment":
            assert "prompt" in entry, entry["id"]
            prompt_path = REPO_ROOT / entry["prompt"]
            assert prompt_path.is_file(), f"{entry['id']}: {prompt_path} не существует"
        else:
            assert "prompt" not in entry, entry["id"]


def test_non_list_root_raises(tmp_path):
    bad = tmp_path / "catalog.yaml"
    bad.write_text(
        "id: X-1\ntitle: t\nbucket: update\nkind: deterministic\n"
        "severity: low\naction: comment\nmaturity: experimental\n",
        encoding="utf-8",
    )
    with pytest.raises(CatalogError):
        load_catalog(bad)


def test_non_mapping_entry_raises(tmp_path):
    bad = tmp_path / "catalog.yaml"
    bad.write_text("- just a string\n- id: X-1\n", encoding="utf-8")
    with pytest.raises(CatalogError):
        load_catalog(bad)
