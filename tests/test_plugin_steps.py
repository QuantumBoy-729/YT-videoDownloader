"""Switching a plugin's processing steps on and off, and passing them options."""

from __future__ import annotations

import json
import urllib.request

import pytest

from universal_downloader.core import (
    DownloadJob,
    DownloadRequest,
    JobState,
    PluginError,
    PluginManager,
)
from universal_downloader.core.plugins import (
    WHEN_LABELS,
    find_postprocessor_keys,
    format_options,
    parse_options,
)

from .conftest import NO_PROXY
from .test_plugins import entry, make_zip, pp_zip


@pytest.fixture
def manager(tmp_path) -> PluginManager:
    return PluginManager(tmp_path / "plugins", opener=urllib.request.build_opener(urllib.request.ProxyHandler({})))


def install(manager, tmp_path, name):
    """Install the stand-in postprocessor plugin ``name`` and return it."""
    archive = tmp_path / f"{name}.zip"
    archive.write_bytes(pp_zip(name))
    return manager.install_archive(str(archive))


def download(manager, server, out, **request):
    job = DownloadJob(
        DownloadRequest(url=f"{server}/clip.mp4", output_dir=out, **request),
        extra_opts=NO_PROXY,
        plugin_postprocessors=manager.postprocessors(),
    )
    result = job.run()
    assert result.state is JobState.DONE, result.error
    # "clip [clip].mp4" -> "mp4", and the step's marker "clip [clip].mp4.Name" -> "mp4.Name"
    return sorted(p.name.split(".", 1)[1] for p in out.iterdir())


# -- finding the steps -----------------------------------------------------------


def test_steps_are_found_by_class_name_without_running_anything(tmp_path):
    package = tmp_path / "yt_dlp_plugins" / "postprocessor"
    (package / "nested").mkdir(parents=True)
    (package / "a.py").write_text(
        "raise SystemExit('must never run')\n"
        "class AlphaPP: pass\n"
        "class _HiddenPP: pass\n"
        "class PP: pass\n"
        "class Helper: pass\n"
        "class AlphaPP: pass\n"  # duplicate
    )
    (package / "nested" / "__init__.py").write_text("class BetaPP(object): pass\n")
    (package / "broken.py").write_text("def (:\n")
    (tmp_path / "yt_dlp_plugins" / "extractor").mkdir()
    (tmp_path / "yt_dlp_plugins" / "extractor" / "site.py").write_text("class SiteIE: pass\nclass NotAStepPP: pass\n")
    assert find_postprocessor_keys(tmp_path) == ["Alpha", "Beta"]
    assert find_postprocessor_keys(tmp_path / "missing") == []


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", {}),
        ("  ;  ; ", {}),
        ("a=1", {"a": "1"}),
        ("a=1; b = two words ;c=", {"a": "1", "b": "two words", "c": ""}),
        ("url=http://x/?q=1", {"url": "http://x/?q=1"}),
    ],
)
def test_parse_options(text, expected):
    assert parse_options(text) == expected
    assert parse_options(format_options(expected)) == expected


@pytest.mark.parametrize("text", ["novalue", "=1", "a b=1", "1a=2", "key=x", "when=post_process", "ok=1; bad"])
def test_bad_options_are_rejected_with_the_offending_part(text):
    with pytest.raises(PluginError, match="name=value"):
        parse_options(text)


# -- settings --------------------------------------------------------------------


def test_new_plugin_steps_start_off_and_can_be_switched_on(manager, tmp_path):
    plugin = install(manager, tmp_path, "StepOne")
    assert plugin.pp_keys == ("StepOne",)
    assert plugin.pp_config["StepOne"] == {"enabled": False, "when": "post_process", "options": {}}
    assert manager.postprocessors() == []

    manager.configure_postprocessor(plugin.id, "StepOne", enabled=True)
    assert manager.postprocessors() == [{"key": "StepOne", "when": "post_process"}]

    manager.configure_postprocessor(plugin.id, "StepOne", when="after_move", options={"text": "hi", "n": "2"})
    assert manager.postprocessors() == [{"key": "StepOne", "when": "after_move", "text": "hi", "n": "2"}]

    manager.configure_postprocessor(plugin.id, "StepOne", enabled=False)
    assert manager.postprocessors() == []
    # Switching off keeps the settings for next time.
    assert manager.installed()[0].pp_config["StepOne"]["options"] == {"text": "hi", "n": "2"}


def test_settings_survive_a_restart(manager, tmp_path):
    plugin = install(manager, tmp_path, "StepTwo")
    manager.configure_postprocessor(plugin.id, "StepTwo", enabled=True, options={"text": "kept"})
    again = PluginManager(manager.root)
    assert again.postprocessors() == [{"key": "StepTwo", "when": "post_process", "text": "kept"}]


def test_catalog_steps_start_on_and_can_be_switched_off(manager, server, media_dir):
    (media_dir / "cat.zip").write_bytes(pp_zip("StepCatalog"))
    plugin = manager.install(entry("step-catalog", f"{server}/cat.zip", "StepCatalog"))
    assert plugin.pp_config["StepCatalog"] == {"enabled": True, "when": "post_process", "options": {"text": "hello"}}
    assert manager.postprocessors() == [{"key": "StepCatalog", "when": "post_process", "text": "hello"}]
    manager.configure_postprocessor("step-catalog", "StepCatalog", enabled=False)
    assert manager.postprocessors() == []
    manager.configure_postprocessor("step-catalog", "StepCatalog", enabled=True)
    assert manager.postprocessors()[0]["text"] == "hello"


