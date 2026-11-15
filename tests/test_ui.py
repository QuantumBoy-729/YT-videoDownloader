"""Drives the real window (offscreen) against the local test server."""

from __future__ import annotations

import time
import urllib.request

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from universal_downloader.core import JobState, PluginManager, RepoInfo  # noqa: E402
from universal_downloader.ui import fmt  # noqa: E402
from universal_downloader.ui.main_window import MAX_CONCURRENT, MainWindow  # noqa: E402
from universal_downloader.ui.plugins_dialog import PluginsDialog  # noqa: E402

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
    from universal_downloader.core import CATALOG

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


# -- browsing GitHub ---------------------------------------------------------------


def repo(name, stars=10, description="", owner="someone"):
    return RepoInfo(
        full_name=f"{owner}/{name}", description=description, stars=stars,
        pushed="2026-10-01", license="MIT", default_branch="main",
    )


@pytest.fixture
def browser(window, server, media_dir):
    (media_dir / "found.zip").write_bytes(pp_zip("Found"))
    state = {"repos": [], "error": None, "confirm": True, "asked": [], "installs": []}

    def discover():
        if state["error"]:
            raise RuntimeError(state["error"])
        return state["repos"]

    def confirm(url):
        state["asked"].append(url)
        return state["confirm"]

    dlg = PluginsDialog(window.plugins, window._theme, window, catalog=(), confirm=confirm, discover=discover)
    # Serve every repo's archive from the local test server.
    original = window.plugins.install_github

    def install_github(full_name, ref=""):
        state["installs"].append((full_name, ref))
        from universal_downloader.core import plugins as plugins_module

        return window.plugins._install(
            plugins_module.slug(full_name.replace("/", "-")), full_name.split("/")[1],
            f"{server}/found.zip", "", (),
        )

    window.plugins.install_github = install_github
    dlg.state = state
    dlg.show()
    yield dlg
    window.plugins.install_github = original
    dlg.close()


def test_found_list_is_hidden_until_browsing(browser):
    assert browser._found_rows == {}
    assert not browser.filter_edit.isVisible() and not browser.found_status.isVisible()
    assert browser.browse_found_button.text() == "Browse plugins on GitHub"


def test_browse_lists_repos(app, browser):
    browser.state["repos"] = [repo("alpha", 500, "Adds alpha site"), repo("beta", 20)]
    browser.browse_found_button.click()
    assert browser.browse_found_button.text() == "Loading…" and not browser.browse_found_button.isEnabled()
    assert pump(app, lambda: len(browser._found_rows) == 2)
    assert list(browser._found_rows) == ["someone-alpha", "someone-beta"]
    assert browser.browse_found_button.text() == "Refresh list" and browser.browse_found_button.isEnabled()
    assert browser.filter_edit.isVisible()
    assert browser.found_status.text() == "2 found."
    row = browser._found_rows["someone-alpha"]
    assert row.button.text() == "Install" and "500 stars" in row.details_label.text()


def test_browse_error_can_be_retried(app, browser):
    browser.state["error"] = "GitHub's request limit was reached."
    browser.browse_found_button.click()
    assert pump(app, lambda: browser.found_status.isVisible())
    assert browser.found_status.text() == "GitHub's request limit was reached."
    assert browser.found_status.objectName() == "error"
    assert browser.browse_found_button.text() == "Try again" and browser.browse_found_button.isEnabled()

    browser.state.update(error=None, repos=[repo("alpha")])
    browser.browse_found_button.click()
    assert pump(app, lambda: "someone-alpha" in browser._found_rows)
    assert browser.found_status.objectName() == "muted"


def test_filter_matches_name_and_description(app, browser):
    browser.state["repos"] = [repo("alpha-site", description="Video host"), repo("beta", description="Subtitles")]
    browser.browse_found_button.click()
    assert pump(app, lambda: len(browser._found_rows) == 2)

    browser.filter_edit.setText("subtitle")
    assert list(browser._found_rows) == ["someone-beta"]
    browser.filter_edit.setText("ALPHA")
    assert list(browser._found_rows) == ["someone-alpha-site"]
    browser.filter_edit.setText("zzz")
    assert browser._found_rows == {} and browser.found_status.text() == "Nothing matches."
    browser.filter_edit.clear()
    assert len(browser._found_rows) == 2


