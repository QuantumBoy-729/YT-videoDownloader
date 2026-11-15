"""Shared fixtures: a local HTTP server with small real media files.

Nothing in the test suite touches the internet.
"""

from __future__ import annotations

import functools
import os
import http.server
import subprocess
import threading
import time
from pathlib import Path

import pytest

from universal_downloader.core import find_ffmpeg

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Never route test traffic to 127.0.0.1 through a system proxy.
NO_PROXY = {"proxy": ""}


class _ThrottledHandler(http.server.SimpleHTTPRequestHandler):
    """Serves files; paths under /slow/ are trickled so tests can interrupt."""

    def log_message(self, *args) -> None:
        pass

    def translate_path(self, path: str) -> str:
        return super().translate_path(path.replace("/slow/", "/", 1))

    def copyfile(self, source, outputfile) -> None:
        slow = self.path.startswith("/slow/")
        try:
            while chunk := source.read(8 * 1024):
                outputfile.write(chunk)
                if slow:
                    outputfile.flush()
                    time.sleep(0.02)
        except (BrokenPipeError, ConnectionResetError):
            pass  # Client went away (cancelled download or a probe request).


@pytest.fixture(scope="session")
def ffmpeg() -> str:
    path = find_ffmpeg()
    if not path:
        pytest.skip("ffmpeg not available")
    return path


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory, ffmpeg) -> Path:
    root = tmp_path_factory.mktemp("media")
    subprocess.run(
        [
            ffmpeg, "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=15",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-c:v", "mpeg4", "-q:v", "2", "-c:a", "aac", "-shortest",
            str(root / "clip.mp4"),
        ],
        check=True,
    )
    return root


@pytest.fixture(scope="session")
def server(media_dir) -> str:
    handler = functools.partial(_ThrottledHandler, directory=str(media_dir))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
