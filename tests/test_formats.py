"""Tests for DLC crack config format adapters (pure string logic)."""

from __future__ import annotations

from sims4_updater.dlc.formats import (
    AnadiusCodexAdapter,
    AnadiusSimpleAdapter,
    CodexAdapter,
    RldOriginAdapter,
    RuneAdapter,
)

# -- RldOriginAdapter ----------------------------------------------------------


class TestRldOriginAdapter:
    adapter = RldOriginAdapter()

    SAMPLE = "[DLC]\nIID1=EP01\n;IID2=EP02\nIID3=GP01\n;IID4=SP01\n"

    def test_read_enabled(self):
        result = self.adapter.read_enabled_dlcs(self.SAMPLE, ["EP01", "EP02", "GP01", "SP01"])
        assert result["EP01"] is True
        assert result["EP02"] is False
        assert result["GP01"] is True
        assert result["SP01"] is False

    def test_read_unknown_code(self):
        result = self.adapter.read_enabled_dlcs(self.SAMPLE, ["UNKNOWN"])
        assert result == {}

    def test_enable(self):
        result = self.adapter.set_dlc_state(self.SAMPLE, "EP02", enabled=True)
        assert "\nIID2=EP02" in result
        assert "\n;IID2=EP02" not in result

    def test_disable(self):
        result = self.adapter.set_dlc_state(self.SAMPLE, "EP01", enabled=False)
        assert "\n;IID1=EP01" in result

    def test_format_name(self):
        assert self.adapter.get_format_name() == "RldOrigin"


# -- CodexAdapter --------------------------------------------------------------


class TestCodexAdapter:
    adapter = CodexAdapter()

    SAMPLE = '"EP01"\n{\n  "Group"  "THESIMS4PC"\n}\n"EP02"\n{\n  "Group"  "_"\n}\n'

    def test_read_enabled(self):
        result = self.adapter.read_enabled_dlcs(self.SAMPLE, ["EP01", "EP02"])
        assert result["EP01"] is True
        assert result["EP02"] is False

    def test_enable(self):
        result = self.adapter.set_dlc_state(self.SAMPLE, "EP02", enabled=True)
        check = self.adapter.read_enabled_dlcs(result, ["EP02"])
        assert check["EP02"] is True

    def test_disable(self):
        result = self.adapter.set_dlc_state(self.SAMPLE, "EP01", enabled=False)
        check = self.adapter.read_enabled_dlcs(result, ["EP01"])
        assert check["EP01"] is False

    def test_format_name(self):
        assert self.adapter.get_format_name() == "CODEX"


# -- RuneAdapter ---------------------------------------------------------------


class TestRuneAdapter:
    adapter = RuneAdapter()

    SAMPLE = "[EP01]\n[EP02_]\n[GP01]\n[SP01_]\n"

    def test_read_enabled(self):
        result = self.adapter.read_enabled_dlcs(self.SAMPLE, ["EP01", "EP02", "GP01", "SP01"])
        assert result["EP01"] is True
        assert result["EP02"] is False
        assert result["GP01"] is True
        assert result["SP01"] is False

    def test_enable(self):
        result = self.adapter.set_dlc_state(self.SAMPLE, "EP02", enabled=True)
        assert "[EP02]" in result
        assert "[EP02_]" not in result

    def test_disable(self):
        result = self.adapter.set_dlc_state(self.SAMPLE, "EP01", enabled=False)
        assert "[EP01_]" in result

    def test_format_name(self):
        assert self.adapter.get_format_name() == "Rune"


# -- AnadiusSimpleAdapter ------------------------------------------------------


class TestAnadiusSimpleAdapter:
    adapter = AnadiusSimpleAdapter()

    SAMPLE = '{\n  "EP01"\n  //"EP02"\n  "GP01"\n  //"SP01"\n}\n'

    def test_read_enabled(self):
        result = self.adapter.read_enabled_dlcs(self.SAMPLE, ["EP01", "EP02", "GP01", "SP01"])
        assert result["EP01"] is True
        assert result["EP02"] is False
        assert result["GP01"] is True
        assert result["SP01"] is False

    def test_enable(self):
        result = self.adapter.set_dlc_state(self.SAMPLE, "EP02", enabled=True)
        check = self.adapter.read_enabled_dlcs(result, ["EP02"])
        assert check["EP02"] is True

    def test_disable(self):
        result = self.adapter.set_dlc_state(self.SAMPLE, "EP01", enabled=False)
        check = self.adapter.read_enabled_dlcs(result, ["EP01"])
        assert check["EP01"] is False

    def test_format_name(self):
        assert self.adapter.get_format_name() == "anadius (simple)"


# -- AnadiusCodexAdapter -------------------------------------------------------


class TestAnadiusCodexAdapter:
    adapter = AnadiusCodexAdapter()

    # Same format as Codex but from anadius.cfg with Config2
    SAMPLE = (
        '"Config2"\n{\n}\n"EP01"\n{\n  "Group"  "THESIMS4PC"\n}\n"EP02"\n{\n  "Group"  "_"\n}\n'
    )

    def test_read_enabled(self):
        result = self.adapter.read_enabled_dlcs(self.SAMPLE, ["EP01", "EP02"])
        assert result["EP01"] is True
        assert result["EP02"] is False

    def test_enable(self):
        result = self.adapter.set_dlc_state(self.SAMPLE, "EP02", enabled=True)
        check = self.adapter.read_enabled_dlcs(result, ["EP02"])
        assert check["EP02"] is True

    def test_format_name(self):
        assert self.adapter.get_format_name() == "anadius (codex-like)"

    def test_encoding(self):
        assert self.adapter.get_encoding() == "utf-8"
