# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

RUNTIME = Path(SPECPATH) / '柒悁工具箱'

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[(str(RUNTIME / name), '.') for name in ('tool.raw', 'launcher.raw', 'ai_panel.raw', 'library_manager.raw', 'mythware_panel.raw', 'reaction_test.raw', 'favicon.ico')],
    hiddenimports=['pyautogui', 'pyzipper', 'psutil', 'PIL', 'cryptography', 'rarfile', 'requests'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['cv2'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    [],
    name='Toolbox',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(RUNTIME / 'favicon.ico')],
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Toolbox',
)
