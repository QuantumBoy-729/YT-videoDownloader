"""Small reusable widgets."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QFontMetrics, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QLabel, QPushButton, QSizePolicy

from . import icons
from .theme import Theme


class ElidedLabel(QLabel):
    """A single-line label that shortens its text with an ellipsis to fit."""

    def __init__(self, text: str = "", mode=Qt.TextElideMode.ElideRight, parent=None) -> None:
        super().__init__(parent)
        self._full = ""
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming)
        self._full = text
        self.setToolTip(text)
        self._update()

    def fullText(self) -> str:  # noqa: N802
        return self._full

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(40, super().minimumSizeHint().height())

    def _update(self) -> None:
        metrics = QFontMetrics(self.font())
        super().setText(metrics.elidedText(self._full, self._mode, max(self.width(), 40)))


class IconButton(QPushButton):
    """A square, icon-only button that still has a name for tooltips and screen readers."""

    def __init__(self, icon_name: str, label: str, theme: Theme, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("iconButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme = theme
        self.set_icon(icon_name, label)

    def set_icon(self, icon_name: str, label: str) -> None:
        self._icon_name = icon_name
        self.setIcon(icons.icon(icon_name, self._theme.text, self._theme.muted))
        self.setIconSize(QSize(18, 18))
        self.setToolTip(label)
        self.setAccessibleName(label)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.set_icon(self._icon_name, self.toolTip())


def rounded(pixmap: QPixmap, width: int, height: int, radius: int = 8, dpr: float = 2.0) -> QPixmap:
    """Scale ``pixmap`` to cover ``width`` x ``height`` and round its corners."""
    target = QSize(int(width * dpr), int(height * dpr))
    scaled = pixmap.scaled(
        target,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    out = QPixmap(target)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, target.width(), target.height()), radius * dpr, radius * dpr)
    painter.setClipPath(path)
    painter.drawPixmap(
        (target.width() - scaled.width()) // 2, (target.height() - scaled.height()) // 2, scaled
    )
    painter.end()
    out.setDevicePixelRatio(dpr)
    return out
