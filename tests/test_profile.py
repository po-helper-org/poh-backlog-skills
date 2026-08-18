from pathlib import Path

import pytest

from poh_backlog.profile import Profile, ProfileError, load_profile

DEFAULTS = Path(__file__).parent.parent / "rules" / "thresholds.yaml"


def test_defaults_load():
    profile = load_profile(DEFAULTS)
    assert profile.get("staleness.story_days") == 60
    assert profile.get("staleness.bug_days") == 30
    assert profile.get("description.min_words") == 20
    assert profile.get("phases.support_label") == "support"
    assert profile.get("plan.max_actions_per_run") == 50


def test_profile_overrides_defaults(tmp_path):
    override = tmp_path / "backlog-profile.yaml"
    override.write_text("staleness:\n  story_days: 90\n", encoding="utf-8")
    profile = load_profile(DEFAULTS, override)
    assert profile.get("staleness.story_days") == 90
    assert profile.get("staleness.bug_days") == 30


def test_unknown_key_raises(tmp_path):
    override = tmp_path / "backlog-profile.yaml"
    override.write_text("staleness:\n  story_weeks: 9\n", encoding="utf-8")
    with pytest.raises(ProfileError) as exc:
        load_profile(DEFAULTS, override)
    assert "staleness.story_weeks" in str(exc.value)


def test_missing_path_raises():
    profile = load_profile(DEFAULTS)
    with pytest.raises(ProfileError):
        profile.get("staleness.nope")


def test_scalar_default_overridden_with_dict_raises(tmp_path):
    override = tmp_path / "backlog-profile.yaml"
    override.write_text("staleness:\n  story_days:\n    sub: 1\n", encoding="utf-8")
    with pytest.raises(ProfileError) as exc:
        load_profile(DEFAULTS, override)
    assert "staleness.story_days" in str(exc.value)


def test_dict_default_overridden_with_scalar_raises(tmp_path):
    override = tmp_path / "backlog-profile.yaml"
    override.write_text("phases: mvp\n", encoding="utf-8")
    with pytest.raises(ProfileError) as exc:
        load_profile(DEFAULTS, override)
    assert "phases" in str(exc.value)


def test_mapping_only_profile_loads(tmp_path):
    override = tmp_path / "backlog-profile.yaml"
    override.write_text("mapping: mappings/github.yaml\n", encoding="utf-8")
    profile = load_profile(DEFAULTS, override)
    assert profile.get("staleness.story_days") == 60
