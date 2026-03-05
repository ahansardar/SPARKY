# SPARKY

<p align="center">
  <img src="https://github.com/user-attachments/assets/3060d7b1-1781-410d-bc79-265e280a42de" alt="SPARKY Logo" width="220" />
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT" /></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-blue" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/Platform-Windows-informational" alt="Platform Windows" />
  <img src="https://img.shields.io/badge/LLM-Ollama-black" alt="LLM Ollama" />
</p>
<p align="center">
  <img src="https://img.shields.io/badge/Wake%20Word-OpenWakeWord-orange" alt="Wake Word OpenWakeWord" />
  <img src="https://img.shields.io/badge/TTS-Piper-ff69b4" alt="TTS Piper" />
  <img src="https://img.shields.io/badge/STT-SpeechRecognition-yellow" alt="STT SpeechRecognition" />
  <img src="https://img.shields.io/badge/UI-Tkinter-9cf" alt="UI Tkinter" />
</p>

Desktop AI assistant for local automation, voice interaction, and tool execution.
**SPARKY** stands for **Smart Personal Assistant for Real-time Knowledge and Productivity**.

Created by **Ahan Sardar**.

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Requirements](#requirements)
- [System Requirements](#system-requirements)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Supported Commands](#supported-commands)
- [Models and Assets](#models-and-assets)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [Roadmap](#roadmap)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Safety Notice](#safety-notice)
- [License](#license)

## Features

- Chat and reasoning via **Ollama** (`llama3:8b`)
- Natural-language action execution (apps, browser, files, system tasks)
- Wake word support with **OpenWakeWord** (`hey_sparky`)
- Voice input via microphone + SpeechRecognition
- Voice output via **Piper TTS**
- Vision-enabled actions (uses `llava:7b` when needed)[Still under development]
- Animated Tkinter desktop UI
- User memory read/update support

## Tech Stack

- Python 3.11+
- Ollama
- Tkinter + Pillow
- PyAudio + SpeechRecognition
- OpenWakeWord
- FFmpeg (bundled build included in this repo)
- Piper runtime (`piper/`) with local voice model (`models/`)

## Requirements

- Windows (recommended; automation coverage is strongest on Windows)
- Python 3.11 or newer
- Ollama installed and running
- Microphone and speakers
- FFmpeg available (repo includes `ffmpeg-8.0.1-essentials_build/`)

## System Requirements

Minimum:

- OS: Windows 10/11 (64-bit)
- CPU: 4-core processor (Intel i5 8th gen / Ryzen 5 equivalent)
- RAM: 8 GB
- Storage: 15 GB free space
- GPU: Not required
- Network: Stable internet for first-time Ollama/model download

Recommended:

- OS: Windows 11 (64-bit)
- CPU: 6+ cores (Intel i7 / Ryzen 7 or better)
- RAM: 16 GB or more
- Storage: 30 GB+ free SSD space
- GPU: Optional (helps with some model/vision workloads)
- Audio: Good quality mic + speakers/headset

## Quick Start

1. Clone the repo and move into the project directory.
2. Create and activate virtual environment.

```powershell
python -m venv venv
venv\Scripts\activate
```

3. Install dependencies.

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install
```

4. Pull required Ollama models.

```powershell
ollama pull llama3:8b
ollama pull llava:7b
```

5. Run SPARKY.

```powershell
python src/ai_agent.py
```

## Usage

- Type in the input box and press `Enter` or click `SEND`.
- Click `MIC` to capture voice input.
- Say **"Hey Sparky"** for wake-word activation.
- Type `info` in chat to view supported command examples.

Note: Slash action format (`/action ...`) is disabled in the current app flow. Use natural language commands.

## Supported Commands

Examples you can type directly:

- `open youtube.com`
- `open calculator`
- `play <song or video name>`
- `pause` / `resume` / `stop song`
- `search <topic>`
- `weather now`
- `weather in <city>`
- `volume up` / `volume down` / `mute` / `set volume to 45`
- `brightness up` / `brightness down`
- `remind me to <task> at HH:MM on YYYY-MM-DD`
- `remember <fact>`
- `show my memory`
- `quit`

## Models and Assets

- Required LLM: `llama3:8b`
- Vision model (for screen/camera features): `llava:7b`
- Wake word model: `models/hey_sparky.onnx` (and/or `.tflite`)
- TTS model: `models/en_US-lessac-medium.onnx`
- Piper binary: `piper/piper.exe`
- FFmpeg binaries: `ffmpeg-8.0.1-essentials_build/bin/`

## Environment Variables

- `SPARKY_STT_CACHE`  
  Optional cache path for model/artifact downloads used by runtime dependencies.

- `SPARKY_ACTIONS_DIR`  
  Optional custom actions folder (defaults to project `actions/`).

- `SPARKY_OWW_MODEL`  
  OpenWakeWord model name fallback (default: `hey_sparky`).

- `SPARKY_WAKEWORD_THRESHOLD`  
  Wake-word detection threshold (default in code: `0.30`).

- `SPARKY_OWW_ANY_THRESHOLD`  
  Backup detector threshold (default in code: `0.55`).

- `SPARKY_WAKE_RMS_THRESHOLD`  
  Minimum input energy for wake pipeline (default in code: `80`).

## Project Structure

```text
SPARKY/
  actions/         Action modules
  agent/           Planner/executor/task queue components
  assets/          UI assets (logo, text image, icons)
  config/          Model config
  memory/          Memory management
  models/          Wake-word and TTS model files
  piper/           Piper runtime binaries
  src/             Main app, bridge, voice IO, LLM clients
  ui.py            Desktop UI
  requirements.txt
```

## Roadmap

- Bundled one-click installers with smoother dependency setup flow
- UI/UX upgrade for cleaner interaction, better feedback, and accessibility
- Performance optimization for faster startup and lower memory usage
- Better cross-platform automation support (Linux/macOS parity)
- Better onboarding setup checks on first launch
- Improved logging/export for debugging sessions
- Additional wake-word and voice profiles
- Background detection pipeline for always-on wake monitoring
- More productivity actions and advanced automation workflows in future updates

## Troubleshooting

- Chat not responding:
  - Make sure Ollama is running.
  - Verify `llama3:8b` is pulled.

- Vision actions fail:
  - Pull `llava:7b` with `ollama pull llava:7b`.

- No microphone input:
  - Check OS microphone permissions.
  - Verify PyAudio installation matches your Python build.

- TTS issues:
  - Confirm `piper/piper.exe` exists.
  - Confirm `models/en_US-lessac-medium.onnx` exists.

- Media/YouTube audio issues:
  - Confirm FFmpeg exists at `ffmpeg-8.0.1-essentials_build/bin/ffmpeg.exe`.
  - Optionally add that `bin` folder to your system `PATH`.

- If none of the above contact me at ahansardarvis@gmail.com

## Contributing

Contributions are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Make your changes with clear commit messages.
4. Run basic checks before opening a PR.
5. Open a pull request with a short summary and testing notes.

## Safety Notice

Some actions can control keyboard/mouse, open apps/websites, and modify files. Use carefully on machines with important data.

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE).

This project also depends on third-party tools/models (including FFmpeg and Ollama models).  
Review their respective licenses before redistribution or commercial use.
