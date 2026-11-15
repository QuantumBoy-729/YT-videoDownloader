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

import ast
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
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from yt_dlp.utils import POSTPROCESS_WHEN

MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_UNPACKED_BYTES = 25 * 1024 * 1024
MAX_FILES = 500
_PACKAGE = "yt_dlp_plugins"
#: GitHub's REST API. Changed by tests to point at a local imitation.
GITHUB_API = "https://api.github.com"
USER_AGENT = "UniversalDownloader"
_GITHUB_REPO = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?"
    r"(?:/tree/(?P<ref>[^/?#]+))?/?(?:[?#].*)?$"
)
_NOT_OWNERS = {"topics", "orgs", "settings", "marketplace", "sponsors", "features", "about"}


class PluginError(Exception):
    """A plugin could not be installed or set up; the message is safe to show a user."""


#: When a processing step runs, with a plain description for each yt-dlp stage.
WHEN_LABELS: dict[str, str] = {
    "post_process": "After each download finishes",
    "after_move": "After the file is moved to its folder",
    "before_dl": "Before each download starts",
    "pre_process": "Right after the video is looked up",
    "after_filter": "After the video passes your filters",
    "video": "After the quality is chosen",
    "after_video": "After all formats of a video are done",
    "playlist": "At the end of a playlist",
}
assert set(WHEN_LABELS) == set(POSTPROCESS_WHEN), "yt-dlp changed its processing stages"
DEFAULT_WHEN = "post_process"
_OPTION_NAME = re.compile(r"[A-Za-z_]\w*")


def parse_options(text: str) -> dict[str, str]:
    """Read ``name=value; name=value`` (yt-dlp's own style) into a dict."""
    options: dict[str, str] = {}
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        name, separator, value = part.partition("=")
        name = name.strip()
        if not separator or not _OPTION_NAME.fullmatch(name) or name in ("key", "when"):
            raise PluginError(
                f'Could not read "{part}". Write options as name=value, separated by semicolons.'
            )
        options[name] = value.strip()
    return options


def format_options(options: dict[str, str]) -> str:
    return "; ".join(f"{name}={value}" for name, value in options.items())


def _clean_step(raw: Any) -> dict[str, Any]:
    """Normalise one stored processing-step setting."""
    raw = raw if isinstance(raw, dict) else {}
    when = raw.get("when")
    options = raw.get("options")
    return {
        "enabled": bool(raw.get("enabled")),
        "when": when if when in POSTPROCESS_WHEN else DEFAULT_WHEN,
        "options": {str(k): str(v) for k, v in options.items()} if isinstance(options, dict) else {},
    }


