from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path

VIDEO_FORMATS = ("mp4", "mkv", "webm")
AUDIO_FORMATS = ("mp3", "m4a", "opus")

#: Heights offered before a URL has been inspected.
DEFAULT_HEIGHTS = (2160, 1440, 1080, 720, 480, 360, 240, 144)


class JobState(enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def finished(self) -> bool:
        return self in (JobState.DONE, JobState.FAILED, JobState.CANCELLED)


@dataclass(frozen=True)
class DownloadRequest:
    """Everything needed to start one download."""

    url: str
    output_dir: Path
    audio_only: bool = False
    #: Container for video (see VIDEO_FORMATS) or codec for audio (AUDIO_FORMATS).
    file_format: str = "mp4"
    #: Maximum video height in pixels; ``None`` means best available.
    max_height: int | None = None
    #: Download every entry when the URL points at a playlist.
    playlist: bool = False

    def __post_init__(self) -> None:
        allowed = AUDIO_FORMATS if self.audio_only else VIDEO_FORMATS
        if self.file_format not in allowed:
            raise ValueError(
                f"Unsupported {'audio' if self.audio_only else 'video'} format: {self.file_format!r}"
            )
        if self.max_height is not None and self.max_height <= 0:
            raise ValueError("max_height must be positive")


@dataclass(frozen=True)
class MediaInfo:
    """What we learn about a URL before downloading it."""

    url: str
    title: str
    uploader: str = ""
    duration: float | None = None
    thumbnail_url: str = ""
    #: Video heights available, highest first. Empty if unknown.
    heights: tuple[int, ...] = ()
    is_playlist: bool = False
    entry_count: int | None = None


@dataclass(frozen=True)
class Progress:
    """A snapshot of a running job."""

    #: "video", "audio", "media" (single stream) or "processing".
    stage: str = "media"
    downloaded: int = 0
    total: int | None = None
    speed: float | None = None
    eta: float | None = None
    title: str = ""
    #: 1-based position in a playlist, when downloading one.
    playlist_index: int | None = None
    playlist_count: int | None = None

    @property
    def fraction(self) -> float | None:
        if self.stage == "processing" or not self.total:
            return None
        return max(0.0, min(1.0, self.downloaded / self.total))


@dataclass
class JobResult:
    state: JobState
    files: list[Path] = field(default_factory=list)
    error: str = ""
