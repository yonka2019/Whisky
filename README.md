# Whisky

Hold-to-talk dictation for Windows. Local Whisper, EN / RU / HE (auto-detect).

## Use
- Hold **Right Ctrl** (default) → speak → release → text is pasted into the focused app.
- Taps under 0.3s and hotkey + other key (e.g. RCtrl+C) are ignored.
- Max 3 min per recording. Audio is transcribed after you release the key.
- Optional per-language hotkeys (English / Русский / עברית) force that language.
- Each hotkey can use its own model (default: same as main). Every assigned model stays loaded while Whisky runs — Settings shows ⚠ with the list and total memory.
- Tray → **Settings…**: hotkeys, language, models (select / download % / delete), microphone, **Live test** (listens, writes each phrase, never pastes), start with Windows, paste options.

## Install
`installer\Output\Whisky-Setup-1.3.2.exe` → no admin needed. Installs to `%LOCALAPPDATA%\Programs\Whisky`.

Newer setup over an installed one → **Update** (settings and models kept).

First run opens Settings and downloads the model from Hugging Face (≈0.5–1.6 GB).

## Models
Settings → **Models**: one card per model (what it's good for, speed, accuracy, disk, memory). Download → Select.

| Model | Good for | Disk | Avg memory (GPU) | Avg memory (CPU) |
|---|---|---|---|---|
| Auto | NVIDIA GPU → large-v3-turbo, else small | | | |
| small | quick notes, PCs without GPU | 0.5 GB | RAM 0.4 + VRAM 0.4 GB | RAM 0.4 GB |
| medium | CPU-only, more than small | 1.5 GB | RAM 0.4 + VRAM ≈1.1 GB | RAM ≈1.0 GB |
| large-v3-turbo | everyday EN / RU / HE | 1.6 GB | RAM 0.4 + VRAM 1.1 GB | RAM 1.0 GB |
| large-v3 | best accuracy, slowest | 3.1 GB | RAM 0.4 + VRAM ≈1.9 GB | RAM ≈1.9 GB |
| hebrew-turbo ([ivrit-ai](https://huggingface.co/ivrit-ai/whisper-large-v3-turbo-ct2)) | mostly-Hebrew dictation | 1.6 GB | RAM 0.4 + VRAM ≈1.1 GB | RAM ≈1.0 GB |

Loaded models stay in RAM / GPU memory while Whisky runs (also in the tray). ≈ = estimate.

Broken or missing model files → downloaded again automatically.

## Data
`%LOCALAPPDATA%\Whisky` → `config.json`, `models\<name>\` (plain files), `whisky.log`

`config.json` extra keys: `hotkey` (virtual-key codes, e.g. `[163]` = Right Ctrl), `lang_hotkeys` (e.g. `{"he": [162, 72]}` = Left Ctrl + H → Hebrew), `lang_models` (e.g. `{"he": "hebrew-turbo"}`), `min_hold_ms`, `language`, `languages` (limit auto-detect, e.g. `["en","ru","he"]`), `beam_size`, `append_space`, `restore_clipboard`. Restart the app after editing.

## Build
```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
build.bat
```
Needs [Inno Setup 6](https://jrsoftware.org/isdl.php). Dev run: `run.bat`.
