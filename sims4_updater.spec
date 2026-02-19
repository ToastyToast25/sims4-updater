# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Sims 4 Updater.

Builds a single-file Windows executable with:
  - CustomTkinter GUI
  - Bundled tools (xdelta3, unrar)
  - Data files (version hashes, DLC catalog)
  - Patcher library (for patch application)
"""

import os
import sys
from pathlib import Path

# Paths — SPECPATH is set by PyInstaller to the spec file's directory
SPEC_DIR = SPECPATH
SRC_DIR = os.path.join(SPEC_DIR, 'src')
DATA_DIR = os.path.join(SPEC_DIR, 'data')
PATCHER_DIR = os.path.join(os.path.dirname(SPEC_DIR), 'patcher')
TOOLS_DIR = os.path.join(PATCHER_DIR, 'tools')

# Find customtkinter for bundling
import customtkinter
CTK_DIR = os.path.dirname(customtkinter.__file__)

block_cipher = None

a = Analysis(
    [os.path.join(SRC_DIR, 'sims4_updater', '__main__.py')],
    pathex=[SRC_DIR, PATCHER_DIR],
    binaries=[],
    datas=[
        # Data files
        (os.path.join(DATA_DIR, 'version_hashes.json'), 'data'),
        (os.path.join(DATA_DIR, 'dlc_catalog.json'), 'data'),
        # Tools
        (os.path.join(TOOLS_DIR, 'xdelta3-x64.exe'), 'tools'),
        (os.path.join(TOOLS_DIR, 'xdelta3-x86.exe'), 'tools'),
        (os.path.join(TOOLS_DIR, 'unrar.exe'), 'tools'),
        (os.path.join(TOOLS_DIR, 'unrar-license.txt'), 'tools'),
        # Application icon (for window title bar — PNG for crisp rendering)
        (os.path.join(SPEC_DIR, 'sims4.png'), '.'),
        # CustomTkinter assets
        (CTK_DIR, 'customtkinter'),
    ],
    hiddenimports=[
        'customtkinter',
        'pywintypes',
        'win32file',
        'win32timezone',
        'win32api',
        'patcher',
        'patcher.patcher',
        'patcher.myzipfile',
        'patcher.cache',
        'patcher.subprocess_',
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
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Sims4Updater',
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
    icon=os.path.join(SPEC_DIR, 'sims4.ico'),
)
