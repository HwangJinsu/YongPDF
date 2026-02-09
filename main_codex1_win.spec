# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

_spec_file = globals().get('__file__')
if _spec_file:
    root_dir = os.path.abspath(os.path.dirname(_spec_file))
else:
    root_dir = os.path.abspath(os.getcwd())
hooks_dir = os.path.join(root_dir, 'hooks')
assets_dir = os.path.join(root_dir, 'assets')

static_dir = os.path.join(root_dir, 'static')
static_datas = []
if os.path.isdir(static_dir):
    static_datas.append((static_dir, 'static'))

# i18n 폴더 추가
i18n_dir = os.path.join(root_dir, 'i18n')
if os.path.isdir(i18n_dir):
    static_datas.append((i18n_dir, 'i18n'))

brand_images = ['YongPDF_page_img.png', 'YongPDF_text_img.png', 'yongpdf_donation.jpg']
for image_name in brand_images:
    image_path = os.path.join(assets_dir, image_name)
    if os.path.isfile(image_path):
        static_datas.append((image_path, 'static'))

icon_path = os.path.join(assets_dir, 'YongPDF_text_icon.ico')

runtime_hook = os.path.join(hooks_dir, 'rthook_change_wd.py') if os.path.isfile(os.path.join(hooks_dir, 'rthook_change_wd.py')) else None

hidden_modules = [
    'fitz',
    'shiboken6',
    'PySide6.QtWidgets',
    'PySide6.QtGui',
    'PySide6.QtCore',
    'fontTools.ttLib',
]

a = Analysis(
    ['main_codex1.py'],
    pathex=[root_dir],
    binaries=[],
    datas=static_datas,
    hiddenimports=hidden_modules,
    hookspath=[hooks_dir] if os.path.isdir(hooks_dir) else [],
    runtime_hooks=[runtime_hook] if runtime_hook else [],
    excludes=['PyQt6', 'PyQt5'],
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
    name='YongPDF_text',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    icon=icon_path if os.path.isfile(icon_path) else None,
)

coll = COLLECT(
    exe,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='YongPDF_text',
)
