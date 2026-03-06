"""Tests for the keyword/pattern-based emotion classifier."""

from backend.soul.emotion_classifier import classify_emotion


class TestKeywordMatching:
    def test_happy_text(self) -> None:
        result = classify_emotion("That's wonderful, I'm so happy!")
        assert result.name == "happy"
        assert result.intensity > 0.2
        assert result.confidence > 0.1

    def test_sad_text(self) -> None:
        result = classify_emotion("I'm feeling really sad and lonely today.")
        assert result.name == "sad"
        assert result.intensity > 0.2

    def test_excited_text(self) -> None:
        result = classify_emotion("Wow, that's incredible! I can't wait!")
        assert result.name == "excited"
        assert result.intensity > 0.3

    def test_curious_text(self) -> None:
        result = classify_emotion("I wonder how that works? That's really fascinating.")
        assert result.name == "curious"
        assert result.intensity > 0.2

    def test_amused_text(self) -> None:
        result = classify_emotion("Haha that's so funny, what a great joke!")
        assert result.name == "amused"
        assert result.intensity > 0.2

    def test_concerned_text(self) -> None:
        result = classify_emotion("I'm really worried about you. Are you alright?")
        assert result.name == "concerned"
        assert result.intensity > 0.2

    def test_thoughtful_text(self) -> None:
        result = classify_emotion(
            "Let me think about that. It's a really profound question "
            "with a lot of nuance to consider."
        )
        assert result.name == "thoughtful"
        assert result.intensity > 0.2

    def test_angry_text(self) -> None:
        result = classify_emotion(
            "I'm so angry about this! It's absolutely unacceptable!"
        )
        assert result.name == "angry"
        assert result.intensity > 0.3


class TestNeutralFallback:
    def test_empty_string(self) -> None:
        result = classify_emotion("")
        assert result.name == "neutral"
        assert result.confidence == 0.0

    def test_whitespace_only(self) -> None:
        result = classify_emotion("   ")
        assert result.name == "neutral"
        assert result.confidence == 0.0

    def test_no_emotion_keywords(self) -> None:
        result = classify_emotion("The temperature is 72 degrees Fahrenheit.")
        assert result.name == "neutral"
        assert result.confidence == 0.0


class TestPriorityOverNeutral:
    def test_single_keyword_still_detects(self) -> None:
        result = classify_emotion("That sounds interesting to me.")
        # Should detect curious (from "interesting") not stay neutral
        assert result.name != "neutral"
        assert result.confidence > 0.0

    def test_weak_signal_low_confidence(self) -> None:
        result = classify_emotion(
            "The project involves many different considerations "
            "and the data shows various patterns across the "
            "different regions we examined. Nice."
        )
        # Only one weak keyword in a long text
        if result.name != "neutral":
            assert result.confidence < 0.8


class TestConfidenceThresholds:
    def test_strong_signal_high_confidence(self) -> None:
        result = classify_emotion(
            "I'm so happy and glad and delighted about this wonderful news!"
        )
        assert result.confidence > 0.5

    def test_mixed_signals_lower_confidence(self) -> None:
        # Mix of happy and sad keywords
        result = classify_emotion(
            "I'm happy about the progress but sad about the loss."
        )
        # Should still pick one, but lower confidence due to mixed signals
        assert result.name in ("happy", "sad")
        # Mixed signals should have lower dominance
        pure = classify_emotion("I'm so happy and glad and wonderful!")
        assert result.confidence <= pure.confidence


class TestIntensitySignals:
    def test_exclamations_boost_intensity(self) -> None:
        calm = classify_emotion("That's great")
        excited = classify_emotion("That's great!!!")
        # Exclamations should boost intensity
        assert excited.intensity >= calm.intensity

    def test_more_keywords_higher_intensity(self) -> None:
        weak = classify_emotion(
            "I went to the store and picked up some things. It was nice."
        )
        strong = classify_emotion("That's great, wonderful, amazing, and fantastic!")
        assert strong.intensity > weak.intensity
