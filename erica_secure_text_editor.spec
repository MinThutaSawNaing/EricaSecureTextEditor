# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

native_dll = Path(SPECPATH).resolve() / 'erica_storage.dll'
if not native_dll.is_file() or native_dll.stat().st_size == 0:
    raise SystemExit(
        f'Missing or empty native storage DLL: {native_dll}. '
        'Run build_native.ps1 from this project with an installed Windows Rust '
        'toolchain and the committed native/erica_storage/Cargo.lock, then retry PyInstaller.'
    )

a = Analysis(
    ['erica_secure_text_editor.py'],
    pathex=[],
    binaries=[(str(native_dll), '.')],
    datas=[('icon.ico', '.'), ('closebutton.png', '.')],
    hiddenimports=[],
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
    name='EricaSecureTextEditor',
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
