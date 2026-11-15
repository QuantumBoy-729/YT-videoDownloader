"""Browsing and installing plugins from GitHub, against a local imitation of its API."""

from __future__ import annotations

import http.server
import json
import threading
import time
import urllib.request

import pytest

from universal_downloader.core import PluginError, PluginManager, RepoInfo, search_topic
from universal_downloader.core import plugins as plugins_module
from universal_downloader.core.plugins import github_archive_url

from .test_plugins import make_zip, pp_zip

EXTRACTOR_ONLY = make_zip(
    {"src/yt_dlp_plugins/extractor/site.py": "x = 1"}, prefix="someone-site-plugin-0a1b2c3d4e5f/"
)

SEARCH_RESULT = {
    "total_count": 4,
    "items": [
        {
            "full_name": "someone/site-plugin", "description": "Adds a site", "stargazers_count": 120,
            "pushed_at": "2026-10-30T12:00:00Z", "license": {"spdx_id": "MIT"},
            "default_branch": "main", "html_url": "https://github.com/someone/site-plugin",
        },
        {"full_name": "other/dead-plugin", "archived": True, "stargazers_count": 999},
        {
            "full_name": "other/pp-plugin", "description": None, "stargazers_count": 3,
            "pushed_at": None, "license": None, "default_branch": None,
        },
        "garbage",
    ],
}


@pytest.fixture
def api(server, media_dir, monkeypatch) -> str:
    """Local stand-in for api.github.com, served from the shared test server."""
    root = media_dir / "gh"
    (root / "search").mkdir(parents=True, exist_ok=True)
    (root / "search" / "repositories").write_text(json.dumps(SEARCH_RESULT))
    for repo, data in (("someone/site-plugin", EXTRACTOR_ONLY), ("other/pp-plugin", pp_zip("Other"))):
        folder = root / "repos" / repo / "zipball"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "main").write_bytes(data)
        # No branch given: GitHub serves the default branch. Directories serve index.html here.
        (folder / "index.html").write_bytes(data)
    monkeypatch.setattr(plugins_module, "GITHUB_API", f"{server}/gh")
    return f"{server}/gh"


@pytest.fixture
def manager(tmp_path) -> PluginManager:
    return PluginManager(tmp_path / "plugins", opener=urllib.request.build_opener(urllib.request.ProxyHandler({})))


def test_search_parses_and_skips_archived_and_junk(api, manager):
    found = search_topic(manager.opener)
    assert [r.full_name for r in found] == ["someone/site-plugin", "other/pp-plugin"]
    first, second = found
    assert (first.stars, first.pushed, first.license, first.default_branch) == (120, "2026-10-30", "MIT", "main")
    assert first.id == "someone-site-plugin" and first.owner == "someone" and first.name == "site-plugin"
    assert (second.description, second.pushed, second.license, second.default_branch) == ("", "", "", "HEAD")
    assert second.url == "https://github.com/other/pp-plugin"


class _Limited(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(403)
        self.send_header("X-RateLimit-Remaining", "0")
        self.send_header("X-RateLimit-Reset", str(int(time.time()) + 600))
        self.send_header("Content-Length", "0")
        self.end_headers()


def test_rate_limit_is_explained(monkeypatch, manager):
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Limited)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setattr(plugins_module, "GITHUB_API", f"http://127.0.0.1:{httpd.server_address[1]}")
    try:
        with pytest.raises(PluginError, match=r"limit.*about (9|10) minutes"):
            search_topic(manager.opener)
    finally:
        httpd.shutdown()


def test_unreachable_github_is_explained(monkeypatch, manager):
    monkeypatch.setattr(plugins_module, "GITHUB_API", "http://127.0.0.1:9")
    with pytest.raises(PluginError, match="Could not reach GitHub"):
        search_topic(manager.opener)


def test_bad_reply_is_explained(api, media_dir, manager):
    (media_dir / "gh" / "search" / "repositories").write_text("<html>nope")
    with pytest.raises(PluginError, match="could not read"):
        search_topic(manager.opener)


def test_install_from_repo_records_commit_and_kind(api, manager):
    plugin = manager.install_github("someone/site-plugin", "main")
    assert plugin.id == "someone-site-plugin"
    assert plugin.revision == "0a1b2c3d4e5f", "taken from the archive's folder name"
    assert plugin.kinds == ("extractor",)
    # The src/ layout is flattened so yt-dlp can find the package.
    assert (manager.root / "someone-site-plugin" / "yt_dlp_plugins" / "extractor" / "site.py").is_file()

    again = manager.installed()[0]
    assert (again.revision, again.kinds) == ("0a1b2c3d4e5f", ("extractor",))


def test_postprocessor_plugin_from_repo_is_installed_but_not_enabled(api, manager):
    plugin = manager.install_github("other/pp-plugin")
    assert plugin.kinds == ("postprocessor",)
    assert manager.postprocessors() == []


@pytest.mark.parametrize("name", ["nope", "a/b/c", "a b/c", "../x/y", ""])
def test_repo_names_are_validated(manager, name):
    with pytest.raises(PluginError, match="valid GitHub repository"):
        manager.install_github(name)


@pytest.mark.parametrize(
    "link, name, ref",
    [
        ("https://github.com/someone/site-plugin", "site-plugin", ""),
        ("https://github.com/someone/site-plugin/", "site-plugin", ""),
        ("https://github.com/someone/site-plugin.git", "site-plugin", ""),
        ("https://www.github.com/someone/site-plugin?tab=readme", "site-plugin", ""),
        ("https://github.com/someone/site-plugin/tree/dev", "site-plugin", "/dev"),
    ],
)
def test_repo_page_links_become_archive_links(link, name, ref):
    url, owner, found = github_archive_url(link)
    assert (owner, found) == ("someone", name)
    assert url == f"{plugins_module.GITHUB_API}/repos/someone/site-plugin/zipball{ref}"


@pytest.mark.parametrize(
    "link",
    [
        "https://github.com/topics/yt-dlp-plugins",
        "https://github.com/someone/site-plugin/archive/master.zip",
        "https://github.com/someone",
        "https://example.com/someone/site-plugin",
        "plugin.zip",
    ],
)
def test_other_links_are_left_alone(link):
    assert github_archive_url(link) is None


def test_pasting_a_repo_page_installs_it(api, manager):
    plugin = manager.install_archive("https://github.com/someone/site-plugin/tree/main")
    assert (plugin.id, plugin.kinds) == ("someone-site-plugin", ("extractor",))


def test_same_repo_name_from_two_authors_does_not_clash():
    a, b = RepoInfo("one/yt-dlp-plugins"), RepoInfo("two/yt-dlp-plugins")
    assert a.id != b.id
