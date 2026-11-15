"""Translate a :class:`DownloadRequest` into yt-dlp options.

Kept free of side effects so the format logic can be unit-tested offline.
"""

from __future__ import annotations

from typing import Any

from .models import DownloadRequest

#: Stream extensions (video, audio) to prefer for each output container. mkv
#: holds anything, so favour the widely compatible H.264/AAC streams.
_PREFERRED_EXT = {"mp4": "mp4:m4a", "webm": "webm:webm", "mkv": "mp4:m4a"}
#: Containers yt-dlp may merge into, in order of preference.
_MERGE = {"mp4": "mp4/mkv", "webm": "webm/mkv", "mkv": "mkv"}


def build_options(request: DownloadRequest, ffmpeg_path: str | None) -> dict[str, Any]:
    """Return yt-dlp options for ``request``.

    ``ffmpeg_path`` is the ffmpeg binary to use, or ``None`` when ffmpeg is not
    available. Without ffmpeg, separate video and audio streams cannot be
    merged and audio cannot be converted, so we fall back to single-file
    formats and keep whatever container the site provides.
    """
    opts: dict[str, Any] = {
        "outtmpl": {
            "default": str(request.output_dir / "%(title).150B [%(id)s].%(ext)s"),
        },
        "noplaylist": not request.playlist,
        "ignoreerrors": "only_download" if request.playlist else False,
        "continuedl": True,
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30,
        "windowsfilenames": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "postprocessors": [],
    }
    if ffmpeg_path:
        opts["ffmpeg_location"] = ffmpeg_path

    if request.audio_only:
        opts["format"] = "bestaudio/best"
        if ffmpeg_path:
            opts["postprocessors"] += [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": request.file_format,
                    # 0 = best VBR quality for lossy codecs.
                    "preferredquality": "0",
                },
                {"key": "FFmpegMetadata"},
            ]
        return opts

    height = request.max_height
    limit = f"[height<={height}]" if height else ""
    container = request.file_format

    if not ffmpeg_path:
        # Only formats that already contain both video and audio.
        opts["format"] = f"best{limit}/best"
        opts["format_sort"] = [f"res:{height}" if height else "res", f"ext:{container}"]
        return opts

    # Best video + best audio, falling back to a combined file. If nothing fits
    # under the height limit, take the closest thing rather than failing.
    opts["format"] = f"bestvideo*{limit}+bestaudio/best{limit}/bestvideo*+bestaudio/best"
    # Resolution first, then prefer streams that already match the container so
    # the merge is a cheap remux and plays everywhere.
    opts["format_sort"] = [
        f"res:{height}" if height else "res",
        f"ext:{_PREFERRED_EXT[container]}",
    ]
    opts["merge_output_format"] = _MERGE[container]
    if container != "webm":
        # webm only holds VP8/VP9/AV1, so remuxing e.g. H.264 into it would fail.
        opts["postprocessors"].append(
            {"key": "FFmpegVideoRemuxer", "preferedformat": container}
        )
    opts["postprocessors"].append({"key": "FFmpegMetadata"})
    return opts