def test_only_the_most_popular_are_shown(app, browser):
    browser.state["repos"] = [repo(f"plugin-{i}") for i in range(60)]
    browser.browse_found_button.click()
    assert pump(app, lambda: len(browser._found_rows) == 40)
    assert "40 most popular of 60" in browser.found_status.text()


def test_install_found_plugin_asks_first(app, window, browser):
    browser.state["repos"] = [repo("alpha")]
    browser.browse_found_button.click()
    assert pump(app, lambda: "someone-alpha" in browser._found_rows)

    browser.state["confirm"] = False
    browser._found_rows["someone-alpha"].button.click()
    assert browser.state["asked"] == ["https://github.com/someone/alpha"]
    assert browser.state["installs"] == [] and window.plugins.installed() == []

    browser.state["confirm"] = True
    browser._found_rows["someone-alpha"].button.click()
    assert browser._found_rows["someone-alpha"].button.text() == "Installing…"
    assert pump(app, lambda: window.plugins.is_installed("someone-alpha"))
    assert browser.state["installs"] == [("someone/alpha", "main")]

    # It moves from "found" to the installed list and no longer offers Install.
    assert pump(app, lambda: "someone-alpha" in browser._rows)
    assert "someone-alpha" not in browser._found_rows
    assert browser._rows["someone-alpha"].button.text() == "Remove"
    assert window.plugins.installed()[0].kinds == ("postprocessor",)


def test_failed_found_install_shows_reason(app, window, browser, monkeypatch):
    browser.state["repos"] = [repo("alpha")]
    browser.browse_found_button.click()
    assert pump(app, lambda: "someone-alpha" in browser._found_rows)

    def boom(full_name, ref=""):
        from universal_downloader.core import PluginError

        raise PluginError("Could not download the plugin: HTTP Error 404")

    monkeypatch.setattr(window.plugins, "install_github", boom)
    browser._found_rows["someone-alpha"].button.click()
    assert pump(app, lambda: browser._found_rows["someone-alpha"].error_label.isVisible())
    assert "404" in browser._found_rows["someone-alpha"].error_label.text()
    assert browser._found_rows["someone-alpha"].button.isEnabled()


def test_already_installed_and_catalog_plugins_are_not_offered_again(app, window, browser, tmp_path):
    archive = tmp_path / "alpha.zip"
    archive.write_bytes(pp_zip("Alpha"))
    window.plugins.install_archive(str(archive))
    browser.reload()
    browser.state["repos"] = [repo("alpha"), repo("beta")]
    browser.browse_found_button.click()
    assert pump(app, lambda: "someone-beta" in browser._found_rows)
    assert list(browser._found_rows) == ["someone-beta"]


def test_repos_known_by_source_are_not_offered_again(app, window, browser):
    from universal_downloader.core import CATALOG

    catalog_repo = CATALOG[0].homepage.removeprefix("https://github.com/")
    browser.state["repos"] = [repo(catalog_repo.split("/")[1], owner=catalog_repo.split("/")[0]), repo("fresh")]
    browser._catalog = tuple(CATALOG)
    browser.browse_found_button.click()
    assert pump(app, lambda: "someone-fresh" in browser._found_rows)
    assert list(browser._found_rows) == ["someone-fresh"]


def test_duplicate_repo_names_get_separate_rows(app, browser):
    browser.state["repos"] = [repo("yt-dlp-plugins", owner="one"), repo("yt-dlp-plugins", owner="two")]
    browser.browse_found_button.click()
    assert pump(app, lambda: len(browser._found_rows) == 2)
    assert browser.found_layout.count() == 2


# -- switching plugin steps on and off -------------------------------------------------


