# 📄 YongPDF_page (PDF Page Editor)

**YongPDF_page** is a professional tool designed for easy and intuitive management of PDF pages. Optimized for document structure editing—including reordering, rotating, adding, deleting, extracting, and compressing pages—it provides a seamless UI/UX through thumbnails, drag-and-drop, and right-click context menus.

---

## ✨ Key Features

### 1. Intuitive "Point & Click" Page Management
*   **Thumbnail View**: View the entire document structure at a glance with flexible resizing (window and page sizes).
*   **Drag-and-Drop Reordering**: Rearrange pages effortlessly by dragging thumbnails. (Supports adding new pages as well)
*   **Multi-Selection Support**: Select multiple pages to delete, move, or rotate via the right-click menu.

### 2. Essential Editing Tools
*   **Delete Page**: Easily remove unnecessary pages.
*   **Rotate Page**: Rotate pages 90 degrees left or right.
*   **Add Page**: Insert external PDF files directly by dragging them into the desired position.
*   **Save/Extract**: Select and save specific pages as a new, separate PDF file.

### 3. Advanced Features
*   **PDF Compression**: Powerful compression via Ghostscript (General structural optimization / Advanced DPI downsampling).
*   **YongPDF_text Integration**: Launch **YongPDF_text** directly from the page view to edit text content.
*   **Print Support**: Print your edited documents immediately from the app.

### 4. User Convenience
*   **Dark Mode**: Choose between a comfortable Dark theme and a clean Light theme.
*   **Multi-Language Support**: Full support for Korean, English, Japanese, and Chinese (Simplified/Traditional).
*   **Shortcut Support**: Optimize your workflow with comprehensive keyboard shortcuts.

---

## 🚀 Installation & Execution

*   **Single Package**: Run the standalone `YongPDF_page.exe` (or OS-specific binary) without any installation process.
*   **Portable Execution**: Distributed as a single executable containing all necessary libraries.

---

## ⌨️ Key Shortcuts

| Feature | Shortcut |
| :--- | :--- |
| **Open PDF** | `Ctrl + O` |
| **Save PDF** | `Ctrl + S` |
| **Add Page** | `Insert` |
| **Delete Page** | `Delete` |
| **Move Up** | `Ctrl + Shift + ↑` |
| **Move Down** | `Ctrl + Shift + ↓` |
| **Rotate Left** | `Ctrl + Shift + ←` |
| **Rotate Right** | `Ctrl + Shift + →` |
| **Undo / Redo** | `Ctrl + Z` / `Ctrl + Y` |
| **Zoom In / Out** | `Ctrl + +` / `Ctrl + -` |

---

## 🌐 Multi-Language Support
Currently supporting:
*   English
*   Korean (Default)
*   Japanese
*   Simplified Chinese / Traditional Chinese

---

## ❣️ Support the Developer
If this program has helped you, please consider supporting the developer through the **[❣️Support the Developer❣️]** menu. Your contributions are vital for maintenance and future feature development.

---

## ⚖️ Open Source Licenses
This application utilizes the following open source projects:

*   **PyMuPDF (MuPDF)**: AGPL-3.0
    *   https://pymupdf.readthedocs.io/ / https://mupdf.com/
*   **Pillow**: HPND / PIL License
    *   https://python-pillow.org/
*   **PyQt6**: GPLv3 / Commercial
    *   https://www.riverbankcomputing.com/software/pyqt/
*   **Ghostscript (optional)**: AGPL-3.0 / Commercial
    *   https://ghostscript.com/
*   **PySide6 (Qt for Python, external editor)**: LGPL-3.0 / Commercial
    *   https://www.qt.io/qt-for-python
*   **fontTools (external editor)**: MIT License
    *   https://github.com/fonttools/fonttools
*   **Matplotlib (external editor)**: PSF License
    *   https://matplotlib.org/
*   **Icons/Emojis**: as provided by system fonts.

---
**Copyright © 2026 YongPDF · Hwang Jinsu. All rights reserved.**

----------

# 📄 YongPDF_text (PDF Text Editor)

**YongPDF_text** is a professional PDF text editing tool that allows you to modify and reposition text with minimal disparity from the original. Specialized for PDFs converted from **Hancom Office (HWP)**, it provides seamless results through auto-detection of fonts/sizes and high-resolution flattening with background color matching.

---

## ✨ Key Features

### 1. Intuitive Usability
*   **Easy "Double-Click" Editing**: Double-click any text block to open the editor immediately.
*   **Property Auto-Detection**: Automatically detects and applies the original font and size. (Displays a guide if the font is missing).
*   **Patch & Eraser Modes**: Draw text with a background patch or use "Eraser Mode" to hide original text using a color-matched patch.

### 2. Advanced Editing Tools
*   **Precise Typography**: Adjust stretch (width) and tracking (kerning) similar to HWP for perfect alignment.
*   **Seamless Correction**: Like using "correction tape," it auto-detects background colors to create patches that blend perfectly with the original document.
*   **High Zoom Support**: Zoom up to **800%** for pixel-perfect adjustments.
*   **Session Management**: Save your work-in-progress layers as `.pdfses` files to resume editing later.

### 3. Precision Editing Experience
*   **Synthetic Bold Control**: Force-apply bold effects even when the font file lacks a bold variant (adjustable from 100% to 500% thickness).
*   **HWP Space Correction**: Detects and corrects the unique wide spaces (50% of a character width) found in HWP-converted PDFs.
*   **Micro-Positioning**: Fine-tune the position of selected text overlays using keyboard arrow keys.

### 4. Full WYSIWYG & High-Res Storage
*   **600 DPI Flattening**: Merges modifications into the PDF at 600 DPI for crystal-clear print quality.
*   **Perfect Alignment**: Ensures that text position, thickness, and spacing on the screen exactly match the final PDF output.

---

## 🚀 Installation & Execution

*   **Single Package**: Run `YongPDF_text.exe` instantly without installation.
*   **Portable**: A single executable containing all required dependencies.

---

## ⌨️ Key Shortcuts

| Feature | Shortcut |
| :--- | :--- |
| **Open PDF** | `Ctrl + O` |
| **Save PDF** | `Ctrl + S` |
| **Edit Text** | **Double-click** text block |
| **Fine Tuning** | **Arrow keys** (on selected overlay) |
| **Undo / Redo** | `Ctrl + Z` / `Ctrl + Y` |
| **Zoom In / Out** | `Ctrl + +` / `Ctrl + -` (or `Ctrl + Scroll`) |
| **Fit Width / Height** | `Ctrl + 0` / `Ctrl + Shift + 0` |

---

## 🌐 Multi-Language Support
Currently supporting English, Korean, Japanese, and Chinese (Simplified/Traditional).

---

## ❣️ Support the Developer
Contributions help us keep the project alive and improve features. Use the in-app donation menu to help out!

---

## ⚖️ Open Source Licenses
*   **PyMuPDF (MuPDF)** — AGPL-3.0
*   **PySide6 (Qt for Python)** — LGPL-3.0 / Commercial
*   **fontTools** — MIT License
*   **Matplotlib (font_manager)** — PSF License
*   **Icons/Emojis** — provided by system fonts.

---
**Copyright © 2026 YongPDF · Hwang Jinsu. All rights reserved.**