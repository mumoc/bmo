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
import json
import math
import warnings
import scipy.signal
from urllib3.exceptions import NotOpenSSLWarning
warnings.filterwarnings("ignore", category=NotOpenSSLWarning)

# 🌐 SERVER
app = Flask(__name__)
CORS(app)
logging.getLogger('werkzeug').disabled = True

state = {"state": "idle", "volume": 0.0}

MODEL_RATE = 16000       # whisper expects this
INTERRUPT_THRESHOLD = 0.05   # volume to cut BMO mid-speech (post-amplification)
INTERRUPT_FRAMES = 8         # consecutive frames above threshold required
MAX_HISTORY = 5         # conversation turns kept in prompt

talkative = True
conversation_history = []   # list of {"user": ..., "bmo": ...}
long_term_memory = []       # persistent facts, loaded from memory.json

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
        print("⚠️  No explicit mic found — using system default input (e.g. iPhone Continuity Mic)")
        return None

    chosen = valid[0]
    print(f"\n✅ Using mic id: {chosen}\n")

    return chosen

MIC_DEVICE = get_input_device()
MIC_RATE = int(sd.query_devices(kind='input')['default_samplerate'])

# 🔊 SPEAK
def speak(text):
    global state

    busy.set()
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
        time.sleep(0.8)  # let room echo die before re-enabling mic
        busy.clear()

# 🤖 RESPONSE
def ask_bmo(user_input):
    global talkative

    state["state"] = "thinking"

    if "be quiet" in user_input.lower():
        talkative = False
    if "talk more" in user_input.lower():
        talkative = True

    memory_block = "\n".join(f"- {f}" for f in long_term_memory) or "Nothing yet."
    history_block = "\n".join(
        f"User: {h['user']}\nBMO: {h['bmo']}"
        for h in conversation_history[-MAX_HISTORY:]
    )

    prompt = f"""You are BMO. Playful, weird, short (1 sentence max).

What BMO knows about you:
{memory_block}

Recent conversation:
{history_block}

User: {user_input}
BMO:"""

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

        if not np.isfinite(audio).all():
            return ""

        audio = audio / max(1e-6, np.max(np.abs(audio)))

        sf.write("temp.wav", audio, MODEL_RATE)

        segments, _ = model.transcribe("temp.wav", vad_filter=True)
        return " ".join([s.text for s in segments]).strip()

    except:
        return ""

# 🧠 LONG-TERM MEMORY
def load_memory():
    if os.path.exists("memory.json"):
        try:
            with open("memory.json") as f:
                data = json.load(f)
                long_term_memory.extend(data.get("facts", []))
                print(f"🧠 Loaded {len(long_term_memory)} memory facts")
        except:
            pass

def save_memory():
    with open("memory.json", "w") as f:
        json.dump({"facts": long_term_memory}, f, indent=2)

def extract_memory(user_input, reply):
    """Runs in background thread. Asks Ollama if anything from this exchange is worth remembering."""
    try:
        known = json.dumps(long_term_memory)
        prompt = f"""You are helping BMO remember important facts about the user.
Given this exchange, extract any personal facts worth remembering long-term (name, job, hobbies, preferences, etc.).
Reply ONLY with a JSON array of short fact strings. Reply [] if nothing new.
Current known facts: {known}
Exchange — User: {user_input} / BMO: {reply}
Facts:"""
        res = requests.post("http://localhost:11434/api/generate", json={
            "model": "llama3",
            "prompt": prompt,
            "stream": False
        })
        raw = res.json()["response"].strip()
        start, end = raw.find("["), raw.rfind("]") + 1
        if start >= 0 and end > start:
            new_facts = json.loads(raw[start:end])
            added = [f for f in new_facts if f and f not in long_term_memory]
            if added:
                long_term_memory.extend(added)
                save_memory()
                print(f"🧠 Remembered: {added}")
    except:
        pass

load_memory()

busy = threading.Event()  # set while BMO is thinking or speaking

# 🎤 PROCESS UTTERANCE (runs in worker thread, not in audio callback)
def process_utterance(audio):
    busy.set()
    try:
        gcd = math.gcd(MODEL_RATE, MIC_RATE)
        audio = scipy.signal.resample_poly(audio, MODEL_RATE // gcd, MIC_RATE // gcd)

        print("🧠 Processing...")
        text = transcribe(audio)
        print("You:", text)

        if text.strip():
            reply = ask_bmo(text)
            print("BMO:", reply)
            conversation_history.append({"user": text, "bmo": reply})
            if len(conversation_history) > MAX_HISTORY:
                conversation_history.pop(0)
            threading.Thread(target=extract_memory, args=(text, reply), daemon=True).start()
            speak(reply)  # speak() owns busy from here — sets it again + clears with cooldown
        else:
            busy.clear()
            print("👂 Listening...")
    except Exception:
        busy.clear()
        print("👂 Listening...")

# 🎤 STREAM LOOP
def audio_stream_loop():
    speaking = False
    silence = 0
    buffer = []
    interrupt_count = 0

    print("👂 BMO is listening...\n")

    def callback(indata, frames, t, status):
        nonlocal speaking, silence, buffer, interrupt_count

        if status:
            print("⚠️ Audio status:", status)

        mono = indata.mean(axis=1) if indata.ndim > 1 else indata
        mono = mono * 12.0
        vol = np.abs(mono).mean()

        if busy.is_set():
            if state["state"] == "talking" and vol > INTERRUPT_THRESHOLD:
                interrupt_count += 1
                if interrupt_count >= INTERRUPT_FRAMES:
                    print("✋ Interrupted!")
                    interrupt_count = 0
                    speaking = False
                    silence = 0
                    buffer.clear()
                    threading.Thread(target=sd.stop, daemon=True).start()
            else:
                interrupt_count = 0
            return

        interrupt_count = 0

        if vol > 0.002:
            if not speaking:
                print("🎤 Heard something...")
                state["state"] = "listening"
            speaking = True
            silence = 0
            buffer.append(mono.copy())

        elif speaking:
            silence += 1
            buffer.append(mono.copy())

            if silence > 40:
                total_samples = sum(len(chunk) for chunk in buffer)
                if total_samples < MIC_RATE * 0.7:
                    print("⏭ Too short, ignoring")
                    buffer.clear()
                    speaking = False
                    silence = 0
                    state["state"] = "idle"
                    return

                audio = np.concatenate(buffer)
                buffer.clear()
                speaking = False
                silence = 0

                threading.Thread(target=process_utterance, args=(audio,), daemon=True).start()

    with sd.InputStream(
        samplerate=MIC_RATE,   # 🔥 KEY FIX
        channels=1,
        dtype='float32',
        callback=callback,
        device=MIC_DEVICE
    ):
        while True:
            if talkative and not busy.is_set() and random.random() < 0.01:
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