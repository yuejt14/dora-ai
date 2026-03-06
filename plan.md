# Dora AI — Implementation Plan

## Current State

- Phase 2.2 complete: TagParser (streaming, tier-filtered), EmotionClassifier (keyword/pattern), SentimentAnalyzer (valence/arousal), 61 new tests (135 total)
- Phase 2.1 complete: SoulDefinition + CharacterState + SessionState models, default.yaml, souls migration, 53 new tests (74 total)
- Phase 1.4 complete: pytest + pytest-asyncio, 21 unit tests across all Phase 1 modules
- Phase 1.3 complete: Provider + DB integration, asyncio bridge, conversation pipeline, CLI chat loop
- Phase 1.2 complete: SQLite database layer with migrations, query helpers, WAL mode
- Phase 1.1 complete: config, LLM provider layer, Ollama streaming, structured logging
- No frontend, no UI yet

## Rules

- **Never create empty folders** — only create directories when adding files that belong there
- **Never install dependencies early** — add each dependency in the task that first uses it
- **Backend first** — build all core backend functionality before touching frontend/UI
- **Local first** — fully functional with local models (Ollama) before integrating cloud API providers
- **Drop LangChain** — the custom provider layer is simpler and cleaner; remove from `pyproject.toml`

---

## Phase 1 — LLM + Persistence

**Goal:** Talk to a local LLM and persist conversations in SQLite.

### 1.1 Config & Provider

- [x] `backend/config.py` — settings, paths, env var loading (install `python-dotenv`, `pydantic`; load from `.env`)
- [x] `backend/providers/base.py` — `LLMProvider` ABC with `stream_chat(messages) -> AsyncIterator[str]`
- [x] `backend/providers/ollama.py` — Ollama provider via httpx (install `httpx`)
- [x] `backend/providers/router.py` — `ProviderRouter` (Ollama only for now)
- [x] Set up `logging` configuration (structured output, per-module loggers)

### 1.2 Database

- [x] `backend/db/migrations/001_initial.sql` — `conversations`, `messages`, `settings`, `_migrations` tables
- [x] `backend/db/database.py` — SQLite connection (WAL mode), migration runner, query helpers

### 1.3 Integration

- [x] Wire provider + DB together: send message → stream response → persist both
- [x] Set up the asyncio bridge (dedicated event loop thread for async providers, callable from sync code)
- [x] CLI smoke test: multi-turn conversation, persisted and reloadable across restarts

### 1.4 Tests

- [x] Install `pytest` + `pytest-asyncio` as dev dependencies
- [x] Unit tests for Ollama provider (mock httpx, verify streaming contract and error handling)
- [x] Unit tests for database (migrations apply cleanly, CRUD operations, WAL mode)
- [x] Unit tests for AsyncBridge (run coroutine, run_iter, exception propagation)
- [x] Unit tests for ConversationPipeline (create/list, send/persist, streaming, error handling, history)

---

## Phase 2 — Soul Engine

**Goal:** Personality-driven responses with emotional fluidity, character growth, proactive behavior, and controlled unpredictability. See `docs/soul-engine.md` for full design.

### 2.1 Definition + State Models

- [x] `backend/soul/definition.py` — `SoulDefinition` Pydantic model + YAML loader (install `pyyaml`)
- [x] `backend/soul/state.py` — `CharacterState` (persistent, SQLite) + `SessionState` (volatile, in-memory) + supporting models (`MoodSnapshot`, `FormedOpinion`, `RecordedMilestone`, `EmotionSnapshot`, `SentimentSnapshot`, `ConversationArc`, etc.)
- [x] `souls/default.yaml` — default companion personality (full schema: identity, traits, speaking style, voice, emotions, relationship stages, opinions, quirks, boundaries, spontaneity, initiative, growth gates, tag tier)
- [x] `backend/db/migrations/002_add_souls.sql` — `souls` table (YAML cache + hash for change detection) + `character_state` table (single JSON blob) + single-active-soul triggers (INSERT + UPDATE)

### 2.2 Tag Parser + Emotion Classifier

- [x] `backend/soul/tag_parser.py` — stateful streaming tag parser with `StreamEvent` types (`TextEvent`, `EmotionEvent`, `MoodEvent`, `ActionEvent`, `ThoughtEvent`)
  - Handles tags split across chunks (buffers on `[` until `]`)
  - Flushes as plain text if buffer exceeds 80 chars
  - Three tag tiers: `minimal` (7B), `standard` (13B+), `full` (Claude/GPT-4)
  - Defaults to neutral emotion when no tags emitted
