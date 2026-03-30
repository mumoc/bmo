---
# App Context — BMO Brain

## System Purpose

A voice-activated AI companion styled as BMO (Adventure Time). The user speaks; BMO listens,
transcribes locally, generates a short playful response via a local LLM, and speaks it back
using macOS TTS. A browser-based face animates in sync with BMO's speech.

## Primary Actor

Single local user (the developer). No authentication, no multi-user support.

## Architecture

Flat single-file Python app (`bmo-brain.py`). No framework beyond Flask for the state endpoint.

```
Microphone (48kHz) → VAD buffer → resample to 16kHz → Whisper → LLM (Ollama/llama3) → say (TTS) → speaker
                                                                                           ↓
                                                                             /state endpoint → index.html face
```

**Threads:**
- Main thread: `audio_stream_loop()` — runs the sounddevice InputStream with a callback
- `run_server()` daemon thread: Flask on port 5050
- Per-utterance: `speak()` spawns two threads (play + animate volume)

## Business Rules

1. **Voice activity detection:** Audio above `vol > 0.002` (after 12x amplification) starts buffering.
   Silence for >20 callback frames ends the utterance. Utterances shorter than 0.7s are discarded.

2. **Response persona:** BMO always responds in 1 sentence max, playful and weird. Prompt is
   hardcoded in `ask_bmo()`. Response is truncated at 120 chars.

3. **Talkative mode:** Controlled by keywords in user speech:
   - "be quiet" → sets `talkative = False` (suppresses idle thoughts)
   - "talk more" → sets `talkative = True`

4. **Idle thoughts:** When `talkative=True`, ~1% chance per 0.2s tick to speak an unprompted
   random thought (LLM-generated, truncated at 80 chars). Falls back to "beep boop" on error.

5. **TTS flow:** `say` writes to `bmo.aiff`, which is read and played via sounddevice for
   volume-sync animation. Falls back to direct `say` subprocess if file I/O fails.

6. **State machine:** `state["state"]` transitions: `idle` → `thinking` (LLM call) → `talking`
   (TTS playback) → `idle`. The frontend polls this at 50ms to animate the face.

## Frontend (`index.html`)

Static HTML/CSS/JS. No build step. Polls `http://127.0.0.1:5050/state` every 50ms.
Animates face CSS class (`idle`, `thinking`, `talking`) and mouth height by volume.
Open directly in a browser — no server needed for the HTML itself.

## Entry Point

`run-bmo.sh` — starts Ollama if not running, ensures `llama3` model is present, then runs
`bmo-brain.py`. Run this to start BMO.

## Known Constraints

- macOS only (`say` command for TTS).
- Requires Ollama running locally with `llama3` model pulled.
- Mic device selection is automatic (first available input device).
- No persistence — BMO has no memory between runs.
- `temp.wav` and `bmo.aiff` are written to the working directory at runtime.
