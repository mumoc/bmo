# BMO

A voice-activated AI companion styled as BMO from Adventure Time.
BMO listens to you, responds with short playful sentences, and occasionally rambles on its own.
A browser-based animated face syncs to its speech in real time.

## Requirements

- macOS (uses the `say` command for text-to-speech)
- Python 3.9+
- [Homebrew](https://brew.sh)
- [Ollama](https://ollama.com) — install and make sure `ollama` is in your PATH
- A microphone — built-in, USB headset, or **iPhone via Continuity Microphone** (see below)

## Running

```bash
./run-bmo.sh
```

The script handles everything on first run:
- Installs Python dependencies (`pip3 install -r requirements.txt`)
- Installs `portaudio` via Homebrew if missing
- Starts Ollama if it isn't already running
- Pulls the `llama3` model if not already downloaded
- Starts the animated face server at `http://localhost:8080`
- Launches the BMO brain

Open `http://localhost:8080` in your browser to see BMO's face.

Press `Ctrl+C` to stop everything.

## Using iPhone as microphone (no headset needed)

1. Both iPhone and Mac must be on the same Apple ID and Wi-Fi network
2. iPhone: Settings → General → AirPlay & Handoff → Continuity Camera → ON
3. Mac: System Settings → Sound → Input → select **iPhone Microphone**

BMO will use whatever is set as the system default input device.

## Talking to BMO

Just speak naturally. BMO will:

1. Detect your voice automatically (no wake word needed)
2. Transcribe what you said locally via Whisper
3. Generate a short, playful response via Ollama (`llama3`)
4. Speak the response using macOS `say`

**Special voice commands:**
- `"be quiet"` — stops BMO from making unprompted idle remarks
- `"talk more"` — re-enables idle remarks

**Interrupting BMO:** speak loudly while BMO is talking to cut it off mid-sentence.

## BMO's memory

BMO remembers two things:

- **Conversation context** — the last 5 exchanges are included in every prompt, so BMO can refer back to what was just said.
- **Long-term facts** — after each exchange, BMO silently asks Ollama if anything is worth remembering (your name, preferences, etc.). Facts are saved to `memory.json` and reloaded every time BMO starts.

To wipe BMO's memory: `rm memory.json`

## Configuration

All tunable values are constants at the top of `bmo-brain.py`:

| Constant | Default | What it does |
|---|---|---|
| `MAX_HISTORY` | `5` | Conversation turns kept in prompt |
| `INTERRUPT_THRESHOLD` | `0.05` | Amplified volume needed to interrupt BMO |
| `INTERRUPT_FRAMES` | `8` | Consecutive frames above threshold to confirm interrupt |

Idle thought frequency is controlled by the probability in the main loop (`0.01` = ~1 thought per 20 seconds). Increase for a chattier BMO, decrease for a quieter one.
