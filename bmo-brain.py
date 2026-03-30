from flask import Flask, jsonify
from flask_cors import CORS
import threading
import requests
import sounddevice as sd
import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
import subprocess
import time
import random
import os
import logging
import scipy.signal

# 🌐 SERVER
app = Flask(__name__)
CORS(app)
logging.getLogger('werkzeug').disabled = True

state = {"state": "idle", "volume": 0.0}

MODEL_RATE = 16000  # whisper expects this
MIC_RATE = 48000    # 🔥 headset native rate

talkative = True

print("Loading Whisper...")
model = WhisperModel("base", device="cpu", compute_type="int8")
print("Whisper ready!")

# 🎤 SELECT MIC
def get_input_device():
    devices = sd.query_devices()

    print("\n🎤 Available microphones:")
    valid = []

    for i, d in enumerate(devices):
        if d['max_input_channels'] > 0:
            print(f"{i}: {d['name']}")
            valid.append(i)

    if not valid:
        raise Exception("No microphone found")

    chosen = valid[0]
    print(f"\n✅ Using mic id: {chosen}\n")

    return chosen

MIC_DEVICE = get_input_device()

# 🔊 SPEAK
def speak(text):
    global state

    state["state"] = "talking"
    print("🔊", text)

    try:
        if os.path.exists("bmo.aiff"):
            os.remove("bmo.aiff")

        subprocess.run(["say", "-o", "bmo.aiff", text], check=True)

        audio, rate = sf.read("bmo.aiff", dtype='float32')

        if audio.ndim > 1:
            audio = audio[:, 0]

        audio = audio / max(1e-6, np.max(np.abs(audio)))

        def play():
            sd.play(audio, rate)
            sd.wait()

        def animate():
            chunk = int(rate * 0.02)
            for i in range(0, len(audio), chunk):
                part = audio[i:i+chunk]
                state["volume"] = float(np.abs(part).mean())
                time.sleep(0.02)
            state["volume"] = 0

        t1 = threading.Thread(target=play)
        t2 = threading.Thread(target=animate)

        t1.start()
        t2.start()

        t1.join()
        t2.join()

    except:
        subprocess.run(["say", text])

    finally:
        state["state"] = "idle"
        state["volume"] = 0

# 🤖 RESPONSE
def ask_bmo(user_input):
    global talkative

    state["state"] = "thinking"

    if "be quiet" in user_input.lower():
        talkative = False
    if "talk more" in user_input.lower():
        talkative = True

    prompt = f"""
You are BMO.
Playful, weird, short (1 sentence max).

User: {user_input}
BMO:
"""

    res = requests.post("http://localhost:11434/api/generate", json={
        "model": "llama3",
        "prompt": prompt,
        "stream": False
    })

    return res.json()["response"].strip()[:120]

# 🎲 IDLE
def idle_thought():
    try:
        res = requests.post("http://localhost:11434/api/generate", json={
            "model": "llama3",
            "prompt": "Say a short playful random thought.",
            "stream": False
        })
        return res.json()["response"].strip()[:80]
    except:
        return "beep boop"

# 🧠 TRANSCRIBE
def transcribe(audio):
    try:
        if len(audio) < MODEL_RATE:
            return ""

        audio = audio / max(1e-6, np.max(np.abs(audio)))

        sf.write("temp.wav", audio, MODEL_RATE)

        segments, _ = model.transcribe("temp.wav")
        return " ".join([s.text for s in segments]).strip()

    except:
        return ""

# 🎤 STREAM LOOP
def audio_stream_loop():
    speaking = False
    silence = 0
    buffer = []

    print("👂 BMO is listening...\n")

    def callback(indata, frames, t, status):
        nonlocal speaking, silence, buffer

        mono = indata.mean(axis=1) if indata.ndim > 1 else indata

        # 🔥 amplify
        mono = mono * 12.0

        vol = np.abs(mono).mean()

        if vol > 0.002:
            speaking = True
            silence = 0
            buffer.append(mono.copy())

        elif speaking:
            silence += 1
            buffer.append(mono.copy())

            if silence > 20:
                if len(buffer) < MIC_RATE * 0.7:
                    buffer.clear()
                    speaking = False
                    silence = 0
                    return

                audio = np.concatenate(buffer)

                # 🔥 RESAMPLE 48k → 16k
                audio = scipy.signal.resample(
                    audio,
                    int(len(audio) * MODEL_RATE / MIC_RATE)
                )

                print("🧠 Processing...")
                text = transcribe(audio)
                print("You:", text)

                if text.strip():
                    reply = ask_bmo(text)
                    print("BMO:", reply)
                    speak(reply)

                buffer.clear()
                speaking = False
                silence = 0

    with sd.InputStream(
        samplerate=MIC_RATE,   # 🔥 KEY FIX
        channels=1,
        dtype='float32',
        callback=callback,
        device=MIC_DEVICE
    ):
        while True:
            if talkative and random.random() < 0.01:
                speak(idle_thought())

            time.sleep(0.2)

# 🌐 STATE
@app.route("/state")
def get_state():
    return jsonify(state)

def run_server():
    app.run(host="0.0.0.0", port=5050)

# 🚀 START
if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    time.sleep(1)

    audio_stream_loop()