# CLAUDE.md — Dora AI

## What This Is

A Python desktop AI companion app (inspired by [moeru-ai/airi](https://github.com/moeru-ai/airi)). Persistent, expressive AI character on the desktop with text/voice chat, memory, and configurable personality ("soul"). See `plan.md` for implementation phases.

## Architecture (critical constraints)

**This is a desktop app, NOT a web app. There is NO HTTP server.**

```
pywebview (native desktop window)
│
│  window.pywebview.api.method()   ← JS calls Python directly
│  evaluate_js()                   ← Python pushes to JS (batched event bus)
│
├── React frontend — thin rendering layer
│   ├── Chat UI (text input + streaming messages)
│   ├── Character canvas (Live2D or sprite via pixi.js)
│   ├── Settings panel
│   └── Zustand stores (chatStore, characterStore, settingsStore, voiceStore)
│
└── Python backend (runs in pywebview process, no server)
    ├── SoulEngine — personality middleware (3 state layers, pre/post processes LLM calls)
    │   ├── SoulDefinition (YAML) + CharacterState (SQLite) + SessionState (volatile)
    │   ├── PromptBuilder — compresses all layers into system prompt
    │   ├── TagParser — streaming emotion/action/mood/thought tag extraction
    │   ├── GrowthEvaluator — async batched personality evolution
    │   └── InitiativeScheduler — timer-driven proactive messages
    ├── ProviderRouter — abstracts Ollama / Claude / OpenAI
    ├── MemoryManager — SQLite + sqlite-vec for persistent memory + vector search
    ├── VoicePipeline — faster-whisper (STT), Silero VAD, ElevenLabs/Piper (TTS)
    └── ConversationPipeline — orchestrator tying it all together
```

There is NO FastAPI, NO Flask, NO WebSocket server. pywebview's JS bridge is the only communication layer.

### Core Concepts

- **Soul Engine:** NOT just a system prompt — a multi-layered personality system with three temporal scales. **Permanent** (SoulDefinition from YAML — identity, traits, style, emotions, voice, relationship stages, spontaneity, initiative rules, growth bounds). **Persistent** (CharacterState in SQLite — trait drift values, relationship stage, formed opinions, mood with time-decay, milestones). **Session** (SessionState in-memory — emotion trail with inertia, conversation arc tracking, topic/callback tracking, spontaneity cooldowns). Pre-processing compresses all three layers into a system prompt via PromptBuilder. Post-processing extracts `[emotion:NAME intensity:FLOAT]`, `[mood:NAME]`, `[action:*desc*]`, `[thought:text]` tags (tier-adapted for model capability) and feeds emotions back into SessionState for cross-turn continuity. Includes GrowthEvaluator (async batched personality evolution), InitiativeScheduler (proactive AI-initiated messages), and spontaneity system (controlled wildcard injections). See `docs/soul-engine.md` for full design. Soul definitions are YAML files in `souls/`.
- **Provider Router:** All providers implement `stream_chat(messages) -> AsyncIterator[str]`. User picks provider in settings (Ollama, Claude, OpenAI-compatible).
- **Memory System:** Two tiers — short-term (recent messages) and long-term (extracted facts with vector embeddings for semantic search). Extraction is batched, not per-turn.
- **Voice Pipeline:** Mic → Silero VAD → faster-whisper STT → ConversationPipeline → TTS (ElevenLabs / Piper) → audio playback + lipsync.
- **Character Display:** pixi-live2d-display in React. Python sends emotion events, frontend maps to Live2D expressions. Simpler v1: sprite sheet swapping on emotion events.

See `docs/architecture.md` for threading, streaming, and error handling. See `docs/soul-engine.md` for the full soul engine design.

## Hard Rules

- **No HTTP servers.** All communication goes through `window.pywebview.api`.
- **No dataclasses.** Use Pydantic `BaseModel` everywhere (validation + serialization for free).
- **No LangChain.** Custom provider layer is simpler.
- **Frontend never calls external APIs.** Everything routes through Python backend.
- **SQLite is the only persistence layer.** No external databases.
- **Never create empty folders.** Only create directories when adding files.
- **Never install dependencies early.** Add each dependency in the task that first uses it.
- **Backend first.** Build all core backend functionality before touching frontend/UI.
- **Update `plan.md` on task completion.** `plan.md` tracks progress — whenever a task or sub-task is finished, check the corresponding checkbox and update the "Current State" summary at the top.

## Coding Conventions

- Python 3.14+, type hints everywhere, async where I/O bound
- `uv` for Python dependency management
- Frontend: React 19, TypeScript strict, Zustand for state, Tailwind for styling
- All Python-JS communication typed in `frontend/src/lib/bridge.ts`
- Soul definitions: YAML files in `souls/` are source of truth; `souls` DB table caches them. Re-scan on startup.
- Streaming: all Python→JS push events go through the batched event bus, never raw `evaluate_js` with string interpolation.
- Keep Python backend fully testable without pywebview (all logic in plain classes, pywebview is just glue)
- Env vars (API keys) loaded via `python-dotenv` from `.env`. Never commit `.env`.

## Code Style

- Ruff for linting and formatting
- `ruff check .` / `ruff format .` / `ruff check --fix .`

## Dev Workflow

```bash
# Frontend dev server with hot reload
cd frontend && npm run dev

# Python app pointing at Vite dev server
python -m backend.app --dev  # loads http://localhost:5173

# Production
cd frontend && npm run build
python -m backend.app        # loads frontend/dist/index.html
```

## Key Constraints

- **faster-whisper:** Has known Python 3.14 issues (ctranslate2 wheels). Check before Phase 4. Fallback: `openai-whisper` or `whisper.cpp` bindings.
- **Threading:** pywebview API methods run on background threads. Async providers bridge via dedicated asyncio thread. Details in `docs/architecture.md`.
- **sqlite-vec:** Requires `db.enable_load_extension(True)` then `sqlite_vec.load(db)`. Falls back to LIKE queries if unavailable.