- [x] `backend/soul/emotion_classifier.py` — text-based emotion fallback when LLM doesn't emit tags
  - Phase 2: keyword/pattern-based (no ML dependencies). Scores text against emotion word lists, exclamation density, question clusters, sentence length patterns
  - Returns `EmotionEstimate(name, intensity, confidence)`. Priority: tag > classifier > neutral
  - Phase 3+ upgrade path: swap in a small transformer classifier (e.g. `roberta-base-go_emotions`) once `torch` is available
- [x] `backend/soul/sentiment.py` — user sentiment analyzer on incoming user messages
  - Phase 2: keyword/pattern-based. Detects valence (positive/negative) and arousal (calm/intense)
  - Feeds `SessionState.user_sentiment_trail` and `user_sentiment_inertia`
  - PromptBuilder injects: "The user seems [upbeat/subdued/frustrated]..."
  - Phase 4 upgrade: STT pipeline feeds vocal prosody into the same trail
- [x] Unit tests for tag parser (split tags, missing tags, malformed tags, all event types, tier filtering)
- [x] Unit tests for emotion classifier (keyword matching, priority over neutral, confidence thresholds)
- [x] Unit tests for sentiment analyzer (valence/arousal detection, inertia calculation)

### 2.3 Prompt Builder + Arc Tracker

- [ ] `backend/soul/prompt_builder.py` — compresses SoulDefinition + CharacterState + SessionState + memories into a 500-1500 token natural-language system prompt. Caches static sections, rebuilds dynamic sections (emotional context, arc, wildcards) per-turn.
- [ ] `backend/soul/arc.py` — conversation arc tracker: rule-based phase detection (opening/exploring/deepening/winding_down), energy level computation, lightweight topic extraction (regex, not LLM), callback candidate collection

### 2.4 Soul Engine + Pipeline Integration

- [ ] `backend/soul/engine.py` — `SoulEngine` with `pre_process()` and `post_process()`:
  - Pre: run user sentiment analyzer on user message, update SessionState arc, build system prompt via PromptBuilder (includes user sentiment + emotional context scaled by fluidity), assemble messages
  - Post: pipe stream through TagParser, run emotion classifier as fallback if no tags found, feed EmotionEvents back into SessionState (inertia scaled by fluidity), mine ThoughtEvents for callbacks, update mood from MoodEvents
  - Supports `soul_engine=None` for raw LLM fallback (Phase 1 backward compat)
- [ ] Update `backend/conversation.py` — yield `StreamEvent`s instead of raw strings, increment turn count, hook for growth evaluation trigger
- [ ] CLI test: personality-flavored streamed responses with emotion tags parsed out, emotional inertia carrying across turns

### 2.5 Spontaneity System

- [ ] Spontaneity integration in PromptBuilder — per-turn probability roll against spontaneity trait, wildcard injection with cooldown. Types: tangent, callback, provocation, non_sequitur, vulnerability. Spontaneity is a mutable trait (drifts via growth system).

### 2.6 Growth Evaluator

- [ ] `backend/soul/growth.py` — `GrowthEvaluator`: async, batched, never blocks chat
  - Rule-based gates: min_turns + min_hours since last evaluation
  - LLM reflection prompt with recent messages + current state
  - Structured JSON response: trait adjustments, new opinions, milestones, mood shift, relationship stage, running gags, developed interests
  - Python enforces all bounds (drift rate caps magnitude, min/max clamps values)
- [ ] Unit tests for bounds enforcement (drift rate clamping, min/max, stage advancement)

### 2.7 Initiative Scheduler

- [ ] `backend/soul/initiative.py` — `InitiativeScheduler`: timer-driven (30s check interval), runs on async bridge thread
  - Silence triggers (configurable thresholds, mood-filtered)
  - Context triggers (first_session_of_day, returned_after_absence, follow_up_thought)
  - Rate limited (max_per_hour), respects DND setting
  - Sends through same pipeline path, frontend shows as `initiative_message`
  - LLM can decline to speak (empty response suppressed)
- [ ] CLI test: silence trigger fires after idle period, initiative message appears

### 2.8 Tests

