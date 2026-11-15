# Universal Downloader

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
- **Plugins** - install add-ons for the download engine from a built-in list,
  or any other yt-dlp plugin from its zip archive (see [Plugins](#plugins)).
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
universal-downloader
```

Or run it straight from the checkout:

```bash
pip install yt-dlp PySide6-Essentials imageio-ffmpeg
python -m universal_downloader
```

Sites change often and old yt-dlp versions stop working. If downloads start
failing, update it first:

```bash
pip install -U yt-dlp
```

## Plugins

Open **Plugins** in the top-right corner to install or remove add-ons.

| Plugin | What it does | Source |
| --- | --- | --- |
| Upload date as file date | Sets each file's modified date to the video's upload date, so folders sort by release date. | [bradenhilton/yt-dlp-FixupMtime](https://github.com/bradenhilton/yt-dlp-FixupMtime) |
| DeArrow titles | Names YouTube downloads with the community-written [DeArrow](https://dearrow.ajay.app/) title when one exists. Contacts `sponsor.ajay.app` for each download. | [QuantumWarpCode/yt-dlp-dearrow](https://github.com/QuantumWarpCode/yt-dlp-dearrow) |

The list comes from [yt-dlp's own plugin page](https://github.com/yt-dlp/yt-dlp/wiki/Plugins),
limited to plugins that do something useful in this app, and each one is
pinned to an exact commit so what gets installed cannot change underneath you.
To add one, append a `CatalogEntry` to `CATALOG` in
`universal_downloader/core/plugins.py`.

### More plugins from GitHub

Under **More from GitHub**, press **Browse plugins on GitHub** to list
everything tagged [`yt-dlp-plugins`](https://github.com/topics/yt-dlp-plugins)
(around 80 repositories, most-starred first, archived ones left out). Each shows
its stars, last update and licence, with a link to the source; there is a filter
box, and **Install** asks for confirmation first. The list is fetched live, so it
needs an internet connection and is subject to GitHub's request limit for
anonymous use (about 10 searches a minute).

Nothing on that list has been reviewed. It includes plugins for other tools,
plugins that need extra programs, and at least one collection of rejected or
controversial code, so read the description and source before installing.

You can also paste a repository page (`https://github.com/owner/repo`, or a
`/tree/<branch>` link) or any zip archive into **Install from a zip file or
link**. Each install records the exact version it fetched.

What to expect once installed:

- **Plugins that add site support or YouTube features** work as soon as they are
  installed.
- **Post-processing plugins** outside the built-in list are installed but not
  switched on, because each one needs its own settings. They are labelled as
  such in the list.
- **Plugins that need extra Python packages or programs** may not load, since the
  app cannot install packages for them.

Good to know:

- Plugins are third-party code and run with the same access to your computer
  as the app. Install only ones you trust.
- Only the plugin's `yt_dlp_plugins` folder is unpacked - its `setup.py` is
  never run and extra Python packages it may depend on are not installed.
- Plugins are kept in a per-user folder (`%APPDATA%\UniversalDownloader\plugins` on
  Windows, `~/.local/share/universal-downloader/plugins` on Linux,
  `~/Library/Application Support/UniversalDownloader/plugins` on macOS), so they work
  in the packaged executable too and survive app updates.

## Windows executable

A single-file `UniversalDownloader.exe` (no Python needed) is built by GitHub Actions:
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
universal_downloader/
  core/      download engine - no GUI imports, usable on its own
    options.py   DownloadRequest -> yt-dlp options (format selection)
    engine.py    DownloadJob (pause/resume/cancel), fetch_info, find_ffmpeg
    plugins.py   plugin catalog, installer and yt-dlp loading
    site_fixes.py  stopgap fixes for sites broken in current yt-dlp
  ui/        Qt interface
    main_window.py, queue_item.py, plugins_dialog.py, theme.py, ...
packaging/   PyInstaller build script
tests/
```

Using the engine without the GUI:

```python
from pathlib import Path
from universal_downloader.core import DownloadJob, DownloadRequest

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
