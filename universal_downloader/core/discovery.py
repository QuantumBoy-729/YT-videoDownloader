"""Find yt-dlp plugins published on GitHub under the ``yt-dlp-plugins`` topic.

This lists what is out there; it says nothing about whether any of it is safe
or works with this app. Everything found is unreviewed third-party code.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from . import plugins
from .plugins import PluginError, slug

TOPIC = "yt-dlp-plugins"


@dataclass(frozen=True)
class RepoInfo:
    full_name: str
    description: str = ""
    stars: int = 0
    pushed: str = ""
    license: str = ""
    default_branch: str = "HEAD"
    url: str = ""

    def __post_init__(self) -> None:
        if not self.url:
            object.__setattr__(self, "url", f"https://github.com/{self.full_name}")

    @property
    def name(self) -> str:
        return self.full_name.split("/", 1)[-1]

    @property
    def owner(self) -> str:
        return self.full_name.split("/", 1)[0]

    @property
    def id(self) -> str:
        """Folder name the plugin is installed under; includes the owner so names cannot clash."""
        return slug(f"{self.owner}-{self.name}")


def _rate_limit_message(headers) -> str:
    reset = headers.get("X-RateLimit-Reset")
    if reset and reset.isdigit():
        minutes = max(1, round((int(reset) - time.time()) / 60))
        return f"GitHub's request limit was reached. Try again in about {minutes} minute{'s' if minutes != 1 else ''}."
    return "GitHub's request limit was reached. Try again in a few minutes."


def search_topic(
    opener: urllib.request.OpenerDirector | None = None, topic: str = TOPIC
) -> list[RepoInfo]:
    """Repositories tagged with ``topic``, most-starred first. Archived ones are left out."""
    query = urllib.parse.urlencode(
        {"q": f"topic:{topic} archived:false", "sort": "stars", "order": "desc", "per_page": 100}
    )
    request = urllib.request.Request(
        f"{plugins.GITHUB_API}/search/repositories?{query}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": plugins.USER_AGENT},
    )
    try:
        with (opener or urllib.request.build_opener()).open(request, timeout=20) as response:
            data = json.loads(response.read(5 * 1024 * 1024))
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise PluginError(_rate_limit_message(exc.headers)) from exc
        raise PluginError(f"GitHub answered with an error ({exc.code}).") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise PluginError("Could not reach GitHub. Check your internet connection.") from exc
    except ValueError as exc:
        raise PluginError("GitHub sent a reply this app could not read.") from exc

    found = []
    for item in data.get("items", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict) or not item.get("full_name") or item.get("archived"):
            continue
        found.append(
            RepoInfo(
                full_name=item["full_name"],
                description=(item.get("description") or "").strip(),
                stars=int(item.get("stargazers_count") or 0),
                pushed=str(item.get("pushed_at") or "")[:10],
                license=(item.get("license") or {}).get("spdx_id") or "",
                default_branch=item.get("default_branch") or "HEAD",
                url=item.get("html_url") or "",
            )
        )
    return found
