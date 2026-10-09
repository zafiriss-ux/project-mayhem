# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Build Spec for TITAN.exe

Builds standalone Windows executable with bundled Python 3.12+ runtime.

Build command:
    pyinstaller launcher/build.spec

Output:
    dist/TITAN.exe  (single-file executable)

Requirements:
    pip install pyinstaller
"""

import sys
from pathlib import Path

block_cipher = None

# Project root
root_dir = Path('.').absolute()

# Hidden imports (packages not auto-detected by PyInstaller)
hidden_imports = [
    'titan',
    'titan.core',
    'titan.science',
    'titan.integration',
    'titan.orchestration',
    'launcher',
    'launcher.errors',
    'launcher.validator',
    'launcher.wizard',
    'launcher.gui_wizard',
    'launcher.logger',
    # External dependencies
    'sqlite3',
    'threading',
    'tkinter',
    'tkinter.ttk',
    'json',
    'logging',
    'pathlib',
    'datetime',
]

# Data files to include
datas = [
    # titan.__version__ reads the version from pyproject.toml (AGENTS RE-01);
    # the bundle has no package metadata, so the file ships at the bundle root.
    (str(root_dir / 'pyproject.toml'), '.'),
]

a = Analysis(
    ['main.py'],  # Entry point
    pathex=[str(root_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy unused packages
        'matplotlib',
        'pandas',
        'numpy',
        'scipy',
        'pytest',
        'IPython',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TITAN',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Compress with UPX
    upx_exclude=[],
    runtime_tmpdir=None,
    # TITAN's main menu reads the keyboard in a console window. A windowed
    # build (console=False) has no stdin/stdout, so after the setup wizard
    # nothing appeared and the menu could not start (v5.8.0, v5.8.1).
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # TODO: Add titan.ico
)
