## Environment Variables

Create a `.env` file in the project root with your credentials:

```
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
```

Never commit real secrets. Use environment variables or a `.env` file that is excluded from git.
## Voca

Python voice interaction app: local Coqui STT/TTS for speech, OpenAI GPT-4o for reasoning, WebRTC stubs for SIP call audio, and a Tkinter GUI.

### Features
- Local STT (Coqui STT) and TTS (Coqui TTS)
  - If Coqui STT is unavailable on your Python version, Vosk is used automatically.
- Remote LLM via OpenAI GPT-4o (API key required)
- WebRTC (aiortc) audio pipeline stubs for SIP integration
- Tkinter GUI with API key input, call controls, and logs
- Optional voice-based system control (cursor, open apps) via LLM tool-calling

### Quickstart
1) Install Python 3.10+

2) Create venv and install deps
```bash
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: . .venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

3) Create .env
```bash
copy .env.example .env
# Edit .env to add your OpenAI API key
```

4) Download Coqui models (examples)
- STT (English): download a Coqui STT model and scorer, e.g.,:
  - Model (tflite/onnx): place in `models/stt/model.tflite` (or `.onnx`)
  - Scorer/Language model: place in `models/stt/kenlm.scorer` (optional)
- TTS (English): download a Coqui TTS model
  - Example: `tts_models/en/ljspeech/tacotron2-DDC` (auto-downloaded by TTS on first run)

If Coqui STT install fails on your platform (e.g., Python 3.11 on Windows), Vosk fallback is enabled:
- Download a Vosk English model and unpack to `models/vosk/en-us`.
  - Example (small): `vosk-model-small-en-us-0.15`
  - Example (large): `vosk-model-en-us-0.22`
  - Set `VOCA_VOSK_MODEL_DIR` if you use a different folder.

Update paths in `src/voca/config.py` or via environment variables.

5) Run GUI
```bash
python -m src.main
```

### Environment
See `.env.example` for available variables. Only OpenAI API uses a key.

### Notes
- WebRTC/SIP: This repo includes aiortc-based stubs to connect to a remote audio track. Integrate with Asterisk/FreeSWITCH (e.g., via sip-js/gateway) as needed.
- Security: Keep only `GPT4ALL_API_KEY` in `.env`. Do not commit it. Consider OS keychain or file ACLs for additional protection.

### Troubleshooting
- If Coqui STT fails to load, confirm model file paths and CPU/GPU compatibility.
- On Windows, install build tools if `aiortc` requires them. See project docs.


