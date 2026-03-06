"""Stateful streaming tag parser for soul engine output.

Extracts [emotion:...], [action:...], [mood:...], [thought:...] tags from
LLM output chunks and emits typed StreamEvents. Handles tags split across
chunks by buffering on ``[`` until ``]`` is found.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from backend.soul.definition import TagTier
from backend.utils import clamp

# ── Stream event types ────────────────────────────────────────────────────


class TextEvent(BaseModel):
    type: Literal["text"] = "text"
    text: str


class EmotionEvent(BaseModel):
    type: Literal["emotion"] = "emotion"
    name: str
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)


class MoodEvent(BaseModel):
    type: Literal["mood"] = "mood"
    name: str


class ActionEvent(BaseModel):
    type: Literal["action"] = "action"
    description: str


class ThoughtEvent(BaseModel):
    type: Literal["thought"] = "thought"
    text: str


StreamEvent = TextEvent | EmotionEvent | MoodEvent | ActionEvent | ThoughtEvent

# ── Tag regexes ───────────────────────────────────────────────────────────

_RE_EMOTION = re.compile(r"\[emotion:(\w+)(?:\s+intensity:([\d.]+))?\]", re.IGNORECASE)
_RE_ACTION = re.compile(r"\[action:\*(.+?)\*\]", re.IGNORECASE)
_RE_MOOD = re.compile(r"\[mood:(\w+)\]", re.IGNORECASE)
_RE_THOUGHT = re.compile(r"\[thought:(.+?)\]", re.IGNORECASE)

_BUFFER_FLUSH_LIMIT = 80

# Which tag types are allowed per tier
_TIER_TAGS: dict[TagTier, set[str]] = {
    TagTier.minimal: {"emotion"},
    TagTier.standard: {"emotion", "action"},
    TagTier.full: {"emotion", "action", "mood", "thought"},
}

# Prefix → (tag type name, compiled regex)
_PREFIX_DISPATCH: list[tuple[str, str, re.Pattern[str]]] = [
    ("[emotion:", "emotion", _RE_EMOTION),
    ("[action:", "action", _RE_ACTION),
    ("[mood:", "mood", _RE_MOOD),
    ("[thought:", "thought", _RE_THOUGHT),
]


# ── Parser ────────────────────────────────────────────────────────────────


class TagParser:
    """Stateful streaming tag parser.

    Feed chunks via ``feed()`` which yields ``StreamEvent`` objects.
    Call ``flush()`` at end-of-stream to emit any remaining buffered content
    and a default neutral emotion if no emotion tags were found.
    """

    def __init__(self, tier: TagTier = TagTier.standard) -> None:
        self.tier = tier
        self._allowed = _TIER_TAGS[tier]
        self._buf: list[str] = []
        self._in_tag: bool = False
        self._saw_emotion: bool = False

    def feed(self, chunk: str) -> list[StreamEvent]:
        """Process a chunk of streamed text and return any events produced."""
        events: list[StreamEvent] = []
        for char in chunk:
            if self._in_tag:
                self._buf.append(char)
                if char == "]":
                    events.append(self._parse_tag("".join(self._buf)))
                    self._buf.clear()
                    self._in_tag = False
                elif len(self._buf) > _BUFFER_FLUSH_LIMIT:
                    # Tag too long — flush as plain text
                    events.append(TextEvent(text="".join(self._buf)))
                    self._buf.clear()
                    self._in_tag = False
            elif char == "[":
                # Flush any pending plain text before starting tag
                if self._buf:
                    events.append(TextEvent(text="".join(self._buf)))
                    self._buf.clear()
                self._buf.append("[")
                self._in_tag = True
            else:
                self._buf.append(char)

        # Emit accumulated plain text (outside any tag)
        if self._buf and not self._in_tag:
            events.append(TextEvent(text="".join(self._buf)))
            self._buf.clear()

        return events

    def flush(self) -> list[StreamEvent]:
        """Flush remaining buffer and emit default emotion if none were found."""
        events: list[StreamEvent] = []
        if self._buf:
            events.append(TextEvent(text="".join(self._buf)))
            self._buf.clear()
            self._in_tag = False

        if not self._saw_emotion:
            events.append(EmotionEvent(name="neutral", intensity=0.5))
            self._saw_emotion = True

        return events

    def _parse_tag(self, tag_str: str) -> StreamEvent:
        """Try to parse a complete ``[...]`` tag string into an event."""
        tag_lower = tag_str.lower()
        for prefix, tag_type, regex in _PREFIX_DISPATCH:
            if not tag_lower.startswith(prefix):
                continue
            if tag_type not in self._allowed:
                break  # tier-filtered — emit as text
            m = regex.match(tag_str)
            if not m:
                break
            if tag_type == "emotion":
                name = m.group(1).lower()
                intensity = clamp(float(m.group(2)), 0.0, 1.0) if m.group(2) else 0.5
                self._saw_emotion = True
                return EmotionEvent(name=name, intensity=intensity)
            if tag_type == "action":
                return ActionEvent(description=m.group(1).strip())
            if tag_type == "mood":
                return MoodEvent(name=m.group(1).lower())
            if tag_type == "thought":
                return ThoughtEvent(text=m.group(1).strip())

        # Unrecognized or tier-filtered — pass through as plain text
        return TextEvent(text=tag_str)
