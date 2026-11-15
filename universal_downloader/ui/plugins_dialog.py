"""Dialog for installing and removing yt-dlp plugins."""

from __future__ import annotations

import html
import threading
from typing import Callable, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.plugins import CATALOG, CatalogEntry, InstalledPlugin, PluginManager
from .theme import Theme

_INTRO = (
    "Plugins add features to the download engine. They are written by other "
    "people and run with the same access to your computer as this app, so only "
    "install ones you trust."
)
_CUSTOM_HINT = (
    "Any other yt-dlp plugin can be installed from its zip archive. Plugins that "
    "add support for more sites work straight away; other kinds may need options "
    "this app does not set."
)


class PluginRow(QFrame):
    """One plugin, with an Install or Remove button."""

    installRequested = Signal(object)
    removeRequested = Signal(str)

    def __init__(
        self,
        plugin_id: str,
        name: str,
        details: str,
        description: str = "",
        note: str = "",
        entry: CatalogEntry | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.plugin_id = plugin_id
        self.entry = entry
        self._installed = False
        self._busy = False

        self.name_label = QLabel(name)
        self.name_label.setObjectName("itemTitle")
        self.name_label.setTextFormat(Qt.TextFormat.PlainText)
        self.badge = QLabel("Installed")
        self.badge.setObjectName("chip")
        title = QHBoxLayout()
        title.setSpacing(8)
        title.addWidget(self.name_label)
        title.addWidget(self.badge)
        title.addStretch(1)

        # ``details`` may contain a link, so it is rich text built by the caller.
        self.details_label = QLabel(details)
        self.details_label.setObjectName("muted")
        self.details_label.setOpenExternalLinks(True)
        self.details_label.setWordWrap(True)

        text = QVBoxLayout()
        text.setSpacing(4)
        text.addLayout(title)
        text.addWidget(self.details_label)
        for content in (description, note):
            if content:
                label = QLabel(content)
                label.setTextFormat(Qt.TextFormat.PlainText)
                label.setWordWrap(True)
                if content is note:
                    label.setObjectName("muted")
                text.addWidget(label)
        self.error_label = QLabel()
        self.error_label.setObjectName("error")
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        text.addWidget(self.error_label)

        self.button = QPushButton()
        self.button.setMinimumWidth(96)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.clicked.connect(self._clicked)

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 12, 12)
        row.setSpacing(12)
        row.addLayout(text, 1)
        row.addWidget(self.button, 0, Qt.AlignmentFlag.AlignTop)
        self._refresh()

    @property
    def installed(self) -> bool:
        return self._installed

    def set_installed(self, installed: bool) -> None:
        self._installed = installed
        self._busy = False
        self._refresh()

    def set_busy(self) -> None:
        self._busy = True
        self.error_label.clear()
        self.error_label.setVisible(False)
        self._refresh()

    def set_error(self, message: str) -> None:
        self._busy = False
        self.error_label.setText(message)
        self.error_label.setVisible(bool(message))
        self._refresh()

    def _refresh(self) -> None:
        self.badge.setVisible(self._installed)
        self.button.setEnabled(not self._busy)
        if self._busy:
            self.button.setText("Installing…")
        else:
            self.button.setText("Remove" if self._installed else "Install")
        self.button.setAccessibleName(f"{self.button.text()} {self.name_label.text()}")

    def _clicked(self) -> None:
        if self._installed:
            self.removeRequested.emit(self.plugin_id)
        elif self.entry is not None:
            self.installRequested.emit(self.entry)


