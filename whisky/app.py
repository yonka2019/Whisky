import logging
import logging.handlers
import os
import sys
import time

from . import config as C

MAX_REC_S = 180


def _setup_logging():
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(C.LOG_PATH, maxBytes=1_000_000, backupCount=1, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.addHandler(h)
    root.setLevel(logging.INFO)
    if sys.stdout is None or sys.stderr is None:  # windowed exe
        f = open(C.LOG_PATH.with_suffix(".out.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f


def _dir_mb(p):
    try:
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1e6
    except Exception:
        return 0


def main():
    _setup_logging()
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")   # real files: some PCs create links they can't open
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")   # default 10s is too short on slow links
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "30")
    log = logging.getLogger("whisky")

    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(C.APP_NAME)

    # --- single instance ---
    sock_name = f"WhiskyInstance-{os.environ.get('USERNAME', 'u')}"
    s = QLocalSocket()
    s.connectToServer(sock_name)
    if s.waitForConnected(300):
        s.write(b"show")
        s.flush()
        s.waitForBytesWritten(300)
        return 0
    QLocalServer.removeServer(sock_name)
    server = QLocalServer()
    server.listen(sock_name)

    from . import cuda_setup
    cuda_setup.setup()
    from . import keys as K
    from .hotkey import HoldKey
    from .icon import icon
    from .paster import paste
    from .popup import Popup
    from .recorder import Recorder
    from .settings import SettingsWindow
    from . import models as M
    from .transcriber import Transcriber, _is_downloaded, resolve

    cfg = C.load()
    rec = Recorder()
    popup = Popup(rec)
    stt = Transcriber(cfg)
    hk = HoldKey(cfg["hotkey"], cfg["lang_hotkeys"])
    st = {"t": 0.0, "recording": False, "pending": 0, "state": "loading", "model": "", "announce": False,
          "pct": 0, "lang": None}
    ic_idle, ic_rec = icon(False), icon(True)

    def key():
        return K.label(cfg["hotkey"])

    # --- tray ---
    tray = QSystemTrayIcon(ic_idle)
    menu = QMenu()
    status_act = menu.addAction("Loading…")
    status_act.setEnabled(False)
    menu.addSeparator()
    settings_act = menu.addAction("Settings…")
    menu.addAction("Open data folder").triggered.connect(
        lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(C.DATA_DIR))))
    menu.addSeparator()
    menu.addAction("Quit").triggered.connect(app.quit)
    tray.setContextMenu(menu)

    def status_line():
        if st["state"] == "ready":
            return f"{'Auto → ' if cfg['model'] == 'auto' else ''}{st['model']}"
        if st["state"] == "downloading":
            return f"Downloading {st['model']} · {st['pct']}%"
        if st["state"] == "error":
            return "Model error — see log"
        return f"Loading {st['model']}…"

    def refresh_status():
        txt = status_line()
        status_act.setText(txt)
        tray.setToolTip(f"Whisky — hold {key()} to dictate\n{txt}")

    def state_text(auto_only=False):
        """For the Settings window."""
        if auto_only:
            return stt.desc if cfg["model"] == "auto" and stt.model is not None else ""
        if st["state"] == "ready":
            return f"Using {stt.desc}"
        return status_line()

    def set_model(m):
        if cfg["model"] != m:
            cfg["model"] = m
            C.save(cfg)
            stt.load()

    def set_hotkey():
        hk.set_keys(cfg["hotkey"], cfg["lang_hotkeys"])
        stt.sync()             # load/unload per-language models
        refresh_status()
        log.info("hotkeys: main=%s langs=%s", key(), {l: K.label(v) for l, v in cfg["lang_hotkeys"].items()})

    def progress():
        return (st["model"], st["pct"]) if st["state"] == "downloading" else None

    settings = SettingsWindow(cfg, hk, stt, on_model=set_model, on_hotkey=set_hotkey,
                              state_text=state_text, progress=progress, icon=ic_idle)
    settings_act.triggered.connect(lambda: settings.open_window())

    # --- download progress ---
    dl_timer = QTimer(interval=1000)

    def dl_tick():
        total = M.APPROX_MB.get(st["model"], 1500)
        st["pct"] = max(0, min(99, int(_dir_mb(C.MODELS_DIR) - st["dl_base"]) * 100 // total))
        refresh_status()   # progress shows in tray tooltip + Settings only
    dl_timer.timeout.connect(dl_tick)

    def on_status(state, detail):
        st["state"], st["model"] = state, detail
        if state == "downloading":
            st["dl_base"] = _dir_mb(C.MODELS_DIR)
            st["announce"] = stt.model is None   # first model: say "Ready" when done
            st["pct"] = 0
            dl_tick()
            dl_timer.start()
        else:
            dl_timer.stop()
        if state == "ready" and st["announce"]:
            st["announce"] = False
            if not st["recording"]:
                popup.show_msg(f"Ready · hold {key()} to dictate", 2500)
        refresh_status()
        log.info("status %s %s", state, detail)

    def notify(msg, ms):
        if not st["recording"]:
            popup.show_msg(msg, ms)

    def back_to_state():
        """Popup after a recording ends without a new job."""
        if st["pending"]:
            popup.show_busy()
        elif popup.mode == "rec":
            popup.fade_out()

    def on_failed(msg):
        st["pending"] = max(0, st["pending"] - 1)
        notify(f"Error: {msg}", 3000)

    def on_load_failed(msg):
        dl_timer.stop()
        if stt.model is not None:   # failed switch/download: old model still works
            st["state"], st["model"] = "ready", stt.desc
        else:
            st["state"] = "error"
        refresh_status()
        notify(msg, 6000)

    # --- hotkey flow ---
    show_timer = QTimer(singleShot=True, interval=120)
    show_timer.timeout.connect(lambda: st["recording"] and popup.show_rec())
    max_timer = QTimer(singleShot=True, interval=MAX_REC_S * 1000)  # missed key-up (Win+L, UAC...)
    max_timer.timeout.connect(lambda: (log.info("max recording length reached"), on_release()))

    def on_press(tag=""):
        st["lang"] = tag or None
        try:
            rec.start(cfg["mic"])
        except Exception:
            log.exception("mic")
            popup.show_msg("Mic unavailable — check Windows privacy settings", 3000)
            return
        st["t"], st["recording"] = time.monotonic(), True
        tray.setIcon(ic_rec)
        show_timer.start()
        max_timer.start()

    def end_rec():
        st["recording"] = False
        show_timer.stop()
        max_timer.stop()
        tray.setIcon(ic_idle)
        return rec.stop()

    def on_cancel():
        if st["recording"]:
            end_rec()
            back_to_state()

    def on_release():
        if not st["recording"]:
            return
        held = (time.monotonic() - st["t"]) * 1000
        audio = end_rec()
        if held < cfg["min_hold_ms"]:
            back_to_state()
            return
        st["pending"] += 1
        back_to_state()
        stt.submit(audio, st["lang"])

    def on_result(text, lang):
        st["pending"] = max(0, st["pending"] - 1)
        if text:
            paste(text + (" " if cfg.get("append_space", True) else ""), cfg.get("restore_clipboard", True))
        if st["recording"]:
            return
        if st["pending"]:
            popup.show_busy()
        elif text:
            popup.show_msg(f"✓  {lang.upper()}", 700)
        else:
            popup.show_msg("No speech", 900)

    hk.pressed.connect(on_press)
    hk.released.connect(on_release)
    hk.cancelled.connect(on_cancel)
    stt.status.connect(on_status)
    stt.result.connect(on_result)
    stt.failed.connect(on_failed)
    stt.load_failed.connect(on_load_failed)

    def on_conn():
        c = server.nextPendingConnection()
        if c:
            c.waitForReadyRead(200)
            popup.show_msg(f"Whisky is running · hold {key()}", 2000)
    server.newConnection.connect(on_conn)

    if os.environ.get("WHISKY_SELFTEST"):  # test hook: simulate hold, short tap, combo, then quit
        def selftest(state, _):
            if state != "ready" or st.get("tested"):
                return
            st["tested"] = True
            press = lambda tag="": hk.pressed.emit(tag)
            seq = [(0, press), (1500, hk.released.emit),
                   (6000, press), (6100, hk.released.emit),
                   (7000, press), (7400, hk.cancelled.emit), (7500, hk.released.emit),
                   (8000, lambda: press("he")), (9500, hk.released.emit),
                   (14000, app.quit)]
            for ms, fn in seq:
                QTimer.singleShot(ms, lambda fn=fn: (log.info("selftest %s", fn), fn()))
        stt.status.connect(selftest)
        stt.result.connect(lambda t, l: log.info("selftest result %s %r", l, t))
    first_run = not _is_downloaded(resolve(cfg["model"])[0])
    if first_run or os.environ.get("WHISKY_OPEN_SETTINGS"):  # first run: show download progress
        QTimer.singleShot(300, lambda: settings.open_window(1 if first_run else None))  # 1 = Models tab

    if QSystemTrayIcon.isSystemTrayAvailable():
        tray.show()
    refresh_status()
    hk.start()
    stt.load()
    log.info("started; hotkey=%s", key())
    rc = app.exec()
    logging.shutdown()
    os._exit(rc)  # skip Qt/threads teardown (pynput hook, worker thread)