def _step_from_entry(entry: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Turn a yt-dlp postprocessor entry into a stored, enabled step setting."""
    options = {str(k): str(v) for k, v in entry.items() if k not in ("key", "when")}
    return str(entry["key"]), _clean_step({"enabled": True, "when": entry.get("when"), "options": options})


def find_postprocessor_keys(folder: Path) -> list[str]:
    """Names of the processing steps a plugin provides, found without running it.

    yt-dlp loads a step from every class named ``<Key>PP`` under the plugin's
    ``postprocessor`` package, and refers to it as ``<Key>``.
    """
    keys: list[str] = []
    for path in sorted((folder / _PACKAGE / "postprocessor").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, ValueError, OSError):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ClassDef)
                and node.name.endswith("PP")
                and len(node.name) > 2
                and not node.name.startswith("_")
                and node.name[:-2] not in keys
            ):
                keys.append(node.name[:-2])
    return keys


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
    #: What the plugin adds: "extractor" (sites / YouTube features) and/or "postprocessor".
    kinds: tuple[str, ...] = ()
    #: Processing steps the plugin provides, and the user's settings for each:
    #: ``{"enabled": bool, "when": stage, "options": {name: value}}``.
    pp_keys: tuple[str, ...] = ()
    pp_config: dict[str, dict[str, Any]] = field(default_factory=dict, compare=False)
    path: Path = field(default=Path(), compare=False)


def default_plugins_dir() -> Path:
    """Per-user folder where this app keeps the plugins it installs."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "UniversalDownloader" / "plugins"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "UniversalDownloader" / "plugins"
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "universal-downloader" / "plugins"


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


def github_archive_url(source: str) -> tuple[str, str, str] | None:
    """For a github.com repository page: the API link to its zip, the owner and the repo name.

    ``https://github.com/owner/repo`` (optionally ``/tree/<branch>``) becomes the
    zip of that branch, or of the default branch when none is given.
    """
    match = _GITHUB_REPO.match(source.strip())
    if not match or match["owner"].lower() in _NOT_OWNERS:
        return None
    ref = f"/{match['ref']}" if match["ref"] else ""
    return f"{GITHUB_API}/repos/{match['owner']}/{match['repo']}/zipball{ref}", match["owner"], match["repo"]


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


def _extract(data: bytes, destination: Path) -> tuple[list[str], str]:
    """Unpack only the ``yt_dlp_plugins`` folder of a zip into ``destination``.

    Returns the kinds of plugin found ("extractor", "postprocessor") and the
    archive's top-level folder name (GitHub puts the commit hash in it).
    """
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
        kinds = sorted(
            {
                PurePosixPath(m.filename[len(prefix):]).parts[1]
                for m in members
                if len(PurePosixPath(m.filename[len(prefix):]).parts) > 2
                and PurePosixPath(m.filename[len(prefix):]).parts[1] in ("extractor", "postprocessor")
            }
        )
        return kinds, prefix.strip("/").split("/")[0]


class PluginManager:
    """Owns one plugin directory and keeps yt-dlp pointed at it."""

    def __init__(self, root: Path | None = None, opener: urllib.request.OpenerDirector | None = None) -> None:
        self.root = Path(root) if root else default_plugins_dir()
        if opener is None:
            opener = urllib.request.build_opener()
            opener.addheaders = [("User-Agent", USER_AGENT)]
        self._opener = opener
        #: True once something was removed that yt-dlp keeps loaded until exit.
        self.needs_restart = False

    @property
    def opener(self) -> urllib.request.OpenerDirector:
        return self._opener

    # -- queries ---------------------------------------------------------------

    def installed(self) -> list[InstalledPlugin]:
        plugins = []
        if not self.root.is_dir():
            return plugins
        for folder in sorted(self.root.iterdir()):
            try:
                plugins.append(self._load(folder))
            except (OSError, ValueError, KeyError, TypeError):
                continue  # Not one of ours, or damaged: ignore it.
        return plugins

    @staticmethod
    def _load(folder: Path) -> InstalledPlugin:
        meta = json.loads((folder / "plugin.json").read_text(encoding="utf-8"))
        config = {str(k): _clean_step(v) for k, v in (meta.get("pp_config") or {}).items()}
        if not config:
            # Older installs stored the enabled entries directly.
            config = dict(_step_from_entry(e) for e in meta.get("postprocessors", []))
        keys = list(dict.fromkeys([*map(str, meta.get("pp_keys", [])), *config]))
        for key in keys:
            config.setdefault(key, _clean_step({}))
        entries = tuple(
            {"key": key, "when": config[key]["when"], **config[key]["options"]}
            for key in keys
            if config[key]["enabled"]
        )
        return InstalledPlugin(
            id=folder.name,
            name=str(meta["name"]),
            source=str(meta.get("source", "")),
            revision=str(meta.get("revision", "")),
            postprocessors=entries,
            kinds=tuple(str(k) for k in meta.get("kinds", [])),
            pp_keys=tuple(keys),
            pp_config=config,
            path=folder,
        )

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
        github = github_archive_url(source)
        if github:
            source, owner, name = github
            # Two authors can publish plugins with the same repository name.
            return self._install(slug(f"{owner}-{name}"), f"{owner}/{name}", source, "", ())
        name = _name_from_source(source)
        return self._install(slug(name), name, source, "", ())

    def install_github(self, full_name: str, ref: str = "") -> InstalledPlugin:
        """Install a plugin from a GitHub repository (``owner/name``)."""
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", full_name):
            raise PluginError("That is not a valid GitHub repository name.")
        owner, repo = full_name.split("/")
        url = f"{GITHUB_API}/repos/{owner}/{repo}/zipball" + (f"/{ref}" if ref else "")
        return self._install(slug(f"{owner}-{repo}"), full_name, url, "", ())

    def remove(self, plugin_id: str) -> None:
        for plugin in self.installed():
            if plugin.id == plugin_id:
                shutil.rmtree(plugin.path, ignore_errors=True)
                # Postprocessors only run when we ask for them, so they are
                # gone at once; anything else stays imported until restart.
                if not plugin.postprocessors:
                    self.needs_restart = True

    def configure_postprocessor(
        self,
        plugin_id: str,
        key: str,
        *,
        enabled: bool | None = None,
        when: str | None = None,
        options: dict[str, str] | None = None,
    ) -> None:
        """Switch a plugin's processing step on or off, or change when it runs and its options."""
        plugin = next((p for p in self.installed() if p.id == plugin_id), None)
        if plugin is None or key not in plugin.pp_keys:
            raise PluginError("That plugin step is not installed.")
        if when is not None and when not in POSTPROCESS_WHEN:
            raise PluginError("That is not a valid time for the step to run.")
        for name in options or {}:
            if not _OPTION_NAME.fullmatch(name) or name in ("key", "when"):
                raise PluginError(f'"{name}" is not a valid option name.')

        step = dict(plugin.pp_config[key])
        if enabled is not None:
            step["enabled"] = enabled
        if when is not None:
            step["when"] = when
        if options is not None:
            step["options"] = dict(options)
        config = {**plugin.pp_config, key: _clean_step(step)}

        meta_path = plugin.path / "plugin.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["pp_keys"] = list(plugin.pp_keys)
        meta["pp_config"] = config
        meta.pop("postprocessors", None)
        temporary = meta_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        os.replace(temporary, meta_path)

    def _install(self, plugin_id, name, source, revision, postprocessors) -> InstalledPlugin:
        data = self._read(source)
        self.root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".installing-", dir=self.root))
        try:
            kinds, top_folder = _extract(data, staging)
            if not revision:
                # GitHub names the folder <owner>-<repo>-<commit>, which pins what we got.
                found = re.search(r"-([0-9a-f]{7,40})$", top_folder)
                revision = found.group(1) if found else ""
            # Steps a catalog entry recommends start switched on; anything else
            # the plugin provides starts off until the user turns it on.
            config = dict(_step_from_entry(e) for e in postprocessors)
            keys = list(dict.fromkeys([*find_postprocessor_keys(staging), *config]))
            meta = {
                "name": name,
                "source": source,
                "revision": revision,
                "kinds": kinds,
                "pp_keys": keys,
                "pp_config": {key: config.get(key, _clean_step({})) for key in keys},
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
        return self._load(target)

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

