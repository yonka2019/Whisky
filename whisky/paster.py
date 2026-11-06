import logging
import os

from pynput.keyboard import Controller, Key, KeyCode
from PySide6.QtCore import QMimeData, QTimer
from PySide6.QtGui import QGuiApplication

log = logging.getLogger("whisky.paste")
_kb = Controller()
_V = KeyCode.from_vk(0x56)  # physical V: works under any layout (HE/RU)
_saved = None               # user's clipboard before the first of back-to-back pastes
_timer = None


def _clone(mime):
    copy = QMimeData()
    if mime is not None:
        for f in mime.formats():
            copy.setData(f, mime.data(f))
    return copy


def _restore():
    global _saved
    if _saved is not None:
        QGuiApplication.clipboard().setMimeData(_saved)
        _saved = None


def paste(text, restore=True):
    """Put text on clipboard, send Ctrl+V to the focused app, then restore old clipboard."""
    global _saved, _timer
    cb = QGuiApplication.clipboard()
    if restore and _saved is None:
        _saved = _clone(cb.mimeData())
    cb.setText(text)
    try:
        if os.environ.get("WHISKY_NO_PASTE"):
            log.info("paste skipped (test mode): %r", text)
        else:
            with _kb.pressed(Key.ctrl):
                _kb.press(_V)
                _kb.release(_V)
    except Exception:
        log.exception("paste keystroke failed")
    finally:
        if restore:
            if _timer is None:
                _timer = QTimer(singleShot=True, interval=400)
                _timer.timeout.connect(_restore)
            _timer.start()  # restart: restore once after the last paste
