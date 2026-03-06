"""User sentiment analyzer — keyword/pattern-based (Phase 2).

Analyzes incoming user messages for valence (positive/negative) and
arousal (calm/intense). Feeds SessionState.user_sentiment_trail.

Phase 4 upgrade: STT pipeline adds vocal prosody to the same trail.
"""

from __future__ import annotations

import re

from backend.soul.state import SentimentSnapshot
from backend.utils import clamp

# ── Word lists ────────────────────────────────────────────────────────────

_POSITIVE_WORDS: list[str] = [
    "love",
    "great",
    "awesome",
    "amazing",
    "wonderful",
    "fantastic",
    "happy",
    "glad",
    "excited",
    "beautiful",
    "perfect",
    "excellent",
    "thank",
    "thanks",
    "appreciate",
    "enjoy",
    "fun",
    "nice",
    "good",
    "cool",
    "sweet",
    "brilliant",
    "incredible",
    "delighted",
    "pleased",
    "yes",
    "yeah",
    "yay",
    "hooray",
    "absolutely",
    "definitely",
]

_NEGATIVE_WORDS: list[str] = [
    "hate",
    "awful",
    "terrible",
    "horrible",
    "worst",
    "bad",
    "sad",
    "angry",
    "frustrated",
    "annoyed",
    "disappointed",
    "upset",
    "hurt",
    "sucks",
    "ugh",
    "damn",
    "hell",
    "crap",
    "stupid",
    "boring",
    "tired",
    "exhausted",
    "stressed",
    "worried",
    "anxious",
    "scared",
    "sorry",
    "unfortunately",
    "depressed",
    "lonely",
    "miserable",
]

_HIGH_AROUSAL_WORDS: list[str] = [
    "amazing",
    "incredible",
    "unbelievable",
    "insane",
    "crazy",
    "furious",
    "thrilled",
    "ecstatic",
    "terrified",
    "desperate",
    "screaming",
    "dying",
    "exploding",
    "omg",
    "oh my god",
    "wtf",
    "urgent",
    "emergency",
    "panic",
    "freaking",
    "absolutely",
]

_LOW_AROUSAL_WORDS: list[str] = [
    "okay",
    "fine",
    "alright",
    "meh",
    "whatever",
    "I guess",
    "not bad",
    "so-so",
    "calm",
    "quiet",
    "peaceful",
    "relaxed",
    "sleepy",
    "tired",
    "bored",
    "nothing much",
    "same old",
]


def _compile_alternation(words: list[str]) -> re.Pattern[str]:
    """Compile a word list into a single alternation regex."""
    return re.compile(
        r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE
    )


# Single alternation regex per word list (one search instead of N)
_RE_POS = _compile_alternation(_POSITIVE_WORDS)
_RE_NEG = _compile_alternation(_NEGATIVE_WORDS)
_RE_HIGH = _compile_alternation(_HIGH_AROUSAL_WORDS)
_RE_LOW = _compile_alternation(_LOW_AROUSAL_WORDS)

# Emoji sentiment — use alternation instead of character class to handle
# multi-codepoint sequences (e.g. ❤️ = U+2764 + U+FE0F) correctly.
_POSITIVE_EMOJI = re.compile(
    "|".join(
        re.escape(e)
        for e in [
            "😊",
            "😄",
            "😁",
            "🥰",
            "😍",
            "🎉",
            "❤️",
            "💕",
            "👍",
            "🙌",
            "✨",
            "🥳",
            "💪",
            "👏",
            "😎",
            "🤩",
        ]
    )
)
_NEGATIVE_EMOJI = re.compile(
    "|".join(
        re.escape(e)
        for e in [
            "😢",
            "😭",
            "😞",
            "😔",
            "😠",
            "😡",
            "💔",
            "😤",
            "😰",
            "😥",
            "😩",
            "😫",
            "🥺",
            "😿",
        ]
    )
)


def analyze_sentiment(text: str, turn: int = 0) -> SentimentSnapshot:
    """Analyze user message text for valence and arousal.

    Args:
        text: The user's message text.
        turn: Current turn number for the snapshot.

    Returns:
        SentimentSnapshot with valence (-1.0 to 1.0) and arousal (0.0 to 1.0).
    """
    if not text.strip():
        return SentimentSnapshot(valence=0.0, arousal=0.0, turn=turn)

    # ── Valence ───────────────────────────────────────────────────────
    pos_hits = len(_RE_POS.findall(text))
    neg_hits = len(_RE_NEG.findall(text))

    # Emoji contributions
    pos_hits += len(_POSITIVE_EMOJI.findall(text))
    neg_hits += len(_NEGATIVE_EMOJI.findall(text))

    total_hits = pos_hits + neg_hits
    if total_hits > 0:
        valence = (pos_hits - neg_hits) / total_hits
    else:
        valence = 0.0

    # ── Arousal ───────────────────────────────────────────────────────
    high_hits = len(_RE_HIGH.findall(text))
    low_hits = len(_RE_LOW.findall(text))

    # Punctuation signals
    exclamation_count = text.count("!")
    question_count = text.count("?")
    caps_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)

    # Base arousal from word signals
    arousal_signal = high_hits - low_hits

    # Exclamations and caps raise arousal
    arousal_boost = min(exclamation_count * 0.15, 0.4)
    arousal_boost += min(caps_ratio * 2.0, 0.3) if caps_ratio > 0.3 else 0.0
    # Multiple question marks raise arousal slightly
    arousal_boost += min(question_count * 0.05, 0.15)

    # Normalize arousal to 0.0-1.0
    if arousal_signal > 0:
        base_arousal = min(arousal_signal * 0.2, 0.6)
    elif arousal_signal < 0:
        base_arousal = max(arousal_signal * 0.15, -0.3)
    else:
        base_arousal = 0.0

    # Start from neutral (0.3), shift by signal
    arousal = clamp(0.3 + base_arousal + arousal_boost, 0.0, 1.0)

    # Short messages with no signals = low arousal
    word_count = len(text.split())
    if word_count <= 3 and total_hits == 0 and exclamation_count == 0:
        arousal = min(arousal, 0.2)

    return SentimentSnapshot(
        valence=round(clamp(valence, -1.0, 1.0), 3),
        arousal=round(arousal, 3),
        turn=turn,
    )
