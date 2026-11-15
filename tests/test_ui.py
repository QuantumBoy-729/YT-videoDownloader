"""Drives the real window (offscreen) against the local test server."""

from __future__ import annotations

import time
import urllib.request

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from yt_downloader.core import JobState, PluginManager  # noqa: E402
from yt_downloader.ui import fmt  # noqa: E402
from yt_downloader.ui.main_window import MAX_CONCURRENT, MainWindow  # noqa: E402
from yt_downloader.ui.plugins_dialog import PluginsDialog  # noqa: E402

from .conftest import NO_PROXY  # noqa: E402
from .test_plugins import entry, pp_zip  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("output_dir", str(tmp_path / "out"))
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    win = MainWindow(
        settings=settings,
        job_options={"extra_opts": NO_PROXY},
        info_options=NO_PROXY,
        plugins=PluginManager(tmp_path / "plugins", opener=opener),
    )
    win.show()
    yield win
    for item in list(win._items):
        item.cancel()
    pump(app, lambda: all(i.state.finished for i in win._items))
    win._items.clear()  # Skip the "quit?" prompt.
    win.close()


def pump(app, predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_initial_state(window):
    assert not window.download_button.isEnabled()
    assert window.empty_label.isVisible()
    assert not window.clear_button.isVisible()
    assert window.format_combo.currentData() == "mp4"
    assert window.quality_combo.currentData() == 1080


def test_lookup_then_download(app, window, server, tmp_path):
    window.url_edit.setText(f"{server}/clip.mp4")
    window.lookup()
    assert pump(app, lambda: window._info is not None)
    assert window.media_title.text() == "clip"
    assert window.download_button.isEnabled()

    item = window.enqueue()
    assert item is not None
    assert window.url_edit.text() == ""
    assert not window.empty_label.isVisible()
    assert pump(app, lambda: item.result is not None)

    assert item.state is JobState.DONE, item.result.error
    assert item.bar.value() == item.bar.maximum()
    assert item.status_label.fullText().startswith("Saved to")
    assert item.folder_button.isVisible() and not item.pause_button.isVisible()
    assert [p.suffix for p in (tmp_path / "out").iterdir()] == [".mp4"]

    assert window.clear_button.isVisible()
    window.clear_finished()
    assert window._items == []
    assert window.empty_label.isVisible()


def test_lookup_error_is_shown_and_cleared(app, window, server):
    window.url_edit.setText(f"{server}/missing.mp4")
    window.lookup()
    assert pump(app, lambda: window.message.objectName() == "error")
    assert "404" in window.message.text()
    window.url_edit.setText("")
    assert window.message.objectName() == "muted"


def test_rejects_non_url(window):
    window.url_edit.setText("not a link")
    assert window.enqueue() is None
    assert window.message.objectName() == "error"
    assert window._items == []


def test_stale_lookup_is_ignored(app, window, server):
    window.url_edit.setText(f"{server}/slow/clip.mp4")
    window.lookup()
    window.url_edit.setText("")  # User cleared the box before the answer arrived.
    pump(app, lambda: False, timeout=1.5)
    assert window._info is None
    assert not window.media_title.isVisible()


def test_audio_mode_switches_formats(window):
    window.audio_button.setChecked(True)
    assert [window.format_combo.itemData(i) for i in range(window.format_combo.count())] == [
        "mp3", "m4a", "opus",
    ]
    assert not window.quality_combo.isVisible()
    window.video_button.setChecked(True)
    assert window.format_combo.currentData() == "mp4"
    assert window.quality_combo.isVisible()


def test_pause_resume_cancel_retry(app, window, server):
    window.url_edit.setText(f"{server}/slow/clip.mp4")
    item = window.enqueue()
    assert pump(app, lambda: item._last is not None and item._last.downloaded > 0)

    item.pause_button.click()
    assert pump(app, lambda: item.state is JobState.PAUSED)
    assert item.pause_button.toolTip() == "Resume"
    assert "Paused" in item.status_label.fullText()

    item.pause_button.click()
    assert pump(app, lambda: item.state is JobState.RUNNING)

    item.close_button.click()
    assert pump(app, lambda: item.result is not None)
    assert item.state is JobState.CANCELLED
    assert item.retry_button.isVisible()
    assert list(window.output_dir.iterdir()) == []

    item.retry_button.click()
    assert pump(app, lambda: item.result is not None and item.state is JobState.DONE)


def test_failed_download_shows_reason(app, window, server):
    window.url_edit.setText(f"{server}/missing.mp4")
    item = window.enqueue()
    assert pump(app, lambda: item.result is not None)
    assert item.state is JobState.FAILED
    assert "404" in item.status_label.fullText()
    assert item.retry_button.isVisible()


def test_queue_limits_concurrency(app, window, server):
    items = []
    for _ in range(MAX_CONCURRENT + 2):
        window.url_edit.setText(f"{server}/slow/clip.mp4")
        items.append(window.enqueue())
    app.processEvents()
    assert sum(i.active for i in items) == MAX_CONCURRENT
    assert sum(i.waiting for i in items) == 2
    assert items[0].active, "oldest download should start first"

    # Cancelling a waiting item must not start it; freeing a slot starts the next.
    items[-1].cancel()
    items[0].cancel()
    assert pump(app, lambda: items[0].result is not None)
    assert pump(app, lambda: items[2].active)
    assert items[-1].state is JobState.CANCELLED


def test_settings_persist(app, window, tmp_path):
    window.audio_button.setChecked(True)
    window.format_combo.setCurrentIndex(window.format_combo.findData("m4a"))
    window.set_output_dir(tmp_path / "elsewhere")
    window.toggle_theme()
    theme = window._theme.name

    again = MainWindow(settings=window._settings, plugins=window.plugins)
    assert again.audio_only
    assert again.format_combo.currentData() == "m4a"
    assert again.output_dir == tmp_path / "elsewhere"
    assert again._theme.name == theme
    again.close()


def test_quality_list_follows_available_heights(window):
    window._preferred_height = 1080
    window._fill_qualities((720, 480, 360))
    assert window.quality_combo.currentData() == 720
    window._fill_qualities((2160, 1440))
    assert window.quality_combo.currentData() == 1440
    window._preferred_height = None
    window._fill_qualities((2160, 1080))
    assert window.quality_combo.currentData() is None


@pytest.mark.parametrize(
    "value, expected",
    [(0, "0 B"), (2048, "2 KB"), (5 * 1024**2, "5.0 MB"), (3 * 1024**3, "3.0 GB"), (None, "?")],
)
def test_size_format(value, expected):
    assert fmt.size(value) == expected


def test_clock_format():
    assert fmt.clock(75) == "1:15"
    assert fmt.clock(3675) == "1:01:15"
    assert fmt.clock(None) == ""


# -- plugins ---------------------------------------------------------------------


@pytest.fixture
def dialog(window, server, media_dir):
    (media_dir / "ui-plugin.zip").write_bytes(pp_zip("UiMarker"))
    catalog = (
        entry("ui-marker", f"{server}/ui-plugin.zip", "UiMarker"),
        entry("ui-broken", f"{server}/does-not-exist.zip", "UiBroken"),
    )
    answers = {"confirm": True, "asked": []}

    def confirm(source):
        answers["asked"].append(source)
        return answers["confirm"]

    dlg = PluginsDialog(window.plugins, window._theme, window, catalog=catalog, confirm=confirm)
    dlg.answers = answers
    dlg.show()
    yield dlg
    dlg.close()


def test_plugins_dialog_lists_catalog(dialog):
    assert list(dialog._rows) == ["ui-marker", "ui-broken"]
    row = dialog.row("ui-marker")
    assert row.button.text() == "Install" and not row.badge.isVisible()
    assert not dialog.restart_label.isVisible()
    assert not dialog.custom_button.isEnabled()


def test_default_dialog_shows_the_real_catalog(app, window):
    from yt_downloader.core import CATALOG

    dlg = window.show_plugins()
    assert list(dlg._rows) == [e.id for e in CATALOG]
    assert all(r.button.text() == "Install" for r in dlg._rows.values())
    dlg.close()


def test_install_and_remove_from_dialog(app, window, dialog, server, tmp_path):
    dialog.row("ui-marker").button.click()
    assert dialog.row("ui-marker").button.text() == "Installing…"
    assert pump(app, lambda: dialog.row("ui-marker").installed)
    # The list is rebuilt after an install; let Qt show the new row.
    assert pump(app, lambda: dialog.row("ui-marker").badge.isVisible())
    row = dialog.row("ui-marker")
    assert row.button.text() == "Remove"
    assert window.plugins.is_installed("ui-marker")

    # The plugin now takes part in downloads started from the main window.
    window.url_edit.setText(f"{server}/clip.mp4")
    item = window.enqueue()
    assert pump(app, lambda: item.result is not None)
    assert item.state is JobState.DONE, item.result.error
    assert sorted(p.suffix for p in (tmp_path / "out").iterdir()) == [".UiMarker", ".mp4"]

    dialog.row("ui-marker").button.click()
    assert not window.plugins.is_installed("ui-marker")
    assert dialog.row("ui-marker").button.text() == "Install"
    assert not dialog.restart_label.isVisible()


def test_failed_install_shows_reason(app, dialog):
    dialog.row("ui-broken").button.click()
    assert pump(app, lambda: dialog.row("ui-broken").error_label.isVisible())
    row = dialog.row("ui-broken")
    assert "Could not download" in row.error_label.text()
    assert row.button.text() == "Install" and row.button.isEnabled()


def test_custom_install_needs_confirmation(app, window, dialog, tmp_path):
    archive = tmp_path / "Extra-Site.zip"
    archive.write_bytes(pp_zip("ExtraSite"))
    dialog.source_edit.setText(str(archive))
    assert dialog.custom_button.isEnabled()

    dialog.answers["confirm"] = False
    dialog.custom_button.click()
    assert dialog.answers["asked"] == [str(archive)]
    assert window.plugins.installed() == []

    dialog.answers["confirm"] = True
    dialog.custom_button.click()
    assert pump(app, lambda: dialog.row("extra-site") is not None)
    assert dialog.row("extra-site").installed
    assert pump(app, lambda: dialog.row("extra-site").badge.isVisible())
    assert dialog.source_edit.text() == ""

    dialog.row("extra-site").button.click()
    assert dialog.row("extra-site") is None
    assert dialog.restart_label.isVisible()


def test_custom_install_error(app, dialog, tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"nope")
    dialog.source_edit.setText(str(bad))
    dialog.custom_button.click()
    assert pump(app, lambda: dialog.custom_error.isVisible())
    assert "not a zip" in dialog.custom_error.text()
    assert dialog.custom_button.isEnabled() and dialog.source_edit.isEnabled()
