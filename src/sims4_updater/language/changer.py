"""
Language changer for The Sims 4.

Modifies the anadius crack config (primary), registry, and RldOrigin.ini
to change the game language. Supports all 18 official Sims 4 languages.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

LANGUAGES = {
    "cs_CZ": "Čeština",
    "da_DK": "Dansk",
    "de_DE": "Deutsch",
    "en_US": "English",
    "es_ES": "Español",
    "fr_FR": "Français",
    "it_IT": "Italiano",
    "nl_NL": "Nederlands",
    "no_NO": "Norsk",
    "pl_PL": "Polski",
    "pt_BR": "Português (Brasil)",
    "fi_FI": "Suomi",
    "sv_SE": "Svenska",
    "ru_RU": "Русский",
    "ja_JP": "日本語",
    "zh_TW": "繁體中文",
    "zh_CN": "简体中文",
    "ko_KR": "한국어",
}

# Mapping from locale code → Strings package file suffix (e.g. "ENG_US")
# The game stores translations in Data/Client/Strings_XXX_XX.package
LOCALE_TO_STRINGS = {
    "cs_CZ": "CZE_CZ",
    "da_DK": "DAN_DK",
    "de_DE": "GER_DE",
    "en_US": "ENG_US",
    "es_ES": "SPA_ES",
    "fr_FR": "FRE_FR",
    "it_IT": "ITA_IT",
    "nl_NL": "DUT_NL",
    "no_NO": "NOR_NO",
    "pl_PL": "POL_PL",
    "pt_BR": "POR_BR",
    "fi_FI": "FIN_FI",
    "sv_SE": "SWE_SE",
    "ru_RU": "RUS_RU",
    "ja_JP": "JPN_JP",
    "zh_TW": "CHT_CN",
    "zh_CN": "CHS_CN",
    "ko_KR": "KOR_KR",
}

# Paths to check for Strings_XXX_XX.package files (relative to game dir)
STRINGS_CHECK_DIRS = [
    "Data/Client",
    "Delta/Base",
]

REGISTRY_KEY = r"SOFTWARE\Maxis\The Sims 4"
REGISTRY_VALUE = "Locale"

# Mapping from locale code → Steam language name
# Steam stores language as lowercase English names in appmanifest ACF files
LOCALE_TO_STEAM = {
    "cs_CZ": "czech",
    "da_DK": "danish",
    "de_DE": "german",
    "en_US": "english",
    "es_ES": "spanish",
    "fr_FR": "french",
    "it_IT": "italian",
    "nl_NL": "dutch",
    "no_NO": "norwegian",
    "pl_PL": "polish",
    "pt_BR": "brazilian",
    "fi_FI": "finnish",
    "sv_SE": "swedish",
    "ru_RU": "russian",
    "ja_JP": "japanese",
    "zh_TW": "tchinese",
    "zh_CN": "schinese",
    "ko_KR": "koreana",
}

# Steam app ID for The Sims 4
SIMS4_STEAM_APP_ID = "1222670"

RLD_CONFIG_PATHS = [
    "Game/Bin/RldOrigin.ini",
    "Game-cracked/Bin/RldOrigin.ini",
    "Game/Bin_LE/RldOrigin.ini",
    "Game-cracked/Bin_LE/RldOrigin.ini",
]

# Anadius crack config locations (checked in order)
ANADIUS_CONFIG_PATHS = [
    "Game-cracked/Bin/anadius.cfg",
    "Game/Bin/anadius.cfg",
    "Game-cracked/Bin_LE/anadius.cfg",
    "Game/Bin_LE/anadius.cfg",
]

# All supported locale codes as a comma-separated string (for override file)
_ALL_LANGUAGES_CSV = ",".join(LANGUAGES.keys())

# Template for anadius_override.cfg language section
_OVERRIDE_TEMPLATE = """\
    "Config2"
    {{
        "Game"
        {{
            "Languages"             "{languages}"
            "Language"              "{language}"
            "LanguageRegistryKey"   "Software\\Maxis\\The Sims 4\\Locale"
        }}
    }}
