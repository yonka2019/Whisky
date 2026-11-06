# PyInstaller spec: one-dir windowed build -> dist\Whisky\Whisky.exe
import site
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

sp = Path([p for p in site.getsitepackages() if p.endswith("site-packages")][0])
NV = {  # only DLLs CTranslate2 actually loads for Whisper inference
    "cublas": ["cublas64_12.dll", "cublasLt64_12.dll"],
    "cudnn": ["cudnn64_9.dll"],
}
binaries = [(str(sp / "nvidia" / pkg / "bin" / f), f"nvidia/{pkg}/bin") for pkg, fs in NV.items() for f in fs]
binaries += collect_dynamic_libs("ctranslate2") + collect_dynamic_libs("onnxruntime")
datas = collect_data_files("faster_whisper")

a = Analysis(
    ["main.py"],
    binaries=binaries,
    datas=datas,
    hiddenimports=["pynput.keyboard._win32", "pynput.mouse._win32"],
    excludes=["tkinter", "matplotlib", "IPython", "PySide6.QtWebEngineCore", "PySide6.QtQml",
              "PySide6.QtQuick", "PySide6.QtPdf", "PySide6.Qt3DCore", "PySide6.QtMultimedia"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Whisky", console=False,
          icon="assets/whisky.ico", version="version_info.txt", upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Whisky", upx=False)
