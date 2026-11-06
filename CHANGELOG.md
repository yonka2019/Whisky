# Changelog

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