"""


def get_current_language(game_dir: str | Path | None = None) -> str:
    """Read current language, checking anadius config first, then registry.

    Args:
        game_dir: Optional game directory to check anadius.cfg.

    Returns:
        Language code like "en_US".
    """
    # Try anadius config first (most reliable for cracked installs)
    if game_dir:
        lang = _read_anadius_language(Path(game_dir))
        if lang and lang in LANGUAGES:
            return lang

    # Fall back to registry
    if os.name != "nt":
        return "en_US"

    try:
        import winreg
    except ImportError:
        return "en_US"

    for view in (
        winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        winreg.KEY_READ | winreg.KEY_WOW64_32KEY,
    ):
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, REGISTRY_KEY, 0, view,
            ) as key:
                value, _ = winreg.QueryValueEx(key, REGISTRY_VALUE)
                if value in LANGUAGES:
                    return value
        except (OSError, FileNotFoundError):
            continue

    return "en_US"


def get_strings_filename(language_code: str) -> str | None:
    """Get the Strings package filename for a locale code.

    Returns e.g. "Strings_DAN_DK.package" for "da_DK", or None if unknown.
    """
    suffix = LOCALE_TO_STRINGS.get(language_code)
    if suffix:
        return f"Strings_{suffix}.package"
    return None


def check_language_pack(game_dir: str | Path, language_code: str) -> bool:
    """Check if the language pack (Strings file) is installed for the given language."""
    if not game_dir:
        return False
    game_dir = Path(game_dir)
    filename = get_strings_filename(language_code)
    if not filename:
        return False

    # Check primary Strings locations
    for check_dir in STRINGS_CHECK_DIRS:
        strings_path = game_dir / check_dir.replace("/", os.sep) / filename
        if strings_path.is_file():
            return True
    return False


def get_installed_languages(game_dir: str | Path) -> dict[str, bool]:
    """Check which languages have Strings pack files installed.

    Returns dict of {language_code: is_installed}.
    """
    result = {}
    for code in LANGUAGES:
        result[code] = check_language_pack(game_dir, code)
    return result


@dataclass
class LanguageChangeResult:
    """Result of a language change operation."""

    anadius_updated: list[str]  # paths that were updated
    registry_ok: bool
    rld_updated: list[str]  # paths that were updated
    steam_updated: bool = False  # Steam appmanifest updated

    @property
    def success(self) -> bool:
        return bool(self.anadius_updated) or self.registry_ok or self.steam_updated


def set_language(
    language_code: str,
    game_dir: str | Path | None = None,
    log: callable = None,
) -> LanguageChangeResult:
    """
    Change the game language across all config sources.

    Updates (in order):
      1. anadius.cfg + anadius_override.cfg — sets Language and LanguageRegistryKey
      2. Windows registry — HKLM\\SOFTWARE\\Maxis\\The Sims 4\\Locale
      3. RldOrigin.ini — for non-anadius cracks

    Args:
        language_code: Locale code like "en_US".
        game_dir: Game directory to update crack configs.
        log: Optional callback for status messages.

    Returns:
        LanguageChangeResult with details of what was changed.
    """
    if language_code not in LANGUAGES:
        raise ValueError(f"Unknown language code: {language_code}")

    if log is None:
        log = lambda msg: None

    # Check if language pack files are installed
    if game_dir and not check_language_pack(game_dir, language_code):
        expected = get_strings_filename(language_code) or language_code
        log(
            f"WARNING: Language pack not found ({expected} missing from Data/Client/).\n"
            f"  The config will be updated, but the game may not display in this language\n"
            f"  until the language pack is installed. Use the anadius updater or change\n"
            f"  the Steam language setting to download the required files."
        )

    # 1. Update anadius crack config (most important for cracked games)
    anadius_updated = []
    if game_dir:
        anadius_updated = _update_anadius_configs(
            Path(game_dir), language_code, log,
        )

    # 2. Update Windows registry
    registry_ok = _set_registry_language(language_code)
    if registry_ok:
        log("Registry updated.")
    else:
        log("Warning: Could not write to registry (try running as Administrator).")

    # 3. Update Steam appmanifest (for legit Steam installs)
    steam_updated = False
    if game_dir:
        steam_updated = _update_steam_manifest(Path(game_dir), language_code, log)

    # 4. Update RldOrigin.ini files
    rld_updated = []
    if game_dir:
        rld_updated = _update_rld_configs(Path(game_dir), language_code, log)

    return LanguageChangeResult(
        anadius_updated=anadius_updated,
        registry_ok=registry_ok,
        rld_updated=rld_updated,
        steam_updated=steam_updated,
    )


def _set_registry_language(language_code: str) -> bool:
    """Write language to Windows registry."""
    if os.name != "nt":
        return False

    try:
        import winreg
    except ImportError:
        return False

    success = False

    # Write to both 32-bit and 64-bit registry views.
    # The game/crack may read from either view depending on the build.
    for view in (
        winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY,
        winreg.KEY_WRITE | winreg.KEY_WOW64_32KEY,
    ):
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, REGISTRY_KEY, 0, view
            ) as key:
                winreg.SetValueEx(key, REGISTRY_VALUE, 0, winreg.REG_SZ, language_code)
                success = True
        except (OSError, PermissionError):
            continue

    return success


# ── Anadius crack config ─────────────────────────────────────────

def _read_anadius_language(game_dir: Path) -> str | None:
    """Read the Language field, checking override file first, then anadius.cfg."""
    for config_rel in ANADIUS_CONFIG_PATHS:
        config_path = game_dir / config_rel.replace("/", os.sep)
        if not config_path.is_file():
            continue

        # Check override file first (takes priority over anadius.cfg)
        override_path = config_path.with_name("anadius_override.cfg")
        for check_path in (override_path, config_path):
            if not check_path.is_file():
                continue
            try:
                content = check_path.read_text(encoding="utf-8", errors="replace")
                # Match: "Language"   "en_US"
                m = re.search(r'"Language"\s+"([^"]+)"', content)
                if m:
                    return m.group(1)
            except (OSError, PermissionError):
                continue
    return None


def _update_anadius_configs(
    game_dir: Path, language_code: str, log: callable,
) -> list[str]:
    """Update language in anadius.cfg and anadius_override.cfg files.

    The anadius crack reads language from anadius_override.cfg which
    intercepts registry reads via the LanguageRegistryKey field.
    We update anadius.cfg (if it has a Language field) AND create/update
    anadius_override.cfg to ensure the crack uses the new language.

    Returns list of config paths that were updated.
    """
    updated = []
    for config_rel in ANADIUS_CONFIG_PATHS:
        config_path = game_dir / config_rel.replace("/", os.sep)
        if not config_path.is_file():
            continue

        try:
            content = config_path.read_text(encoding="utf-8", errors="replace")
            original = content

            # Update "Language" value (but not "Languages" which is the list)
            # Pattern: "Language"  followed by whitespace and a quoted value
            # Must NOT match "Languages" or "LanguageRegistryKey" etc.
            content = re.sub(
                r'("Language"(\s+)")[^"]*(")',
                rf'\g<1>{language_code}\3',
                content,
            )

            # Ensure LanguageRegistrySpoof is "true" so the crack uses the
            # Language field directly instead of reading the registry
            content = re.sub(
                r'("LanguageRegistrySpoof"(\s+)")[^"]*(")',
                r'\g<1>true\3',
                content,
            )

            if content != original:
                config_path.write_text(content, encoding="utf-8")
                # Verify write by reading back
                verify = config_path.read_text(encoding="utf-8", errors="replace")
                m = re.search(r'"Language"\s+"([^"]+)"', verify)
                written_lang = m.group(1) if m else "???"
                m2 = re.search(r'"LanguageRegistrySpoof"\s+"([^"]+)"', verify)
                spoof_val = m2.group(1) if m2 else "not found"
                log(f"Updated: {config_path}")
                log(f"  Language = \"{written_lang}\", LanguageRegistrySpoof = \"{spoof_val}\"")
                updated.append(str(config_path))
            else:
                log(f"No changes needed: {config_path}")

        except PermissionError:
            log(f"Permission denied: {config_path} (try running as Administrator)")
        except OSError as e:
            log(f"Error updating {config_path}: {e}")

        # Create/update anadius_override.cfg alongside anadius.cfg.
        # This is the proper mechanism for language changes — the override
        # file tells the crack to intercept registry reads and return the
        # configured language instead.
        override_path = config_path.with_name("anadius_override.cfg")
        try:
            _ensure_language_override(override_path, language_code, log)
            if str(override_path) not in updated:
                updated.append(str(override_path))
        except PermissionError:
            log(f"Permission denied: {override_path} (try running as Administrator)")
        except OSError as e:
            log(f"Error updating {override_path}: {e}")

    return updated


def _ensure_language_override(
    override_path: Path, language_code: str, log: callable,
):
    """Create or update anadius_override.cfg with language settings.

    The override file tells the anadius crack to intercept the game's
    registry read for the Locale key and return the configured language.
    """
    if override_path.is_file():
        content = override_path.read_text(encoding="utf-8", errors="replace")

        # Check if it already has a Language field to update
        if re.search(r'"Language"\s+"[^"]*"', content):
            new_content = re.sub(
                r'("Language"(\s+)")[^"]*(")',
                rf'\g<1>{language_code}\3',
                content,
            )
            if new_content != content:
                override_path.write_text(new_content, encoding="utf-8")
                log(f"Updated override: {override_path}")
                log(f"  Language = \"{language_code}\"")
            else:
                log(f"Override already set: {override_path}")
            return

        # File exists but has no Language field (e.g. Documents override).
        # Add the Game section inside the existing Config2 block.
        game_section = (
            '    "Game"\n'
            '    {\n'
            f'        "Languages"             "{_ALL_LANGUAGES_CSV}"\n'
            f'        "Language"              "{language_code}"\n'
            '        "LanguageRegistryKey"   "Software\\Maxis\\The Sims 4\\Locale"\n'
            '    }\n'
        )
        if '"Config2"' in content:
            # Insert before the last closing brace of Config2
            idx = content.rfind("}")
            if idx >= 0:
                new_content = content[:idx] + game_section + content[idx:]
                override_path.write_text(new_content, encoding="utf-8")
                log(f"Added language section to override: {override_path}")
                return

    # File doesn't exist or couldn't be updated — create from template
    content = _OVERRIDE_TEMPLATE.format(
        languages=_ALL_LANGUAGES_CSV,
        language=language_code,
    )
    override_path.write_text(content, encoding="utf-8")
    log(f"Created override: {override_path}")


# ── Steam appmanifest ────────────────────────────────────────────

def _find_steam_manifest(game_dir: Path) -> Path | None:
    """Find the Steam appmanifest for The Sims 4.

    The game_dir is typically:
      <steam>/steamapps/common/The Sims 4
    The manifest is at:
      <steam>/steamapps/appmanifest_1222670.acf
    """
    # Walk up from game_dir to find steamapps/common, then look for manifest
    # in the steamapps folder
    for parent in (game_dir, game_dir.parent):
        if parent.name.lower() == "common":
            steamapps = parent.parent
            manifest = steamapps / f"appmanifest_{SIMS4_STEAM_APP_ID}.acf"
            if manifest.is_file():
                return manifest
    return None


def _update_steam_manifest(
    game_dir: Path, language_code: str, log: callable,
) -> bool:
    """Update the Steam appmanifest language for The Sims 4.

    Steam reads the language from appmanifest_1222670.acf and uses it
    to determine which language the game runs in. Without updating this,
    legit Steam installs will ignore registry/crack config changes.
    """
    steam_lang = LOCALE_TO_STEAM.get(language_code)
    if not steam_lang:
        return False

    manifest = _find_steam_manifest(game_dir)
    if not manifest:
        log("Steam manifest not found (not a Steam install, or non-standard path).")
        return False

    try:
        content = manifest.read_text(encoding="utf-8", errors="replace")
        original = content

        # Update "language" in both UserConfig and MountedConfig sections
        # Pattern: "language"		"english"  (with tabs as separators)
        content = re.sub(
            r'("language"\s+")[^"]*(")',
            rf'\g<1>{steam_lang}\2',
            content,
        )

        if content != original:
            manifest.write_text(content, encoding="utf-8")
            log(f"Steam manifest updated: {manifest}")
            log(f'  language = "{steam_lang}"')
            return True
        else:
            log(f"Steam manifest already set to {steam_lang}.")
            return True

    except PermissionError:
        log(f"Permission denied: {manifest} (close Steam and try again)")
    except OSError as e:
        log(f"Error updating Steam manifest: {e}")
    return False


# ── RldOrigin.ini ────────────────────────────────────────────────

def _update_rld_configs(
    game_dir: Path, language_code: str, log: callable,
) -> list[str]:
    """Update RldOrigin.ini files with the new language.

    Returns list of config paths that were updated.
    """
    updated = []
    for config_rel in RLD_CONFIG_PATHS:
        config_path = game_dir / config_rel.replace("/", os.sep)
        if not config_path.is_file():
            continue

        try:
            content = config_path.read_text(encoding="utf-8", errors="replace")

            # Update or add [Origin] Language = <code>
            if re.search(r"(?i)\[Origin\]", content):
                # Section exists, update or add Language key
                if re.search(r"(?i)Language\s*=", content):
                    content = re.sub(
                        r"(?i)(Language\s*=\s*)\S+",
                        rf"\g<1>{language_code}",
                        content,
                    )
                else:
                    content = re.sub(
                        r"(?i)(\[Origin\])",
                        rf"\1\nLanguage = {language_code}",
                        content,
                    )
            else:
                content += f"\n[Origin]\nLanguage = {language_code}\n"

            config_path.write_text(content, encoding="utf-8")
            log(f"Updated: {config_path}")
            updated.append(str(config_path))
        except PermissionError:
            log(f"Permission denied: {config_path}")
        except OSError as e:
            log(f"Error updating {config_path}: {e}")

    return updated