def install_ui_marker(app, dialog):
    dialog.row("ui-marker").button.click()
    assert pump(app, lambda: "ui-marker" in dialog._step_settings and dialog.row("ui-marker").installed)
    return dialog._step_settings["ui-marker"]


def test_recommended_steps_start_on_with_their_options(app, window, dialog):
    settings = install_ui_marker(app, dialog)
    assert settings._checks["UiMarker"].isChecked()
    assert settings._options["UiMarker"].text() == "text=hello"
    assert settings._whens["UiMarker"].currentData() == "post_process"
    assert window.plugins.postprocessors() == [{"key": "UiMarker", "when": "post_process", "text": "hello"}]


def test_switching_a_step_off_and_on(app, window, dialog):
    settings = install_ui_marker(app, dialog)
    settings._checks["UiMarker"].setChecked(False)
    assert window.plugins.postprocessors() == []
    settings._checks["UiMarker"].setChecked(True)
    assert len(window.plugins.postprocessors()) == 1


def test_changing_when_a_step_runs_and_its_options(app, window, dialog):
    settings = install_ui_marker(app, dialog)
    combo = settings._whens["UiMarker"]
    combo.setCurrentIndex(combo.findData("after_move"))
    combo.activated.emit(combo.currentIndex())
    field = settings._options["UiMarker"]
    field.setText("text=changed; extra = 1")
    field.editingFinished.emit()
    assert window.plugins.postprocessors() == [
        {"key": "UiMarker", "when": "after_move", "text": "changed", "extra": "1"}
    ]
    assert settings._errors["UiMarker"].isHidden()


def test_unreadable_options_show_a_message_and_change_nothing(app, window, dialog):
    settings = install_ui_marker(app, dialog)
    field = settings._options["UiMarker"]
    field.setText("this is not an option")
    field.editingFinished.emit()
    assert not settings._errors["UiMarker"].isHidden()
    assert "name=value" in settings._errors["UiMarker"].text()
    assert window.plugins.postprocessors()[0]["text"] == "hello"

    field.setText("text=fixed")
    field.editingFinished.emit()
    assert settings._errors["UiMarker"].isHidden()
    assert window.plugins.postprocessors()[0]["text"] == "fixed"


def test_settings_are_restored_when_the_dialog_reopens(app, window, dialog):
    settings = install_ui_marker(app, dialog)
    settings._checks["UiMarker"].setChecked(False)
    settings._options["UiMarker"].setText("text=later")
    settings._options["UiMarker"].editingFinished.emit()

    dialog.reload()
    again = dialog._step_settings["ui-marker"]
    assert not again._checks["UiMarker"].isChecked()
    assert again._options["UiMarker"].text() == "text=later"


def test_a_custom_plugin_step_starts_off_and_is_offered(app, window, dialog, tmp_path):
    archive = tmp_path / "Custom-Step.zip"
    archive.write_bytes(pp_zip("UiCustomStep"))
    dialog.source_edit.setText(str(archive))
    dialog.custom_button.click()
    assert pump(app, lambda: "custom-step" in dialog._step_settings)
    settings = dialog._step_settings["custom-step"]
    assert not settings._checks["UiCustomStep"].isChecked()
    assert window.plugins.postprocessors() == []
    settings._checks["UiCustomStep"].setChecked(True)
    assert window.plugins.postprocessors() == [{"key": "UiCustomStep", "when": "post_process"}]


def test_a_switched_on_step_takes_part_in_downloads_from_the_window(app, window, dialog, server, tmp_path):
    settings = install_ui_marker(app, dialog)
    settings._options["UiMarker"].setText("text=from the dialog")
    settings._options["UiMarker"].editingFinished.emit()

    window.url_edit.setText(f"{server}/clip.mp4")
    item = window.enqueue()
    assert pump(app, lambda: item.result is not None)
    assert item.state is JobState.DONE, item.result.error
    marker = next((tmp_path / "out").glob("*.UiMarker"))
    assert marker.read_text() == "from the dialog"
