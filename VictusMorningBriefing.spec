# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for a single-file Windows build (run build_windows.ps1)."""
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
# SPEC is injected by PyInstaller when this file runs.
spec_dir = os.path.dirname(os.path.abspath(SPEC))

# edge_tts ships data files; pygame is handled by PyInstaller's hook (avoid collect_all(pygame) — it pulls tests).
d_edge, b_edge, h_edge = collect_all("edge_tts")

datas = d_edge + [(os.path.join(spec_dir, "config.example.json"), ".")]
binaries = b_edge

hiddenimports = list(
    set(
        h_edge
        + collect_submodules("victus")
        + [
            "pygame",
            "pyttsx3",
            "comtypes",
            "pkg_resources",
            "requests",
            "feedparser",
            "certifi",
        ]
    )
)

a = Analysis(
    ["morning_briefing.py"],
    pathex=[spec_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="VictusMorningBriefing",
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
)
