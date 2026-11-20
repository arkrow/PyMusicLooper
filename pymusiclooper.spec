# -*- mode: python ; coding: utf-8 -*-
"""Cross-platform PyInstaller spec for building standalone PyMusicLooper executables.

Build with:
    pyinstaller --clean --noconfirm pymusiclooper.spec
"""

import os
from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

datas = []
binaries = []
hiddenimports = [
    "sounddevice",
    "soundfile",
    "taglib",
    "yt_dlp",
]

# Bundle package metadata so importlib.metadata.version("pymusiclooper") works in frozen builds
datas += copy_metadata("pymusiclooper")

# Bundle native audio backends and package data files
for pkg in ("sounddevice", "soundfile"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

datas += collect_data_files("librosa")
hiddenimports += collect_submodules("pymusiclooper")
hiddenimports += collect_submodules("rich._unicode_data")

a = Analysis(
    [os.path.join("pymusiclooper", "__main__.py")],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="pymusiclooper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
