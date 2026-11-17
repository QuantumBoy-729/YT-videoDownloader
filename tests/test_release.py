"""Things that only matter for a published build: icon, self-check, link hardening."""

from __future__ import annotations

import json
import struct

import pytest

pytest.importorskip("PySide6")

from universal_downloader import selfcheck  # noqa: E402
from universal_downloader.ui import appicon  # noqa: E402
from universal_downloader.ui.app import main  # noqa: E402

from .test_ui import app  # noqa: E402,F401  (shared QApplication fixture)


def test_icon_has_every_size(app):
    icon = appicon.app_icon()
    assert not icon.isNull()
    assert {s.width() for s in icon.availableSizes()} >= {16, 32, 256}


def test_ico_file_is_well_formed(app, tmp_path):
    path = tmp_path / "icon.ico"
    appicon.write_ico(path)
    data = path.read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    assert (reserved, kind, count) == (0, 1, len(appicon.SIZES))
    for index, size in enumerate(appicon.SIZES):
        width, height, _, _, planes, bits, length, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * index)
        assert (width, height) == ((0, 0) if size >= 256 else (size, size))
        assert (planes, bits) == (1, 32)
        assert data[offset : offset + 8] == b"\x89PNG\r\n\x1a\n", "each image is a PNG"
        assert offset + length <= len(data)


def test_self_check_passes(app):
    lines: list[str] = []
    assert selfcheck.run(lines.append) == 0, lines
    assert lines[-1] == "PASSED"
    assert [line.split(" - ")[0].split(None, 1)[1] for line in lines[1:-1]] == [
        "yt-dlp", "ffmpeg", "site fixes", "icon", "plugin loading", "main window",
    ]


def test_self_check_reports_failures(app, monkeypatch):
    monkeypatch.setattr("universal_downloader.core.find_ffmpeg", lambda: None)
    lines: list[str] = []
    assert selfcheck.run(lines.append) == 1
    assert any(line.startswith("FAIL ffmpeg") for line in lines)
    assert lines[-1] == "1 CHECK(S) FAILED"


def test_smoke_test_flag_writes_a_log_and_exit_code(app, tmp_path, monkeypatch):
    log = tmp_path / "smoke.log"
    monkeypatch.setenv("UD_SMOKE_LOG", str(log))
    assert main(["universal-downloader", "--smoke-test"]) == 0
    assert "PASSED" in log.read_text()


def test_self_check_leaves_no_trace_in_user_plugin_dirs(app):
    from yt_dlp.globals import plugin_dirs

    before = list(plugin_dirs.value)
    selfcheck.run(lambda line: None)
    assert plugin_dirs.value == before


def test_search_results_cannot_inject_links_or_paths(tmp_path, server, media_dir, monkeypatch):
    import urllib.request

    from universal_downloader.core import plugins as plugins_module
    from universal_downloader.core import search_topic

    hostile = {
        "items": [
            {"full_name": "fine/plugin", "html_url": "file:///etc/passwd", "stargazers_count": 1},
            {"full_name": "../../etc/passwd", "stargazers_count": 1},
            {"full_name": "a/b/c", "stargazers_count": 1},
            {"full_name": "bad name/plugin", "stargazers_count": 1},
            {"full_name": 12345, "stargazers_count": 1},
            {"stargazers_count": 1},
        ]
    }
    (media_dir / "gh2" / "search").mkdir(parents=True, exist_ok=True)
    (media_dir / "gh2" / "search" / "repositories").write_text(json.dumps(hostile))
    monkeypatch.setattr(plugins_module, "GITHUB_API", f"{server}/gh2")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    found = search_topic(opener)
    assert [r.full_name for r in found] == ["fine/plugin"]
    assert found[0].url == "https://github.com/fine/plugin", "the link is built, not copied from the reply"