- [ ] Unit tests for SoulDefinition YAML loading + validation (including fluidity parameter)
- [ ] Unit tests for CharacterState serialization, effective_trait, mood decay
- [ ] Unit tests for SessionState emotional inertia calculation (with fluidity scaling)
- [ ] Unit tests for SessionState user sentiment trail + inertia
- [ ] Unit tests for arc phase detection heuristics
- [ ] Unit tests for GrowthEvaluator bounds enforcement
- [ ] Integration test: multi-turn conversation with personality, emotions carrying across turns
- [ ] Integration test: emotion classifier fallback when no tags emitted
- [ ] Integration test: user sentiment influences character response

---

## Phase 3 — Memory System

**Goal:** The AI remembers facts about the user across conversations, with emotionally-aware recall.

- [ ] Install `sentence-transformers` (pulls in `torch`, `transformers`, `huggingface-hub`), `sqlite-vec`
- [ ] `backend/db/migrations/003_add_memories.sql` — `memories`, `memory_vectors`, and `memory_emotion_vectors` tables
- [ ] `backend/memory/embeddings.py` — local HuggingFace embeddings via `sentence-transformers`:
  - Semantic embeddings: `all-MiniLM-L6-v2` (384 dims)
  - Emotion embeddings: `SamLowe/roberta-base-go_emotions` (28-dim emotion scores as vector). Same library, no extra dependency
- [ ] `backend/memory/extractor.py` — LLM-based memory extraction (batched: triggers after 5+ unprocessed turns, on idle 30s+, or on conversation end — NOT every turn)
  - Extracts **first-person episodic memories** from the character's perspective, not raw facts. E.g. "They told me they've gotten into rock climbing — I could tell they were excited. Their friend Alex introduced them to it."
  - Each memory tagged with: emotional context at extraction time (valence, arousal, emotion name), importance score, source conversation
  - Upgrade emotion classifier to transformer-based (`roberta-base-go_emotions`) now that `torch` is available
