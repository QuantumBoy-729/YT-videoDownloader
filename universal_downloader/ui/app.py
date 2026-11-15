from __future__ import annotations

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


def main(argv: list[str] | None = None) -> int:
    _use_bundled_certificates()
    app = QApplication(sys.argv if argv is None else argv)
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
