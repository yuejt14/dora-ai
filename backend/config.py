"""Application configuration — settings, paths, env var loading."""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env before anything reads os.environ
load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
SOULS_DIR = APP_DIR / "souls"
DB_PATH = DATA_DIR / "dora.db"


# ── Settings models ───────────────────────────────────────────────────────


class OllamaSettings(BaseModel):
    base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model: str = os.getenv("OLLAMA_MODEL", "llama3.2")


class ProviderSettings(BaseModel):
    active: str = "ollama"
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)


class AppSettings(BaseModel):
    provider: ProviderSettings = Field(default_factory=ProviderSettings)
    log_level: str = "INFO"


# ── Logging setup ─────────────────────────────────────────────────────────


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging with per-module loggers."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        root.addHandler(handler)

    # Quiet noisy third-party loggers
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a per-module logger."""
    return logging.getLogger(name)
