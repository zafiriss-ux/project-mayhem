from pathlib import Path

from launcher import paths


def test_validate_paths_requires_launcher_module_in_dev_mode(tmp_path, monkeypatch):
    bundle_dir = Path(tmp_path)
    (bundle_dir / "titan").mkdir()
    monkeypatch.setattr(paths, "get_bundle_dir", lambda: bundle_dir)
    monkeypatch.setattr(paths, "is_frozen", lambda: False)

    assert paths.validate_paths() is False


def test_validate_paths_allows_missing_launcher_in_frozen_mode(tmp_path, monkeypatch):
    bundle_dir = Path(tmp_path)
    (bundle_dir / "titan").mkdir()
    monkeypatch.setattr(paths, "get_bundle_dir", lambda: bundle_dir)
    monkeypatch.setattr(paths, "is_frozen", lambda: True)

    assert paths.validate_paths() is True
