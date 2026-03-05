import json
import sys
from pathlib import Path

def _resolve_config_path() -> Path:
    candidates = []

    # PyInstaller one-file extracts under _MEIPASS; one-folder runs near executable.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "config" / "models.json")

    candidates.append(Path(sys.executable).resolve().parent / "config" / "models.json")
    candidates.append(Path(__file__).resolve().parents[2] / "config" / "models.json")

    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


CONFIG_PATH = _resolve_config_path()
FORCED_MODEL = "llama3:8b"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    _config = json.load(f)

DEFAULT_MODEL = FORCED_MODEL
MODELS = {m["id"]: m for m in _config["models"] if m["id"] == FORCED_MODEL}
