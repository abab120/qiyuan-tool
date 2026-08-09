# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\Administrator.SC-202011011119\\Desktop\\0\\柒悁工具箱\\tool.raw', '.'), ('C:\\Users\\Administrator.SC-202011011119\\Desktop\\0\\柒悁工具箱\\launcher.raw', '.'), ('C:\\Users\\Administrator.SC-202011011119\\Desktop\\0\\柒悁工具箱\\ai_panel.raw', '.'), ('C:\\Users\\Administrator.SC-202011011119\\Desktop\\0\\柒悁工具箱\\library_manager.raw', '.'), ('C:\\Users\\Administrator.SC-202011011119\\Desktop\\0\\柒悁工具箱\\mythware_panel.raw', '.'), ('C:\\Users\\Administrator.SC-202011011119\\Desktop\\0\\柒悁工具箱\\reaction_test.raw', '.'), ('C:\\Users\\Administrator.SC-202011011119\\Desktop\\0\\柒悁工具箱\\favicon.ico', '.')],
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
    a.binaries,
    a.datas,
    [],
    name='Toolbox',
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
    icon=['C:\\Users\\Administrator.SC-202011011119\\Desktop\\0\\柒悁工具箱\\favicon.ico'],
)
