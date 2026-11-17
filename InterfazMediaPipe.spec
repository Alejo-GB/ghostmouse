# -*- mode: python ; coding: utf-8 -*-

import os

from PyInstaller.utils.hooks import collect_all

project_dir = os.path.abspath(SPECPATH)
assets_dir = os.path.join(project_dir, "assets")
gif_dir = os.path.join(assets_dir, "gif")

mediapipe_datas, mediapipe_binaries, mediapipe_hiddenimports = collect_all(
    "mediapipe"
)
gif_datas = [
    (os.path.join(gif_dir, name), os.path.join("assets", "gif"))
    for name in os.listdir(gif_dir)
    if name.lower().endswith(".gif")
]

a = Analysis(
    [os.path.join(project_dir, "Interfaz.py")],
    pathex=[project_dir],
    binaries=mediapipe_binaries,
    datas=mediapipe_datas
    + gif_datas
    + [
        (os.path.join(project_dir, "hand_landmarker.task"), "."),
        (os.path.join(assets_dir, "logo.png"), "assets"),
    ],
    hiddenimports=mediapipe_hiddenimports,
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
    exclude_binaries=False,
    name="GhostMouse",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join(assets_dir, "logo.ico"),
)
