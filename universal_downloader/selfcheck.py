"""A quick self-test of an installed or packaged copy of the app.

Run with ``universal-downloader --smoke-test``. It checks the pieces that only
fail in a packaged build (a missing ffmpeg, a plugin loader that cannot find
its files, a lost resource) and exits 0 if all is well. Set ``UD_SMOKE_LOG`` to
a file path to also write the report there, which is the only way to read it
from a windowed executable.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

from . import __version__

_PLUGIN = '''
from yt_dlp.extractor.common import InfoExtractor

class SmokePluginIE(InfoExtractor):
    _VALID_URL = r"smoke-test-plugin:"

    def _real_extract(self, url):
        return {"id": "smoke", "title": "Loaded from a plugin", "url": "http://localhost/smoke.mp4"}
'''


def run(report: Callable[[str], None] = print) -> int:
    """Run every check, calling ``report`` once per line. Returns 0 if all passed.

    Needs a running ``QApplication``. Uses a throwaway settings file and plugin
    folder, so nothing of the user's is read or changed.
    """
    failures = 0

    def check(name: str, passed: bool, detail: str = "") -> None:
        nonlocal failures
        failures += 0 if passed else 1
        report(f"{'ok  ' if passed else 'FAIL'} {name}{f' - {detail}' if detail else ''}")

    def attempt(name: str, action: Callable[[], str]) -> None:
        try:
            check(name, True, action())
        except Exception as exc:
            check(name, False, f"{type(exc).__name__}: {exc}")

    from yt_dlp.globals import plugin_dirs

    report(f"Universal Downloader {__version__} self-check")
    workdir = Path(tempfile.mkdtemp(prefix="ud-selfcheck-"))
    plugin_dirs_before = list(plugin_dirs.value)  # the checks add temporary folders

    def yt_dlp_present() -> str:
        import yt_dlp

        return yt_dlp.version.__version__

    def ffmpeg_present() -> str:
        from .core import find_ffmpeg

        path = find_ffmpeg()
        if not path:
            raise RuntimeError("no ffmpeg binary found")
        return path

    def site_fix_registered() -> str:
        import yt_dlp.extractor.beeg as stock

        if stock.BeegIE.__name__ != "BeegFixedIE":
            raise RuntimeError("the beeg.com fix is not active")
        return "active"

    def icon_renders() -> str:
        from .ui import appicon

        icon = appicon.app_icon()
        if icon.isNull() or not icon.availableSizes():
            raise RuntimeError("icon is empty")
        ico = workdir / "icon.ico"
        appicon.write_ico(ico)
        return f"{ico.stat().st_size} byte .ico"

    def plugin_loads() -> str:
        import zipfile

        from .core import PluginManager, fetch_info

        archive = workdir / "smoke-plugin.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("smoke-plugin-abc1234/yt_dlp_plugins/extractor/smoke.py", _PLUGIN)
        manager = PluginManager(workdir / "plugins")
        manager.install_archive(str(archive))
        title = fetch_info("smoke-test-plugin:").title
        if title != "Loaded from a plugin":
            raise RuntimeError(f"unexpected result {title!r}")
        return "installed and used"

    def window_opens() -> str:
        from PySide6.QtCore import QSettings

        from .core import PluginManager
        from .ui.main_window import MainWindow

        window = MainWindow(
            settings=QSettings(str(workdir / "settings.ini"), QSettings.Format.IniFormat),
            plugins=PluginManager(workdir / "window-plugins"),
        )
        try:
            window.show()
            if window.windowIcon().isNull():
                raise RuntimeError("window has no icon")
            return "ok"
        finally:
            window._items.clear()
            window.close()
            window.deleteLater()

    attempt("yt-dlp", yt_dlp_present)
    attempt("ffmpeg", ffmpeg_present)
    attempt("site fixes", site_fix_registered)
    attempt("icon", icon_renders)
    attempt("plugin loading", plugin_loads)
    attempt("main window", window_opens)
    plugin_dirs.value = plugin_dirs_before

    report("PASSED" if not failures else f"{failures} CHECK(S) FAILED")
    return 0 if not failures else 1
