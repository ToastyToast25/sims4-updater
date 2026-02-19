"""
Crack config format parsers for DLC toggling.

Ported from dlc-toggler.au3 — supports 5 crack config formats across
Game/ and Game-cracked/ directories.
"""

import re
import os
from abc import ABC, abstractmethod
from pathlib import Path


class DLCConfigAdapter(ABC):
    """Abstract base for reading/writing DLC state in crack configs."""

    @abstractmethod
    def detect(self, game_dir: Path) -> bool:
        """Returns True if this format's config exists in game_dir."""

    @abstractmethod
    def get_config_path(self, game_dir: Path) -> Path | None:
        """Return the path to the config file, or None if not found."""

    @abstractmethod
    def read_enabled_dlcs(self, config_content: str, dlc_codes: list[str]) -> dict[str, bool]:
        """Read enabled/disabled state for each DLC code. Returns {code: enabled}."""

    @abstractmethod
    def set_dlc_state(self, config_content: str, dlc_code: str, enabled: bool) -> str:
        """Modify config content to enable/disable a DLC. Returns modified content."""

    @abstractmethod
    def get_format_name(self) -> str:
        """Human-readable format name."""

    @abstractmethod
    def get_encoding(self) -> str:
        """File encoding for reading/writing."""


class RldOriginAdapter(DLCConfigAdapter):
    """ReLoaded Origin crack — RldOrigin.ini"""

    CONFIG_PATHS = [
        "Game/Bin/RldOrigin.ini",
        "Game-cracked/Bin/RldOrigin.ini",
    ]

    def detect(self, game_dir: Path) -> bool:
        return self.get_config_path(game_dir) is not None

    def get_config_path(self, game_dir: Path) -> Path | None:
        for p in self.CONFIG_PATHS:
            path = game_dir / p.replace("/", os.sep)
            if path.is_file():
                return path
        return None

    def read_enabled_dlcs(self, config_content: str, dlc_codes: list[str]) -> dict[str, bool]:
        result = {}
        for code in dlc_codes:
            pattern = re.compile(rf"(?i)(\n)(;?)(IID\d+={re.escape(code)})")
            match = pattern.search(config_content)
            if match:
                result[code] = match.group(2) == ""  # no semicolon = enabled
        return result

    def set_dlc_state(self, config_content: str, dlc_code: str, enabled: bool) -> str:
        pattern = re.compile(rf"(?i)(\n)(;?)(IID\d+={re.escape(dlc_code)})")
        replacement = r"\1" + ("" if enabled else ";") + r"\3"
        return pattern.sub(replacement, config_content)

    def get_format_name(self) -> str:
        return "RldOrigin"

    def get_encoding(self) -> str:
        return "utf-8"


class CodexAdapter(DLCConfigAdapter):
    """CODEX crack — codex.cfg (also used for anadius.cfg v2)"""

    CONFIG_PATHS = [
        "Game/Bin/codex.cfg",
        "Game-cracked/Bin/codex.cfg",
    ]
    VALID_GROUP = "THESIMS4PC"
    INVALID_GROUP = "_"

    def detect(self, game_dir: Path) -> bool:
        return self.get_config_path(game_dir) is not None

    def get_config_path(self, game_dir: Path) -> Path | None:
        for p in self.CONFIG_PATHS:
            path = game_dir / p.replace("/", os.sep)
            if path.is_file():
                return path
        return None

    def _codex_pattern(self, code: str) -> re.Pattern:
        escaped = re.escape(code)
        # Build regex without f-string to avoid brace escaping issues
        return re.compile(
            '(?i)("' + escaped + r'"[\s\n]+\{[^\}]+"Group"\s+")([^"]+)()',
            re.DOTALL,
        )

    def read_enabled_dlcs(self, config_content: str, dlc_codes: list[str]) -> dict[str, bool]:
        result = {}
        for code in dlc_codes:
            match = self._codex_pattern(code).search(config_content)
            if match:
                result[code] = match.group(2) == self.VALID_GROUP
        return result

    def set_dlc_state(self, config_content: str, dlc_code: str, enabled: bool) -> str:
        group = self.VALID_GROUP if enabled else self.INVALID_GROUP
        return self._codex_pattern(dlc_code).sub(r"\g<1>" + group + r"\3", config_content)

    def get_format_name(self) -> str:
        return "CODEX"

    def get_encoding(self) -> str:
        return "utf-8"


