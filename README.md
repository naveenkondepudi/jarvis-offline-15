# Jarvis Offline v15 (Speech-to-Speech, Windows)

**Offline STT** using `faster-whisper` (Whisper via CTranslate2) and **offline TTS** using `pyttsx3`.

## What it can do (safe, whitelisted actions)
- Push-to-talk on a hotkey
- Understand a command in (many) languages (model-based STT)
- Reply using offline TTS
- Supported commands:
  - `open chrome`, `open edge`, `open notepad`, `open calculator`, `open command prompt`
  - `search cats` / `search for cats` (opens browser to Google search)
  - `volume up` / `volume down` / `mute` / `unmute`
  - `what time`, `what date`
  - `stop` / `exit`
  - `fix the errors and problem itself`
## Speed notes (important)
- Uses a **short fixed recording window** (5 seconds) for speed.
- For even faster responses: change `listen_once()` in `jarvis.py` from `seconds=5.0` to `3.0` or `2.0`.
- Choose a smaller model in `config.json` (e.g. `small`, `medium`).

## Windows setup
### 1) Create venv
From `C:/Users/navee/Desktop/jarvis-offline-15/`:
```bat
python -m venv .venv
.
\.venv\Scripts\activate
```

### 2) Install dependencies
```bat
pip install -r requirements.txt
```

### 3) (First run) Download the Whisper model
When you run the app, Whisper will download the selected model automatically.

### 4) Run
```bat
python jarvis.py
```

## Hotkey
Edit `config.json`:
```json
"hotkey": {"push_to_talk_key": "ctrl+shift+v"}
```

## Build to EXE (optional)
```bat
pip install pyinstaller
pyinstaller --onefile --noconsole jarvis.py
```

Outputs will be in `dist/`.

