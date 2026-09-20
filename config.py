"""Shared runtime configuration for the bot and the workers."""

import os


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean env var. Accepts 1/true/yes/on (case-insensitive)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Ollama
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:20b-cloud")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")

# Summarization is optional and stays off unless an Ollama API key is set.
# A local Ollama needs no key, so set ENABLE_SUMMARIZATION=1 to force it on.
SUMMARIZATION_ENABLED = _env_flag("ENABLE_SUMMARIZATION", bool(OLLAMA_API_KEY))

# Data gathering: feedback buttons, audio retention in dataset_audio/, and
# dataset.json writes. Off means transcribe, reply, done.
DATA_COLLECTION_ENABLED = _env_flag("ENABLE_DATA_COLLECTION", True)
