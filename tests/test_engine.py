"""End-to-end engine tests against a local HTTP server (no internet)."""

from __future__ import annotations

import subprocess
import threading
import time

import pytest

from universal_downloader.core import DownloadJob, DownloadRequest, JobState, fetch_info
from universal_downloader.core.engine import clean_error

from .conftest import NO_PROXY


def make_job(url, out, **kwargs):
    progress, states = [], []
    job = DownloadJob(
        DownloadRequest(url=url, output_dir=out, **kwargs),
        on_progress=progress.append,
        on_state=states.append,
        extra_opts=NO_PROXY,
    )
    return job, progress, states


def run_in_thread(job):
    result = {}
    thread = threading.Thread(target=lambda: result.update(r=job.run()), daemon=True)
    thread.start()
    return thread, result


def wait_for(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def same_size(path, original) -> bool:
    """Metadata tagging rewrites the container, so allow a little slack."""
    return path.stat().st_size == pytest.approx(original.stat().st_size, rel=0.02)


def probe(ffmpeg, path) -> str:
    return subprocess.run([ffmpeg, "-i", str(path)], capture_output=True, text=True).stderr


def test_fetch_info(server):
    info = fetch_info(f"{server}/clip.mp4", extra_opts=NO_PROXY)
    assert info.title == "clip"
    assert not info.is_playlist


def test_fetch_info_reports_failure(server):
    with pytest.raises(RuntimeError) as exc:
        fetch_info(f"{server}/missing.mp4", extra_opts=NO_PROXY)
    assert "404" in str(exc.value)


def test_video_download(server, media_dir, tmp_path, ffmpeg):
    job, progress, states = make_job(f"{server}/clip.mp4", tmp_path)
    result = job.run()

    assert result.state is JobState.DONE, result.error
    assert states == [JobState.RUNNING, JobState.DONE]
    assert len(result.files) == 1
    out = result.files[0]
    assert out.suffix == ".mp4"
    assert same_size(out, media_dir / "clip.mp4")
    assert "Video: mpeg4" in probe(ffmpeg, out)
    assert progress[-1].stage == "processing" or progress[-1].fraction == 1.0
    assert any(p.fraction == 1.0 for p in progress)
    assert not list(tmp_path.glob("*.part"))


def test_video_remuxed_to_requested_container(server, tmp_path, ffmpeg):
    job, _, _ = make_job(f"{server}/clip.mp4", tmp_path, file_format="mkv")
    result = job.run()
    assert result.state is JobState.DONE, result.error
    assert result.files[0].suffix == ".mkv"
    assert "matroska" in probe(ffmpeg, result.files[0])


@pytest.mark.parametrize("codec, marker", [("mp3", "Audio: mp3"), ("m4a", "Audio: aac")])
def test_audio_extraction(server, tmp_path, ffmpeg, codec, marker):
    job, _, _ = make_job(f"{server}/clip.mp4", tmp_path, audio_only=True, file_format=codec)
    result = job.run()
    assert result.state is JobState.DONE, result.error
    assert result.files[0].suffix == f".{codec}"
    info = probe(ffmpeg, result.files[0])
    assert marker in info
    assert "Video:" not in info


def test_works_without_ffmpeg(server, tmp_path):
    job = DownloadJob(
        DownloadRequest(url=f"{server}/clip.mp4", output_dir=tmp_path),
        ffmpeg_path=None,
        extra_opts=NO_PROXY,
    )
    result = job.run()
    assert result.state is JobState.DONE, result.error


def test_cancel_removes_partial_file(server, tmp_path):
    job, progress, _ = make_job(f"{server}/slow/clip.mp4", tmp_path)
    thread, result = run_in_thread(job)
    assert wait_for(lambda: len(progress) >= 2)
    job.cancel()
    thread.join(10)

    assert result["r"].state is JobState.CANCELLED
    assert list(tmp_path.iterdir()) == []


def test_pause_and_resume(server, media_dir, tmp_path):
    job, progress, states = make_job(f"{server}/slow/clip.mp4", tmp_path)
    thread, result = run_in_thread(job)
    assert wait_for(lambda: len(progress) >= 2)

    job.pause()
    assert wait_for(lambda: job.state is JobState.PAUSED)
    seen = len(progress)
    time.sleep(0.5)
    assert len(progress) == seen, "progress advanced while paused"
    assert thread.is_alive()

    job.resume()
    thread.join(30)
    assert result["r"].state is JobState.DONE, result["r"].error
    assert states == [JobState.RUNNING, JobState.PAUSED, JobState.RUNNING, JobState.DONE]
    assert same_size(result["r"].files[0], media_dir / "clip.mp4")


def test_cancel_while_paused(server, tmp_path):
    job, progress, _ = make_job(f"{server}/slow/clip.mp4", tmp_path)
    thread, result = run_in_thread(job)
    assert wait_for(lambda: len(progress) >= 2)
    job.pause()
    assert wait_for(lambda: job.state is JobState.PAUSED)
    job.cancel()
    thread.join(10)
    assert result["r"].state is JobState.CANCELLED
    assert list(tmp_path.iterdir()) == []


def test_cancel_before_start(server, tmp_path):
    job, _, states = make_job(f"{server}/clip.mp4", tmp_path)
    job.cancel()
    assert job.run().state is JobState.CANCELLED
    assert states == [JobState.CANCELLED]
    assert list(tmp_path.iterdir()) == []


def test_failure_is_reported_not_raised(server, tmp_path):
    job, _, states = make_job(f"{server}/missing.mp4", tmp_path)
    result = job.run()
    assert result.state is JobState.FAILED
    assert "404" in result.error
    assert states[-1] is JobState.FAILED


def test_clean_error():
    raw = (
        "\x1b[0;31mERROR:\x1b[0m [youtube] abc: Video unavailable; please report this issue on "
        "https://github.com/yt-dlp/yt-dlp/issues , filling out the template"
    )
    assert clean_error(raw) == "[youtube] abc: Video unavailable"
    assert clean_error("") == "Unknown error"