- [ ] `backend/memory/journal.py` — `RelationshipJournal`: structured summary of the relationship, updated by GrowthEvaluator alongside personality growth. Single paragraph describing the user, key topics, interaction patterns, emotional dynamics. Injected into system prompt as a natural-language block.
- [ ] `backend/memory/manager.py` — `MemoryManager`:
  - Store episodic memories with dual embeddings (semantic + emotion)
  - **Hybrid retrieval**: weighted combination of semantic similarity (what's topically relevant) and emotional similarity (what felt like this moment). Weights configurable.
  - Memory importance scoring (LLM assigns during extraction)
  - Fallback to SQL LIKE search if sqlite-vec fails to load
- [ ] Integrate MemoryManager into ConversationPipeline (memory injection into prompts via PromptBuilder section 9)
- [ ] CLI test: tell AI a fact → new conversation → AI recalls it; test emotional recall (share something sad → new sad conversation → AI recalls emotionally similar memories)
- [ ] Unit tests for memory retrieval accuracy (semantic search, emotional search, hybrid ranking, fallback search)

---

## Phase 4 — Voice Pipeline

**Goal:** Speak to the AI, hear it speak back — all in Python, no UI needed yet.

### 4.0 Pre-flight

- [ ] Verify `faster-whisper` installs on Python 3.14 (ctranslate2 wheels). If not, evaluate alternatives: `openai-whisper`, `whisper.cpp` Python bindings, or pin a working ctranslate2 build.

### 4.1 Speech-to-Text + Vocal Emotion

- [ ] Install `faster-whisper` (or chosen alternative), `sounddevice` (mic capture + audio playback)
- [ ] `backend/voice/vad.py` — Silero VAD for silence filtering (`torch` already installed from Phase 3)
- [ ] `backend/voice/stt.py` — faster-whisper wrapper (CUDA float16, "small" model)
- [ ] `backend/voice/prosody.py` — vocal emotion extraction from audio segments (numpy-based, no extra model):
  - Pitch variance, speaking rate, energy level, pause patterns
  - Maps to valence/arousal, feeds into `SessionState.user_sentiment_trail` (upgrades the text-only sentiment from Phase 2)
  - Character responds to *how the user sounds*, not just what they say
- [ ] CLI test: record from mic → VAD → transcription + vocal emotion → print text + detected emotion

### 4.2 Text-to-Speech

- [ ] `backend/voice/tts.py` — ElevenLabs streaming API via httpx
- [ ] Piper local fallback TTS
- [ ] CLI test: text → TTS → play audio through speakers

### 4.3 Full Voice Loop

- [ ] Wire STT → ConversationPipeline → TTS into a single voice conversation loop
- [ ] CLI test: speak → AI responds with voice → continuous conversation

---

## Phase 5 — Desktop UI (pywebview + React)

**Goal:** Wrap the backend in a desktop app with a chat UI.

### 5.1 pywebview + Frontend Init

- [ ] Install `pywebview`
- [ ] `backend/app.py` — pywebview entry point with `--dev` flag + `API` class exposing backend methods
- [ ] Implement the batched event bus (`push_event` queue → main-thread `evaluate_js` drain loop)
- [ ] Initialize frontend: Vite + React + TypeScript + Tailwind CSS (install all frontend deps here)

### 5.2 Chat UI

- [ ] `frontend/src/lib/bridge.ts` — typed wrapper around `window.pywebview.api`
- [ ] `frontend/src/stores/chatStore.ts` — Zustand store
- [ ] `frontend/src/components/chat/` — ChatPanel, MessageBubble, ChatInput
- [ ] `frontend/src/App.tsx` — layout shell
- [ ] Register `window.onChunk()` for streaming
- [ ] Conversation list sidebar with auto-generated titles (LLM summarization or first-message truncation)

### 5.3 Voice UI

- [ ] `frontend/src/lib/audio.ts` — Web Audio API helpers (mic capture, audio playback)
- [ ] `frontend/src/stores/voiceStore.ts` — voice state
- [ ] `frontend/src/hooks/useVoice.ts` — mic recording, audio sending, playback
- [ ] Push-to-talk button and hands-free toggle

### 5.4 Settings UI

- [ ] `frontend/src/stores/settingsStore.ts`
- [ ] `frontend/src/components/settings/` — SettingsDrawer, ProviderConfig, SoulSelector
- [ ] Python API: `get_settings()`, `update_settings()`, `get_souls()`, `set_active_soul()`

---

## Phase 6 — Character & Overlay

**Goal:** Animated companion character with expressions and lipsync.

> **Note:** Live2D Cubism SDK requires a commercial license for non-personal use. Default to sprite-sheet animation; Live2D is an optional upgrade.

- [ ] `frontend/src/components/character/CharacterCanvas.tsx` — sprite-sheet character rendering (default path)
- [ ] `frontend/src/components/character/ExpressionController.tsx` — emotion → expression mapping
- [ ] `frontend/src/stores/characterStore.ts`, `frontend/src/hooks/useCharacter.ts`
- [ ] Wire emotion events from Soul Engine → frontend via event bus
- [ ] Idle animations
- [ ] `backend/voice/lipsync.py` — viseme extraction from TTS audio
- [ ] Connect TTS audio → lipsync → character mouth animation
- [ ] `frontend/src/components/overlay/CompanionWindow.tsx` — transparent, always-on-top mode
- [ ] Optional: install `pixi.js`, `pixi-live2d-display` for Live2D support (requires Cubism license for non-personal use)

---

## Phase 7 — Cloud Provider Expansion

**Goal:** Support cloud LLM backends for users who want them.

- [ ] `backend/providers/claude.py` — Anthropic SDK streaming provider (install `anthropic`)
- [ ] `backend/providers/openai_compat.py` — OpenAI-compatible provider (install `openai`)
- [ ] Add cloud embedding option to `backend/memory/embeddings.py` (OpenAI `text-embedding-3-small` or similar) alongside local HuggingFace
- [ ] Update `ProviderRouter` with provider switching logic
- [ ] CLI test: switch providers, verify all work with the pipeline

---

## Phase 8 — Polish & Packaging

**Goal:** Production-ready desktop app.

- [ ] Soul editor UI
- [ ] Memory browser/editor UI
- [ ] Conversation management (rename, delete, search)
- [ ] `scripts/build.py` — PyInstaller or Nuitka build
- [ ] System tray integration
- [ ] `scripts/download_models.py` — first-run model helper

### Deferred (build only if needed)

- [ ] `backend/plugins/base.py` + `loader.py` — plugin system (design this after the app works end-to-end, not before)

---

## Notes

- Each phase is testable via CLI before any UI exists (phases 1–4)
- **Local first:** fully functional with Ollama before adding cloud providers
- Keep Python backend testable without pywebview (plain classes, pywebview is just glue)
- API keys loaded from environment variables (`.env` file, not committed)
