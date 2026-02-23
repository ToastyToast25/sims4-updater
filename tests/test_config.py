"""Tests for Settings dataclass load/save."""

from __future__ import annotations

import json

from sims4_updater.config import Settings


class TestSettingsDefaults:
    def test_default_values(self):
        s = Settings()
        assert s.game_path == ""
        assert s.language == "English"
        assert s.check_updates_on_start is True
        assert s.manifest_url == "https://cdn.hyperabyss.com/manifest.json"
        assert s.contribute_url == "https://api.hyperabyss.com/contribute"
        assert s.theme == "dark"
        assert s.download_concurrency == 3
        assert s.download_speed_limit == 0
        assert s.backup_enabled is False
        assert s.backup_max_count == 3

    def test_post_init_fills_empty_urls(self):
        s = Settings(manifest_url="", contribute_url="")
        assert s.manifest_url == "https://cdn.hyperabyss.com/manifest.json"
        assert s.contribute_url == "https://api.hyperabyss.com/contribute"

    def test_post_init_preserves_custom_urls(self):
        s = Settings(
            manifest_url="https://custom.example.com/m.json",
            contribute_url="https://custom.example.com/c",
        )
        assert s.manifest_url == "https://custom.example.com/m.json"
        assert s.contribute_url == "https://custom.example.com/c"


class TestSettingsLoadSave:
    def test_save_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "settings.json"
        original = Settings(
            game_path="C:\\Games\\Sims4",
            language="Deutsch",
            theme="light",
            download_concurrency=5,
        )
        original.save(path)
        loaded = Settings.load(path)
        assert loaded.game_path == "C:\\Games\\Sims4"
        assert loaded.language == "Deutsch"
        assert loaded.theme == "light"
        assert loaded.download_concurrency == 5

    def test_load_missing_file_returns_defaults(self, tmp_path):
        s = Settings.load(tmp_path / "nonexistent.json")
        assert s.game_path == ""
        assert s.theme == "dark"

    def test_load_invalid_json_returns_defaults(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json at all", encoding="utf-8")
        s = Settings.load(path)
        assert s.theme == "dark"

    def test_load_ignores_unknown_keys(self, tmp_path):
        path = tmp_path / "settings.json"
        data = {"game_path": "C:\\Test", "unknown_key": "value", "another_unknown": 42}
        path.write_text(json.dumps(data), encoding="utf-8")
        s = Settings.load(path)
        assert s.game_path == "C:\\Test"
        assert not hasattr(s, "unknown_key")

    def test_load_subset_of_fields(self, tmp_path):
        path = tmp_path / "settings.json"
        data = {"theme": "light"}
        path.write_text(json.dumps(data), encoding="utf-8")
        s = Settings.load(path)
        assert s.theme == "light"
        assert s.game_path == ""  # default
        assert s.manifest_url == "https://cdn.hyperabyss.com/manifest.json"

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "subdir" / "nested" / "settings.json"
        Settings().save(path)
        assert path.is_file()
        loaded = Settings.load(path)
        assert loaded.theme == "dark"

    def test_save_produces_valid_json(self, tmp_path):
        path = tmp_path / "settings.json"
        Settings(game_path="test").save(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert data["game_path"] == "test"
