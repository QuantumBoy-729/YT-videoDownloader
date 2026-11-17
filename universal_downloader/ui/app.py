from __future__ import annotations

import gc
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .. import APP_NAME, __version__
from .. import selfcheck
from .main_window import MainWindow


def _use_bundled_certificates() -> None:
    """Point SSL at certifi's CA bundle when running as a frozen executable."""
    if getattr(sys, "frozen", False) and "SSL_CERT_FILE" not in os.environ:
        try:
            import certifi

            os.environ["SSL_CERT_FILE"] = certifi.where()
        except Exception:
            pass


def keep_gc_on_main_thread(parent) -> list[QTimer]:
    """Run Python's garbage collector only on the GUI thread.

    Left automatic, a collection can start on any thread, including a download
    worker. If it then frees a Qt widget (a closed dialog, a removed queue item)
    it destroys the underlying C++ object from the wrong thread, which corrupts
    memory and crashes the app. So automatic collection is switched off and a
    timer on the GUI thread does the work instead.
    """
    gc.disable()
    young = QTimer(parent)
    young.setInterval(1000)
    young.timeout.connect(lambda: gc.collect(1))
    full = QTimer(parent)
    full.setInterval(60_000)
    full.timeout.connect(gc.collect)
    young.start()
    full.start()
    return [young, full]


def main(argv: list[str] | None = None) -> int:
    _use_bundled_certificates()
    if os.name == "nt":
        # Without this, Windows groups the window under python.exe's icon.
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("UniversalDownloader.App")
        except Exception:
            pass
    args = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(args)
    keep_gc_on_main_thread(app)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    if "--smoke-test" in args:
        return _smoke_test()
    window = MainWindow()
    window.show()
    return app.exec()


def _smoke_test() -> int:
    """Self-check for CI and for people verifying a download; see selfcheck.py."""
    log = os.environ.get("UD_SMOKE_LOG")
    lines: list[str] = []

    def report(line: str) -> None:
        lines.append(line)
        # A windowed Windows executable has no console, so stdout may not exist.
        if sys.stdout is not None:
            print(line)

    try:
        code = selfcheck.run(report)
    except Exception as exc:  # The check itself must never hang or hide a failure.
        report(f"FAIL self-check crashed - {type(exc).__name__}: {exc}")
        code = 1
    if log:
        with open(log, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    return code
