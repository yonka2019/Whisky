"""Settings window (tabs): Dictation (hotkeys, language, mic, live test) · Models (cards) · General."""
from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog,
                               QLabel, QMessageBox, QPushButton, QScrollArea, QTabWidget, QToolButton, QToolTip,
                               QVBoxLayout, QWidget)

from . import autostart
from . import config as C
from . import keys as K
from . import models as M
from .livetest import LiveTest
from .langs import NAMES, TOP, choices as lang_choices
from .recorder import input_devices

LANG_HELP = ("Pick your language for better recognition — the model doesn't have to guess.\n"
             "Auto-detect works for any language but can misread short phrases.")
KEYS_HELP = ("Extra hotkeys that force a language, for better recognition when you switch languages.\n"
             "E.g. Left Ctrl + H → Hebrew. Each can use its own model.")
HINT = "Hold to talk. Language hotkeys force that language."
MUTED = "color: palette(placeholder-text);"
LOADED_NOTE = "While Whisky runs (also in the tray), its models stay loaded in RAM and GPU memory."
WARN = "color: #b26a00;"
CARD_CSS = """
QFrame#card { border: 1px solid palette(mid); border-radius: 8px; background: palette(base); }
QFrame#card[chosen="true"] { border: 2px solid palette(highlight); }
QLabel#title { font-size: 11pt; font-weight: 600; }
QLabel#chip { border-radius: 8px; padding: 1px 8px; background: palette(highlight); color: palette(highlighted-text);
              font-size: 8pt; font-weight: 600; }
"""


def _mb(mb):
    return f"{mb / 1000:.1f} GB" if mb >= 1000 else f"{mb} MB"


def _dots(n):
    return "●" * n + "○" * (4 - n)


def lang_name(code):
    return dict(TOP).get(code) or NAMES.get(code, code)


def _help(text):
    """Small round '?' — hover or click shows the tip."""
    b = QToolButton(text="?")
    b.setToolTip(text)
    b.setAccessibleName("Help")
    b.setAccessibleDescription(text)
    b.setFixedSize(20, 20)
    b.setCursor(Qt.WhatsThisCursor)
    b.setStyleSheet("QToolButton { border: 1px solid palette(mid); border-radius: 10px; font-weight: 600;"
                    " color: palette(placeholder-text); }")
    b.clicked.connect(lambda: QToolTip.showText(b.mapToGlobal(QPoint(0, b.height())), text, b))
    return b


def _caption(text, help_text=None):
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(6)
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignAbsolute | Qt.AlignLeft | Qt.AlignVCenter)   # Hebrew text would align right
    h.addWidget(lbl)
    if help_text:
        h.addWidget(_help(help_text))
    h.addStretch(1)
    return w


