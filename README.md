# Dora AI

A persistent, expressive AI companion for your desktop. Talk to an AI character with personality, memory, and voice — running locally with [Ollama](https://ollama.com/) or via cloud providers.

Inspired by [moeru-ai/airi](https://github.com/moeru-ai/airi).

## Features

- **Personality system** — YAML-defined "souls" that shape how the AI speaks and behaves, with emotion detection
- **Persistent memory** — the AI remembers facts about you across conversations using SQLite + vector search
- **Streaming responses** — real-time token streaming from local or cloud LLMs
- **Voice chat** — speech-to-text and text-to-speech for hands-free conversation (planned)
- **Desktop companion** — native desktop window with an animated character overlay (planned)
- **Local-first** — fully functional with Ollama before any cloud API keys are needed

## Status

Early development. The backend core is functional (Phases 1.1–1.4 complete):

- Config and environment loading
- Ollama streaming provider
- SQLite persistence with migrations
- Async bridge and conversation pipeline
- CLI chat loop
- Unit test suite (21 tests covering all core modules)

See [plan.md](plan.md) for the full roadmap.

## Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Ollama](https://ollama.com/) running locally with a model pulled (e.g. `ollama pull llama3`)

## Getting Started

```bash
# Clone the repository
git clone https://github.com/your-username/dora-ai.git
cd dora-ai

# Install dependencies
uv sync

# Set up environment variables
cp .env.example .env  # then edit .env with your settings

# Run the CLI chat
uv run python -m backend.cli
```

## Configuration

Configuration is loaded from environment variables (`.env` file):

| Variable | Description | Default |
|----------|-------------|---------|
| `OLLAMA_BASE_URL` | Ollama API endpoint | `http://localhost:11434` |
| `OLLAMA_MODEL` | Model to use | `llama3` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |

## CLI Commands

Once in the chat loop, the following commands are available:

| Command | Description |
|---------|-------------|
| `/new` | Start a new conversation |
| `/history` | Show message history for the current conversation |
| `/quit` | Exit the chat |

On startup, you can select an existing conversation to resume or create a new one.

## Development

```bash
# Lint
uv run ruff check .

# Format
uv run ruff format .

# Auto-fix lint issues
uv run ruff check --fix .

# Run tests
uv run pytest tests/ -v
```

## Architecture

**This is a desktop app, not a web app.** There is no HTTP server — communication between the Python backend and the React frontend (coming in Phase 5) uses [pywebview](https://pywebview.flowrl.com/)'s native JS bridge.

Key design decisions:

- **Pydantic models** for all data structures (no dataclasses)
- **Custom provider layer** (no LangChain)
- **SQLite** as the only persistence layer
- **Frontend never calls external APIs** — everything routes through the Python backend

See [docs/architecture.md](docs/architecture.md) for detailed design.

## License

TBD
