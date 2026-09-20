import os
import requests
import re
from celery import Celery
from funasr import AutoModel

app = Celery("audio_worker", broker="redis://localhost:6379/0")

print("Worker process starting... Loading SenseVoice into VRAM...")
model = AutoModel(
    model="iic/SenseVoiceSmall",
    trust_remote_code=True,
    device="cuda:0",
    disable_update=True,
)
print("Model loaded and ready!")

BOT_TOKEN = os.getenv("BOT_TOKEN")

@app.task
def transcribe_and_reply(chat_id, file_path, original_msg_id):
    try:
        res = model.generate(input=file_path, cache={}, language="auto", use_itn=True)
        text = res[0]["text"]
        clean_text = re.sub(r"<\|.*?\|>", "", text).strip()

        payload = {
            "chat_id": chat_id,
            "text": clean_text,
            "reply_to_message_id": original_msg_id,
        }
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload
        )
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        print(f"Error: {e}")
