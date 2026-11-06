"""Small floating pill with live voice bars (no focus steal, click-through)."""
import ctypes
import ctypes.wintypes
import math
import time

from PySide6.QtCore import QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter,
                           QPainterPath)
from PySide6.QtWidgets import QWidget

BARS = 22
H = 44


def reduced_motion():
    """Windows 'Animation effects' off -> True."""
    try:
        v = ctypes.wintypes.BOOL()
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(v), 0)
        return not v.value
    except Exception:
        return False


class Popup(QWidget):
    def __init__(self, recorder):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.rec = recorder
        self.mode = "hidden"          # rec | busy | msg
        self.text = ""
        self.heights = [0.0] * BARS
        self.reduced = reduced_motion()
        self.font_ = QFont("Segoe UI", 10, QFont.DemiBold)
        self.timer = QTimer(self, interval=16, timeout=self._tick)
        self.hide_timer = QTimer(self, singleShot=True, timeout=self.fade_out)
        self.anim = QPropertyAnimation(self, b"windowOpacity", self)
        self.anim.finished.connect(self._anim_done)
        self._fading_out = False
        self.t0 = time.monotonic()

    # ---------- states ----------
    def show_rec(self):
        self.heights = [0.0] * BARS
        self._show("rec", "", 200)

    def show_busy(self):
        self._show("busy", "", 200)

    def show_msg(self, text, ms=1400):
        fm = QFontMetrics(self.font_)
        text = fm.elidedText(text, Qt.ElideRight, 476)
        w = max(120, fm.horizontalAdvance(text) + 44)
        self._show("msg", text, w)
        if ms:
            self.hide_timer.start(ms)

    def _show(self, mode, text, width):
        self.hide_timer.stop()
        self.mode, self.text = mode, text
        self.resize(width, H)
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        self.move(g.x() + (g.width() - width) // 2, g.bottom() - H - 28)
        self._fading_out = False
        self.anim.stop()
        if not self.isVisible():
            if self.reduced:
                self.setWindowOpacity(1.0)
            else:
                self.setWindowOpacity(0.0)
                self.anim.setDuration(120)
                self.anim.setStartValue(0.0)
                self.anim.setEndValue(1.0)
                self.anim.start()
            self.show()
        else:
            self.setWindowOpacity(1.0)
        if mode in ("rec", "busy"):
            self.timer.start()      # animate only these; static messages need no repaint loop
        else:
            self.timer.stop()
        self.update()

    def fade_out(self):
        if not self.isVisible():
            return
        if self.reduced:
            self._hide_now()
            return
        self._fading_out = True
        self.anim.stop()
        self.anim.setDuration(180)
        self.anim.setStartValue(self.windowOpacity())
        self.anim.setEndValue(0.0)
        self.anim.start()

    def _anim_done(self):
        if self._fading_out:
            self._hide_now()

    def _hide_now(self):
        self._fading_out = False
        self.timer.stop()
        self.mode = "hidden"
        self.hide()

    # ---------- animation ----------
    def _tick(self):
        if self.mode == "rec":
            # bars = real mic levels only: newest in the center, older ones move outward
            hist = list(self.rec.levels)
            half = BARS // 2
            for k in range(half):
                blk = hist[-(2 * k + 2):len(hist) - 2 * k] if len(hist) > 2 * k else []
                target = max(blk) if blk else 0.0
                for i in (half - 1 - k, half + k):
                    if self.reduced:
                        self.heights[i] = target
                    else:
                        c = 0.6 if target > self.heights[i] else 0.25
                        self.heights[i] += (target - self.heights[i]) * c
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.fillPath(path, QColor(18, 18, 22, 235))
        p.setPen(QColor(255, 255, 255, 30))
        p.drawPath(path)
        cy = r.center().y()

        if self.mode == "rec":
            bw, gap = 3.0, 3.6
            total = BARS * bw + (BARS - 1) * gap
            x0 = r.center().x() - total / 2 + 9
            # red rec dot
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 69, 58))
            p.drawEllipse(QRectF(r.left() + 14, cy - 4, 8, 8))
            p.setBrush(QColor(255, 255, 255, 235))
            for i, h in enumerate(self.heights):
                bh = 3 + min(1.0, h ** 0.75) * (r.height() - 14)
                p.drawRoundedRect(QRectF(x0 + i * (bw + gap), cy - bh / 2, bw, bh), 1.5, 1.5)
        elif self.mode == "busy":
            t = time.monotonic() - self.t0
            p.setPen(Qt.NoPen)
            for i in range(5):
                a = 0.6 if self.reduced else 0.3 + 0.7 * (0.5 + 0.5 * math.sin(t * 7 - i * 0.7))
                dy = 0 if self.reduced else -3 * math.sin(t * 7 - i * 0.7)
                p.setBrush(QColor(255, 255, 255, int(255 * a)))
                p.drawEllipse(QRectF(r.center().x() - 34 + i * 16, cy - 3 + dy, 6, 6))
        elif self.mode == "msg":
            p.setPen(QColor(240, 240, 245))
            p.setFont(self.font_)
            p.drawText(r, Qt.AlignCenter, self.text)
