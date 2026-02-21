"""
Troubleshooting diagnostics — auto-detect common Sims 4 issues.

Checks:
  - VC Redistributable 2015-2022 (x64) installed
  - .NET Framework enabled
  - Windows Defender ransomware protection (Controlled Folder Access)
  - Game directory permissions
  - Game directory path issues (semicolons, non-ASCII)
  - Key game files not quarantined by antivirus
  - Documents/Electronic Arts folder accessible
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class CheckStatus(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class DiagnosticResult:
    name: str
    status: CheckStatus
    message: str
    fix: str = ""  # Suggested fix


@dataclass
class DiagnosticsReport:
    results: list[DiagnosticResult]
    game_dir: str = ""

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.PASS)

    @property
    def warn_count(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.WARN)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if r.status == CheckStatus.FAIL)

    @property
    def is_healthy(self) -> bool:
        return self.fail_count == 0


def run_diagnostics(game_dir: str | Path | None = None) -> DiagnosticsReport:
    """Run all diagnostic checks and return a report."""
    results = []
    game_dir_str = str(game_dir) if game_dir else ""

    results.append(_check_vc_redist())
    results.append(_check_dotnet_framework())

    if game_dir:
        game_path = Path(game_dir)
        results.append(_check_dir_path_issues(game_path))
        results.append(_check_dir_permissions(game_path))
        results.append(_check_game_exe_exists(game_path))
        results.append(_check_game_bin_files(game_path))

    results.append(_check_documents_folder())
    results.append(_check_controlled_folder_access())

    return DiagnosticsReport(results=results, game_dir=game_dir_str)


def _check_vc_redist() -> DiagnosticResult:
    """Check if Visual C++ Redistributable 2015-2022 (x64) is installed."""
    if os.name != "nt":
        return DiagnosticResult(
            name="VC++ Redistributable",
            status=CheckStatus.SKIP,
            message="Not applicable on this OS.",
        )

    try:
        import winreg

        # Check for VC Redist 2015-2022 x64 in multiple registry locations
        vc_keys = [
            (
                r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
                "Installed",
            ),
            (
                r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
                "Installed",
            ),
        ]

        for key_path, value_name in vc_keys:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
                    if value == 1:
                        # Get version info
                        try:
                            major, _ = winreg.QueryValueEx(key, "Major")
                            minor, _ = winreg.QueryValueEx(key, "Minor")
                            bld, _ = winreg.QueryValueEx(key, "Bld")
                            return DiagnosticResult(
                                name="VC++ Redistributable",
                                status=CheckStatus.PASS,
                                message=f"VC++ 2015-2022 x64 installed (v{major}.{minor}.{bld}).",
                            )
                        except OSError:
                            return DiagnosticResult(
                                name="VC++ Redistributable",
                                status=CheckStatus.PASS,
                                message="VC++ 2015-2022 x64 installed.",
                            )
            except OSError:
                continue

        # Also check if the DLLs exist directly
        sys32 = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32"
        required_dlls = ["vcruntime140.dll", "msvcp140.dll"]
        all_present = all((sys32 / dll).is_file() for dll in required_dlls)

        if all_present:
            return DiagnosticResult(
                name="VC++ Redistributable",
                status=CheckStatus.PASS,
                message="VC++ runtime DLLs found in System32.",
            )

        return DiagnosticResult(
            name="VC++ Redistributable",
            status=CheckStatus.FAIL,
            message="VC++ 2015-2022 x64 not detected.",
            fix=(
                "Download and install from: "
                "https://aka.ms/vs/17/release/vc_redist.x64.exe"
            ),
        )
    except Exception as e:
        return DiagnosticResult(
            name="VC++ Redistributable",
            status=CheckStatus.WARN,
            message=f"Could not check: {e}",
        )


def _check_dotnet_framework() -> DiagnosticResult:
    """Check if .NET Framework is enabled."""
    if os.name != "nt":
        return DiagnosticResult(
            name=".NET Framework",
            status=CheckStatus.SKIP,
            message="Not applicable on this OS.",
        )

    try:
        import winreg

        key_path = r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            release, _ = winreg.QueryValueEx(key, "Release")
            # 528040 = .NET 4.8, 461808 = .NET 4.7.2
            if release >= 461808:
                return DiagnosticResult(
                    name=".NET Framework",
                    status=CheckStatus.PASS,
                    message=f".NET Framework 4.7.2+ detected (release {release}).",
                )
            else:
                return DiagnosticResult(
                    name=".NET Framework",
                    status=CheckStatus.WARN,
                    message=f".NET Framework found but may be outdated (release {release}).",
                    fix="Update .NET Framework via Windows Update.",
                )
    except OSError:
        return DiagnosticResult(
            name=".NET Framework",
            status=CheckStatus.FAIL,
            message=".NET Framework 4.x not detected.",
            fix=(
                "Enable via Control Panel > Programs > "
                "Turn Windows features on or off > .NET Framework"
            ),
        )
    except Exception as e:
        return DiagnosticResult(
            name=".NET Framework",
            status=CheckStatus.WARN,
            message=f"Could not check: {e}",
        )


def _check_dir_path_issues(game_dir: Path) -> DiagnosticResult:
    """Check game directory path for known problematic characters."""
    path_str = str(game_dir)
    issues = []

    if ";" in path_str:
        issues.append("path contains a semicolon (;) — causes graphics errors")

    try:
        path_str.encode("ascii")
    except UnicodeEncodeError:
        issues.append("path contains non-ASCII characters — may cause issues")

    if len(path_str) > 200:
        issues.append("path is very long — may cause issues with some files")

    if issues:
        return DiagnosticResult(
            name="Game Directory Path",
            status=CheckStatus.WARN,
            message="; ".join(issues) + ".",
            fix="Move the game to a simpler path like C:\\Games\\The Sims 4.",
        )

    return DiagnosticResult(
        name="Game Directory Path",
        status=CheckStatus.PASS,
        message=f"Path looks good: {path_str}",
    )


def _check_dir_permissions(game_dir: Path) -> DiagnosticResult:
    """Check if we can read and write to the game directory."""
    if not game_dir.is_dir():
        return DiagnosticResult(
            name="Directory Permissions",
            status=CheckStatus.FAIL,
            message=f"Game directory does not exist: {game_dir}",
        )

    # Check read access
    can_read = os.access(game_dir, os.R_OK)
    can_write = os.access(game_dir, os.W_OK)

    if can_read and can_write:
        return DiagnosticResult(
            name="Directory Permissions",
            status=CheckStatus.PASS,
            message="Read and write access to game directory confirmed.",
        )
    elif can_read:
        return DiagnosticResult(
            name="Directory Permissions",
            status=CheckStatus.FAIL,
            message="Game directory is read-only.",
            fix="Right-click game folder > Properties > Security > ensure Full Control.",
        )
    else:
        return DiagnosticResult(
            name="Directory Permissions",
            status=CheckStatus.FAIL,
            message="Cannot access game directory.",
            fix="Run the updater as administrator, or fix folder permissions.",
        )


def _check_game_exe_exists(game_dir: Path) -> DiagnosticResult:
    """Check if the main game executable exists (not quarantined by AV)."""
    exe_paths = [
        game_dir / "Game" / "Bin" / "TS4_x64.exe",
        game_dir / "Game-cracked" / "Bin" / "TS4_x64.exe",
    ]

    found = []
    missing = []
    for p in exe_paths:
        if p.is_file():
            found.append(str(p.relative_to(game_dir)))
        else:
            missing.append(str(p.relative_to(game_dir)))

    if not found:
        return DiagnosticResult(
            name="Game Executable",
            status=CheckStatus.FAIL,
            message="TS4_x64.exe not found — may have been quarantined by antivirus.",
            fix="Add Game\\Bin to your antivirus exclusions and restore the file.",
        )

    return DiagnosticResult(
        name="Game Executable",
        status=CheckStatus.PASS,
        message=f"Found: {', '.join(found)}",
    )


def _check_game_bin_files(game_dir: Path) -> DiagnosticResult:
    """Check for critical DLL files in Game/Bin that AV may quarantine."""
    bin_dir = game_dir / "Game" / "Bin"
    if not bin_dir.is_dir():
        return DiagnosticResult(
            name="Game Bin Files",
            status=CheckStatus.SKIP,
            message="Game/Bin directory not found.",
        )

    critical_files = [
        "anadius64.dll",
        "anadius32.dll",
        "OrangeEmu64.dll",
        "Default.ini",
    ]

    missing = []
    found = []
    for fname in critical_files:
        if (bin_dir / fname).is_file():
            found.append(fname)
        else:
            # These files are optional depending on crack type, so just note them
            missing.append(fname)

    # At least Default.ini should exist
    if "Default.ini" in missing:
        return DiagnosticResult(
            name="Game Bin Files",
            status=CheckStatus.FAIL,
            message="Default.ini missing from Game/Bin.",
            fix="Verify game integrity or re-run the updater.",
        )

    if missing:
        # Only warn, since which DLLs exist depends on crack type
        return DiagnosticResult(
            name="Game Bin Files",
            status=CheckStatus.PASS,
            message=f"Core files present. Optional files not found: {', '.join(missing)}",
        )

    return DiagnosticResult(
        name="Game Bin Files",
        status=CheckStatus.PASS,
        message="All critical Game/Bin files present.",
    )


def _check_documents_folder() -> DiagnosticResult:
    """Check if the Documents/Electronic Arts/The Sims 4 folder is accessible."""
    docs = Path(os.path.expanduser("~")) / "Documents" / "Electronic Arts" / "The Sims 4"

    if not docs.exists():
        return DiagnosticResult(
            name="Save Data Folder",
            status=CheckStatus.WARN,
            message="Documents\\Electronic Arts\\The Sims 4 not found.",
            fix="Run the game once to create it, or check OneDrive sync settings.",
        )

    can_read = os.access(docs, os.R_OK)
    can_write = os.access(docs, os.W_OK)

    if can_read and can_write:
        return DiagnosticResult(
            name="Save Data Folder",
            status=CheckStatus.PASS,
            message="Documents folder accessible with read/write permissions.",
        )

    return DiagnosticResult(
        name="Save Data Folder",
        status=CheckStatus.FAIL,
        message="Cannot write to Documents\\Electronic Arts\\The Sims 4.",
        fix=(
            "Check Windows Defender Ransomware Protection — disable Controlled "
            "Folder Access or add TS4_x64.exe to the allowed apps list."
        ),
    )


def _check_controlled_folder_access() -> DiagnosticResult:
    """Check if Windows Defender Controlled Folder Access is enabled."""
    if os.name != "nt":
        return DiagnosticResult(
            name="Controlled Folder Access",
            status=CheckStatus.SKIP,
            message="Not applicable on this OS.",
        )

    try:
        # Query via PowerShell (requires admin for full info, but we can try)
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-MpPreference | Select-Object -ExpandProperty EnableControlledFolderAccess",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        output = result.stdout.strip()
        if output == "1" or output.lower() == "true":
            return DiagnosticResult(
                name="Controlled Folder Access",
                status=CheckStatus.WARN,
                message="Windows Defender Controlled Folder Access is ENABLED.",
                fix=(
                    "This can prevent the game from saving. Either disable it or "
                    "add TS4_x64.exe to the allowed apps list in Windows Security > "
                    "Virus & threat protection > Ransomware protection."
                ),
            )
        elif output == "0" or output.lower() == "false":
            return DiagnosticResult(
                name="Controlled Folder Access",
                status=CheckStatus.PASS,
                message="Controlled Folder Access is disabled.",
            )
        else:
            return DiagnosticResult(
                name="Controlled Folder Access",
                status=CheckStatus.WARN,
                message=f"Could not determine CFA status (output: {output}).",
            )
    except subprocess.TimeoutExpired:
        return DiagnosticResult(
            name="Controlled Folder Access",
            status=CheckStatus.WARN,
            message="Check timed out.",
        )
    except Exception:
        return DiagnosticResult(
            name="Controlled Folder Access",
            status=CheckStatus.WARN,
            message="Could not check (may need admin privileges).",
        )
