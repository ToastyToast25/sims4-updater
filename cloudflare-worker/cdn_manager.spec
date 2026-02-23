# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for CDN Manager.

Builds a single-file Windows executable with:
  - CustomTkinter GUI
  - Patcher library (for patch creation)
  - Binary tools (xdelta3, unrar)
  - Data files (DLC catalog)
"""

import os
from pathlib import Path

# Paths — SPECPATH is set by PyInstaller to the spec file's directory
SPEC_DIR = SPECPATH  # cloudflare-worker/
REPO_DIR = os.path.dirname(SPEC_DIR)  # sims4-updater/
PATCHER_DIR = os.path.join(os.path.dirname(REPO_DIR), 'patcher')
TOOLS_DIR = os.path.join(PATCHER_DIR, 'tools')
DATA_DIR = os.path.join(REPO_DIR, 'data')

# Find customtkinter for bundling
import customtkinter
CTK_DIR = os.path.dirname(customtkinter.__file__)

block_cipher = None

# Collect data files — only include what exists
datas = [
    # CustomTkinter assets (required for theming)
    (CTK_DIR, 'customtkinter'),
]

# DLC catalog for DLC names/types
dlc_catalog = os.path.join(DATA_DIR, 'dlc_catalog.json')
if os.path.isfile(dlc_catalog):
    datas.append((dlc_catalog, 'data'))

# Version hashes for fingerprint verification
version_hashes = os.path.join(DATA_DIR, 'version_hashes.json')
if os.path.isfile(version_hashes):
    datas.append((version_hashes, 'data'))

# Icon for window
icon_png = os.path.join(REPO_DIR, 'sims4.png')
if os.path.isfile(icon_png):
    datas.append((icon_png, '.'))

# Patcher tools (for patch creation)
for tool in ['xdelta3-x64.exe', 'xdelta3-x86.exe', 'unrar.exe', 'unrar-license.txt']:
    tool_path = os.path.join(TOOLS_DIR, tool)
    if os.path.isfile(tool_path):
        datas.append((tool_path, 'tools'))

a = Analysis(
    [os.path.join(SPEC_DIR, 'cdn_manager', '__main__.py')],
    pathex=[
        PATCHER_DIR,    # ../patcher/ (for PatchMaker)
    ],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'customtkinter',
        'paramiko',
        'bcrypt',
        'nacl',
        'cryptography',
        'requests',
        # Patcher (for patch creation)
        'patcher',
        'patcher.patch_maker',
        'patcher.patcher',
        'patcher.myzipfile',
        'patcher.files',
        'patcher.utils',
        'patcher.exceptions',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
        'cv2',
        'pytest',
        'ruff',
        'win32com',
        'pywin32',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Icon
icon_file = os.path.join(REPO_DIR, 'sims4.ico')
if not os.path.isfile(icon_file):
    icon_file = None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CDNManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)
