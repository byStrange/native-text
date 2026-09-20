from funasr import AutoModel
# 1. Initialize the Model
# We load 'SenseVoiceSmall' from the 'iic' (Interactive Intelligent Computing) repo.
# device="cuda:0" forces it onto your RTX 3050.
print("Loading Model to GPU...")
model = AutoModel(
    model="iic/SenseVoiceSmall",
    trust_remote_code=True,
    device="cuda:0",
    disable_update=True  # optional: prevents checking for updates every run
)

audio_file = "audio_2026-01-29_22-22-08.ogg"  # Make sure this file exists!

# 3. Inference
# language="auto" lets it detect language.
# use_itn=True (Inverse Text Normalization) converts "one hundred" to "100".
print(f"Transcribing {audio_file}...")
res = model.generate(
    input=audio_file,
    cache={},
    language="auto", 
    use_itn=True,
    batch_size_s=60, # Process 60 seconds of audio at a time (fits in your VRAM)
)

text = res[0]['text']

print("-" * 30)
print("Raw Output:")
print(text)
print("-" * 30)
