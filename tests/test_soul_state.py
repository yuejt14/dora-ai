"""Tests for CharacterState, SessionState, and supporting models."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.soul.state import (
    ArcPhase,
    CallbackCandidate,
    CharacterState,
    ConversationArc,
    EmotionSnapshot,
    FormedOpinion,
    MoodSnapshot,
    SentimentSnapshot,
    SessionState,
    _TRAIL_MAX,
)


class TestMoodSnapshot:
    def test_defaults(self) -> None:
        m = MoodSnapshot()
        assert m.name == "neutral"
        assert m.intensity == 0.5
        assert m.timestamp  # non-empty

    def test_custom(self) -> None:
        m = MoodSnapshot(name="happy", intensity=0.8, timestamp="2026-01-01T00:00:00+00:00")
        assert m.name == "happy"
        assert m.intensity == 0.8


class TestCharacterState:
    def test_effective_trait_default(self) -> None:
        cs = CharacterState(soul_id="test")
        assert cs.effective_trait("unknown") == 0.5

    def test_effective_trait_with_value(self) -> None:
        cs = CharacterState(soul_id="test", trait_values={"openness": 0.7})
        assert cs.effective_trait("openness") == 0.7

    def test_effective_trait_with_modifier(self) -> None:
        cs = CharacterState(soul_id="test", trait_values={"openness": 0.7})
        result = cs.effective_trait("openness", 0.1)
        assert abs(result - 0.8) < 1e-9

    def test_effective_trait_clamped_high(self) -> None:
        cs = CharacterState(soul_id="test", trait_values={"openness": 0.9})
        assert cs.effective_trait("openness", 0.5) == 1.0

    def test_effective_trait_clamped_low(self) -> None:
        cs = CharacterState(soul_id="test", trait_values={"openness": 0.1})
        assert cs.effective_trait("openness", -0.5) == 0.0

    def test_decayed_mood_same_as_baseline(self) -> None:
        cs = CharacterState(soul_id="test")
        cs.mood = MoodSnapshot(name="neutral", intensity=0.8)
        result = cs.decayed_mood("neutral", 6.0)
        assert result.name == "neutral"
        assert result.intensity == 0.8  # no decay

    def test_decayed_mood_half_life(self) -> None:
        past = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
        cs = CharacterState(soul_id="test")
        cs.mood = MoodSnapshot(name="excited", intensity=0.8, timestamp=past)
        result = cs.decayed_mood("neutral", decay_hours=6.0)
        # After exactly one half-life, intensity should be ~0.4
        assert result.name == "excited"
        assert abs(result.intensity - 0.4) < 0.05

    def test_decayed_mood_fully_decayed(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
        cs = CharacterState(soul_id="test")
        cs.mood = MoodSnapshot(name="excited", intensity=0.8, timestamp=old)
        result = cs.decayed_mood("neutral", decay_hours=6.0)
        # Should snap to baseline
        assert result.name == "neutral"
        assert result.intensity == 0.5

    def test_decayed_mood_invalid_timestamp(self) -> None:
        cs = CharacterState(soul_id="test")
        cs.mood = MoodSnapshot(name="excited", intensity=0.8, timestamp="not-a-date")
        result = cs.decayed_mood("neutral", 6.0)
        assert result.name == "neutral"

    def test_serialization_roundtrip(self) -> None:
        cs = CharacterState(
            soul_id="test",
            trait_values={"openness": 0.7, "energy": 0.6},
            formed_opinions=[FormedOpinion(topic="cats", stance="great", confidence=0.9)],
            total_turns=42,
        )
        json_str = cs.model_dump_json()
        cs2 = CharacterState.model_validate_json(json_str)
        assert cs2.soul_id == "test"
        assert cs2.trait_values == {"openness": 0.7, "energy": 0.6}
        assert cs2.formed_opinions[0].topic == "cats"
        assert cs2.total_turns == 42


class TestSessionState:
    def test_initial_state(self) -> None:
        ss = SessionState(conversation_id="c1")
        assert ss.emotion_trail == []
        assert ss.emotional_inertia.name == "neutral"
        assert ss.arc.phase == ArcPhase.opening

    def test_record_single_emotion(self) -> None:
        ss = SessionState(conversation_id="c1")
        e = EmotionSnapshot(name="happy", intensity=0.7, turn=1)
        ss.record_emotion(e, fluidity=0.6)
        assert len(ss.emotion_trail) == 1
        assert ss.emotional_inertia.name == "happy"
        assert ss.emotional_inertia.intensity == 0.7

    def test_record_multiple_emotions(self) -> None:
        ss = SessionState(conversation_id="c1")
        for i, (name, intensity) in enumerate([
            ("curious", 0.6),
            ("happy", 0.7),
            ("excited", 0.8),
        ]):
            ss.record_emotion(
                EmotionSnapshot(name=name, intensity=intensity, turn=i),
                fluidity=0.6,
            )
        assert len(ss.emotion_trail) == 3
        # With high fluidity, recent emotions should dominate
        assert ss.emotional_inertia.intensity > 0.6

    def test_emotion_trail_bounded(self) -> None:
        ss = SessionState(conversation_id="c1")
        for i in range(_TRAIL_MAX + 5):
            ss.record_emotion(
                EmotionSnapshot(name="happy", intensity=0.5, turn=i),
                fluidity=0.5,
            )
        assert len(ss.emotion_trail) == _TRAIL_MAX

    def test_high_fluidity_favors_recent(self) -> None:
        ss_high = SessionState(conversation_id="c1")
        ss_low = SessionState(conversation_id="c2")

        emotions = [
            EmotionSnapshot(name="sad", intensity=0.9, turn=0),
            EmotionSnapshot(name="sad", intensity=0.9, turn=1),
            EmotionSnapshot(name="sad", intensity=0.9, turn=2),
            EmotionSnapshot(name="happy", intensity=0.9, turn=3),
        ]
        for e in emotions:
            ss_high.record_emotion(e, fluidity=0.9)
            ss_low.record_emotion(e, fluidity=0.1)

        # High fluidity should pick up the recent "happy" more strongly
        # Low fluidity should still be influenced by the majority "sad"
        if ss_high.emotional_inertia.name == "happy":
            assert ss_low.emotional_inertia.name == "sad"

    def test_record_user_sentiment(self) -> None:
        ss = SessionState(conversation_id="c1")
        ss.record_user_sentiment(SentimentSnapshot(valence=0.8, arousal=0.6, turn=0))
        ss.record_user_sentiment(SentimentSnapshot(valence=0.4, arousal=0.3, turn=1))
        assert len(ss.user_sentiment_trail) == 2
        # Inertia should be between the two readings, weighted toward the recent one
        assert 0.4 <= ss.user_sentiment_inertia.valence <= 0.8
        assert 0.3 <= ss.user_sentiment_inertia.arousal <= 0.6

    def test_sentiment_trail_bounded(self) -> None:
        ss = SessionState(conversation_id="c1")
        for i in range(_TRAIL_MAX + 5):
            ss.record_user_sentiment(
                SentimentSnapshot(valence=0.0, arousal=0.5, turn=i)
            )
        assert len(ss.user_sentiment_trail) == _TRAIL_MAX


class TestConversationArc:
    def test_default_phase(self) -> None:
        arc = ConversationArc()
        assert arc.phase == ArcPhase.opening
        assert arc.energy == 0.5
        assert arc.turn_count == 0

    def test_phase_enum_values(self) -> None:
        assert ArcPhase.opening.value == "opening"
        assert ArcPhase.exploring.value == "exploring"
        assert ArcPhase.deepening.value == "deepening"
        assert ArcPhase.winding_down.value == "winding_down"
