import sys
from pathlib import Path

import pytest

from helix_stadium_mcp import config


def _resources(root: Path, *, catalog: bool) -> Path:
    res = root / "Helix Stadium.app" / "Contents" / "Resources"
    res.mkdir(parents=True)
    (res / "modeldefs").mkdir()
    if catalog:
        (res / config.CATALOG).write_text("{}")
    return res


def test_macos_candidates_are_the_app_bundle_resources(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert config.candidate_res_dirs() == [
        Path("/Applications/Line6/Helix Stadium.app/Contents/Resources"),
        Path("/Applications/Helix Stadium.app/Contents/Resources"),
    ]


def test_macos_auto_detect_finds_the_installer_layout(tmp_path, monkeypatch):
    installed = _resources(tmp_path / "Line6", catalog=True)
    monkeypatch.delenv("HELIX_STADIUM_RES", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(config, "_MACOS", [str(installed), str(tmp_path / "missing")])
    assert config.resolve_res_dir() == installed
    assert config.detect() == {"found": True, "res_dir": str(installed), "has_catalog": True}


def test_auto_detect_passes_over_a_folder_without_the_catalog(tmp_path, monkeypatch):
    empty = _resources(tmp_path / "other", catalog=False)
    installed = _resources(tmp_path / "Line6", catalog=True)
    monkeypatch.delenv("HELIX_STADIUM_RES", raising=False)
    monkeypatch.setattr(config, "candidate_res_dirs", lambda: [empty, installed])
    assert config.resolve_res_dir() == installed


def test_auto_detect_without_a_catalog_lists_every_probed_folder(tmp_path, monkeypatch):
    empty = _resources(tmp_path, catalog=False)
    monkeypatch.delenv("HELIX_STADIUM_RES", raising=False)
    monkeypatch.setattr(config, "candidate_res_dirs", lambda: [empty])
    with pytest.raises(FileNotFoundError) as err:
        config.resolve_res_dir()
    assert str(empty) in str(err.value)
    assert config.CATALOG in str(err.value)
    assert config.detect()["found"] is False
