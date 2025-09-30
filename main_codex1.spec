# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

_spec_file = globals().get('__file__')
if _spec_file:
    root_dir = os.path.abspath(os.path.dirname(_spec_file))
else:
    root_dir = os.path.abspath(os.getcwd())
hooks_dir = os.path.join(root_dir, 'hooks')

runtime_hook = os.path.join(hooks_dir, 'rthook_change_wd.py') if os.path.isfile(os.path.join(hooks_dir, 'rthook_change_wd.py')) else None

hidden_modules = sorted(set(
    ['fitz'] +
    collect_submodules('PySide6') +
    collect_submodules('matplotlib') +
    collect_submodules('fontTools')
))

a = Analysis(
    ['main_codex1.py'],
    pathex=[root_dir],
    binaries=[],
    datas=[],
    hiddenimports=hidden_modules,
    hookspath=[hooks_dir] if os.path.isdir(hooks_dir) else [],
    runtime_hooks=[runtime_hook] if runtime_hook else [],
    excludes=['PyQt6'],
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
    name='main_codex1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
)

coll = COLLECT(
    exe,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='main_codex1',
)
