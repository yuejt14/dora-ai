"""Tests for the user sentiment analyzer."""

from backend.soul.sentiment import analyze_sentiment


class TestValenceDetection:
    def test_positive_message(self) -> None:
        result = analyze_sentiment("I love this! It's amazing and wonderful!")
        assert result.valence > 0.3

    def test_negative_message(self) -> None:
        result = analyze_sentiment("I hate this, it's terrible and awful.")
        assert result.valence < -0.3

    def test_neutral_message(self) -> None:
        result = analyze_sentiment("The meeting is at 3pm tomorrow.")
        assert abs(result.valence) < 0.2

    def test_mixed_valence(self) -> None:
        result = analyze_sentiment(
            "I'm happy about the progress but worried about deadlines."
        )
        # Mixed signal — should be moderate, not extreme
        assert -0.7 < result.valence < 0.7

    def test_empty_string(self) -> None:
        result = analyze_sentiment("")
        assert result.valence == 0.0
        assert result.arousal == 0.0

    def test_positive_emoji(self) -> None:
        result = analyze_sentiment("Had a great day! 😊❤️")
        assert result.valence > 0.3

    def test_negative_emoji(self) -> None:
        result = analyze_sentiment("Feeling down 😢😔")
        assert result.valence < -0.3


class TestArousalDetection:
    def test_high_arousal_exclamations(self) -> None:
        result = analyze_sentiment("OMG THIS IS INCREDIBLE!!!")
        assert result.arousal > 0.5

    def test_low_arousal_calm(self) -> None:
        result = analyze_sentiment("okay, that's fine I guess")
        assert result.arousal < 0.4

    def test_caps_raise_arousal(self) -> None:
        calm = analyze_sentiment("this is amazing")
        shouting = analyze_sentiment("THIS IS AMAZING")
        assert shouting.arousal > calm.arousal

    def test_short_neutral_low_arousal(self) -> None:
        result = analyze_sentiment("ok")
        assert result.arousal < 0.3

    def test_multiple_questions_some_arousal(self) -> None:
        result = analyze_sentiment("What?? How?? Why would they do that???")
        assert result.arousal > 0.3


class TestTurnTracking:
    def test_turn_number_preserved(self) -> None:
        result = analyze_sentiment("Hello there!", turn=5)
        assert result.turn == 5

    def test_default_turn_zero(self) -> None:
        result = analyze_sentiment("Hello!")
        assert result.turn == 0


class TestInertiaCalculation:
    def test_sentiment_feeds_session_state(self) -> None:
        """Verify that sentiment snapshots integrate with SessionState."""
        from backend.soul.state import SessionState

        ss = SessionState(conversation_id="test")
        s1 = analyze_sentiment("I love this so much!", turn=1)
        s2 = analyze_sentiment("This is terrible and awful.", turn=2)

        ss.record_user_sentiment(s1)
        assert ss.user_sentiment_inertia.valence > 0.0

        ss.record_user_sentiment(s2)
        # After a negative message, inertia should shift
        # It should be between the two values, weighted toward recent
        assert ss.user_sentiment_inertia.valence < s1.valence

    def test_consistent_positive_builds_inertia(self) -> None:
        from backend.soul.state import SessionState

        ss = SessionState(conversation_id="test")
        for i in range(5):
            s = analyze_sentiment("This is great and amazing!", turn=i)
            ss.record_user_sentiment(s)

        assert ss.user_sentiment_inertia.valence > 0.3
