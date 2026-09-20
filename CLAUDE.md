# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Uzbek Speech-to-Text Telegram Bot with dataset collection and LLM-powered summarization. The bot receives voice messages and transcribes them, generates summaries, and collects user feedback/corrections to build a training dataset. It also supports text message summarization.

## Architecture

**Producer-Consumer Pattern with Celery + Redis + Ollama:**
- `bot.py` - Telegram bot (producer): Receives messages, downloads voice files, queues tasks
- `worker_test.py` - Celery worker (consumer): Transcribes audio with Whisper, generates summaries via Ollama
- `prompts/summarization_system_prompt.txt` - System prompt for LLM summarization

**Voice Message Flow:**
1. User sends voice → bot downloads to `downloads/`
2. Celery task queued (`transcribe_task`)
3. Worker transcribes with faster-whisper (large-v3-turbo)
4. User receives **transcription** (1:1 text)
5. Worker generates **summary** via Ollama ("User is trying to...")
6. If Uzbek detected (or low confidence), audio moved to `dataset_audio/` + feedback buttons shown *(only when `ENABLE_DATA_COLLECTION` is on)*
7. User corrections saved to `dataset.json`

Steps 5-7 are gated behind the feature flags below.

**Text Message Flow:**
1. User sends text (not in correction mode)
2. Celery task queued (`summarize_text_task`)
3. Worker generates summary via Ollama
4. Summary sent back to user

## Development Commands

**Install dependencies:**
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Start Redis (required):**
```bash
redis-server
```

**Start the bot (producer):**
```bash
source venv/bin/activate
python bot.py
```

**Start the worker (consumer):**
```bash
source venv/bin/activate
python worker_test.py
# Or for SenseVoice alternative:
# python worker.py
```

**Test transcription standalone:**
```bash
python test.py  # Uses SenseVoiceSmall model
```

## Key Files

| File | Purpose |
|------|---------|
| `bot.py` | Telegram bot frontend, voice + text handlers, feedback collection |
| `worker_test.py` | **Active worker**: Whisper transcription + Ollama summarization |
| `worker.py` | Alternative worker using SenseVoice model (no summarization) |
| `test.py` | Standalone SenseVoice transcription test |
| `prompts/summarization_system_prompt.txt` | LLM system prompt for summarization |
| `config.py` | Shared env config + feature flags |
| `requirements.txt` | Python dependencies |
| `dataset.json` | Collected training data (verified/corrected transcriptions) |
| `dataset_audio/` | Persistent audio files for dataset |
| `downloads/` | Temporary audio download folder (auto-cleaned) |

## Environment Variables

```bash
export BOT_TOKEN="your_telegram_bot_token"      # Required for bot.py, worker_test.py, worker.py

# Ollama Configuration
export OLLAMA_HOST="http://localhost:11434"     # For local: http://localhost:11434
                                                # For Ollama Cloud: https://ollama.com
export OLLAMA_MODEL="llama3.2"                # Model name (e.g., llama3.2, mistral, etc.)
export OLLAMA_API_KEY="your_api_key"            # Required for Ollama Cloud, optional for local

# Feature flags (see config.py)
export ENABLE_SUMMARIZATION=1                   # Default: on only if OLLAMA_API_KEY is set
export ENABLE_DATA_COLLECTION=0                 # Default: on
```

**Feature flags:**

| Flag | Default | Off behavior |
|------|---------|--------------|
| `ENABLE_SUMMARIZATION` | On only when `OLLAMA_API_KEY` is set | No summary after transcriptions; text messages get no reply at all. Ollama is never contacted. Set to `1` to enable against a local Ollama, which needs no key. |
| `ENABLE_DATA_COLLECTION` | On | No feedback buttons, no audio kept in `dataset_audio/`, nothing written to `dataset.json`. Voice notes are transcribed, replied to, and the temp file deleted. |

Accepted truthy values: `1`, `true`, `yes`, `on` (case-insensitive). Anything else is false.
Note that Uzbek re-transcription is a transcription-quality fix and runs regardless of
`ENABLE_DATA_COLLECTION`.

## Key Implementation Details

**Language Detection & Forced Correction:**
- Worker detects language; if it's in `["tr", "uz", "kk", "az"]` or probability < 0.6, re-transcribes with forced `language="uz"`
- This handles Whisper's tendency to confuse Turkic languages

**State Management:**
- Redis stores task data at `task_data:{chat_id}_{msg_id}` with 24h TTL
- Stores: transcription text, audio path, language probabilities
- Bot retrieves this on feedback callback to save to dataset

**Dataset Schema:**
```json
{
  "audio_path": "dataset_audio/5555876379_1340.ogg",
  "text": "o'zbekchani eplalmayaptiyu",
  "verified": true,
  "original_machine_text": "Guzbekihani iplenme yaptıyo."
}
```

**Dependencies (from venv):**
- `python-telegram-bot` (v20+, async)
- `faster-whisper`
- `celery`
- `redis`
- `funasr` (for SenseVoice model in test.py/worker.py)
- `torch`
- `ollama` (Python library for Ollama API)

## Ollama Setup

### Install Ollama Python Library
```bash
pip install ollama
```

### Option 1: Local Ollama (Default)
```bash
# Install Ollama from https://ollama.ai
# Then run your chosen model:
ollama run llama3.2  # Or whatever model you configure in OLLAMA_MODEL
```
Environment:
```bash
export OLLAMA_HOST="http://localhost:11434"
export OLLAMA_MODEL="llama3.2"
# No API key needed for local
```

### Option 2: Ollama Cloud
Sign up at https://ollama.com/cloud and get your API key.

Environment:
```bash
export OLLAMA_HOST="https://ollama.com"
export OLLAMA_MODEL="llama3.2"  # or cloud models like gpt-oss:120b, kimi-k2:1t-cloud
export OLLAMA_API_KEY="your_ollama_cloud_api_key"
```

The summarization system prompt is defined in `prompts/summarization_system_prompt.txt`.

## Testing Audio Files

Several test audio files are in the repo for manual testing:
- `behruz_voice_*_test.m4a` - Test voice samples (en, ru, uz)
- `audio_2026-01-29_22-22-08.ogg` - Sample for test.py
