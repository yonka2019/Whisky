import json
import logging
import os
import sys
from pathlib import Path

APP_NAME = "Whisky"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
MODELS_DIR = DATA_DIR / "models"
CONFIG_PATH = DATA_DIR / "config.json"
LOG_PATH = DATA_DIR / "whisky.log"

MODELS = ["small", "medium", "large-v3-turbo", "large-v3"]
REPOS = {  # Hugging Face repos (faster-whisper / CTranslate2 format)
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "large-v3": "Systran/faster-whisper-large-v3",
}


def repo_dir(model):
    """Old Hugging Face cache layout (≤1.3.1, read-only fallback)."""
    return MODELS_DIR / ("models--" + REPOS[model].replace("/", "--"))


def model_dir(model):
    """Plain folder with real files (no links), e.g. models/small."""
    return MODELS_DIR / model

DEFAULTS = {
    "model": "auto",          # auto | small | medium | large-v3-turbo
    "hotkey": [163],          # virtual-key codes held together; 163 = Right Ctrl
    "lang_hotkeys": {},       # optional per-language hotkeys, e.g. {"he": [162, 72]} -> forces Hebrew
    "lang_models": {},        # model per language hotkey, e.g. {"he": "small"}; missing = same as main
    "min_hold_ms": 300,       # shorter taps are ignored
    "language": "auto",       # auto | en | ru | he | ...
    "languages": [],          # limit auto-detect, e.g. ["en","ru","he"]; empty = any
    "mic": None,              # input device name; None = system default
    "beam_size": 5,
    "append_space": True,     # trailing space so consecutive dictations don't glue
    "restore_clipboard": True,
}


def load():
    cfg = dict(DEFAULTS)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        for k, v in data.items():
            if k == "hotkey":
                from .keys import parse
                cfg[k] = parse(v)
                continue
            if k == "model" and v not in ["auto"] + MODELS:   # e.g. removed hebrew-turbo
                continue
            if k == "lang_models":
                if isinstance(v, dict):
                    cfg[k] = {l: m for l, m in v.items() if m in ["auto"] + MODELS}
                continue
            if k == "lang_hotkeys":
                if isinstance(v, dict):
                    from .langs import NAMES
                    lk = {l: [int(x) for x in ks if isinstance(x, int) and 0 < x < 256]
                          for l, ks in v.items() if l in NAMES and isinstance(ks, list)}
                    cfg[k] = {l: ks for l, ks in lk.items() if ks}       # drop entries left empty
                continue
            if k == "language":
                from .langs import NAMES
                if v != "auto" and v not in NAMES:                       # unknown code -> auto-detect
                    logging.getLogger("whisky.cfg").warning("config language %r unknown, using auto", v)
                    continue
            d = DEFAULTS.get(k)
            if k in DEFAULTS and d is not None and not isinstance(v, type(d)):
                logging.getLogger("whisky.cfg").warning("config %s: bad type %r, using default", k, v)
                continue
            cfg[k] = v
        # a language model without its hotkey is stale (old "Clear" kept it)
        cfg["lang_models"] = {l: m for l, m in cfg["lang_models"].items() if l in cfg["lang_hotkeys"]}
    except FileNotFoundError:
        save(cfg)
    except Exception:
        logging.getLogger("whisky.cfg").exception("config.json unreadable, using defaults")
    return cfg


def save(cfg):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def base_dir():
    """Folder with bundled files (PyInstaller) or project root (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent
