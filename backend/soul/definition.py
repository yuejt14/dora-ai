"""SoulDefinition — Pydantic models mapping to the YAML soul schema + loader."""

from __future__ import annotations

import hashlib
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from backend.config import SOULS_DIR, get_logger

log = get_logger(__name__)


# ── Enums ──────────────────────────────────────────────────────────────────

_DRIFT_DELTAS: dict[str, float] = {"slow": 0.02, "medium": 0.05, "fast": 0.1}


class DriftRate(str, Enum):
    slow = "slow"
    medium = "medium"
    fast = "fast"

    @property
    def max_delta(self) -> float:
        return _DRIFT_DELTAS[self.value]


class Vocabulary(str, Enum):
    formal = "formal"
    mid_formal = "mid-formal"
    mid_casual = "mid-casual"
    casual = "casual"


class Humor(str, Enum):
    dry = "dry"
    witty = "witty"
    warm_playful = "warm-playful"
    sarcastic = "sarcastic"
    absurdist = "absurdist"


class TTSProvider(str, Enum):
    elevenlabs = "elevenlabs"
    piper = "piper"
    system = "system"


class TagTier(str, Enum):
    minimal = "minimal"
    standard = "standard"
    full = "full"


class MilestoneDetect(str, Enum):
    auto = "auto"
    llm = "llm"


class ContextTriggerType(str, Enum):
    first_session_of_day = "first_session_of_day"
    returned_after_long_absence = "returned_after_long_absence"
    follow_up_thought = "follow_up_thought"


# ── Sub-models ─────────────────────────────────────────────────────────────


class Meta(BaseModel):
    id: str
    version: int = 1


class Identity(BaseModel):
    name: str
    age: str
    background: str
    values: list[str] = Field(default_factory=list)


class CoreTrait(BaseModel):
    name: str
    behavior: str


class MutableTrait(BaseModel):
    name: str
    base: float = Field(ge=0.0, le=1.0)
    min: float = Field(ge=0.0, le=1.0)
    max: float = Field(ge=0.0, le=1.0)
    drift_rate: DriftRate = DriftRate.medium
    behavior: str


class Traits(BaseModel):
    core: list[CoreTrait] = Field(default_factory=list)
    mutable: list[MutableTrait] = Field(default_factory=list)


class EmotionTendency(BaseModel):
    triggers: list[str] = Field(default_factory=list)
    expression: str = ""
    range: tuple[float, float] = (0.0, 1.0)


class MoodConfig(BaseModel):
    decay_hours: float = 6.0


class Emotions(BaseModel):
    baseline: str = "neutral"
    fluidity: float = Field(default=0.5, ge=0.0, le=1.0)
    tendencies: dict[str, EmotionTendency] = Field(default_factory=dict)
    mood: MoodConfig = Field(default_factory=MoodConfig)


class SpeakingStyle(BaseModel):
    voice: str = ""
    vocabulary: Vocabulary = Vocabulary.mid_casual
    humor: Humor = Humor.warm_playful
    quirks: list[str] = Field(default_factory=list)
    by_emotion: dict[str, str] = Field(default_factory=dict)


class VoiceBase(BaseModel):
    speed: float = 1.0
    pitch: float = 0.0
    stability: float = 0.75


class CadenceConfig(BaseModel):
    filler_words: list[str] = Field(default_factory=list)
    pause_markers: list[str] = Field(default_factory=list)
    emphasis_style: str = ""


class VoiceConfig(BaseModel):
    tts_provider: TTSProvider = TTSProvider.system
    voice_id: str = ""
    base: VoiceBase = Field(default_factory=VoiceBase)
    by_emotion: dict[str, VoiceBase] = Field(default_factory=dict)
    cadence: CadenceConfig = Field(default_factory=CadenceConfig)


class RelationshipStage(BaseModel):
    name: str
    after_turns: int = 0
    description: str = ""
    modifiers: dict[str, float] = Field(default_factory=dict)


class Relationship(BaseModel):
    stages: list[RelationshipStage] = Field(default_factory=list)


class SeedOpinion(BaseModel):
    topic: str
    stance: str


