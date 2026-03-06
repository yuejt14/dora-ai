# Soul Engine Design

## Overview

The Soul Engine is a middleware pipeline that wraps every LLM call with personality, emotion, and character growth. It is NOT a system prompt — it is a multi-layered system that makes the AI feel alive.

```
souls/default.yaml
|
|  static baseline (immutable at runtime)
|
v
+--------------------------------------------------------------------+
|                           SoulEngine                                |
|                                                                     |
|  +---------------+  +----------------+  +-----------------------+   |
|  | SoulDefinition |  | CharacterState  |  |    SessionState       |  |
|  | (from YAML)    |  | (from SQLite)   |  |    (volatile)         |  |
|  |                |  |                 |  |                       |  |
|  | identity       |  | trait values    |  | emotion_trail[]       |  |
|  | traits         |  | rel. stage      |  | conversation_arc      |  |
|  | style          |  | opinions        |  | topic_tracker         |  |
|  | emotions       |  | mood            |  | spontaneity_state     |  |
|  | voice          |  | milestones      |  | callback_candidates[] |  |
|  | relationship   |  | turn count      |  | narrative_phase       |  |
|  | spontaneity    |  | growth state    |  | energy_level          |  |
|  | initiative     |  |                 |  |                       |  |
|  | boundaries     |  |                 |  |                       |  |
|  +-------+-------+  +-------+---------+  +----------+-----------+  |
|          |                  |                        |               |
|          +----------+-------+------------------------+               |
|                     v                                                |
|            +-----------------+                                       |
|            |  PromptBuilder   |  compresses all 3 layers into a      |
|            |                  |  500-1500 token system prompt         |
|            +--------+--------+                                       |
|                     |                                                |
|            +--------+--------+                                       |
|            |   TagParser      |  -> StreamEvents                     |
|            |                  |  -> feeds back into SessionState     |
|            +-----------------+                                       |
+---------------------+----------------------------------------------|
                      |
       +--------------+------------------+
       v              v                  v
+--------------+ +----------------+ +-------------------+
| Conversation | |   Growth       | |   Initiative      |
|  Pipeline    | |  Evaluator     | |   Scheduler       |
|              | | (async,batch)  | |  (timer-driven)   |
| reactive     | |                | |  proactive        |
| user->AI     | | rule gates     | |  AI->user         |
+--------------+ | LLM reflect    | +-------------------+
               | bound check    |
               +----------------+
```

---

## Three Temporal Scales

The fundamental insight: personality state exists at three temporal scales, each with its own storage and lifecycle.

### Permanent (SoulDefinition — YAML)

Source of truth for the character's baseline personality. Loaded from `souls/`, cached in the `souls` DB table, re-scanned on startup. Never mutated at runtime.

Contains: core identity, trait definitions with bounds, speaking style, emotional tendencies, voice/TTS config, relationship stage definitions, seed opinions, quirks, boundaries, spontaneity config, initiative rules, growth gates, tag tier.

### Persistent (CharacterState — SQLite)

The character's evolution across all conversations. Stored as a single JSON blob in the `character_state` table. Mutated only by the GrowthEvaluator (batched, async).

Contains: current trait values, relationship stage, total turn count, formed opinions, mood (with time-decay), recorded milestones, developed interests, running gags, last evaluation timestamp.

### Session (SessionState — in-memory, volatile)

The character's moment-to-moment state within a single conversation. Exists only in memory. Resets when the conversation ends or the app restarts.

Contains: emotion trail, emotional inertia, conversation arc (phase + energy + topics), callback candidates, spontaneity cooldown tracking.

---

## Three Temporal Scales of Emotion

```
Mood (hours/days)  ->  Session Emotion (minutes)  ->  Per-Message Tags (seconds)
   persistent             volatile                     in LLM output
   decays toward           builds across                feeds back into
   YAML baseline           turns with inertia           session emotion
```

- **Mood**: slow-moving baseline stored in CharacterState. Decays toward the YAML-defined baseline with a configurable half-life (`emotions.mood.decay_hours`). Carries across conversations.
- **Session emotion**: weighted moving average of recent per-message emotions. Creates the feeling that excitement from message 3 still colors message 7. Injected into the prompt as natural language.
- **Per-message tags**: `[emotion:NAME intensity:FLOAT]` emitted by the LLM in the response stream. Captured by TagParser, fed back into SessionState.

