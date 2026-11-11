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

datas = []

# 1. static 폴더 번들링
if os.path.isdir(static_dir):
    datas.append((static_dir, 'static'))

# 2. i18n 35개 다국어 번역 파일 폴더 번들링
if os.path.isdir(i18n_dir):
    datas.append((i18n_dir, 'i18n'))

# 3. Assets 폴더 번들링
if os.path.isdir(assets_dir):
    datas.append((assets_dir, 'Assets'))

# 4. 개별 브랜드 이미지 파일 추가 번들링
brand_images = ['YongPDF_page_img.png', 'YongPDF_text_img.png', 'yongpdf_donation.jpg']
for image_name in brand_images:
    for base_p in (assets_dir, static_dir, root_dir):
        image_path = os.path.join(base_p, image_name)
        if os.path.isfile(image_path):
            datas.append((image_path, 'static'))
            break

# macOS 앱 아이콘 (.icns)
icon_path = os.path.join(assets_dir, 'YongPDF_page_icon.icns')
if not os.path.isfile(icon_path):
    icon_path = os.path.join(root_dir, 'YongPDF_page_icon.icns')

runtime_hook = os.path.join(hooks_dir, 'rthook_change_wd.py') if os.path.isfile(os.path.join(hooks_dir, 'rthook_change_wd.py')) else None

hidden_modules = [
    'fitz',
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.QtPrintSupport',
    'PIL',
    'PIL.Image',
]

a = Analysis(
    ['pdf_editor_v2.py'],
    pathex=[root_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_modules,
    hookspath=[hooks_dir] if os.path.isdir(hooks_dir) else [],
    runtime_hooks=[runtime_hook] if runtime_hook else [],
    excludes=['PySide6', 'PySide2', 'PyQt5', 'scipy', 'tkinter'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='YongPDF_page',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon_path if (icon_path and os.path.isfile(icon_path)) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='YongPDF_page',
)

app = BUNDLE(
    coll,
    name='YongPDF_page.app',
    icon=icon_path if (icon_path and os.path.isfile(icon_path)) else None,
    bundle_identifier='com.yongpdf.page',
    info_plist={
        'CFBundleDisplayName': 'YongPDF Page',
        'CFBundleName': 'YongPDF Page',
        'CFBundleExecutable': 'YongPDF_page',
        'CFBundlePackageType': 'APPL',
        'CFBundleSignature': '????',
        'CFBundleShortVersionString': '1.1.0',
        'CFBundleVersion': '1.1.0',
        'NSHighResolutionCapable': True,
        'NSRequiresAquaSystemAppearance': False,
        'LSEnvironment': {
            'LANG': 'ko_KR.UTF-8',
        },
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'PDF Document',
                'CFBundleTypeExtensions': ['pdf'],
                'CFBundleTypeRole': 'Editor',
                'LSHandlerRank': 'Owner',
                'LSItemContentTypes': ['com.adobe.pdf'],
            }
        ],
    },
)
