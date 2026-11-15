"""Dialog for installing and removing yt-dlp plugins."""

from __future__ import annotations

import html
import threading
from typing import Callable, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.discovery import RepoInfo, search_topic
from ..core.plugins import (
    CATALOG,
    WHEN_LABELS,
    CatalogEntry,
    InstalledPlugin,
    PluginError,
    PluginManager,
    format_options,
    parse_options,
    slug,
)
from .theme import Theme

_INTRO = (
    "Plugins add features to the download engine. They are written by other "
    "people and run with the same access to your computer as this app, so only "
    "install ones you trust."
)
_FOUND_HINT = (
    "Everything tagged yt-dlp-plugins on GitHub. None of it has been reviewed, and "
    "many are for other tools or need extra software, so some will not work here. "
    "Plugins that add site support are the ones most likely to."
)
_MAX_FOUND_ROWS = 40
_CUSTOM_HINT = (
    "Any other yt-dlp plugin can be installed from its zip archive or GitHub page. "
    "Plugins that add site support work straight away. Plugins that add a "
    "processing step get a switch and options in the list above."
)


class PostprocessorSettings(QWidget):
    """Switch, timing and options for each processing step a plugin provides."""

    #: step name, switched on, stage, options text
    changed = Signal(str, bool, str, str)

    def __init__(self, plugin: InstalledPlugin, parent=None) -> None:
        super().__init__(parent)
        self._errors: dict[str, QLabel] = {}
        self._checks: dict[str, QCheckBox] = {}
        self._whens: dict[str, QComboBox] = {}
        self._options: dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(8)
        for key in plugin.pp_keys:
            step = plugin.pp_config[key]
            check = QCheckBox(f"Use {key} on new downloads")
            check.setChecked(step["enabled"])
            when = QComboBox()
            when.setAccessibleName(f"When {key} runs")
            for stage, label in WHEN_LABELS.items():
                when.addItem(label, stage)
            when.setCurrentIndex(max(0, when.findData(step["when"])))
            options = QLineEdit(format_options(step["options"]))
            options.setPlaceholderText("name=value; name=value  (optional)")
            options.setAccessibleName(f"Options for {key}")
            error = QLabel()
            error.setObjectName("error")
            error.setWordWrap(True)
            error.setTextFormat(Qt.TextFormat.PlainText)
            error.setVisible(False)
            self._checks[key], self._whens[key] = check, when
            self._options[key], self._errors[key] = options, error

            def emit(*_args, key=key) -> None:
                self.changed.emit(
                    key,
                    self._checks[key].isChecked(),
                    self._whens[key].currentData(),
                    self._options[key].text(),
                )

            check.toggled.connect(emit)
            when.activated.connect(emit)
            options.editingFinished.connect(emit)

            grid = QGridLayout()
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(6)
            grid.setColumnStretch(1, 1)
            runs = QLabel("Runs")
            runs.setObjectName("muted")
            opts = QLabel("Options")
            opts.setObjectName("muted")
            grid.addWidget(runs, 0, 0)
            grid.addWidget(when, 0, 1)
            grid.addWidget(opts, 1, 0)
            grid.addWidget(options, 1, 1)
            layout.addWidget(check)
            layout.addLayout(grid)
            layout.addWidget(error)
        note = QLabel("Changes apply to downloads you start afterwards.")
        note.setObjectName("muted")
        layout.addWidget(note)

    def set_error(self, key: str, message: str) -> None:
        label = self._errors.get(key)
        if label is not None:
            label.setText(message)
            label.setVisible(bool(message))


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
        entry: object | None = None,
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
        self._text_layout = text
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

    def add_widget(self, widget: QWidget) -> None:
        """Add ``widget`` below the description (above any error message)."""
        self._text_layout.insertWidget(self._text_layout.count() - 1, widget)

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
    # list[RepoInfo] on success, an error message otherwise
    _discovered = Signal(object)

    def __init__(
        self,
        manager: PluginManager,
        theme: Theme,
        parent=None,
        catalog: Sequence[CatalogEntry] = CATALOG,
        confirm: Callable[[str], bool] | None = None,
        discover: Callable[[], Sequence[RepoInfo]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager
        self._catalog = tuple(catalog)
        self._confirm = confirm or self._ask
        self._rows: dict[str, PluginRow] = {}
        self._step_settings: dict[str, PostprocessorSettings] = {}
        self._found_rows: dict[str, PluginRow] = {}
        self._found: list[RepoInfo] | None = None
        self._discover = discover or (lambda: search_topic(self.manager.opener))
        self._discovering = False
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
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(8)
        body_layout.addLayout(self.rows_layout)

        found_title = QLabel("More from GitHub")
        found_title.setObjectName("sectionTitle")
        found_hint = QLabel(_FOUND_HINT)
        found_hint.setObjectName("muted")
        found_hint.setWordWrap(True)
        self.browse_found_button = QPushButton("Browse plugins on GitHub")
        self.browse_found_button.setMinimumHeight(38)
        self.browse_found_button.clicked.connect(self.discover)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by name or description")
        self.filter_edit.setAccessibleName("Filter plugins")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setVisible(False)
        self.filter_edit.textChanged.connect(self._render_found)
        found_row = QHBoxLayout()
        found_row.setSpacing(8)
        found_row.addWidget(self.browse_found_button)
        found_row.addWidget(self.filter_edit, 1)
        self.found_status = QLabel()
        self.found_status.setObjectName("muted")
        self.found_status.setWordWrap(True)
        self.found_status.setTextFormat(Qt.TextFormat.PlainText)
        self.found_status.setVisible(False)
        self.found_layout = QVBoxLayout()
        self.found_layout.setSpacing(8)
        body_layout.addSpacing(10)
        body_layout.addWidget(found_title)
        body_layout.addWidget(found_hint)
        body_layout.addLayout(found_row)
        body_layout.addWidget(self.found_status)
        body_layout.addLayout(self.found_layout)
        body_layout.addStretch(1)
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
        self._discovered.connect(self._on_discovered)
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
        self._step_settings.clear()

        installed = {p.id: p for p in self.manager.installed()}
        for entry in self._catalog:
            self._add_row(self._catalog_row(entry), entry.id in installed)
            if entry.id in installed:
                self._attach_settings(installed[entry.id])
        catalog_ids = {e.id for e in self._catalog}
        for plugin in installed.values():
            if plugin.id not in catalog_ids:
                self._add_row(self._custom_row(plugin), True)
                self._attach_settings(plugin)
        self.restart_label.setVisible(self.manager.needs_restart)
        self._refresh_custom()
        self._render_found()

    def _add_row(self, row: PluginRow, installed: bool) -> None:
        row.set_installed(installed)
        row.installRequested.connect(self.install)
        row.removeRequested.connect(self.remove)
        self._rows[row.plugin_id] = row
        self.rows_layout.addWidget(row)

    def _attach_settings(self, plugin: InstalledPlugin) -> None:
        if not plugin.pp_keys:
            return
        settings = PostprocessorSettings(plugin)
        settings.changed.connect(lambda key, on, when, text, pid=plugin.id: self._configure(pid, key, on, when, text))
        self._step_settings[plugin.id] = settings
        self._rows[plugin.id].add_widget(settings)

    def _configure(self, plugin_id: str, key: str, enabled: bool, when: str, options_text: str) -> None:
        """Save a change made in a plugin's step settings."""
        settings = self._step_settings.get(plugin_id)
        try:
            self.manager.configure_postprocessor(
                plugin_id, key, enabled=enabled, when=when, options=parse_options(options_text)
            )
            message = ""
        except PluginError as exc:
            message = str(exc)
        if settings is not None:
            settings.set_error(key, message)

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
        notes = []
        if "extractor" in plugin.kinds:
            notes.append("Adds support for more sites or YouTube features; works on its own.")
        if "postprocessor" in plugin.kinds:
            notes.append(
                "Adds a processing step. It starts switched off; turn it on below, and "
                "check the plugin's page for the options it accepts."
            )
        if plugin.revision:
            notes.append(f"Version {plugin.revision[:10]}.")
        return PluginRow(
            plugin.id, plugin.name, f"Installed from {html.escape(plugin.source)}", note=" ".join(notes)
        )

    # -- GitHub browsing -------------------------------------------------------

    def discover(self) -> None:
        if self._discovering:
            return
        self._discovering = True
        self.browse_found_button.setEnabled(False)
        self.browse_found_button.setText("Loading…")
        self._set_found_status("")

        def task() -> None:
            try:
                result: object = list(self._discover())
            except Exception as exc:
                result = str(exc) or "Could not load the list."
            try:
                self._discovered.emit(result)
            except RuntimeError:
                pass  # Dialog closed while loading.

        threading.Thread(target=task, daemon=True).start()

    def _on_discovered(self, result: object) -> None:
        self._discovering = False
        self.browse_found_button.setEnabled(True)
        if isinstance(result, str):
            self.browse_found_button.setText("Try again")
            self._set_found_status(result, error=True)
            return
        self._found = list(result)
        self.browse_found_button.setText("Refresh list")
        self.filter_edit.setVisible(True)
        self._render_found()

    def _set_found_status(self, text: str, error: bool = False) -> None:
        self.found_status.setText(text)
        self.found_status.setObjectName("error" if error else "muted")
        self.found_status.style().unpolish(self.found_status)
        self.found_status.style().polish(self.found_status)
        self.found_status.setVisible(bool(text))

    def _render_found(self) -> None:
        for row in self._found_rows.values():
            self.found_layout.removeWidget(row)
            row.deleteLater()
        self._found_rows.clear()
        if self._found is None:
            return

        installed = self.manager.installed()
        taken = {e.id for e in self._catalog} | {p.id for p in installed}
        # Plugins already offered or installed under another name (built-in list,
        # a pasted link, a zip) are recognised by their repository.
        known_repos = {e.homepage.rstrip("/").lower() for e in self._catalog}
        known_sources = " ".join(p.source.lower() for p in installed)
        needle = self.filter_edit.text().strip().lower()
        matches = [
            repo
            for repo in self._found
            if repo.id not in taken
            and slug(repo.name) not in taken
            and repo.url.rstrip("/").lower() not in known_repos
            and f"/{repo.full_name.lower()}/" not in known_sources
            and (not needle or needle in repo.full_name.lower() or needle in repo.description.lower())
        ]
        for repo in matches[:_MAX_FOUND_ROWS]:
            row = self._found_row(repo)
            row.set_installed(False)
            row.installRequested.connect(self.install)
            self._found_rows[repo.id] = row
            self.found_layout.addWidget(row)

        if not matches:
            self._set_found_status("Nothing matches." if needle else "Nothing new to show.")
        elif len(matches) > _MAX_FOUND_ROWS:
            self._set_found_status(
                f"Showing the {_MAX_FOUND_ROWS} most popular of {len(matches)}. Use the filter to narrow it down."
            )
        else:
            self._set_found_status(f"{len(matches)} found.")

    @staticmethod
    def _found_row(repo: RepoInfo) -> PluginRow:
        parts = [f"{repo.stars:,} stars"]
        if repo.pushed:
            parts.append(f"updated {html.escape(repo.pushed)}")
        if repo.license:
            parts.append(html.escape(repo.license))
        parts.append(f'<a href="{html.escape(repo.url, quote=True)}">Source code</a>')
        return PluginRow(
            repo.id,
            repo.full_name,
            " · ".join(parts),
            repo.description,
            "Not reviewed. Written by a third party.",
            repo,
        )

    # -- actions ---------------------------------------------------------------

    def install(self, entry: CatalogEntry | RepoInfo) -> None:
        if isinstance(entry, RepoInfo):
            row = self._found_rows.get(entry.id)
            if row is None or row.installed or not self._confirm(entry.url):
                return
            row.set_busy()
            self._run(entry.id, lambda: self.manager.install_github(entry.full_name, entry.default_branch))
            return
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
            row = self._rows.get(plugin_id) or self._found_rows.get(plugin_id)
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
            "This plugin is not on the built-in list, so nobody has checked it. "
            "It will be able to do anything this app can do on your computer.\n\n"
            f"{source}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes
