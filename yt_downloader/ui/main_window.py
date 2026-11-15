"""The application window: URL bar, media preview, options and the download queue."""

from __future__ import annotations

import threading
import urllib.request
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..core import (
    AUDIO_FORMATS,
    VIDEO_FORMATS,
    DownloadRequest,
    MediaInfo,
    fetch_info,
    find_ffmpeg,
)
from ..core.models import DEFAULT_HEIGHTS
from ..core.plugins import PluginManager
from . import fmt, icons, theme as themes
from .plugins_dialog import PluginsDialog
from .queue_item import QueueItem
from .widgets import ElidedLabel, IconButton, rounded

MAX_CONCURRENT = 2
THUMB_W, THUMB_H = 160, 90
_HINT = "Paste a link to see the available quality options."


def _looks_like_url(text: str) -> bool:
    return text.startswith(("http://", "https://")) and len(text) > 10 and " " not in text


def _fetch_thumbnail(url: str) -> bytes | None:
    if not url.startswith(("http://", "https://")):
        return None
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.read(4 * 1024 * 1024)
    except Exception:
        return None


class MainWindow(QMainWindow):
    # (lookup token, MediaInfo, thumbnail bytes or None) / (lookup token, message)
    _infoReady = Signal(int, object, object)
    _infoFailed = Signal(int, str)

    def __init__(
        self,
        settings: QSettings | None = None,
        job_options: dict[str, Any] | None = None,
        info_options: dict[str, Any] | None = None,
        plugins: PluginManager | None = None,
    ) -> None:
        super().__init__()
        self.plugins = plugins or PluginManager()
        try:
            self.plugins.activate()
        except Exception:
            pass  # A broken plugin folder must never stop the app from starting.
        self._settings = settings or QSettings("YTDownloader", "YTDownloader")
        self._job_options = job_options or {}
        self._info_options = info_options or {}
        self._theme = themes.by_name(self._settings.value("theme", "system"))
        self._ffmpeg = self._job_options.get("ffmpeg_path", find_ffmpeg())
        self._info: MediaInfo | None = None
        self._lookup_token = 0
        self._items: list[QueueItem] = []

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(640, 560)
        self.resize(880, 760)
        self.setAcceptDrops(True)

        self._build()
        self._infoReady.connect(self._on_info_ready)
        self._infoFailed.connect(self._on_info_failed)
        self._lookup_timer = QTimer(self, singleShot=True, interval=500)
        self._lookup_timer.timeout.connect(self.lookup)

        self._restore()
        self.apply_theme(self._theme)
        self.url_edit.setFocus()
        self._refresh_queue_header()

    # -- construction ----------------------------------------------------------

    def _build(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        self.theme_button = IconButton("sun", "Switch theme", self._theme)
        self.theme_button.clicked.connect(self.toggle_theme)
        header = QHBoxLayout()
        header.addWidget(title)
        self.plugins_button = QPushButton(" Plugins")
        self.plugins_button.setObjectName("flat")
        self.plugins_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.plugins_button.clicked.connect(self.show_plugins)
        header.addStretch(1)
        header.addWidget(self.plugins_button)
        header.addWidget(self.theme_button)
        layout.addLayout(header)

        # URL bar
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Paste a video or playlist link")
        self.url_edit.setAccessibleName("Video link")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.textChanged.connect(self._on_url_changed)
        self.url_edit.returnPressed.connect(self.lookup)
        self.paste_button = QPushButton(" Paste")
        self.paste_button.setMinimumHeight(38)
        self.paste_button.clicked.connect(self.paste)
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(self.paste_button)
        layout.addLayout(url_row)

        layout.addWidget(self._build_card())

        if not self._ffmpeg:
            warning = QLabel(
                "ffmpeg was not found, so videos are limited to single-file formats "
                "(usually 360p on YouTube) and audio is saved without conversion. "
                "Install ffmpeg and restart for full quality."
            )
            warning.setObjectName("warning")
            warning.setWordWrap(True)
            layout.addWidget(warning)

        # Queue
        queue_title = QLabel("Downloads")
        queue_title.setObjectName("sectionTitle")
        self.queue_summary = QLabel()
        self.queue_summary.setObjectName("muted")
        self.clear_button = QPushButton("Clear finished")
        self.clear_button.setObjectName("flat")
        self.clear_button.clicked.connect(self.clear_finished)
        queue_header = QHBoxLayout()
        queue_header.setSpacing(10)
        queue_header.addWidget(queue_title)
        queue_header.addWidget(self.queue_summary)
        queue_header.addStretch(1)
        queue_header.addWidget(self.clear_button)
        layout.addSpacing(4)
        layout.addLayout(queue_header)

        body = QWidget()
        body.setObjectName("queueBody")
        self.queue_layout = QVBoxLayout(body)
        self.queue_layout.setContentsMargins(0, 0, 0, 0)
        self.queue_layout.setSpacing(8)
        self.empty_label = QLabel("Nothing here yet. Downloads you start will show up in this list.")
        self.empty_label.setObjectName("muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setMinimumHeight(80)
        self.queue_layout.addWidget(self.empty_label)
        self.queue_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        scroll.viewport().setAutoFillBackground(False)
        layout.addWidget(scroll, 1)

    def _build_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Preview
        self.thumb = QLabel()
        self.thumb.setObjectName("thumb")
        self.thumb.setFixedSize(THUMB_W, THUMB_H)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.media_title = QLabel()
        self.media_title.setObjectName("mediaTitle")
        self.media_title.setWordWrap(True)
        self.media_title.setTextFormat(Qt.TextFormat.PlainText)
        self.media_meta = ElidedLabel()
        self.media_meta.setObjectName("muted")
        self.message = QLabel(_HINT)
        self.message.setObjectName("muted")
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        text = QVBoxLayout()
        text.setSpacing(4)
        text.addWidget(self.media_title)
        text.addWidget(self.media_meta)
        text.addWidget(self.message)
        text.addStretch(1)
        preview = QHBoxLayout()
        preview.setSpacing(14)
        preview.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignTop)
        preview.addLayout(text, 1)
        layout.addLayout(preview)

        # Options
        self.video_button = QPushButton("Video")
        self.audio_button = QPushButton("Audio")
        self.video_button.setProperty("first", True)
        self.audio_button.setProperty("last", True)
        self.kind_group = QButtonGroup(self)
        for button in (self.video_button, self.audio_button):
            button.setObjectName("segment")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.kind_group.addButton(button)
        self.video_button.setChecked(True)
        self.kind_group.buttonToggled.connect(self._on_kind_changed)
        segment = QHBoxLayout()
        segment.setSpacing(0)
        segment.addWidget(self.video_button)
        segment.addWidget(self.audio_button)

        self.format_combo = QComboBox()
        self.format_combo.setAccessibleName("File format")
        self.format_combo.setMinimumWidth(96)
        self.quality_combo = QComboBox()
        self.quality_combo.setAccessibleName("Quality")
        self.quality_combo.setMinimumWidth(150)
        self.playlist_check = QCheckBox("Whole playlist")
        self.playlist_check.setVisible(False)

        options = QHBoxLayout()
        options.setSpacing(10)
        options.addLayout(segment)
        options.addWidget(self.format_combo)
        options.addWidget(self.quality_combo)
        options.addWidget(self.playlist_check)
        options.addStretch(1)
        layout.addLayout(options)

        # Destination + action
        self.folder_icon = QLabel()
        self.folder_label = ElidedLabel(mode=Qt.TextElideMode.ElideMiddle)
        self.folder_label.setObjectName("muted")
        self.folder_button = QPushButton("Change")
        self.folder_button.setAccessibleName("Change download folder")
        self.folder_button.clicked.connect(self.choose_folder)
        self.download_button = QPushButton(" Download")
        self.download_button.setObjectName("primary")
        self.download_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_button.setEnabled(False)
        self.download_button.clicked.connect(self.enqueue)
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        bottom.addWidget(self.folder_icon)
        bottom.addWidget(self.folder_label, 1)
        bottom.addWidget(self.folder_button)
        bottom.addSpacing(8)
        bottom.addWidget(self.download_button)
        layout.addLayout(bottom)
        return card

    # -- settings and theme ----------------------------------------------------

    def _restore(self) -> None:
        s = self._settings
        default_dir = (
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
            or str(Path.home() / "Downloads")
        )
        self.output_dir = Path(s.value("output_dir", default_dir))
        self.folder_label.setText(str(self.output_dir))
        self._video_format = s.value("video_format", VIDEO_FORMATS[0])
        self._audio_format = s.value("audio_format", AUDIO_FORMATS[0])
        height = s.value("max_height", 1080)
        self._preferred_height = int(height) if str(height).isdigit() else None
        if s.value("audio_only", False, type=bool):
            self.audio_button.setChecked(True)
        self._fill_formats()
        self._fill_qualities(DEFAULT_HEIGHTS)
        self.format_combo.currentIndexChanged.connect(self._remember_format)
        self.quality_combo.activated.connect(self._remember_quality)
        geometry = s.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def apply_theme(self, theme: themes.Theme) -> None:
        self._theme = theme
        themes.apply(QApplication.instance(), theme)
        self.theme_button.set_theme(theme)
        self.theme_button.set_icon(
            "sun" if theme.name == "dark" else "moon",
            "Switch to light theme" if theme.name == "dark" else "Switch to dark theme",
        )
        self.paste_button.setIcon(icons.icon("paste", theme.text))
        self.plugins_button.setIcon(icons.icon("package", theme.muted))
        self.download_button.setIcon(icons.icon("download", theme.accent_text, theme.muted))
        self.folder_icon.setPixmap(icons.pixmap("folder", theme.muted, 16))
        if self._info is None or self.thumb.property("placeholder"):
            self._set_thumbnail(None)
        for item in self._items:
            item.set_theme(theme)

    def toggle_theme(self) -> None:
        theme = themes.LIGHT if self._theme.name == "dark" else themes.DARK
        self._settings.setValue("theme", theme.name)
        self.apply_theme(theme)

    def show_plugins(self) -> PluginsDialog:
        dialog = PluginsDialog(self.plugins, self._theme, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.open()
        return dialog

    # -- options ---------------------------------------------------------------

    @property
    def audio_only(self) -> bool:
        return self.audio_button.isChecked()

    def _fill_formats(self) -> None:
        self.format_combo.blockSignals(True)
        self.format_combo.clear()
        formats = AUDIO_FORMATS if self.audio_only else VIDEO_FORMATS
        for name in formats:
            self.format_combo.addItem(name.upper(), name)
        wanted = self._audio_format if self.audio_only else self._video_format
        self.format_combo.setCurrentIndex(max(0, self.format_combo.findData(wanted)))
        self.format_combo.blockSignals(False)
        self.quality_combo.setVisible(not self.audio_only)

    def _fill_qualities(self, heights) -> None:
        self.quality_combo.clear()
        self.quality_combo.addItem(fmt.height_label(None), None)
        for height in heights:
            self.quality_combo.addItem(fmt.height_label(height), height)
        # Select the best option that does not exceed what the user last chose.
        index = 0
        if self._preferred_height is not None:
            fitting = [h for h in heights if h <= self._preferred_height]
            if fitting:
                index = self.quality_combo.findData(max(fitting))
            elif heights:
                index = self.quality_combo.findData(min(heights))
        self.quality_combo.setCurrentIndex(max(0, index))

    def _on_kind_changed(self, _button, checked: bool) -> None:
        if checked:
            self._settings.setValue("audio_only", self.audio_only)
            self._fill_formats()

    def _remember_format(self) -> None:
        value = self.format_combo.currentData()
        if value is None:
            return
        if self.audio_only:
            self._audio_format = value
            self._settings.setValue("audio_format", value)
        else:
            self._video_format = value
            self._settings.setValue("video_format", value)

    def _remember_quality(self) -> None:
        self._preferred_height = self.quality_combo.currentData()
        self._settings.setValue("max_height", self._preferred_height or "best")

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose download folder", str(self.output_dir))
        if folder:
            self.set_output_dir(Path(folder))

    def set_output_dir(self, folder: Path) -> None:
        self.output_dir = folder
        self.folder_label.setText(str(folder))
        self._settings.setValue("output_dir", str(folder))

    # -- URL lookup ------------------------------------------------------------

    def paste(self) -> None:
        text = QGuiApplication.clipboard().text().strip()
        if text:
            self.url_edit.setText(text)
            self.lookup()
        self.url_edit.setFocus()

    def _on_url_changed(self, text: str) -> None:
        text = text.strip()
        self.download_button.setEnabled(bool(text))
        self._lookup_token += 1  # Any lookup in flight is now stale.
        self._lookup_timer.stop()
        if self._info is not None or not text:
            self._reset_preview()
        if _looks_like_url(text):
            self._lookup_timer.start()

    def lookup(self) -> None:
        """Fetch title, thumbnail and available qualities for the current URL."""
        self._lookup_timer.stop()
        url = self.url_edit.text().strip()
        if not url:
            return
        if not _looks_like_url(url):
            self._show_message("Enter a full link starting with http:// or https://", error=True)
            return
        self._lookup_token += 1
        token = self._lookup_token
        self._show_message("Looking up this link…")

        def work() -> None:
            try:
                info = fetch_info(url, self._info_options)
            except Exception as exc:
                self._emit(self._infoFailed, token, str(exc) or "Could not read this link")
                return
            self._emit(self._infoReady, token, info, _fetch_thumbnail(info.thumbnail_url))

        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _emit(signal, *args) -> None:
        try:
            signal.emit(*args)
        except RuntimeError:
            pass  # Window closed while the lookup was running.

    def _on_info_ready(self, token: int, info: MediaInfo, thumbnail: bytes | None) -> None:
        if token != self._lookup_token:
            return
        self._info = info
        self.media_title.setText(info.title)
        self.media_title.setVisible(True)
        meta = [info.uploader] if info.uploader else []
        if info.entry_count:
            meta.append(f"{info.entry_count} videos")
        if info.duration:
            meta.append(fmt.clock(info.duration))
        self.media_meta.setText(" · ".join(meta))
        self.media_meta.setVisible(bool(meta))
        self.message.setVisible(False)

        pixmap = QPixmap()
        self._set_thumbnail(pixmap if thumbnail and pixmap.loadFromData(thumbnail) else None)
        self._fill_qualities(info.heights or DEFAULT_HEIGHTS)

        self.playlist_check.setVisible(info.is_playlist)
        # A playlist link can only be downloaded as a playlist; a video that
        # happens to sit inside one defaults to just the video.
        whole = info.is_playlist and info.entry_count is not None
        self.playlist_check.setChecked(whole)
        self.playlist_check.setEnabled(not whole)

    def _on_info_failed(self, token: int, message: str) -> None:
        if token == self._lookup_token:
            self._show_message(message, error=True)

    def _show_message(self, text: str, error: bool = False) -> None:
        self._info = None
        self.media_title.setVisible(False)
        self.media_meta.setVisible(False)
        self._set_thumbnail(None)
        self.playlist_check.setVisible(False)
        self.playlist_check.setChecked(False)
        self.message.setText(text)
        self.message.setObjectName("error" if error else "muted")
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)
        self.message.setVisible(True)

    def _reset_preview(self) -> None:
        self._show_message(_HINT)
        self._fill_qualities(DEFAULT_HEIGHTS)

    def _set_thumbnail(self, pixmap: QPixmap | None) -> None:
        self.thumb.setProperty("placeholder", pixmap is None)
        if pixmap is None:
            self.thumb.setPixmap(icons.pixmap("film", self._theme.muted, 28))
        else:
            self.thumb.setPixmap(rounded(pixmap, THUMB_W, THUMB_H))

    # -- queue -----------------------------------------------------------------

    def enqueue(self) -> QueueItem | None:
        """Queue a download for the current URL and options."""
        url = self.url_edit.text().strip()
        if not _looks_like_url(url):
            self._show_message("Enter a full link starting with http:// or https://", error=True)
            return None
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._show_message(f"Cannot use the download folder: {exc.strerror or exc}", error=True)
            return None

        request = DownloadRequest(
            url=url,
            output_dir=self.output_dir,
            audio_only=self.audio_only,
            file_format=self.format_combo.currentData(),
            max_height=None if self.audio_only else self.quality_combo.currentData(),
            playlist=self.playlist_check.isChecked(),
        )
        title = self._info.title if self._info else url
        job_options = {**self._job_options, "plugin_postprocessors": self.plugins.postprocessors()}
        item = QueueItem(request, title, self._theme, job_options)
        item.changed.connect(self._pump)
        item.removeRequested.connect(self.remove_item)
        self._items.insert(0, item)
        self.queue_layout.insertWidget(0, item)
        self.url_edit.clear()
        self._pump()
        return item

    def _pump(self) -> None:
        """Start waiting downloads while there is a free slot."""
        running = sum(1 for item in self._items if item.active)
        for item in reversed(self._items):  # Oldest first.
            if running >= MAX_CONCURRENT:
                break
            if item.waiting:
                item.start()
                running += 1
        self._refresh_queue_header()

    def remove_item(self, item: QueueItem) -> None:
        if item in self._items and not item.active:
            self._items.remove(item)
            self.queue_layout.removeWidget(item)
            item.deleteLater()
            self._refresh_queue_header()

    def clear_finished(self) -> None:
        for item in [i for i in self._items if i.state.finished]:
            self.remove_item(item)

    def _refresh_queue_header(self) -> None:
        active = sum(1 for item in self._items if not item.state.finished)
        finished = len(self._items) - active
        self.empty_label.setVisible(not self._items)
        self.clear_button.setVisible(finished > 0)
        self.queue_summary.setText(f"{active} in progress" if active else "")

    # -- window events ---------------------------------------------------------

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        mime = event.mimeData()
        text = mime.urls()[0].toString() if mime.hasUrls() else mime.text().strip()
        if text:
            self.url_edit.setText(text)
            self.lookup()

    def closeEvent(self, event) -> None:  # noqa: N802
        busy = [item for item in self._items if not item.state.finished]
        if busy:
            answer = QMessageBox.question(
                self,
                "Quit and cancel downloads?",
                f"{len(busy)} download{'s are' if len(busy) > 1 else ' is'} still in progress. "
                "Quitting will cancel and discard the unfinished files.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            for item in busy:
                item.cancel()
        self._settings.setValue("geometry", self.saveGeometry())
        event.accept()