def test_plugin_files_from_older_versions_are_still_read(manager, tmp_path):
    plugin = install(manager, tmp_path, "StepLegacy")
    meta_path = plugin.path / "plugin.json"
    meta = json.loads(meta_path.read_text())
    for newer in ("pp_keys", "pp_config"):
        del meta[newer]
    meta["postprocessors"] = [{"key": "StepLegacy", "when": "after_move", "text": "old"}]
    meta_path.write_text(json.dumps(meta))
    assert manager.postprocessors() == [{"key": "StepLegacy", "when": "after_move", "text": "old"}]
    assert manager.installed()[0].pp_keys == ("StepLegacy",)


def test_damaged_settings_fall_back_to_defaults(manager, tmp_path):
    plugin = install(manager, tmp_path, "StepDamaged")
    meta_path = plugin.path / "plugin.json"
    meta = json.loads(meta_path.read_text())
    meta["pp_config"] = {"StepDamaged": {"enabled": True, "when": "nonsense", "options": "oops"}}
    meta_path.write_text(json.dumps(meta))
    assert manager.postprocessors() == [{"key": "StepDamaged", "when": "post_process"}]


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"key": "Nope"}, "not installed"),
        ({"when": "whenever"}, "valid time"),
        ({"options": {"bad name": "x"}}, "not a valid option"),
        ({"options": {"when": "x"}}, "not a valid option"),
    ],
)
def test_invalid_changes_are_rejected_and_change_nothing(manager, tmp_path, kwargs, message):
    plugin = install(manager, tmp_path, "StepStrict")
    before = (plugin.path / "plugin.json").read_text()
    key = kwargs.pop("key", "StepStrict")
    with pytest.raises(PluginError, match=message):
        manager.configure_postprocessor(plugin.id, key, **kwargs)
    assert (plugin.path / "plugin.json").read_text() == before
    with pytest.raises(PluginError, match="not installed"):
        manager.configure_postprocessor("no-such-plugin", "StepStrict", enabled=True)


def test_every_yt_dlp_stage_has_a_plain_label():
    from yt_dlp.utils import POSTPROCESS_WHEN

    assert set(WHEN_LABELS) == set(POSTPROCESS_WHEN)
    assert all(label and "_" not in label for label in WHEN_LABELS.values())


def test_plugins_without_steps_have_none(manager, tmp_path):
    archive = tmp_path / "site.zip"
    archive.write_bytes(make_zip({"yt_dlp_plugins/extractor/stepsite.py": "x = 1"}))
    plugin = manager.install_archive(str(archive))
    assert plugin.pp_keys == () and plugin.kinds == ("extractor",)


# -- effect on downloads -----------------------------------------------------------


def test_a_switched_on_step_runs_with_its_options(manager, server, tmp_path):
    plugin = install(manager, tmp_path, "StepRuns")
    assert download(manager, server, tmp_path / "off") == ["mp4"], "off by default"

    manager.configure_postprocessor(plugin.id, "StepRuns", enabled=True, options={"text": "custom words"})
    assert download(manager, server, tmp_path / "on") == ["mp4", "mp4.StepRuns"]
    marker = next((tmp_path / "on").glob("*.StepRuns"))
    assert marker.read_text() == "custom words"

    manager.configure_postprocessor(plugin.id, "StepRuns", when="after_move")
    assert download(manager, server, tmp_path / "moved") == ["mp4", "mp4.StepRuns"]

    manager.configure_postprocessor(plugin.id, "StepRuns", enabled=False)
    assert download(manager, server, tmp_path / "off-again") == ["mp4"]


def test_options_the_step_does_not_accept_give_a_clear_failure(manager, server, tmp_path):
    plugin = install(manager, tmp_path, "StepPicky")
    manager.configure_postprocessor(plugin.id, "StepPicky", enabled=True, options={"bogus": "1"})
    job = DownloadJob(
        DownloadRequest(url=f"{server}/clip.mp4", output_dir=tmp_path / "out"),
        extra_opts=NO_PROXY,
        plugin_postprocessors=manager.postprocessors(),
    )
    result = job.run()
    assert result.state is JobState.FAILED
    assert "processing step could not be set up" in result.error
    assert "bogus" in result.error and "switch it off" in result.error
    assert "out of date" not in result.error, "must not blame the site"
    assert list((tmp_path / "out").iterdir()) == []


def test_a_step_that_cannot_be_loaded_gives_a_clear_failure(server, tmp_path):
    job = DownloadJob(
        DownloadRequest(url=f"{server}/clip.mp4", output_dir=tmp_path),
        extra_opts=NO_PROXY,
        plugin_postprocessors=[{"key": "NeverInstalled", "when": "post_process"}],
    )
    result = job.run()
    assert result.state is JobState.FAILED
    assert 'The plugin step "NeverInstalled" could not be loaded' in result.error
    assert "Plugins" in result.error
