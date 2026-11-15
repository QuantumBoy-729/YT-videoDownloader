"""Qt-free download engine: everything in here can be used and tested headless."""

from .engine import DownloadJob, fetch_info, find_ffmpeg
from .models import (
    AUDIO_FORMATS,
    VIDEO_FORMATS,
    DownloadRequest,
    JobState,
    MediaInfo,
    Progress,
)
from .options import build_options
from .plugins import CATALOG, CatalogEntry, InstalledPlugin, PluginError, PluginManager

__all__ = [
    "AUDIO_FORMATS",
    "CATALOG",
    "CatalogEntry",
    "InstalledPlugin",
    "PluginError",
    "PluginManager",
    "VIDEO_FORMATS",
    "DownloadJob",
    "DownloadRequest",
    "JobState",
    "MediaInfo",
    "Progress",
    "build_options",
    "fetch_info",
    "find_ffmpeg",
]
