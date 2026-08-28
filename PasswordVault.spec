# -*- mode: python ; coding: utf-8 -*-

# The package's .py files used to be added as data, which shipped readable
# source inside the one-file exe alongside the compiled modules it actually
# imports. They were there because the dialogs are imported lazily inside
# the handlers that open them, so static analysis misses them — but the
# hiddenimports list below already covers that, and it is what the frozen
# app imports from. Verified by building both ways and opening every dialog
# in the built exe.

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('icon.ico', '.')],
    hiddenimports=[
        'password_vault',
        'password_vault.crypto',
        'password_vault.export_import',
        'password_vault.i18n',
        # Imported inside export_import's reader functions, so static
        # analysis does not see them — the same reason the dialogs are
        # listed.
        'password_vault.import_1pux',
        'password_vault.import_json',
        'password_vault.import_profiles',
        'password_vault.instance_lock',
        'password_vault.security',
        'password_vault.settings',
        'password_vault.theme',
        'password_vault.ui',
        'password_vault.ui.floating',
        'password_vault.ui.mini_vault',
        'password_vault.ui.widgets',
        # Dialogs are imported lazily inside the handlers that open them, so
        # they are listed explicitly rather than relying on static analysis.
        'password_vault.ui.dialogs',
        'password_vault.ui.dialogs.about',
        'password_vault.ui.dialogs.backup',
        'password_vault.ui.dialogs.bulk_ssh',
        'password_vault.ui.dialogs.change_password',
        'password_vault.ui.dialogs.data_io',
        'password_vault.ui.dialogs.generator',
        'password_vault.ui.dialogs.security_dashboard',
        'password_vault.ui.dialogs.trash',
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
