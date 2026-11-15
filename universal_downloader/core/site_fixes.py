"""Fixes for sites whose support is broken in current yt-dlp releases.

Each class here replaces one yt-dlp extractor for the whole process (that is
what ``plugin_name`` does). Importing this module is enough to activate them.

Keep this file small: every entry is a stopgap that should be deleted once
yt-dlp ships its own fix, because an override here also hides later upstream
improvements for that site.
"""

from __future__ import annotations

from yt_dlp.extractor.beeg import BeegIE
from yt_dlp.utils import ExtractorError, int_or_none, traverse_obj, unified_timestamp


class BeegFixedIE(BeegIE, plugin_name="UniversalDownloader"):
    """beeg.com changed two things that yt-dlp (as of 2026.10.26) has not followed:

    * Links look like ``/-0<id>``. ``-0`` is a fixed prefix, not part of the
      id; sending the leading zero to the API gives "400 Bad Request".
    * Stream addresses are no longer in the video metadata. They come from a
      separate ``video/play_url/<id>`` endpoint, which returns the path of an
      ordinary HLS master playlist.
    """

    _VALID_URL = r"https?://(?:www\.)?beeg\.com/(?:video/)?(?:-0|-)?(?P<id>\d+)"
    _API_BASE = "https://store.externulls.com"
    _VIDEO_BASE = "https://video.beeg.com"

    def _real_extract(self, url):
        video_id = self._match_id(url)

        video = self._download_json(
            f"{self._API_BASE}/facts/file/{video_id}", video_id, "Downloading video details"
        )
        playlist_path = self._download_webpage(
            f"{self._API_BASE}/video/play_url/{video_id}", video_id, "Downloading stream location"
        ).strip().strip('"')
        if not playlist_path.endswith(".m3u8"):
            raise ExtractorError("The site did not return a playable stream for this video", expected=True)

        formats = self._extract_m3u8_formats(
            f"{self._VIDEO_BASE}/{playlist_path.lstrip('/')}", video_id, ext="mp4"
        )

        # Details are stored as a list of {column, value} pairs.
        details = {
            item.get("cd_column"): item.get("cd_value")
            for item in traverse_obj(video, ("file", "data", ...)) or []
            if isinstance(item, dict)
        }
        facts = [f for f in video.get("fc_facts") or [] if isinstance(f, dict)]
        first_fact = min(facts, key=lambda f: f.get("id") or 0, default={})

        return {
            "id": video_id,
            "title": details.get("sf_name") or traverse_obj(video, ("file", "stuff", "sf_name")) or video_id,
            "description": details.get("sf_story") or traverse_obj(video, ("file", "stuff", "sf_story")),
            "timestamp": unified_timestamp(first_fact.get("fc_created")),
            "duration": int_or_none(traverse_obj(video, ("file", "fl_duration"))),
            "view_count": int_or_none(first_fact.get("fc_st_views")),
            "tags": traverse_obj(video, ("tags", ..., "tg_name")),
            "formats": formats,
            "age_limit": 18,
        }
