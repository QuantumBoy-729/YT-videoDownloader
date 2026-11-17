# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## 2.0.0 - unreleased

A complete rewrite. The Tkinter app is replaced by a Qt (PySide6) app on top of a
tested, GUI-free download engine. Settings from 1.x are not carried over.

### Added

- Real quality selection: the list shows the resolutions each video has, up to 4K,
  and video and audio are merged with ffmpeg.
- MKV and WebM video; MP3, M4A and Opus audio.
- A download queue with per-download progress, speed and time remaining, and
  pause, resume, cancel and retry.
- Playlist downloads.
- Plugins: a built-in list, browsing the `yt-dlp-plugins` GitHub topic, installing
  from a repository page or zip file, and per-plugin switches, timing and
  options for post-processing steps.
- A stopgap fix for beeg.com links, which current yt-dlp cannot read.
- Light and dark themes, an app icon, drag-and-drop links, and remembered settings.
- An ffmpeg binary bundled with the app.
- `--smoke-test`, a self-check of an installation.
- Plain-language error messages, including when a site's support in yt-dlp is out of date.
- An automated test suite (no internet needed), run on Python 3.10 to 3.13.

### Changed

- The interface is built on Qt (PySide6) instead of Tkinter.
- The package is `universal_downloader` and the command is `universal-downloader`.
- The Windows program is `UniversalDownloader.exe`, built by GitHub Actions and
  attached to each release instead of being committed to the repository.

### Fixed

- Choosing 720p or 1080p on YouTube silently gave 360p, because only pre-merged
  formats were considered.
- Stopping a download reported "Download failed" and left partial files behind.
- Pause, Resume and Stop stayed enabled after a download finished.
- Background threads updated the window directly, which could crash or freeze it.

### Removed

- The Tkinter interface and about 400 lines of unused code.
- The cx_Freeze, WiX (MSI) and Inno Setup build files, and the batch launchers.
- The dependency on an unpinned, third-party `yt-dlp-hianime` archive. It can
  still be installed through the Plugins window.
