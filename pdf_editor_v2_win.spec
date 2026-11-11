# -*- mode: python ; coding: utf-8 -*-

import os
import sys

block_cipher = None

_spec_file = globals().get('__file__')
if _spec_file:
    root_dir = os.path.abspath(os.path.dirname(_spec_file))
else:
    root_dir = os.path.abspath(os.getcwd())

hooks_dir = os.path.join(root_dir, 'hooks')

# Assets 디렉토리 탐색 (대소문자 방어)
assets_dir = os.path.join(root_dir, 'Assets')
if not os.path.isdir(assets_dir):
    assets_dir = os.path.join(root_dir, 'assets')

static_dir = os.path.join(root_dir, 'static')
i18n_dir = os.path.join(root_dir, 'i18n')
ghostscript_dir = os.path.join(root_dir, 'ghostscript')
icon_path = os.path.join(assets_dir, 'YongPDF_page_icon.ico')
if not os.path.isfile(icon_path):
    icon_path = os.path.join(root_dir, 'YongPDF_page_icon.ico')

datas_common = []
if os.path.isdir(static_dir):
    datas_common.append((static_dir, 'static'))

if os.path.isdir(i18n_dir):
    datas_common.append((i18n_dir, 'i18n'))

if os.path.isdir(assets_dir):
    datas_common.append((assets_dir, 'Assets'))

# 브랜드 이미지 추가 보장
for image_name in ('YongPDF_page_img.png', 'YongPDF_text_img.png', 'yongpdf_donation.jpg'):
    for base_p in (assets_dir, static_dir, root_dir):
        image_path = os.path.join(base_p, image_name)
        if os.path.isfile(image_path):
            datas_common.append((image_path, 'static'))
            break

# Ghostscript 설치 파일 또는 런타임 번들링
ghostscript_datas = []
if os.path.isdir(ghostscript_dir):
    ghostscript_datas.append((ghostscript_dir, 'ghostscript'))
else:
    for name in ('gs10060w32.exe', 'gs10060w64.exe', 'gswin64c.exe', 'gswin32c.exe', 'gswin64.exe', 'gswin32.exe', 'gs.exe'):
        for search_base in (ghostscript_dir, root_dir, assets_dir):
            candidate = os.path.join(search_base, name)
            if os.path.isfile(candidate):
                ghostscript_datas.append((candidate, 'ghostscript'))
                break

datas_common.extend(ghostscript_datas)

# --- Main viewer (PyQt6) ---
runtime_hook = os.path.join(hooks_dir, 'rthook_change_wd.py') if os.path.isfile(os.path.join(hooks_dir, 'rthook_change_wd.py')) else None

hidden_modules = [
    'fitz',
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.QtPrintSupport',
]

a_main = Analysis(
    ['pdf_editor_v2.py'],
    pathex=[root_dir],
    binaries=[],
    datas=datas_common,
    hiddenimports=hidden_modules,
    hookspath=[hooks_dir] if os.path.isdir(hooks_dir) else [],
    runtime_hooks=[runtime_hook] if runtime_hook else [],
    excludes=['PySide6', 'PyQt5'],
    cipher=block_cipher,
    noarchive=False,
)

pyz_main = PYZ(a_main.pure, a_main.zipped_data, cipher=block_cipher)

# A안: onedir 모드 (exclude_binaries=True, upx=False로 1~1.5초 즉각 기동)
exe_main = EXE(
    pyz_main,
    a_main.scripts,
    [],
    exclude_binaries=True,
    name='YongPDF_page',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon_path if os.path.isfile(icon_path) else None,
)

coll = COLLECT(
    exe_main,
    a_main.binaries,
    a_main.zipfiles,
    a_main.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='YongPDF_page',
)
