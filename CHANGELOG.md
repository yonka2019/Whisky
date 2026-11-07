# Changelog

## [v1.4.2] : 2026-11-07
- README: screenshots (recording bar, Dictation, Models).

## [v1.4.1] : 2026-11-07
- Settings shows the app version (bottom-left).

## [v1.4.0] : 2026-11-07
- Language hotkeys: none by default, **+ Add** any language with its own hotkey and model, ✕ to remove.
- Main language: all ~100 Whisper languages (was EN / RU / HE).
- "?" tips: picking a language = better recognition.
- Removed the Hebrew (ivrit-ai) model. Settings using it fall back to Auto / "Same as main". Downloaded files are left in place.
- large-v3-turbo card: "any language" (was "EN / RU / HE").
- Config: unknown language → Auto-detect; a language model without its hotkey is dropped.

## [v1.3.2] : 2026-11-06
----------- ENV CHANGES -------------
- `HF_HUB_DISABLE_SYMLINKS=1` (set by the app at start): store model files as real files, no links.
---------------------------------------
- Fix: model downloads failing on PCs where file links can't be opened.
- Models download to `models\<name>\` as plain files; resumable.
- Older downloads still load; broken ones are fetched again.
- Error + log name the bad file and reason.

## [v1.3.1] : 2026-11-05
- Fix: broken/empty `model.bin` treated as downloaded ("Unable to open file 'model.bin'").
- Loads the exact folder that was checked.

## [v1.3.0] : 2026-11-04
- Model per hotkey (main + EN / RU / HE), default "Same as main".
- ⚠ warning listing models kept loaded + total memory.
- Note: loaded models stay in RAM / GPU while Whisky runs (also in tray).
- New models: large-v3, hebrew-turbo (ivrit-ai). Model cards in Settings.
- Installer shows "Update" over an installed version.
