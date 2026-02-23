"""Tests for DLCCatalog — DLC loading, lookup, and filtering."""

from __future__ import annotations

from sims4_updater.dlc.catalog import DLCCatalog, DLCInfo, DLCStatus, _parse_dlc_entry


class TestDLCInfo:
    def test_name_en(self):
        dlc = DLCInfo(
            id="EP01",
            code="CODE",
            code2="",
            pack_type="expansion",
            names={"en_us": "Get to Work"},
        )
        assert dlc.name_en == "Get to Work"

    def test_name_en_fallback(self):
        dlc = DLCInfo(id="EP01", code="", code2="", pack_type="expansion", names={})
        assert dlc.name_en == "EP01"

    def test_get_name_locale(self):
        dlc = DLCInfo(
            id="EP01",
            code="",
            code2="",
            pack_type="expansion",
            names={"en_us": "Get to Work", "de_de": "An die Arbeit"},
        )
        assert dlc.get_name("de_DE") == "An die Arbeit"

    def test_get_name_unknown_locale_fallback(self):
        dlc = DLCInfo(
            id="EP01",
            code="",
            code2="",
            pack_type="expansion",
            names={"en_us": "Get to Work"},
        )
        assert dlc.get_name("zh_CN") == "Get to Work"

    def test_all_codes(self):
        dlc = DLCInfo(id="EP01", code="A", code2="B", pack_type="expansion", names={})
        assert dlc.all_codes == ["A", "B"]

    def test_all_codes_no_code2(self):
        dlc = DLCInfo(id="EP01", code="A", code2="", pack_type="expansion", names={})
        assert dlc.all_codes == ["A"]

    def test_all_codes_empty(self):
        dlc = DLCInfo(id="EP01", code="", code2="", pack_type="expansion", names={})
        assert dlc.all_codes == []


class TestDLCStatus:
    def test_status_label_not_installed(self):
        dlc = DLCInfo(id="X", code="", code2="", pack_type="expansion", names={})
        s = DLCStatus(dlc=dlc)
        assert s.status_label == "Not Installed"

    def test_status_label_ready(self):
        dlc = DLCInfo(id="X", code="", code2="", pack_type="expansion", names={})
        s = DLCStatus(dlc=dlc, installed=True, complete=True, registered=True, enabled=True)
        assert s.status_label == "Ready"

    def test_status_label_disabled(self):
        dlc = DLCInfo(id="X", code="", code2="", pack_type="expansion", names={})
        s = DLCStatus(dlc=dlc, installed=True, complete=True, registered=True, enabled=False)
        assert s.status_label == "Disabled"

    def test_status_label_owned(self):
        dlc = DLCInfo(id="X", code="", code2="", pack_type="expansion", names={})
        s = DLCStatus(dlc=dlc, installed=True, complete=True, owned=True)
        assert s.status_label == "Owned"

    def test_status_label_incomplete(self):
        dlc = DLCInfo(id="X", code="", code2="", pack_type="expansion", names={})
        s = DLCStatus(dlc=dlc, installed=True, complete=False)
        assert s.status_label == "Incomplete Install"

    def test_status_label_not_downloaded(self):
        dlc = DLCInfo(id="X", code="", code2="", pack_type="expansion", names={})
        s = DLCStatus(dlc=dlc, installed=False, registered=True)
        assert s.status_label == "Not Downloaded"


class TestParseDlcEntry:
    def test_minimal_entry(self):
        entry = {"id": "EP01"}
        dlc = _parse_dlc_entry(entry)
        assert dlc.id == "EP01"
        assert dlc.code == ""
        assert dlc.pack_type == "other"
        assert dlc.names == {}

    def test_full_entry(self):
        entry = {
            "id": "EP01",
            "code": "CODE1",
            "code2": "CODE2",
            "type": "expansion",
            "names": {"en_us": "Test Pack"},
            "description": "A test",
            "steam_app_id": 12345,
        }
        dlc = _parse_dlc_entry(entry)
        assert dlc.id == "EP01"
        assert dlc.code == "CODE1"
        assert dlc.code2 == "CODE2"
        assert dlc.pack_type == "expansion"
        assert dlc.steam_app_id == 12345


class TestDLCCatalog:
    def test_loads_catalog(self, dlc_catalog_file):
        cat = DLCCatalog(catalog_path=dlc_catalog_file)
        assert len(cat.dlcs) == 3

    def test_get_by_id(self, dlc_catalog_file):
        cat = DLCCatalog(catalog_path=dlc_catalog_file)
        dlc = cat.get_by_id("EP01")
        assert dlc is not None
        assert dlc.name_en == "Get to Work"

    def test_get_by_id_missing(self, dlc_catalog_file):
        cat = DLCCatalog(catalog_path=dlc_catalog_file)
        assert cat.get_by_id("NONEXISTENT") is None

    def test_get_by_code(self, dlc_catalog_file):
        cat = DLCCatalog(catalog_path=dlc_catalog_file)
        dlc = cat.get_by_code("SIMS4.OFF.SOLP.0x0000000000011AC5")
        assert dlc is not None
        assert dlc.id == "EP01"

    def test_get_by_code2(self, dlc_catalog_file):
        cat = DLCCatalog(catalog_path=dlc_catalog_file)
        dlc = cat.get_by_code("SIMS4.GP01.ALT")
        assert dlc is not None
        assert dlc.id == "GP01"

    def test_all_dlcs(self, dlc_catalog_file):
        cat = DLCCatalog(catalog_path=dlc_catalog_file)
        assert len(cat.all_dlcs()) == 3

    def test_by_type(self, dlc_catalog_file):
        cat = DLCCatalog(catalog_path=dlc_catalog_file)
        expansions = cat.by_type("expansion")
        assert len(expansions) == 1
        assert expansions[0].id == "EP01"

    def test_by_type_empty(self, dlc_catalog_file):
        cat = DLCCatalog(catalog_path=dlc_catalog_file)
        assert cat.by_type("kit") == []

    def test_get_installed(self, dlc_catalog_file, sample_dlc_dir):
        cat = DLCCatalog(catalog_path=dlc_catalog_file)
        installed = cat.get_installed(sample_dlc_dir)
        ids = [d.id for d in installed]
        assert "EP01" in ids
        assert "GP01" in ids
        assert "SP01" in ids

    def test_get_missing(self, dlc_catalog_file, sample_game_dir):
        """All DLCs are missing from a bare game dir."""
        cat = DLCCatalog(catalog_path=dlc_catalog_file)
        missing = cat.get_missing(sample_game_dir)
        assert len(missing) == 3  # all DLCs missing
