"""Install, remove and load yt-dlp plugins.

yt-dlp plugins are plain Python packages that live in a ``yt_dlp_plugins``
namespace. Rather than needing pip (which is not available inside the packaged
executable), a plugin archive is downloaded and its ``yt_dlp_plugins`` folder
is unpacked into a directory owned by this app, which yt-dlp is then told to
search::

    <root>/<plugin id>/plugin.json
    <root>/<plugin id>/yt_dlp_plugins/...

Plugins are third-party code and run with the app's permissions.
"""

from __future__ import annotations

import importlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_UNPACKED_BYTES = 25 * 1024 * 1024
MAX_FILES = 500
_PACKAGE = "yt_dlp_plugins"


class PluginError(Exception):
    """A plugin could not be installed; the message is safe to show a user."""


@dataclass(frozen=True)
class CatalogEntry:
    """A plugin known to work with this app, pinned to an exact revision."""

    id: str
    name: str
    author: str
    description: str
    homepage: str
    #: Zip archive of one specific commit, so what gets installed never changes.
    archive_url: str
    revision: str
    license: str = ""
    #: Third-party service the plugin contacts, shown to the user before install.
    contacts: str = ""
    #: yt-dlp postprocessor entries to enable while the plugin is installed.
    #: Extractor plugins need none: yt-dlp picks them up by itself.
    postprocessors: tuple[dict[str, Any], ...] = ()


def _github_archive(repo: str, revision: str) -> str:
    return f"https://github.com/{repo}/archive/{revision}.zip"


#: Taken from yt-dlp's own plugin list (https://github.com/yt-dlp/yt-dlp/wiki/Plugins).
#: Only plugins that do something useful in this app are listed; anything else
#: can still be installed from its zip archive.
CATALOG: tuple[CatalogEntry, ...] = (
    CatalogEntry(
        id="fixup-mtime",
        name="Upload date as file date",
        author="bradenhilton",
        description=(
            "Sets each downloaded file's modified date to the day the video was "
            "uploaded instead of the day you downloaded it, so folders sort by "
            "release date."
        ),
        homepage="https://github.com/bradenhilton/yt-dlp-FixupMtime",
        archive_url=_github_archive(
            "bradenhilton/yt-dlp-FixupMtime", "26a377bee778e20b7405776d303f206320402502"
        ),
        revision="26a377bee778e20b7405776d303f206320402502",
        license="Unlicense",
        postprocessors=(
            {"key": "FixupMtime", "when": "post_process", "mtime_key": "upload_date"},
        ),
    ),
    CatalogEntry(
        id="dearrow",
        name="DeArrow titles",
        author="QuantumWarpCode",
        description=(
            "Names YouTube downloads with the community-written DeArrow title "
            "when one exists, replacing clickbait titles with descriptive ones."
        ),
        homepage="https://github.com/QuantumWarpCode/yt-dlp-dearrow",
        archive_url=_github_archive(
            "QuantumWarpCode/yt-dlp-dearrow", "2e46eca7b2242d8c9765bf2d12f92270b694be64"
        ),
        revision="2e46eca7b2242d8c9765bf2d12f92270b694be64",
        license="MIT",
        contacts="sponsor.ajay.app",
        postprocessors=({"key": "DeArrow", "when": "pre_process"},),
    ),
)


@dataclass(frozen=True)
class InstalledPlugin:
    id: str
    name: str
    source: str
    revision: str = ""
    postprocessors: tuple[dict[str, Any], ...] = ()
    path: Path = field(default=Path(), compare=False)


def default_plugins_dir() -> Path:
    """Per-user folder where this app keeps the plugins it installs."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "YTDownloader" / "plugins"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "YTDownloader" / "plugins"
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "yt-downloader" / "plugins"


def slug(text: str) -> str:
    """A safe folder name derived from ``text``."""
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value[:60] or "plugin"


def _name_from_source(source: str) -> str:
    """Best human name for a custom archive: the GitHub repo, else the file name."""
    match = re.match(r"https?://(?:codeload\.)?github\.com/[^/]+/([^/]+)/", source)
    if match:
        return match.group(1)
    stem = PurePosixPath(source.replace("\\", "/").split("?")[0]).name
    return re.sub(r"\.(zip|whl)$", "", stem, flags=re.I) or "plugin"


def _plugin_members(archive: zipfile.ZipFile) -> tuple[str, list[zipfile.ZipInfo]]:
    """Find the ``yt_dlp_plugins`` folder in ``archive``.

    Returns the prefix in front of it (GitHub archives nest everything inside
    ``<repo>-<revision>/``) and the entries under it.
    """
    prefixes = set()
    for info in archive.infolist():
        parts = PurePosixPath(info.filename).parts
        if _PACKAGE in parts and info.filename.endswith(".py"):
            index = parts.index(_PACKAGE)
            prefixes.add("".join(f"{p}/" for p in parts[:index]))
    if not prefixes:
        raise PluginError("This archive is not a yt-dlp plugin (no yt_dlp_plugins folder).")
    prefix = min(prefixes, key=lambda p: (p.count("/"), p))
    root = f"{prefix}{_PACKAGE}/"
    members = [i for i in archive.infolist() if i.filename.startswith(root) and not i.is_dir()]
    return prefix, members


def _extract(data: bytes, destination: Path) -> None:
    """Unpack only the ``yt_dlp_plugins`` folder of a zip into ``destination``."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise PluginError("This file is not a zip archive.") from exc
    with archive:
        prefix, members = _plugin_members(archive)
        if len(members) > MAX_FILES:
            raise PluginError("This archive contains too many files.")
        if sum(m.file_size for m in members) > MAX_UNPACKED_BYTES:
            raise PluginError("This archive is too large once unpacked.")
        for member in members:
            relative = PurePosixPath(member.filename[len(prefix):])
            # Never write outside the destination, whatever the archive says.
            if relative.is_absolute() or ".." in relative.parts or "\\" in member.filename:
                raise PluginError("This archive contains unsafe file paths.")
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


