# YT Downloader

A desktop app for saving videos and audio from YouTube and the
[many other sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)
supported by yt-dlp. Built with Python, Qt (PySide6) and yt-dlp.

## Features

- **Real quality selection** - paste a link and pick from the resolutions that
  video actually has, up to 4K. Video and audio streams are downloaded
  separately and merged, so 720p/1080p/4K work (not just the 360p combined file).
- **Video or audio** - MP4, MKV or WebM video; MP3, M4A or Opus audio.
- **Download queue** - queue as many links as you like; two run at a time, each
  with its own progress, speed and time remaining.
- **Pause, resume, cancel, retry** - per download. Cancelling removes the
  partial file.
- **Playlists** - download a whole playlist, or just the one video from a
  playlist link.
- **Light and dark themes**, drag-and-drop links, and your folder/format/quality
  choices remembered between runs.
- **No ffmpeg setup** - an ffmpeg binary is installed with the app. A system
  ffmpeg on `PATH` is used instead if you have one.

## Install and run

Requires Python 3.10 or newer.

```bash
git clone https://github.com/QuantumBoy-729/YT-videoDownloader.git
cd YT-videoDownloader
pip install .
yt-downloader
```

Or run it straight from the checkout:

```bash
pip install yt-dlp PySide6-Essentials imageio-ffmpeg
python -m yt_downloader
```

Sites change often and old yt-dlp versions stop working. If downloads start
failing, update it first:

```bash
pip install -U yt-dlp
```

## Windows executable

A single-file `YTDownloader.exe` (no Python needed) is built by GitHub Actions:
download it from the latest run's artifacts, or from the release page for
tagged versions (`v*`). To build it yourself:

```bash
pip install ".[build]"
python packaging/build.py
```

The result is written to `dist/`. The same script produces a native binary on
Linux and macOS.

## Development

```bash
pip install -e ".[dev]"
pytest
```

The tests need ffmpeg but no internet: they serve generated clips from a local
HTTP server and drive both the download engine and the real window (offscreen).

```
yt_downloader/
  core/      download engine - no GUI imports, usable on its own
    options.py   DownloadRequest -> yt-dlp options (format selection)
    engine.py    DownloadJob (pause/resume/cancel), fetch_info, find_ffmpeg
  ui/        Qt interface
    main_window.py, queue_item.py, theme.py, ...
packaging/   PyInstaller build script
tests/
```

Using the engine without the GUI:

```python
from pathlib import Path
from yt_downloader.core import DownloadJob, DownloadRequest

job = DownloadJob(
    DownloadRequest(url="https://...", output_dir=Path("videos"), max_height=1080),
    on_progress=lambda p: print(p.stage, p.fraction),
)
result = job.run()  # blocks; job.pause() / resume() / cancel() from another thread
print(result.state, result.files, result.error)
```

## Legal

For personal use. Only download content you have the right to download, and
respect the terms of service of the sites you use.

## License

See [LICENSE](LICENSE).
