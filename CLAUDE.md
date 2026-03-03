# CLAUDE.md — Soul Companion

## What This Is

A Python desktop AI companion app inspired by [moeru-ai/airi](https://github.com/moeru-ai/airi). The user has a persistent, expressive AI character on their desktop that they can talk to via text and voice. It remembers past conversations, has a configurable personality ("soul"), and displays an animated character.

## Architecture

**This is a desktop app, NOT a web app. There is no HTTP server.**

```
pywebview (native desktop window)
│
│  window.pywebview.api.method()   ← direct Python↔JS bridge
│  window.evaluate_js()            ← Python pushes to JS (streaming)
│
├── React frontend (Vite build) — thin rendering layer
│   ├── Chat UI (text input + streaming messages)
│   ├── Character canvas (Live2D or sprite via pixi.js)
│   ├── Settings panel
│   └── Zustand stores (chatStore, characterStore, settingsStore, voiceStore)
│
└── Python backend (runs in the pywebview process, no server)
    ├── SoulEngine — personality middleware (pre/post processes LLM calls)
    ├── ProviderRouter — abstracts Ollama / Claude / OpenAI
    ├── MemoryManager — SQLite + sqlite-vec for persistent memory + vector search
    ├── VoicePipeline — faster-whisper (STT), Silero VAD, ElevenLabs/Piper (TTS)
    └── ConversationPipeline — ties it all together
```

### Communication Pattern

The frontend calls Python directly via `window.pywebview.api`:

```javascript
// JS → Python (direct call)
const result = await window.pywebview.api.get_conversations();

// For streaming (LLM responses), Python pushes to JS:
window.pywebview.api.send_message(text);
// Python side calls: self.window.evaluate_js(f"window.onChunk({json.dumps(chunk)})")
```

There is NO FastAPI, NO Flask, NO HTTP server, NO WebSocket server. pywebview's JS bridge is the only communication layer.

## Tech Stack

| Layer | Tech |
|---|---|
| Desktop shell | pywebview |
| Frontend | React + TypeScript + Zustand + Vite |
| Character rendering | pixi.js + pixi-live2d-display |
| Styling | Tailwind CSS |
| Python backend | Pure Python classes, no framework |
| LLM (local) | Ollama (REST calls via httpx) |
| LLM (cloud) | anthropic SDK, openai SDK |
| STT | faster-whisper (CTranslate2, CUDA) |
| VAD | Silero VAD via torch |
| TTS | ElevenLabs API (v1), Piper (local fallback) |
| Database | SQLite via better-sqlite3 bindings (or stdlib sqlite3) + sqlite-vec |
| Embeddings | Ollama nomic-embed-text |
| Package manager | uv |

## Project Structure

```
soul-companion/
├── backend/
│   ├── __init__.py
│   ├── app.py                   # pywebview entry point + API class
│   ├── config.py                # Settings, paths, env
│   ├── soul/
│   │   ├── engine.py            # SoulEngine (pre/post processing)
│   │   ├── definition.py        # SoulDefinition dataclass + YAML loader
│   │   └── pipeline.py          # ConversationPipeline (the main orchestrator)
│   ├── providers/
│   │   ├── base.py              # LLMProvider ABC
│   │   ├── ollama.py            # Ollama via httpx
│   │   ├── claude.py            # Anthropic SDK
│   │   ├── openai_compat.py     # OpenAI SDK (also works with vLLM, LM Studio)
│   │   └── router.py            # ProviderRouter
│   ├── memory/
│   │   ├── manager.py           # MemoryManager (search, store, summarize)
│   │   ├── extractor.py         # LLM-based fact extraction
│   │   └── embeddings.py        # Ollama embedding calls
│   ├── voice/
│   │   ├── stt.py               # faster-whisper wrapper
│   │   ├── tts.py               # ElevenLabs / Piper
│   │   ├── vad.py               # Silero VAD
│   │   └── lipsync.py           # Viseme extraction for character mouth
│   ├── db/
│   │   ├── database.py          # SQLite connection, migrations, helpers
│   │   └── schema.sql           # Table definitions
│   └── plugins/
│       ├── base.py              # Plugin interface (v2)
│       └── loader.py            # Plugin discovery
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── components/
│   │   │   ├── chat/
│   │   │   │   ├── ChatPanel.tsx
│   │   │   │   ├── MessageBubble.tsx
│   │   │   │   └── ChatInput.tsx
│   │   │   ├── character/
│   │   │   │   ├── CharacterCanvas.tsx
│   │   │   │   └── ExpressionController.tsx
│   │   │   ├── overlay/
│   │   │   │   └── CompanionWindow.tsx
│   │   │   └── settings/
│   │   │       ├── SettingsDrawer.tsx
│   │   │       ├── ProviderConfig.tsx
│   │   │       ├── SoulSelector.tsx
│   │   │       └── MemoryBrowser.tsx
│   │   ├── stores/
│   │   │   ├── chatStore.ts
│   │   │   ├── characterStore.ts
│   │   │   ├── settingsStore.ts
│   │   │   └── voiceStore.ts
│   │   ├── hooks/
│   │   │   ├── useChat.ts
│   │   │   ├── useVoice.ts
│   │   │   └── useCharacter.ts
│   │   └── lib/
│   │       ├── bridge.ts        # Typed wrapper around window.pywebview.api
│   │       └── audio.ts         # Web Audio API helpers for mic + playback
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── tailwind.config.js
├── souls/
│   ├── default.yaml             # Default companion personality
│   └── examples/
├── data/                        # SQLite DB + cached models (gitignored)
├── assets/                      # Live2D models, sprites, sounds
├── scripts/
│   ├── dev.py                   # Dev mode: starts Vite + pywebview with hot reload
│   ├── build.py                 # PyInstaller / Nuitka build
│   └── download_models.py       # Pull Ollama models
├── pyproject.toml
├── CLAUDE.md
└── README.md
```

## Core Concepts

### Soul Engine

A "soul" is NOT just a system prompt. It's a middleware pipeline that transforms both inputs and outputs to maintain consistent personality. Soul definitions are YAML files in `souls/`.

**Pre-processing:** Takes user input → retrieves relevant memories via vector search → builds full prompt with system prompt + memories + conversation history + user message.

**Post-processing:** Takes raw LLM stream → extracts `[emotion:happy]` tags → enforces response constraints → yields clean text + emotion events separately.

```python
# Soul definition loaded from YAML
@dataclass
class SoulDefinition:
    name: str
    personality: str              # Character description
    system_prompt: str            # Base system prompt
    response_constraints: list[str]
    speaking_style: dict          # formality, verbosity, emotion_range
    memory_instructions: str
    voice_config: dict            # TTS provider, voice_id, speed
```

The LLM is prompted to emit `[emotion:NAME]` tags in responses. The post-processor strips them before display and routes emotion events to the character animation system.

### Memory System

SQLite + sqlite-vec. Two storage tiers:

- **Short-term:** Recent messages in the `messages` table, used for conversation history context window.
- **Long-term:** Extracted facts/preferences/events in the `memories` table with vector embeddings for semantic search.

After each conversation turn, a background task uses the LLM to extract key facts ("user works with AWS CDK", "user prefers concise answers") and stores them with embeddings from Ollama's nomic-embed-text.

Before each LLM call, the MemoryManager does a vector similarity search to find relevant memories and injects them into the prompt.

### Provider Router

Abstracts LLM providers behind a common interface. All providers implement `stream_chat(messages) -> AsyncIterator[str]`.

Providers: OllamaProvider, ClaudeProvider, OpenAICompatProvider.

Default strategy: Ollama for fast local responses, Claude API for complex reasoning. User can switch in settings.

### Voice Pipeline

All runs in-process in Python:

1. Frontend captures mic via MediaRecorder, sends audio bytes via pywebview bridge
2. Silero VAD filters silence
3. faster-whisper transcribes on GPU (CUDA float16, ~1GB VRAM for "small" model)
4. Transcript enters the conversation pipeline
5. LLM response → TTS (ElevenLabs streaming or local Piper)
6. Audio bytes pushed back to frontend for playback
7. Frontend analyzes audio via Web Audio API for lipsync

### Character Display

Runs in the React frontend using pixi-live2d-display (same library AIRI uses). The Python backend sends emotion events, the frontend maps them to Live2D expressions/motions.

Simpler alternative for v1: sprite sheet with pre-drawn expressions that swap on emotion events. The emotion event interface stays the same either way.

## Database Schema

```sql
CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    soul_id     TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role            TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    emotion         TEXT,
    token_count     INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE memories (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL CHECK(type IN ('fact', 'summary', 'preference', 'event')),
    content         TEXT NOT NULL,
    source_msg_id   TEXT REFERENCES messages(id),
    importance      REAL DEFAULT 0.5,
    last_accessed   TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE memory_vectors USING vec0(
    id TEXT PRIMARY KEY,
    embedding float[768]
);

CREATE TABLE souls (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    definition  TEXT NOT NULL,
    is_active   BOOLEAN DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

## Implementation Phases

Backend-first approach — all core features are built and testable via CLI before any UI work. See `plan.md` for detailed task breakdowns.

### Phase 1 — LLM + Persistence
- `LLMProvider` ABC + Ollama streaming provider + `ProviderRouter`
- SQLite schema (`conversations`, `messages`, `settings`) + query helpers
- CLI smoke test: multi-turn conversation, persisted and reloadable

### Phase 2 — Soul Engine
- `SoulDefinition` YAML loader + `SoulEngine` pre/post processing
- `ConversationPipeline` orchestrator
- Emotion tag extraction

### Phase 3 — Memory System
- sqlite-vec vector search + Ollama embeddings
- LLM-based fact extraction + memory injection into prompts

### Phase 4 — Voice Pipeline
- STT: faster-whisper + Silero VAD (CUDA)
- TTS: ElevenLabs streaming + Piper local fallback
- Full voice loop: speak → AI responds with voice

### Phase 5 — Desktop UI (pywebview + React)
- pywebview shell + React chat UI + voice UI + settings UI

### Phase 6 — Character & Overlay
- Live2D rendering, emotion → expression mapping, lipsync, overlay mode

### Phase 7 — Provider Expansion (on-demand)
- Claude (Anthropic) + OpenAI-compatible providers when actually needed

### Phase 8 — Polish & Packaging
- Plugin system, soul editor, memory browser, PyInstaller build, system tray

## Code Style

- Use Ruff as the linter and formatter for all Python code
- Run `ruff check .` for linting and `ruff format .` for formatting
- Run `ruff check --fix .` to auto-fix linting issues

## Coding Conventions

- Python: 3.11+, type hints everywhere, dataclasses over dicts, async where I/O bound
- Use `uv` for Python dependency management
- Frontend: React 19, TypeScript strict, Zustand for state, Tailwind for styling
- All Python↔JS communication goes through `window.pywebview.api` (typed in `frontend/src/lib/bridge.ts`)
- No HTTP servers, no WebSocket servers, no Flask, no FastAPI
- SQLite is the only persistence layer — no external databases
- Soul definitions are YAML files in `souls/`, loaded at runtime
- Streaming LLM responses: Python calls `self.window.evaluate_js()` per chunk, frontend has a global `window.onChunk()` callback registered by the React app
- Keep Python backend fully testable without pywebview (all logic in plain classes, pywebview is just glue)

## Key Dependencies

### Python (pyproject.toml)
```
pywebview
anthropic
openai
httpx
faster-whisper
torch
sqlite-vec
pyyaml
pydantic
```

### Frontend (package.json)
```
react, react-dom
zustand
pixi.js, pixi-live2d-display
tailwindcss
vite
typescript
```

## Dev Workflow

```bash
# Terminal 1: Frontend dev server with hot reload
cd frontend && npm run dev

# Terminal 2: Python app pointing at Vite dev server
python -m backend.app --dev  # loads http://localhost:5173 instead of built files

# Production: build frontend, then run
cd frontend && npm run build
python -m backend.app  # loads frontend/dist/index.html
```

## Important Notes

- The RTX 4070 laptop GPU (8GB VRAM) can run faster-whisper small (~1GB) + Ollama with a Q4 7-8B model (~4-5GB) concurrently. Don't load larger models without checking VRAM budget.
- pywebview's `evaluate_js()` is the streaming mechanism. It runs JS in the webview from Python. This is how LLM chunks, audio data, and emotion events get pushed to the frontend.
- pywebview's `window.pywebview.api` methods run on a background thread by default. Use threading locks or asyncio where needed for shared state.
- The frontend should never call external APIs directly. Everything routes through the Python backend via the bridge.
- sqlite-vec requires loading as an extension: `db.enable_load_extension(True)` then `sqlite_vec.load(db)`.