class OpinionFormation(BaseModel):
    min_discussions: int = 3


class Opinions(BaseModel):
    seed: list[SeedOpinion] = Field(default_factory=list)
    formation: OpinionFormation = Field(default_factory=OpinionFormation)


class SoftBoundary(BaseModel):
    topic: str
    approach: str


class Boundaries(BaseModel):
    hard: list[str] = Field(default_factory=list)
    soft: list[SoftBoundary] = Field(default_factory=list)


class SpontaneityTypes(BaseModel):
    tangent: float = 0.30
    callback: float = 0.30
    provocation: float = 0.20
    non_sequitur: float = 0.10
    vulnerability: float = 0.10


class SpontaneityConfig(BaseModel):
    base: float = Field(default=0.15, ge=0.0, le=1.0)
    min: float = Field(default=0.05, ge=0.0, le=1.0)
    max: float = Field(default=0.40, ge=0.0, le=1.0)
    drift_rate: DriftRate = DriftRate.slow
    cooldown_turns: int = 5
    types: SpontaneityTypes = Field(default_factory=SpontaneityTypes)


class SilenceTrigger(BaseModel):
    after_minutes: int
    mood_filter: list[str] | None = None
    prompt_hint: str = ""


class ContextTrigger(BaseModel):
    type: ContextTriggerType
    prompt_hint: str = ""
    threshold_hours: float | None = None
    delay_minutes: float | None = None


class InitiativeConfig(BaseModel):
    enabled: bool = True
    silence_triggers: list[SilenceTrigger] = Field(default_factory=list)
    context_triggers: list[ContextTrigger] = Field(default_factory=list)
    max_per_hour: int = 3
    respect_dnd: bool = True


class MilestoneDefinition(BaseModel):
    id: str
    detect: MilestoneDetect = MilestoneDetect.auto


class GrowthGates(BaseModel):
    min_turns: int = 20
    min_hours: float = 24.0


class GrowthConfig(BaseModel):
    gates: GrowthGates = Field(default_factory=GrowthGates)
    milestones: list[MilestoneDefinition] = Field(default_factory=list)


# ── Top-level SoulDefinition ───────────────────────────────────────────────


class SoulDefinition(BaseModel):
    meta: Meta
    identity: Identity
    traits: Traits = Field(default_factory=Traits)
    speaking_style: SpeakingStyle = Field(default_factory=SpeakingStyle)
    emotions: Emotions = Field(default_factory=Emotions)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    relationship: Relationship = Field(default_factory=Relationship)
    opinions: Opinions = Field(default_factory=Opinions)
    quirks: list[str] = Field(default_factory=list)
    boundaries: Boundaries = Field(default_factory=Boundaries)
    spontaneity: SpontaneityConfig = Field(default_factory=SpontaneityConfig)
    initiative: InitiativeConfig = Field(default_factory=InitiativeConfig)
    growth: GrowthConfig = Field(default_factory=GrowthConfig)
    tag_tier: TagTier = TagTier.standard


# ── YAML loader ────────────────────────────────────────────────────────────


def load_soul(path: Path) -> tuple[SoulDefinition, str]:
    """Load and validate a SoulDefinition from a YAML file.

    Returns:
        (definition, sha256_hex) — reads the file once for both.
    """
    data = path.read_bytes()
    h = hashlib.sha256(data).hexdigest()
    raw = yaml.safe_load(data.decode("utf-8"))
    return SoulDefinition.model_validate(raw), h


def scan_souls(souls_dir: Path = SOULS_DIR) -> list[tuple[SoulDefinition, str]]:
    """Scan the souls directory and return (definition, hash) pairs."""
    results: list[tuple[SoulDefinition, str]] = []
    if not souls_dir.is_dir():
        log.warning("Souls directory not found: %s", souls_dir)
        return results
    for path in sorted(souls_dir.glob("*.yaml")):
        try:
            defn, h = load_soul(path)
            results.append((defn, h))
            log.info("Loaded soul: %s (%s)", defn.meta.id, path.name)
        except Exception:
            log.exception("Failed to load soul from %s", path)
    return results
