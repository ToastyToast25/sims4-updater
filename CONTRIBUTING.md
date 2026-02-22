# Contributing to Sims 4 Updater

Thank you for your interest in contributing. This guide will take you from a fresh clone to a working development environment and give you the knowledge you need to make meaningful contributions confidently.

If you read this document carefully, you should be productive within 15 minutes.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Development Workflow](#2-development-workflow)
3. [Architecture Overview](#3-architecture-overview)
4. [Code Style Guide](#4-code-style-guide)
5. [Adding a New Feature](#5-adding-a-new-feature)
6. [Threading Rules](#6-threading-rules)
7. [Testing](#7-testing)
8. [Pull Request Guidelines](#8-pull-request-guidelines)
9. [Reporting Issues](#9-reporting-issues)
10. [Project Documentation](#10-project-documentation)

---

## 1. Getting Started

### Prerequisites

- Python 3.12 or later (the project is developed on 3.14; CI runs on 3.12)
- Git
- Windows (the application uses `pywin32` for registry access and Windows API calls; non-Windows development is unsupported)

### Fork and Clone

```bash
# Fork the repository on GitHub first, then:
git clone https://github.com/YOUR_USERNAME/sims4-updater.git
cd sims4-updater
```

### Set Up the Patcher Dependency

This project depends on a sibling repository called `patcher`. It is **not** a pip package — it is injected into `sys.path` at runtime. You must clone it alongside this repository so the directory layout looks like this:

```
parent-directory/
  sims4-updater/     <-- this repo
  patcher/           <-- sibling repo (required)
```

```bash
# From inside sims4-updater, go up one level and clone the sibling:
cd ..
git clone https://github.com/ToastyToast25/patcher.git
cd sims4-updater
```

The injection happens in `src/sims4_updater/updater.py` at module import time:

```python
_patcher_root = Path(__file__).resolve().parents[3] / "patcher"
sys.path.insert(0, str(_patcher_root))
from patcher.patcher import Patcher as BasePatcher, CallbackType
```

If `../patcher/` does not exist, the import will fail with a `ModuleNotFoundError`.

### Install Dev Dependencies

```bash
pip install -e ".[dev]"
```

This installs the package in editable mode along with all development dependencies: `pytest`, `pytest-cov`, `ruff`, and `pyinstaller`.

### Verify Your Setup

```bash
# Launch the GUI — if it opens, your environment is working:
python -m sims4_updater

# Or run a quick CLI smoke test (no game required):
python -m sims4_updater --help
```

---

## 2. Development Workflow

### Branch Naming

Always branch from `main`. The CI also triggers on `master` (a legacy inconsistency), but all human contributors should use `main` as their base.

```bash
git checkout main
git pull origin main
git checkout -b feature/my-feature-name
# or
git checkout -b fix/issue-description
```

### The Standard Loop

```bash
# 1. Make your changes

# 2. Lint — check for style violations
ruff check src/

# 3. Format — auto-fix formatting
ruff format src/

# 4. Run tests
pytest tests/ -v --tb=short

# 5. Optional: build the exe to verify packaging
pyinstaller --clean --noconfirm Sims4Updater.spec
# Output: dist/Sims4Updater.exe

# 6. Commit with a clear message
git commit -m "feat: add language download progress indicator"

# 7. Open a PR against main
git push origin feature/my-feature-name
```

### Lint and Format Details

The project uses `ruff` configured in `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM"]
```

Run both commands before every commit:

```bash
ruff check src/      # reports violations
ruff format src/     # rewrites files in place
```

CI will fail if either command produces output. There is no separate pre-commit hook, so this is a manual step.

---

## 3. Architecture Overview

The codebase is organized into three strict layers. Each layer may only depend on layers below it. The GUI never touches patcher internals directly; the patcher knows nothing about the GUI.

```
Layer 3: GUI
    gui/app.py                  App(ctk.CTk) — main window, sidebar, threading bridge
    gui/frames/*.py             One frame per tab (HomeFrame, DLCFrame, PackerFrame, ...)
    gui/components.py           Shared widgets: InfoCard, StatusBadge, ToastNotification
    gui/theme.py                All colors, fonts, sizing, animation timing constants
    gui/animations.py           Animator, lerp_color(), ease_out_cubic()

Layer 2: Updater Core
    updater.py                  Sims4Updater(BasePatcher) — main engine
    core/                       Version detection, self-update, exceptions, file utils
    patch/                      Manifest parsing, update planning, HTTP downloader
    dlc/                        DLC catalog, format adapters, downloader, packer, Steam prices
    language/                   Language changer, downloader, packer, Steam integration
    greenluma/                  GreenLuma 2025 installer and orchestrator
    mods/                       Mod management

Layer 1: Patcher (external)
    ../patcher/patcher/         BasePatcher, CallbackType — sibling repo, injected via sys.path
```

For a deep dive into any subsystem, see the [Documentation](#10-project-documentation) section.

### Key Entry Points

| Entry Point | Purpose |
|---|---|
| `src/sims4_updater/__main__.py` | CLI argument parsing and GUI launch |
| `src/sims4_updater/updater.py` | `Sims4Updater` engine — the core class |
| `src/sims4_updater/gui/app.py` | `App` — the main GUI window |
| `src/sims4_updater/__init__.py` | `VERSION = "X.Y.Z"` — single source of truth for version |

### GUI Frames (Current)

Each tab in the sidebar corresponds to one frame class:

| File | Frame Class | Tab |
|---|---|---|
| `gui/frames/home_frame.py` | `HomeFrame` | Home / Update |
| `gui/frames/dlc_frame.py` | `DLCFrame` | DLC |
| `gui/frames/packer_frame.py` | `PackerFrame` | DLC Packer |
| `gui/frames/unlocker_frame.py` | `UnlockerFrame` | EA Unlocker |
| `gui/frames/greenluma_frame.py` | `GreenLumaFrame` | GreenLuma |
| `gui/frames/language_frame.py` | `LanguageFrame` | Language |
| `gui/frames/mods_frame.py` | `ModsFrame` | Mods |
| `gui/frames/downloader_frame.py` | `DownloaderFrame` | Downloader |
| `gui/frames/settings_frame.py` | `SettingsFrame` | Settings |
| `gui/frames/progress_frame.py` | `ProgressFrame` | (internal, shown during updates) |
| `gui/frames/diagnostics_frame.py` | `DiagnosticsFrame` | Diagnostics |

---

## 4. Code Style Guide

### Imports

Every non-trivial module must begin with:

```python
from __future__ import annotations
```

This enables PEP 563 postponed evaluation of annotations, which prevents circular import issues at runtime and is required for Python 3.12 compatibility.

Use `TYPE_CHECKING` guards for imports that are only needed for type annotations:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..gui.app import App
```

Heavy or rarely-used modules should be imported inside the function body rather than at module level:

```python
def pack_dlc(args):
    from pathlib import Path
    from sims4_updater.dlc.packer import DLCPacker  # deferred — heavy import
    ...
```

### Naming Conventions

| Target | Convention | Example |
|---|---|---|
| Classes | `PascalCase` | `DLCConfigAdapter`, `SteamPriceCache` |
| Module-level constants | `UPPER_SNAKE_CASE` | `SENTINEL_FILES`, `MANIFEST_URL` |
| Private methods / attributes | Single `_` prefix | `_poll_callbacks`, `_current_frame_name` |
| Functions and variables | `snake_case` | `detect_format`, `game_dir` |

### Line Length

Maximum 100 characters. Configured in `pyproject.toml` and enforced by `ruff`.

### Colors — Critical Rule

CustomTkinter does **not** support `rgba()`, named colors, or any format other than `#RRGGBB`. Every color in the GUI must be a six-digit hex string accessed through the theme system:

```python
# Correct
from .. import theme
label = ctk.CTkLabel(self, text_color=theme.COLORS["text_muted"])
frame = ctk.CTkFrame(self, fg_color=theme.COLORS["bg_card"])

# Wrong — will raise an exception or produce incorrect results
label = ctk.CTkLabel(self, text_color="rgba(160, 160, 176, 1)")
label = ctk.CTkLabel(self, text_color="gray")
label = ctk.CTkLabel(self, text_color="#a0a0b0")  # works but breaks theming
```

All colors are defined in `src/sims4_updater/gui/theme.py` under the `COLORS` dict. If you need a new color, add it there and reference it by key everywhere.

### No Emojis in Code

Do not add emojis to source files, log messages, or UI labels unless explicitly requested.

---

## 5. Adding a New Feature

### New GUI Frame

This is the most common contribution pattern. Follow these steps exactly.

**Step 1.** Create `src/sims4_updater/gui/frames/my_frame.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from .. import theme

if TYPE_CHECKING:
    from ..app import App


class MyFrame(ctk.CTkFrame):
    """One-line description of what this tab does."""

    def __init__(self, parent: ctk.CTkFrame, app: App) -> None:
        super().__init__(parent, fg_color=theme.COLORS["bg_dark"])
        self.app = app
        self._build_ui()

    def _build_ui(self) -> None:
        """Build static widgets. Called once at startup."""
        # Build your layout here
        pass

    def on_show(self) -> None:
        """Called after the slide animation completes when this frame becomes visible.
        Use this for lazy data loading — do NOT load data in __init__."""
        self.app.run_async(self._load_data, on_done=self._on_data_loaded, on_error=self._on_error)

    def _load_data(self):
        """Runs in background thread. Return value is passed to on_done."""
        return {"items": []}

    def _on_data_loaded(self, result: dict) -> None:
        """Runs on the GUI thread after _load_data completes."""
        pass

    def _on_error(self, exc: Exception) -> None:
        self.app.show_toast(f"Failed to load: {exc}", style="error")
```

**Step 2.** Register the frame in `src/sims4_updater/gui/app.py`. Find `_create_frames()` and add:

```python
from .frames.my_frame import MyFrame

# Inside _create_frames():
self.frames["my_feature"] = MyFrame(self._frame_container, self)
```

**Step 3.** Add a sidebar button in `_build_sidebar()`. Find `nav_items` and add your entry:

```python
nav_items = [
    ...
    ("My Feature", "my_feature"),
]
```

**Step 4.** Verify the tab appears and `on_show()` is called when you navigate to it.

### New CLI Command

**Step 1.** Add a handler function in `src/sims4_updater/__main__.py`:

```python
def my_command(args):
    """Brief docstring."""
    from sims4_updater.some_module import SomeClass  # deferred import

    # implementation
```

**Step 2.** Add a subparser in `main()`:

```python
my_parser = subparsers.add_parser("my-command", help="One-line description")
my_parser.add_argument("game_dir", help="Path to The Sims 4 installation directory")
my_parser.add_argument("--flag", help="Optional flag")
```

**Step 3.** Add the dispatch case:

```python
elif args.command == "my-command":
    my_command(args)
```

### New Crack Config Format

The five existing formats cover all known crack distributions, but if a new one appears:

**Step 1.** Open `src/sims4_updater/dlc/formats.py` and subclass `DLCConfigAdapter`:

```python
class MyFormatAdapter(DLCConfigAdapter):
    def detect(self, game_dir: Path) -> bool:
        """Return True if your config file exists."""
        return (game_dir / "Game" / "Bin" / "myformat.cfg").is_file()

    def get_config_path(self, game_dir: Path) -> Path | None:
        p = game_dir / "Game" / "Bin" / "myformat.cfg"
        return p if p.is_file() else None

    def read_enabled_dlcs(self, config_content: str, dlc_codes: list[str]) -> dict[str, bool]:
        """Parse config_content and return {dlc_code: is_enabled}."""
        ...

    def set_dlc_state(self, config_content: str, dlc_code: str, enabled: bool) -> str:
        """Return modified config_content with dlc_code toggled."""
        ...

    def get_format_name(self) -> str:
        return "My Format"

    def get_encoding(self) -> str:
        return "utf-8"  # or "ansi" / "cp1252" as appropriate
```

**Step 2.** Add to `ALL_ADAPTERS`. Detection order is list order — first match wins:

```python
ALL_ADAPTERS: list[DLCConfigAdapter] = [
    AnadiusCodexAdapter(),
    AnadiusSimpleAdapter(),
    RuneAdapter(),
    CodexAdapter(),
    RldOriginAdapter(),
    MyFormatAdapter(),  # add last unless yours should take priority
]
```

### New DLC in the Catalog

Add an entry to `data/dlc_catalog.json`. Match the existing schema:

```json
{
  "id": "EP20",
  "names": {
    "en_US": "My New Expansion",
    "de_DE": "Meine neue Erweiterung"
  },
  "pack_type": "expansion",
  "steam_app_id": 1234567,
  "description": "One sentence description."
}
```

Valid `pack_type` values: `"expansion"`, `"game_pack"`, `"stuff_pack"`, `"kit"`, `"free_pack"`, `"other"`.

---

## 6. Threading Rules

The GUI runs entirely on the main thread. Long-running work (version detection, downloads, file hashing) runs on a background thread. Violating these rules causes deadlocks, crashes, or silent data corruption.

### The Rules

**Rule 1: Never update a widget from a background thread.**

```python
# Wrong — calling widget methods from a background thread
def _bg_task(self):
    self.label.configure(text="Done")  # crashes or corrupts state

# Correct — enqueue the GUI update for the main thread
def _bg_task(self):
    self.app._enqueue_gui(self.label.configure, text="Done")
```

**Rule 2: Use `run_async()` for background work.**

```python
# Submits to the single-worker ThreadPoolExecutor
self.app.run_async(
    self._heavy_function,       # runs in background
    arg1, arg2,                 # positional args passed to the function
    on_done=self._on_success,   # called on main thread with return value
    on_error=self._on_failure,  # called on main thread with the exception
)
```

**Rule 3: DLC downloads use dedicated threads.**

DLC downloads are long-running and must not block the shared executor (which is used for version detection and patching). The `DLCDownloader` class manages its own `threading.Thread`. Do not submit DLC downloads to `run_async()`.

**Rule 4: `_enqueue_gui()` is your escape hatch from any thread.**

```python
# Safe from any thread — queued and dispatched on the next 100ms poll cycle
self.app._enqueue_gui(self._update_progress_bar, fraction)
self.app._enqueue_gui(self.app.show_toast, "Download complete", "success")
```

### Toast Notifications

```python
# From the GUI thread:
self.app.show_toast("Settings saved", style="success")
self.app.show_toast("Game not found", style="warning")
self.app.show_toast("Download failed", style="error")
self.app.show_toast("Checking manifest...", style="info")
```

Valid styles: `"success"`, `"warning"`, `"error"`, `"info"`.

### Status Badges

```python
badge.set_status("Installed", "success")
badge.set_status("Not found", "error")
badge.set_status("Checking...", "muted")
```

Valid styles: `"success"`, `"warning"`, `"error"`, `"info"`, `"muted"`.

---

## 7. Testing

### Running Tests

```bash
# Basic test run
pytest tests/ -v --tb=short

# With coverage report
pytest tests/ -v --cov=src/sims4_updater --cov-report=term

# Run a single test file
pytest tests/test_version_detect.py -v

# Run a single test
pytest tests/test_version_detect.py::test_exact_match -v
```

### Writing Tests

Tests live in the `tests/` directory. The directory currently has an `__init__.py` but minimal test coverage — contributions of tests are especially welcome.

Follow these conventions:

```python
# tests/test_my_module.py
from __future__ import annotations

import pytest
from sims4_updater.my_module import MyClass


def test_basic_case():
    obj = MyClass()
    result = obj.do_something("input")
    assert result == "expected"


def test_error_case():
    obj = MyClass()
    with pytest.raises(ValueError, match="invalid input"):
        obj.do_something(None)


@pytest.fixture
def sample_game_dir(tmp_path):
    """Create a minimal fake Sims 4 directory structure for testing."""
    (tmp_path / "Game" / "Bin").mkdir(parents=True)
    (tmp_path / "Game" / "Bin" / "TS4_x64.exe").write_bytes(b"")
    (tmp_path / "Data" / "Client").mkdir(parents=True)
    return tmp_path
```

### What to Test

- Unit tests for pure logic: version detection, manifest parsing, update planning, DLC config parsing
- Integration tests for file I/O: use `tmp_path` fixtures, never touch real game directories
- Do not test GUI code directly — test the underlying logic methods that frames call

---

## 8. Pull Request Guidelines

### Before Opening a PR

Run this checklist locally:

```bash
ruff check src/         # must produce no output
ruff format src/        # apply formatting
pytest tests/ -v        # all tests must pass
```

If you built the exe, verify it launches without errors.

### PR Content

- **Title**: Short, imperative sentence. "Add rate limiter for manifest requests", not "Added rate limiting".
- **Description**: Explain what you changed and why. Link any related issues with `Fixes #123` or `Related to #456`.
- **Scope**: One feature or fix per PR. Do not bundle unrelated changes.
- **Formatting**: Do not include mass reformatting of unrelated files. It makes review difficult.

### What Reviewers Look For

- Correctness: does the feature work as described?
- Threading: are all GUI updates dispatched via `_enqueue_gui()` or `on_done`/`on_error`?
- Colors: are all colors hex strings from `theme.COLORS`?
- Style: does `ruff check` pass?
- Tests: are new logic paths covered?
- Layer discipline: does the change respect the three-layer boundary?

---

## 9. Reporting Issues

Use [GitHub Issues](https://github.com/ToastyToast25/sims4-updater/issues).

### What to Include

A good bug report contains:

1. **Steps to reproduce** — exact steps, starting from launching the application
2. **Expected behavior** — what you expected to happen
3. **Actual behavior** — what actually happened (screenshots welcome)
4. **Game version** — e.g., `1.121.372.1020` (visible in the Home tab)
5. **OS version** — e.g., Windows 11 22H2
6. **Updater version** — visible in the window title or About section
7. **Log output** — if there was a crash, include the full traceback

### For Crashes

The updater writes log output to its console (if run from a terminal) and may also write to a log file in `%LOCALAPPDATA%\ToastyToast25\sims4_updater\`. Include the full content of any log file present.

### Feature Requests

Feature requests are welcome. Open an issue describing:
- The problem you are trying to solve
- Your proposed solution or the behavior you want
- Any alternatives you considered

---

## 10. Project Documentation

Full technical documentation lives in the `Documentation/` directory. Read these before making significant changes to a subsystem.

| File | What It Covers |
|---|---|
| `Documentation/User_Guide.md` | End-user reference for all tabs, CLI commands, and troubleshooting |
| `Documentation/Architecture_and_Developer_Guide.md` | Three-layer architecture, full module map, threading model, GUI patterns, build system |
| `Documentation/Update_and_Patching_System.md` | Version detection, manifest parsing, BFS update planning, patch downloading, hash learning |
| `Documentation/DLC_Management_System.md` | DLC catalog, all five crack config formats, download pipeline, EA Unlocker, Steam pricing |
| `Documentation/DLC_Packer_and_Distribution.md` | DLC packer class, ZIP format spec, manifest generation, import flow, distribution workflow |
| `Documentation/GreenLuma_Integration.md` | GreenLuma 2025 installation, configuration, and Steam launch orchestration |

The `Architecture_and_Developer_Guide.md` is the best starting point for understanding how the pieces fit together.

---

## Data and Settings Paths (Reference)

| Path | Content |
|---|---|
| `%LOCALAPPDATA%\ToastyToast25\sims4_updater\settings.json` | User preferences (game path, manifest URL, language, theme) |
| `%LOCALAPPDATA%\ToastyToast25\sims4_updater\learned_hashes.json` | Self-learned version fingerprints from the `learn` command |
| `%LOCALAPPDATA%\ToastyToast25\sims4_updater\downloads\` | Patch download cache |
| `%LOCALAPPDATA%\ToastyToast25\sims4_updater\packed_dlcs\` | DLC Packer output directory |
| `%APPDATA%\ToastyToast25\EA DLC Unlocker\` | EA DLC Unlocker entitlements file |

---

## CLI Quick Reference

```bash
python -m sims4_updater                                    # Launch GUI
python -m sims4_updater status [game_dir]                  # Show game status overview
python -m sims4_updater detect <game_dir>                  # Detect installed version
python -m sims4_updater check [game_dir] [--manifest-url]  # Check for updates
python -m sims4_updater manifest <url|file>                # Inspect a patch manifest
python -m sims4_updater dlc <game_dir>                     # Show DLC enabled/disabled states
python -m sims4_updater dlc-auto <game_dir>                # Auto-toggle DLCs to match installed
python -m sims4_updater pack-dlc <game_dir> EP01 GP05 -o . # Pack DLC zip archives
python -m sims4_updater learn <game_dir> 1.121.372.1020    # Learn version hashes from install
python -m sims4_updater language [code] [--game-dir]       # Show or set language
```

---

## Exception Hierarchy (Reference)

All application errors subclass `UpdaterError`, defined in `src/sims4_updater/core/exceptions.py`:

```
UpdaterError
  ExitingError
  WritePermissionError
  NotEnoughSpaceError
  FileMissingError
  VersionDetectionError
  ManifestError
  DownloadError
  IntegrityError
  NoUpdatePathError
  NoCrackConfigError
  XdeltaError
  AVButtinInError
```

Catch the narrowest exception you can handle. Let others propagate to the `on_error` callback in the GUI layer, where they become toast notifications.
