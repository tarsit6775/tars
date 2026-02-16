# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for TARS Control macOS menu bar app.
Build: cd tars && pyinstaller app/tars_control.spec
"""

import os
import sys

block_cipher = None

TARS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))

a = Analysis(
    [os.path.join(TARS_DIR, 'app', 'tars_control.py')],
    pathex=[TARS_DIR],
    binaries=[],
    datas=[],
    hiddenimports=[
        'rumps',
        'yaml',
        'json',
        'subprocess',
        'threading',
        'webbrowser',
        'logging',
        'urllib.request',
        'ssl',
        'certifi',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas',
        'PIL', 'cv2', 'torch', 'tensorflow',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TARS Control',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TARS Control',
)

app = BUNDLE(
    coll,
    name='TARS Control.app',
    icon=os.path.join(TARS_DIR, 'app', 'icon.icns'),
    bundle_identifier='com.tars.control',
    info_plist={
        'CFBundleName': 'TARS Control',
        'CFBundleDisplayName': 'TARS Control',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleInfoDictionaryVersion': '6.0',
        'CFBundlePackageType': 'APPL',
        'CFBundleSignature': 'TARS',
        'LSMinimumSystemVersion': '10.15',
        'LSUIElement': True,  # Menu bar app — no dock icon
        'NSHighResolutionCapable': True,
        'LSApplicationCategoryType': 'public.app-category.utilities',
        'NSAppleEventsUsageDescription': 'TARS needs to control apps for automation.',
    },
)
