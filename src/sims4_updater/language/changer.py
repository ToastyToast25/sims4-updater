"""
Language changer for The Sims 4.

Ported from language-changer.au3 — modifies registry and RldOrigin.ini config.
"""

import os
from pathlib import Path

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

REGISTRY_KEY = r"SOFTWARE\Maxis\The Sims 4"
REGISTRY_VALUE = "Locale"

RLD_CONFIG_PATHS = [
    "Game/Bin/RldOrigin.ini",
    "Game-cracked/Bin/RldOrigin.ini",
    "Game/Bin_LE/RldOrigin.ini",
    "Game-cracked/Bin_LE/RldOrigin.ini",
]


def get_current_language() -> str:
    """Read current language from Windows registry."""
    if os.name != "nt":
        return "en_US"

    try:
        import winreg
    except ImportError:
        return "en_US"

    for hive in (winreg.HKEY_LOCAL_MACHINE,):
        for view in (winreg.KEY_READ, winreg.KEY_READ | winreg.KEY_WOW64_64KEY):
            try:
                with winreg.OpenKey(hive, REGISTRY_KEY, 0, view) as key:
                    value, _ = winreg.QueryValueEx(key, REGISTRY_VALUE)
                    if value in LANGUAGES:
                        return value
            except (OSError, FileNotFoundError):
                continue

    return "en_US"


def set_language(language_code: str, game_dir: str | Path | None = None) -> bool:
    """
    Change the game language.

    Args:
        language_code: Locale code like "en_US".
        game_dir: Optional game directory to update RldOrigin.ini configs.

    Returns:
        True if registry was updated successfully.
    """
    if language_code not in LANGUAGES:
        raise ValueError(f"Unknown language code: {language_code}")

    registry_ok = _set_registry_language(language_code)

    if game_dir:
        _update_rld_configs(Path(game_dir), language_code)

    return registry_ok


def _set_registry_language(language_code: str) -> bool:
    """Write language to Windows registry."""
    if os.name != "nt":
        return False

    try:
        import winreg
    except ImportError:
        return False

    success = False

    # Write to both 32-bit and 64-bit registry views
    for view in (winreg.KEY_WRITE, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY):
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, REGISTRY_KEY, 0, view
            ) as key:
                winreg.SetValueEx(key, REGISTRY_VALUE, 0, winreg.REG_SZ, language_code)
                success = True
        except (OSError, PermissionError):
            continue

    return success


def _update_rld_configs(game_dir: Path, language_code: str) -> None:
    """Update RldOrigin.ini files with the new language."""
    for config_rel in RLD_CONFIG_PATHS:
        config_path = game_dir / config_rel.replace("/", os.sep)
        if not config_path.is_file():
            continue

        try:
            content = config_path.read_text(encoding="utf-8", errors="replace")

            # Update or add [Origin] Language = <code>
            import re
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
        except (OSError, PermissionError):
            continue
