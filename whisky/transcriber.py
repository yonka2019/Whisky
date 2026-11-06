import gc
import logging
import os
import queue
import re
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, Signal

from .config import MODELS_DIR, MODELS, REPOS, model_dir, repo_dir
from .recorder import RATE

log = logging.getLogger("whisky.stt")


def resolve(choice):
    """Return (model, device, compute_type, label)."""
    import ctranslate2
    has_gpu = False
    try:
        has_gpu = ctranslate2.get_cuda_device_count() > 0
    except Exception:
        pass
    if choice == "auto" or choice not in MODELS:
        model = "large-v3-turbo" if has_gpu else "small"
    else:
        model = choice
    device = "cuda" if has_gpu else "cpu"
    return model, device, _compute_type(device)


def _compute_type(device):
    import ctranslate2
    try:
        supported = ctranslate2.get_supported_compute_types(device)
    except Exception:
        supported = set()
    for ct in (("int8_float16", "int8_float32", "float16", "int8", "float32")
               if device == "cuda" else ("int8", "int8_float32", "float32")):
        if ct in supported:
            return ct
    return "default"


_NET = re.compile(r"Connect|Timeout|Network|Protocol|LocalEntryNotFound|OfflineMode|HfHubHTTP|HTTPError|SSL|Proxy")
_PATH = re.compile(r"[A-Za-z]:[\\/][^'\"]*?([^\\/'\"]+)(?=['\"]|$)")


def _is_network(e):
    seen = set()
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        if isinstance(e, ConnectionError) or any(_NET.search(c.__name__) for c in type(e).__mro__):
            return True
        e = e.__cause__ or e.__context__
    return False


def _short(e):
    if _is_network(e):
        return "Model download failed — check internet, then retry in Settings"
    if "Unable to open file" in str(e):
        return "Can't read model file — Delete it in Settings, then download again"
    msg = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
    msg = _PATH.sub(lambda m: "…\\" + m.group(1), msg)   # drop long folder paths
    return f"{type(e).__name__}: {msg}"[:110]


FILES = ("model.bin", "config.json", "tokenizer.json", "vocabulary.*")


def _readable(p):
    """Real non-empty file (follows links; a broken link = missing) that can be opened."""
    try:
        if not p.is_file() or p.stat().st_size == 0:
            return False
        with open(p, "rb") as f:
            f.read(1)
        return True
    except OSError:
        return False


PATTERNS = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]


def _complete(folder):
    return all(any(_readable(p) for p in folder.glob(f)) for f in FILES)


def _snapshot(model):
    """Usable model folder: plain folder first, then old cache snapshots (newest first); else None."""
    if _complete(model_dir(model)):
        return model_dir(model)
    snaps = sorted(repo_dir(model).glob("snapshots/*"), key=lambda s: s.stat().st_mtime, reverse=True)
    for snap in snaps:
        if _complete(snap):
            return snap
    return None


def _is_downloaded(model):
    return _snapshot(model) is not None


def _why(folder):
    """Why a folder is unusable, e.g. 'model.bin: link -> ../blobs/x, PermissionError' (log + error)."""
    if not folder.is_dir():
        return "folder missing"
    out = []
    for f in FILES:
        hits = list(folder.glob(f))
        if not hits:
            out.append(f"{f}: missing")
            continue
        p = hits[0]
        if _readable(p):
            continue
        d = f"link -> {os.readlink(p)}, " if p.is_symlink() else ""
        try:
            with open(p, "rb") as fh:
                fh.read(1)
            err = f"size {p.stat().st_size}"
        except OSError as e:
            err = f"{type(e).__name__}: {e.strerror or e}"
        out.append(f"{p.name}: {d}{err}")
    return "; ".join(out) or "ok"


def _drop_broken(folder):
    """Remove broken/unopenable links and empty files so the download fetches them again."""
    for p in list(folder.rglob("*")) if folder.is_dir() else []:
        try:
            if (p.is_symlink() and not _readable(p)) or (p.is_file() and p.stat().st_size == 0
                                                          and p.parent.name != "refs" and p.suffix != ".lock"):
                log.warning("removing broken model file %s", p)
                p.unlink()
        except OSError:
            pass


