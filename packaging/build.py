"""Build a single-file executable with PyInstaller.

    pip install ".[build]"
    python packaging/build.py

The result is written to ``dist/`` (``UniversalDownloader.exe`` on Windows). It
contains Python, Qt, yt-dlp and an ffmpeg binary, so it runs on machines with
nothing else installed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def windows_icon() -> list[str]:
    """Draw the app icon into build/icon.ico for the .exe. Other platforms skip it."""
    if sys.platform != "win32":
        return []
    from universal_downloader.ui.appicon import write_ico

    icon = ROOT / "build" / "icon.ico"
    icon.parent.mkdir(exist_ok=True)
    write_ico(icon)
    return [f"--icon={icon}"]


def main() -> None:
    PyInstaller.__main__.run(
        [
            str(ROOT / "universal_downloader" / "__main__.py"),
            "--name=UniversalDownloader",
            "--onefile",
            "--windowed",
            "--noconfirm",
            "--clean",
            f"--paths={ROOT}",
            # The ffmpeg binary ships as package data inside imageio-ffmpeg.
            "--collect-all=imageio_ffmpeg",
            f"--distpath={ROOT / 'dist'}",
            f"--workpath={ROOT / 'build'}",
            f"--specpath={ROOT / 'build'}",
            *windows_icon(),
        ]
    )


if __name__ == "__main__":
    main()
