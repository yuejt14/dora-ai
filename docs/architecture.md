# Architecture

## Overview

```
┌──────────────────────────────────────────────────────────────┐
│                  Desktop Shell (pywebview)                    │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              Web UI (React + Zustand)                   │  │
│  │  ┌─────────┐  ┌──────────┐  ┌───────────────────────┐ │  │
│  │  │ Chat UI │  │Character │  │   Settings Panel      │ │  │
│  │  │         │  │ Canvas   │  │                       │ │  │
│  │  └────┬────┘  └────┬─────┘  └───────────┬───────────┘ │  │
│  │       │            │                     │             │  │
│  │  ┌────┴────────────┴─────────────────────┴──────────┐  │  │
│  │  │           Zustand Stores                          │  │  │
│  │  │  chatStore · characterStore · settingsStore       │  │  │
│  │  └──────────────────┬───────────────────────────────┘  │  │
│  └─────────────────────┼──────────────────────────────────┘  │
│                        │                                     │
│          window.pywebview.api (JS→Python)                    │
│          evaluate_js batched event bus (Python→JS)           │
│                        │                                     │
│  ┌─────────────────────┼──────────────────────────────────┐  │
│  │              Python Backend (no server)                  │  │
│  │                                                         │  │
│  │  ┌──────────┐ ┌──────────────┐ ┌─────────────────────┐ │  │
│  │  │  Soul    │ │   Memory     │ │  Provider Router    │ │  │
│  │  │  Engine  │ │   Manager    │ │  (LLM Abstraction)  │ │  │
│  │  └────┬─────┘ └──────┬───────┘ └──────────┬──────────┘ │  │
│  │       │              │                     │            │  │
│  │  ┌────┴──────────────┴─────────────────────┴─────────┐  │  │
│  │  │              Conversation Pipeline                  │  │  │
│  │  │  (Soul Transform → LLM → Memory → TTS → Lipsync)  │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  │                                                         │  │
│  │  ┌──────────────────────────────────────────────────┐   │  │
│  │  │            Voice Layer                            │   │  │
│  │  │  Silero VAD · faster-whisper STT · TTS            │   │  │
│  │  └──────────────────────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
         │                    │                    │
    ┌────┴────┐         ┌────┴────┐          ┌────┴────┐
    │ Ollama  │         │ Claude  │          │ OpenAI  │
    │ (local) │         │  API    │          │ / etc   │
    └─────────┘         └─────────┘          └─────────┘
```

## Communication

No HTTP server, no WebSocket. Two mechanisms only:

```
JS → Python:  window.pywebview.api.method()       (direct call, returns Promise)
Python → JS:  batched event bus via evaluate_js()  (buffered ~50ms, thread-safe queue)
```

**Event types pushed from Python:**

| Event | Payload | When |
|---|---|---|
| `chunk` | `{text: "..."}` | Each LLM response fragment |
| `emotion` | `{name: "happy"}` | Emotion tag extracted from stream |
| `audio` | `{data: "base64..."}` | TTS audio chunk |
| `status` | `{voice: "listening"}` | Pipeline state changes |

## Data Flow

```
User input (text or voice)
    │
    ├─ [voice path] Frontend mic → pywebview bridge → VAD → STT → text
    │
    ▼
SoulEngine.pre_process()
    ├── Retrieve relevant memories (vector search)
    ├── Build system prompt (personality + memories + constraints)
    └── Assemble messages (system + history + user input)
    │
    ▼
ProviderRouter.get().stream_chat(messages)
    │  (Ollama / Claude / OpenAI — user's choice)
    │
    ▼
SoulEngine.post_process()
    ├── Buffer & extract [emotion:NAME] tags (handles chunk splits)
    ├── Yield clean text → event bus → frontend
    └── Yield emotion events → event bus → character expressions
    │
    ▼
Persist to SQLite (messages table)
    │
    ├─ [voice path] TTS → audio chunks → event bus → frontend playback + lipsync
    │
    └─ [batched] Memory extraction (after 5+ turns / 30s idle / conversation end)
         └── LLM extracts facts → embed → store in memories + memory_vectors
```

---

## Threading & Async Strategy

pywebview runs API methods on a background thread. The backend uses async providers (`AsyncIterator[str]`).

- **Dedicated asyncio thread:** On startup, spin up a single thread with a persistent event loop. pywebview API methods dispatch async work via `asyncio.run_coroutine_threadsafe()` and await results via `concurrent.futures`.
- **SQLite:** One connection per thread, WAL mode for concurrent reads. The asyncio thread owns the primary connection.
- **`evaluate_js()` thread safety:** On GTK/Qt backends, must be called from the main thread. All push events go through a thread-safe queue that the main thread drains on a ~16ms timer.
- **Shared state:** Minimal. Immutable snapshots read freely, mutations go through the asyncio thread. No bare threading locks if avoidable.

## Streaming & Event System

All Python→JS push communication goes through a single batched event bus — never raw `evaluate_js` calls with string interpolation:

```python
def push_event(self, event_type: str, payload: dict):
    """Batched, thread-safe push to frontend."""
    self._event_queue.put((event_type, payload))

# Main thread drains queue every ~16ms and calls:
# evaluate_js(f"window.__bridge.onEvent({json.dumps(event_type)}, {json.dumps(payload)})")
```

Chunks are buffered ~50ms before flushing to reduce IPC round-trips. The frontend's `bridge.ts` wraps this in a typed EventEmitter.

## Emotion Tag Parsing

The LLM emits `[emotion:NAME]` tags inline. The stream post-processor:
- Maintains a buffer for partial tags (tags can split across chunks: `[emoti` + `on:happy]`)
- If `[` seen without `]`, buffer until resolved. Flush as plain text if buffer exceeds 50 chars.
- Defaults to `neutral` if no tags found — local 7B models are unreliable at emitting tags.

## Memory Extraction

Batched, NOT per-turn. Triggers when:
- 5+ unprocessed turns accumulated
- User idle 30+ seconds
- Conversation ends

This avoids queuing a second LLM inference while the main response is still generating.

## Error Handling

- **Ollama not running:** Detect on startup, show clear error with instructions.
- **Network drops mid-stream:** Catch httpx timeouts, surface user-visible error, don't persist half-finished assistant messages.
- **sqlite-vec fails to load:** Fall back to SQL LIKE queries for memory search.
- **Voice recording is noise:** VAD rejects it, STT returns empty — treat as no input.
- **General:** Log errors, surface when actionable, degrade gracefully, never corrupt persisted state.
