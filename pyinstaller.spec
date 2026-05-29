# PyInstaller spec for Tethered Alarm
# This file is a starting point for packaging the server entry point into an exe.
# Run: pyinstaller pyinstaller.spec

# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

import os
from PyInstaller.utils.hooks import collect_submodules

base_dir = os.path.abspath(os.path.dirname(__file__))

a = Analysis(
    [os.path.join(base_dir, 'server', 'main.py')],
    pathex=[base_dir],
    binaries=[],
    datas=[
        (os.path.join(base_dir, 'server', 'static'), 'server/static'),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TetheredAlarm',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='TetheredAlarm',
)