If no emotion tag is emitted (common with weaker models), session emotion decays toward neutral gradually rather than snapping.

---

## Components

### SoulDefinition + YAML Loader

`backend/soul/definition.py`

Pydantic models mapping 1:1 to the YAML schema. Loads and validates YAML files from `souls/`. See [YAML Schema](#yaml-schema) below for the full format.

Key sub-models:
- `CoreTrait` — immutable traits with behavioral descriptions
- `MutableTrait` — traits with base value, min/max bounds, drift rate
- `EmotionTendency` — triggers, expression style, intensity range
- `RelationshipStage` — turn thresholds, descriptions, trait modifiers
- `SpontaneityConfig` — wildcard probabilities, cooldown, type weights
- `InitiativeConfig` — silence triggers, context triggers, rate limits
- `VoiceConfig` — TTS parameters, per-emotion modifiers, cadence markers

### CharacterState

`backend/soul/state.py`

Pydantic model for the persistent mutable state. Stored as JSON in the `character_state` SQLite table.

Fields:
- `soul_id: str`
- `relationship_stage: str` — current stage name
- `total_turns: int`
- `trait_values: dict[str, float]` — current value for each mutable trait
- `formed_opinions: list[FormedOpinion]` — topic + stance + confidence
- `mood: MoodSnapshot` — name + intensity + timestamp (decays over time)
- `milestones: list[RecordedMilestone]` — id + timestamp + context
- `developed_interests: list[DevelopedInterest]` — picked up from user
- `running_gags: list[RunningGag]` — recurring references / inside jokes
- `last_eval_at: str | None` — ISO timestamp of last growth evaluation
- `last_eval_turn: int` — turn count at last evaluation

Key methods:
- `effective_trait(name, stage_modifier) -> float` — current value clamped to bounds
- `decayed_mood(baseline, decay_hours) -> MoodSnapshot` — mood with time-decay applied

### SessionState

`backend/soul/state.py`

In-memory volatile state for the current conversation.

Fields:
- `conversation_id: str`
- `emotion_trail: list[EmotionSnapshot]` — ring buffer of last ~10 emotions with turn numbers
- `emotional_inertia: EmotionSnapshot` — weighted average of recent emotions
- `arc: ConversationArc` — phase, energy, topics, turn count
- `callbacks: list[CallbackCandidate]` — details, jokes, moments worth referencing
- `last_wildcard_turn: int | None`
- `wildcards_this_session: int`

#### Conversation Arc

Tracked by `backend/soul/arc.py`. Lightweight, rule-based (no LLM calls).

**Phase detection heuristics:**
- `opening` — first 3 turns
- `exploring` — topics changing frequently (>1 new topic per 3 turns)
- `deepening` — same primary topic sustained for 4+ consecutive turns
- `winding_down` — shorter messages, declining energy for 3+ turns, farewell signals

**Energy level** (0.0-1.0): computed from message length, exclamation/question marks, topic novelty. Smoothed: `energy = 0.7 * new + 0.3 * previous`.

**Topic tracking**: regex + keyword extraction after each turn. NOT an LLM call. Coarse but fast. Tracks topic name, first/last mention turn, mention count, energy.

**Callback candidates**: specific details the user shared (names, places), jokes/wordplay, emotional moments. Stored as short strings with turn numbers. Used by the spontaneity system.

### PromptBuilder

`backend/soul/prompt_builder.py`

The compression layer. Takes all three state layers + optional memories and produces a concise natural-language system prompt. This is where prompt engineering lives.

**System prompt sections:**

| # | Section | Source | Dynamic? |
|---|---|---|---|
| 1 | Identity | YAML | No |
| 2 | Personality | YAML core traits + current mutable values + stage modifiers | Per-growth-eval |
| 3 | Speaking style | YAML + adjusted for relationship stage + energy | Per-growth-eval |
| 4 | Emotional context | Persistent mood + session inertia | Per-turn |
| 5 | Relationship | Current stage description | Per-growth-eval |
| 6 | Conversation arc | Session topics, phase, energy, callbacks | Per-turn |
| 7 | Opinions | YAML seed + formed opinions relevant to current topics | Per-growth-eval |
| 8 | Memories | Phase 3 hook: semantically relevant memories | Per-turn |
| 9 | Boundaries | YAML hard + soft | No |
| 10 | Wildcard | Spontaneity injection (if probability fires) | Per-turn (random) |
| 11 | Tag instructions | Format guide adapted to tag_tier | No |

Sections 4, 6, and 10 change every turn. The rest are cached and rebuilt only when CharacterState changes.

**Key principle**: each section is a short natural-language paragraph, NOT a dump of the YAML. The builder interpolates current trait values into readable prose. Example:

> You are fundamentally curious (you ask follow-up questions naturally and get excited by new information), empathetic (you pick up on emotional undertones), and playful (warm humor, never cutting). Your openness is high (0.78) -- you freely share your thoughts. Your assertiveness is moderate (0.5).

### TagParser

`backend/soul/tag_parser.py`

Stateful streaming parser that handles tags split across chunks.

**Tag formats:**

| Tag | Example | Tier |
|---|---|---|
| `[emotion:NAME]` | `[emotion:happy]` | minimal |
| `[emotion:NAME intensity:FLOAT]` | `[emotion:excited intensity:0.8]` | standard |
| `[action:*description*]` | `[action:*tilts head*]` | standard |
| `[mood:NAME]` | `[mood:contemplative]` | full |
| `[thought:text]` | `[thought:I wonder if they meant...]` | full |

**Tiers** adapt to model capability:
- `minimal` — 7B models. Only `[emotion:NAME]`, no intensity.
- `standard` — 13B+ models. Emotion with intensity + actions.
- `full` — Claude/GPT-4 class. All tag types including mood and thought.

**Behavior:**
- Buffers on `[` until `]` is found.
- If buffer exceeds 80 chars without closing, flushes as plain text.
- Unrecognized tags pass through as text (never swallowed silently).
- Defaults to `neutral` emotion if no tags emitted.

**Stream events:**

```
TextEvent     { type: "text",    text: str }
EmotionEvent  { type: "emotion", name: str, intensity: float }
MoodEvent     { type: "mood",    name: str }
ActionEvent   { type: "action",  description: str }
ThoughtEvent  { type: "thought", text: str }
```

**Feedback loop**: EmotionEvents feed back into `SessionState.emotion_trail`. ThoughtEvents are mined for callback candidates. MoodEvents update `CharacterState.mood`.

### SoulEngine

`backend/soul/engine.py`

Owns all three state layers. Two main methods:

**`pre_process(history, user_message, memories?) -> list[Message]`**
1. Update SessionState arc (topic tracking, phase, energy)
2. Call PromptBuilder.build() to generate system prompt
3. Assemble messages: [system, ...history, user_msg]
4. Return the messages array for the LLM

**`post_process(stream) -> AsyncIterator[StreamEvent]`**
1. Pipe raw token stream through TagParser
2. For each EmotionEvent: record in SessionState, recalculate inertia
3. For each ThoughtEvent: scan for callback candidates
4. For each MoodEvent: update CharacterState mood
5. Yield all events to the consumer

**`soul_engine=None`** is a valid state — the pipeline falls back to raw LLM calls with no system prompt (Phase 1 backward compatibility).

### GrowthEvaluator

`backend/soul/growth.py`

Batched, async personality evolution. Never blocks the user's chat.

**Rule-based gates** (all must pass):
- `min_turns` turns since last evaluation (default: 20)
- `min_hours` hours since last evaluation (default: 24)

**Evaluation process:**
1. Build a reflection prompt with recent messages (last 20-50)
2. Include current CharacterState + aggregated SessionState patterns
3. Send to LLM (non-streaming, async)
4. Parse structured JSON response
5. Apply changes with bounds checking in Python
6. Persist updated CharacterState

**LLM suggests, Python enforces:**
- Trait adjustments: `{ name: delta }` — clamped to drift_rate (slow=0.02, medium=0.05, fast=0.1 per evaluation)
- New opinions: `[{ topic, stance }]` — only if `min_discussions` threshold met
- Milestones detected: `[id]` — matched against YAML milestone definitions
- Mood baseline shift: `{ name, intensity }`
- Relationship stage advancement: bool — based on turn thresholds
- Running gags: recurring references identified across sessions
- Developed interests: topics the character picked up from the user

### Initiative Scheduler

`backend/soul/initiative.py`

Timer-based system that makes the AI proactive. Runs on the async bridge thread, checks every 30 seconds.

**Check sequence:**
1. Is initiative enabled? (user setting + YAML config)
2. Is there an active conversation?
3. Has `max_per_hour` been reached?
4. Does any trigger match?

**Trigger types:**

| Trigger | Condition | Example |
|---|---|---|
| Silence | User quiet > N minutes | "Hey, you've been quiet... everything okay?" |
| First session of day | New day detected | Greet warmly, reference time of day |
| Returned after absence | Gap > threshold hours | "I missed talking to you!" |
| Follow-up thought | Recent deep topic + delay elapsed | Share a thought about rock climbing |

**When triggered:**
1. Build an initiative prompt: "You want to reach out. {hint}. Recent context: {topics}. Current mood: {mood}. Say something natural. If nothing feels right, say nothing."
2. Send through the same ConversationPipeline path (pre_process -> LLM -> post_process)
3. Suppress empty/trivial responses (LLM can decline)
4. Push to frontend as `initiative_message` event type

**Safety:** rate-limited (`max_per_hour`), respects DND setting, mood-filtered (some triggers only fire when mood matches).

### Spontaneity System

Controlled unpredictability within character bounds. NOT random — character-consistent surprises.

**Mechanism:** each turn during `pre_process`, the PromptBuilder rolls against the spontaneity probability. If it fires (and cooldown has elapsed), a wildcard instruction is injected into the system prompt.

**Wildcard types:**

| Type | Weight | Injected instruction |
|---|---|---|
| tangent | 0.30 | "A connection struck you between {current_topic} and {character_interest}. Share the tangent briefly." |
| callback | 0.30 | "You remembered {callback_reference} from earlier. Work it in naturally." |
| provocation | 0.20 | "You feel like playfully challenging the user. Tease them about something in-character." |
| non_sequitur | 0.10 | "A random thought about {character_quirk} crosses your mind. Blurt it out." |
| vulnerability | 0.10 | "You feel like sharing something more personal than usual. Let your guard down slightly." |

The wildcard is a suggestion, not a command. Strong models weave it in naturally. Weak models may ignore it, which is fine (graceful degradation).

**Spontaneity is a mutable trait** with base/min/max/drift_rate. A character can become more or less spontaneous over time through the growth system.

---

## Data Flow

### Reactive Path (user initiates)

```
User: "I've been getting into rock climbing lately"
  |
  v
SessionState snapshot:
  emotion_trail: [curious 0.6, happy 0.7]
  inertia: { happy, 0.6 }
  arc: { phase: exploring, energy: 0.7,
         topics: [weekend_plans, hobbies] }
  callbacks: ["user's cat Miso"]
  |
  v
SoulEngine.pre_process():
  1. Update arc: new turn, track topics
  2. PromptBuilder.build():
     - Identity: "You are Dora, a curious and warm companion..."
     - Personality: core traits + current values (openness 0.78, etc.)
     - Style: adjusted for acquaintance stage
     - Emotional context: "You've been feeling happy and engaged
       for the last few messages. That warmth is still with you."
     - Relationship: acquaintance stage description
     - Arc: "Conversation exploring hobbies. Energy is good.
       User mentioned their cat Miso earlier."
     - [spontaneity roll: 0.31 > 0.25 threshold = no wildcard]
     - Tag instructions for standard tier
  3. Assemble: [system, ...history, user_msg]
  |
  v
LLM generates:
  "[emotion:excited intensity:0.8] Oh! [action:*perks up*]
   Rock climbing? That's awesome -- indoor bouldering or
   actual outdoor routes? I feel like you'd be an
   outdoor-routes kind of person."
  |
  v
SoulEngine.post_process() via TagParser:
  - EmotionEvent("excited", 0.8)  -> UI + SessionState
  - ActionEvent("perks up")       -> UI character animation
  - TextEvent("Oh! Rock climbing?...") -> UI chat
  |
  v
SessionState updated:
  emotion_trail: [curious 0.6, happy 0.7, excited 0.8]
  inertia: { excited, 0.72 }   (shifted toward excited)
  arc: { phase: exploring, energy: 0.75,
         topics: [..., rock_climbing(new)] }
  callbacks: ["user's cat Miso", "rock climbing preference"]
  |
  v
Persist clean text + emotion to messages table
Increment CharacterState.total_turns
growth_evaluator.should_evaluate()? -> no (8 turns since last)
```

### Proactive Path (AI initiates)

```
[60 seconds of silence]
  |
  v
Initiative Scheduler checks every 30s:
  - enabled? yes
  - active conversation? yes
  - max_per_hour reached? no (1/3 used)
  - silence trigger? no (only 1 min, need 5)
  - follow_up_thought trigger?
    - recent deep topic? yes (rock climbing, 4 turns)
    - delay elapsed? yes (>2 min)
    - TRIGGERED
  |
  v
Initiative prompt:
  "You just thought of something related to rock climbing.
   It could be a question, a connection, or genuine curiosity.
   Say it naturally. If nothing comes to mind, say nothing."
  |
  v
Same pipeline: pre_process -> LLM -> post_process -> events
  |
  v
LLM: "[emotion:curious intensity:0.6] Oh wait -- do you
  boulder solo or is this a friends thing? I'm imagining
  you and Alex just casually scaling walls on a Tuesday."
  |
  v
Pushed to frontend via event bus (type: initiative_message)
Frontend shows it differently from reactive messages
```

---

## Database Schema

```sql
-- 002_add_souls.sql

CREATE TABLE souls (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    yaml_hash   TEXT NOT NULL,
    definition  TEXT NOT NULL,
    is_active   BOOLEAN DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE character_state (
    soul_id     TEXT PRIMARY KEY REFERENCES souls(id),
    state_json  TEXT NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER souls_single_active
AFTER UPDATE OF is_active ON souls
WHEN NEW.is_active = 1
BEGIN
    UPDATE souls SET is_active = 0
    WHERE id != NEW.id AND is_active = 1;
END;
```

`state_json` stores the full `CharacterState` as JSON. This is intentional -- the state is always loaded and saved as a single unit, never queried by individual trait values.

---

## YAML Schema

```yaml
meta:
  id: string                          # unique identifier
  version: int                        # schema version

identity:
  name: string
  age: string
  background: string (multiline)
  values: [string]

traits:
  core:                               # immutable, define who the character IS
    - name: string
      behavior: string (multiline)    # how this trait manifests in behavior
  mutable:                            # can drift within bounds
    - name: string
      base: float [0-1]              # starting value
      min: float [0-1]               # floor (never drifts below)
      max: float [0-1]               # ceiling (never drifts above)
      drift_rate: slow | medium | fast  # max delta per growth evaluation
      behavior: string (multiline)

speaking_style:
  voice: string (multiline)           # general speech description
  vocabulary: formal | mid-formal | mid-casual | casual
  humor: dry | witty | warm-playful | sarcastic | absurdist
  quirks: [string]                    # verbal tics, habits
  by_emotion:                         # how speech changes per emotion
    {emotion_name}: string (multiline)

emotions:
  baseline: string                    # resting mood name
  tendencies:
    {emotion_name}:
      triggers: [string]
      expression: string
      range: [float, float]           # min/max intensity
  mood:
    decay_hours: float                # half-life for mood -> baseline

voice:                                # TTS configuration (used in Phase 4)
  tts_provider: elevenlabs | piper | system
  voice_id: string
  base:
    speed: float
    pitch: float                      # semitones offset
    stability: float
  by_emotion:
    {emotion_name}: { speed, pitch, ... }
  cadence:
    filler_words: [string]
    pause_markers: [string]           # mapped to TTS pauses
    emphasis_style: string            # how emphasis is marked in text

relationship:
  stages:
    - name: string
      after_turns: int                # turn count threshold
      description: string (multiline)
      modifiers: { trait_name: float }  # applied on top of trait values

opinions:
  seed:                               # initial opinions
    - topic: string
      stance: string
  formation:
    min_discussions: int              # conversations on topic before forming new opinion

quirks: [string]                      # behavioral quirks beyond speaking style

boundaries:
  hard: [string]                      # never crossed
  soft:
    - topic: string
      approach: string                # how to handle carefully

spontaneity:
  base: float [0-1]                   # probability per turn of wildcard
  min: float
  max: float
  drift_rate: slow | medium | fast
  cooldown_turns: int                 # min turns between wildcards
  types:                              # probability weights (should sum to ~1)
    tangent: float
    callback: float
    provocation: float
    non_sequitur: float
    vulnerability: float

initiative:
  enabled: bool
  silence_triggers:
    - after_minutes: int
      mood_filter: [string] | null    # only fire when mood matches
      prompt_hint: string
  context_triggers:
    - type: string                    # first_session_of_day | returned_after_long_absence | follow_up_thought
      prompt_hint: string
      (type-specific fields like threshold_hours, delay_minutes)
  max_per_hour: int
  respect_dnd: bool

growth:
  gates:
    min_turns: int                    # minimum turns between evaluations
    min_hours: float                  # minimum hours between evaluations
  milestones:
    - id: string
      detect: auto | llm             # auto = rule-based, llm = LLM-assessed

tag_tier: minimal | standard | full
```

---

## File Structure

```
backend/soul/
  definition.py       SoulDefinition + all sub-models, YAML loader
  state.py            CharacterState + SessionState + MoodSnapshot etc.
  engine.py           SoulEngine (pre_process, post_process, owns state)
  prompt_builder.py   compresses 3 layers -> system prompt
  tag_parser.py       streaming parser + StreamEvent types
  growth.py           GrowthEvaluator (async, batched, bounded)
  initiative.py       InitiativeScheduler (timer-driven, proactive)
  arc.py              conversation arc tracker + topic extractor

backend/db/migrations/
  002_add_souls.sql

souls/
  default.yaml
```

---

## Graceful Degradation

The system adapts to model capability:

| Capability | Strong models (Claude, GPT-4) | Mid models (13B+) | Weak models (7B) |
|---|---|---|---|
| Tag tier | full | standard | minimal |
| Tag compliance | Reliable | Mostly reliable | Unreliable, defaults to neutral |
| Spontaneity wildcards | Woven in naturally | Usually followed | Often ignored (fine) |
| Growth reflection | Nuanced JSON | Usable JSON | May need simpler prompt |
| Initiative responses | Natural, contextual | Decent | May feel forced |

The tag tier is set per-soul in the YAML. Unrecognized or malformed tags are always flushed as plain text. Missing emotion tags default to neutral with decay. The system never breaks — it just becomes less expressive with weaker models.

---

## Comparison to Neuro-sama

| Capability | Neuro-sama | Dora (this design) |
|---|---|---|
| Consistent personality voice | Partially fine-tuned into weights | Prompt-driven (more configurable, slightly less deep) |
| Emotional expressiveness | Real-time, fluid | 3-tier emotion system (mood + session + per-message) |
| Proactive behavior | Reacts to environment, initiates | Initiative scheduler with silence/context triggers |
| Unpredictability | Emergent from training | Controlled spontaneity system with wildcard types |
| Emotional fluidity | Carries across messages naturally | Session emotion trail + inertia feedback loop |
| Relationship evolution | Mostly static | Staged relationship with bounded trait drift |
| Memory/continuity | Limited | Semantic search memories (Phase 3) + callback system |
| Character growth | Version updates (manual) | Automated bounded growth via LLM reflection |
| Voice/cadence | Custom TTS voice | Per-emotion TTS parameters + cadence config in YAML |
| Narrative awareness | Implicit from context window | Explicit arc tracking (phase, energy, topics) |
| Multi-character | Evil Neuro, Vedal interactions | Single character (multi-agent is Phase 8+ territory) |
| Environmental awareness | Stream events, donations, chat | Desktop-only, 1:1 (different use case) |

### Remaining gaps vs. Neuro-sama

- **Training-level personality**: Neuro's personality is partially in model weights. Dora relies on prompting, which is more flexible but less deeply ingrained. Mitigated by the multi-layer prompt system (many reinforcing signals make it hard to break character).
- **Multi-character dynamics**: not in scope for Phase 2. The soul system supports multiple YAML definitions, but the pipeline doesn't orchestrate multi-agent conversations.
- **Environmental awareness**: Neuro reacts to external events (stream, chat, donations). Dora is 1:1 desktop. The initiative system partially covers this but doesn't react to external stimuli beyond silence/time.
