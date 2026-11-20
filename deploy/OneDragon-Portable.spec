# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

REPO_ROOT = (
    Path(SPECPATH).resolve().parent if 'SPECPATH' in locals() else Path.cwd().parent
)
SRC_DIR = str(REPO_ROOT / 'src')

velopack_datas, velopack_binaries, velopack_hiddenimports = collect_all('velopack')

datas = [
    (str(REPO_ROOT / 'config' / 'project.yml'), 'resources/config'),
    (str(REPO_ROOT / 'config' / 'repository.yml'), 'resources/config'),
    (str(REPO_ROOT / 'assets' / 'template'), 'resources/assets/template'),
    (str(REPO_ROOT / 'assets' / 'ui'), 'resources/assets/ui'),
    (str(REPO_ROOT / 'assets' / 'text'), 'resources/assets/text'),
    (str(REPO_ROOT / 'assets' / 'game_data'), 'resources/assets/game_data'),
] + velopack_datas

binaries = list(velopack_binaries)
hiddenimports = ['_cffi_backend'] + list(velopack_hiddenimports)

a = Analysis(
    [str(REPO_ROOT / 'src' / 'zzz_od' / 'gui' / 'app.py')],
    pathex=[SRC_DIR],
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
    [],
    exclude_binaries=True,
    name='OneDragon',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
    icon=[str(REPO_ROOT / 'assets' / 'ui' / 'logo.ico')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='OneDragon',
)