class Transcriber(QObject):
    status = Signal(str, str)        # state, detail  (loading|downloading|ready|error)
    result = Signal(str, str)        # text, language
    test_result = Signal(str, str)   # live-test window result (never pasted)
    failed = Signal(str)             # transcription failed (one pending job done)
    load_failed = Signal(str)        # model load/download failed (old model kept)
    models_changed = Signal()        # a download finished (or failed)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.model = None            # main model
        self.name = ""               # main model name
        self.desc = ""               # e.g. "large-v3-turbo · GPU"
        self.loaded = {}             # name -> (WhisperModel, "GPU"|"CPU"): main + per-language models
        self._q = queue.Queue()
        threading.Thread(target=self._run, daemon=True).start()

    # --- public (any thread) ---
    def load(self):
        self._q.put(("load", None))

    def submit(self, audio, lang=None):
        """lang: force language (per-language hotkey); None = Settings language."""
        self._q.put(("stt", (audio, lang)))

    def submit_test(self, audio):
        self._q.put(("test", audio))

    def download(self, name):
        self._q.put(("fetch", name))

    def sync(self):
        """Load/unload per-language models after a Settings change."""
        self._q.put(("sync", None))

    def loaded_desc(self):
        return {n: d for n, (_, d) in list(self.loaded.items())}

    # --- worker ---
    def _run(self):
        while True:
            kind, payload = self._q.get()
            try:
                if kind == "load":
                    try:
                        self._load()
                    except Exception as e:
                        log.exception("model load failed")
                        self.load_failed.emit(_short(e))
                elif kind == "fetch":
                    try:
                        self._fetch(payload)
                        if self.model is None:
                            self._load()    # nothing loaded yet (e.g. earlier failure): retry
                        else:
                            self.status.emit("ready", self.desc)
                    except Exception as e:
                        log.exception("download failed")
                        self.load_failed.emit(_short(e))
                    self.models_changed.emit()
                elif kind == "sync":
                    if self.model is not None:
                        self._sync()
                elif kind == "stt":
                    self._transcribe(*payload)
                elif kind == "test":
                    try:
                        self._transcribe(payload, test=True)
                    except Exception:
                        log.exception("live test failed")
                        self.test_result.emit("", "")
            except Exception as e:
                log.exception("worker error")
                self.failed.emit(_short(e))

    def _fetch(self, name):
        """Model folder path; downloads if missing (errors propagate, no CPU fallback)."""
        from huggingface_hub import snapshot_download
        snap = _snapshot(name)
        if snap:
            self.status.emit("loading", name)
            return str(snap)         # load exactly the folder that was checked
        dest = model_dir(name)
        if dest.is_dir():
            log.warning("model %s files unusable, fetching again: %s", name, _why(dest))
        dest.mkdir(parents=True, exist_ok=True)
        _drop_broken(dest)
        self.status.emit("downloading", name)
        for attempt in range(4):   # partial files resume on retry
            try:
                snapshot_download(REPOS[name], local_dir=str(dest), allow_patterns=PATTERNS,
                                  cache_dir=str(MODELS_DIR / ".hf"))   # real files, no links
                break
            except Exception as e:
                if attempt == 3 or not (_is_network(e) or isinstance(e, OSError)):
                    raise
                log.warning("download %s attempt %d failed: %s — retrying", name, attempt + 1, e)
                time.sleep(3 * (attempt + 1))
        if not _complete(dest):
            why = _why(dest)
            log.error("model %s unusable after download: %s", name, why)
            raise RuntimeError(f"Model files unreadable ({why[:60]}) — see whisky.log")
        log.info("model %s downloaded to %s", name, dest)
        return str(dest)

    def _build(self, name, cpu_alt=None):
        """(name, model, 'GPU'|'CPU'); cached. GPU failure (e.g. out of memory) -> CPU (or cpu_alt model)."""
        if name in self.loaded:
            return name, *self.loaded[name]
        from faster_whisper import WhisperModel
        _, device, ct = resolve(name)
        path = self._fetch(name)
        try:
            m = WhisperModel(path, device=device, compute_type=ct)
            list(m.transcribe(np.zeros(RATE, np.float32), beam_size=1, language="en")[0])  # warm-up / GPU check
        except Exception:
            if device != "cuda":
                raise
            log.exception("GPU init failed for %s, falling back to CPU", name)
            if cpu_alt and cpu_alt != name:
                return self._build_cpu(cpu_alt)
            return self._build_cpu(name, path)
        dev = "GPU" if device == "cuda" else "CPU"
        self.loaded[name] = (m, dev)
        log.info("model ready: %s · %s (%s)", name, dev, ct)
        return name, m, dev

    def _build_cpu(self, name, path=None):
        from faster_whisper import WhisperModel
        if name in self.loaded:
            return name, *self.loaded[name]
        path = path or self._fetch(name)
        m = WhisperModel(path, device="cpu", compute_type=_compute_type("cpu"))
        self.loaded[name] = (m, "CPU")
        log.info("model ready: %s · CPU", name)
        return name, m, "CPU"

    def _load(self):
        name = resolve(self.cfg["model"])[0]
        name, m, dev = self._build(name, cpu_alt="small" if self.cfg["model"] == "auto" else None)
        self.model, self.name = m, name   # swap only on success
        self.desc = f"{name} · {dev}"
        self.status.emit("ready", self.desc)
        self._sync()

    def _wanted(self):
        want = {self.name}
        lk = self.cfg.get("lang_hotkeys") or {}
        for lang, m in (self.cfg.get("lang_models") or {}).items():
            if m and lk.get(lang):
                want.add(resolve(m)[0])
        return want

    def _sync(self):
        want = self._wanted()
        for n in list(self.loaded):
            if n not in want:
                del self.loaded[n]
                log.info("unloaded %s", n)
        gc.collect()
        for n in sorted(want - set(self.loaded)):
            if not _is_downloaded(n):
                log.warning("language model %s not downloaded, skipped", n)
                continue
            try:
                self._build(n)
            except Exception as e:
                log.exception("language model %s failed", n)
                self.load_failed.emit(f"{n}: {_short(e)}")
        self.models_changed.emit()
        self.status.emit("ready", self.desc)

    def model_for(self, lang):
        """Model used for a hotkey's language tag (None/'' = main)."""
        m = (self.cfg.get("lang_models") or {}).get(lang) if lang else None
        if m:
            n = resolve(m)[0]
            if n in self.loaded:
                return self.loaded[n][0]
        return self.model

    def _transcribe(self, audio, lang=None, test=False):
        out = self.test_result if test else self.result
        if self.model is None:
            self._load()
        if len(audio) < RATE * 0.25 or float(np.abs(audio).max(initial=0)) < 0.01:
            out.emit("", "")
            return
        if lang:
            self._emit_stt(out, audio, lang, self.model_for(lang))
            return
        lang = self.cfg.get("language") or "auto"
        lang = None if lang == "auto" else lang
        allowed = [l for l in (self.cfg.get("languages") or []) if l]
        if lang is None and allowed:
            try:
                _, _, probs = self.model.detect_language(audio)  # main model
                probs = dict(probs)
                lang = max(allowed, key=lambda l: probs.get(l, 0.0))
            except Exception:
                log.exception("detect_language failed")
        self._emit_stt(out, audio, lang, self.model)

    def _emit_stt(self, out, audio, lang, model):
        segs, info = model.transcribe(
            audio, language=lang, beam_size=int(self.cfg.get("beam_size", 5)),
            vad_filter=True, condition_on_previous_text=False)
        text = "".join(s.text for s in segs).strip()
        log.info("[%s %.2f] %d chars", info.language, info.language_probability, len(text))
        out.emit(text, info.language or lang or "")
