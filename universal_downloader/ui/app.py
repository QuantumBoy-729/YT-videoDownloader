from __future__ import annotations

import gc
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .. import APP_NAME, __version__
from ..core import find_ffmpeg
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
    app = QApplication(sys.argv if argv is None else argv)
    keep_gc_on_main_thread(app)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    window = MainWindow()
    window.show()
    if "--smoke-test" in app.arguments():
        # Used by CI on the packaged executable: start up, check the bundled
        # pieces are present, and exit without user interaction.
        import yt_dlp  # noqa: F401

        window._items.clear()
        QTimer.singleShot(500, lambda: app.exit(0 if find_ffmpeg() else 1))
    return app.exec()
