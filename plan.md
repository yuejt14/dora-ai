# Dora AI — Implementation Plan

## Current State

- Bare project scaffold: `main.py` (hello world), `pyproject.toml` with Python 3.14+, ruff
- No backend, no frontend, no database, no UI

## Rules

- **Never create empty folders** — only create directories when adding files that belong there
- **Never install dependencies early** — add each dependency in the task that first uses it
- **Backend first** — build all core backend functionality before touching frontend/UI
- **Drop LangChain** — the custom provider layer is simpler and cleaner; remove from `pyproject.toml`

---

## Phase 1 — LLM + Persistence

**Goal:** Talk to an LLM and persist conversations in SQLite.

### 1.1 Config & Provider

- [ ] `backend/config.py` — settings, paths, env var loading (install `python-dotenv`, load from `.env`)
- [ ] `backend/providers/base.py` — `LLMProvider` ABC with `stream_chat(messages) -> AsyncIterator[str]`
- [ ] `backend/providers/ollama.py` — Ollama provider via httpx (install `httpx`)
- [ ] `backend/providers/router.py` — `ProviderRouter` (Ollama only for now)

### 1.2 Database

- [ ] `backend/db/migrations/001_initial.sql` — `conversations`, `messages`, `settings`, `_migrations` tables
- [ ] `backend/db/database.py` — SQLite connection (WAL mode), migration runner, query helpers

### 1.3 Integration

- [ ] Wire provider + DB together: send message → stream response → persist both
- [ ] Set up the asyncio bridge (dedicated event loop thread for async providers, callable from sync code)
- [ ] CLI smoke test: multi-turn conversation, persisted and reloadable across restarts

### 1.4 Tests

- [ ] Install `pytest` as dev dependency
- [ ] Unit tests for Ollama provider (mock httpx, verify streaming contract and error handling)
- [ ] Unit tests for database (migrations apply cleanly, CRUD operations, WAL mode)

---

## Phase 2 — Soul Engine

**Goal:** Personality-driven responses via a middleware pipeline.

- [ ] `backend/soul/definition.py` — `SoulDefinition` Pydantic model + YAML loader (install `pyyaml`, `pydantic`)
- [ ] `souls/default.yaml` — default companion personality
- [ ] `backend/soul/engine.py` — `SoulEngine` pre/post processing:
  - Pre: inject system prompt + conversation history
  - Post: streaming emotion tag parser (handles split tags across chunks, defaults to `neutral`), enforce response constraints
- [ ] `backend/soul/pipeline.py` — `ConversationPipeline` orchestrator tying providers + DB + soul together
- [ ] Auto-generate conversation titles from first exchange (LLM summarization or first-message truncation)
- [ ] CLI test: personality-flavored streamed responses with emotion tags parsed out
- [ ] Unit tests for emotion tag parser (split tags, missing tags, malformed tags, multiple tags per chunk)

---

## Phase 3 — Memory System

**Goal:** The AI remembers facts about the user across conversations.

- [ ] Install `sqlite-vec`
- [ ] `backend/db/migrations/002_add_memories.sql` — `memories` and `memory_vectors` tables
- [ ] `backend/memory/embeddings.py` — Ollama `nomic-embed-text` embedding calls
- [ ] `backend/memory/extractor.py` — LLM-based fact extraction (batched: triggers after 5+ unprocessed turns, on idle 30s+, or on conversation end — NOT every turn)
- [ ] `backend/memory/manager.py` — `MemoryManager`:
  - Store facts with vector embeddings
  - Semantic search for relevant memories before each LLM call
  - Memory importance scoring
  - Fallback to SQL LIKE search if sqlite-vec fails to load
- [ ] Integrate MemoryManager into ConversationPipeline (memory injection into prompts)
- [ ] CLI test: tell AI a fact → new conversation → AI recalls it
- [ ] Unit tests for memory retrieval accuracy (store facts, verify semantic search recalls them, test fallback search)

---

## Phase 4 — Voice Pipeline

**Goal:** Speak to the AI, hear it speak back — all in Python, no UI needed yet.

### 4.0 Pre-flight

- [ ] Verify `faster-whisper` installs on Python 3.14 (ctranslate2 wheels). If not, evaluate alternatives: `openai-whisper`, `whisper.cpp` Python bindings, or pin a working ctranslate2 build.

### 4.1 Speech-to-Text

