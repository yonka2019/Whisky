"""Global hold-to-talk key or combo via a low-level keyboard hook (vk codes).

Several bindings: {tag: vks}; tag "" = main hotkey, "en"/"ru"/"he" = per-language.
- pressed(tag): all keys of a binding held (and nothing else)
- released:  any key of the active binding released
- cancelled: another key pressed while holding (normal shortcut, not dictation)
- captured:  capture mode result (list of vks; [] = cancelled with Esc)
Non-modifier hotkey keys (e.g. Space in Ctrl+Space) are swallowed so they don't type.
"""
import ctypes
import logging

from pynput import keyboard
from PySide6.QtCore import QObject, Signal

from . import keys as K

log = logging.getLogger("whisky.key")
_WM_DOWN = (0x100, 0x104)
_WM_UP = (0x101, 0x105)
_INJECTED = 0x10 | 0x02
_gaks = ctypes.windll.user32.GetAsyncKeyState


class HoldKey(QObject):
    pressed = Signal(str)
    released = Signal()
    cancelled = Signal()
    captured = Signal(list)

    def __init__(self, vks, langs=None):
        super().__init__()
        self.tag = ""
        self.set_keys(vks, langs)
        self.held = set()
        self.active = False
        self.combo = False
        self.swallowed = set()
        self.capturing = False
        self.cap = []
        self._l = keyboard.Listener(win32_event_filter=self._filter)
        self._l.daemon = True

    def start(self):
        self._l.start()

    def set_keys(self, vks, langs=None):
        b = {"": frozenset(vks or K.DEFAULT)}
        for t, ks in (langs or {}).items():
            if ks and frozenset(ks) not in b.values():
                b[t] = frozenset(ks)
        self.binds = b
        self.keys = b[""]

    def _match(self):
        for t, ks in self.binds.items():
            if self.held == ks:
                return t
        return None

    def start_capture(self):
        self.cap = []
        self.active = False
        self.capturing = True

    def stop_capture(self):
        self.capturing = False

    # --- hook thread ---
    def _filter(self, msg, data):
        self._handle(msg, data)  # may raise pynput's suppress exception -> key swallowed
        return False             # no pynput callbacks needed

    def _suppress(self):
        self._l.suppress_event()

    def _handle(self, msg, data):
        if data.flags & _INJECTED:
            return                          # synthetic keys (incl. our own Ctrl+V)
        vk = data.vkCode
        if vk == 0xA2 and data.scanCode & 0x200:
            return                          # fake LCtrl sent with AltGr
        down, up = msg in _WM_DOWN, msg in _WM_UP

        if self.capturing:
            if down:
                if vk == K.ESC and not self.cap:
                    self.capturing = False
                    self.captured.emit([])
                elif vk not in self.cap:
                    self.cap.append(vk)
                self.held.add(vk)
            elif up:
                self.held.discard(vk)
                if self.cap and not (self.held & set(self.cap)):
                    self.capturing = False
                    self.captured.emit(list(self.cap))
            self._suppress()

        if down:
            repeat = vk in self.held
            if not repeat:                  # drop keys whose key-up we missed
                self.held = {v for v in self.held if _gaks(v) & 0x8000}
            self.held.add(vk)
            tag = None if repeat else self._match()
            if self.active:
                if tag is not None and tag != self.tag:     # e.g. main=RCtrl, Hebrew=RCtrl+H
                    self.cancelled.emit()
                    self.tag, self.keys, self.combo = tag, self.binds[tag], False
                    self.pressed.emit(tag)
                elif vk not in self.keys and not self.combo:
                    self.combo = True
                    self.cancelled.emit()
            elif tag is not None and vk in self.binds[tag]:
                self.active, self.combo = True, False
                self.tag, self.keys = tag, self.binds[tag]
                self.pressed.emit(tag)
            if vk not in K.MODIFIERS and any(vk in ks and self.held >= ks for ks in self.binds.values()):
                self.swallowed.add(vk)
                self._suppress()
        elif up:
            self.held.discard(vk)
            if self.active and vk in self.keys:
                self.active = False
                if not self.combo:
                    self.released.emit()
            if vk in self.swallowed:
                self.swallowed.discard(vk)
                self._suppress()
