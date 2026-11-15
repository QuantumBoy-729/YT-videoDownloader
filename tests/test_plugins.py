"""Plugin installation and loading, using small plugins built on the fly."""

from __future__ import annotations

import io
import urllib.request
import zipfile

import pytest

from universal_downloader.core import (
    CATALOG,
    CatalogEntry,
    DownloadJob,
    DownloadRequest,
    JobState,
    PluginError,
    PluginManager,
    build_options,
    fetch_info,
)
from universal_downloader.core import plugins as plugins_module

from .conftest import NO_PROXY

POSTPROCESSOR = '''
from yt_dlp.postprocessor.common import PostProcessor

class {name}PP(PostProcessor):
    def __init__(self, downloader=None, text="ran"):
        super().__init__(downloader)
        self._text = text

    def run(self, info):
        with open(info["filepath"] + ".{name}", "w") as f:
            f.write(self._text)
        return [], info
'''

EXTRACTOR = '''
from yt_dlp.extractor.common import InfoExtractor

class PluginTestIE(InfoExtractor):
    _VALID_URL = r"plugintest:(?P<id>\\w+)"

    def _real_extract(self, url):
        return {{"id": self._match_id(url), "title": "From a plugin", "url": "{media}", "ext": "mp4"}}
'''


def make_zip(files: dict[str, str], prefix: str = "some-plugin-abc123/") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(prefix + name, content)
    return buffer.getvalue()


def pp_zip(name: str) -> bytes:
    return make_zip(
        {
            "README.md": "docs",
            "setup.py": "raise SystemExit('must never run')",
            f"yt_dlp_plugins/postprocessor/{name.lower()}.py": POSTPROCESSOR.format(name=name),
        }
    )


def entry(plugin_id: str, url: str, name: str) -> CatalogEntry:
    return CatalogEntry(
        id=plugin_id, name=name, author="tests", description="", homepage="",
        archive_url=url, revision="abc123",
        postprocessors=({"key": name, "when": "post_process", "text": "hello"},),
    )


@pytest.fixture
def manager(tmp_path) -> PluginManager:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return PluginManager(tmp_path / "plugins", opener=opener)


def test_catalog_is_pinned_and_consistent():
    assert len({e.id for e in CATALOG}) == len(CATALOG)
    for e in CATALOG:
        assert e.archive_url.startswith("https://github.com/")
        assert len(e.revision) == 40 and e.revision in e.archive_url, "must pin an exact commit"
        assert e.id == plugins_module.slug(e.id)
        assert e.name and e.description and e.homepage.startswith("https://")


def test_install_from_file_unpacks_only_the_plugin_package(manager, tmp_path):
    archive = tmp_path / "My-Plugin.zip"
    archive.write_bytes(pp_zip("FromFile"))
    plugin = manager.install_archive(str(archive))

    assert plugin.id == "my-plugin" and plugin.name == "My-Plugin"
    folder = manager.root / "my-plugin"
    assert sorted(p.name for p in folder.iterdir()) == ["plugin.json", "yt_dlp_plugins"]
    assert (folder / "yt_dlp_plugins" / "postprocessor" / "fromfile.py").is_file()
    assert [p.id for p in manager.installed()] == ["my-plugin"]
    assert manager.is_installed("my-plugin")
    assert not list(manager.root.glob(".installing-*"))


def test_install_from_url(manager, server, media_dir):
    (media_dir / "plugin.zip").write_bytes(pp_zip("FromUrl"))
    plugin = manager.install(entry("from-url", f"{server}/plugin.zip", "FromUrl"))
    assert plugin.revision == "abc123"
    assert manager.postprocessors() == [{"key": "FromUrl", "when": "post_process", "text": "hello"}]


def test_github_style_names():
    name = plugins_module._name_from_source
    assert name("https://github.com/someone/yt-dlp-thing/archive/master.zip") == "yt-dlp-thing"
    assert name("C:\\Users\\me\\Downloads\\cool_plugin.ZIP") == "cool_plugin"
    assert plugins_module.slug("Cool Plugin!!") == "cool-plugin"
    assert plugins_module.slug("../..") == "plugin"


@pytest.mark.parametrize(
    "data, message",
    [
        (b"this is not a zip", "not a zip"),
        (make_zip({"README.md": "x", "thing.py": "x"}), "not a yt-dlp plugin"),
        (make_zip({"yt_dlp_plugins/../../evil.py": "x"}), "unsafe"),
        (make_zip({"yt_dlp_plugins/a.py": "x", "yt_dlp_plugins/..\\evil.py": "x"}), "unsafe"),
    ],
)
def test_bad_archives_are_rejected_cleanly(manager, tmp_path, data, message):
    archive = tmp_path / "bad.zip"
    archive.write_bytes(data)
    with pytest.raises(PluginError, match=message):
        manager.install_archive(str(archive))
    assert manager.installed() == []
    assert not (tmp_path / "evil.py").exists()
    assert not manager.root.exists() or list(manager.root.iterdir()) == []


