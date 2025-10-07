# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

_spec_file = globals().get('__file__')
if _spec_file:
    root_dir = os.path.abspath(os.path.dirname(_spec_file))
else:
    root_dir = os.path.abspath(os.getcwd())
hooks_dir = os.path.join(root_dir, 'hooks')
static_dir = os.path.join(root_dir, 'static')
ghostscript_dir = os.path.join(root_dir, 'ghostscript')
icon_path = os.path.join(root_dir, 'YongPDF_page_icon.ico')

datas_common = []
if os.path.isdir(static_dir):
    datas_common.append((static_dir, 'static'))

for image_name in ('YongPDF_page_img.png', 'YongPDF_text_img.png'):
    image_path = os.path.join(root_dir, image_name)
    if os.path.isfile(image_path):
        datas_common.append((image_path, 'static'))

# Bundle Ghostscript executables or directory if present so the runtime helper can deploy them
ghostscript_datas = []
if os.path.isdir(ghostscript_dir):
    ghostscript_datas.append((ghostscript_dir, 'ghostscript'))
else:
    for name in ('gswin64c.exe', 'gswin32c.exe', 'gswin64.exe', 'gswin32.exe', 'gs.exe', 'gs10060w32.exe', 'gs10060w64.exe'):
        candidate = os.path.join(root_dir, name)
        if os.path.isfile(candidate):
            ghostscript_datas.append((candidate, 'ghostscript'))

datas_common.extend(ghostscript_datas)

# --- Main viewer (PyQt6) ---
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
    icon=icon_path if os.path.isfile(icon_path) else None,
)

coll = COLLECT(
    exe_main,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='YongPDF',
)
