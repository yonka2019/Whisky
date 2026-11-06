"""Make NVIDIA pip-wheel DLLs (cuBLAS, cuDNN, NVRTC) loadable by CTranslate2."""
import os
import site
import sys
from pathlib import Path

from .config import base_dir


def _candidate_roots():
    roots = [base_dir()]
    if not getattr(sys, "frozen", False):
        roots += [Path(p) for p in site.getsitepackages()]
    return roots


def setup():
    found = []
    for root in _candidate_roots():
        nv = root / "nvidia"
        if not nv.is_dir():
            continue
        for bin_dir in nv.glob("*/bin"):
            found.append(str(bin_dir))
    for d in found:
        try:
            os.add_dll_directory(d)
        except OSError:
            pass
    if found:
        os.environ["PATH"] = os.pathsep.join(found) + os.pathsep + os.environ.get("PATH", "")
    return found
