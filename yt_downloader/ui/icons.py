"""Small stroke icons, drawn from inline SVG so they can follow the theme."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "download": '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>',
    "pause": '<path d="M9 5v14M15 5v14"/>',
    "play": '<path d="M8 5l11 7-11 7z"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "paste": '<path d="M9 3h6v4H9zM9 5H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-3"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2'
    'M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "retry": '<path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5"/>',
    "film": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9.5l5 2.5-5 2.5z"/>',
    "package": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
    "chevron": '<path d="M6 9l6 6 6-6"/>',
    "alert": '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.5v.2"/>',
}

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)


def svg(name: str, color: str) -> bytes:
    return _SVG.format(color=color, body=_PATHS[name]).encode()


def pixmap(name: str, color: str, size: int = 18, dpr: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg(name, color)))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter, QRectF(0, 0, pm.width(), pm.height()))
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color: str, disabled_color: str | None = None) -> QIcon:
    result = QIcon(pixmap(name, color))
    if disabled_color:
        result.addPixmap(pixmap(name, disabled_color), QIcon.Mode.Disabled)
    return result