class RuneAdapter(DLCConfigAdapter):
    """Rune crack — rune.ini"""

    CONFIG_PATHS = [
        "Game/Bin/rune.ini",
        "Game-cracked/Bin/rune.ini",
    ]

    def detect(self, game_dir: Path) -> bool:
        return self.get_config_path(game_dir) is not None

    def get_config_path(self, game_dir: Path) -> Path | None:
        for p in self.CONFIG_PATHS:
            path = game_dir / p.replace("/", os.sep)
            if path.is_file():
                return path
        return None

    def read_enabled_dlcs(self, config_content: str, dlc_codes: list[str]) -> dict[str, bool]:
        result = {}
        for code in dlc_codes:
            pattern = re.compile(rf"(?i)(\[{re.escape(code)})(_?)(\])")
            match = pattern.search(config_content)
            if match:
                result[code] = match.group(2) == ""  # no underscore = enabled
        return result

    def set_dlc_state(self, config_content: str, dlc_code: str, enabled: bool) -> str:
        pattern = re.compile(rf"(?i)(\[{re.escape(dlc_code)})(_?)(\])")
        replacement = r"\1" + ("" if enabled else "_") + r"\3"
        return pattern.sub(replacement, config_content)

    def get_format_name(self) -> str:
        return "Rune"

    def get_encoding(self) -> str:
        return "utf-8"


class AnadiusSimpleAdapter(DLCConfigAdapter):
    """Anadius crack v1 (simple format) — anadius.cfg without Config2"""

    CONFIG_PATHS = [
        "Game/Bin/anadius.cfg",
        "Game-cracked/Bin/anadius.cfg",
    ]

    def detect(self, game_dir: Path) -> bool:
        path = self.get_config_path(game_dir)
        if path is None:
            return False
        content = path.read_text(encoding="utf-8", errors="replace")
        return '"Config2"' not in content

    def get_config_path(self, game_dir: Path) -> Path | None:
        for p in self.CONFIG_PATHS:
            path = game_dir / p.replace("/", os.sep)
            if path.is_file():
                return path
        return None

    def read_enabled_dlcs(self, config_content: str, dlc_codes: list[str]) -> dict[str, bool]:
        result = {}
        for code in dlc_codes:
            pattern = re.compile(rf'(?i)(\s)(/*)("{re.escape(code)}")')
            match = pattern.search(config_content)
            if match:
                result[code] = match.group(2) == ""  # no // = enabled
        return result

    def set_dlc_state(self, config_content: str, dlc_code: str, enabled: bool) -> str:
        pattern = re.compile(rf'(?i)(\s)(/*)("{re.escape(dlc_code)}")')
        replacement = r"\1" + ("" if enabled else "//") + r"\3"
        return pattern.sub(replacement, config_content)

    def get_format_name(self) -> str:
        return "anadius (simple)"

    def get_encoding(self) -> str:
        return "utf-8"


class AnadiusCodexAdapter(CodexAdapter):
    """Anadius crack v2 (codex-like format) — anadius.cfg with Config2"""

    CONFIG_PATHS = [
        "Game/Bin/anadius.cfg",
        "Game-cracked/Bin/anadius.cfg",
    ]

    def detect(self, game_dir: Path) -> bool:
        path = self.get_config_path(game_dir)
        if path is None:
            return False
        content = path.read_text(encoding="utf-8", errors="replace")
        return '"Config2"' in content

    def get_format_name(self) -> str:
        return "anadius (codex-like)"


# Detection order: reverse (highest index first), matching the AutoIt script
ALL_ADAPTERS = [
    AnadiusCodexAdapter(),
    AnadiusSimpleAdapter(),
    RuneAdapter(),
    CodexAdapter(),
    RldOriginAdapter(),
]


def detect_format(game_dir: str | Path) -> DLCConfigAdapter | None:
    """Auto-detect which crack config format is present."""
    game_dir = Path(game_dir)
    for adapter in ALL_ADAPTERS:
        if adapter.detect(game_dir):
            return adapter
    return None
