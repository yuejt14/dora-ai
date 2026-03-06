"""Text-based emotion fallback classifier (keyword/pattern, no ML).

Analyzes response text to detect emotion when the LLM doesn't emit tags.
Phase 2 uses keyword/pattern matching. Phase 3+ can swap in a transformer.

Priority: TagParser tags > this classifier > neutral fallback.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from backend.utils import clamp


class EmotionEstimate(BaseModel):
    name: str = "neutral"
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# ── Emotion word lists ────────────────────────────────────────────────────

_EMOTION_WORDS: dict[str, list[str]] = {
    "happy": [
        "happy",
        "glad",
        "great",
        "wonderful",
        "awesome",
        "fantastic",
        "love",
        "joy",
        "delighted",
        "pleased",
        "thrilled",
        "yay",
        "hooray",
        "sweet",
        "beautiful",
        "lovely",
        "amazing",
        "perfect",
        "brilliant",
        "excellent",
    ],
    "excited": [
        "excited",
        "exciting",
        "wow",
        "whoa",
        "incredible",
        "can't wait",
        "pumped",
        "stoked",
        "fired up",
        "electrifying",
        "thrilling",
        "mind-blowing",
        "blown away",
        "oh my god",
        "omg",
        "unbelievable",
    ],
    "sad": [
        "sad",
        "sorry",
        "unfortunately",
        "heartbreaking",
        "miss",
        "lonely",
        "disappointed",
        "sigh",
        "painful",
        "hurt",
        "loss",
        "grief",
        "tragic",
        "devastating",
        "awful",
        "terrible",
    ],
    "curious": [
        "wonder",
        "wondering",
        "interesting",
        "fascinating",
        "curious",
        "hmm",
        "huh",
        "what if",
        "how does",
        "why does",
        "intriguing",
        "tell me more",
        "I'd love to know",
    ],
    "amused": [
        "haha",
        "lol",
        "funny",
        "hilarious",
        "laughing",
        "laugh",
        "joke",
        "pun",
        "witty",
        "comedy",
        "absurd",
        "cracking up",
        "that's gold",
    ],
    "concerned": [
        "worried",
        "concern",
        "careful",
        "hope you're okay",
        "are you alright",
        "that sounds tough",
        "hang in there",
        "take care",
        "be careful",
        "troubling",
        "alarming",
    ],
    "thoughtful": [
        "think",
        "consider",
        "reflect",
        "ponder",
        "contemplate",
        "philosophical",
        "perspective",
        "nuance",
        "complex",
        "depth",
        "meaningful",
        "profound",
    ],
    "angry": [
        "angry",
        "furious",
        "outraged",
        "infuriating",
        "ridiculous",
        "unacceptable",
        "frustrating",
        "fed up",
        "sick of",
        "hate",
        "disgusting",
        "enraged",
    ],
}

# Pre-compile a single alternation regex per emotion (one search instead of N)
_COMPILED_PATTERNS: dict[str, re.Pattern[str]] = {
    emotion: re.compile(
        r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE
    )
    for emotion, words in _EMOTION_WORDS.items()
}


def classify_emotion(text: str) -> EmotionEstimate:
    """Classify the dominant emotion in a text using keyword/pattern matching.

    Returns an EmotionEstimate with the detected emotion, intensity, and
    confidence. Low confidence means the text didn't have strong signals.
    """
    if not text.strip():
        return EmotionEstimate()

    # Score each emotion by keyword hits (one regex per emotion)
    scores: dict[str, float] = {}
    for emotion, pattern in _COMPILED_PATTERNS.items():
        hits = len(pattern.findall(text))
        if hits > 0:
            scores[emotion] = hits

    if not scores:
        return EmotionEstimate()

    # Normalize scores relative to word count for intensity
    word_count = max(len(text.split()), 1)

    # Pick the emotion with the most keyword hits
    best_emotion = max(scores, key=scores.__getitem__)
    raw_hits = scores[best_emotion]

    # Intensity: based on keyword density + punctuation signals
    exclamation_density = text.count("!") / max(len(text), 1)

    # More hits relative to text length = higher intensity
    keyword_density = raw_hits / word_count
    base_intensity = min(keyword_density * 8.0, 1.0)

    # Exclamations boost intensity
    intensity = clamp(base_intensity + exclamation_density * 3.0, 0.2, 1.0)

    # Confidence: how clear is the signal?
    total_hits = sum(scores.values())
    # Dominance of the top emotion over others
    dominance = raw_hits / total_hits if total_hits > 0 else 0.0
    # More hits = more confident
    hit_confidence = min(raw_hits / 3.0, 1.0)
    confidence = clamp(dominance * 0.6 + hit_confidence * 0.4, 0.1, 1.0)

    # Questions slightly boost curious
    if best_emotion == "curious":
        question_density = text.count("?") / max(len(text), 1)
        if question_density > 0.01:
            intensity = clamp(intensity + 0.1, 0.2, 1.0)
            confidence = clamp(confidence + 0.1, 0.1, 1.0)

    return EmotionEstimate(
        name=best_emotion,
        intensity=round(intensity, 3),
        confidence=round(confidence, 3),
    )