class SettingsWindow(QWidget):
    def __init__(self, cfg, hk, stt, on_model, on_hotkey, state_text, progress, icon=None):
        super().__init__()
        self.cfg, self.hk, self.stt = cfg, hk, stt
        self.on_model, self.on_hotkey = on_model, on_hotkey
        self.state_text, self.progress = state_text, progress
        self.setWindowTitle("Whisky Settings")
        if icon:
            self.setWindowIcon(icon)
        self.setStyleSheet(CARD_CSS)
        self.resize(780, 660)
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # ================= Dictation tab =================
        page = QWidget()
        pv = QVBoxLayout(page)
        g = QGroupBox("Hotkeys")
        gv = QVBoxLayout(g)
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        gv.addLayout(grid)
        self.grid = grid
        self.keys, self.slot_models, self.lang_rows = {}, {}, {}
        self.pending = None              # language being added (waiting for its hotkey)
        hdr = QLabel("Model")
        hdr.setStyleSheet(MUTED)
        grid.addWidget(hdr, 0, 4)
        main_cap = _caption("Main hotkey")
        main_cap.setMinimumWidth(130)
        grid.addWidget(main_cap, 1, 0)
        self._key_row("", 1)
        self.lang = QComboBox()
        for i, (code, label) in enumerate(lang_choices()):
            self.lang.addItem(label, code)
            if i == 3:
                self.lang.insertSeparator(4)
        self.lang.setMaxVisibleItems(15)
        self.lang.setCurrentIndex(max(0, self.lang.findData(cfg["language"])))
        self.lang.currentIndexChanged.connect(lambda _: self._save("language", self.lang.currentData()))
        grid.addWidget(_caption("Main language", LANG_HELP), 2, 0)
        grid.addWidget(self.lang, 2, 1, 1, 4)
        sep = QFrame(frameShape=QFrame.HLine)
        sep.setStyleSheet("color: palette(mid);")
        grid.addWidget(sep, 3, 0, 1, 5)
        head = QHBoxLayout()
        title = QLabel("Language hotkeys")
        title.setStyleSheet("font-weight:600;")
        head.addWidget(title)
        head.addWidget(_help(KEYS_HELP))
        self.lang_empty = QLabel("None — the main hotkey only.")
        self.lang_empty.setStyleSheet(MUTED)
        head.addWidget(self.lang_empty)
        head.addStretch(1)
        self.add_btn = QPushButton("+ Add")
        self.add_btn.setToolTip("Add a hotkey that forces a language")
        self.add_btn.clicked.connect(lambda _=False: self._add_lang())
        head.addWidget(self.add_btn)
        grid.addLayout(head, 4, 0, 1, 5)
        self.lang_row0 = 5               # language hotkey rows start here (same grid -> aligned columns)
        self.key_hint = QLabel(HINT)
        self.key_hint.setStyleSheet(MUTED)
        gv.addWidget(self.key_hint)
        pv.addWidget(g)
        self.multi_warn = QLabel()
        self.multi_warn.setWordWrap(True)
        self.multi_warn.setStyleSheet(WARN)
        pv.addWidget(self.multi_warn)
        self.loaded_note = QLabel()
        self.loaded_note.setWordWrap(True)
        self.loaded_note.setStyleSheet(MUTED)
        pv.addWidget(self.loaded_note)

        g = QGroupBox("Microphone")
        h = QHBoxLayout(g)
        self.mic = QComboBox()
        self.mic.currentIndexChanged.connect(self._mic_changed)
        self.live_btn = QPushButton("Live test…")
        self.live_btn.setToolTip("Listens while open and writes what you say. Nothing is pasted.")
        h.addWidget(self.mic, 1)
        h.addWidget(self.live_btn)
        pv.addWidget(g)
        pv.addStretch(1)
        self.tabs.addTab(page, "Dictation")
        self.live = LiveTest(cfg, stt, icon)
        self.live_btn.clicked.connect(self.live.open_window)

        # ================= Models tab =================
        page = QWidget()
        pv = QVBoxLayout(page)
        self.status = QLabel()
        self.status.setStyleSheet(MUTED)
        pv.addWidget(self.status)
        inner = QWidget()
        cards = QVBoxLayout(inner)
        cards.setSpacing(8)
        cards.setContentsMargins(0, 0, 4, 0)
        self.rows, self.cards = {}, {}
        for m in ["auto"] + C.MODELS:
            cards.addWidget(self._card(m))
        cards.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(inner)
        pv.addWidget(scroll, 1)
        self.multi_warn2 = QLabel()
        self.multi_warn2.setWordWrap(True)
        self.multi_warn2.setStyleSheet(WARN)
        pv.addWidget(self.multi_warn2)
        self.loaded_note2 = QLabel()
        self.loaded_note2.setWordWrap(True)
        self.loaded_note2.setStyleSheet(MUTED)
        pv.addWidget(self.loaded_note2)
        note = QLabel("Memory = average while loaded · ≈ = estimate. Model per hotkey: Dictation tab.")
        note.setStyleSheet(MUTED)
        pv.addWidget(note)
        self.tabs.addTab(page, "Models")

        # ================= General tab =================
        page = QWidget()
        pv = QVBoxLayout(page)
        self.auto = QCheckBox("Start with Windows")
        self.auto.toggled.connect(autostart.set_enabled)
        self.space = QCheckBox("Add space after text")
        self.space.toggled.connect(lambda on: self._save("append_space", on))
        self.restore = QCheckBox("Restore clipboard after paste")
        self.restore.toggled.connect(lambda on: self._save("restore_clipboard", on))
        restore_hint = QLabel("Puts back what you had copied before dictating.")
        restore_hint.setStyleSheet(MUTED + " margin-left: 22px;")
        for w in (self.auto, self.space, self.restore, restore_hint):
            pv.addWidget(w)
        pv.addStretch(1)
        self.tabs.addTab(page, "General")

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        bottom.addWidget(close)
        root.addLayout(bottom)

        self.cap_slot = None
        self._dl = None
        hk.captured.connect(self._captured)
        stt.models_changed.connect(self.refresh_models)
        self.poll = QTimer(self, interval=500, timeout=self._poll)
        self.cap_timeout = QTimer(self, singleShot=True, interval=10000, timeout=lambda: self._captured([]))

    def _key_row(self, slot, r):
        lbl = QLabel()
        lbl.setStyleSheet("font-weight:600; padding:4px 8px; border:1px solid palette(mid); border-radius:4px;")
        set_btn = QPushButton("Change…")
        set_btn.clicked.connect(lambda _=False, s=slot: self._capture(s))
        clr = QPushButton("Reset" if slot == "" else "✕")
        name = lang_name(slot) if slot else "main"
        if slot:
            clr.setToolTip("Remove this language hotkey")
            clr.clicked.connect(lambda _=False, s=slot: self._remove_lang(s))
        else:
            clr.clicked.connect(lambda _=False: self._apply_key("", list(K.DEFAULT)))
        mc = QComboBox()
        lbl.setAccessibleName(f"{name} hotkey")
        set_btn.setAccessibleName(f"Change {name} hotkey")
        clr.setAccessibleName(f"Remove {name} hotkey" if slot else "Reset main hotkey")
        mc.setAccessibleName(f"Model for {name} hotkey")
        mc.setMinimumWidth(170)
        mc.currentIndexChanged.connect(lambda _, s=slot: self._slot_model_changed(s))
        for c, w in enumerate((lbl, set_btn, clr, mc), 1):
            self.grid.addWidget(w, r, c)
        self.keys[slot] = (lbl, set_btn, clr)
        self.slot_models[slot] = mc
        return [lbl, set_btn, clr, mc]

    def _build_lang_rows(self):
        """(Re)create one grid row per language hotkey (+ the one being added)."""
        for slot, ws in self.lang_rows.items():
            for w in ws:
                self.grid.removeWidget(w)
                w.setParent(None)
                w.deleteLater()
            self.keys.pop(slot, None)
            self.slot_models.pop(slot, None)
        self.lang_rows = {}
        langs = list(self.cfg.get("lang_hotkeys") or {})
        if self.pending and self.pending not in langs:
            langs.append(self.pending)
        for i, code in enumerate(langs):
            r = self.lang_row0 + i
            cap = _caption(lang_name(code))
            self.grid.addWidget(cap, r, 0)
            self.lang_rows[code] = [cap] + self._key_row(code, r)
        self.lang_empty.setVisible(not langs)
        chain = [self.add_btn] + [w for ws in self.lang_rows.values() for w in ws[2:]] + [self.mic]
        for a, b in zip(chain, chain[1:]):
            QWidget.setTabOrder(a, b)

    def _card(self, m):
        title, desc, good, speed, acc = M.CARDS[m]
        card = QFrame(objectName="card")
        grid = QGridLayout(card)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(3)
        head = QHBoxLayout()
        head.setSpacing(10)
        name = QLabel(title, objectName="title")
        chip = QLabel("Selected", objectName="chip")
        head.addWidget(name)
        head.addWidget(chip)
        head.addStretch(1)
        grid.addLayout(head, 0, 0)
        d = QLabel(desc)
        d.setWordWrap(True)
        grid.addWidget(d, 1, 0)
        g = QLabel(f"Good for: {good}")
        g.setWordWrap(True)
        g.setStyleSheet(MUTED)
        grid.addWidget(g, 2, 0)
        meta = QHBoxLayout()
        meta.setSpacing(16)
        size, use = QLabel(), QLabel()
        use.setToolTip("Average memory while loaded")
        if speed:
            meta.addWidget(QLabel(f"Speed {_dots(speed)}"))
            meta.addWidget(QLabel(f"Accuracy {_dots(acc)}"))
        meta.addWidget(size)
        size.setVisible(m != "auto")
        meta.addWidget(use)
        meta.addStretch(1)
        grid.addLayout(meta, 3, 0)
        grid.setColumnStretch(0, 1)
        side = QVBoxLayout()
        side.setSpacing(4)
        st = QLabel()
        st.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sel = QPushButton("Select")
        sel.setFixedWidth(110)
        sel.clicked.connect(lambda _=False: self._select(m))
        side.addWidget(st)
        side.addWidget(sel, 0, Qt.AlignRight)
        btn = None
        if m != "auto":
            btn = QPushButton()
            btn.setFixedWidth(110)
            btn.clicked.connect(lambda _=False: self._model_btn(m))
            side.addWidget(btn, 0, Qt.AlignRight)
        side.addStretch(1)
        grid.addLayout(side, 0, 1, 4, 1)
        self.rows[m] = (name, size, use, st, sel, btn)
        self.cards[m] = (card, chip)
        return card

    # ---------- open / refresh ----------
    def open_window(self, tab=None):
        if self.cap_slot is not None:
            self._captured([])           # cancel a capture left running (e.g. reopened from tray)
        self.refresh()
        if tab is not None:
            self.tabs.setCurrentIndex(tab)
        self.show()
        self.raise_()
        self.activateWindow()

    def _slot_keys(self, slot):
        return self.cfg["hotkey"] if slot == "" else (self.cfg.get("lang_hotkeys") or {}).get(slot, [])

    def refresh_keys(self):
        self._build_lang_rows()
        for slot, (lbl, set_btn, clr) in self.keys.items():
            vks = self._slot_keys(slot)
            lbl.setText(K.label(vks) if vks else "Not set")
            set_btn.setEnabled(True)
            clr.setEnabled(bool(vks) or slot == "")
        self.refresh_slot_models()

    def refresh_slot_models(self, info=None):
        info = info if info is not None else M.info()
        auto = M.auto_model()
        lk = self.cfg.get("lang_hotkeys") or {}
        lm = self.cfg.get("lang_models") or {}
        for slot, mc in self.slot_models.items():
            mc.blockSignals(True)
            mc.clear()
            if slot:
                mc.addItem("Same as main", None)
            for m in ["auto"] + C.MODELS:
                target = auto if m == "auto" else m
                have = info.get(target) is not None
                text = f"Auto (→ {auto})" if m == "auto" else M.CARDS[m][0]
                mc.addItem(text if have else f"{text} — not downloaded", m)
                mc.model().item(mc.count() - 1).setEnabled(have)
            cur = self.cfg["model"] if slot == "" else lm.get(slot)
            mc.setCurrentIndex(max(0, mc.findData(cur)))
            if slot:
                mc.setEnabled(bool(lk.get(slot)))
                mc.setToolTip("Model for this hotkey" if lk.get(slot) else "Set a hotkey first")
            mc.blockSignals(False)
        self.refresh_planned()

    def refresh_planned(self):
        names = M.planned(self.cfg)
        loaded = f"Loaded now: {', '.join(f'{n} ({d})' for n, d in self.stt.loaded_desc().items())}."             if self.stt.loaded else ""
        note = f"{LOADED_NOTE} {loaded}".strip()
        warn = ""
        if len(names) > 1:
            warn = (f"⚠ {len(names)} models stay loaded all the time while Whisky runs: {', '.join(names)} "
                    f"— together ≈ {M.total_usage(names)}.")
        for w, t in ((self.multi_warn, warn), (self.multi_warn2, warn), (self.loaded_note, note),
                     (self.loaded_note2, note)):
            w.setText(t)
            w.setVisible(bool(t))

    def refresh(self):
        self.refresh_keys()
        self.mic.blockSignals(True)
        self.mic.clear()
        self.mic.addItem("System default", None)
        for n in input_devices(refresh=not self.live.isVisible()):
            self.mic.addItem(n, n)
        self.mic.setCurrentIndex(max(0, self.mic.findData(self.cfg["mic"])))
        self.mic.blockSignals(False)
        for w, val in ((self.auto, autostart.enabled()), (self.space, self.cfg["append_space"]),
                       (self.restore, self.cfg["restore_clipboard"])):
            w.blockSignals(True)
            w.setChecked(bool(val))
            w.blockSignals(False)
        self.refresh_models()

    def refresh_models(self):
        info = M.info()
        self._dl = self.progress()
        dl_name = self._dl[0] if self._dl else None
        loaded = set(self.stt.loaded_desc())
        planned = set(M.planned(self.cfg))
        chosen = self.cfg["model"] if self.cfg["model"] in C.MODELS else "auto"
        for m, (name, size, use, st, sel, btn) in self.rows.items():
            target = M.auto_model() if m == "auto" else m
            have = info.get(target) is not None
            if m == "auto":
                name.setText(f"Auto  → {target}")
                size.setText("")
                st.setText(f"Downloading {self._dl[1]}%" if target == dl_name
                           else "✓ Ready" if have else "Not downloaded")
            else:
                size.setText(f"Disk {_mb(info[m])}" if have else f"Disk ≈{_mb(M.APPROX_MB[m])}")
                if m == dl_name:
                    st.setText(f"Downloading {self._dl[1]}%")
                    btn.setText("Downloading…")
                    btn.setEnabled(False)
                elif have:
                    st.setText("✓ Loaded" if m in loaded else "✓ Downloaded")
                    btn.setText("Delete")
                    busy = m in loaded or m in planned or m == chosen
                    btn.setEnabled(not busy)
                    btn.setToolTip("Model in use" if busy else "")
                else:
                    st.setText("Not downloaded")
                    btn.setText("Download")
                    btn.setEnabled(dl_name is None)
                    btn.setToolTip("" if dl_name is None else "Another download is running")
            use.setText(f"Memory {M.usage(target)}")
            card, chip = self.cards[m]
            card.setProperty("chosen", m == chosen)
            card.style().unpolish(card)
            card.style().polish(card)
            chip.setVisible(m == chosen)
            if m == chosen:
                sel.setText("✓ Selected")
                sel.setEnabled(False)
                sel.setToolTip("")
            else:
                sel.setText("Select")
                sel.setEnabled(have)
                sel.setToolTip("" if have else "Download it first")
        self.status.setText(self.state_text())
        self.refresh_slot_models(info)

    def _poll(self):
        self.status.setText(self.state_text())
        dl = self.progress()
        if (dl is None) != (self._dl is None) or (dl and self._dl and dl[0] != self._dl[0]):
            self.refresh_models()        # download started / finished
        elif dl:
            self._dl = dl
            self.rows[dl[0]][3].setText(f"Downloading {dl[1]}%")
            if M.auto_model() == dl[0]:
                self.rows["auto"][3].setText(f"Downloading {dl[1]}%")

    def showEvent(self, e):
        self.poll.start()
        super().showEvent(e)

    def closeEvent(self, e):
        self.poll.stop()
        if self.hk.capturing:
            self._captured([])
        super().closeEvent(e)

    # ---------- actions ----------
    def _save(self, k, v):
        self.cfg[k] = v
        C.save(self.cfg)

    def _select(self, m):
        self.on_model(m)
        self.refresh_models()

    def _model_btn(self, m):
        st, btn = self.rows[m][3], self.rows[m][5]
        if btn.text() == "Download":
            btn.setText("Downloading…")
            btn.setEnabled(False)
            st.setText("Downloading 0%")
            self.stt.download(m)
        elif QMessageBox.question(self, "Delete model", f"Delete {M.CARDS[m][0]}?") == QMessageBox.Yes:
            try:
                M.delete(m)
            except Exception as e:
                QMessageBox.warning(self, "Delete model", str(e)[:200])
            self.refresh_models()

    def _slot_model_changed(self, slot):
        m = self.slot_models[slot].currentData()
        if slot == "":
            if m:
                self._select(m)
            return
        lm = dict(self.cfg.get("lang_models") or {})
        if m:
            lm[slot] = m
        else:
            lm.pop(slot, None)
        self._save("lang_models", lm)
        self.stt.sync()
        self.refresh_planned()
        self.refresh_models()

    def _mic_changed(self, _):
        self._save("mic", self.mic.currentData())
        self.live.restart()

    # ---------- hotkey capture ----------
    def _capture(self, slot):
        self.cap_slot = slot
        for _, set_btn, clr in self.keys.values():
            set_btn.setEnabled(False)
            clr.setEnabled(False)
        self.add_btn.setEnabled(False)
        self.keys[slot][0].setText("Press keys…")
        self.key_hint.setText("Press and release the key or combo. Esc = cancel.")
        self.hk.start_capture()
        self.cap_timeout.start()

    def _captured(self, vks):
        if self.cap_slot is None:
            return
        slot, self.cap_slot = self.cap_slot, None
        self.cap_timeout.stop()
        self.hk.stop_capture()
        if slot == self.pending:
            self.pending = None          # added (if keys ok) or cancelled
        self._apply_key(slot, vks)
        self.add_btn.setEnabled(True)

    def _conflict(self, slot, vks):
        for other in [""] + list(self.cfg.get("lang_hotkeys") or {}):
            if other != slot and set(self._slot_keys(other)) == set(vks):
                return f"Already used by {lang_name(other) if other else 'Main'}"
        return None

    def _apply_key(self, slot, vks):
        """Validate (keys + duplicates), then save; else show why."""
        err = (K.validate(vks) or self._conflict(slot, vks)) if vks else None
        if vks and not err:
            self._set_key(slot, K.ordered(vks))
        else:
            self.refresh_keys()
            self.key_hint.setText(err or HINT)

    def _set_key(self, slot, vks):
        if slot == "":
            self.cfg["hotkey"] = vks
        else:
            lk = dict(self.cfg.get("lang_hotkeys") or {})
            if vks:
                lk[slot] = vks
            else:
                lk.pop(slot, None)
            self.cfg["lang_hotkeys"] = lk
        C.save(self.cfg)
        self.on_hotkey()
        self.refresh_keys()
        self.key_hint.setText(HINT)

    def _add_lang(self, code=None):
        used = set(self.cfg.get("lang_hotkeys") or {})
        options = [(c, n) for c, n in lang_choices() if c != "auto" and c not in used]
        if code is None:
            name, ok = QInputDialog.getItem(self, "Add language hotkey", "Language:", [n for _, n in options], 0, False)
            if not ok:
                return
            code = {n: c for c, n in options}[name]
        if code in used:
            return
        lm = dict(self.cfg.get("lang_models") or {})
        if lm.pop(code, None):                                  # stale model from an old removed hotkey
            self.cfg["lang_models"] = lm
        self.pending = code
        self.refresh_keys()
        self._capture(code)

    def _remove_lang(self, code):
        lk = dict(self.cfg.get("lang_hotkeys") or {})
        lm = dict(self.cfg.get("lang_models") or {})
        lk.pop(code, None)
        lm.pop(code, None)
        self.cfg["lang_hotkeys"], self.cfg["lang_models"] = lk, lm
        C.save(self.cfg)
        self.on_hotkey()
        self.refresh_keys()
        self.refresh_models()
        self.add_btn.setFocus()