- [ ] Install `faster-whisper` (or chosen alternative), `torch`
- [ ] `backend/voice/vad.py` — Silero VAD for silence filtering
- [ ] `backend/voice/stt.py` — faster-whisper wrapper (CUDA float16, "small" model)
- [ ] CLI test: record from mic → VAD → transcription → print text

### 4.2 Text-to-Speech

- [ ] `backend/voice/tts.py` — ElevenLabs streaming API (install `httpx` if not yet added)
- [ ] Piper local fallback TTS
- [ ] CLI test: text → TTS → play audio through speakers

### 4.3 Full Voice Loop

- [ ] Wire STT → ConversationPipeline → TTS into a single voice conversation loop
- [ ] CLI test: speak → AI responds with voice → continuous conversation
- [ ] `backend/voice/lipsync.py` — viseme extraction (for future character sync)

---

## Phase 5 — Desktop UI (pywebview + React)

**Goal:** Wrap the backend in a desktop app with a chat UI.

### 5.1 pywebview Shell

- [ ] Install `pywebview`
- [ ] `backend/app.py` — pywebview entry point + `API` class exposing backend methods
- [ ] Implement the batched event bus (`push_event` queue → main-thread `evaluate_js` drain loop)
- [ ] Initialize frontend: Vite + React + TypeScript (install frontend deps here)
- [ ] `scripts/dev.py` — dev mode runner (Vite + pywebview together)

### 5.2 Chat UI

- [ ] `frontend/src/lib/bridge.ts` — typed wrapper around `window.pywebview.api`
- [ ] `frontend/src/stores/chatStore.ts` — Zustand store
- [ ] `frontend/src/components/chat/` — ChatPanel, MessageBubble, ChatInput
- [ ] `frontend/src/App.tsx` — layout shell
- [ ] Register `window.onChunk()` for streaming
- [ ] Conversation list sidebar

### 5.3 Voice UI

- [ ] `frontend/src/lib/audio.ts` — Web Audio API helpers (mic capture, audio playback)
- [ ] `frontend/src/stores/voiceStore.ts` — voice state
- [ ] `frontend/src/hooks/useVoice.ts` — mic recording, audio sending, playback
- [ ] Push-to-talk button and hands-free toggle

### 5.4 Settings UI

- [ ] `frontend/src/stores/settingsStore.ts`
- [ ] `frontend/src/components/settings/` — SettingsDrawer, ProviderConfig, SoulSelector
- [ ] Python API: `get_settings()`, `update_settings()`, `get_souls()`, `set_active_soul()`
- [ ] Configure Tailwind CSS

---

## Phase 6 — Character & Overlay

**Goal:** Animated companion character with expressions and lipsync.

- [ ] Install `pixi.js`, `pixi-live2d-display` (frontend)
- [ ] `frontend/src/components/character/CharacterCanvas.tsx` — Live2D rendering
- [ ] `frontend/src/components/character/ExpressionController.tsx` — emotion → expression mapping
- [ ] `frontend/src/stores/characterStore.ts`, `frontend/src/hooks/useCharacter.ts`
- [ ] Wire emotion events from Soul Engine → frontend via `evaluate_js()`
- [ ] Idle animations
- [ ] `frontend/src/components/overlay/CompanionWindow.tsx` — transparent, always-on-top mode
- [ ] Connect TTS audio → lipsync → Live2D mouth

---

## Phase 7 — Provider Expansion (on-demand)

**Goal:** Support cloud LLM backends when actually needed.

- [ ] `backend/providers/claude.py` — Anthropic SDK streaming provider (install `anthropic`)
- [ ] `backend/providers/openai_compat.py` — OpenAI-compatible provider (install `openai`)
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

## Testing Strategy

Tests are in-phase tasks (see each phase above), not a separate effort. Run with `pytest`.

- **Phase 1:** Provider streaming contract (mock httpx), DB migrations + CRUD
- **Phase 2:** Emotion tag parser (split chunks, missing tags, malformed), conversation pipeline integration
- **Phase 3:** Memory retrieval accuracy (store facts, verify semantic search recalls them, test LIKE fallback)
- **Phase 4:** VAD filtering, STT output format
- **Phase 5+:** Manual testing via the UI; consider Playwright for pywebview if automated UI tests become necessary

---

## Notes

- Each phase is testable via CLI before any UI exists (phases 1–4)
- Primary target is API models; local Ollama for dev/testing only
- Keep Python backend testable without pywebview (plain classes, pywebview is just glue)
- API keys loaded from environment variables (`.env` file, not committed)
