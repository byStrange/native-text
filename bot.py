import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
from celery import Celery
import redis
import json

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Same token
DOWNLOAD_DIR = "downloads"
DATASET_FILE = "dataset.json"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

celery_app = Celery("audio_producer", broker="redis://localhost:6379/0")
redis_client = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    print(f"Received voice note from {user.first_name}")

    voice_file = await update.message.voice.get_file()

    file_path = os.path.join(DOWNLOAD_DIR, f"{user.id}_{update.message.id}.ogg")

    await voice_file.download_to_drive(file_path)

    celery_app.send_task(
        "transcribe_task",
        args=[update.message.chat_id, file_path, update.message.id, voice_file.file_id],
    )


async def handle_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    action, task_id = data.split(":", 1)

    # Retrieve state from Redis
    redis_key = f"task_data:{task_id}"
    state_json = redis_client.get(redis_key)

    if not state_json:
        await query.edit_message_text(text="⚠️ Interaction expired or data lost.")
        return

    state_data = json.loads(state_json)
    audio_path = state_data.get("audio_path")
    original_text = state_data.get("text")

    if action == "good":
        # Save to dataset immediately
        entry = {"audio_path": audio_path, "text": original_text, "verified": True}
        save_dataset_entry(entry)
        await query.edit_message_text(text=f"✅ Marked as accurate!\n\n{original_text}")

    elif action == "bad":
        # Ask for correction
        # We store the task_id in user_data to know what they are correcting
        context.user_data["correction_task_id"] = task_id
        await query.edit_message_text(
            text=f"❌ Marked as inaccurate.\n\nPlease reply with the correct text for this audio."
        )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages - routes to correction mode or summarization."""
    # Check if user is in correction mode first
    task_id = context.user_data.get("correction_task_id")
    if task_id:
        await process_correction(update, context, task_id)
        return

    # Regular text message - queue for summarization
    user = update.message.from_user
    text = update.message.text
    print(f"Received text message from {user.first_name}: {text[:50]}...")

    # Queue summarization task
    celery_app.send_task(
        "summarize_text_task",
        args=[update.message.chat_id, text, update.message.id],
    )

    # Send a "thinking" indicator
    await update.message.reply_text("🤔 Analyzing your message...")


async def process_correction(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: str):
    """Process a correction from user feedback."""
    text = update.message.text

    # Retrieve state from Redis
    redis_key = f"task_data:{task_id}"
    state_json = redis_client.get(redis_key)

    if not state_json:
        await update.message.reply_text("⚠️ Original audio data expired.")
        del context.user_data["correction_task_id"]
        return

    state_data = json.loads(state_json)
    audio_path = state_data.get("audio_path")

    # Save correction
    state_data["corrected_text"] = text
    save_dataset_entry(state_data)

    await update.message.reply_text("✅ Correction saved! Thank you.")
    del context.user_data["correction_task_id"]


def save_dataset_entry(entry):
    """Appends an entry to the dataset JSON file."""
    data = []
    if os.path.exists(DATASET_FILE):
        try:
            with open(DATASET_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            pass  # Start fresh if corrupt

    data.append(entry)

    with open(DATASET_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Filter for Voice notes only
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(CallbackQueryHandler(handle_feedback))
    # Handle all text messages (corrections handled inside via user_data check)
    app.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text_message)
    )

    print("Bot is polling...")
    app.run_polling()
