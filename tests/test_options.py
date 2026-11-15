"""Format selection, checked against a YouTube-shaped format list - offline."""

from __future__ import annotations

from pathlib import Path

import pytest
import yt_dlp

from yt_downloader.core import DownloadRequest, build_options


def _video(fid, height, ext, vcodec, tbr):
    return {
        "format_id": fid, "url": f"http://x/{fid}", "ext": ext, "protocol": "https",
        "height": height, "width": height * 16 // 9, "vcodec": vcodec, "acodec": "none",
        "tbr": tbr, "fps": 30,
    }


def _audio(fid, ext, acodec, abr):
    return {
        "format_id": fid, "url": f"http://x/{fid}", "ext": ext, "protocol": "https",
        "vcodec": "none", "acodec": acodec, "abr": abr, "tbr": abr,
    }


# Mirrors what YouTube serves: one low-res combined file, everything else split,
# and anything above 1080p only as VP9/webm.
FORMATS = [
    {
        "format_id": "18", "url": "http://x/18", "ext": "mp4", "protocol": "https",
        "height": 360, "width": 640, "vcodec": "avc1.42001E", "acodec": "mp4a.40.2",
        "tbr": 500, "fps": 30,
    },
    _audio("140", "m4a", "mp4a.40.2", 129),
    _audio("251", "webm", "opus", 135),
    _video("134", 360, "mp4", "avc1.4d401e", 400),
    _video("136", 720, "mp4", "avc1.4d401f", 1500),
    _video("247", 720, "webm", "vp9", 1300),
    _video("137", 1080, "mp4", "avc1.640028", 3000),
    _video("248", 1080, "webm", "vp9", 2600),
    _video("313", 2160, "webm", "vp9", 14000),
]


def select(request: DownloadRequest, ffmpeg: str | None = "ffmpeg") -> list[str]:
    """Return the format ids yt-dlp picks for ``request``."""
    opts = build_options(request, ffmpeg)
    opts.update(simulate=True, postprocessors=[])
    opts.pop("ffmpeg_location", None)
    info = {
        "id": "abc", "title": "t", "extractor": "test", "extractor_key": "Test",
        "webpage_url": "http://x", "formats": [dict(f) for f in FORMATS],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        result = ydl.process_ie_result(info, download=True)
    chosen = result.get("requested_formats") or [result]
    return [f["format_id"] for f in chosen]


def req(**kwargs) -> DownloadRequest:
    return DownloadRequest(url="http://x", output_dir=Path("."), **kwargs)


@pytest.mark.parametrize(
    "container, height, expected",
    [
        ("mp4", 720, ["136", "140"]),
        ("mp4", 1080, ["137", "140"]),
        ("webm", 1080, ["248", "251"]),
        ("mkv", 720, ["136", "140"]),
        # Resolution wins over container: 4K only exists as VP9.
        ("mp4", 2160, ["313", "140"]),
        ("mp4", None, ["313", "140"]),
        # Nothing at 480p: take the best below it, never above. At 360p the
        # combined file has the higher bitrate, so it wins and needs no merge.
        ("mp4", 480, ["18"]),
        # Below everything on offer: fall back instead of failing.
        ("mp4", 144, ["18"]),
    ],
)
def test_video_selection(container, height, expected):
    assert select(req(file_format=container, max_height=height)) == expected


def test_requested_resolution_is_honoured_not_capped_at_combined_file():
    """Regression: the old selector only considered combined files (360p)."""
    assert select(req(max_height=1080)) != ["18"]


def test_without_ffmpeg_only_combined_formats():
    assert select(req(max_height=1080), ffmpeg=None) == ["18"]


@pytest.mark.parametrize("codec", ["mp3", "m4a", "opus"])
def test_audio_selects_audio_only_stream(codec):
    chosen = select(req(audio_only=True, file_format=codec))
    assert chosen in (["140"], ["251"])


def test_audio_postprocessors():
    opts = build_options(req(audio_only=True, file_format="mp3"), "ffmpeg")
    extract = opts["postprocessors"][0]
    assert extract["key"] == "FFmpegExtractAudio"
    assert extract["preferredcodec"] == "mp3"
    # Without ffmpeg we cannot convert, so no postprocessors at all.
    assert build_options(req(audio_only=True, file_format="mp3"), None)["postprocessors"] == []


def test_merge_container_and_remux():
    mp4 = build_options(req(file_format="mp4"), "ffmpeg")
    assert mp4["merge_output_format"] == "mp4/mkv"
    assert {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"} in mp4["postprocessors"]
    webm = build_options(req(file_format="webm"), "ffmpeg")
    assert webm["merge_output_format"] == "webm/mkv"
    assert all(p["key"] != "FFmpegVideoRemuxer" for p in webm["postprocessors"])


def test_playlist_flag():
    assert build_options(req(), None)["noplaylist"] is True
    assert build_options(req(playlist=True), None)["noplaylist"] is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {"file_format": "mp3"},
        {"audio_only": True, "file_format": "mp4"},
        {"max_height": 0},
    ],
)
def test_invalid_requests_rejected(kwargs):
    with pytest.raises(ValueError):
        req(**kwargs)
