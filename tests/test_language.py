"""Tests for language changer module."""

from __future__ import annotations

from sims4_updater.language.changer import (
    LANGUAGES,
    LOCALE_TO_STEAM,
    LOCALE_TO_STRINGS,
    LanguageChangeResult,
    get_strings_filename,
)


class TestLanguageMappings:
    def test_all_dicts_have_same_keys(self):
        assert set(LANGUAGES.keys()) == set(LOCALE_TO_STRINGS.keys())
        assert set(LANGUAGES.keys()) == set(LOCALE_TO_STEAM.keys())

    def test_18_languages(self):
        assert len(LANGUAGES) == 18

    def test_english_present(self):
        assert "en_US" in LANGUAGES
        assert LANGUAGES["en_US"] == "English"

    def test_steam_language_names(self):
        assert LOCALE_TO_STEAM["en_US"] == "english"
        assert LOCALE_TO_STEAM["de_DE"] == "german"
        assert LOCALE_TO_STEAM["ja_JP"] == "japanese"
        assert LOCALE_TO_STEAM["ko_KR"] == "koreana"


class TestGetStringsFilename:
    def test_known_locale(self):
        assert get_strings_filename("da_DK") == "Strings_DAN_DK.package"
        assert get_strings_filename("en_US") == "Strings_ENG_US.package"
        assert get_strings_filename("de_DE") == "Strings_GER_DE.package"
        assert get_strings_filename("zh_CN") == "Strings_CHS_CN.package"

    def test_unknown_locale(self):
        assert get_strings_filename("xx_XX") is None
        assert get_strings_filename("") is None


class TestLanguageChangeResult:
    def test_success_with_anadius(self):
        r = LanguageChangeResult(
            anadius_updated=["path/anadius.cfg"], registry_ok=False, rld_updated=[]
        )
        assert r.success is True

    def test_success_with_registry(self):
        r = LanguageChangeResult(anadius_updated=[], registry_ok=True, rld_updated=[])
        assert r.success is True

    def test_success_with_steam(self):
        r = LanguageChangeResult(
            anadius_updated=[], registry_ok=False, rld_updated=[], steam_updated=True
        )
        assert r.success is True

    def test_failure_all_false(self):
        r = LanguageChangeResult(anadius_updated=[], registry_ok=False, rld_updated=[])
        assert r.success is False
