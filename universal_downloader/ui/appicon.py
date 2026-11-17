"""The application icon, drawn from SVG so it stays sharp at any size."""

from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#8f82f8"/>
      <stop offset="1" stop-color="#5a48e0"/>
    </linearGradient>
  </defs>
  <rect width="256" height="256" rx="56" fill="url(#g)"/>
  <g fill="none" stroke="#fff" stroke-width="20" stroke-linecap="round" stroke-linejoin="round">
    <path d="M128 56v100M84 116l44 44 44-44M72 200h112"/>
  </g>
</svg>"""

SIZES = (16, 24, 32, 48, 64, 128, 256)


def _render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(_SVG)).render(painter)
    painter.end()
    return image


def app_icon() -> QIcon:
    """The icon for windows and the taskbar. Needs a running QApplication."""
    icon = QIcon()
    for size in SIZES:
        icon.addPixmap(QPixmap.fromImage(_render(size)))
    return icon


def write_ico(path: Path) -> None:
    """Write a Windows ``.ico`` containing every size (each stored as PNG)."""
    blobs = []
    for size in SIZES:
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        _render(size).save(buffer, "PNG")
        blobs.append((size, bytes(buffer.data())))

    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = len(header) + 16 * len(blobs)
    entries, data = b"", b""
    for size, png in blobs:
        dimension = 0 if size >= 256 else size  # 0 means 256 in the format
        entries += struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    Path(path).write_bytes(header + entries + data)
