# -*- mode: python ; coding: utf-8 -*-

import os

# Collect all password_vault package files
_pkg_dir = os.path.join(SPECPATH, 'password_vault')
_pkg_datas = []
for root, dirs, files in os.walk(_pkg_dir):
    for f in files:
        if f.endswith('.py'):
            src = os.path.join(root, f)
            dst = os.path.relpath(root, SPECPATH)
            _pkg_datas.append((src, dst))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('icon.ico', '.')] + _pkg_datas,
    hiddenimports=[
        'password_vault',
        'password_vault.crypto',
        'password_vault.export_import',
        'password_vault.security',
        'password_vault.settings',
        'password_vault.theme',
        'password_vault.ui',
        'password_vault.ui.floating',
        'password_vault.ui.mini_vault',
        'password_vault.ui.widgets',
    ],
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
    name='PasswordVault',
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
    icon=['icon.ico'],
)
