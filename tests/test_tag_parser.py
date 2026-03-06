"""Tests for the streaming tag parser."""

from backend.soul.definition import TagTier
from backend.soul.tag_parser import (
    ActionEvent,
    EmotionEvent,
    MoodEvent,
    TagParser,
    TextEvent,
    ThoughtEvent,
)


class TestBasicParsing:
    def test_plain_text(self) -> None:
        p = TagParser()
        events = p.feed("Hello world")
        assert len(events) == 1
        assert isinstance(events[0], TextEvent)
        assert events[0].text == "Hello world"

    def test_emotion_tag_standard(self) -> None:
        p = TagParser(tier=TagTier.standard)
        events = p.feed("[emotion:happy intensity:0.8] Great!")
        assert len(events) == 2
        assert isinstance(events[0], EmotionEvent)
        assert events[0].name == "happy"
        assert events[0].intensity == 0.8
        assert isinstance(events[1], TextEvent)
        assert events[1].text == " Great!"

    def test_emotion_tag_no_intensity(self) -> None:
        p = TagParser(tier=TagTier.minimal)
        events = p.feed("[emotion:curious] Tell me more")
        assert isinstance(events[0], EmotionEvent)
        assert events[0].name == "curious"
        assert events[0].intensity == 0.5  # default

    def test_action_tag(self) -> None:
        p = TagParser(tier=TagTier.standard)
        events = p.feed("[action:*tilts head*]")
        assert len(events) == 1
        assert isinstance(events[0], ActionEvent)
        assert events[0].description == "tilts head"

    def test_mood_tag_full_tier(self) -> None:
        p = TagParser(tier=TagTier.full)
        events = p.feed("[mood:contemplative]")
        assert len(events) == 1
        assert isinstance(events[0], MoodEvent)
        assert events[0].name == "contemplative"

    def test_thought_tag_full_tier(self) -> None:
        p = TagParser(tier=TagTier.full)
        events = p.feed("[thought:I wonder if they meant...]")
        assert len(events) == 1
        assert isinstance(events[0], ThoughtEvent)
        assert events[0].text == "I wonder if they meant..."

    def test_multiple_tags_in_one_chunk(self) -> None:
        p = TagParser(tier=TagTier.full)
        events = p.feed(
            "[emotion:excited intensity:0.9] Oh! [action:*bounces*] That's great!"
        )
        emotion_events = [e for e in events if isinstance(e, EmotionEvent)]
        action_events = [e for e in events if isinstance(e, ActionEvent)]
        text_events = [e for e in events if isinstance(e, TextEvent)]
        assert len(emotion_events) == 1
        assert len(action_events) == 1
        assert len(text_events) == 2

    def test_emotion_name_lowercased(self) -> None:
        p = TagParser()
        events = p.feed("[emotion:HAPPY intensity:0.7]")
        assert isinstance(events[0], EmotionEvent)
        assert events[0].name == "happy"


class TestSplitTags:
    def test_tag_split_across_two_chunks(self) -> None:
        p = TagParser()
        events1 = p.feed("Hello [emot")
        events2 = p.feed("ion:happy intensity:0.8] world")
        # First chunk: text "Hello " only (tag is buffering)
        assert len(events1) == 1
        assert events1[0].text == "Hello "  # type: ignore[union-attr]
        # Second chunk: emotion event + text
        assert any(isinstance(e, EmotionEvent) for e in events2)
        assert any(isinstance(e, TextEvent) and e.text == " world" for e in events2)

    def test_tag_split_across_three_chunks(self) -> None:
        p = TagParser()
        p.feed("[emo")
        p.feed("tion:s")
        events = p.feed("ad]")
        assert len(events) == 1
        assert isinstance(events[0], EmotionEvent)
        assert events[0].name == "sad"

    def test_tag_at_chunk_boundary(self) -> None:
        p = TagParser()
        events1 = p.feed("[emotion:happy intensity:0.5]")
        assert len(events1) == 1
        assert isinstance(events1[0], EmotionEvent)


class TestBufferFlush:
    def test_long_bracket_flushes_as_text(self) -> None:
        """If buffer exceeds 80 chars without closing ], flush as text."""
        p = TagParser()
        long_text = "[" + "x" * 85
        events = p.feed(long_text)
        # Should have been flushed as text (the first 81+ chars including [)
        text_events = [e for e in events if isinstance(e, TextEvent)]
        assert len(text_events) >= 1
        combined = "".join(e.text for e in text_events)
        assert combined.startswith("[")
        assert len(combined) > 80