class PluginsDialog(QDialog):
    # (plugin id, InstalledPlugin on success or an error message)
    _installFinished = Signal(str, object)

    def __init__(
        self,
        manager: PluginManager,
        theme: Theme,
        parent=None,
        catalog: Sequence[CatalogEntry] = CATALOG,
        confirm: Callable[[str], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager
        self._catalog = tuple(catalog)
        self._confirm = confirm or self._ask
        self._rows: dict[str, PluginRow] = {}
        self._custom_busy = False

        self.setWindowTitle("Plugins")
        self.resize(640, 600)
        self.setMinimumSize(480, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        heading = QLabel("Plugins")
        heading.setObjectName("title")
        intro = QLabel(_INTRO)
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(intro)

        body = QWidget()
        body.setObjectName("queueBody")
        self.rows_layout = QVBoxLayout(body)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(8)
        self.rows_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        scroll.viewport().setAutoFillBackground(False)
        layout.addWidget(scroll, 1)

        # Install from an archive
        custom_title = QLabel("Install from a zip file or link")
        custom_title.setObjectName("sectionTitle")
        custom_hint = QLabel(_CUSTOM_HINT)
        custom_hint.setObjectName("muted")
        custom_hint.setWordWrap(True)
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("https://…/plugin.zip or a file on this computer")
        self.source_edit.setAccessibleName("Plugin zip file or link")
        self.source_edit.textChanged.connect(self._refresh_custom)
        self.source_edit.returnPressed.connect(self.install_custom)
        self.browse_button = QPushButton("Browse")
        self.browse_button.setMinimumHeight(38)
        self.browse_button.clicked.connect(self._browse)
        self.custom_button = QPushButton("Install")
        self.custom_button.setMinimumHeight(38)
        self.custom_button.clicked.connect(self.install_custom)
        source_row = QHBoxLayout()
        source_row.setSpacing(8)
        source_row.addWidget(self.source_edit, 1)
        source_row.addWidget(self.browse_button)
        source_row.addWidget(self.custom_button)
        self.custom_error = QLabel()
        self.custom_error.setObjectName("error")
        self.custom_error.setTextFormat(Qt.TextFormat.PlainText)
        self.custom_error.setWordWrap(True)
        self.custom_error.setVisible(False)
        layout.addWidget(custom_title)
        layout.addWidget(custom_hint)
        layout.addLayout(source_row)
        layout.addWidget(self.custom_error)

        self.restart_label = QLabel("Restart the app to finish removing that plugin.")
        self.restart_label.setObjectName("warning")
        close_button = QPushButton("Close")
        close_button.setMinimumWidth(96)
        close_button.clicked.connect(self.accept)
        footer = QHBoxLayout()
        footer.addWidget(self.restart_label)
        footer.addStretch(1)
        footer.addWidget(close_button)
        layout.addLayout(footer)

        self._installFinished.connect(self._on_install_finished)
        self.reload()

    # -- rows ------------------------------------------------------------------

    def row(self, plugin_id: str) -> PluginRow | None:
        return self._rows.get(plugin_id)

    def reload(self) -> None:
        """Rebuild the list from the catalog plus whatever is installed."""
        for row in self._rows.values():
            self.rows_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        installed = {p.id: p for p in self.manager.installed()}
        for entry in self._catalog:
            self._add_row(self._catalog_row(entry), entry.id in installed)
        catalog_ids = {e.id for e in self._catalog}
        for plugin in installed.values():
            if plugin.id not in catalog_ids:
                self._add_row(self._custom_row(plugin), True)
        self.restart_label.setVisible(self.manager.needs_restart)
        self._refresh_custom()

    def _add_row(self, row: PluginRow, installed: bool) -> None:
        row.set_installed(installed)
        row.installRequested.connect(self.install)
        row.removeRequested.connect(self.remove)
        self._rows[row.plugin_id] = row
        self.rows_layout.insertWidget(self.rows_layout.count() - 1, row)

    @staticmethod
    def _catalog_row(entry: CatalogEntry) -> PluginRow:
        parts = [f"by {html.escape(entry.author)}"]
        if entry.license:
            parts.append(f"{html.escape(entry.license)} licence")
        parts.append(f'<a href="{html.escape(entry.homepage, quote=True)}">Source code</a>')
        note = f"Looks things up on {entry.contacts} for each download." if entry.contacts else ""
        return PluginRow(entry.id, entry.name, " · ".join(parts), entry.description, note, entry)

    @staticmethod
    def _custom_row(plugin: InstalledPlugin) -> PluginRow:
        return PluginRow(plugin.id, plugin.name, f"Installed from {html.escape(plugin.source)}")

    # -- actions ---------------------------------------------------------------

    def install(self, entry: CatalogEntry) -> None:
        row = self._rows.get(entry.id)
        if row is None or row.installed:
            return
        row.set_busy()
        self._run(entry.id, lambda: self.manager.install(entry))

    def install_custom(self) -> None:
        source = self.source_edit.text().strip()
        if not source or self._custom_busy:
            return
        if not self._confirm(source):
            return
        self._custom_busy = True
        self._set_custom_error("")
        self._refresh_custom()
        self._run("", lambda: self.manager.install_archive(source))

    def remove(self, plugin_id: str) -> None:
        self.manager.remove(plugin_id)
        self.reload()

    def _run(self, plugin_id: str, work: Callable[[], InstalledPlugin]) -> None:
        def task() -> None:
            try:
                result: object = work()
            except Exception as exc:
                result = str(exc) or "The plugin could not be installed."
            try:
                self._installFinished.emit(plugin_id, result)
            except RuntimeError:
                pass  # Dialog closed while installing.

        threading.Thread(target=task, daemon=True).start()

    def _on_install_finished(self, plugin_id: str, result: object) -> None:
        failed = isinstance(result, str)
        if not plugin_id:
            self._custom_busy = False
            if failed:
                self._set_custom_error(result)
                self._refresh_custom()
                return
            self.source_edit.clear()
        elif failed:
            row = self._rows.get(plugin_id)
            if row is not None:
                row.set_error(result)
            return
        self.reload()

    # -- custom source ---------------------------------------------------------

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a plugin archive", "", "Zip archives (*.zip *.whl)")
        if path:
            self.source_edit.setText(path)

    def _refresh_custom(self) -> None:
        busy = self._custom_busy
        self.custom_button.setEnabled(bool(self.source_edit.text().strip()) and not busy)
        self.custom_button.setText("Installing…" if busy else "Install")
        self.source_edit.setEnabled(not busy)
        self.browse_button.setEnabled(not busy)

    def _set_custom_error(self, message: str) -> None:
        self.custom_error.setText(message)
        self.custom_error.setVisible(bool(message))

    def _ask(self, source: str) -> bool:
        answer = QMessageBox.question(
            self,
            "Install this plugin?",
            "This plugin is not on the built-in list, so it has not been checked. "
            "It will be able to do anything this app can do on your computer.\n\n"
            f"{source}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes
