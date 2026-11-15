"""Thin, thread-safe wrapper around yt-dlp.

A :class:`DownloadJob` runs on whatever thread calls :meth:`DownloadJob.run`
and reports through plain callbacks, so it has no GUI dependencies.
``pause``/``resume``/``cancel`` may be called from any other thread.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, urlparse

import yt_dlp
from yt_dlp.utils import DownloadCancelled, YoutubeDLError

from .models import DownloadRequest, JobResult, JobState, MediaInfo, Progress
from .options import build_options

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_AUTO = object()


class _UserCancelled(DownloadCancelled):
    """Raised inside yt-dlp hooks to unwind a download the user cancelled."""


class _Logger:
    """Keeps yt-dlp off stdout and remembers the last error for reporting."""

    def __init__(self) -> None:
        self.last_error = ""

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        self.last_error = msg


def clean_error(message: str) -> str:
    """Turn a yt-dlp error into something short enough to show a user."""
    message = _ANSI.sub("", str(message)).strip()
    message = re.sub(r"^ERROR:\s*", "", message)
    # Drop the "please report this issue on ..." boilerplate.
    message = re.split(r";?\s*please report this issue", message, maxsplit=1)[0]
    message = re.sub(r"\s*\(caused by .*\)\s*$", "", message)
    return message.strip() or "Unknown error"


def describe_error(exc: BaseException) -> str:
    """Explain a failed lookup or download in terms a user can act on."""
    if isinstance(exc, (YoutubeDLError, OSError)):
        return clean_error(str(exc) or repr(exc))
    # Anything else is yt-dlp's site-specific code tripping over a page it no
    # longer understands (an AttributeError, KeyError, ...), which says nothing
    # useful on its own.
    return (
        "Support for this site looks out of date in the installed yt-dlp, so the "
        "link could not be read. Updating yt-dlp may fix it. "
        f"(Details: {type(exc).__name__}: {exc})"
    )


def find_ffmpeg() -> str | None:
    """Locate an ffmpeg binary: next to the app, on PATH, or from imageio-ffmpeg."""
    name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    app_dir = Path(sys.executable if getattr(sys, "frozen", False) else __file__).parent
    bundled = app_dir / name
    if bundled.is_file():
        return str(bundled)
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _has_playlist_param(url: str) -> bool:
    try:
        return bool(parse_qs(urlparse(url).query).get("list"))
    except ValueError:
        return False


def _best_thumbnail(info: dict[str, Any]) -> str:
    if info.get("thumbnail"):
        return info["thumbnail"]
    thumbs = [t for t in info.get("thumbnails") or [] if t.get("url")]
    if thumbs:
        return thumbs[-1]["url"]
    for entry in info.get("entries") or []:
        if entry:
            return _best_thumbnail(entry)
    return ""


def fetch_info(url: str, extra_opts: dict[str, Any] | None = None) -> MediaInfo:
    """Inspect ``url`` without downloading. Raises ``RuntimeError`` on failure."""
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        # List playlist entries without resolving each one - much faster.
        "extract_flat": "in_playlist",
        "socket_timeout": 30,
        "logger": _Logger(),
    }
    opts.update(extra_opts or {})
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # DownloadError, but also e.g. unsupported URL schemes.
        raise RuntimeError(describe_error(exc)) from exc
    if not info:
        raise RuntimeError("No media found at this URL")

    if info.get("_type") == "playlist":
        entries = [e for e in info.get("entries") or [] if e]
        return MediaInfo(
            url=url,
            title=info.get("title") or "Playlist",
            uploader=info.get("uploader") or info.get("channel") or "",
            thumbnail_url=_best_thumbnail(info),
            is_playlist=True,
            entry_count=info.get("playlist_count") or len(entries),
        )

    heights = sorted(
        {
            int(f["height"])
            for f in info.get("formats") or []
            if f.get("height") and f.get("vcodec") != "none"
        },
        reverse=True,
    )
    return MediaInfo(
        url=url,
        title=info.get("title") or url,
        uploader=info.get("uploader") or info.get("channel") or "",
        duration=info.get("duration"),
        thumbnail_url=_best_thumbnail(info),
        heights=tuple(heights),
        is_playlist=_has_playlist_param(url),
    )


class DownloadJob:
    """One download, with pause / resume / cancel."""

    def __init__(
        self,
        request: DownloadRequest,
        on_progress: Callable[[Progress], None] | None = None,
        on_state: Callable[[JobState], None] | None = None,
        ffmpeg_path: Any = _AUTO,
        extra_opts: dict[str, Any] | None = None,
        plugin_postprocessors: Iterable[dict[str, Any]] = (),
    ) -> None:
        self.request = request
        self._plugin_postprocessors = [dict(pp) for pp in plugin_postprocessors]
        self._on_progress = on_progress or (lambda p: None)
        self._on_state = on_state or (lambda s: None)
        self._ffmpeg = find_ffmpeg() if ffmpeg_path is _AUTO else ffmpeg_path
        self._extra_opts = extra_opts or {}

        self._state = JobState.QUEUED
        self._lock = threading.Lock()
        self._cancelled = threading.Event()
        self._unpaused = threading.Event()
        self._unpaused.set()
        self._last_emit = 0.0
        self._temp_files: set[str] = set()

    # -- control (any thread) ------------------------------------------------

    @property
    def state(self) -> JobState:
        return self._state

    def pause(self) -> None:
        """Hold the download at its next chunk. No-op unless running."""
        if self._state is JobState.RUNNING:
            self._unpaused.clear()

    def resume(self) -> None:
        self._unpaused.set()

    def cancel(self) -> None:
        """Stop as soon as possible and discard partial files."""
        self._cancelled.set()
        self._unpaused.set()
        with self._lock:
            if self._state is JobState.QUEUED:
                self._set_state_locked(JobState.CANCELLED)

    # -- execution (worker thread) -------------------------------------------

    def run(self) -> JobResult:
        """Download, blocking until finished. Never raises."""
        with self._lock:
            if self._state is not JobState.QUEUED:
                return JobResult(self._state)
            self._set_state_locked(JobState.RUNNING)

        logger = _Logger()
        opts = build_options(self.request, self._ffmpeg, self._plugin_postprocessors)
        opts["logger"] = logger
        opts["progress_hooks"] = [self._progress_hook]
        opts["postprocessor_hooks"] = [self._postprocessor_hook]
        opts.update(self._extra_opts)

        try:
            self.request.output_dir.mkdir(parents=True, exist_ok=True)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.request.url, download=True)
            files = self._collect_files(info)
            if self._cancelled.is_set():
                raise _UserCancelled()
            if not files:
                return self._finish(
                    JobState.FAILED,
                    error=clean_error(logger.last_error or "Nothing was downloaded"),
                )
            return self._finish(JobState.DONE, files=files)
        except DownloadCancelled:
            self._remove_temp_files()
            return self._finish(JobState.CANCELLED)
        except Exception as exc:  # yt-dlp raises many types; report them all.
            if self._cancelled.is_set():
                self._remove_temp_files()
                return self._finish(JobState.CANCELLED)
            return self._finish(JobState.FAILED, error=describe_error(exc))

    # -- internals -------------------------------------------------------------

    def _set_state_locked(self, state: JobState) -> None:
        if state is not self._state:
            self._state = state
            self._on_state(state)

    def _set_state(self, state: JobState) -> None:
        with self._lock:
            self._set_state_locked(state)

    def _finish(self, state: JobState, files: list[Path] | None = None, error: str = "") -> JobResult:
        self._set_state(state)
        return JobResult(state, files or [], error)

    def _checkpoint(self) -> None:
        """Called from yt-dlp hooks: honour cancel, and block while paused."""
        if self._cancelled.is_set():
            raise _UserCancelled()
        if not self._unpaused.is_set():
            self._set_state(JobState.PAUSED)
            self._unpaused.wait()
            if self._cancelled.is_set():
                raise _UserCancelled()
            self._set_state(JobState.RUNNING)

    def _stage(self, info: dict[str, Any]) -> str:
        if self.request.audio_only or info.get("vcodec") == "none":
            return "audio"
        if info.get("acodec") == "none":
            return "video"
        return "media"

    def _progress_hook(self, d: dict[str, Any]) -> None:
        if d.get("tmpfilename"):
            self._temp_files.add(d["tmpfilename"])
        self._checkpoint()

        now = time.monotonic()
        finished = d.get("status") == "finished"
        if not finished and now - self._last_emit < 0.1:
            return
        self._last_emit = now

        info = d.get("info_dict") or {}
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        downloaded = d.get("downloaded_bytes") or 0
        self._on_progress(
            Progress(
                stage=self._stage(info),
                downloaded=int(total if finished and total else downloaded),
                total=int(total) if total else None,
                speed=d.get("speed"),
                eta=d.get("eta"),
                title=info.get("title") or "",
                playlist_index=info.get("playlist_index"),
                playlist_count=info.get("n_entries") or info.get("playlist_count"),
            )
        )

    def _postprocessor_hook(self, d: dict[str, Any]) -> None:
        if self._cancelled.is_set():
            raise _UserCancelled()
        if d.get("status") == "started":
            info = d.get("info_dict") or {}
            self._on_progress(
                Progress(
                    stage="processing",
                    title=info.get("title") or "",
                    playlist_index=info.get("playlist_index"),
                    playlist_count=info.get("n_entries") or info.get("playlist_count"),
                )
            )

    @staticmethod
    def _collect_files(info: dict[str, Any] | None) -> list[Path]:
        if not info:
            return []
        items = info.get("entries") if info.get("_type") == "playlist" else [info]
        files: list[Path] = []
        for item in items or []:
            for download in (item or {}).get("requested_downloads") or []:
                path = download.get("filepath")
                if path and os.path.exists(path):
                    files.append(Path(path))
        return files

    def _remove_temp_files(self) -> None:
        for tmp in self._temp_files:
            for path in (tmp, tmp + ".ytdl"):
                try:
                    os.remove(path)
                except OSError:
                    pass
        self._temp_files.clear()
