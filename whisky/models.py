"""Downloaded-model info and deletion (models/<name> folders; old HF cache read too)."""
import logging

from .config import MODELS, MODELS_DIR, REPOS, model_dir, repo_dir

log = logging.getLogger("whisky.models")
APPROX_MB = {"small": 484, "medium": 1530, "large-v3-turbo": 1620, "large-v3": 3090, "hebrew-turbo": 1620}
# avg memory while loaded, whole app, int8: (RAM MB, VRAM MB). Measured on GTX 1050 Ti except ESTIMATED.
USAGE_MB = {
    "small":          {"gpu": (420, 380),  "cpu": (430, 0)},
    "medium":         {"gpu": (420, 1050), "cpu": (1000, 0)},
    "large-v3-turbo": {"gpu": (420, 1120), "cpu": (1020, 0)},
    "large-v3":       {"gpu": (420, 1900), "cpu": (1900, 0)},
    "hebrew-turbo":   {"gpu": (420, 1120), "cpu": (1020, 0)},
}
ESTIMATED = {"medium", "large-v3", "hebrew-turbo"}
_gpu = None


def has_gpu():
    global _gpu
    if _gpu is None:
        try:
            import ctranslate2
            _gpu = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            _gpu = False
    return _gpu


def usage(model):
    """e.g. 'RAM 0.4 · GPU 1.1 GB' (device the app would use)."""
    gpu = has_gpu()
    ram, vram = USAGE_MB[model]["gpu" if gpu else "cpu"]
    est = "≈" if model in ESTIMATED else ""
    return f"RAM {ram / 1000:.1f} · GPU {est}{vram / 1000:.1f} GB" if gpu else f"RAM {est}{ram / 1000:.1f} GB"


def info():
    """{model: size_mb or None if not downloaded}"""
    from .transcriber import _snapshot
    res = {}
    for m in MODELS:
        try:
            snap = _snapshot(m)
            res[m] = round(sum(f.stat().st_size for f in snap.iterdir() if f.is_file()) / 1e6) if snap else None
        except OSError:
            res[m] = APPROX_MB[m]
    return res


def delete(model):
    import shutil
    shutil.rmtree(model_dir(model), ignore_errors=True)
    old = repo_dir(model)        # old cache layout (≤1.3.1)
    if old.is_dir():
        try:
            from huggingface_hub import scan_cache_dir
            cache = scan_cache_dir(str(MODELS_DIR))
            hashes = [rv.commit_hash for r in cache.repos if r.repo_id == REPOS[model] for rv in r.revisions]
            if hashes:
                cache.delete_revisions(*hashes).execute()
        except Exception:
            log.exception("old cache delete")
        shutil.rmtree(old, ignore_errors=True)
    log.info("deleted %s", model)


def auto_model():
    """What 'auto' resolves to on this PC."""
    return "large-v3-turbo" if has_gpu() else "small"


# card text for Settings: (title, description, good for, speed 1-4, accuracy 1-4)
CARDS = {
    "auto": ("Auto", "Picks for this PC: large-v3-turbo with an NVIDIA GPU, else small.",
             "Most people — no tuning needed.", 0, 0),
    "small": ("Small", "Fastest and lightest. OK accuracy.",
              "Quick chat replies, short notes, PCs without a GPU.", 4, 2),
    "medium": ("Medium", "Mid-size, older generation. Slower than turbo.",
               "CPU-only PCs that need more than Small.", 2, 3),
    "large-v3-turbo": ("Large v3 Turbo", "Near-best accuracy, fast on GPU.",
                       "Everyday dictation in EN / RU / HE — emails, docs, messages.", 3, 3),
    "large-v3": ("Large v3", "Most accurate, slowest. Needs a strong GPU.",
                 "Long texts, names and terms, noisy rooms.", 1, 4),
    "hebrew-turbo": ("Hebrew · ivrit-ai", "Turbo tuned on Hebrew speech. Weaker in English and Russian.",
                     "Mostly-Hebrew dictation — WhatsApp, emails, documents.", 3, 4),
}


def resolve_name(choice):
    return auto_model() if choice not in MODELS else choice


def planned(cfg):
    """Models kept loaded: main + models of language hotkeys that are set (ordered, unique)."""
    out = [resolve_name(cfg["model"])]
    lk = cfg.get("lang_hotkeys") or {}
    for lang in ("en", "ru", "he"):
        m = (cfg.get("lang_models") or {}).get(lang)
        if m and lk.get(lang) and resolve_name(m) not in out:
            out.append(resolve_name(m))
    return out


def total_usage(names):
    """Approx. combined memory, e.g. 'RAM 0.4 · GPU 2.2 GB' (one app process)."""
    gpu = has_gpu()
    ram = 420 + sum(USAGE_MB[n]["gpu" if gpu else "cpu"][0] - 420 for n in names)
    vram = sum(USAGE_MB[n]["gpu"][1] for n in names) if gpu else 0
    return f"RAM {ram / 1000:.1f} · GPU {vram / 1000:.1f} GB" if gpu else f"RAM {ram / 1000:.1f} GB"
