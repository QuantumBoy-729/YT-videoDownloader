"""The beeg.com fix, exercised against a local imitation of the site's API."""

from __future__ import annotations

import json
import re
import subprocess

import pytest

from universal_downloader.core import DownloadJob, DownloadRequest, JobState, fetch_info
from universal_downloader.core.site_fixes import BeegFixedIE

from .conftest import NO_PROXY

VIDEO_ID = "123456789012345"
SIGNED = "key=abc,end=1,limit=10/data=d00d/media=hls4A"
PLAY_PATH = f"{SIGNED}/multi=426x240:240p:eA,1280x720:720p:eQ/_TPL_/{VIDEO_ID}.mp4.m3u8"


@pytest.mark.parametrize(
    "url, expected",
    [
        (f"https://beeg.com/-0{VIDEO_ID}", VIDEO_ID),
        (f"https://www.beeg.com/-0{VIDEO_ID}?t=4-861", VIDEO_ID),
        (f"https://beeg.com/-{VIDEO_ID}", VIDEO_ID),
        (f"https://beeg.com/{VIDEO_ID}", VIDEO_ID),
        (f"https://beeg.com/video/{VIDEO_ID}", VIDEO_ID),
    ],
)
def test_id_drops_the_link_prefix(url, expected):
    assert BeegFixedIE.suitable(url)
    assert re.match(BeegFixedIE._VALID_URL, url).group("id") == expected


def test_fix_replaces_the_stock_extractor():
    import yt_dlp.extractor.beeg as stock

    assert stock.BeegIE is BeegFixedIE
    assert BeegFixedIE.ie_key() == "Beeg"


@pytest.fixture
def fake_site(server, media_dir, ffmpeg, monkeypatch) -> str:
    """Lay out the site's two API endpoints and an HLS stream on the test server."""
    api = media_dir / "site"
    (api / "facts" / "file").mkdir(parents=True, exist_ok=True)
    (api / "video" / "play_url").mkdir(parents=True, exist_ok=True)
    (api / "facts" / "file" / VIDEO_ID).write_text(
        json.dumps(
            {
                "fc_facts": [{"id": 7, "fc_created": "2024-05-06T07:08:09Z", "fc_st_views": 42}],
                "file": {
                    "id": int(VIDEO_ID),
                    "fl_duration": 3,
                    "data": [{"cd_column": "sf_name", "cd_value": "A test clip"}],
                },
                "tags": [{"tg_name": "Example"}],
            }
        )
    )
    (api / "video" / "play_url" / VIDEO_ID).write_text(PLAY_PATH + "\n")

    master = api.joinpath(*PLAY_PATH.split("/"))
    master.parent.mkdir(parents=True, exist_ok=True)
    lines = ["#EXTM3U"]
    for label, size, bandwidth in (("240p", "426x240", 500000), ("720p", "1280x720", 3000000)):
        variant = api.joinpath(*SIGNED.split("/"), label)
        variant.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                ffmpeg, "-loglevel", "error", "-y", "-i", str(media_dir / "clip.mp4"),
                # H.264 + AAC, like the real streams.
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
                "-f", "hls", "-hls_time", "1", "-hls_playlist_type", "vod",
                str(variant / f"{VIDEO_ID}.mp4.m3u8"),
            ],
            check=True,
        )
        lines.append(f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={size},CODECS="avc1.64001E,mp4a.40.2"')
        lines.append(f"/site/{SIGNED}/{label}/{VIDEO_ID}.mp4.m3u8")
    master.write_text("\n".join(lines) + "\n")

    monkeypatch.setattr(BeegFixedIE, "_API_BASE", f"{server}/site")
    monkeypatch.setattr(BeegFixedIE, "_VIDEO_BASE", f"{server}/site")
    return f"https://beeg.com/-0{VIDEO_ID}"


def test_lookup_lists_the_available_qualities(fake_site):
    info = fetch_info(fake_site, extra_opts=NO_PROXY)
    assert info.title == "A test clip"
    assert info.heights == (720, 240)
    assert info.duration == 3


def test_download(fake_site, tmp_path, ffmpeg):
    job = DownloadJob(
        DownloadRequest(url=fake_site, output_dir=tmp_path, max_height=240), extra_opts=NO_PROXY
    )
    result = job.run()
    assert result.state is JobState.DONE, result.error
    out = result.files[0]
    assert out.name == f"A test clip [{VIDEO_ID}].mp4"
    probe = subprocess.run([ffmpeg, "-i", str(out)], capture_output=True, text=True).stderr
    assert "Video:" in probe and "Audio:" in probe


def test_no_stream_is_reported_clearly(fake_site, media_dir):
    (media_dir / "site" / "video" / "play_url" / VIDEO_ID).write_text("")
    with pytest.raises(RuntimeError, match="did not return a playable stream"):
        fetch_info(fake_site, extra_opts=NO_PROXY)
