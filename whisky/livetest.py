"""Live test window: listens while open, transcribes each phrase after a pause. Nothing is pasted."""
import math
from collections import deque

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout,
                               QWidget)

from .recorder import RATE, Recorder

BLOCK = RATE // 10          # 100 ms
PRE, END_SIL, MIN_SPEECH, MAX_BLOCKS = 3, 8, 3, 200   # blocks: pre-roll, pause to cut, min speech, 20 s cap


class LiveTest(QWidget):
    def __init__(self, cfg, stt, icon=None):
        super().__init__()
        self.cfg, self.stt = cfg, stt
        self.setWindowTitle("Whisky Live Test")
        if icon:
            self.setWindowIcon(icon)
        self.resize(480, 340)
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        self.state = QLabel()
        self.meter = QProgressBar()
        self.meter.setRange(0, 100)
        self.meter.setTextVisible(False)
        self.meter.setFixedWidth(120)
        top.addWidget(self.state, 1)
        top.addWidget(self.meter)
        v.addLayout(top)
        self.text = QPlainTextEdit(readOnly=True)
        self.text.setPlaceholderText("Speak — text appears after each pause. Nothing is pasted.")
        v.addWidget(self.text, 1)
        bottom = QHBoxLayout()
        clear = QPushButton("Clear")
        clear.clicked.connect(self.text.clear)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        bottom.addWidget(clear)
        bottom.addStretch(1)
        bottom.addWidget(close)
        v.addLayout(bottom)
        self.rec = None
        self.jobs = 0
        self.timer = QTimer(self, interval=100, timeout=self._tick)
        stt.test_result.connect(self._on_result)
        self._reset()

    # ---------- lifecycle ----------
    def open_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def showEvent(self, e):
        self._start()
        super().showEvent(e)

    def closeEvent(self, e):
        self._stop()
        super().closeEvent(e)

    def restart(self):
        """Mic changed in Settings."""
        if self.isVisible():
            self._stop()
            self._start()

    def _start(self):
        self._reset()
        self.rec = Recorder()
        try:
            self.rec.start(self.cfg["mic"])
        except Exception:
            self.rec = None
            self._set_state("Mic unavailable — check Windows privacy settings")
            return
        self.timer.start()
        self._set_state()

    def _stop(self):
        self.timer.stop()
        if self.rec:
            self.rec.stop()
            self.rec = None
        self.meter.setValue(0)
        self._reset()

    def _reset(self):
        self.buf = np.zeros(0, np.float32)
        self.pre = deque(maxlen=PRE)
        self.seg, self.speech, self.sil = None, 0, 0
        self.floor = None

    # ---------- audio ----------
    def _tick(self):
        if self.rec:
            self.feed(self.rec.take())
            self.meter.setValue(int(self.rec.level * 100))

    def feed(self, audio):
        self.buf = np.concatenate([self.buf, audio]) if len(audio) else self.buf
        while len(self.buf) >= BLOCK:
            blk, self.buf = self.buf[:BLOCK], self.buf[BLOCK:]
            self._block(blk)

    def _block(self, blk):
        db = 20 * math.log10(float(np.sqrt(np.mean(blk * blk))) + 1e-9)
        # noise floor: follows quiet levels at once, rises slowly (0.3 dB/s)
        self.floor = db if self.floor is None or db < self.floor else self.floor + 0.03
        voiced = db > max(self.floor + 10, -50)
        if self.seg is None:
            self.pre.append(blk)
            if voiced:
                self.seg, self.speech, self.sil = list(self.pre), 1, 0
                self._set_state()
            return
        self.seg.append(blk)
        if voiced:
            self.speech += 1
            self.sil = 0
        else:
            self.sil += 1
        if self.sil >= END_SIL or len(self.seg) >= MAX_BLOCKS:
            self._flush()

    def _flush(self):
        seg, speech = self.seg, self.speech
        self.seg, self.speech, self.sil = None, 0, 0
        self.pre.clear()
        if seg and speech >= MIN_SPEECH:
            self.jobs += 1
            self.stt.submit_test(np.concatenate(seg))
        self._set_state()

    def _on_result(self, text, lang):
        self.jobs = max(0, self.jobs - 1)
        if text:
            self.text.appendPlainText(f"[{lang.upper()}] {text}" if lang else text)
        self._set_state()

    def _set_state(self, msg=None):
        if msg is None:
            msg = "Hearing you…" if self.seg is not None else "Listening…"
            if self.jobs:
                msg += "  · transcribing"
        self.state.setText(msg)
