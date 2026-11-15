"""Build a single-file executable with PyInstaller.

    pip install ".[build]"
    python packaging/build.py

The result is written to ``dist/`` (``YTDownloader.exe`` on Windows). It
contains Python, Qt, yt-dlp and an ffmpeg binary, so it runs on machines with
nothing else installed.
"""

from __future__ import annotations

from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    PyInstaller.__main__.run(
        [
            str(ROOT / "yt_downloader" / "__main__.py"),
            "--name=YTDownloader",
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
        ]
    )


if __name__ == "__main__":
    main()
