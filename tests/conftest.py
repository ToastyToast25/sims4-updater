"""Shared test fixtures for the sims4_updater test suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def sample_game_dir(tmp_path: Path) -> Path:
    """Create a minimal Sims 4 game directory structure."""
    game_dir = tmp_path / "The Sims 4"

    # Base game markers
    (game_dir / "Game" / "Bin").mkdir(parents=True)
    (game_dir / "Game" / "Bin" / "TS4_x64.exe").write_bytes(b"fake exe")
    (game_dir / "Game" / "Bin" / "Default.ini").write_text("fake ini", encoding="utf-8")
    (game_dir / "Data" / "Client").mkdir(parents=True)
    (game_dir / "Data" / "Client" / "ClientFullBuild0.package").write_bytes(b"pkg")
    (game_dir / "Data" / "Client" / "ClientDeltaBuild0.package").write_bytes(b"pkg")

    return game_dir


@pytest.fixture()
def sample_dlc_dir(sample_game_dir: Path) -> Path:
    """Add a few DLC folders to the sample game dir."""
    for dlc_id in ("EP01", "EP02", "GP01", "SP01"):
        dlc_dir = sample_game_dir / dlc_id
        dlc_dir.mkdir()
        (dlc_dir / "SimulationFullBuild0.package").write_bytes(b"dlc pkg data")

    # Add an incomplete DLC (no package file)
    (sample_game_dir / "EP03").mkdir()

    return sample_game_dir


@pytest.fixture()
def version_db_file(tmp_path: Path) -> Path:
    """Create a minimal version_hashes.json for testing."""
    db = {
        "sentinel_files": [
            "Game/Bin/TS4_x64.exe",
            "Game/Bin/Default.ini",
        ],
        "versions": {
            "1.100.0.1000": {
                "Game/Bin/TS4_x64.exe": "aaa111",
                "Game/Bin/Default.ini": "bbb222",
            },
            "1.101.0.1000": {
                "Game/Bin/TS4_x64.exe": "ccc333",
                "Game/Bin/Default.ini": "ddd444",
            },
        },
    }
    path = tmp_path / "version_hashes.json"
    path.write_text(json.dumps(db), encoding="utf-8")
    return path


@pytest.fixture()
def dlc_catalog_file(tmp_path: Path) -> Path:
    """Create a minimal dlc_catalog.json for testing."""
    catalog = {
        "schema_version": 1,
        "dlcs": [
            {
                "id": "EP01",
                "code": "SIMS4.OFF.SOLP.0x0000000000011AC5",
                "code2": "",
                "type": "expansion",
                "names": {"en_us": "Get to Work", "de_de": "An die Arbeit"},
                "description": "First expansion pack",
                "steam_app_id": 1222671,
            },
            {
                "id": "GP01",
                "code": "SIMS4.OFF.SOLP.GP01CODE",
                "code2": "SIMS4.GP01.ALT",
                "type": "game_pack",
                "names": {"en_us": "Outdoor Retreat"},
                "description": "First game pack",
                "steam_app_id": None,
            },
            {
                "id": "SP01",
                "code": "SIMS4.OFF.SOLP.SP01CODE",
                "code2": "",
                "type": "stuff_pack",
                "names": {"en_us": "Luxury Party Stuff"},
                "description": "",
            },
        ],
    }
    path = tmp_path / "dlc_catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")
    return path
