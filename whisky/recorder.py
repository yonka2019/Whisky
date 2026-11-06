import logging
import os
import threading
from collections import deque

import numpy as np
import sounddevice as sd

RATE = 16000
log = logging.getLogger("whisky.rec")


def input_devices(refresh=False):
    """Input device names of the default host API (deduped)."""
    try:
        if refresh:  # PortAudio caches devices; re-init to see newly plugged mics
            sd._terminate()
            sd._initialize()
        api = sd.default.hostapi
        names = []
        for d in sd.query_devices():
            if d["max_input_channels"] > 0 and d["hostapi"] == api and d["name"] not in names:
                names.append(d["name"])
        return names
    except Exception:
        log.exception("device query failed")
        return []


def _device_index(name):
    if not name:
        return None
    api = sd.default.hostapi
    for i, d in enumerate(sd.query_devices()):
        if d["name"] == name and d["max_input_channels"] > 0 and d["hostapi"] == api:
            return i
    return None


class Recorder:
    def __init__(self):
        self.level = 0.0
        self.levels = deque(maxlen=64)   # one entry per 20ms block (newest last)
        self._chunks = []
        self._stream = None
        self._rate = RATE
        self._lock = threading.Lock()
        self._fake = os.environ.get("WHISKY_FAKE_AUDIO")  # test hook: wav path

    def start(self, mic=None):
        self._close()
        with self._lock:
            self._chunks = []
            self.level = 0.0
            self.levels.clear()
        if self._fake:
            return
        dev = _device_index(mic)
        try:
            self._open(dev, RATE)
        except Exception:
            info = sd.query_devices(dev if dev is not None else sd.default.device[0])
            self._open(dev, int(info["default_samplerate"]))

    def _open(self, dev, rate):
        self._rate = rate
        self._stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                                      device=dev, callback=self._cb, blocksize=int(rate * 0.02))
        self._stream.start()

    def _cb(self, data, frames, t, status):
        mono = data[:, 0].copy()
        with self._lock:
            self._chunks.append(mono)
        rms = float(np.sqrt(np.mean(mono * mono)) + 1e-9)
        # ~ -60dB..-10dB -> 0..1
        self.level = float(np.clip((20 * np.log10(rms) + 60) / 50, 0, 1))
        self.levels.append(self.level)

    @property
    def active(self):
        return self._stream is not None

    def _close(self):
        s, self._stream = self._stream, None
        if s:
            try:
                s.stop()
                s.close()
            except Exception:
                log.exception("stream close")

    def stop(self):
        if self._fake:
            return _load_wav(self._fake)
        self._close()
        audio = self.take()
        self.level = 0.0
        return audio

    def take(self):
        """Audio captured since the last take/start (16 kHz mono); keeps recording."""
        with self._lock:
            chunks, self._chunks = self._chunks, []
        audio = np.concatenate(chunks) if chunks else np.zeros(0, np.float32)
        if self._rate != RATE and len(audio):
            n = int(len(audio) * RATE / self._rate)
            audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
        return audio


def _load_wav(path):
    import wave
    with wave.open(path, "rb") as w:
        rate, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw == 1:
        a = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
    elif sw == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
        i = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        a = (np.where(i >= 1 << 23, i - (1 << 24), i) / float(1 << 23)).astype(np.float32)
    else:
        a = np.frombuffer(raw, {2: np.int16, 4: np.int32}[sw]).astype(np.float32) / float(2 ** (8 * sw - 1))
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    if rate != RATE:
        n = int(len(a) * RATE / rate)
        a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a)
    return a.astype(np.float32)
