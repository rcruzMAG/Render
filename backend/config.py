"""Load and persist config.json (ComfyUI URL, model filenames, API keys)."""

import json
import threading
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
_lock = threading.Lock()

DEFAULTS = {
    "comfyui_url": "http://127.0.0.1:8188",
    "comfyui_loras_dir": "",
    "host": "127.0.0.1",
    "port": 8500,
    "models": {},
    "providers": {"fal": {"api_key": ""}, "replicate": {"api_token": ""}},
}


def load() -> dict:
    with _lock:
        cfg = dict(DEFAULTS)
        if CONFIG_PATH.exists():
            cfg.update(json.loads(CONFIG_PATH.read_text()))
        return cfg


def save(cfg: dict) -> None:
    with _lock:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def model(name: str) -> str:
    return load().get("models", {}).get(name, name)
