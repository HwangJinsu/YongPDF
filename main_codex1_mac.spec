# -*- mode: python ; coding: utf-8 -*-

import os
import sys
import subprocess
from PIL import Image

block_cipher = None

_spec_file = globals().get('__file__')
if _spec_file:
    root_dir = os.path.abspath(os.path.dirname(_spec_file))
else:
    root_dir = os.path.abspath(os.getcwd())

hooks_dir = os.path.join(root_dir, 'hooks')
static_dir = os.path.join(root_dir, 'static')
mac_icon_path = os.path.join(root_dir, 'YongPDF_text_icon.icns')

# Ensure macOS .icns exists (generate from PNG if necessary)
def ensure_icns(png_path: str, icns_path: str) -> str | None:
    if os.path.isfile(icns_path):
        return icns_path
    if not os.path.isfile(png_path):
        return None
    try:
        import shutil
        iconset_dir = os.path.join(root_dir, '_yongpdf_text_iconset')
        if os.path.isdir(iconset_dir):
            shutil.rmtree(iconset_dir, ignore_errors=True)
        os.makedirs(iconset_dir, exist_ok=True)
        base_img = Image.open(png_path).convert('RGBA')
        sizes = [16, 32, 64, 128, 256, 512]
        for size in sizes:
            for scale in (1, 2):
                dim = size * scale
                resized = base_img.resize((dim, dim), Image.LANCZOS)
                suffix = f"@{scale}x" if scale == 2 else ''
                resized.save(os.path.join(iconset_dir, f'icon_{size}x{size}{suffix}.png'))
        subprocess.run(['iconutil', '-c', 'icns', iconset_dir, '-o', icns_path], check=False)
        shutil.rmtree(iconset_dir, ignore_errors=True)
        return icns_path if os.path.isfile(icns_path) else None
    except Exception:
        return None


static_datas = []
if os.path.isdir(static_dir):
    static_datas.append((static_dir, os.path.join('Contents', 'Resources', 'static')))

for image_name in ('YongPDF_page_img.png', 'YongPDF_text_img.png'):
    image_path = os.path.join(root_dir, image_name)
    if os.path.isfile(image_path):
        static_datas.append((image_path, os.path.join('Contents', 'Resources', 'static', image_name)))

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
    icon=ensure_icns(os.path.join(root_dir, 'YongPDF_text_img.png'), mac_icon_path),
)

app = BUNDLE(
    exe,
    name='YongPDF_text.app',
    icon=ensure_icns(os.path.join(root_dir, 'YongPDF_text_img.png'), mac_icon_path),
    bundle_identifier='com.yongpdf.editor',
)