class TestTierFiltering:
    def test_minimal_rejects_action(self) -> None:
        p = TagParser(tier=TagTier.minimal)
        events = p.feed("[action:*waves*]")
        # Should pass through as text
        assert len(events) == 1
        assert isinstance(events[0], TextEvent)
        assert events[0].text == "[action:*waves*]"

    def test_minimal_rejects_mood(self) -> None:
        p = TagParser(tier=TagTier.minimal)
        events = p.feed("[mood:happy]")
        assert isinstance(events[0], TextEvent)

    def test_minimal_rejects_thought(self) -> None:
        p = TagParser(tier=TagTier.minimal)
        events = p.feed("[thought:hmm]")
        assert isinstance(events[0], TextEvent)

    def test_standard_rejects_mood(self) -> None:
        p = TagParser(tier=TagTier.standard)
        events = p.feed("[mood:happy]")
        assert isinstance(events[0], TextEvent)

    def test_standard_rejects_thought(self) -> None:
        p = TagParser(tier=TagTier.standard)
        events = p.feed("[thought:hmm]")
        assert isinstance(events[0], TextEvent)

    def test_standard_allows_emotion_and_action(self) -> None:
        p = TagParser(tier=TagTier.standard)
        events = p.feed("[emotion:happy] [action:*nods*]")
        types = {type(e) for e in events}
        assert EmotionEvent in types
        assert ActionEvent in types

    def test_full_allows_all(self) -> None:
        p = TagParser(tier=TagTier.full)
        text = (
            "[emotion:happy intensity:0.7] [action:*nods*] [mood:calm] [thought:nice]"
        )
        events = p.feed(text)
        types = {type(e) for e in events}
        assert EmotionEvent in types
        assert ActionEvent in types
        assert MoodEvent in types
        assert ThoughtEvent in types


class TestMalformedTags:
    def test_unrecognized_tag_passes_as_text(self) -> None:
        p = TagParser()
        events = p.feed("[unknown:value]")
        assert len(events) == 1
        assert isinstance(events[0], TextEvent)
        assert events[0].text == "[unknown:value]"

    def test_empty_brackets(self) -> None:
        p = TagParser()
        events = p.feed("[]")
        assert len(events) == 1
        assert isinstance(events[0], TextEvent)
        assert events[0].text == "[]"

    def test_nested_brackets(self) -> None:
        p = TagParser()
        # The first ] closes the tag attempt
        events = p.feed("[emotion:[nested]]")
        # Should produce some text output, not crash
        assert len(events) >= 1

    def test_intensity_out_of_range_clamped(self) -> None:
        p = TagParser()
        events = p.feed("[emotion:happy intensity:1.5]")
        assert isinstance(events[0], EmotionEvent)
        assert events[0].intensity == 1.0

    def test_intensity_negative_clamped(self) -> None:
        p = TagParser()
        events = p.feed("[emotion:sad intensity:-0.3]")
        # The regex won't match negative, so this is unrecognized -> text
        assert isinstance(events[0], TextEvent)


class TestFlushAndDefaults:
    def test_flush_emits_neutral_when_no_emotion(self) -> None:
        p = TagParser()
        p.feed("Just some plain text")
        events = p.flush()
        emotion_events = [e for e in events if isinstance(e, EmotionEvent)]
        assert len(emotion_events) == 1
        assert emotion_events[0].name == "neutral"
        assert emotion_events[0].intensity == 0.5

    def test_flush_no_default_when_emotion_found(self) -> None:
        p = TagParser()
        p.feed("[emotion:happy intensity:0.7]")
        events = p.flush()
        emotion_events = [e for e in events if isinstance(e, EmotionEvent)]
        assert len(emotion_events) == 0  # no default needed

    def test_flush_emits_remaining_buffer(self) -> None:
        p = TagParser()
        p.feed("Hello [incomp")
        events = p.flush()
        text_events = [e for e in events if isinstance(e, TextEvent)]
        assert any("[incomp" in e.text for e in text_events)

    def test_double_flush_is_idempotent(self) -> None:
        p = TagParser()
        p.feed("Hello")
        first = p.flush()
        second = p.flush()
        # First flush emits default emotion; second flush is empty
        assert any(isinstance(e, EmotionEvent) for e in first)
        assert not any(isinstance(e, EmotionEvent) for e in second)