class PluginManager:
    """Owns one plugin directory and keeps yt-dlp pointed at it."""

    def __init__(self, root: Path | None = None, opener: urllib.request.OpenerDirector | None = None) -> None:
        self.root = Path(root) if root else default_plugins_dir()
        self._opener = opener or urllib.request.build_opener()
        #: True once something was removed that yt-dlp keeps loaded until exit.
        self.needs_restart = False

    # -- queries ---------------------------------------------------------------

    def installed(self) -> list[InstalledPlugin]:
        plugins = []
        if not self.root.is_dir():
            return plugins
        for folder in sorted(self.root.iterdir()):
            try:
                meta = json.loads((folder / "plugin.json").read_text(encoding="utf-8"))
                plugins.append(
                    InstalledPlugin(
                        id=folder.name,
                        name=str(meta["name"]),
                        source=str(meta.get("source", "")),
                        revision=str(meta.get("revision", "")),
                        postprocessors=tuple(dict(p) for p in meta.get("postprocessors", [])),
                        path=folder,
                    )
                )
            except (OSError, ValueError, KeyError, TypeError):
                continue  # Not one of ours, or damaged: ignore it.
        return plugins

    def is_installed(self, plugin_id: str) -> bool:
        return any(p.id == plugin_id for p in self.installed())

    def postprocessors(self) -> list[dict[str, Any]]:
        """yt-dlp postprocessor entries for every installed plugin."""
        return [dict(pp) for plugin in self.installed() for pp in plugin.postprocessors]

    # -- changes ---------------------------------------------------------------

    def install(self, entry: CatalogEntry) -> InstalledPlugin:
        """Download and install a plugin from the catalog."""
        return self._install(
            entry.id, entry.name, entry.archive_url, entry.revision, entry.postprocessors
        )

    def install_archive(self, source: str) -> InstalledPlugin:
        """Install a plugin from a zip file on disk or an http(s) link to one."""
        source = source.strip()
        name = _name_from_source(source)
        return self._install(slug(name), name, source, "", ())

    def remove(self, plugin_id: str) -> None:
        for plugin in self.installed():
            if plugin.id == plugin_id:
                shutil.rmtree(plugin.path, ignore_errors=True)
                # Postprocessors only run when we ask for them, so they are
                # gone at once; anything else stays imported until restart.
                if not plugin.postprocessors:
                    self.needs_restart = True

    def _install(self, plugin_id, name, source, revision, postprocessors) -> InstalledPlugin:
        data = self._read(source)
        self.root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".installing-", dir=self.root))
        try:
            _extract(data, staging)
            meta = {
                "name": name,
                "source": source,
                "revision": revision,
                "postprocessors": list(postprocessors),
            }
            (staging / "plugin.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
            target = self.root / plugin_id
            if target.exists():
                shutil.rmtree(target)
            os.replace(staging, target)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        self.activate()
        return InstalledPlugin(plugin_id, name, source, revision, tuple(postprocessors), target)

    def _read(self, source: str) -> bytes:
        if re.match(r"https?://", source, flags=re.I):
            try:
                with self._opener.open(source, timeout=30) as response:
                    data = response.read(MAX_ARCHIVE_BYTES + 1)
            except Exception as exc:
                raise PluginError(f"Could not download the plugin: {exc}") from exc
        elif "://" in source:
            raise PluginError("Only http(s) links and local zip files can be installed.")
        else:
            try:
                path = Path(source).expanduser()
                if path.stat().st_size > MAX_ARCHIVE_BYTES:
                    raise PluginError("This archive is too large.")
                data = path.read_bytes()
            except OSError as exc:
                raise PluginError(f"Could not read the file: {exc.strerror or exc}") from exc
        if len(data) > MAX_ARCHIVE_BYTES:
            raise PluginError("This archive is too large.")
        return data

    # -- yt-dlp integration ----------------------------------------------------

    def activate(self) -> None:
        """Make yt-dlp search this directory and (re)load all plugins."""
        from yt_dlp.globals import plugin_dirs
        from yt_dlp.plugins import load_all_plugins

        self.root.mkdir(parents=True, exist_ok=True)
        for leftover in self.root.glob(".installing-*"):
            shutil.rmtree(leftover, ignore_errors=True)
        root = str(self.root)
        if root not in plugin_dirs.value:
            plugin_dirs.value = [*plugin_dirs.value, root]
        # Forget the cached namespace packages so new folders are discovered.
        importlib.invalidate_caches()
        load_all_plugins()


def describe(plugin: InstalledPlugin | CatalogEntry) -> dict[str, Any]:
    """Plain-dict view, handy for logging and tests."""
    data = asdict(plugin)
    data.pop("path", None)
    return data
