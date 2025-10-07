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
ghostscript_dir = os.path.join(root_dir, 'ghostscript')
mac_icon_path = os.path.join(root_dir, 'YongPDF_page_icon.icns')
external_app_dir = os.path.join(root_dir, 'external', 'YongPDF_text.app')

# Ensure macOS .icns exists (generate from PNG if necessary)
def ensure_icns(png_path: str, icns_path: str) -> str | None:
    if os.path.isfile(icns_path):
        return icns_path
    if not os.path.isfile(png_path):
        return None
    try:
        import shutil
        iconset_dir = os.path.join(root_dir, '_yongpdf_iconset')
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


datas_common = []
if os.path.isdir(static_dir):
    datas_common.append((static_dir, os.path.join('Contents', 'Resources', 'static')))

for image_name in ('YongPDF_page_img.png', 'YongPDF_text_img.png'):
    image_path = os.path.join(root_dir, image_name)
    if os.path.isfile(image_path):
        datas_common.append((image_path, os.path.join('Contents', 'Resources', 'static', image_name)))

if os.path.isdir(ghostscript_dir):
    datas_common.append((ghostscript_dir, 'ghostscript'))

if os.path.isdir(external_app_dir):
    datas_common.append((external_app_dir, os.path.join('Contents', 'Resources', 'external', 'YongPDF_text.app')))

runtime_hook = os.path.join(hooks_dir, 'rthook_change_wd.py') if os.path.isfile(os.path.join(hooks_dir, 'rthook_change_wd.py')) else None

a_main = Analysis(
    ['pdf_editor_v2.py'],
    pathex=[root_dir],
    binaries=[],
    datas=datas_common,
    hiddenimports=['fitz'],
    hookspath=[hooks_dir] if os.path.isdir(hooks_dir) else [],
    runtime_hooks=[runtime_hook] if runtime_hook else [],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz_main = PYZ(a_main.pure, a_main.zipped_data, cipher=block_cipher)

exe_main = EXE(
    pyz_main,
    a_main.scripts,
    a_main.binaries,
    a_main.zipfiles,
    a_main.datas,
    [],
    name='YongPDF',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    icon=ensure_icns(os.path.join(root_dir, 'YongPDF_page_img.png'), mac_icon_path),
)

app = BUNDLE(
    exe_main,
    name='YongPDF.app',
    icon=ensure_icns(os.path.join(root_dir, 'YongPDF_page_img.png'), mac_icon_path),
    bundle_identifier='com.yongpdf.viewer',
)
