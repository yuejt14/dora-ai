"""Tests for SoulDefinition YAML loading and validation."""

from pathlib import Path

import pytest
import yaml

from backend.soul.definition import (
    ContextTriggerType,
    DriftRate,
    SoulDefinition,
    TagTier,
    load_soul,
    scan_souls,
)


@pytest.fixture
def default_yaml() -> Path:
    return Path(__file__).resolve().parent.parent / "souls" / "default.yaml"


@pytest.fixture
def soul(default_yaml: Path) -> SoulDefinition:
    defn, _ = load_soul(default_yaml)
    return defn


class TestYAMLLoading:
    def test_load_returns_definition_and_hash(self, default_yaml: Path) -> None:
        defn, h = load_soul(default_yaml)
        assert isinstance(defn, SoulDefinition)
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex

    def test_load_same_file_gives_same_hash(self, default_yaml: Path) -> None:
        _, h1 = load_soul(default_yaml)
        _, h2 = load_soul(default_yaml)
        assert h1 == h2

    def test_scan_souls_finds_default(self) -> None:
        results = scan_souls()
        assert len(results) >= 1
        ids = [defn.meta.id for defn, _ in results]
        assert "default" in ids

    def test_scan_souls_empty_dir(self, tmp_path: Path) -> None:
        assert scan_souls(tmp_path) == []

    def test_scan_souls_missing_dir(self, tmp_path: Path) -> None:
        assert scan_souls(tmp_path / "nonexistent") == []

    def test_scan_souls_skips_invalid_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "bad.yaml").write_text("not: [valid: soul")
        results = scan_souls(tmp_path)
        assert results == []

    def test_load_invalid_yaml_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("meta:\n  id: test\n")
        with pytest.raises(Exception):
            load_soul(bad)


class TestIdentity:
    def test_meta(self, soul: SoulDefinition) -> None:
        assert soul.meta.id == "default"
        assert soul.meta.version == 1

    def test_identity(self, soul: SoulDefinition) -> None:
        assert soul.identity.name == "Dora"
        assert soul.identity.age == "early 20s"
        assert len(soul.identity.values) > 0


class TestTraits:
    def test_core_traits_loaded(self, soul: SoulDefinition) -> None:
        names = [t.name for t in soul.traits.core]
        assert "curious" in names
        assert "empathetic" in names
        assert "playful" in names

    def test_mutable_traits_loaded(self, soul: SoulDefinition) -> None:
        names = [t.name for t in soul.traits.mutable]
        assert "openness" in names
        assert "assertiveness" in names
        assert "energy" in names

    def test_mutable_trait_bounds(self, soul: SoulDefinition) -> None:
        for t in soul.traits.mutable:
            assert 0.0 <= t.min <= t.base <= t.max <= 1.0
            assert isinstance(t.drift_rate, DriftRate)

    def test_drift_rate_max_delta(self) -> None:
        assert DriftRate.slow.max_delta == 0.02
        assert DriftRate.medium.max_delta == 0.05
        assert DriftRate.fast.max_delta == 0.1


class TestEmotions:
    def test_baseline_and_fluidity(self, soul: SoulDefinition) -> None:
        assert soul.emotions.baseline == "content"
        assert 0.0 <= soul.emotions.fluidity <= 1.0

    def test_tendencies_loaded(self, soul: SoulDefinition) -> None:
        assert "happy" in soul.emotions.tendencies
        assert "excited" in soul.emotions.tendencies
        t = soul.emotions.tendencies["happy"]
        assert len(t.triggers) > 0
        assert t.range[0] < t.range[1]

    def test_mood_decay(self, soul: SoulDefinition) -> None:
        assert soul.emotions.mood.decay_hours > 0


class TestRelationship:
    def test_stages_ordered_by_turns(self, soul: SoulDefinition) -> None:
        turns = [s.after_turns for s in soul.relationship.stages]
        assert turns == sorted(turns)

    def test_first_stage_is_stranger(self, soul: SoulDefinition) -> None:
        assert soul.relationship.stages[0].name == "stranger"

    def test_modifiers_present(self, soul: SoulDefinition) -> None:
        stranger = soul.relationship.stages[0]
        assert "openness" in stranger.modifiers


class TestSpontaneity:
    def test_bounds(self, soul: SoulDefinition) -> None:
        s = soul.spontaneity
        assert s.min <= s.base <= s.max
        assert s.cooldown_turns > 0

    def test_type_weights_sum_to_one(self, soul: SoulDefinition) -> None:
        t = soul.spontaneity.types
        total = t.tangent + t.callback + t.provocation + t.non_sequitur + t.vulnerability
        assert abs(total - 1.0) < 0.01


class TestInitiative:
    def test_config(self, soul: SoulDefinition) -> None:
        assert soul.initiative.enabled is True
        assert soul.initiative.max_per_hour > 0

    def test_context_trigger_types(self, soul: SoulDefinition) -> None:
        types = [t.type for t in soul.initiative.context_triggers]
        assert ContextTriggerType.first_session_of_day in types
        assert ContextTriggerType.follow_up_thought in types


class TestTagTier:
    def test_default_tier(self, soul: SoulDefinition) -> None:
        assert soul.tag_tier == TagTier.standard


class TestValidation:
    def test_fluidity_out_of_range_rejected(self, tmp_path: Path) -> None:
        data = {
            "meta": {"id": "test", "version": 1},
            "identity": {"name": "T", "age": "1", "background": "t"},
            "emotions": {"fluidity": 2.0},
        }
        p = tmp_path / "bad.yaml"
        p.write_text(yaml.dump(data))
        with pytest.raises(Exception):
            load_soul(p)

    def test_mutable_trait_base_clamped(self, tmp_path: Path) -> None:
        data = {
            "meta": {"id": "test", "version": 1},
            "identity": {"name": "T", "age": "1", "background": "t"},
            "traits": {
                "mutable": [
                    {"name": "x", "base": 1.5, "min": 0, "max": 1, "behavior": "t"}
                ]
            },
        }
        p = tmp_path / "bad.yaml"
        p.write_text(yaml.dump(data))
        with pytest.raises(Exception):
            load_soul(p)
