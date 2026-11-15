"""Human-readable formatting for sizes, speeds and times."""

from __future__ import annotations


def size(num_bytes: float | None) -> str:
    if num_bytes is None:
        return "?"
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit in ("B", "KB") else f"{value:.1f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def speed(bytes_per_second: float | None) -> str:
    return f"{size(bytes_per_second)}/s" if bytes_per_second else ""


def clock(seconds: float | None) -> str:
    """``75`` -> ``1:15``, ``3675`` -> ``1:01:15``."""
    if seconds is None:
        return ""
    total = int(round(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def height_label(height: int | None) -> str:
    if height is None:
        return "Best available"
    return f"{height}p · 4K" if height == 2160 else f"{height}p"