def test_size_limits(manager, tmp_path, monkeypatch):
    archive = tmp_path / "big.zip"
    archive.write_bytes(pp_zip("Big"))
    monkeypatch.setattr(plugins_module, "MAX_UNPACKED_BYTES", 10)
    with pytest.raises(PluginError, match="too large once unpacked"):
        manager.install_archive(str(archive))
    monkeypatch.setattr(plugins_module, "MAX_ARCHIVE_BYTES", 10)
    with pytest.raises(PluginError, match="too large"):
        manager.install_archive(str(archive))
    assert manager.installed() == []


@pytest.mark.parametrize("source", ["ftp://example.com/p.zip", "file:///etc/passwd"])
def test_only_http_links_and_files(manager, source):
    with pytest.raises(PluginError, match="Only http"):
        manager.install_archive(source)


def test_download_and_missing_file_errors(manager, server, tmp_path):
    with pytest.raises(PluginError, match="Could not download"):
        manager.install_archive(f"{server}/nope.zip")
    with pytest.raises(PluginError, match="Could not read"):
        manager.install_archive(str(tmp_path / "nope.zip"))


def test_failed_reinstall_keeps_working_copy(manager, tmp_path):
    good = tmp_path / "thing.zip"
    good.write_bytes(pp_zip("Keep"))
    manager.install_archive(str(good))
    good.write_bytes(b"corrupted")
    with pytest.raises(PluginError):
        manager.install_archive(str(good))
    assert (manager.root / "thing" / "yt_dlp_plugins" / "postprocessor" / "keep.py").is_file()


def test_remove(manager, tmp_path, server, media_dir):
    (media_dir / "rm.zip").write_bytes(pp_zip("Removable"))
    manager.install(entry("removable", f"{server}/rm.zip", "Removable"))
    manager.remove("removable")
    assert manager.installed() == [] and manager.postprocessors() == []
    assert not manager.needs_restart, "postprocessor plugins stop at once"

    custom = tmp_path / "custom.zip"
    custom.write_bytes(pp_zip("Custom"))
    manager.install_archive(str(custom))
    manager.remove("custom")
    assert manager.needs_restart, "other plugins stay loaded until exit"
    manager.remove("never-installed")  # No error.


def test_installed_ignores_foreign_folders(manager):
    (manager.root / "junk").mkdir(parents=True)
    (manager.root / "broken").mkdir()
    (manager.root / "broken" / "plugin.json").write_text("{not json")
    (manager.root / "stray.txt").write_text("x")
    assert manager.installed() == []
    manager.activate()  # Must cope with them too.


def test_plugin_postprocessors_are_appended_to_options(tmp_path):
    request = DownloadRequest(url="http://x", output_dir=tmp_path)
    extra = [{"key": "Thing", "when": "pre_process"}]
    opts = build_options(request, "ffmpeg", extra)
    assert opts["postprocessors"][-1] == extra[0]
    assert opts["postprocessors"][-1] is not extra[0]
    assert build_options(request, None, extra)["postprocessors"] == extra


def test_installed_postprocessors_run_during_download(manager, server, media_dir, tmp_path):
    (media_dir / "first.zip").write_bytes(pp_zip("FirstMarker"))
    (media_dir / "second.zip").write_bytes(pp_zip("SecondMarker"))

    def download(name):
        job = DownloadJob(
            DownloadRequest(url=f"{server}/clip.mp4", output_dir=tmp_path / name),
            extra_opts=NO_PROXY,
            plugin_postprocessors=manager.postprocessors(),
        )
        result = job.run()
        assert result.state is JobState.DONE, result.error
        return sorted(p.suffix for p in (tmp_path / name).iterdir())

    manager.install(entry("first", f"{server}/first.zip", "FirstMarker"))
    assert download("one") == [".FirstMarker", ".mp4"]

    # Installing another plugin later, in the same session, must also work.
    manager.install(entry("second", f"{server}/second.zip", "SecondMarker"))
    assert download("two") == [".FirstMarker", ".SecondMarker", ".mp4"]
    assert (next((tmp_path / "two").glob("*.SecondMarker"))).read_text() == "hello"

    manager.remove("first")
    assert download("three") == [".SecondMarker", ".mp4"]


def test_installed_extractor_plugin_is_used(manager, server, tmp_path):
    archive = tmp_path / "site-support.zip"
    archive.write_bytes(
        make_zip({"yt_dlp_plugins/extractor/plugintest.py": EXTRACTOR.format(media=f"{server}/clip.mp4")})
    )
    with pytest.raises(RuntimeError):
        fetch_info("plugintest:abc", extra_opts=NO_PROXY)

    manager.install_archive(str(archive))
    assert fetch_info("plugintest:abc", extra_opts=NO_PROXY).title == "From a plugin"

    job = DownloadJob(
        DownloadRequest(url="plugintest:abc", output_dir=tmp_path / "out"), extra_opts=NO_PROXY
    )
    result = job.run()
    assert result.state is JobState.DONE, result.error
    assert result.files[0].name.startswith("From a plugin")
