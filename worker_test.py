import os
import requests
from faster_whisper import WhisperModel
from celery import Celery
from torch.cuda import temperature
from ollama import Client

import shutil
import json
import redis

# Ollama configuration
# For Ollama Cloud, use: https://ollama.com (no /api suffix - the client handles it)
# For local Ollama, use: http://localhost:11434 (default)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:20b-cloud")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")  # Required for Ollama Cloud

def get_ollama_client():
    """Create and configure Ollama client with proper authentication."""
    if OLLAMA_API_KEY:
        # Cloud mode with API key
        return Client(
            host=OLLAMA_HOST,
            headers={'Authorization': f'Bearer {OLLAMA_API_KEY}'}
        )
    else:
        # Local mode (no auth needed)
        return Client(host=OLLAMA_HOST)

def load_system_prompt():
    """Load the system prompt for summarization from file."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "summarization_system_prompt.txt")
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        # Fallback prompt if file doesn't exist
        return (
            "You are a helpful assistant that analyzes user messages and provides "
            "concise summaries of what the user is trying to communicate. "
            "Format your response as: '📝 Summary: User is trying to [action/intent]'. "
            "Maintain the original language of the user."
        )

SYSTEM_PROMPT = load_system_prompt()

def generate_summary(text: str) -> str:
    """Generate a summary of the user's message using Ollama."""
    try:
        client = get_ollama_client()
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        return response.message.content
    except Exception as e:
        print(f"Ollama error: {e}")
        return f"⚠️ Could not generate summary: {str(e)}"
        return f"⚠️ Could not generate summary: {str(e)}"
    except KeyError:
        print(f"Unexpected Ollama response format: {result}")
        return "⚠️ Could not generate summary: unexpected response format"

BOT_TOKEN = os.getenv("BOT_TOKEN")

app = Celery("audio_worker", broker="redis://localhost:6379/0")
redis_client = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)
DATASET_AUDIO_DIR = "dataset_audio"
os.makedirs(DATASET_AUDIO_DIR, exist_ok=True)

print("Worker process starting... Loading WhisperModel into VRAM...")

model_size = "large-v3-turbo"
global_model = WhisperModel(model_size, device="cuda", compute_type="float16")

print("Worker process loaded the model")


@app.task(name="transcribe_task")
def transcribe_and_reply(chat_id, file_path, original_msg_id, file_id):
    segments, info = global_model.transcribe(
        file_path,
        beam_size=5,
        temperature=0.0,
        vad_filter=True,
        condition_on_previous_text=False,
    )

    detected_lang = info.language
    probability = info.language_probability
    enable_collection = False
    uz_related_langs = ["tr", "uz", "kk", "az"]

    original_segments = segments
    original_lang = detected_lang
    original_probability = probability
    original_info = info

    print(f"Detected: {detected_lang} ({probability:.2f})")

    if (detected_lang in uz_related_langs) or probability < 0.6:
        enable_collection = True
        print(f"{detected_lang} detected! Correcting to Uzbek...")
        segments, info = global_model.transcribe(
            file_path,
            beam_size=5,
            language="uz",
            temperature=0.0,
            vad_filter=True,
            condition_on_previous_text=False,
        )

    text = " ".join([segment.text for segment in segments])
    original_segments = " ".join([segment.text for segment in original_segments])

    # Chunking Logic
    MAX_CHUNK_SIZE = 4000
    chunks = []
    if len(text) <= MAX_CHUNK_SIZE:
        chunks = [text]
    else:
        # Split by spaces to avoid breaking words, or just hard split if needed
        # Simple implementation:
        for i in range(0, len(text), MAX_CHUNK_SIZE):
            chunks.append(text[i : i + MAX_CHUNK_SIZE])

    # Audio Persistence & State Logic
    saved_audio_path = None
    task_unique_id = (
        f"{chat_id}_{original_msg_id}"  # Simple unique ID for this interaction
    )

    print(detected_lang)
    if enable_collection:
        # Move file to persistence directory
        filename = os.path.basename(file_path)
        final_path = os.path.join(DATASET_AUDIO_DIR, filename)
        shutil.move(file_path, final_path)
        saved_audio_path = final_path

        # Save state to Redis for bot to retrieve on callback
        # Key format: task:{chat_id}:{original_msg_id}
        state_data = {
            "text": text,
            "audio_path": saved_audio_path,
            "file_id": file_id,
            "initial_response": original_segments,
            "initial_response_lang": original_lang,
            "initial_probability": original_probability,
            "forced": True,
            "forced_lang": info.language,
            "forced_probability": info.language_probability,
            "all_language_probs": original_info.all_language_probs,
        }
        redis_client.setex(f"task_data:{task_unique_id}", 86400, json.dumps(state_data))
    else:
        if os.path.exists(file_path):
            os.remove(file_path)

    # Send Chunks
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1

        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "reply_to_message_id": original_msg_id,
        }

        # Add buttons to the last chunk if Uzbek
        if is_last and enable_collection:
            reply_markup = {
                "inline_keyboard": [
                    [
                        {
                            "text": "👍 Accurate",
                            "callback_data": f"good:{task_unique_id}",
                        },
                        {
                            "text": "👎 Inaccurate",
                            "callback_data": f"bad:{task_unique_id}",
                        },
                    ]
                ]
            }
            payload["reply_markup"] = reply_markup

        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload
            )
        except Exception as e:
            print(f"Error sending message: {e}")

    # Generate and send summary after all chunks
    try:
        print(f"Generating summary for transcription...")
        summary = generate_summary(text)

        summary_payload = {
            "chat_id": chat_id,
            "text": f"📋 **Summary**:\n{summary}",
            "reply_to_message_id": original_msg_id,
            "parse_mode": "Markdown",
        }
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=summary_payload
        )
    except Exception as e:
        print(f"Error generating summary: {e}")


@app.task(name="summarize_text_task")
def summarize_text_and_reply(chat_id: int, text: str, original_msg_id: int):
    """Summarize a text message and send the result back to Telegram."""
    try:
        print(f"Summarizing text message: {text[:50]}...")
        summary = generate_summary(text)

        payload = {
            "chat_id": chat_id,
            "text": f"📋 **Message Summary**:\n{summary}",
            "reply_to_message_id": original_msg_id,
            "parse_mode": "Markdown",
        }

        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload
        )
        print("Summary sent successfully")
    except Exception as e:
        print(f"Error in summarize_text_task: {e}")
