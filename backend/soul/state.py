"""CharacterState (persistent) + SessionState (volatile) + supporting models."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from backend.utils import clamp, utc_now


# ── Supporting models ──────────────────────────────────────────────────────


class MoodSnapshot(BaseModel):
    name: str = "neutral"
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    timestamp: str = Field(default_factory=utc_now)


class FormedOpinion(BaseModel):
    topic: str
    stance: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class RecordedMilestone(BaseModel):
    id: str
    timestamp: str
    context: str = ""


class DevelopedInterest(BaseModel):
    topic: str
    source: str = ""


class RunningGag(BaseModel):
    reference: str
    turn_count: int = 1


class EmotionSnapshot(BaseModel):
    name: str = "neutral"
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    turn: int = 0


class SentimentSnapshot(BaseModel):
    valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal: float = Field(default=0.0, ge=0.0, le=1.0)
    turn: int = 0


class TrackedTopic(BaseModel):
    name: str
    first_turn: int
    last_turn: int
    mention_count: int = 1
    energy: float = Field(default=0.5, ge=0.0, le=1.0)


class ArcPhase(str, Enum):
    opening = "opening"
    exploring = "exploring"
    deepening = "deepening"
    winding_down = "winding_down"


class ConversationArc(BaseModel):
    phase: ArcPhase = ArcPhase.opening
    energy: float = Field(default=0.5, ge=0.0, le=1.0)
    topics: list[TrackedTopic] = Field(default_factory=list)
    turn_count: int = 0


class CallbackCandidate(BaseModel):
    detail: str
    turn: int


# ── CharacterState (persistent, SQLite) ────────────────────────────────────


class CharacterState(BaseModel):
    soul_id: str
    relationship_stage: str = "stranger"
    total_turns: int = 0
    trait_values: dict[str, float] = Field(default_factory=dict)
    formed_opinions: list[FormedOpinion] = Field(default_factory=list)
    mood: MoodSnapshot = Field(default_factory=MoodSnapshot)
    milestones: list[RecordedMilestone] = Field(default_factory=list)
    developed_interests: list[DevelopedInterest] = Field(default_factory=list)
    running_gags: list[RunningGag] = Field(default_factory=list)
    last_eval_at: str | None = None
    last_eval_turn: int = 0

    def effective_trait(self, name: str, stage_modifier: float = 0.0) -> float:
        """Return clamped trait value with stage modifier applied."""
        base = self.trait_values.get(name, 0.5)
        return clamp(base + stage_modifier, 0.0, 1.0)

    def decayed_mood(self, baseline: str, decay_hours: float) -> MoodSnapshot:
        """Return mood with time-decay toward baseline.

        Intensity decays exponentially with the given half-life in hours.
        If the mood name matches baseline, no decay is applied.
        """
        if self.mood.name == baseline:
            return self.mood

        try:
            ts = datetime.fromisoformat(self.mood.timestamp)
        except ValueError, TypeError:
            return MoodSnapshot(name=baseline, intensity=0.5)

        now = datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        elapsed_hours = (now - ts).total_seconds() / 3600.0
        if elapsed_hours <= 0:
            return self.mood

        decay_factor = math.pow(0.5, elapsed_hours / decay_hours)
        decayed_intensity = self.mood.intensity * decay_factor

        if decayed_intensity < 0.1:
            return MoodSnapshot(name=baseline, intensity=0.5)

        return MoodSnapshot(
            name=self.mood.name,
            intensity=round(decayed_intensity, 3),
            timestamp=self.mood.timestamp,
        )


# ── SessionState (volatile, in-memory) ─────────────────────────────────────

_TRAIL_MAX = 10


class SessionState(BaseModel):
    conversation_id: str
    emotion_trail: list[EmotionSnapshot] = Field(default_factory=list)
    emotional_inertia: EmotionSnapshot = Field(
        default_factory=lambda: EmotionSnapshot(name="neutral", intensity=0.5)
    )
    user_sentiment_trail: list[SentimentSnapshot] = Field(default_factory=list)
    user_sentiment_inertia: SentimentSnapshot = Field(default_factory=SentimentSnapshot)
    arc: ConversationArc = Field(default_factory=ConversationArc)
    callbacks: list[CallbackCandidate] = Field(default_factory=list)
    last_wildcard_turn: int | None = None
    wildcards_this_session: int = 0

    def record_emotion(self, emotion: EmotionSnapshot, fluidity: float) -> None:
        """Append an emotion to the trail and recalculate inertia.

        Args:
            emotion: The new emotion snapshot.
            fluidity: 0.0 (stoic) to 1.0 (reactive). Controls how much
                      recent emotions dominate the inertia calculation.
        """
        self.emotion_trail.append(emotion)
        if len(self.emotion_trail) > _TRAIL_MAX:
            del self.emotion_trail[: len(self.emotion_trail) - _TRAIL_MAX]

        self.emotional_inertia = _weighted_emotion(self.emotion_trail, fluidity)

    def record_user_sentiment(self, sentiment: SentimentSnapshot) -> None:
        """Append a user sentiment reading and recalculate inertia."""
        self.user_sentiment_trail.append(sentiment)
        if len(self.user_sentiment_trail) > _TRAIL_MAX:
            del self.user_sentiment_trail[: len(self.user_sentiment_trail) - _TRAIL_MAX]

        self.user_sentiment_inertia = _weighted_sentiment(self.user_sentiment_trail)


# ── Helpers ────────────────────────────────────────────────────────────────


def _weighted_emotion(trail: list[EmotionSnapshot], fluidity: float) -> EmotionSnapshot:
    """Compute weighted-average emotion from a trail.

    Weight formula: ``recency_factor ** (1 / fluidity)``
    where recency_factor goes from 0.0 (oldest) to 1.0 (newest).
    High fluidity makes recent emotions dominate.
    """
    if not trail:
        return EmotionSnapshot(name="neutral", intensity=0.5)

    if len(trail) == 1:
        return trail[0].model_copy()

    # Clamp fluidity to avoid division by zero
    exp = 1.0 / max(fluidity, 0.05)
    n = len(trail)

    # Single pass: accumulate weights, emotion contributions, and intensity
    emotion_weights: dict[str, float] = {}
    total_weight = 0.0
    weighted_intensity = 0.0
    for i, snap in enumerate(trail):
        recency = (i + 1) / n
        w = recency**exp
        total_weight += w
        emotion_weights[snap.name] = emotion_weights.get(snap.name, 0.0) + w
        weighted_intensity += snap.intensity * w

    dominant = max(emotion_weights, key=emotion_weights.get)  # type: ignore[arg-type]
    avg_intensity = weighted_intensity / total_weight

    return EmotionSnapshot(
        name=dominant,
        intensity=round(clamp(avg_intensity, 0.0, 1.0), 3),
        turn=trail[-1].turn,
    )


def _weighted_sentiment(trail: list[SentimentSnapshot]) -> SentimentSnapshot:
    """Compute weighted-average user sentiment (recency-weighted)."""
    if not trail:
        return SentimentSnapshot()

    if len(trail) == 1:
        return trail[0].model_copy()

    # Single pass
    n = len(trail)
    total_weight = 0.0
    w_valence = 0.0
    w_arousal = 0.0
    for i, s in enumerate(trail):
        w = (i + 1) / n
        total_weight += w
        w_valence += s.valence * w
        w_arousal += s.arousal * w

    return SentimentSnapshot(
        valence=round(clamp(w_valence / total_weight, -1.0, 1.0), 3),
        arousal=round(clamp(w_arousal / total_weight, 0.0, 1.0), 3),
        turn=trail[-1].turn,
    )
