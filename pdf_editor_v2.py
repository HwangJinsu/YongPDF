import os
import sys
import tempfile
import traceback
import webbrowser
import urllib.request
import urllib.error
import urllib.parse
import re
import platform
import glob
import json
import uuid
import time
import ctypes
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
import fitz
import io
import subprocess
import shutil

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QMenu, QMenuBar,
    QStatusBar, QToolBar, QFileDialog, QDialog, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QMessageBox, QFrame, QLineEdit,
    QDialogButtonBox, QRubberBand, QSlider, QCheckBox, QProgressDialog, QRadioButton, QTextEdit, QProgressBar, QSplashScreen
)
from PyQt6.QtCore import Qt, QSize, QPoint, QRect, QEvent, QTimer, QItemSelectionModel, QItemSelection, QSettings, QFileSystemWatcher, QProcess
from PyQt6.QtGui import QImage, QPixmap, QIcon, QAction, QTextCursor, QPainter, QColor, QWheelEvent, QActionGroup, QKeySequence, QShortcut, QFont
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog


if sys.platform.startswith('win'):
    GS_FIXED_PATH = r"C:\\Program Files (x86)\\gs\\gs10.06.0\\bin\\gswin32c.exe"
else:
    GS_FIXED_PATH = None

TEXT_EDITOR_EXE_NAME = 'YongPDF_text.exe'
TEXT_EDITOR_STEM = 'YongPDF_text'
TEXT_EDITOR_APP_NAME = 'YongPDF_text.app'
TEXT_EDITOR_APP_BINARY = os.path.join('Contents', 'MacOS', 'YongPDF_text')
LEGACY_EDITOR_EXE_NAME = 'main_codex1.exe'
LEGACY_EDITOR_STEM = 'main_codex1'
TEXT_EDITOR_SCRIPT_NAME = 'main_codex1.py'

RESUME_STATE_PATH: Optional[str] = None
POST_INSTALL_STATE_PATH: Optional[str] = None
if '--resume-install' in sys.argv:
    try:
        idx = sys.argv.index('--resume-install')
        if idx + 1 < len(sys.argv):
            RESUME_STATE_PATH = sys.argv[idx + 1]
        del sys.argv[idx:idx + 2]
    except ValueError:
        RESUME_STATE_PATH = None
if '--post-install' in sys.argv:
    try:
        idx = sys.argv.index('--post-install')
        if idx + 1 < len(sys.argv):
            POST_INSTALL_STATE_PATH = sys.argv[idx + 1]
        del sys.argv[idx:idx + 2]
    except ValueError:
        POST_INSTALL_STATE_PATH = None


def _resolve_static_path(*relative_parts: str) -> str:
    """Return an absolute path to a file located under the static directory.

    Searches the source directory, the PyInstaller bundle directory, and any
    adjacent ``static`` folders so the resource is available in both
    development and packaged environments.
    """

    candidates: list[str] = []
    try:
        module_dir = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        module_dir = os.getcwd()

    bundle_dir = getattr(sys, '_MEIPASS', None)

    mac_resources = None
    if sys.platform == 'darwin':
        try:
            exec_dir = os.path.dirname(os.path.abspath(sys.executable))
            mac_resources = os.path.normpath(os.path.join(exec_dir, '..', 'Resources'))
        except Exception:
            mac_resources = None

    for root in (bundle_dir, module_dir, mac_resources):
        if not root:
            continue
        candidates.append(root)
        candidates.append(os.path.join(root, 'static'))

    seen: set[str] = set()
    for base in candidates:
        if not base:
            continue
        candidate = os.path.normpath(os.path.join(base, *relative_parts))
        if candidate in seen:
            continue
        seen.add(candidate)
        if os.path.exists(candidate):
            return candidate

    basename = relative_parts[-1] if relative_parts else ''
    if basename:
        searched: set[str] = set()
        for base in candidates:
            if not base or not os.path.isdir(base):
                continue
            base = os.path.abspath(base)
            if base in searched:
                continue
            searched.add(base)
            for root, _, files in os.walk(base):
                if basename in files:
                    return os.path.join(root, basename)

    # Fallback to module directory to avoid returning a non-existent bundle path
    return os.path.normpath(os.path.join(module_dir, *relative_parts))


def _load_static_pixmap(filename: str) -> Optional[QPixmap]:
    try:
        path = _resolve_static_path(filename)
    except Exception:
        path = filename

    pixmap = QPixmap()
    if path and os.path.exists(path):
        pixmap.load(path)
    if pixmap.isNull():
        return None
    return pixmap


def _build_splash_pixmap() -> Optional[QPixmap]:
    width, height = 448, 336  # 80% of the previous dimensions
    pixmap = QPixmap(width, height)
    if pixmap.isNull():
        return None

    pixmap.fill(QColor('#ffffff'))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    logo_path = _resolve_static_path('YongPDF_page_img.png')
    logo = QPixmap(logo_path)
    if not logo.isNull():
        target_size = min(int(220 * 0.8), width - 96)
        scaled = logo.scaled(
            target_size,
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        logo_x = (width - scaled.width()) // 2
        painter.drawPixmap(logo_x, 32, scaled)

    painter.setPen(QColor('#1a2740'))
    title_font = QFont('Arial', 17)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.drawText(QRect(0, 224, width, 28), Qt.AlignmentFlag.AlignHCenter, 'YongPDF')

    painter.setPen(QColor('#505050'))
    subtitle_font = QFont('Arial', 8)
    painter.setFont(subtitle_font)
    lines = [
        '빠르고 직관적인 PDF 페이지 편집기',
        '개발: Hwang Jinsu · 이메일: iiish@hanmail.net',
        '구성 요소를 초기화하는 동안 잠시만 기다려주세요...'
    ]
    top = 260
    for line in lines:
        painter.drawText(QRect(0, top, width, 18), Qt.AlignmentFlag.AlignHCenter, line)
        top += 21

    painter.setPen(QColor('#808080'))
    copyright_font = QFont('Arial', 7)
    painter.setFont(copyright_font)
    painter.drawText(
        QRect(0, height - 28, width, 18),
        Qt.AlignmentFlag.AlignHCenter,
        '© 2025 YongPDF · Hwang Jinsu. All rights reserved.'
    )

    painter.end()
    return pixmap


def _show_startup_splash(app: QApplication) -> Optional[QSplashScreen]:
    try:
        pixmap = _build_splash_pixmap()
    except Exception as splash_err:
        print(f"[Splash] Failed to build splash pixmap: {splash_err}")
        pixmap = None

    if pixmap is None or pixmap.isNull():
        return None

    splash = QSplashScreen(pixmap, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    splash.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    try:
        splash.setFont(QFont('Arial', 8))
    except Exception:
        pass
    splash.show()
    splash.raise_()
    splash.activateWindow()
    splash.showMessage(
        'PDF 모듈을 불러오는 중입니다...',
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        QColor(90, 90, 90)
    )
    app.processEvents()
    return splash

class ThumbnailWidget(QListWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(120, 169))
        self.setSpacing(15)
        self.setMovement(QListWidget.Movement.Static)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setWrapping(True)
        self.setUniformItemSizes(False) # 가변 크기 아이템 허용
        # Use uniform sizing and explicit grid to avoid paint glitches
        self.setUniformItemSizes(True)
        ic = self.iconSize()
        self.setGridSize(QSize(ic.width() + 24, ic.height() + 40))
        # Force full repaints to avoid stale partial updates
        try:
            from PyQt6.QtWidgets import QListView as _QListView
            self.setViewportUpdateMode(_QListView.ViewportUpdateMode.FullViewportUpdate)  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            self.setDragDropOverwriteMode(False)  # type: ignore[attr-defined]
        except Exception:
            pass

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        # Allow drags and drops; we handle drops ourselves
        self.setDragDropMode(QListWidget.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

        self._scroll_position = 0
        self._drag_rows: list[int] = []
        self.pages = []

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
        self.selectionModel().selectionChanged.connect(self.on_selection_changed)

        # Custom drop indicator (visible line)
        from PyQt6.QtWidgets import QFrame as _QFrame
        self._indicator = _QFrame(self.viewport())
        self._indicator.setStyleSheet("background: #0078d7;")
        self._indicator.setVisible(False)
        # Ensure we receive drag events delivered to viewport
        self.viewport().installEventFilter(self)

    def _linear_order(self):
        """Return list of (index, (cy, cx), rect) sorted by row-major (y then x)."""
        items = []
        for i in range(self.count()):
            it = self.item(i)
            r = self.visualItemRect(it)
            c = (r.center().y(), r.center().x())
            items.append((i, c, r))
        items.sort(key=lambda t: (t[1][0], t[1][1]))
        return items

    def _group_rows(self):
        """Group items into visual rows based on Y proximity."""
        items = self._linear_order()  # already sorted by y then x
        rows = []
        row = []
        ref_y = None
        tol = None
        for idx, (_, (cy, _), rect) in enumerate(items):
            if ref_y is None:
                ref_y = cy
                tol = rect.height() * 0.6
                row = [(items[idx][0], items[idx][2])]
            else:
                if abs(cy - ref_y) <= tol:
                    row.append((items[idx][0], items[idx][2]))
                    # update ref_y softly
                    ref_y = (ref_y * (len(row) - 1) + cy) / len(row)
                else:
                    # start new row
                    rows.append(sorted(row, key=lambda t: t[1].left()))
                    ref_y = cy
                    tol = items[idx][2].height() * 0.6
                    row = [(items[idx][0], items[idx][2])]
        if row:
            rows.append(sorted(row, key=lambda t: t[1].left()))
        return rows

    def _compute_dest_row(self, pos: QPoint) -> int:
        """Map a viewport pos to insertion index using actual item edges (gaps only)."""
        rows = self._group_rows()
        if not rows:
            return 0
        py, px = pos.y(), pos.x()
        # Choose row by edges, not midpoints (tighter tolerance)
        row_idx = None
        for i, row in enumerate(rows):
            top = min(r.top() for _, r in row)
            bot = max(r.bottom() for _, r in row)
            if py < top:
                row_idx = i
                break
            if top <= py <= bot:
                row_idx = i
                break
        if row_idx is None:
            row_idx = len(rows)
        linear_before = sum(len(r) for r in rows[:min(row_idx, len(rows))])
        if row_idx >= len(rows):
            return linear_before
        row = rows[row_idx]
        # Column based on actual gaps only
        if px <= row[0][1].left():
            return linear_before
        for i in range(len(row) - 1):
            left_r = row[i][1]
            right_r = row[i + 1][1]
            if left_r.right() <= px <= right_r.left():
                # within gap strictly -> between i and i+1
                return linear_before + i + 1
            if px < left_r.right():
                # still inside left item -> before boundary
                return linear_before + i
        # after last
        last_r = row[-1][1]
        if px < last_r.right():
            return linear_before + len(row) - 1
        return linear_before + len(row)

    def _draw_indicator(self, dest_index: int):
        rows = self._group_rows()
        if not rows:
            self._indicator.setVisible(False)
            return
        total = sum(len(r) for r in rows)
        if dest_index <= 0:
            r0 = rows[0][0][1]
            x = r0.left()
            y1 = min(rr[1].top() for rr in rows[0])
            y2 = max(rr[1].bottom() for rr in rows[0])
            self._indicator.setGeometry(x - 1, y1, 3, y2 - y1)
            self._indicator.setVisible(True)
            return
        if dest_index >= total:
            rN = rows[-1][-1][1]
            x = rN.right()
            y1 = min(rr[1].top() for rr in rows[-1])
            y2 = max(rr[1].bottom() for rr in rows[-1])
            self._indicator.setGeometry(x - 1, y1, 3, y2 - y1)
            self._indicator.setVisible(True)
            return
        # Find row and column for dest_index
        count = 0
        row_idx = 0
        while row_idx < len(rows) and count + len(rows[row_idx]) < dest_index:
            count += len(rows[row_idx])
            row_idx += 1
        col = dest_index - count
        row = rows[row_idx]
        y1 = min(rr[1].top() for rr in row)
        y2 = max(rr[1].bottom() for rr in row)
        if col == 0:
            x = row[0][1].left()
        elif col >= len(row):
            x = row[-1][1].right()
        else:
            x = (row[col - 1][1].right() + row[col][1].left()) // 2
        self._indicator.setGeometry(x - 1, y1, 3, y2 - y1)
        self._indicator.setVisible(True)

    def apply_new_order_to_view(self, new_order: list[int]):
        """Reorder QListWidget items in-place to match new page order without rebuilding icons.
        new_order is a list of old indices in their new order.
        """
        count = self.count()
        if count != len(new_order):
            return
        self.setUpdatesEnabled(False)
        # Take all items
        old_items = [self.takeItem(0) for _ in range(count)]
        # Reinsert in new order
        for idx in new_order:
            self.addItem(old_items[idx])
        # Update labels to reflect 1-based page numbers
        for i in range(self.count()):
            it = self.item(i)
            if it:
                it.setText(f"Page {i + 1}")
        self.setUpdatesEnabled(True)
        self.doItemsLayout()
        self.viewport().update()
        self.repaint()

    def on_selection_changed(self, selected, deselected):
        if getattr(self.editor, '_suppress_scroll_sync', False):
            return
        selected_indexes = self.get_selected_indexes()
        if len(selected_indexes) == 1:
            self.editor.scroll_to_page(selected_indexes[0])

    def save_scroll_position(self):
        self._scroll_position = self.verticalScrollBar().value()

    def restore_scroll_position(self):
        self.verticalScrollBar().setValue(self._scroll_position)

    def add_thumbnail(self, pixmap, page_num):
        # Use native icon/text rendering for robustness
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, page_num)
        item.setIcon(QIcon(pixmap))
        item.setText(f"Page {page_num + 1}")
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
        # Ensure predictable footprint to avoid partial paints
        ic = self.iconSize()
        item.setSizeHint(QSize(ic.width() + 24, ic.height() + 32))
        self.addItem(item)


    def show_context_menu(self, position):
        selected_items = self.selectedItems()
        if not selected_items:
            return

        menu = QMenu(self)
        t = self.editor.t if hasattr(self.editor,'t') else (lambda k:k)
        move_up = QAction(t('move_up'), self)
        move_down = QAction(t('move_down'), self)
        add_page = QAction(t('add_page'), self)
        delete_pages = QAction(t('cm_delete_selected') if t('cm_delete_selected')!='cm_delete_selected' else "🗑️ Delete Selected Pages", self)
        rotate_left = QAction(t('rotate_left'), self)
        rotate_right = QAction(t('rotate_right'), self)
        save_page = QAction(t('cm_save_selected') if t('cm_save_selected')!='cm_save_selected' else "💾 Save Selected Pages", self)

        menu.addActions([add_page, delete_pages])
        menu.addSeparator()
        menu.addActions([move_up, move_down])
        menu.addSeparator()
        menu.addActions([rotate_left, rotate_right])
        menu.addSeparator()
        menu.addAction(save_page)

        action = menu.exec(self.mapToGlobal(position))
        if not action:
            return

        selected_indexes = self.get_selected_indexes()
        if action == move_up:
            self.editor.move_pages_up(selected_indexes)
        elif action == move_down:
            self.editor.move_pages_down(selected_indexes)
        elif action == add_page:
            self.editor.add_blank_page()
        elif action == delete_pages:
            self.editor.delete_pages(selected_indexes)
        elif action == rotate_left:
            self.editor.rotate_pages(selected_indexes, -90)
        elif action == rotate_right:
            self.editor.rotate_pages(selected_indexes, 90)
        elif action == save_page:
            self.editor.save_pages_as_file(selected_indexes)

    def dropEvent(self, event):
        # Prefer rows captured at dragEnter to avoid selection churn
        source_rows = getattr(self, '_drag_rows', [])
        if not source_rows:
            source_items = self.selectedItems()
            if not source_items:
                event.ignore()
                return
            source_rows = sorted([self.row(item) for item in source_items])
        # Reset drag rows snapshot
        self._drag_rows = []

        pos = event.position().toPoint()
        dest_row = self._compute_dest_row(pos)

        # ignore drop within the dragged block range (no-op) — allow exactly after block
        if source_rows[0] <= dest_row <= source_rows[-1]:
            event.ignore()
            return

        self._indicator.setVisible(False)
        # Reorder on next tick to let view exit drag state before we rebuild
        QTimer.singleShot(0, lambda sr=source_rows, dr=dest_row: self.editor.reorder_pages(sr, dr))
        event.setDropAction(Qt.DropAction.MoveAction)
        event.acceptProposedAction()

    def dragEnterEvent(self, event):
        # Snapshot current selection rows to ensure stability during DnD
        self._drag_rows = sorted([self.row(item) for item in self.selectedItems()])
        event.setDropAction(Qt.DropAction.MoveAction)
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.setDropAction(Qt.DropAction.MoveAction)
        event.acceptProposedAction()
        # Show indicator aligned with computed destination
        pos = event.position().toPoint()
        dest = self._compute_dest_row(pos)
        self._draw_indicator(dest)

    def dragLeaveEvent(self, event):
        self._indicator.setVisible(False)

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def eventFilter(self, obj, event):
        if obj is self.viewport():
            if event.type() == QEvent.Type.DragEnter:
                self.dragEnterEvent(event)
                return True
            if event.type() == QEvent.Type.DragMove:
                self.dragMoveEvent(event)
                return True
            if event.type() == QEvent.Type.Drop:
                self.dropEvent(event)
                return True
        return super().eventFilter(obj, event)

    def get_selected_indexes(self):
        sel = [self.row(item) for item in self.selectedItems()]
        if sel:
            return sel
        # 선택이 없으면 현재 페이지를 기본으로 사용
        if self.editor and self.editor.pdf_document:
            return [self.editor.current_page]
        return []

    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            current_value = self.editor.thumbnail_zoom_slider.value()
            if delta > 0:
                self.editor.thumbnail_zoom_slider.setValue(current_value + 10)
            else:
                self.editor.thumbnail_zoom_slider.setValue(current_value - 10)
            event.accept()
        else:
            super().wheelEvent(event)


class PDFScrollArea(QScrollArea):
    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    
    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.editor.zoom_in()
            else:
                self.editor.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)

class PDFPageLabel(QLabel):
    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setMouseTracking(True)

    def contextMenuEvent(self, event):
        # Determine this page index in the document view
        try:
            page_idx = self.editor.page_labels.index(self)
        except ValueError:
            page_idx = self.editor.current_page
        self.editor.current_page = page_idx
        t = self.editor.t if hasattr(self.editor, 't') else (lambda k: k)
        menu = QMenu(self)
        act_add = QAction(t('add_page'), self)
        act_del = QAction(t('delete_page'), self)
        act_up = QAction(t('move_up'), self)
        act_down = QAction(t('move_down'), self)
        act_rl = QAction(t('rotate_left'), self)
        act_rr = QAction(t('rotate_right'), self)
        act_save = QAction(t('cm_save_selected') if t('cm_save_selected') != 'cm_save_selected' else '💾 Save Selected Pages', self)
        menu.addActions([act_add, act_del])
        menu.addSeparator()
        menu.addActions([act_up, act_down])
        menu.addSeparator()
        menu.addActions([act_rl, act_rr])
        menu.addSeparator()
        menu.addAction(act_save)
        a = menu.exec(event.globalPos())
        if not a:
            return
        if a == act_add:
            self.editor.add_blank_page()
        elif a == act_del:
            self.editor.delete_pages([page_idx])
        elif a == act_up:
            self.editor.move_pages_up([page_idx])
        elif a == act_down:
            self.editor.move_pages_down([page_idx])
        elif a == act_rl:
            self.editor.rotate_pages([page_idx], -90)
        elif a == act_rr:
            self.editor.rotate_pages([page_idx], 90)
        elif a == act_save:
            self.editor.save_pages_as_file([page_idx])

class PDFCompressionDialog(QDialog):
    def __init__(self, parent=None, source_path: str | None = None, editor=None):
        super().__init__(parent)
        self.editor = editor if editor is not None else parent
        self._t = (self.editor.t if hasattr(self.editor, 't') else (lambda k: k))
        self.setWindowTitle(self._t('compress_pdf'))
        self.setModal(True)
        self.source_path = source_path

        layout = QVBoxLayout(self)

        self.info_label = QLabel((self._t('info_compress') if self._t('info_compress') != 'info_compress' else "Choose compression mode.\n- General: structure optimization (lossless)\n- Advanced: downsample images (DPI)"))
        layout.addWidget(self.info_label)

        # 모드 선택
        self.general_radio = QRadioButton(self._t('general_compress'))
        self.advanced_radio = QRadioButton(self._t('advanced_compress'))
        self.advanced_radio.setChecked(True)
        layout.addWidget(self.general_radio)
        layout.addWidget(self.advanced_radio)

        # DPI 슬라이더 (10단계)
        self.dpi_values = [50, 72, 96, 120, 144, 168, 192, 216, 240, 300]
        self.dpi_slider = QSlider(Qt.Orientation.Horizontal)
        self.dpi_slider.setRange(0, len(self.dpi_values) - 1)
        self.dpi_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.dpi_slider.setTickInterval(1)
        self.dpi_slider.setValue(1)  # 기본 72 DPI
        layout.addWidget(QLabel(self._t('color_dpi_label')))
        layout.addWidget(self.dpi_slider)

        # 그레이스케일/모노 DPI
        self.gray_dpi_slider = QSlider(Qt.Orientation.Horizontal)
        self.gray_dpi_slider.setRange(0, len(self.dpi_values) - 1)
        self.gray_dpi_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.gray_dpi_slider.setTickInterval(1)
        self.gray_dpi_slider.setValue(1)
        layout.addWidget(QLabel(self._t('gray_dpi_label')))
        layout.addWidget(self.gray_dpi_slider)

        self.mono_dpi_slider = QSlider(Qt.Orientation.Horizontal)
        self.mono_dpi_slider.setRange(0, len(self.dpi_values) - 1)
        self.mono_dpi_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.mono_dpi_slider.setTickInterval(1)
        self.mono_dpi_slider.setValue(1)
        layout.addWidget(QLabel(self._t('mono_dpi_label')))
        layout.addWidget(self.mono_dpi_slider)

        # 텍스트/벡터 보존 체크
        self.preserve_vector_checkbox = QCheckBox(self._t('preserve_vector'))
        self.preserve_vector_checkbox.setChecked(True)
        layout.addWidget(self.preserve_vector_checkbox)

        # 예상 파일 크기 표시
        self.estimate_label = QLabel(self._t('estimate_prefix') + ": -")
        layout.addWidget(self.estimate_label)

        # 슬라이더 활성/비활성
        def on_mode_change():
            enabled = self.advanced_radio.isChecked()
            self.dpi_slider.setEnabled(enabled)
            self.gray_dpi_slider.setEnabled(enabled)
            self.mono_dpi_slider.setEnabled(enabled)
            self.preserve_vector_checkbox.setEnabled(enabled)
            self.update_estimate()
        self.general_radio.toggled.connect(on_mode_change)
        self.advanced_radio.toggled.connect(on_mode_change)

        # 슬라이더 값 변경 시 라벨 업데이트
        self.dpi_slider.valueChanged.connect(self.update_estimate)
        self.gray_dpi_slider.valueChanged.connect(self.update_estimate)
        self.mono_dpi_slider.valueChanged.connect(self.update_estimate)
        self.update_estimate()

        buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)
        layout.addWidget(buttonBox)

    def _format_size(self, size_bytes: int) -> str:
        units = ["B", "KB", "MB", "GB"]
        size = float(size_bytes)
        for u in units:
            if size < 1024 or u == units[-1]:
                return f"{size:.1f} {u}"
            size /= 1024
        return f"{size_bytes} B"

    def update_estimate(self):
        if not self.source_path or not os.path.isfile(self.source_path):
            # 파일 없으면 DPI 표시만
            dpi = self.dpi_values[self.dpi_slider.value()]
            self.estimate_label.setText(f"{self._t('selected_dpi')}: {dpi} ({self._t('estimate_unavailable')})")
            return
        original_size = os.path.getsize(self.source_path)
        dpi = self.dpi_values[self.dpi_slider.value()]
        if self.general_radio.isChecked():
            # 무손실 구조 최적화는 대략 5~20% 절감으로 보정
            est = int(original_size * 0.9)
            self.estimate_label.setText(
                f"{self._t('estimate_prefix')}: ~{self._format_size(est)} ({self._t('current')}: {self._format_size(original_size)})")
        else:
            # 간단한 휴리스틱: 이미지 지배 문서 기준 (min(color,gray,mono)/300)^2 비례
            gray_dpi = self.dpi_values[self.gray_dpi_slider.value()]
            mono_dpi = self.dpi_values[self.mono_dpi_slider.value()]
            min_dpi = min(dpi, gray_dpi, mono_dpi)
            scale = (min_dpi / 300.0) ** 2
            est = int(max(original_size * 0.15, original_size * scale))
            self.estimate_label.setText(
                f"{self._t('color')}: {dpi} / {self._t('gray')}: {gray_dpi} / {self._t('mono')}: {mono_dpi}  •  {self._t('estimate_prefix')}: ~{self._format_size(est)} ({self._t('current')}: {self._format_size(original_size)})")

    def get_settings(self):
        if self.general_radio.isChecked():
            return {'level': 'general'}
        else:
            return {
                'level': 'advanced',
                'dpi_color': self.dpi_values[self.dpi_slider.value()],
                'dpi_gray': self.dpi_values[self.gray_dpi_slider.value()],
                'dpi_mono': self.dpi_values[self.mono_dpi_slider.value()],
                'preserve_vector': self.preserve_vector_checkbox.isChecked()
            }

class PDFEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        if sys.platform.startswith('win'):
            self.app_name = "용PDF_page"
        else:
            self.app_name = "YongPDF_page"
        self.setWindowTitle(self.app_name)
        self.settings = QSettings('pdf-editor-pe', 'pdf-editor-v2')
        # language (ko/en/ja/zh-CN/zh-TW)
        self._init_language()
        # restore language from settings
        try:
            saved_lang = self.settings.value('language')
            if saved_lang:
                self.language = saved_lang
        except Exception:
            pass
        self.current_file = None
        self.pdf_document = None
        self.current_page = 0
        self.zoom_level = 1.0
        self.has_unsaved_changes = False
        self.page_labels = []
        self.status_page_label = QLabel()
        self.status_zoom_label = QLabel()
        # Simple pixmap caches
        self._thumb_cache: dict[tuple[int, int], QPixmap] = {}
        self._page_cache: dict[tuple[int, int], QPixmap] = {}
        # Undo/redo stacks (store PDF bytes)
        self._undo_stack: list[bytes] = []
        self._redo_stack: list[bytes] = []
        self._external_editor_process: QProcess | None = None
        self._pending_reopen_path: str | None = None
        self._external_previous_title: str | None = None
        self._ghostscript_inline_attempted = False
        self._startup_loader: Optional[QProgressDialog] = None
        self._external_loading_dialog: Optional[QProgressDialog] = None
        try:
            self.dual_page_view = bool(int(self.settings.value('dual_page_view', 0)))
        except Exception:
            self.dual_page_view = False
        try:
            self._cached_ghostscript_path: Optional[str] = self.settings.value('ghostscript_path', type=str)
        except Exception:
            self._cached_ghostscript_path = None
        # Scroll sync guard to prevent jumps during rerender
        self._suppress_scroll_sync = False

        self.setup_ui()
        self.update_page_info()
        QTimer.singleShot(0, self._show_startup_loading)
        # Restore theme and window/splitter state
        theme = self.settings.value('theme', 'dark')
        self.set_theme(theme)
        if theme == 'dark':
            self.dark_theme_action.setChecked(True)
        else:
            self.light_theme_action.setChecked(True)
        # Restore geometry
        geom = self.settings.value('geometry')
        if geom is not None:
            try:
                self.restoreGeometry(geom)
            except Exception:
                pass
        # Restore splitter sizes
        sizes = self.settings.value('splitter_sizes')
        if sizes:
            try:
                self.splitter.setSizes([int(x) for x in sizes])
            except Exception:
                pass

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        layout = QHBoxLayout(main_widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setStyleSheet("QSplitter::handle { background-color: #3d3d3d; width: 3px; }")

        thumbnail_container = QWidget()
        thumbnail_layout = QVBoxLayout(thumbnail_container)
        thumbnail_layout.setContentsMargins(5, 5, 5, 5)
        thumbnail_layout.setSpacing(5)
        
        self.thumbnail_widget = ThumbnailWidget(self)
        
        self.thumbnail_zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.thumbnail_zoom_slider.setRange(40, 250)
        initial_zoom = int(self.settings.value('thumbnail_zoom', 120))
        self.thumbnail_zoom_slider.setValue(initial_zoom)
        self.thumbnail_zoom_slider.valueChanged.connect(self.on_thumbnail_zoom_slider_changed)

        thumbnail_layout.addWidget(self.thumbnail_widget)
        thumbnail_layout.addWidget(self.thumbnail_zoom_slider)
        
        self.document_container = QWidget()
        self.document_container.setObjectName("documentContainer")
        self.document_layout = QVBoxLayout(self.document_container)
        self.document_layout.setContentsMargins(10, 10, 10, 10)
        self.document_layout.setSpacing(15)
        self.document_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.scroll_area = PDFScrollArea(self)
        self.scroll_area.setWidget(self.document_container)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        self.splitter.addWidget(thumbnail_container)
        self.splitter.addWidget(self.scroll_area)
        self.splitter.setSizes([200, 1000])

        layout.addWidget(self.splitter)
        
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.update_current_page_on_scroll)
        
        self.setup_menubar()
        self.setup_toolbar()
        self.setup_statusbar()

        # Ensure grid sizing matches current icon size on first load
        try:
            self.on_thumbnail_zoom_slider_changed(self.thumbnail_zoom_slider.value())
        except Exception:
            pass

        # Global navigation shortcuts
        QShortcut(QKeySequence("PgUp"), self, activated=self.prev_page)
        QShortcut(QKeySequence("PgDown"), self, activated=self.next_page)
        QShortcut(QKeySequence("Home"), self, activated=lambda: self.scroll_to_page(0))
        QShortcut(QKeySequence("End"), self, activated=lambda: self.scroll_to_page(self.pdf_document.page_count - 1) if self.pdf_document else None)
        
        self.setGeometry(100, 100, 1200, 800)

    def on_thumbnail_zoom_slider_changed(self, value: int):
        """썸네일 줌 슬라이더 값 변경 시 호출되는 슬롯"""
        # 아이콘 크기만 변경하고, load_thumbnails를 다시 호출하여 리렌더링
        self.thumbnail_widget.setIconSize(QSize(value, int(value * 1.414)))
        # keep grid in sync with icon size to prevent missing paints
        self.thumbnail_widget.setGridSize(QSize(value + 24, int(value * 1.414) + 40))
        # prevent cache growth across many widths
        self._thumb_cache.clear()
        self.load_thumbnails() 
        # 값 보존(QSettings)
        if hasattr(self, 'settings'):
            self.settings.setValue('thumbnail_zoom', value)

    def setup_menubar(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu(self.t('file_menu'))
        open_action = QAction(self.t('open'), self)
        open_action.triggered.connect(self.open_file)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        save_action = QAction(self.t('save'), self)
        save_action.triggered.connect(self.save_file)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_as_action = QAction(self.t('save_as'), self)
        save_as_action.triggered.connect(self.save_as_file)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.print_action = QAction(self.t('print'), self)
        self.print_action.triggered.connect(self.print_document)
        self.print_action.setShortcut(QKeySequence.StandardKey.Print)
        exit_action = QAction(self.t('exit'), self)
        exit_action.triggered.connect(self.close)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        file_menu.addActions([save_action, save_as_action, self.print_action])
        file_menu.addSeparator()
        file_menu.addAction(exit_action)
        
        page_menu = menubar.addMenu(self.t('page_menu'))
        add_page_action = QAction(self.t('add_page'), self)
        add_page_action.triggered.connect(self.add_blank_page)
        add_page_action.setShortcut(QKeySequence("Alt+Insert"))
        delete_page_action = QAction(self.t('delete_page'), self)
        delete_page_action.triggered.connect(lambda: self.delete_pages(self.thumbnail_widget.get_selected_indexes()))
        delete_page_action.setShortcut(QKeySequence.StandardKey.Delete)
        move_up_action = QAction(self.t('move_up'), self)
        move_up_action.triggered.connect(lambda: self.move_pages_up(self.thumbnail_widget.get_selected_indexes()))
        move_up_action.setShortcut(QKeySequence("Alt+Up"))
        move_down_action = QAction(self.t('move_down'), self)
        move_down_action.triggered.connect(lambda: self.move_pages_down(self.thumbnail_widget.get_selected_indexes()))
        move_down_action.setShortcut(QKeySequence("Alt+Down"))
        rotate_left_action = QAction(self.t('rotate_left'), self)
        rotate_left_action.triggered.connect(lambda: self.rotate_pages(self.thumbnail_widget.get_selected_indexes(), -90))
        rotate_left_action.setShortcut(QKeySequence("Alt+Left"))
        rotate_right_action = QAction(self.t('rotate_right'), self)
        rotate_right_action.triggered.connect(lambda: self.rotate_pages(self.thumbnail_widget.get_selected_indexes(), 90))
        rotate_right_action.setShortcut(QKeySequence("Alt+Right"))
        page_menu.addActions([add_page_action, delete_page_action])
        page_menu.addSeparator()
        page_menu.addActions([move_up_action, move_down_action])
        page_menu.addSeparator()
        page_menu.addActions([rotate_left_action, rotate_right_action])

         # Undo/Redo + external editor launcher
        edit_menu = menubar.addMenu(self.t('edit_menu'))
        undo_action_menu = QAction(self.t('undo'), self)
        undo_action_menu.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action_menu.triggered.connect(self.undo_action)
        redo_action_menu = QAction(self.t('redo'), self)
        redo_action_menu.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action_menu.triggered.connect(self.redo_action)
        edit_menu.addActions([undo_action_menu, redo_action_menu])

        view_menu = menubar.addMenu(self.t('view_menu'))
        theme_group = QActionGroup(self)
        self.light_theme_action = QAction(self.t('theme_light_mode'), self, checkable=True)
        self.light_theme_action.triggered.connect(lambda: self.set_theme('light'))
        self.dark_theme_action = QAction(self.t('theme_dark_mode'), self, checkable=True)
        self.dark_theme_action.triggered.connect(lambda: self.set_theme('dark'))
        theme_group.addAction(self.light_theme_action)
        theme_group.addAction(self.dark_theme_action)
        view_menu.addAction(self.light_theme_action)
        view_menu.addAction(self.dark_theme_action)
        view_menu.addSeparator()
        self.single_page_action = QAction(self.t('single_view'), self, checkable=True)
        self.dual_page_action = QAction(self.t('dual_view'), self, checkable=True)
        self.single_page_action.setChecked(not getattr(self, 'dual_page_view', False))
        self.dual_page_action.setChecked(getattr(self, 'dual_page_view', False))
        self.single_page_action.triggered.connect(lambda: self.set_page_view_mode('single'))
        self.dual_page_action.triggered.connect(lambda: self.set_page_view_mode('dual'))
        view_mode_group = QActionGroup(self)
        view_mode_group.setExclusive(True)
        view_mode_group.addAction(self.single_page_action)
        view_mode_group.addAction(self.dual_page_action)
        view_menu.addActions([self.single_page_action, self.dual_page_action])
        view_menu.addSeparator()
        self.fit_width_action = QAction(self.t('fit_width'), self)
        self.fit_width_action.setShortcut(QKeySequence("Ctrl+Shift+W"))
        self.fit_width_action.triggered.connect(self.fit_to_width)
        self.fit_height_action = QAction(self.t('fit_height'), self)
        self.fit_height_action.setShortcut(QKeySequence("Ctrl+Shift+H"))
        self.fit_height_action.triggered.connect(self.fit_to_height)
        view_menu.addActions([self.fit_width_action, self.fit_height_action])

        # Language menu (fixed labels per language)
        lang_menu = menubar.addMenu(self.t('language_menu'))
        lang_group = QActionGroup(self)
        def add_lang(code, label):
            act = QAction(label, self, checkable=True)
            lang_group.addAction(act)
            act.setChecked(self.language == code)
            act.triggered.connect(lambda checked=False, c=code: self.set_language(c))
            lang_menu.addAction(act)
        add_lang('ko', '한국어')
        add_lang('en', 'English')
        add_lang('ja', '日本語')
        add_lang('zh-CN', '简体中文')
        add_lang('zh-TW', '繁體中文')

        tools_menu = menubar.addMenu(self.t('tools_menu'))
        compress_action = QAction(self.t('compress_pdf'), self)
        compress_action.triggered.connect(self.show_compression_settings)
        launch_editor_action = QAction(self.t('edit_short'), self)
        launch_editor_action.triggered.connect(self.launch_external_editor)
        ghostscript_action = QAction(self.t('ghostscript_config'), self)
        ghostscript_action.triggered.connect(self.configure_ghostscript_path)
        tools_menu.addActions([compress_action, launch_editor_action, ghostscript_action])

        help_menu = menubar.addMenu(self.t('help_menu'))
        about_action = QAction(self.t('about'), self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)
        licenses_action = QAction(self.t('licenses_menu') if self.language!='en' else 'Open-Source Licenses', self)
        licenses_action.triggered.connect(self.show_licenses_dialog)
        help_menu.addAction(licenses_action)

    def setup_toolbar(self):
        self.toolbar = self.addToolBar("도구")
        toolbar = self.toolbar
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))
        
        undo_action = QAction(self.t('undo'), self)
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self.undo_action)
        redo_action = QAction(self.t('redo'), self)
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self.redo_action)

        open_btn = QAction(self.t('open'), self)
        open_btn.triggered.connect(self.open_file)
        save_btn = QAction(self.t('save'), self)
        save_btn.triggered.connect(self.save_file)
        zoom_in_btn = QAction(self.t('zoom_in'), self)
        zoom_in_btn.triggered.connect(self.zoom_in)
        zoom_out_btn = QAction(self.t('zoom_out'), self)
        zoom_out_btn.triggered.connect(self.zoom_out)
        prev_btn = QAction(self.t('prev'), self)
        prev_btn.triggered.connect(self.prev_page)
        next_btn = QAction(self.t('next'), self)
        next_btn.triggered.connect(self.next_page)
        add_page_btn = QAction(self.t('add_short'), self)
        add_page_btn.triggered.connect(self.add_blank_page)
        add_page_btn.setShortcut(QKeySequence("Insert"))
        delete_page_btn = QAction(self.t('delete_short'), self)
        delete_page_btn.triggered.connect(lambda: self.delete_pages(self.thumbnail_widget.get_selected_indexes()))
        move_page_up_btn = QAction(self.t('move_up_short'), self)
        move_page_up_btn.triggered.connect(lambda: self.move_pages_up(self.thumbnail_widget.get_selected_indexes()))
        move_page_down_btn = QAction(self.t('move_down_short'), self)
        move_page_down_btn.triggered.connect(lambda: self.move_pages_down(self.thumbnail_widget.get_selected_indexes()))
        rotate_left_btn = QAction(self.t('rotate_left_short'), self)
        rotate_left_btn.triggered.connect(lambda: self.rotate_pages(self.thumbnail_widget.get_selected_indexes(), -90))
        rotate_left_btn.setShortcut(QKeySequence("Alt+Left"))
        rotate_right_btn = QAction(self.t('rotate_right_short'), self)
        rotate_right_btn.triggered.connect(lambda: self.rotate_pages(self.thumbnail_widget.get_selected_indexes(), 90))
        rotate_right_btn.setShortcut(QKeySequence("Alt+Right"))
        compress_action = QAction(self.t('compress_pdf'), self)
        compress_action.triggered.connect(self.show_compression_settings)
        edit_btn = QAction(self.t('edit_short'), self)
        edit_btn.triggered.connect(self.launch_external_editor)

        # Theme toggle buttons (toolbar)
        theme_group_tb = QActionGroup(self)
        theme_group_tb.setExclusive(True)
        self.theme_light_btn = QAction(self.t('theme_light'), self)
        self.theme_light_btn.setCheckable(True)
        self.theme_light_btn.triggered.connect(lambda: self.set_theme('light'))
        self.theme_dark_btn = QAction(self.t('theme_dark'), self)
        self.theme_dark_btn.setCheckable(True)
        self.theme_dark_btn.triggered.connect(lambda: self.set_theme('dark'))
        theme_group_tb.addAction(self.theme_light_btn)
        theme_group_tb.addAction(self.theme_dark_btn)

        # Order: Open/Save -> Undo/Redo -> Prev/Input/Next -> Zoom -> Others -> Theme
        toolbar.addActions([open_btn, save_btn])
        toolbar.addSeparator()
        toolbar.addActions([undo_action, redo_action])
        toolbar.addSeparator()
        # Move zoom after prev/next as requested
        toolbar.addActions([prev_btn])
        self.page_input = QLineEdit()
        self.page_input.setFixedWidth(50)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.returnPressed.connect(self.goto_page)
        toolbar.addWidget(self.page_input)
        self.total_pages_label = QLabel("/0")
        toolbar.addWidget(self.total_pages_label)
        toolbar.addActions([next_btn])
        toolbar.addSeparator()
        toolbar.addActions([zoom_in_btn, zoom_out_btn])
        toolbar.addActions([self.fit_width_action, self.fit_height_action])
        toolbar.addSeparator()
        toolbar.addActions([self.single_page_action, self.dual_page_action])
        toolbar.addSeparator()
        toolbar.addActions([add_page_btn, delete_page_btn])
        toolbar.addSeparator()
        toolbar.addActions([move_page_up_btn, move_page_down_btn])
        toolbar.addSeparator()
        toolbar.addActions([rotate_left_btn, rotate_right_btn])
        toolbar.addSeparator()
        toolbar.addActions([compress_action, edit_btn])
        toolbar.addSeparator()
        toolbar.addActions([self.theme_light_btn, self.theme_dark_btn])
        
    def setup_statusbar(self):
        statusbar = self.statusBar()
        if hasattr(self, '_statusbar_widgets'):
            for widget in self._statusbar_widgets:
                try:
                    statusbar.removeWidget(widget)
                except Exception:
                    pass
        self._statusbar_widgets: list[QWidget] = []
        statusbar.addWidget(self.status_page_label)
        statusbar.addPermanentWidget(self.status_zoom_label)
        self._statusbar_widgets.extend([self.status_page_label, self.status_zoom_label])
        if not hasattr(self, 'status_progress'):
            self.status_progress = QProgressBar()
            self.status_progress.setMaximumWidth(120)
            self.status_progress.setTextVisible(False)
            self.status_progress.setVisible(False)
        statusbar.addPermanentWidget(self.status_progress)
        self._statusbar_widgets.append(self.status_progress)
        self.show_status(self.t('status_ready'))

    def show_status(self, message: str, busy: bool = False, duration: int = 3000):
        if busy:
            self.statusBar().showMessage(message)
            if hasattr(self, 'status_progress'):
                self.status_progress.setRange(0, 0)
                self.status_progress.setVisible(True)
        else:
            self.statusBar().showMessage(message, duration)
            if hasattr(self, 'status_progress'):
                self.status_progress.setRange(0, 1)
                self.status_progress.setVisible(False)

    def clear_status(self):
        self.statusBar().clearMessage()
        if hasattr(self, 'status_progress'):
            self.status_progress.setVisible(False)
        try:
            self.statusBar().showMessage(self.t('status_ready'), 2000)
        except Exception:
            pass

    def _create_loading_dialog(self, message: str, modal: bool = True) -> QProgressDialog:
        dlg = QProgressDialog(message, None, 0, 0, self)
        dlg.setWindowTitle(self.app_name)
        dlg.setRange(0, 0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.setMinimumWidth(280)
        dlg.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        dlg.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        if modal:
            dlg.setWindowModality(Qt.WindowModality.WindowModal)
        else:
            dlg.setWindowModality(Qt.WindowModality.NonModal)
        return dlg

    def _show_startup_loading(self):
        if self._startup_loader:
            return
        dlg = self._create_loading_dialog(self.t('loading_app'), modal=False)
        self._startup_loader = dlg
        dlg.show()
        QApplication.processEvents()
        QTimer.singleShot(1400, self._close_startup_loading)

    def _close_startup_loading(self):
        if self._startup_loader:
            try:
                self._startup_loader.close()
            except Exception:
                pass
            self._startup_loader = None

    def _show_external_loading_dialog(self):
        self._close_external_loading_dialog()
        dlg = self._create_loading_dialog(self.t('loading_external_editor'))
        self._external_loading_dialog = dlg
        dlg.show()
        QApplication.processEvents()

    def _close_external_loading_dialog(self):
        if self._external_loading_dialog:
            try:
                self._external_loading_dialog.close()
            except Exception:
                pass
            self._external_loading_dialog = None

    def _handle_external_editor_started(self):
        self._close_external_loading_dialog()
        self.statusBar().showMessage(self.t('external_editor_ready'), 5000)

    def _get_dark_theme_stylesheet(self):
        return """
            QMainWindow, QDialog { background-color: #2b2b2b; color: #ffffff; }
            QMenuBar { font-size: 13px; padding: 3px 5px; background-color: #2b2b2b; color: #ffffff; }
            QMenuBar::item:selected { background-color: #3d3d3d; }
            QMenu { background-color: #2b2b2b; color: #ffffff; border: 1px solid #3d3d3d; }
            QMenu::item { padding: 8px 22px; }
            QMenu::item:selected { background-color: #3d3d3d; }
            QMenu::separator { height: 1px; background-color: #3d3d3d; margin: 5px 0px; }
            QToolBar { spacing: 4px; padding: 4px; background-color: #2b2b2b; border-bottom: 1px solid #3d3d3d; }
            QToolButton { color: #ffffff; padding: 5px 7px; border: 1px solid transparent; border-radius: 4px; font-size: 12px; }
            QToolButton:hover { background-color: #3d3d3d; }
            QToolButton:pressed, QToolButton:checked { background-color: #404040; }
            QStatusBar { padding-left: 8px; background: #2b2b2b; color: #ffffff; }
            QSplitter::handle {
                background-color: #3d3d3d;
                width: 3px;
            }
            #documentContainer {
                background-color: #1e1e1e;
            }
            QLabel { background-color: transparent; color: #ffffff; }
            QLineEdit { background-color: #1e1e1e; color: #ffffff; border: 1px solid #3d3d3d; }
            QPushButton, QDialogButtonBox QPushButton { background-color: #3d3d3d; color: #ffffff; border: none; padding: 5px 15px; border-radius: 3px; }
            QPushButton:hover, QDialogButtonBox QPushButton:hover { background-color: #4d4d4d; }
            QListWidget { background-color: #1e1e1e; border: none; outline: none; padding: 0px; }
            QListWidget::item { background-color: #2d2d2d; border: 1px solid #3d3d3d; margin: 2px; border-radius: 3px; color: #ffffff; }
            QListWidget::item:hover { background-color: rgba(0, 120, 215, 0.3); border: 1px solid #0078d7; }
            QListWidget::item:selected { background-color: rgba(0, 120, 215, 0.5); border: 1px solid #0078d7; }
            QCheckBox, QRadioButton { color: #ffffff; }
        """

    def _get_light_theme_stylesheet(self):
        return """
            QMainWindow, QDialog {
                background-color: #f0f0f0;
                color: #000000;
            }
            QMenuBar {
                font-size: 13px;
                padding: 3px 5px;
                background-color: #f0f0f0;
                color: #000000;
            }
            QMenuBar::item:selected {
                background-color: #dcdcdc;
            }
            QMenu {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
            }
            QMenu::item {
                padding: 8px 22px;
            }
            QMenu::item:selected {
                background-color: #0078d7;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #e0e0e0;
                margin: 5px 0px;
            }
            QToolBar {
                spacing: 4px;
                padding: 4px;
                background-color: #f0f0f0;
                border-bottom: 1px solid #cccccc;
            }
            QToolButton {
                color: #000000;
                padding: 5px 7px;
                border: 1px solid transparent;
                border-radius: 4px;
                font-size: 12px;
            }
            QToolButton:hover {
                background-color: #e0e0e0;
                border: 1px solid #cccccc;
            }
            QToolButton:pressed, QToolButton:checked {
                background-color: #c8c8c8;
                border: 1px solid #aaaaaa;
            }
            QStatusBar {
                padding-left: 8px;
                background: #f0f0f0;
                color: #000000;
            }
            QSplitter::handle {
                background-color: #cccccc;
                width: 3px;
            }
            #documentContainer {
                background-color: #ffffff;
            }
            QLabel {
                background-color: transparent;
                color: #000000;
            }
            QLineEdit {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
            }
            QPushButton, QDialogButtonBox QPushButton {
                background-color: #e0e0e0;
                color: #000000;
                border: 1px solid #cccccc;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover, QDialogButtonBox QPushButton:hover {
                background-color: #f0f0f0;
            }
            QListWidget {
                background-color: #f0f0f0;
                border: none;
                outline: none;
                padding: 0px;
            }
            QListWidget::item {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                margin: 2px;
                border-radius: 3px;
                color: #000000;
            }
            QListWidget::item:hover {
                background-color: #f0f8ff;
                border: 1px solid #0078d7;
            }
            QListWidget::item:selected {
                background-color: #e6f3ff;
                border: 1px solid #0078d7;
                color: #000000;
            }
            QCheckBox, QRadioButton {
                color: #000000;
            }
        """

    def set_theme(self, theme):
        app = QApplication.instance()
        if theme == 'dark':
            app.setStyleSheet(self._get_dark_theme_stylesheet())
        else:  # 'light'
            app.setStyleSheet(self._get_light_theme_stylesheet())
        # Persist theme and keep actions in sync
        if hasattr(self, 'settings'):
            self.settings.setValue('theme', theme)
        if hasattr(self, 'light_theme_action') and hasattr(self, 'dark_theme_action'):
            if theme == 'dark':
                self.dark_theme_action.setChecked(True)
                self.light_theme_action.setChecked(False)
            else:
                self.light_theme_action.setChecked(True)
                self.dark_theme_action.setChecked(False)
        if hasattr(self, 'theme_light_btn') and hasattr(self, 'theme_dark_btn'):
            if theme == 'dark':
                self.theme_dark_btn.setChecked(True)
                self.theme_light_btn.setChecked(False)
            else:
                self.theme_light_btn.setChecked(True)
                self.theme_dark_btn.setChecked(False)

    def _init_language(self):
        self.language = 'ko'
        self.translations = {
            'ko': {
                'zoom_in': '➕ 확대',
                'zoom_out': '➖ 축소',
                'theme_light': '☀️ 라이트',
                'theme_dark': '🌙 다크',
                'theme_light_mode': '☀️ 라이트 모드',
                'theme_dark_mode': '🌙 다크 모드',
                'status_page': '페이지',
                'status_zoom': '배율',
                'status_ready': '준비됨',
                'status_saving': '저장 중...',
                'status_saved': '저장 완료',
                'status_reordering': '페이지 순서를 변경하는 중...',
                'status_reordered': '페이지 순서를 변경했습니다.',
                'status_rotating': '페이지를 회전하는 중...',
                'status_rotated': '페이지를 회전했습니다.',
                'status_printing': '인쇄 준비 중...',
                'status_print_done': '인쇄 명령을 보냈습니다.',
                'status_compressing': '압축 중...',
                'status_compress_done': '압축이 완료되었습니다.',
                'status_patch_mode_on': '🩹 패치 모드가 활성화되었습니다.',
                'status_patch_mode_off': '🩹 패치 모드가 해제되었습니다.',
                'status_patch_eraser_on': '🧽 지우개 모드가 활성화되었습니다.',
                'status_patch_eraser_off': '🧽 지우개 모드가 해제되었습니다.',
                'progress_compress': 'PDF 압축 중...',
                'progress_compress_adv': '고급 PDF 압축 중...',
                'progress_preparing_fonts': '고급 압축을 위한 글꼴을 준비하는 중입니다...',
                'progress_ensuring_fonts': '페이지 {page} 글꼴을 적용하는 중입니다...',
                'progress_applying_overlay': "페이지 {page} 오버레이 반영 중… '{text}'",
                'file_menu': '파일',
                'open': '📂 열기',
                'save': '💾 저장',
                'save_as': '📑 다른 이름으로 저장',
                'print': '🖨️ 인쇄',
                'exit': '🚪 종료',
                'alert_no_pdf': 'PDF 파일이 열려 있지 않습니다.',
                'alert_no_edit_pdf': '편집할 PDF 파일이 열려 있지 않습니다.',
                'page_menu': '페이지',
                'add_page': '🙏 페이지 추가',
                'delete_page': '🗑️ 페이지 삭제',
                'cm_delete_selected': '🗑️ 선택한 페이지 삭제',
                'cm_save_selected': '💾 선택한 페이지 별도 저장',
                'move_up': '👆 위로 이동',
                'move_down': '👇 아래로 이동',
                'rotate_left': '⤴️ 왼쪽으로 회전',
                'rotate_right': '⤵️ 오른쪽으로 회전',
                'view_menu': '보기',
                'single_view': '📄 한쪽 보기',
                'dual_view': '📖 두쪽 보기',
                'fit_width': '↔️ 가로 맞춤',
                'fit_height': '↕️ 세로 맞춤',
                'tools_menu': '도구',
                'compress_pdf': '📦 PDF 압축',
                'edit_menu': '편집',
                'undo': '↩️ 실행 취소',
                'redo': '↪️ 다시 실행',
                'language_menu': '언어',
                'korean': '한글',
                'english': 'English',
                'help_menu': '도움말', 'licenses_menu': '📜 오픈소스 라이선스', 'licenses_title': '오픈소스 라이선스',
                'about': 'ℹ️ 정보',
                'prev': '👈 이전',
                'next': '👉 다음',
                'add_short': '🙏 추가',
                'delete_short': '🗑️ 삭제',
                'move_up_short': '👆 위로',
                'move_down_short': '👇 아래로',
                'rotate_left_short': '⤴️ 왼쪽 회전',
                'rotate_right_short': '⤵️ 오른쪽 회전',
                'edit_short': '✏️ 편집',
                'about_text': '용PDF\n개발: Hwang Jinsu\n메일: iiish@hanmail.net\n라이선스: 프리웨어\n본 소프트웨어는 개인/업무용 무료 사용 가능합니다.',
                'info_compress': '압축 방식을 선택하세요.\n- 일반 압축: 구조 최적화 (무손실)\n- 고급 압축: 이미지 DPI 다운샘플',
                'ghostscript_config': '🛠️ Ghostscript 경로 설정',
                'ghostscript_prompt': 'Ghostscript가 설치되어 있지 않습니다. 지금 설치하시겠습니까?',
                'ghostscript_select': 'Ghostscript 실행 파일 선택',
                'ghostscript_set': 'Ghostscript 경로가 저장되었습니다.',
                'ghostscript_not_found': 'Ghostscript 실행 파일을 찾을 수 없습니다.',
                'ghostscript_install': '지금 설치',
                'ghostscript_install_proceed': '설치 진행',
                'ghostscript_install_cancel': '취소',
                'ghostscript_install_hint': 'Ghostscript 다운로드 페이지를 열었습니다. 설치 후 다시 시도해 주세요.',
                'ghostscript_install_notice_mac': "macOS에서 고급 PDF 압축을 사용하려면 Ghostscript가 필요합니다.\n'설치 진행'을 누르면 Homebrew로 'brew install ghostscript' 명령을 실행하여 설치를 시도합니다.\nHomebrew가 설치되어 있지 않다면 https://brew.sh 에서 먼저 설치해주세요.",
                'ghostscript_installing': '터미널에서 Ghostscript 설치 중입니다... ({manager})',
                'ghostscript_install_success': 'Ghostscript 설치가 완료되었습니다.',
                'ghostscript_install_failed': 'Ghostscript 설치에 실패했습니다.',
                'ghostscript_install_missing_pm': '자동 설치를 위한 패키지 관리자를 찾을 수 없습니다. 직접 설치해주세요.',
                'ghostscript_install_missing_mac': "Homebrew를 찾을 수 없습니다. https://brew.sh 에서 Homebrew를 설치한 뒤 터미널에서 'brew install ghostscript'를 실행해주세요.",
                'ghostscript_install_manual': '자동 설치를 사용할 수 없어 Ghostscript 다운로드 페이지를 열었습니다. 설치 후 다시 시도해주세요.',
                'ghostscript_install_check_path': '설치가 완료된 것 같지만 실행 파일을 찾지 못했습니다. 경로를 직접 지정해주세요.',
                'ghostscript_bundle_ready': '번들에 포함된 Ghostscript 실행 파일을 사용할 준비가 되었습니다.',
                'ghostscript_program_files_missing': 'Windows Program Files 경로를 찾지 못했습니다. 관리자 권한으로 다시 실행한 뒤 시도해 주세요.',
                'ghostscript_local_installing': '번들 Ghostscript를 준비하는 중입니다...',
                'ghostscript_local_install_done': '번들 Ghostscript 경로가 설정되었습니다.',
                'ghostscript_local_install_failed': '번들 Ghostscript 설치에 실패했습니다.',
                'ghostscript_resume_title': 'Ghostscript 설치 완료',
                'ghostscript_resume_prompt': "Ghostscript 설치가 완료되었습니다.\n이전 설정으로 고급 PDF 압축을 다시 진행할까요?\n\n출력 파일: {output}\n컬러 DPI: {dpi_color} / 그레이 DPI: {dpi_gray} / 모노 DPI: {dpi_mono}\n텍스트/벡터 보존: {preserve_vector}",
                'ghostscript_resume_failed': "Ghostscript 설치에 실패했습니다.\n관리자 권한으로 앱을 다시 실행한 후 시도해주세요.\n\n오류: {error}",
                'ghostscript_program_files_missing': 'Windows Program Files 경로를 찾지 못했습니다. 관리자 권한으로 다시 실행한 뒤 시도해 주세요.',
                'loading_app': '용PDF를 준비하는 중입니다...',
                'loading_external_editor': '외부 편집기를 실행하는 중입니다...',
                'external_editor_ready': '외부 편집기를 열었습니다.',
                'external_editor_running': '외부 편집기가 이미 실행 중입니다.',
                'external_editor_refresh_notice': '외부 편집 저장을 감지하여 문서를 새로고침했습니다.',
                'print_error': '인쇄 중 오류가 발생했습니다.',
                'compress_adv_done': '고급 PDF 압축 완료',
                'compress_adv_error': '고급 PDF 압축 중 오류가 발생했습니다.',
                'compress_adv_permission_error': "Ghostscript 설치에는 관리자 권한 승인이 필요합니다.\n'설치 진행'을 눌러 설치를 완료하면 압축이 자동으로 이어집니다.",
                'ghostscript_install_notice': "고급 PDF 압축을 계속하려면 Ghostscript 설치가 필요합니다.\n'설치 진행'을 누르면 앱이 관리자 권한으로 다시 실행되며 Ghostscript를 자동으로 설치한 뒤, 열려 있던 문서와 압축 작업을 이어갑니다.\n지금 설치를 진행할까요?",
                'ghostscript_install_proceed': '설치 진행',
                'ghostscript_install_cancel': '취소',
                'ghostscript_install_already': 'Ghostscript가 이미 사용 가능한 상태입니다.',
                'progress_compress': 'PDF 압축 중...',
                'progress_compress_adv': '고급 PDF 압축 중...',
                'progress_preparing_fonts': '고급 압축에 필요한 글꼴을 준비하는 중입니다...',
                'progress_ensuring_fonts': '페이지 {page} 글꼴을 적용하는 중입니다...',
                'progress_applying_overlay': "페이지 {page} 오버레이 반영 중… '{text}'",
                'save_permission_error': '현재 위치에 저장할 수 없습니다. 다른 위치에 저장해 주세요.',
                'save_failed': '파일을 저장하지 못했습니다.',
                'err_editor_missing': 'YongPDF_text (앱/실행파일) 또는 main_codex1.py를 찾을 수 없습니다.',
                'err_editor_launch': '외부 편집기를 실행하지 못했습니다.',
                'general_compress': '일반 압축 (무손실, 파일 구조 최적화)',
                'advanced_compress': '고급 압축 (이미지 DPI 조절)',
                'color_dpi_label': '컬러 이미지 DPI (10단계)',
                'gray_dpi_label': '그레이스케일 이미지 DPI',
                'mono_dpi_label': '모노(흑백) 이미지 DPI',
                'preserve_vector': '텍스트/벡터 보존 (이미지만 처리)',
                'estimate_prefix': '예상 파일 크기',
                'selected_dpi': '선택 DPI',
                'estimate_unavailable': '예상 크기 계산 불가',
                'current': '현재',
                'color': '컬러', 'gray': '그레이', 'mono': '모노',
                'saved': '저장됨', 'saved_as': '다른 이름으로 저장됨',
                'unsaved_changes': '수정사항이 있습니다. 저장하시겠습니까?',
                'btn_yes': '예', 'btn_save_as': '다른 이름으로 저장', 'btn_no': '아니오', 'btn_cancel': '취소'
            },
            'en': {
                'zoom_in': '➕ Zoom In',
                'zoom_out': '➖ Zoom Out',
                'theme_light': '☀️ Light',
                'theme_dark': '🌙 Dark',
                'theme_light_mode': '☀️ Light Mode',
                'theme_dark_mode': '🌙 Dark Mode',
                'status_page': 'Page',
                'status_zoom': 'Zoom',
                'status_ready': 'Ready',
                'status_saving': 'Saving...',
                'status_saved': 'Save completed',
                'status_reordering': 'Reordering pages...',
                'status_reordered': 'Pages reordered.',
                'status_rotating': 'Rotating pages...',
                'status_rotated': 'Pages rotated.',
                'status_printing': 'Preparing print job...',
                'status_print_done': 'Print job sent.',
                'status_compressing': 'Compressing...',
                'status_compress_done': 'Compression finished.',
                'status_patch_mode_on': '🩹 Patch mode enabled.',
                'status_patch_mode_off': '🩹 Patch mode disabled.',
                'status_patch_eraser_on': '🧽 Eraser mode enabled.',
                'status_patch_eraser_off': '🧽 Eraser mode disabled.',
                'unsaved_changes': 'There are unsaved changes. Save?',
                'file_menu': 'File',
                'open': '📂 Open',
                'save': '💾 Save',
                'save_as': '📑 Save As',
                'print': '🖨️ Print',
                'exit': '🚪 Exit',
                'page_menu': 'Pages',
                'add_page': '🙏 Add Page',
                'delete_page': '🗑️ Delete Page',
                'cm_delete_selected': '🗑️ Delete Selected Pages',
                'cm_save_selected': '💾 Save Selected Pages',
                'move_up': '👆 Move Up',
                'move_down': '👇 Move Down',
                'rotate_left': '⤴️ Rotate Left',
                'rotate_right': '⤵️ Rotate Right',
                'view_menu': 'View',
                'single_view': '📄 Single Page View',
                'dual_view': '📖 Two-Page View',
                'fit_width': '↔️ Fit Width',
                'fit_height': '↕️ Fit Height',
                'tools_menu': 'Tools',
                'compress_pdf': '📦 Compress PDF',
                'edit_menu': 'Edit',
                'undo': '↩️ Undo',
                'redo': '↪️ Redo',
                'language_menu': 'Language',
                'korean': 'Korean',
                'english': 'English',
                'help_menu': 'Help', 'licenses_menu': '📜 Open-Source Licenses', 'licenses_title': 'Open-Source Licenses',
                'about': 'ℹ️ About',
                'prev': '👈 Prev',
                'next': '👉 Next',
                'add_short': '🙏 Add',
                'delete_short': '🗑️ Delete',
                'move_up_short': '👆 Up',
                'move_down_short': '👇 Down',
                'rotate_left_short': '⤴️ Rotate Left',
                'rotate_right_short': '⤵️ Rotate Right',
                'edit_short': '✏️ Edit',
                'about_text': 'YongPDF\nDeveloper: Hwang Jinsu\nEmail: iiish@hanmail.net\nLicense: Freeware\nThis software is free for personal and work use.',
                'info_compress': 'Choose compression mode.\n- General: structure optimization (lossless)\n- Advanced: downsample images (DPI)',
                'alert_no_pdf': 'No PDF is open.',
                'ghostscript_config': '🛠️ Configure Ghostscript Path',
                'ghostscript_prompt': 'Ghostscript is missing. Install it now?',
                'ghostscript_select': 'Select Ghostscript Executable',
                'ghostscript_set': 'Ghostscript path saved.',
                'ghostscript_not_found': 'Ghostscript executable could not be found.',
                'ghostscript_install': 'Install Now',
                'ghostscript_install_proceed': 'Proceed with installation',
                'ghostscript_install_cancel': 'Cancel',
                'ghostscript_install_hint': 'Opened the Ghostscript download page. After installing, try again.',
                'ghostscript_install_notice_mac': "Ghostscript is required for advanced compression on macOS.\nSelecting 'Proceed' runs 'brew install ghostscript' via Homebrew.\nIf Homebrew is not installed, please install it first from https://brew.sh.",
                'ghostscript_installing': 'Installing Ghostscript via {manager}...',
                'ghostscript_install_success': 'Ghostscript installation completed.',
                'ghostscript_install_failed': 'Failed to install Ghostscript.',
                'ghostscript_install_missing_pm': 'No supported package manager found for automatic install. Please install Ghostscript manually.',
                'ghostscript_install_missing_mac': "Homebrew was not detected. Install it from https://brew.sh and then run 'brew install ghostscript' to add Ghostscript.",
                'ghostscript_install_manual': 'Automatic install is unavailable; opened the Ghostscript download page. Install it and try again.',
                'ghostscript_install_check_path': 'Installation seems complete, but the executable was not found. Please set the path manually.',
                'ghostscript_bundle_ready': 'Using the bundled Ghostscript executable.',
                'ghostscript_program_files_missing': 'Unable to locate the Windows Program Files directory. Please rerun YongPDF as administrator and try again.',
                'ghostscript_local_installing': 'Preparing bundled Ghostscript...',
                'ghostscript_local_install_done': 'Bundled Ghostscript is ready to use.',
                'ghostscript_local_install_failed': 'Failed to prepare bundled Ghostscript.',
                'ghostscript_resume_title': 'Ghostscript Ready',
                'ghostscript_resume_prompt': "Ghostscript installation is complete.\nResume the advanced PDF compression with your previous settings?\n\nOutput file: {output}\nColor DPI: {dpi_color} / Gray DPI: {dpi_gray} / Mono DPI: {dpi_mono}\nPreserve text/vector: {preserve_vector}",
                'ghostscript_resume_failed': "Ghostscript installation failed.\nPlease restart YongPDF with administrator rights and try again.\n\nError: {error}",
                'loading_app': 'Loading YongPDF...',
                'loading_external_editor': 'Launching the external editor...',
                'external_editor_ready': 'External editor started.',
                'external_editor_running': 'External editor is already running.',
                'external_editor_refresh_notice': 'Detected external edits and reloaded the document.',
                'print_error': 'An error occurred while printing.',
                'save_permission_error': 'Cannot write to the current location. Please save to another location.',
                'save_failed': 'Failed to save the file.',
                'general_compress': 'General (lossless, structure optimization)',
                'advanced_compress': 'Advanced (image DPI control)',
                'color_dpi_label': 'Color Image DPI (10 steps)',
                'gray_dpi_label': 'Grayscale Image DPI',
                'mono_dpi_label': 'Monochrome Image DPI',
                'preserve_vector': 'Preserve text/vector (images only)',
                'estimate_prefix': 'Estimated size',
                'selected_dpi': 'Selected DPI',
                'estimate_unavailable': 'estimation unavailable',
                'current': 'current',
                'color': 'Color', 'gray': 'Gray', 'mono': 'Mono',
                'saved': 'Saved', 'saved_as': 'Saved As',
                'btn_yes': 'Save', 'btn_save_as': 'Save As', 'btn_no': "Don't Save", 'btn_cancel': 'Cancel',
                'err_open_pdf': 'Failed to open PDF.',
                'err_restore': 'Error occurred while restoring.',
                'err_undo': 'Error occurred while undoing.',
                'err_redo': 'Error occurred while redoing.',
                'alert_no_edit_pdf': 'No PDF is open to edit.',
                'err_editor_missing': 'YongPDF_text (app/executable) or main_codex1.py not found.',
                'err_editor_launch': 'Failed to launch external editor',
                'progress_compress': 'Compressing PDF...',
                'progress_compress_adv': 'Advanced PDF compression...',
                'progress_preparing_fonts': 'Preparing fonts for advanced compression…',
                'progress_ensuring_fonts': 'Ensuring fonts on page {page}…',
                'progress_applying_overlay': "Applying overlay on page {page}… '{text}'",
                'compress_done': 'PDF compression completed',
                'compress_error': 'Error occurred during PDF compression',
                'compress_adv_done': 'Advanced PDF compression completed',
                'gs_missing': 'Ghostscript executable not found.\nInstall Ghostscript and add it to PATH.',
                'compress_adv_error': 'Error occurred during advanced PDF compression',
                'compress_adv_permission_error': "Ghostscript installation needs administrator approval.\nChoose 'Install now' to relaunch YongPDF with elevated rights so the install can finish and compression can resume.",
                'ghostscript_install_notice': "Advanced compression requires Ghostscript.\nSelecting 'Install now' will relaunch YongPDF with administrator rights, install Ghostscript automatically, then reopen your document and resume compression.\nContinue?",
                'ghostscript_install_already': 'Ghostscript is already available; no installation is required.',
            },
            'ja': {
                'alert_no_pdf': 'PDFが開かれていません。',
                'alert_no_edit_pdf': '編集するPDFが開かれていません。',
                'unsaved_changes': '未保存の変更があります。保存しますか？',
                'btn_yes': 'はい', 'btn_save_as': '名前を付けて保存', 'btn_no': 'いいえ', 'btn_cancel': 'キャンセル',
                'zoom_in': '➕ 拡大', 'zoom_out': '➖ 縮小',
                'theme_light': '☀️ ライト', 'theme_dark': '🌙 ダーク',
                'theme_light_mode': '☀️ ライトモード', 'theme_dark_mode': '🌙 ダークモード',
                'status_page': 'ページ', 'status_zoom': '倍率',
                'status_ready': '準備完了',
                'status_saving': '保存中...',
                'status_saved': '保存しました。',
                'status_reordering': 'ページの順序を変更しています...',
                'status_reordered': 'ページの順序を変更しました。',
                'status_rotating': 'ページを回転しています...',
                'status_rotated': 'ページを回転しました。',
                'status_printing': '印刷を準備しています...',
                'status_print_done': '印刷ジョブを送信しました。',
                'status_compressing': '圧縮中...',
                'status_compress_done': '圧縮が完了しました。',
                'status_patch_mode_on': '🩹 パッチモードを有効にしました。',
                'status_patch_mode_off': '🩹 パッチモードを無効にしました。',
                'status_patch_eraser_on': '🧽 消しゴムモードを有効にしました。',
                'status_patch_eraser_off': '🧽 消しゴムモードを無効にしました。',
                'progress_compress': 'PDF を圧縮しています...',
                'progress_compress_adv': '高度な PDF 圧縮を実行中...',
                'progress_preparing_fonts': '高度な圧縮用にフォントを準備しています...',
                'progress_ensuring_fonts': 'ページ {page} のフォントを適用中...',
                'progress_applying_overlay': "ページ {page} のオーバーレイを反映中…『{text}』",
                'file_menu': 'ファイル', 'open': '📂 開く', 'save': '💾 保存', 'save_as': '📑 名前を付けて保存', 'print': '🖨️ 印刷', 'exit': '🚪 終了',
                'page_menu': 'ページ', 'add_page': '🙏 ページ追加', 'delete_page': '🗑️ ページ削除', 'cm_delete_selected': '🗑️ 選択ページを削除', 'cm_save_selected': '💾 選択ページを保存',
                'move_up': '👆 上へ移動', 'move_down': '👇 下へ移動', 'rotate_left': '⤴️ 左回転', 'rotate_right': '⤵️ 右回転',
                'view_menu': '表示', 'single_view': '📄 1ページ表示', 'dual_view': '📖 2ページ表示', 'fit_width': '↔️ 幅を合わせる', 'fit_height': '↕️ 高さを合わせる',
                'tools_menu': 'ツール', 'compress_pdf': '📦 PDF圧縮',
                'edit_menu': '編集', 'undo': '↩️ 元に戻す', 'redo': '↪️ やり直し', 'language_menu': '言語', 'korean': '韓国語', 'english': '英語', 'help_menu': 'ヘルプ', 'licenses_menu': '📜 オープンソース ライセンス', 'licenses_title': 'オープンソース ライセンス', 'about': 'ℹ️ 情報',
                'prev': '👈 前へ', 'next': '👉 次へ', 'add_short': '🙏 追加', 'delete_short': '🗑️ 削除', 'move_up_short': '👆 上へ', 'move_down_short': '👇 下へ', 'rotate_left_short': '⤴️ 左回転', 'rotate_right_short': '⤵️ 右回転', 'edit_short': '✏️ 編集',
                'about_text': 'YongPDF\n開発者: Hwang Jinsu\nメール: iiish@hanmail.net\nライセンス: フリーウェア\n本ソフトは個人/業務利用とも無料です。',
                'info_compress': '圧縮モードを選択してください。\n- 一般: 構造最適化(ロスレス)\n- 高度: 画像をDPIでダウンサンプル', 'general_compress': '一般(ロスレス、構造最適化)', 'advanced_compress': '高度(画像DPI調整)',
                'color_dpi_label': 'カラー画像 DPI (10段階)', 'gray_dpi_label': 'グレースケール画像 DPI', 'mono_dpi_label': 'モノクロ画像 DPI', 'preserve_vector': 'テキスト/ベクターを保持(画像のみ処理)',
                'ghostscript_config': '🛠️ Ghostscript パス設定', 'ghostscript_prompt': 'Ghostscript がインストールされていません。今すぐインストールしますか？', 'ghostscript_select': 'Ghostscript 実行ファイルを選択', 'ghostscript_set': 'Ghostscript パスを保存しました。', 'ghostscript_not_found': 'Ghostscript 実行ファイルを見つけられませんでした。', 'ghostscript_install': '今すぐインストール', 'ghostscript_install_proceed': 'インストールを実行', 'ghostscript_install_cancel': 'キャンセル', 'ghostscript_install_hint': 'Ghostscript のダウンロードページを開きました。インストール後に再試行してください。', 'ghostscript_install_notice_mac': "macOS で高度な圧縮を行うには Ghostscript が必要です。\n『インストールを実行』を押すと Homebrew から『brew install ghostscript』コマンドを実行します。\nHomebrew が未導入の場合は https://brew.sh から先に導入してください。", 'print_error': '印刷中にエラーが発生しました。', 'compress_adv_done': '高度なPDF圧縮が完了しました。', 'compress_adv_error': '高度なPDF圧縮中にエラーが発生しました。', 'compress_adv_permission_error': "Ghostscript のインストールには管理者権限が必要です。\n『インストールを実行』を選択して再起動後の案内に従ってください。", 'save_permission_error': '現在の場所に保存できません。他の場所に保存してください。', 'save_failed': 'ファイルを保存できませんでした。', 'saved': '保存済み', 'saved_as': '別名で保存済み',
                'ghostscript_installing': 'ターミナルで Ghostscript をインストールしています... ({manager})',
                'ghostscript_install_success': 'Ghostscript のインストールが完了しました。',
                'ghostscript_install_failed': 'Ghostscript のインストールに失敗しました。',
                'ghostscript_install_missing_pm': '自動インストールに対応するパッケージマネージャーが見つかりません。手動でインストールしてください。', 'ghostscript_install_missing_mac': "Homebrew が見つかりません。https://brew.sh で Homebrew をインストールし、ターミナルで『brew install ghostscript』を実行してください。",
                'ghostscript_install_manual': '自動インストールが利用できないため、Ghostscript のダウンロードページを開きました。インストール後に再試行してください。',
                'ghostscript_install_check_path': 'インストールは完了したようですが、実行ファイルを検出できませんでした。パスを手動で設定してください。',
                'ghostscript_bundle_ready': '同梱の Ghostscript 実行ファイルを使用します。',
                'ghostscript_program_files_missing': 'Windows の Program Files ディレクトリを確認できません。管理者権限で再起動してからもう一度お試しください。',
                'ghostscript_local_installing': '同梱の Ghostscript を準備しています...',
                'ghostscript_local_install_done': '同梱の Ghostscript を利用できるようにしました。',
                'ghostscript_local_install_failed': '同梱の Ghostscript を準備できませんでした。',
                'ghostscript_resume_title': 'Ghostscript の準備完了',
                'ghostscript_resume_prompt': "Ghostscript のインストールが完了しました。\n前回の設定で高度な PDF 圧縮を続行しますか？\n\n出力ファイル: {output}\nカラー DPI: {dpi_color} / グレー DPI: {dpi_gray} / モノクロ DPI: {dpi_mono}\nテキスト/ベクター保持: {preserve_vector}",
                'ghostscript_resume_failed': "Ghostscript のインストールに失敗しました。\n管理者権限で YongPDF を再起動してから再試行してください。\n\nエラー: {error}",
                'ghostscript_install_notice': '高度な圧縮には Ghostscript が必要です。\n『インストールを実行』を選ぶと、アプリが管理者権限で再起動し、自動で Ghostscript を導入した後、ドキュメントと圧縮処理を再開します。\n続行しますか？',
                'ghostscript_install_already': 'Ghostscript は既に利用可能です。',
                'loading_app': 'YongPDF を準備しています...',
                'loading_external_editor': '外部エディタを起動しています...',
                'external_editor_ready': '外部エディタを起動しました。',
                'external_editor_running': '外部エディタは既に実行中です。',
                'external_editor_refresh_notice': '外部エディタでの保存を検知し、文書を再読み込みしました。',
                'estimate_prefix': '推定サイズ', 'selected_dpi': '選択DPI', 'estimate_unavailable': '推定不可', 'current': '現在', 'color': 'カラー', 'gray': 'グレー', 'mono': 'モノ'
            },
            'zh-CN': {
                'alert_no_pdf': '没有打开任何 PDF。', 'alert_no_edit_pdf': '没有可编辑的 PDF 被打开。', 'unsaved_changes': '存在未保存的更改，是否保存？', 'btn_yes': '是', 'btn_save_as': '另存为', 'btn_no': '否', 'btn_cancel': '取消',
                'zoom_in': '➕ 放大', 'zoom_out': '➖ 缩小', 'theme_light': '☀️ 亮色', 'theme_dark': '🌙 暗色', 'theme_light_mode': '☀️ 亮色模式', 'theme_dark_mode': '🌙 暗色模式',
                'status_page': '页面', 'status_zoom': '缩放', 'status_ready': '就绪', 'status_saving': '正在保存…', 'status_saved': '已保存。',
                'status_reordering': '正在重新排序页面…', 'status_reordered': '页面已重新排序。', 'status_rotating': '正在旋转页面…', 'status_rotated': '页面已旋转。',
                'status_printing': '正在准备打印…', 'status_print_done': '打印任务已发送。',
                'status_compressing': '正在压缩…', 'status_compress_done': '压缩已完成。',
                'status_patch_mode_on': '🩹 补丁模式已启用。', 'status_patch_mode_off': '🩹 补丁模式已关闭。',
                'status_patch_eraser_on': '🧽 橡皮模式已启用。', 'status_patch_eraser_off': '🧽 橡皮模式已关闭。',
                'progress_compress': '正在压缩 PDF...', 'progress_compress_adv': '正在执行高级 PDF 压缩...',
                'progress_preparing_fonts': '正在为高级压缩准备字体...', 'progress_ensuring_fonts': '正在为第 {page} 页应用字体...',
                'progress_applying_overlay': "正在为第 {page} 页应用覆盖层…“{text}”",
                'file_menu': '文件', 'open': '📂 打开', 'save': '💾 保存', 'save_as': '📑 另存为', 'print': '🖨️ 打印', 'exit': '🚪 退出',
                'page_menu': '页面', 'add_page': '🙏 添加页面', 'delete_page': '🗑️ 删除页面', 'cm_delete_selected': '🗑️ 删除所选页面', 'cm_save_selected': '💾 保存所选页面',
                'move_up': '👆 上移', 'move_down': '👇 下移', 'rotate_left': '⤴️ 向左旋转', 'rotate_right': '⤵️ 向右旋转', 'view_menu': '视图', 'single_view': '📄 单页显示', 'dual_view': '📖 双页显示', 'fit_width': '↔️ 适应宽度', 'fit_height': '↕️ 适应高度', 'tools_menu': '工具', 'compress_pdf': '📦 压缩PDF',
                'edit_menu': '编辑', 'undo': '↩️ 撤销', 'redo': '↪️ 重做', 'language_menu': '语言', 'korean': '韩文', 'english': '英文', 'help_menu': '帮助', 'licenses_menu': '📜 开源许可', 'licenses_title': '开源许可', 'about': 'ℹ️ 关于',
                'prev': '👈 上一页', 'next': '👉 下一页', 'add_short': '🙏 添加', 'delete_short': '🗑️ 删除', 'move_up_short': '👆 上移', 'move_down_short': '👇 下移', 'rotate_left_short': '⤴️ 左旋转', 'rotate_right_short': '⤵️ 右旋转', 'edit_short': '✏️ 编辑',
                'about_text': 'YongPDF\n开发者: Hwang Jinsu\n邮箱: iiish@hanmail.net\n许可: 免费软件\n本软件可免费用于个人/工作用途。',
                'info_compress': '请选择压缩模式。\n- 一般: 结构优化(无损)\n- 高级: 按DPI降采样图像', 'general_compress': '一般(无损, 结构优化)', 'advanced_compress': '高级(图像DPI调节)',
                'color_dpi_label': '彩色图像 DPI (10级)', 'gray_dpi_label': '灰度图像 DPI', 'mono_dpi_label': '黑白图像 DPI', 'preserve_vector': '保留文本/矢量(仅处理图像)',
                'ghostscript_config': '🛠️ 设置 Ghostscript 路径', 'ghostscript_prompt': '未安装 Ghostscript。现在安装吗？', 'ghostscript_select': '选择 Ghostscript 可执行文件', 'ghostscript_set': '已保存 Ghostscript 路径。', 'ghostscript_not_found': '找不到 Ghostscript 可执行文件。', 'ghostscript_install': '立即安装', 'ghostscript_install_proceed': '安装并继续', 'ghostscript_install_cancel': '取消', 'ghostscript_install_hint': '已打开 Ghostscript 下载页面。安装后请重试。', 'ghostscript_install_notice_mac': "在 macOS 上进行高级压缩需要 Ghostscript。\n点击“安装并继续”会通过 Homebrew 执行“brew install ghostscript”。\n如果尚未安装 Homebrew，请先访问 https://brew.sh。", 'print_error': '打印时发生错误。', 'compress_adv_done': '高级 PDF 压缩已完成。', 'compress_adv_error': '高级 PDF 压缩时发生错误。', 'compress_adv_permission_error': "Ghostscript 安装需要管理员授权。请选择'安装并继续'，按提示完成安装后压缩会自动继续。", 'save_permission_error': '无法写入当前位置。请另存到其他位置。', 'save_failed': '无法保存文件。', 'saved': '已保存', 'saved_as': '已另存为', 'err_editor_missing': '未找到 YongPDF_text（應用/可執行檔）或 main_codex1.py。', 'err_editor_launch': '无法启动外部编辑器。',
                'ghostscript_installing': '正在通过终端安装 Ghostscript...（{manager}）',
                'ghostscript_install_success': 'Ghostscript 安装完成。',
                'ghostscript_install_failed': 'Ghostscript 安装失败。',
                'ghostscript_install_missing_pm': '未找到支持自动安装的包管理器，请手动安装 Ghostscript。', 'ghostscript_install_missing_mac': "未找到 Homebrew。请先在 https://brew.sh 安装 Homebrew，然后在终端执行“brew install ghostscript”。",
                'ghostscript_install_manual': '无法自动安装，已打开 Ghostscript 下载页面。安装后请重试。',
                'ghostscript_install_check_path': '安装似乎已完成，但未找到可执行文件。请手动指定路径。',
                'ghostscript_bundle_ready': '已使用随附的 Ghostscript 可执行文件。',
                'ghostscript_program_files_missing': '无法定位 Windows 的 Program Files 目录。请以管理员权限重新运行 YongPDF 后重试。',
                'ghostscript_local_installing': '正在准备随附的 Ghostscript...',
                'ghostscript_local_install_done': '已准备好使用随附的 Ghostscript。',
                'ghostscript_local_install_failed': '随附的 Ghostscript 准备失败。',
                'ghostscript_resume_title': 'Ghostscript 已就绪',
                'ghostscript_resume_prompt': "Ghostscript 安装已完成。\n要使用之前的设置继续执行高级 PDF 压缩吗？\n\n输出文件: {output}\n彩色 DPI: {dpi_color} / 灰度 DPI: {dpi_gray} / 黑白 DPI: {dpi_mono}\n保留文本/矢量: {preserve_vector}",
                'ghostscript_resume_failed': "Ghostscript 安装失败。\n请以管理员权限重新启动 YongPDF 后重试。\n\n错误: {error}",
                'ghostscript_install_notice': "高级压缩需要 Ghostscript。\n点击'安装并继续'后，应用会以管理员权限重新启动，自动安装 Ghostscript，并重新打开文档继续压缩。\n现在执行吗？",
                'ghostscript_install_already': 'Ghostscript 已可用，无需再次安装。',
                'loading_app': '正在启动 YongPDF...',
                'loading_external_editor': '正在启动外部编辑器...',
                'external_editor_ready': '外部编辑器已启动。',
                'external_editor_running': '外部编辑器已在运行。',
                'external_editor_refresh_notice': '检测到外部编辑保存，已重新加载文档。',
                'estimate_prefix': '预计大小', 'selected_dpi': '选择的DPI', 'estimate_unavailable': '无法估计', 'current': '当前', 'color': '彩色', 'gray': '灰度', 'mono': '黑白'
            },
            'zh-TW': {
                'alert_no_pdf': '沒有開啟任何 PDF。', 'alert_no_edit_pdf': '尚未開啟可編輯的 PDF。', 'unsaved_changes': '有未儲存的變更，是否儲存？', 'btn_yes': '是', 'btn_save_as': '另存新檔', 'btn_no': '否', 'btn_cancel': '取消',
                'zoom_in': '➕ 放大', 'zoom_out': '➖ 縮小', 'theme_light': '☀️ 亮色', 'theme_dark': '🌙 暗色', 'theme_light_mode': '☀️ 亮色模式', 'theme_dark_mode': '🌙 暗色模式',
                'status_page': '頁面', 'status_zoom': '縮放', 'status_ready': '就緒', 'status_saving': '正在儲存…', 'status_saved': '已儲存。', 'status_reordering': '正在重新排序頁面…', 'status_reordered': '已重新排序頁面。', 'status_rotating': '正在旋轉頁面…', 'status_rotated': '頁面已旋轉。', 'status_printing': '正在準備列印…', 'status_print_done': '列印工作已送出。', 'status_compressing': '正在壓縮…', 'status_compress_done': '壓縮完成。',
                'status_patch_mode_on': '🩹 補丁模式已啟用。', 'status_patch_mode_off': '🩹 補丁模式已停用。',
                'status_patch_eraser_on': '🧽 橡皮模式已啟用。', 'status_patch_eraser_off': '🧽 橡皮模式已停用。',
                'progress_compress': '正在壓縮 PDF...', 'progress_compress_adv': '正在執行進階 PDF 壓縮...',
                'progress_preparing_fonts': '正在為進階壓縮準備字體...', 'progress_ensuring_fonts': '正在為第 {page} 頁套用字體...',
                'progress_applying_overlay': "正在於第 {page} 頁套用覆蓋層…「{text}」",
                'file_menu': '檔案', 'open': '📂 開啟', 'save': '💾 儲存', 'save_as': '📑 另存新檔', 'print': '🖨️ 列印', 'exit': '🚪 結束',
                'page_menu': '頁面', 'add_page': '🙏 新增頁面', 'delete_page': '🗑️ 刪除頁面', 'cm_delete_selected': '🗑️ 刪除所選頁面', 'cm_save_selected': '💾 儲存所選頁面',
                'move_up': '👆 上移', 'move_down': '👇 下移', 'rotate_left': '⤴️ 向左旋轉', 'rotate_right': '⤵️ 向右旋轉', 'view_menu': '檢視', 'single_view': '📄 單頁檢視', 'dual_view': '📖 雙頁檢視', 'fit_width': '↔️ 配合寬度', 'fit_height': '↕️ 配合高度', 'tools_menu': '工具', 'compress_pdf': '📦 壓縮PDF',
                'edit_menu': '編輯', 'undo': '↩️ 復原', 'redo': '↪️ 取消復原', 'language_menu': '語言', 'korean': '韓文', 'english': '英文', 'help_menu': '說明', 'licenses_menu': '📜 開源授權', 'licenses_title': '開源授權', 'about': 'ℹ️ 關於',
                'prev': '👈 上一頁', 'next': '👉 下一頁', 'add_short': '🙏 新增', 'delete_short': '🗑️ 刪除', 'move_up_short': '👆 上移', 'move_down_short': '👇 下移', 'rotate_left_short': '⤴️ 左旋轉', 'rotate_right_short': '⤵️ 右旋轉', 'edit_short': '✏️ 編輯',
                'about_text': 'YongPDF\n開發者: Hwang Jinsu\n信箱: iiish@hanmail.net\n授權: 免費軟體\n本軟體可免費用於個人/商務。',
                'info_compress': '請選擇壓縮模式。\n- 一般: 結構最佳化(無損)\n- 進階: 依DPI降採樣影像', 'general_compress': '一般(無損, 結構最佳化)', 'advanced_compress': '進階(影像DPI調整)',
                'color_dpi_label': '彩色影像 DPI (10級)', 'gray_dpi_label': '灰階影像 DPI', 'mono_dpi_label': '黑白影像 DPI', 'preserve_vector': '保留文字/向量(僅處理影像)',
                'ghostscript_config': '🛠️ 設定 Ghostscript 路徑', 'ghostscript_prompt': '尚未安裝 Ghostscript，要立即安裝嗎？', 'ghostscript_select': '選擇 Ghostscript 執行檔', 'ghostscript_set': '已儲存 Ghostscript 路徑。', 'ghostscript_not_found': '找不到 Ghostscript 執行檔。', 'ghostscript_install': '立即安裝', 'ghostscript_install_proceed': '安裝並繼續', 'ghostscript_install_cancel': '取消', 'ghostscript_install_hint': '已開啟 Ghostscript 下載頁面。安裝後請再試一次。', 'ghostscript_install_notice_mac': "在 macOS 上進行進階壓縮需要 Ghostscript。\n按下「安裝並繼續」會透過 Homebrew 執行「brew install ghostscript」。\n若尚未安裝 Homebrew，請先前往 https://brew.sh。", 'print_error': '列印時發生錯誤。', 'compress_adv_done': '進階 PDF 壓縮完成。', 'compress_adv_error': '進階 PDF 壓縮時發生錯誤。', 'compress_adv_permission_error': "Ghostscript 安裝需要管理員授權。請點選'安裝並繼續'，依照指示完成後會自動續行壓縮。", 'save_permission_error': '無法寫入目前位置。請另存到其他位置。', 'save_failed': '無法儲存檔案。', 'saved': '已儲存', 'saved_as': '已另存新檔', 'err_editor_missing': '找不到 YongPDF_text（應用/可執行檔）或 main_codex1.py。', 'err_editor_launch': '無法啟動外部編輯器。',
                'ghostscript_installing': '正在透過終端機安裝 Ghostscript...（{manager}）',
                'ghostscript_install_success': 'Ghostscript 安裝完成。',
                'ghostscript_install_failed': 'Ghostscript 安裝失敗。',
                'ghostscript_install_missing_pm': '找不到支援自動安裝的套件管理器，請手動安裝 Ghostscript。', 'ghostscript_install_missing_mac': "找不到 Homebrew。請先在 https://brew.sh 安裝 Homebrew，然後在終端執行「brew install ghostscript」。",
                'ghostscript_install_manual': '無法自動安裝，已開啟 Ghostscript 下載頁面。安裝後請再試一次。',
                'ghostscript_install_check_path': '安裝似乎完成，但未找到執行檔。請手動指定路徑。',
                'ghostscript_bundle_ready': '已使用隨附的 Ghostscript 可執行檔。',
                'ghostscript_program_files_missing': '找不到 Windows 的 Program Files 目錄。請以系統管理員身分重新啟動 YongPDF 後再試一次。',
                'ghostscript_local_installing': '正在準備內建的 Ghostscript...',
                'ghostscript_local_install_done': '已可使用內建 Ghostscript。',
                'ghostscript_local_install_failed': '無法準備內建 Ghostscript。',
                'ghostscript_resume_title': 'Ghostscript 已就緒',
                'ghostscript_resume_prompt': "Ghostscript 安裝完成。\n要以先前的設定繼續進行進階 PDF 壓縮嗎？\n\n輸出檔案: {output}\n彩色 DPI: {dpi_color} / 灰階 DPI: {dpi_gray} / 黑白 DPI: {dpi_mono}\n保留文字/向量: {preserve_vector}",
                'ghostscript_resume_failed': "Ghostscript 安裝失敗。\n請以系統管理員身分重新啟動 YongPDF 後再試一次。\n\n錯誤: {error}",
                'ghostscript_install_notice': "進階壓縮需要 Ghostscript。\n按下'安裝並繼續'後，應用會以管理員權限重新啟動，自動安裝 Ghostscript，並重新開啟文件繼續壓縮。\n要立即執行嗎？",
                'ghostscript_install_already': 'Ghostscript 已可使用，無需再次安裝。',
                'loading_app': '正在準備 YongPDF...',
                'loading_external_editor': '正在啟動外部編輯器...',
                'external_editor_ready': '外部編輯器已啟動。',
                'external_editor_running': '外部編輯器已在執行。',
                'external_editor_refresh_notice': '偵測到外部編輯儲存，已重新載入文件。',
                'estimate_prefix': '預估大小', 'selected_dpi': '選擇的DPI', 'estimate_unavailable': '無法預估', 'current': '目前', 'color': '彩色', 'gray': '灰階', 'mono': '黑白'
            }
        }

    def t(self, key: str) -> str:
        return self.translations.get(self.language, {}).get(key, key)

    def set_language(self, lang: str):
        if lang not in ('ko', 'en', 'ja', 'zh-CN', 'zh-TW'):
            return
        self.language = lang
        try:
            self.settings.setValue('language', lang)
        except Exception:
            pass
        # rebuild menus and toolbar
        mb = self.menuBar()
        mb.clear()
        self.setup_menubar()
        # remove all existing toolbars to avoid duplicates
        for tb in self.findChildren(QToolBar):
            self.removeToolBar(tb)
        self.setup_toolbar()
        # title
        title = os.path.basename(self.current_file) if self.current_file else ''
        self.setWindowTitle(f"{self.app_name} - {title}" if title else self.app_name)
        # refresh statusbar text
        self.update_page_info()

    def reorder_pages(self, source_rows: list[int], dest_row: int):
        """페이지 순서를 재정렬하는 새로운 핵심 메서드."""
        print("--- Initiating reorder_pages ---")
        print(f"[DEBUG] Received source_rows: {source_rows}, dest_row: {dest_row}")

        if not source_rows or dest_row < 0:
            print("[DEBUG] Invalid input, aborting reorder.")
            return

        self.show_status(self.t('status_reordering'), busy=True)
        try:
            # snapshot for undo
            if self.pdf_document:
                try:
                    self._undo_stack.append(self.pdf_document.tobytes(garbage=4, deflate=True))
                    self._redo_stack.clear()
                except Exception:
                    pass

            initial_page_order = list(range(self.pdf_document.page_count))
            print(f"[DEBUG] Initial page order: {initial_page_order}")

            moved_items = [initial_page_order[i] for i in source_rows]
            print(f"[DEBUG] Items to move: {moved_items}")

            remaining_items = [p for i, p in enumerate(initial_page_order) if i not in source_rows]
            print(f"[DEBUG] Remaining items: {remaining_items}")

            true_dest_row = dest_row - sum(1 for i in source_rows if i < dest_row)
            print(f"[DEBUG] Calculated true destination row: {true_dest_row}")

            print(f"[DEBUG] Starting insertion loop. Target index: {true_dest_row}")
            for item in reversed(moved_items):
                remaining_items.insert(true_dest_row, item)
                print(f"  - Inserted {item}. List is now: {remaining_items}")
            
            new_order = remaining_items
            print(f"[DEBUG] Final new_order: {new_order}")
            print(f"[DEBUG] Final item count: {len(new_order)}, Initial count: {len(initial_page_order)}")

            if len(new_order) != len(initial_page_order):
                print("[ERROR] Page count mismatch! Aborting to prevent data loss.")
                QMessageBox.critical(self, "오류", "페이지 순서 변경 중 심각한 오류가 발생했습니다. 데이터 손상을 방지하기 위해 작업을 중단합니다.")
                self.show_status(self.t('status_ready'))
                return

            # mark reordering to suppress view side-effects
            self._reordering_in_progress = True
            # store selection offsets for precise multi-select preservation
            try:
                self._last_moved_offsets = [i - source_rows[0] for i in source_rows]
            except Exception:
                self._last_moved_offsets = list(range(len(moved_items)))
            self._perform_reordering_and_update_ui(new_order, true_dest_row, len(moved_items))
            self.show_status(self.t('status_reordered'))

        except Exception as e:
            print(f"Reordering failed: {e}")
            traceback.print_exc()
            self.clear_status()

    def _perform_reordering_and_update_ui(self, new_order: list[int], new_start_row: int, selection_count: int):
        """ 계산된 새 페이지 순서에 따라 문서를 재구성하고 UI를 새로고침합니다. """
        try:
            self._suppress_scroll_sync = True
            # Use in-place reordering for the document
            self.pdf_document.select(new_order)
            self.mark_as_unsaved()
            self._thumb_cache.clear(); self._page_cache.clear()
            # Reorder thumbnail items to mirror the same mapping without rebuilding pixmaps
            try:
                self.thumbnail_widget.apply_new_order_to_view(new_order)
            except Exception:
                # Fallback: full reload if anything goes wrong
                self.load_thumbnails()
            self.load_document_view()
            # Explicitly set selection to moved items only (preserve multi)
            sel_model = self.thumbnail_widget.selectionModel()
            sel_model.clearSelection()
            offsets = getattr(self, '_last_moved_offsets', list(range(selection_count)))
            for off in offsets:
                idx = new_start_row + off
                item = self.thumbnail_widget.item(idx)
                if item:
                    sel_model.select(self.thumbnail_widget.indexFromItem(item), QItemSelectionModel.SelectionFlag.Select)
            try:
                idx = self.thumbnail_widget.model().index(new_start_row, 0)
                sel_model.setCurrentIndex(idx, QItemSelectionModel.SelectionFlag.NoUpdate)
            except Exception:
                pass
            self.current_page = new_start_row
            self._suppress_scroll_sync = False
            # Ensure thumbnails paint now (prevents “disappearing until next action”)    
            self.thumbnail_widget.doItemsLayout()
            self.thumbnail_widget.viewport().update()
            self.thumbnail_widget.repaint()
            QApplication.processEvents()
            try:
                it = self.thumbnail_widget.item(new_start_row)
                if it:
                    self.thumbnail_widget.scrollToItem(it, QListWidget.ScrollHint.PositionAtCenter)
            except Exception:
                pass
            # Second pass: full reload next tick to hard-sync view order and selection
            QTimer.singleShot(0, lambda ns=new_start_row, sc=selection_count: self._full_thumbnail_reload_after_reorder(ns, sc))
            QTimer.singleShot(0, lambda: self.scroll_to_page(new_start_row))
            self._reordering_in_progress = False

        except Exception as e:
            print(f"Error performing reordering: {e}")

    def update_page_info(self):
        if self.pdf_document and self.pdf_document.page_count > 0:
            current = self.current_page + 1
            total = self.pdf_document.page_count
            self.page_input.setText(str(current))
            self.total_pages_label.setText(f"/{total}")
            self.status_page_label.setText(f"{self.t('status_page')}: {current} / {total}")
            self.status_zoom_label.setText(f"{self.t('status_zoom')}: {int(self.zoom_level * 100)}%")
        else:
            self.page_input.setText("0")
            self.total_pages_label.setText("/0")
            self.status_page_label.setText(f"{self.t('status_page')}: 0 / 0")
            self.status_zoom_label.setText(f"{self.t('status_zoom')}: -")

    def open_file(self, file_path=None):
        if not file_path:
            last_dir = str(self.settings.value('last_dir', os.path.dirname(self.current_file) if self.current_file else os.getcwd())) if hasattr(self, 'settings') else ''
            file_path, _ = QFileDialog.getOpenFileName(self, "📂 PDF 파일 열기", last_dir, "PDF 파일 (*.pdf)")
        if file_path:
            try:
                if self.pdf_document: self.pdf_document.close()
                self.pdf_document = fitz.open(file_path)
                self.current_file = file_path
                self.current_page = 0
                self.has_unsaved_changes = False
                self.setWindowTitle(f"PDF Editor - {os.path.basename(file_path)}")
                self._thumb_cache.clear(); self._page_cache.clear()
                self.load_thumbnails()
                self.load_document_view()
                # Align thumbnail frames with current icon/grid settings
                try:
                    self.on_thumbnail_zoom_slider_changed(self.thumbnail_zoom_slider.value())
                except Exception:
                    pass
                self.update_page_info()
                if hasattr(self, 'settings'):
                    self.settings.setValue('last_dir', os.path.dirname(file_path))
            except Exception as e:
                QMessageBox.critical(self, "오류", f"PDF 파일을 열 수 없습니다.\n{e}")

    def _unload_document(self, preserve_current_file: bool = False):
        if self.pdf_document:
            try:
                self.pdf_document.close()
            except Exception:
                pass
        self.pdf_document = None
        if not preserve_current_file:
            self.current_file = None
        self.current_page = 0
        self.zoom_level = 1.0
        self.has_unsaved_changes = False
        self._thumb_cache.clear()
        self._page_cache.clear()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.thumbnail_widget.clear()
        while self.document_layout.count():
            child = self.document_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()
        self.page_labels.clear()
        self.update_page_info()
        try:
            self.document_container.update()
        except Exception:
            pass

    def _configure_external_watch(self, path: str):
        if not path:
            return
        try:
            if not hasattr(self, '_editor_watcher'):
                self._editor_watcher = QFileSystemWatcher(self)
                self._editor_watcher.fileChanged.connect(self._on_editor_file_changed)
            if path in getattr(self, '_editor_watcher').files():
                self._editor_watcher.removePath(path)
            self._editor_watcher.addPath(path)
            self._editor_watch_path = path
        except Exception:
            self._editor_watch_path = None

    def _disable_external_watch(self):
        try:
            if hasattr(self, '_editor_watcher') and getattr(self, '_editor_watch_path', None):
                if self._editor_watch_path in self._editor_watcher.files():
                    self._editor_watcher.removePath(self._editor_watch_path)
        except Exception:
            pass
        self._editor_watch_path = None

    def _resolve_external_editor_command(self, target_path: str) -> Optional[tuple[str, list[str]]]:
        source_dir = os.path.dirname(os.path.abspath(__file__))
        exec_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else source_dir
        base_dir = getattr(sys, '_MEIPASS', exec_dir)
        candidates: list[tuple[str, bool]] = []

        search_roots = [base_dir]
        if source_dir not in search_roots:
            search_roots.append(source_dir)
        if exec_dir not in search_roots:
            search_roots.append(exec_dir)
        if sys.platform == 'darwin':
            app_root = os.path.normpath(os.path.join(exec_dir, '..', '..'))
            dist_root = os.path.normpath(os.path.join(exec_dir, '..', '..', '..'))
            resources_root = os.path.normpath(os.path.join(exec_dir, '..', 'Resources'))
            for extra in (app_root, dist_root, resources_root):
                if extra not in search_roots:
                    search_roots.append(extra)
        if sys.platform == 'darwin':
            resources_dir = os.path.normpath(os.path.join(exec_dir, '..', 'Resources'))
            if resources_dir not in search_roots:
                search_roots.append(resources_dir)

        seen_paths: set[str] = set()

        def add_candidate(path: str, is_script: bool):
            norm = os.path.normpath(path)
            if norm in seen_paths:
                return
            seen_paths.add(norm)
            candidates.append((norm, is_script))

        if sys.platform.startswith('win'):
            for name in (TEXT_EDITOR_EXE_NAME, LEGACY_EDITOR_EXE_NAME):
                for root in search_roots:
                    add_candidate(os.path.join(root, name), False)
        else:
            for name in (TEXT_EDITOR_STEM, LEGACY_EDITOR_STEM):
                for root in search_roots:
                    add_candidate(os.path.join(root, name), False)
            for root in search_roots:
                add_candidate(os.path.join(root, TEXT_EDITOR_APP_NAME), False)
                add_candidate(os.path.join(root, LEGACY_EDITOR_STEM + '.app'), False)

        for script_name in (TEXT_EDITOR_SCRIPT_NAME, 'main_codex1.py'):
            for root in search_roots:
                add_candidate(os.path.join(root, script_name), True)

        for path, is_script in candidates:
            if not os.path.exists(path):
                continue
            if is_script:
                interpreter = sys.executable or sys.argv[0]
                if not interpreter:
                    continue
                return interpreter, [path, target_path]
            if sys.platform == 'darwin' and path.endswith('.app'):
                app_binary = os.path.join(path, TEXT_EDITOR_APP_BINARY)
                if os.path.isfile(app_binary):
                    return app_binary, [target_path]
                return '/usr/bin/open', ['-a', path, target_path]
            if sys.platform.startswith('win') or os.access(path, os.X_OK):
                return path, [target_path]
        return None

    def save_file(self):
        if not (self.pdf_document and self.current_file):
            QMessageBox.warning(self, self.app_name, self.t('alert_no_pdf'))
            return

        original_watch_path = getattr(self, '_editor_watch_path', None)
        self._disable_external_watch()

        self.show_status(self.t('status_saving'), busy=True)
        try:
            self._save_document_incremental(self.current_file)
            self._finalize_successful_save(self.current_file)
            return
        except PermissionError as perm_err:
            self.clear_status()
            if self._handle_save_permission_denied(perm_err):
                return
            self.show_status(self.t('status_ready'))
            return
        except Exception:
            pass

        try:
            self._save_document_full_replace(self.current_file)
            self._finalize_successful_save(self.current_file)
            return
        except PermissionError as perm_err:
            self.clear_status()
            if self._handle_save_permission_denied(perm_err):
                return
            self.show_status(self.t('status_ready'))
            return
        except Exception as err:
            self.clear_status()
            QMessageBox.critical(self, self.app_name, f"{self.t('save_failed')}\n{err}")
            self.save_as_file()
            return
        finally:
            if original_watch_path and not getattr(self, '_editor_watch_path', None):
                try:
                    self._configure_external_watch(original_watch_path)
                except Exception:
                    pass

    def _restore_from_bytes(self, data: bytes):
        try:
            if self.pdf_document:
                self.pdf_document.close()
            self.pdf_document = fitz.open(stream=data, filetype="pdf")
            # clamp current page
            if self.current_page >= self.pdf_document.page_count:
                self.current_page = max(0, self.pdf_document.page_count - 1)
            self._thumb_cache.clear(); self._page_cache.clear()
            self.load_thumbnails()
            self.load_document_view()
            self.scroll_to_page(self.current_page)
            self.update_page_info()
            self.mark_as_unsaved()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"복원 중 오류가 발생했습니다.\n{e}")

    def undo_action(self):
        if not self._undo_stack:
            return
        try:
            # push current state to redo, pop from undo
            if self.pdf_document:
                self._redo_stack.append(self.pdf_document.tobytes(garbage=4, deflate=True))
            data = self._undo_stack.pop()
            self._restore_from_bytes(data)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"실행 취소 중 오류가 발생했습니다.\n{e}")

    def redo_action(self):
        if not self._redo_stack:
            return
        try:
            if self.pdf_document:
                self._undo_stack.append(self.pdf_document.tobytes(garbage=4, deflate=True))
            data = self._redo_stack.pop()
            self._restore_from_bytes(data)
        except Exception as e:
            QMessageBox.critical(self, "오류", f"다시 실행 중 오류가 발생했습니다.\n{e}")

    def save_as_file(self):
        if not self.pdf_document: return
        default_dir = self._suggest_save_directory()
        default_name = os.path.basename(self.current_file) if self.current_file else "Untitled.pdf"
        default_path = os.path.join(default_dir, default_name)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.t('save_as'),
            default_path,
            'PDF files (*.pdf);;All files (*)'
        )
        if file_path:
            if self.current_file and os.path.abspath(file_path) == os.path.abspath(self.current_file):
                self.save_file()
                return
            try:
                original_watch_path = getattr(self, '_editor_watch_path', None)
                self._disable_external_watch()
                self.show_status(self.t('status_saving'), busy=True)
                self._save_document_full_replace(file_path)
                self._finalize_successful_save(file_path, bar_message_key='saved_as')
            except Exception as e:
                self.clear_status()
                print(f"Error saving as file: {e}")
            finally:
                if original_watch_path and not getattr(self, '_editor_watch_path', None):
                    try:
                        self._configure_external_watch(self.current_file or original_watch_path)
                    except Exception:
                        pass

    def _finalize_successful_save(self, path: str, *, bar_message_key: str = 'saved') -> None:
        self.current_file = path
        self.has_unsaved_changes = False
        self.setWindowTitle(f"{self.app_name} - {os.path.basename(path)}")
        try:
            message = self.t(bar_message_key)
            if self.language == 'en':
                message = 'Saved As' if bar_message_key == 'saved_as' else 'Saved'
            self.statusBar().showMessage(message, 3000)
        except Exception:
            pass
        if hasattr(self, 'settings'):
            try:
                self.settings.setValue('last_dir', os.path.dirname(path))
            except Exception:
                pass
        try:
            self._configure_external_watch(path)
        except Exception:
            pass
        self.show_status(self.t('status_saved'))

    def _save_document_incremental(self, path: str) -> None:
        self.pdf_document.save(path, incremental=True)

    def _save_document_full_replace(self, path: str) -> None:
        base_dir = os.path.dirname(path) or os.getcwd()
        os.makedirs(base_dir, exist_ok=True)

        current_page = self.current_page
        current_zoom = self.zoom_level
        scroll_value = self.scroll_area.verticalScrollBar().value() if self.scroll_area.verticalScrollBar() else 0

        data = self.pdf_document.tobytes(garbage=4, deflate=True)
        tmp_path = os.path.join(base_dir, f".__yongpdf_tmp_{uuid.uuid4().hex}.pdf")

        with open(tmp_path, 'wb') as tmp_file:
            tmp_file.write(data)

        try:
            try:
                self.pdf_document.close()
            except Exception:
                pass

            os.replace(tmp_path, path)

            self.pdf_document = fitz.open(path)
            self._thumb_cache.clear()
            self._page_cache.clear()
            self.load_thumbnails()
            self.load_document_view()
            self.scroll_to_page(min(current_page, max(0, self.pdf_document.page_count - 1)))
            self.scroll_area.verticalScrollBar().setValue(scroll_value)
            self.zoom_level = current_zoom
        except Exception as replace_err:
            try:
                self.pdf_document = fitz.open(stream=data, filetype='pdf')
                self._thumb_cache.clear()
                self._page_cache.clear()
                self.load_thumbnails()
                self.load_document_view()
                self.scroll_to_page(min(current_page, max(0, self.pdf_document.page_count - 1)))
                self.scroll_area.verticalScrollBar().setValue(scroll_value)
                self.zoom_level = current_zoom
            except Exception:
                pass
            raise replace_err
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def _handle_save_permission_denied(self, error: Exception) -> bool:
        QMessageBox.warning(
            self,
            self.app_name,
            f"{self.t('save_permission_error')}\n{error}"
        )
        default_dir = self._suggest_save_directory()
        default_name = os.path.basename(self.current_file) if self.current_file else "Untitled.pdf"
        default_path = os.path.join(default_dir, default_name)
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.t('save_as'),
            default_path,
            'PDF files (*.pdf);;All files (*)'
        )
        if not file_path:
            return False
        if self.current_file and os.path.abspath(file_path) == os.path.abspath(self.current_file):
            self.save_file()
            return True

        original_watch_path = getattr(self, '_editor_watch_path', None)
        self._disable_external_watch()
        try:
            self.show_status(self.t('status_saving'), busy=True)
            self._save_document_full_replace(file_path)
            self._finalize_successful_save(file_path, bar_message_key='saved_as')
            return True
        except Exception as err:
            self.clear_status()
            QMessageBox.critical(self, self.app_name, f"{self.t('save_failed')}\n{err}")
            return False
        finally:
            if original_watch_path and not getattr(self, '_editor_watch_path', None):
                try:
                    self._configure_external_watch(self.current_file or original_watch_path)
                except Exception:
                    pass

    def _suggest_save_directory(self) -> str:
        candidates: list[str] = []
        if hasattr(self, 'settings'):
            try:
                last_dir = self.settings.value('last_dir', type=str)
                if last_dir:
                    candidates.append(last_dir)
            except Exception:
                pass
        if self.current_file:
            candidates.append(os.path.dirname(self.current_file))

        # Common user directories
        home = Path.home()
        documents = home / 'Documents'
        downloads = home / 'Downloads'
        for directory in (documents, downloads, home):
            candidates.append(str(directory))

        candidates.append(os.getcwd())

        for directory in candidates:
            if not directory:
                continue
            try:
                if os.path.isdir(directory) and os.access(directory, os.W_OK):
                    return directory
            except Exception:
                continue
        return os.getcwd()

    def load_document_view(self):
        # try to reuse cached pixmaps per (page, zoom)
        self._suppress_scroll_sync = True
        while self.document_layout.count():
            child = self.document_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.page_labels.clear()
        if not self.pdf_document: return
        zoom_key = int(self.zoom_level * 1000)
        current_row_widget: Optional[QWidget] = None
        current_row_layout: Optional[QHBoxLayout] = None
        for page_num in range(self.pdf_document.page_count):
            cache_key = (page_num, zoom_key)
            pixmap = self._page_cache.get(cache_key)
            if pixmap is None:
                page = self.pdf_document[page_num]
                matrix = fitz.Matrix(self.zoom_level, self.zoom_level)
                pix = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB)
                fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
                pixmap = QPixmap.fromImage(img)
                self._page_cache[cache_key] = pixmap
            page_label = PDFPageLabel(self)
            page_label.setPixmap(pixmap)
            page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            page_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.page_labels.append(page_label)
            if getattr(self, 'dual_page_view', False):
                if page_num % 2 == 0:
                    current_row_widget = QWidget()
                    current_row_widget.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
                    current_row_layout = QHBoxLayout(current_row_widget)
                    current_row_layout.setContentsMargins(10, 0, 10, 0)
                    current_row_layout.setSpacing(30)
                    current_row_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                if current_row_layout is not None:
                    current_row_layout.addWidget(page_label, 0, Qt.AlignmentFlag.AlignCenter)
                if (page_num % 2 == 1) or (page_num == self.pdf_document.page_count - 1):
                    if current_row_widget is not None:
                        self.document_layout.addWidget(current_row_widget, alignment=Qt.AlignmentFlag.AlignCenter)
                    current_row_widget = None
                    current_row_layout = None
            else:
                self.document_layout.addWidget(page_label, 0, Qt.AlignmentFlag.AlignHCenter)
        self.update_page_info()
        if not getattr(self, '_suppress_scroll_sync', False):
            self.thumbnail_widget.setCurrentRow(self.current_page)
        self._suppress_scroll_sync = False

    def scroll_to_page(self, page_num):
        if 0 <= page_num < len(self.page_labels):
            self.current_page = page_num
            self.scroll_area.ensureWidgetVisible(self.page_labels[page_num], 0, 0)
            self.update_page_info()
            try:
                sel_model = self.thumbnail_widget.selectionModel()
                index = self.thumbnail_widget.model().index(page_num, 0)
                sel_model.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.NoUpdate)
            except Exception:
                pass

    def load_thumbnails(self):
        self._suppress_scroll_sync = True
        self.thumbnail_widget.setUpdatesEnabled(False)
        self.thumbnail_widget.clear()
        if self.pdf_document:
            target_width = self.thumbnail_zoom_slider.value()
            for page_num in range(self.pdf_document.page_count):
                cache_key = (page_num, int(target_width))
                pixmap = self._thumb_cache.get(cache_key)
                if pixmap is None:
                    page = self.pdf_document[page_num]
                    rect = page.rect
                    zoom = target_width / rect.width
                    matrix = fitz.Matrix(zoom, zoom)
                    pix = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB)
                    fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
                    img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
                    pixmap = QPixmap.fromImage(img)
                    self._thumb_cache[cache_key] = pixmap
                self.thumbnail_widget.add_thumbnail(pixmap, page_num)
            if not getattr(self, '_suppress_scroll_sync', False):
                self.thumbnail_widget.setCurrentRow(self.current_page)
        # Force layout and repaint to avoid stale visuals
        self.thumbnail_widget.setUpdatesEnabled(True)
        self.thumbnail_widget.doItemsLayout()
        self.thumbnail_widget.viewport().update()
        self.thumbnail_widget.repaint()
        QApplication.processEvents()
        self._suppress_scroll_sync = False

    def refresh_thumbnails_in_place(self):
        """Update existing QListWidgetItems' icons/texts without clearing the list.
        Helps avoid transient disappearance after DnD."""
        if not self.pdf_document:
            return
        self._suppress_scroll_sync = True
        self.thumbnail_widget.setUpdatesEnabled(False)
        target_width = self.thumbnail_zoom_slider.value()
        count = self.pdf_document.page_count
        # If counts mismatch, fallback to full reload
        if self.thumbnail_widget.count() != count:
            self.thumbnail_widget.setUpdatesEnabled(True)
            self._suppress_scroll_sync = False
            self.load_thumbnails()
            return
        for i in range(count):
            cache_key = (i, int(target_width))
            pixmap = self._thumb_cache.get(cache_key)
            if pixmap is None:
                page = self.pdf_document[i]
                rect = page.rect
                zoom = target_width / rect.width
                matrix = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB)
                fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
                pixmap = QPixmap.fromImage(img)
                self._thumb_cache[cache_key] = pixmap
            it = self.thumbnail_widget.item(i)
            if it is None:
                continue
            it.setIcon(QIcon(pixmap))
            it.setText(f"Page {i + 1}")
        self.thumbnail_widget.setUpdatesEnabled(True)
        self.thumbnail_widget.doItemsLayout()
        self.thumbnail_widget.viewport().update()
        self.thumbnail_widget.repaint()
        QApplication.processEvents()
        self._suppress_scroll_sync = False

    def _full_thumbnail_reload_after_reorder(self, new_start_row: int, selection_count: int):
        # Hard reload list and restore selection/scroll to prevent any stale state
        self._suppress_scroll_sync = True
        self.load_thumbnails()
        sel_model = self.thumbnail_widget.selectionModel()
        if sel_model:
            sel_model.clearSelection()
            try:
                # Prefer offset-based multi selection if available
                offsets = getattr(self, '_last_moved_offsets', None)
                if offsets:
                    for off in offsets:
                        idx = new_start_row + off
                        item = self.thumbnail_widget.item(min(idx, self.thumbnail_widget.count()-1))
                        if item:
                            sel_model.select(self.thumbnail_widget.indexFromItem(item), QItemSelectionModel.SelectionFlag.Select)
                else:
                    # Fallback to contiguous range
                    top_left = self.thumbnail_widget.model().index(new_start_row, 0)
                    bottom_right = self.thumbnail_widget.model().index(new_start_row + selection_count - 1, 0)
                    sel = QItemSelection(top_left, bottom_right)
                    sel_model.select(sel, QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)
            except Exception:
                pass
        try:
            idx = self.thumbnail_widget.model().index(min(new_start_row, self.thumbnail_widget.count() - 1), 0)
            sel_model.setCurrentIndex(idx, QItemSelectionModel.SelectionFlag.NoUpdate)
        except Exception:
            pass
        self._suppress_scroll_sync = False
        self.thumbnail_widget.doItemsLayout()
        self.thumbnail_widget.viewport().update()
        self.thumbnail_widget.repaint()
        QApplication.processEvents()
        # Do a second hard reload next frame to cover platform paint delays
        QTimer.singleShot(16, lambda ns=new_start_row, sc=selection_count: self._finalize_thumbnail_reload(ns, sc))

    def _finalize_thumbnail_reload(self, new_start_row: int, selection_count: int):
        self._suppress_scroll_sync = True
        self.load_thumbnails()
        sel_model = self.thumbnail_widget.selectionModel()
        if sel_model:
            sel_model.clearSelection()
            try:
                offsets = getattr(self, '_last_moved_offsets', None)
                if offsets:
                    for off in offsets:
                        idx = new_start_row + off
                        item = self.thumbnail_widget.item(min(idx, self.thumbnail_widget.count()-1))
                        if item:
                            sel_model.select(self.thumbnail_widget.indexFromItem(item), QItemSelectionModel.SelectionFlag.Select)
                else:
                    top_left = self.thumbnail_widget.model().index(new_start_row, 0)
                    bottom_right = self.thumbnail_widget.model().index(new_start_row + selection_count - 1, 0)
                    sel = QItemSelection(top_left, bottom_right)
                    sel_model.select(sel, QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)
            except Exception:
                pass
        try:
            idx = self.thumbnail_widget.model().index(min(new_start_row, self.thumbnail_widget.count() - 1), 0)
            sel_model.setCurrentIndex(idx, QItemSelectionModel.SelectionFlag.NoUpdate)
        except Exception:
            pass
        self._suppress_scroll_sync = False
        self.thumbnail_widget.doItemsLayout()
        self.thumbnail_widget.viewport().update()
        self.thumbnail_widget.repaint()
        QApplication.processEvents()

    def move_pages_up(self, indexes):
        if not indexes: return
        sorted_indexes = sorted(indexes)
        if sorted_indexes[0] == 0: return
        self.reorder_pages(sorted_indexes, sorted_indexes[0] - 1)

    def move_pages_down(self, indexes):
        if not indexes: return
        sorted_indexes = sorted(indexes)
        # 이동 대상 블록의 바로 다음 위치(한 칸 아래)로 보내기 위해 +2 사용
        # (reorder_pages 내부에서 제거 후 삽입하므로 +1은 제자리 유지 효과)
        if sorted_indexes[-1] >= self.pdf_document.page_count - 1: return
        self.reorder_pages(sorted_indexes, sorted_indexes[-1] + 2)

    def add_blank_page(self):
        if not self.pdf_document: return
        last_dir = str(self.settings.value('last_dir', os.path.dirname(self.current_file) if self.current_file else os.getcwd())) if hasattr(self, 'settings') else ''
        file_path, _ = QFileDialog.getOpenFileName(self, self.t('add_page'), last_dir, "PDF 파일 (*.pdf)")
        if file_path:
            # snapshot for undo
            try:
                self._undo_stack.append(self.pdf_document.tobytes(garbage=4, deflate=True))
                self._redo_stack.clear()
            except Exception:
                pass
            insert_at = self.current_page + 1
            insert_doc = fitz.open(file_path)
            self.pdf_document.insert_pdf(insert_doc, from_page=0, to_page=insert_doc.page_count - 1, start_at=insert_at)
            insert_doc.close()
            self.mark_as_unsaved()
            self._thumb_cache.clear(); self._page_cache.clear()
            # Suppress sync during rebuild to avoid jumping to page 1
            self._suppress_scroll_sync = True
            # Set target page early so any intermediate UI refresh reads this value
            self.current_page = insert_at
            self.load_thumbnails()
            self.load_document_view()
            self.scroll_to_page(insert_at)
            # End suppression on next tick to ensure no late scroll events override our target
            QTimer.singleShot(0, lambda: self._finalize_after_insert(insert_at))
            if hasattr(self, 'settings'):
                self.settings.setValue('last_dir', os.path.dirname(file_path))

    def _finalize_after_insert(self, page_idx: int):
        self._suppress_scroll_sync = False
        self.scroll_to_page(page_idx)
        try:
            self.thumbnail_widget.setCurrentRow(page_idx)
        except Exception:
            pass

    def delete_current_page(self):
        if self.pdf_document and self.pdf_document.page_count > 1:
            self.delete_pages([self.current_page])

    def delete_pages(self, indexes):
        if not self.pdf_document or not indexes: return
        self._suppress_scroll_sync = True
        # snapshot for undo
        try:
            self._undo_stack.append(self.pdf_document.tobytes(garbage=4, deflate=True))
            self._redo_stack.clear()
        except Exception:
            pass
        
        for index in sorted(indexes, reverse=True):
            self.pdf_document.delete_page(index)
        
        new_page_count = self.pdf_document.page_count
        if self.current_page >= new_page_count:
            self.current_page = max(0, new_page_count - 1)

        self.mark_as_unsaved()
        self._thumb_cache.clear(); self._page_cache.clear()
        self.load_thumbnails()
        self.load_document_view()
        target = self.current_page
        self._suppress_scroll_sync = False
        QTimer.singleShot(0, lambda t=target: self.scroll_to_page(t))

    def rotate_pages(self, indexes, angle):
        if not self.pdf_document: return
        # preserve current multi-selection if not provided
        sel_before = sorted(indexes) if indexes else sorted(self.thumbnail_widget.get_selected_indexes())
        if not sel_before:
            sel_before = [self.current_page]
        self.show_status(self.t('status_rotating'), busy=True)
        self._suppress_scroll_sync = True
        # snapshot for undo
        try:
            self._undo_stack.append(self.pdf_document.tobytes(garbage=4, deflate=True))
            self._redo_stack.clear()
        except Exception:
            pass
        for index in sel_before:
            page = self.pdf_document[index]
            page.set_rotation((page.rotation + angle) % 360)
        self.mark_as_unsaved()
        self._thumb_cache.clear(); self._page_cache.clear()
        self.load_thumbnails()
        self.load_document_view()
        # restore multi-selection
        sel_model = self.thumbnail_widget.selectionModel()
        sel_model.clearSelection()
        for idx in sel_before:
            item = self.thumbnail_widget.item(min(idx, self.thumbnail_widget.count()-1))
            if item:
                sel_model.select(self.thumbnail_widget.indexFromItem(item), QItemSelectionModel.SelectionFlag.Select)
        self._suppress_scroll_sync = False
        QTimer.singleShot(0, lambda: self.scroll_to_page(min(sel_before)))
        self.show_status(self.t('status_rotated'))

    def goto_page(self):
        try:
            page_num = int(self.page_input.text()) - 1
            if 0 <= page_num < self.pdf_document.page_count:
                self.scroll_to_page(page_num)
        except (ValueError, AttributeError):
            self.update_page_info()

    def zoom_in(self):
        if self.pdf_document:
            self._apply_zoom(min(5.0, self.zoom_level * 1.25))

    def zoom_out(self):
        if self.pdf_document:
            self._apply_zoom(max(0.25, self.zoom_level / 1.25))

    def _apply_zoom(self, zoom: float, target_page: Optional[int] = None):
        target_page = self.current_page if target_page is None else max(0, min(target_page, self.pdf_document.page_count - 1))
        self.zoom_level = max(0.1, min(5.0, zoom))
        self._page_cache.clear()
        self.load_document_view()
        QTimer.singleShot(0, lambda: self.scroll_to_page(target_page))

    def fit_to_width(self):
        if not self.pdf_document:
            QMessageBox.information(self, self.app_name, self.t('alert_no_pdf'))
            return
        page = self.pdf_document[self.current_page]
        viewport_width = max(1, self.scroll_area.viewport().width() - 20)
        effective_width = viewport_width
        if getattr(self, 'dual_page_view', False):
            effective_width = max(1, (viewport_width - 40) / 2)
        page_width = page.rect.width
        if page_width <= 0:
            return
        scale = effective_width / page_width
        self._apply_zoom(scale)

    def fit_to_height(self):
        if not self.pdf_document:
            QMessageBox.information(self, self.app_name, self.t('alert_no_pdf'))
            return
        page = self.pdf_document[self.current_page]
        viewport_height = max(1, self.scroll_area.viewport().height() - 20)
        page_height = page.rect.height
        if page_height <= 0:
            return
        scale = viewport_height / page_height
        self._apply_zoom(scale)

    def set_page_view_mode(self, mode: str):
        dual = mode == 'dual'
        if getattr(self, 'dual_page_view', False) == dual:
            return
        self.dual_page_view = dual
        try:
            if hasattr(self, 'settings'):
                self.settings.setValue('dual_page_view', int(dual))
        except Exception:
            pass
        if hasattr(self, 'single_page_action'):
            self.single_page_action.setChecked(not dual)
        if hasattr(self, 'dual_page_action'):
            self.dual_page_action.setChecked(dual)
        self._page_cache.clear()
        self.load_document_view()
        QTimer.singleShot(0, lambda: self.scroll_to_page(self.current_page))

    def print_document(self):
        if not self.pdf_document:
            QMessageBox.information(self, self.app_name, self.t('alert_no_pdf'))
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        painter = QPainter()
        self.show_status(self.t('status_printing'), busy=True)
        success = False
        try:
            if not painter.begin(printer):
                raise RuntimeError("Failed to initialize printer")
            for page_index in range(self.pdf_document.page_count):
                if page_index > 0:
                    printer.newPage()
                page = self.pdf_document[page_index]
                zoom = printer.resolution() / 72.0
                matrix = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=matrix, alpha=False, colorspace=fitz.csRGB)
                fmt = QImage.Format.Format_RGB888
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
                target_rect = painter.viewport()
                scaled = img.scaled(target_rect.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                x = target_rect.x() + (target_rect.width() - scaled.width()) // 2
                y = target_rect.y() + (target_rect.height() - scaled.height()) // 2
                painter.drawImage(QRect(x, y, scaled.width(), scaled.height()), scaled)
            success = True
        except Exception as e:
            QMessageBox.critical(self, self.app_name, f"{self.t('print_error')}\n{e}")
            self.clear_status()
        finally:
            if painter.isActive():
                painter.end()
        if success:
            self.show_status(self.t('status_print_done'))

    def configure_ghostscript_path(self):
        if not hasattr(self, 'settings'):
            QMessageBox.warning(self, self.app_name, self.t('ghostscript_not_found'))
            return
        caption = self.t('ghostscript_select')
        filt = 'Executables (*.exe)' if sys.platform.startswith('win') else 'All Files (*)'
        file_path, _ = QFileDialog.getOpenFileName(self, caption, '', filt)
        if not file_path:
            return
        self._cached_ghostscript_path = file_path
        try:
            self.settings.setValue('ghostscript_path', file_path)
        except Exception:
            pass
        QMessageBox.information(self, self.app_name, self.t('ghostscript_set'))

    def _prompt_configure_ghostscript(self) -> bool:
        if sys.platform.startswith('win'):
            return self._prompt_elevated_install(None)

        msg = QMessageBox(self)
        msg.setWindowTitle(self.app_name)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText(self.t('ghostscript_prompt'))
        install_btn = msg.addButton(self.t('ghostscript_install'), QMessageBox.ButtonRole.AcceptRole)
        cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(install_btn)
        msg.exec()
        if msg.clickedButton() == install_btn:
            if self.t('ghostscript_install_notice') != 'ghostscript_install_notice':
                QMessageBox.information(self, self.app_name, self.t('ghostscript_install_notice'))
            return self._install_ghostscript_via_terminal()
        return False

    def _ensure_ghostscript_ready(self, resume_payload: Optional[dict] = None) -> bool:
        if self._resolve_ghostscript():
            return True
        if self._ensure_bundled_ghostscript_local(show_feedback=True):
            return True
        return self._prompt_elevated_install(resume_payload)

    def _prompt_elevated_install(self, resume_payload: Optional[dict], allow_inline_resume: bool = False) -> bool:
        msg = QMessageBox(self)
        msg.setWindowTitle(self.app_name)
        msg.setIcon(QMessageBox.Icon.Information)
        message_key = 'ghostscript_install_notice'
        if sys.platform == 'darwin':
            mac_notice = self.t('ghostscript_install_notice_mac')
            if mac_notice != 'ghostscript_install_notice_mac':
                message_key = 'ghostscript_install_notice_mac'
        message = self.t(message_key)
        if message == message_key:
            message = self.t('ghostscript_prompt')
        msg.setText(message)
        msg.setStandardButtons(QMessageBox.StandardButton.NoButton)
        install_text = self.t('ghostscript_install_proceed') if self.t('ghostscript_install_proceed') != 'ghostscript_install_proceed' else self.t('ghostscript_install')
        cancel_text = self.t('ghostscript_install_cancel') if self.t('ghostscript_install_cancel') != 'ghostscript_install_cancel' else self.t('btn_cancel')
        install_btn = msg.addButton(install_text, QMessageBox.ButtonRole.AcceptRole)
        cancel_btn = msg.addButton(cancel_text, QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(install_btn)
        msg.exec()
        if msg.clickedButton() == install_btn:
            if sys.platform.startswith('win'):
                if self._is_running_as_admin():
                    success = self._install_ghostscript_windows()
                    if success and allow_inline_resume:
                        self._resume_post_install(resume_payload)
                    return success
                self._launch_elevated_installer(resume_payload)
                return False
            success = self._install_ghostscript_via_terminal()
            if success and allow_inline_resume:
                self._resume_post_install(resume_payload)
            return success
        return False

    def _read_state_file(self, state_path: str) -> Optional[dict]:
        if not state_path or not os.path.isfile(state_path):
            return None
        try:
            with open(state_path, 'r', encoding='utf-8') as fp:
                return json.load(fp)
        except Exception as err:
            QMessageBox.warning(self, self.app_name, f"Failed to read state file.\n{err}")
            return None

    def _write_state_file(self, state_path: str, state: dict) -> bool:
        try:
            with open(state_path, 'w', encoding='utf-8') as fp:
                json.dump(state, fp, ensure_ascii=False, indent=2)
            return True
        except Exception as err:
            QMessageBox.warning(self, self.app_name, f"Failed to persist state.\n{err}")
            return False

    def _add_state_log(self, state: dict, message: str) -> None:
        try:
            logs = state.setdefault('log', [])
            logs.append({'time': time.time(), 'event': message})
        except Exception:
            pass

    def _launch_post_install_app(self, state_path: str, state: dict) -> bool:
        if not state_path:
            return False
        try:
            if getattr(sys, 'frozen', False):
                program = sys.executable
                params = f'--post-install "{state_path}"'
                if sys.platform.startswith('win'):
                    result = ctypes.windll.shell32.ShellExecuteW(None, 'open', program, params, None, 1)
                    return result > 32
                subprocess.Popen([program, '--post-install', state_path])
                return True
            program = sys.executable
            script = os.path.abspath(__file__)
            if sys.platform.startswith('win'):
                params = f'"{script}" --post-install "{state_path}"'
                result = ctypes.windll.shell32.ShellExecuteW(None, 'open', program, params, None, 1)
                return result > 32
            subprocess.Popen([program, script, '--post-install', state_path])
            return True
        except Exception as err:
            QMessageBox.warning(self, self.app_name, f"{self.t('ghostscript_install_failed')}\n{err}")
        return False

    def _localize_bool(self, value: bool) -> str:
        mapping = {
            'ko': ('예', '아니오'),
            'ja': ('はい', 'いいえ'),
            'zh-CN': ('是', '否'),
            'zh-TW': ('是', '否'),
            'en': ('Yes', 'No')
        }
        yes_no = mapping.get(self.language, ('Yes', 'No'))
        return yes_no[0] if value else yes_no[1]

    def _launch_elevated_installer(self, resume_payload: Optional[dict]) -> None:
        if not sys.platform.startswith('win'):
            QMessageBox.warning(self, self.app_name, self.t('ghostscript_install_manual'))
            return

        state = {
            'timestamp': time.time(),
            'language': getattr(self, 'language', 'ko'),
            'current_file': getattr(self, 'current_file', None),
            'resume_payload': resume_payload,
            'last_dir': None,
            'phase': 'request',
            'post_launch_triggered': False
        }
        self._add_state_log(state, 'request-created')
        try:
            if hasattr(self, 'settings'):
                state['last_dir'] = self.settings.value('last_dir', type=str)
        except Exception:
            state['last_dir'] = None

        state_path = os.path.join(tempfile.gettempdir(), f'yongpdf_resume_{uuid.uuid4().hex}.json')
        if not self._write_state_file(state_path, state):
            return

        if getattr(sys, 'frozen', False):
            program = sys.executable
            parameters = f'--resume-install "{state_path}"'
        else:
            program = sys.executable
            script = os.path.abspath(__file__)
            parameters = f'"{script}" --resume-install "{state_path}"'

        try:
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", program, parameters, None, 1)
        except Exception as err:
            QMessageBox.critical(self, self.app_name, f"{self.t('ghostscript_install_failed')}\n{err}")
            try:
                os.remove(state_path)
            except Exception:
                pass
            return

        if result <= 32:
            QMessageBox.critical(self, self.app_name, f"{self.t('ghostscript_install_failed')}\ncode={result}")
            try:
                os.remove(state_path)
            except Exception:
                pass
            return

        self._add_state_log(state, f'runas-shell-executed:{result}')
        self._write_state_file(state_path, state)
        QApplication.instance().quit()

    def _handle_resume_state(self, state_path: str) -> None:
        state = self._read_state_file(state_path)
        if not state:
            return
        target_language = state.get('language')
        if target_language and target_language != getattr(self, 'language', 'ko'):
            self.set_language(target_language)

        state['phase'] = 'installing'
        self._add_state_log(state, 'admin-install-start')
        self._write_state_file(state_path, state)

        def perform_install():
            install_success = False
            install_error = ''
            try:
                install_success = self._install_ghostscript_windows()
            except Exception as err:
                install_error = str(err)
            state['install_success'] = bool(install_success)
            if install_error:
                state['install_error'] = install_error
            state['phase'] = 'installed'
            state['installed_at'] = time.time()
            state['post_launch_triggered'] = False
            self._add_state_log(state, f'admin-install-result:success={install_success}')
            if not self._write_state_file(state_path, state):
                return
            if install_success:
                launched = self._launch_post_install_app(state_path, state)
                if launched:
                    state['post_launch_triggered'] = True
                    self._add_state_log(state, 'post-launch-dispatched')
                    self._write_state_file(state_path, state)
                    QTimer.singleShot(200, QApplication.instance().quit)
                    return
            # If launch failed or installation failed, restore window and report
            self.show()
            if install_success:
                self._add_state_log(state, 'post-launch-failed')
                QMessageBox.warning(self, self.app_name, self.t('ghostscript_resume_failed').format(error='launch failed'))
            else:
                self._add_state_log(state, f'install-failed:{install_error}')
                QMessageBox.critical(self, self.app_name, self.t('ghostscript_resume_failed').format(error=install_error or 'unknown'))
            self._write_state_file(state_path, state)

        self.hide()
        QTimer.singleShot(200, perform_install)

    def _handle_post_install_state(self, state_path: str) -> None:
        state = self._read_state_file(state_path)
        if not state:
            return

        target_language = state.get('language')
        if target_language and target_language != getattr(self, 'language', 'ko'):
            self.set_language(target_language)

        pending_file = state.get('current_file')
        if pending_file:
            self._reopen_previous_document(pending_file)

        install_success = bool(state.get('install_success', False))
        install_error = state.get('install_error')
        resume_payload = state.get('resume_payload')

        self._add_state_log(state, f'post-install-start success={install_success}')
        self._write_state_file(state_path, state)

        QTimer.singleShot(200, lambda: self._complete_post_install(state_path, state, install_success, install_error, resume_payload))

    def _reopen_previous_document(self, target_path: str) -> bool:
        if not target_path or not os.path.isfile(target_path):
            return False
        if self.current_file == target_path and self.pdf_document:
            return True
        try:
            self.open_file(file_path=target_path)
            return True
        except Exception as err:
            QMessageBox.warning(self, self.app_name, f"Failed to reopen previous PDF.\n{err}")
            return False

    def _complete_post_install(self, state_path: str, state: dict, install_success: bool, install_error: Optional[str], resume_payload: Optional[dict]) -> None:
        if install_success:
            if resume_payload and resume_payload.get('type') == 'advanced_compress':
                self._add_state_log(state, 'prompt-resume')
                self._write_state_file(state_path, state)
                try:
                    self._prompt_resume_compression(resume_payload)
                except Exception as err:
                    QMessageBox.warning(self, self.app_name, f"{self.t('ghostscript_resume_failed').format(error=str(err))}")
            else:
                QMessageBox.information(self, self.t('ghostscript_resume_title'), self.t('ghostscript_local_install_done'))
        else:
            message = self.t('ghostscript_resume_failed').format(error=install_error or 'unknown')
            QMessageBox.critical(self, self.app_name, message)

        try:
            backup_path = state_path + '.done'
            if os.path.isfile(backup_path):
                os.remove(backup_path)
            os.replace(state_path, backup_path)
        except Exception:
            try:
                os.remove(state_path)
            except Exception:
                pass

    def _prompt_resume_compression(self, payload: dict) -> None:
        input_path = payload.get('input') or self.current_file
        output_path = payload.get('output')
        if not input_path or not os.path.isfile(input_path):
            QMessageBox.warning(self, self.app_name, self.t('ghostscript_resume_failed').format(error='input missing'))
            return
        if self.current_file != input_path:
            try:
                self.load_pdf_from_path(input_path)
            except Exception as err:
                QMessageBox.warning(self, self.app_name, f"Failed to reopen PDF.\n{err}")
                return

        dpi_color = payload.get('dpi_color', 72)
        dpi_gray = payload.get('dpi_gray', 72)
        dpi_mono = payload.get('dpi_mono', 72)
        preserve_vector = self._localize_bool(payload.get('preserve_vector', True))

        message = self.t('ghostscript_resume_prompt').format(
            output=output_path or '-',
            dpi_color=dpi_color,
            dpi_gray=dpi_gray,
            dpi_mono=dpi_mono,
            preserve_vector=preserve_vector
        )

        reply = QMessageBox.question(
            self,
            self.t('ghostscript_resume_title'),
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._ghostscript_inline_attempted = False
        if not output_path:
            self.show_compression_settings()
            return
        self.advanced_compress_pdf(
            input_path,
            output_path,
            dpi_color=dpi_color,
            dpi_gray=dpi_gray,
            dpi_mono=dpi_mono,
            preserve_vector=payload.get('preserve_vector', True)
        )


    def _ghostscript_install_command(self) -> Optional[tuple[list[str], bool, str]]:
        if sys.platform.startswith('win'):
            if shutil.which('winget'):
                return ([
                    'winget', 'install', '--id', 'ArtifexSoftware.Ghostscript', '-e',
                    '--accept-source-agreements', '--accept-package-agreements', '--silent'
                ], False, 'winget')
            if shutil.which('choco'):
                return (['choco', 'install', 'ghostscript', '-y'], False, 'choco')
            return None
        if sys.platform == 'darwin':
            if shutil.which('brew'):
                return (['/bin/bash', '-lc', 'brew install ghostscript'], True, 'Homebrew')
            return None
        # For other platforms, automatic install is not attempted to avoid requiring elevated privileges.
        return None

    def _install_ghostscript_via_terminal(self) -> bool:
        existing = self._resolve_ghostscript()
        if existing:
            self._cached_ghostscript_path = existing
            try:
                if hasattr(self, 'settings'):
                    self.settings.setValue('ghostscript_path', existing)
            except Exception:
                pass
            if self.t('ghostscript_install_already') != 'ghostscript_install_already':
                try:
                    self.statusBar().showMessage(self.t('ghostscript_install_already'), 4000)
                except Exception:
                    pass
            return True

        if sys.platform.startswith('win'):
            if self._ensure_bundled_ghostscript_local(show_feedback=True):
                return True

        if sys.platform.startswith('win'):
            return self._install_ghostscript_windows()

        cmd_info = self._ghostscript_install_command()
        if not cmd_info:
            if sys.platform == 'darwin':
                QMessageBox.information(self, self.app_name, self.t('ghostscript_install_missing_mac'))
                try:
                    webbrowser.open('https://brew.sh/')
                except Exception:
                    pass
            else:
                QMessageBox.information(self, self.app_name, self.t('ghostscript_install_missing_pm'))
            try:
                webbrowser.open("https://ghostscript.com/releases/index.html")
                QMessageBox.information(self, self.app_name, self.t('ghostscript_install_manual'))
            except Exception:
                pass
            return False

        command, use_shell, manager_label = cmd_info
        previous_cached_path = getattr(self, '_cached_ghostscript_path', None)
        self._cached_ghostscript_path = None
        progress = QProgressDialog(self.t('ghostscript_installing').format(manager=manager_label), None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()

        self.show_status(self.t('ghostscript_installing').format(manager=manager_label), busy=True)

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        if use_shell:
            process.setProgram(command[0])
            process.setArguments(command[1:])
        else:
            process.setProgram(command[0])
            process.setArguments(command[1:])

        output_chunks: list[str] = []

        def _collect_output():
            try:
                data = process.readAll().data().decode('utf-8', 'ignore')
            except Exception:
                data = ''
            if data:
                output_chunks.append(data)

        process.readyReadStandardOutput.connect(_collect_output)
        process.readyReadStandardError.connect(_collect_output)

        process.start()
        if not process.waitForStarted(10000):
            progress.close()
            self.clear_status()
            QMessageBox.critical(self, self.app_name, self.t('ghostscript_install_failed'))
            return False

        while process.state() != QProcess.ProcessState.NotRunning:
            process.waitForFinished(200)
            QApplication.processEvents()

        progress.close()

        # Capture any trailing output
        _collect_output()
        combined_output = ''.join(output_chunks).strip()

        exit_status = process.exitStatus()
        exit_code = process.exitCode()
        normalized_output = combined_output.lower()
        success_patterns = (
            'already installed',
            'successfully installed',
            'installation completed',
            'was installed',
            'is already installed',
            'already the newest version',
            '설치되어 있습니다',
            '설치가 완료되었습니다',
            '설치 성공',
            '已安裝',
            '已安装',
            'インストールされています',
            'インストールされました'
        )
        success_output = any(pattern in normalized_output for pattern in success_patterns)
        success_exit = exit_status == QProcess.ExitStatus.NormalExit and exit_code in (0, 3010)

        detected = self._resolve_ghostscript()
        # Treat newly detected executable as success even if exit status was atypical
        detected_is_new = detected and detected != previous_cached_path

        if success_exit or success_output or detected_is_new:
            self.show_status(self.t('ghostscript_install_success'))
            if detected:
                QMessageBox.information(
                    self,
                    self.app_name,
                    f"{self.t('ghostscript_install_success')}\n{detected}"
                )
                return True
            QMessageBox.warning(self, self.app_name, self.t('ghostscript_install_check_path'))
            return False

        self.clear_status()
        message = self.t('ghostscript_install_failed')
        if combined_output:
            message = f"{message}\n\n{combined_output}"
        QMessageBox.critical(self, self.app_name, message)
        return False

    def _ensure_bundled_ghostscript_local(self, show_feedback: bool = False) -> bool:
        bundled = self._find_bundled_ghostscript()
        if not bundled or not os.path.isfile(bundled):
            return False

        progress: Optional[QProgressDialog] = None
        if show_feedback:
            progress = QProgressDialog(self.t('ghostscript_local_installing'), None, 0, 0, self)
            progress.setWindowModality(Qt.WindowModality.ApplicationModal)
            progress.setCancelButton(None)
            progress.show()
            QApplication.processEvents()
            self.show_status(self.t('ghostscript_local_installing'), busy=True)

        try:
            previous_path = getattr(self, '_cached_ghostscript_path', None)
            deployed = self._deploy_bundled_ghostscript(bundled)
            final_path = self._normalize_ghostscript_executable(deployed or bundled)
            if not final_path or not os.path.isfile(final_path):
                raise RuntimeError(self.t('ghostscript_install_check_path'))

            same_as_previous = False
            if previous_path and os.path.isfile(previous_path):
                try:
                    same_as_previous = os.path.samefile(previous_path, final_path)
                except Exception:
                    same_as_previous = os.path.abspath(previous_path) == os.path.abspath(final_path)

            self._cached_ghostscript_path = final_path
            try:
                if hasattr(self, 'settings'):
                    self.settings.setValue('ghostscript_path', final_path)
            except Exception:
                pass

            if show_feedback:
                if same_as_previous:
                    self.clear_status()
                else:
                    self.show_status(self.t('ghostscript_local_install_done'))
                    QTimer.singleShot(2000, self.clear_status)

            if same_as_previous:
                return False
            return True
        except Exception as err:
            if show_feedback:
                self.clear_status()
                QMessageBox.warning(self, self.app_name, f"{self.t('ghostscript_local_install_failed')}\n{err}")
            return False
        finally:
            if progress:
                progress.close()


    def _find_bundled_ghostscript(self) -> Optional[str]:
        candidate_names = ['gswin64c.exe', 'gswin32c.exe'] if sys.platform.startswith('win') else ['gs']
        possible_roots: list[str] = []

        try:
            source_dir = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            source_dir = os.getcwd()
        possible_roots.append(source_dir)

        exec_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else source_dir
        possible_roots.append(exec_dir)
        possible_roots.append(getattr(sys, '_MEIPASS', exec_dir))

        static_dirs = [os.path.join(root, 'static') for root in possible_roots]
        ghost_dirs = [os.path.join(root, 'ghostscript') for root in possible_roots]
        vendor_dirs = [os.path.join(root, 'vendor', 'ghostscript') for root in possible_roots]
        possible_roots.extend(static_dirs)
        possible_roots.extend(ghost_dirs)
        possible_roots.extend(vendor_dirs)

        bundle_env = os.environ.get('YONGPDF_GHOSTSCRIPT_DIR')
        if bundle_env:
            possible_roots.append(bundle_env)

        search_roots: list[str] = []
        seen: set[str] = set()
        for root in possible_roots:
            if not root:
                continue
            normalized = os.path.normpath(root)
            if normalized in seen:
                continue
            seen.add(normalized)
            search_roots.append(normalized)

        relative_patterns = [
            '{name}',
            os.path.join('bin', '{name}'),
            os.path.join('ghostscript', '{name}'),
            os.path.join('ghostscript', 'bin', '{name}'),
            os.path.join('resources', 'ghostscript', '{name}'),
            os.path.join('resources', 'ghostscript', 'bin', '{name}'),
            os.path.join('windows', '{name}'),
        ]

        for root in search_roots:
            try:
                if os.path.isfile(root) and os.path.basename(root) in candidate_names:
                    return root
            except Exception:
                continue

            if not os.path.isdir(root):
                continue

            for name in candidate_names:
                for pattern in relative_patterns:
                    candidate = os.path.join(root, pattern.format(name=name))
                    if os.path.isfile(candidate):
                        return candidate

            try:
                pattern = os.path.join(root, '**', 'gswin??c.exe' if sys.platform.startswith('win') else 'gs')
                matches = glob.glob(pattern, recursive=True)
                for match in matches:
                    if os.path.isfile(match):
                        return match
            except Exception:
                pass

        return None

    def _find_bundled_ghostscript_installer(self) -> Optional[str]:
        if not sys.platform.startswith('win'):
            return None
        possible_roots: list[str] = []
        try:
            source_dir = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            source_dir = os.getcwd()
        possible_roots.append(source_dir)
        exec_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else source_dir
        possible_roots.append(exec_dir)
        possible_roots.append(getattr(sys, '_MEIPASS', exec_dir))

        seed_roots = list(possible_roots)
        for root in seed_roots:
            possible_roots.append(os.path.join(root, 'ghostscript'))
            possible_roots.append(os.path.join(root, 'static', 'ghostscript'))
            possible_roots.append(os.path.join(root, 'static'))
            possible_roots.append(os.path.join(root, 'vendor', 'ghostscript'))

        installer_candidates: list[str] = []
        seen: set[str] = set()
        for base in possible_roots:
            if not base or not os.path.isdir(base):
                continue
            normalized = os.path.normpath(base)
            if normalized in seen:
                continue
            seen.add(normalized)
            pattern = os.path.join(normalized, '**', 'gs*?.exe')
            try:
                for match in glob.glob(pattern, recursive=True):
                    name = os.path.basename(match).lower()
                    if not name.endswith('.exe'):
                        continue
                    if name.endswith('c.exe'):
                        continue
                    if 'setup' in name or 'install' in name or name.endswith('w32.exe') or name.endswith('w64.exe'):
                        installer_candidates.append(match)
            except Exception:
                continue

        if not installer_candidates:
            return None
        arch = platform.machine().lower()
        prefer_suffix = 'w64' if '64' in arch else 'w32'

        def score(path: str) -> tuple[int, float]:
            name = os.path.basename(path).lower()
            suffix_score = 2 if prefer_suffix in name else (1 if 'w32' in name or 'w64' in name else 0)
            if '10060' in name or '10.06.0' in name:
                suffix_score += 1
            return (suffix_score, os.path.getsize(path))

        installer_candidates.sort(key=score, reverse=True)
        return installer_candidates[0]

    def _deploy_bundled_ghostscript(self, executable: str) -> Optional[str]:
        if not executable or not os.path.isfile(executable):
            return None

        exe_name = os.path.basename(executable)
        bundle_root = os.path.dirname(executable)
        if os.path.basename(bundle_root).lower() == 'bin':
            bundle_root = os.path.dirname(bundle_root)

        if sys.platform.startswith('win'):
            target_base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
        else:
            target_base = os.path.join(os.path.expanduser('~'), '.local', 'share')

        target_root = os.path.join(target_base, 'YongPDF', 'ghostscript')
        os.makedirs(target_root, exist_ok=True)

        dest_root = os.path.join(target_root, os.path.basename(bundle_root.rstrip(os.sep)) or 'bundle')
        try:
            if os.path.isdir(dest_root):
                for root, _, files in os.walk(dest_root):
                    if exe_name in files:
                        return os.path.join(root, exe_name)
            shutil.copytree(bundle_root, dest_root, dirs_exist_ok=True)
            for root, _, files in os.walk(dest_root):
                if exe_name in files:
                    return os.path.join(root, exe_name)
        except Exception:
            return None
        return None

    def _is_running_as_admin(self) -> bool:
        if not sys.platform.startswith('win'):
            return False
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def _install_ghostscript_windows(self) -> bool:
        if not sys.platform.startswith('win'):
            QMessageBox.warning(self, self.app_name, self.t('ghostscript_install_manual'))
            return False

        installer = self._find_bundled_ghostscript_installer()
        bundled_runtime = self._find_bundled_ghostscript()

        if not installer and not bundled_runtime:
            QMessageBox.critical(
                self,
                self.app_name,
                f"{self.t('ghostscript_install_failed')}\n{self.t('ghostscript_not_found')}"
            )
            return False

        progress_label = self.t('ghostscript_installing').format(manager='Ghostscript Installer' if installer else 'Bundled Ghostscript')
        progress = QProgressDialog(progress_label, None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()
        self.show_status(progress_label, busy=True)

        try:
            if installer:
                cmd = [installer, '/S']
                try:
                    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
                except Exception as err:
                    raise RuntimeError(f"{err}")

                exit_code = result.returncode
                if exit_code not in (0, 3010):
                    output = '\n'.join(filter(None, [result.stdout, result.stderr])).strip()
                    raise RuntimeError(f"Installer exit code {exit_code}\n{output}")
            else:
                if not bundled_runtime or not os.path.isfile(bundled_runtime):
                    raise RuntimeError(self.t('ghostscript_not_found'))
                self._deploy_bundled_runtime_into_program_files(bundled_runtime)

            detected = None
            for _ in range(6):
                detected = self._resolve_ghostscript()
                if detected and os.path.isfile(detected):
                    break
                time.sleep(0.5)
            if not detected or not os.path.isfile(detected):
                raise RuntimeError(self.t('ghostscript_install_check_path'))

            self._cached_ghostscript_path = detected
            try:
                if hasattr(self, 'settings'):
                    self.settings.setValue('ghostscript_path', detected)
            except Exception:
                pass

            self.show_status(self.t('ghostscript_install_success'))
            try:
                self.statusBar().showMessage(self.t('ghostscript_install_success'), 5000)
            except Exception:
                pass
            QMessageBox.information(
                self,
                self.app_name,
                f"{self.t('ghostscript_install_success')}\n{detected}"
            )
            QTimer.singleShot(2000, self.clear_status)
            return True
        except Exception as err:
            QMessageBox.critical(self, self.app_name, f"{self.t('ghostscript_install_failed')}\n{err}")
            self.clear_status()
            return False
        finally:
            progress.close()

    def _deploy_bundled_runtime_into_program_files(self, runtime_path: str) -> None:
        exe_name = os.path.basename(runtime_path)
        bundle_bin_dir = os.path.dirname(runtime_path)
        bundle_root = bundle_bin_dir
        if os.path.basename(bundle_bin_dir).lower() == 'bin':
            bundle_root = os.path.dirname(bundle_bin_dir)

        version_name = os.path.basename(bundle_root.rstrip(os.sep)) or 'ghostscript'
        program_root = os.environ.get('ProgramFiles(x86)') or os.environ.get('ProgramFiles')
        if not program_root:
            raise RuntimeError(self.t('ghostscript_program_files_missing'))

        target_root = os.path.join(program_root, 'gs', version_name)
        os.makedirs(os.path.join(program_root, 'gs'), exist_ok=True)

        if os.path.isdir(bundle_root):
            shutil.copytree(bundle_root, target_root, dirs_exist_ok=True)
        else:
            os.makedirs(target_root, exist_ok=True)
            shutil.copy2(runtime_path, os.path.join(target_root, exe_name))

    def _normalize_ghostscript_executable(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return path
        try:
            base = os.path.basename(path).lower()
            if sys.platform.startswith('win'):
                directory = os.path.dirname(path)
                if base in ('gswin32.exe', 'gswin32c.exe', 'gswin64.exe', 'gswin64c.exe'):
                    if not base.endswith('c.exe'):
                        candidate = os.path.join(directory, base.replace('.exe', 'c.exe'))
                        if os.path.isfile(candidate):
                            return candidate
                elif base == 'gs.exe':
                    for candidate_name in ('gswin64c.exe', 'gswin32c.exe'):
                        candidate = os.path.join(directory, candidate_name)
                        if os.path.isfile(candidate):
                            return candidate
        except Exception:
            pass
        return path

    def _resolve_ghostscript(self) -> Optional[str]:
        if GS_FIXED_PATH and os.path.isfile(GS_FIXED_PATH):
            self._cached_ghostscript_path = GS_FIXED_PATH
            try:
                if hasattr(self, 'settings'):
                    self.settings.setValue('ghostscript_path', GS_FIXED_PATH)
            except Exception:
                pass
            return GS_FIXED_PATH
        if getattr(self, '_cached_ghostscript_path', None) and os.path.isfile(self._cached_ghostscript_path):
            return self._normalize_ghostscript_executable(self._cached_ghostscript_path)
        custom_path = None
        try:
            if hasattr(self, 'settings'):
                custom_path = self.settings.value('ghostscript_path', type=str)
        except Exception:
            custom_path = None
        if custom_path and os.path.isfile(custom_path):
            self._cached_ghostscript_path = custom_path
            return self._normalize_ghostscript_executable(custom_path)
        env_path = os.environ.get('GHOSTSCRIPT_PATH')
        if env_path and os.path.isfile(env_path):
            self._cached_ghostscript_path = env_path
            return self._normalize_ghostscript_executable(env_path)
        if sys.platform.startswith('win'):
            program_dirs = []
            for env_var in ('ProgramFiles', 'ProgramFiles(x86)'):
                base = os.environ.get(env_var)
                if base:
                    candidate_root = os.path.join(base, 'gs')
                    if os.path.isdir(candidate_root):
                        program_dirs.append(candidate_root)
            for root in program_dirs:
                try:
                    versions = sorted(os.listdir(root), reverse=True)
                except Exception:
                    continue
                for version in versions:
                    bin_dir = os.path.join(root, version, 'bin')
                    if not os.path.isdir(bin_dir):
                        continue
                    for name in ('gswin64c.exe', 'gswin32c.exe', 'gswin64.exe', 'gswin32.exe', 'gs.exe'):
                        candidate = os.path.join(bin_dir, name)
                        if os.path.isfile(candidate):
                            normalized = self._normalize_ghostscript_executable(candidate)
                            if normalized and os.path.isfile(normalized):
                                self._cached_ghostscript_path = normalized
                                try:
                                    if hasattr(self, 'settings'):
                                        self.settings.setValue('ghostscript_path', normalized)
                                except Exception:
                                    pass
                                return normalized
            explicit_candidates = []
            pf_x86 = os.environ.get('ProgramFiles(x86)')
            pf = os.environ.get('ProgramFiles')
            if pf_x86:
                explicit_candidates.append(os.path.join(pf_x86, 'gs', 'gs10.06.0', 'bin', 'gswin32c.exe'))
                explicit_candidates.append(os.path.join(pf_x86, 'gs', 'gs10.06.0', 'bin', 'gswin64c.exe'))
            if pf:
                explicit_candidates.append(os.path.join(pf, 'gs', 'gs10.06.0', 'bin', 'gswin64c.exe'))
                explicit_candidates.append(os.path.join(pf, 'gs', 'gs10.06.0', 'bin', 'gswin32c.exe'))
            for candidate in explicit_candidates:
                if candidate and os.path.isfile(candidate):
                    normalized = self._normalize_ghostscript_executable(candidate)
                    if normalized and os.path.isfile(normalized):
                        self._cached_ghostscript_path = normalized
                        try:
                            if hasattr(self, 'settings'):
                                self.settings.setValue('ghostscript_path', normalized)
                        except Exception:
                            pass
                        return normalized
        candidate_names = ['gs']
        if sys.platform.startswith('win'):
            candidate_names = ['gswin64c.exe', 'gswin32c.exe', 'gs']
        for name in candidate_names:
            found = shutil.which(name)
            if found:
                self._cached_ghostscript_path = found
                return self._normalize_ghostscript_executable(found)
        return None

    def mark_as_unsaved(self):
        self.has_unsaved_changes = True
        title = os.path.basename(self.current_file) if self.current_file else "Untitled"
        self.setWindowTitle(f"PDF Editor - *{title}")

    def _save_ui_settings(self):
        try:
            if hasattr(self, 'settings'):
                self.settings.setValue('geometry', self.saveGeometry())
                if hasattr(self, 'splitter'):
                    self.settings.setValue('splitter_sizes', self.splitter.sizes())
                self.settings.setValue('dual_page_view', int(getattr(self, 'dual_page_view', False)))
                if getattr(self, '_cached_ghostscript_path', None):
                    self.settings.setValue('ghostscript_path', self._cached_ghostscript_path)
        except Exception:
            pass

    def _prompt_save_changes(self) -> str:
        dlg = QDialog(self)
        dlg.setWindowTitle(self.app_name)
        lay = QVBoxLayout(dlg)
        msg = QLabel(self.t('unsaved_changes'))
        lay.addWidget(msg)
        btn_bar = QHBoxLayout()
        lay.addLayout(btn_bar)
        def mk(text):
            b = QPushButton(text)
            b.setMinimumWidth(120)
            return b
        btn_yes = mk(self.t('btn_yes'))
        btn_save_as = mk(self.t('btn_save_as'))
        btn_no = mk(self.t('btn_no'))
        btn_cancel = mk(self.t('btn_cancel'))
        for b in (btn_yes, btn_save_as, btn_no, btn_cancel):
            btn_bar.addWidget(b)
        result = {'value': 'cancel'}
        btn_yes.clicked.connect(lambda: (result.update(value='yes'), dlg.accept()))
        btn_save_as.clicked.connect(lambda: (result.update(value='saveas'), dlg.accept()))
        btn_no.clicked.connect(lambda: (result.update(value='no'), dlg.accept()))
        btn_cancel.clicked.connect(lambda: (result.update(value='cancel'), dlg.reject()))
        dlg.exec()
        return result['value']

    def closeEvent(self, event):
        self._close_startup_loading()
        self._close_external_loading_dialog()
        if self.has_unsaved_changes:
            choice = self._prompt_save_changes()
            if choice == 'yes':
                self.save_file()
                self._save_ui_settings()
                event.accept()
            elif choice == 'saveas':
                self.save_as_file()
                self._save_ui_settings()
                event.accept()
            elif choice == 'no':
                self._save_ui_settings()
                event.accept()
            else:
                event.ignore()
        else:
            self._save_ui_settings()
            event.accept()

    def prev_page(self):
        if self.pdf_document and self.current_page > 0:
            self.scroll_to_page(self.current_page - 1)

    def next_page(self):
        if self.pdf_document and self.current_page < self.pdf_document.page_count - 1:
            self.scroll_to_page(self.current_page + 1)

    def save_pages_as_file(self, page_indexes):
        if not self.pdf_document or not page_indexes: return
        
        if self.current_file:
            base, ext = os.path.splitext(os.path.basename(self.current_file))
            if len(page_indexes) == 1:
                default_name = os.path.join(os.path.dirname(self.current_file), f"{base}({page_indexes[0]+1}){ext}")
            else:
                default_name = os.path.join(os.path.dirname(self.current_file), f"{base}({page_indexes[0]+1}-{page_indexes[-1]+1}){ext}")
        else:
            last_dir = str(self.settings.value('last_dir', os.getcwd())) if hasattr(self, 'settings') else os.getcwd()
            default_name = os.path.join(last_dir, "Untitled.pdf")
        
        file_path, _ = QFileDialog.getSaveFileName(self, "💾 선택한 페이지 별도 저장", default_name, "PDF 파일 (*.pdf)")
        if file_path:
            new_doc = fitz.open()
            for page_index in sorted(page_indexes):
                new_doc.insert_pdf(self.pdf_document, from_page=page_index, to_page=page_index)
            new_doc.save(file_path)
            new_doc.close()

    def launch_external_editor(self):
        if not self.current_file:
            QMessageBox.information(self, self.app_name, self.t('alert_no_edit_pdf'))
            return
        if self._external_editor_process and self._external_editor_process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, self.app_name, self.t('external_editor_running'))
            return

        if self.has_unsaved_changes:
            choice = self._prompt_save_changes()
            if choice == 'yes':
                self.save_file()
            elif choice == 'saveas':
                self.save_as_file()
            elif choice == 'cancel':
                return
            if choice in ('yes', 'saveas') and self.has_unsaved_changes:
                QMessageBox.critical(self, self.app_name, self.t('save_failed'))
                return

        target_path = self.current_file
        try:
            resolved = self._resolve_external_editor_command(target_path)
            if not resolved:
                QMessageBox.critical(self, self.app_name, self.t('err_editor_missing'))
                return
            program, arguments = resolved

            self._pending_reopen_path = target_path
            self._external_previous_title = self.windowTitle()
            self._disable_external_watch()
            self._unload_document(preserve_current_file=True)
            self.setWindowTitle(f"PDF Editor - {os.path.basename(target_path)} (외부 편집 중)")
            self.statusBar().showMessage(self.t('loading_external_editor'), 4000)
            self._show_external_loading_dialog()

            process = QProcess(self)
            process.setProgram(program)
            process.setArguments(arguments)
            process.finished.connect(self._on_external_editor_finished)
            process.errorOccurred.connect(self._on_external_editor_error)
            process.started.connect(self._handle_external_editor_started)
            self._external_editor_process = process
            process.start()
        except Exception as e:
            self._external_editor_process = None
            self._close_external_loading_dialog()
            QMessageBox.critical(self, self.app_name, f"{self.t('err_editor_launch')}\n{e}")
            self._reopen_after_external(success=False)

    def _on_editor_file_changed(self, path: str):
        if not hasattr(self, '_editor_watch_path') or path != self._editor_watch_path:
            return
        if self._external_editor_process and self._external_editor_process.state() != QProcess.ProcessState.NotRunning:
            return
        if not self.pdf_document:
            return
        # Debounce slight bursts
        QTimer.singleShot(300, lambda: self._reload_from_external(path))

    def _reload_from_external(self, path: str):
        try:
            if not os.path.isfile(path):
                return
            # Keep current page; open from file to refresh cross-refs
            keep_page = self.current_page
            self._suppress_scroll_sync = True
            if self.pdf_document:
                self.pdf_document.close()
            self.pdf_document = fitz.open(path)
            self._thumb_cache.clear(); self._page_cache.clear()
            self.load_thumbnails()
            self.load_document_view()
            self._suppress_scroll_sync = False
            self.scroll_to_page(min(keep_page, self.pdf_document.page_count - 1))
            self.has_unsaved_changes = False
            self.statusBar().showMessage(self.t('external_editor_refresh_notice'), 6000)
            # Re-arm watcher (macOS sometimes removes it after change)
            self._configure_external_watch(path)
        except Exception as e:
            # Retry once later if file is locked
            QTimer.singleShot(500, lambda: self._retry_reload_external(path))

    def _retry_reload_external(self, path: str):
        try:
            if not os.path.isfile(path):
                return
            keep_page = self.current_page
            self._suppress_scroll_sync = True
            if self.pdf_document:
                self.pdf_document.close()
            self.pdf_document = fitz.open(path)
            self._thumb_cache.clear(); self._page_cache.clear()
            self.load_thumbnails()
            self.load_document_view()
            self._suppress_scroll_sync = False
            self.scroll_to_page(min(keep_page, self.pdf_document.page_count - 1))
            self._configure_external_watch(path)
        except Exception:
            if hasattr(self, 'settings') and os.path.isfile(path):
                self.settings.setValue('last_dir', os.path.dirname(path))

    def _on_external_editor_finished(self, exit_code: int, exit_status: QProcess.ExitStatus):
        self._close_external_loading_dialog()
        self._external_editor_process = None
        success = (exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0)
        self._reopen_after_external(success)

    def _on_external_editor_error(self, error: QProcess.ProcessError):
        self._close_external_loading_dialog()
        self._external_editor_process = None
        error_details = {
            QProcess.ProcessError.FailedToStart: "Failed to start the external editor. Check the executable path.",
            QProcess.ProcessError.Crashed: "The external editor terminated unexpectedly.",
            QProcess.ProcessError.Timedout: "Starting the external editor timed out.",
            QProcess.ProcessError.WriteError: "A write error occurred while communicating with the external editor.",
            QProcess.ProcessError.ReadError: "A read error occurred while communicating with the external editor.",
        }
        detail = error_details.get(error, "An unknown error occurred while launching the external editor.")
        message = f"{self.t('err_editor_launch')}\n{detail}"
        self.statusBar().showMessage(message, 6000)
        QMessageBox.critical(self, self.app_name, message)
        self._reopen_after_external(success=False)

    def _reopen_after_external(self, success: bool):
        self._close_external_loading_dialog()
        path = self._pending_reopen_path
        self._pending_reopen_path = None
        if self._external_previous_title:
            previous_title = self._external_previous_title
            self._external_previous_title = None
        else:
            previous_title = self.windowTitle()

        if not path:
            self.setWindowTitle(previous_title)
            return

        if os.path.isfile(path):
            self.open_file(file_path=path)
            self._configure_external_watch(path)
            if success:
                self.statusBar().showMessage("외부 편집을 완료하여 PDF를 다시 불러왔습니다.", 6000)
            else:
                self.statusBar().showMessage("외부 편집기 오류로 PDF를 다시 불러왔습니다.", 6000)
        else:
            QMessageBox.warning(self, "경고", "외부 편집 후 PDF 파일을 찾을 수 없습니다.")
            self._unload_document(preserve_current_file=False)
            self._disable_external_watch()
            self.setWindowTitle(previous_title)


    def show_compression_settings(self):
        if not self.current_file:
            QMessageBox.information(self, self.app_name, (self.t('alert_no_pdf') if hasattr(self,'t') else "No PDF opened to compress."))
            return
        
        dialog = PDFCompressionDialog(self, source_path=self.current_file, editor=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            settings = dialog.get_settings()
            if not settings: return

            base, ext = os.path.splitext(self.current_file)
            if settings['level'] == 'general':
                suffix = '일반압축'
            else:
                suffix = f"C{settings.get('dpi_color','')}_G{settings.get('dpi_gray','')}_M{settings.get('dpi_mono','')}압축"
            default_output = f"{base}_{suffix}{ext}"
            
            output_pdf, _ = QFileDialog.getSaveFileName(self, self.t('compress_pdf'), default_output, "PDF 파일 (*.pdf)")
            if not output_pdf: return
            
            if settings['level'] == 'general':
                self.compress_pdf(self.current_file, output_pdf, garbage=4, deflate=True, clean=True)
            else:
                resume_payload = {
                    'type': 'advanced_compress',
                    'input': self.current_file,
                    'output': output_pdf,
                    'dpi_color': settings['dpi_color'],
                    'dpi_gray': settings['dpi_gray'],
                    'dpi_mono': settings['dpi_mono'],
                    'preserve_vector': settings.get('preserve_vector', True)
                }
                if not self._ensure_ghostscript_ready(resume_payload):
                    return
                self.advanced_compress_pdf(
                    self.current_file,
                    output_pdf,
                    dpi_color=settings['dpi_color'],
                    dpi_gray=settings['dpi_gray'],
                    dpi_mono=settings['dpi_mono'],
                    preserve_vector=settings.get('preserve_vector', True)
                )

    def show_about_dialog(self):
        box = QMessageBox(self)
        box.setWindowTitle(self.app_name)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        text_html = '<br>'.join(self.t('about_text').splitlines())
        text_html += "<br/><br/><span style='font-size:11px;color:#606060'>© 2025 YongPDF · Hwang Jinsu. All rights reserved.</span>"
        box.setText(f"<div style='min-width:320px'>{text_html}</div>")
        pix = _load_static_pixmap('YongPDF_page_img.png')
        if pix:
            scaled = pix.scaled(160, 160, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            box.setIconPixmap(scaled)
        box.exec()

    def show_licenses_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.t('licenses_title') if self.language!='en' else 'Open-Source Licenses')
        lay = QVBoxLayout(dlg)
        info = QTextEdit()
        info.setReadOnly(True)
        if self.language == 'ko':
            header = (
                "본 앱은 다음 오픈소스 소프트웨어를 사용합니다.\n"
                "각 라이선스 조건을 준수하며 배포됩니다.\n\n"
            )
        elif self.language == 'ja':
            header = (
                "本アプリは以下のオープンソースソフトウェアを使用しています。\n"
                "各ライセンス条件に従って配布されています。\n\n"
            )
        elif self.language == 'zh-CN':
            header = (
                "本应用使用以下开源软件，并遵守各自许可证分发。\n\n"
            )
        elif self.language == 'zh-TW':
            header = (
                "本應用使用以下開源軟體，並遵守各自授權條款發佈。\n\n"
            )
        else:
            header = (
                "This app uses the following open-source software.\n"
                "Distributed in compliance with their licenses.\n\n"
            )
        body = (
            "PyMuPDF (MuPDF) — AGPL-3.0\n"
            "  https://pymupdf.readthedocs.io/ / https://mupdf.com/\n\n"
            "Pillow — HPND / PIL License\n"
            "  https://python-pillow.org/\n\n"
            "PyQt6 — GPLv3 / Commercial\n"
            "  https://www.riverbankcomputing.com/software/pyqt/\n\n"
            "Ghostscript (optional) — AGPL-3.0 / Commercial\n"
            "  https://ghostscript.com/\n\n"
            "PySide6 (Qt for Python, external editor) — LGPL-3.0 / Commercial\n"
            "  https://www.qt.io/qt-for-python\n\n"
            "fontTools (external editor) — MIT License\n"
            "  https://github.com/fonttools/fonttools\n\n"
            "Matplotlib (external editor) — PSF License\n"
            "  https://matplotlib.org/\n\n"
            "Icons/Emojis — as provided by system fonts.\n"
        )
        info.setPlainText(header + body)
        lay.addWidget(info)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.reject)
        btns.accepted.connect(dlg.accept)
        lay.addWidget(btns)
        dlg.resize(640, 520)
        dlg.exec()

    def compress_pdf(self, input_path: str, output_path: str, garbage: int, deflate: bool, clean: bool):
        progress = QProgressDialog(self.t('progress_compress'), None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()

        self.show_status(self.t('status_compressing'), busy=True)
        try:
            doc = fitz.open(input_path)
            doc.save(output_path, garbage=garbage, deflate=deflate, clean=clean)
            doc.close()
            self.show_status(self.t('status_compress_done'))
        except Exception as e:
            self.clear_status()
            self.statusBar().showMessage(self.t('compress_error') if self.language != 'ko' else "PDF 압축 중 오류 발생", 5000)
        finally:
            progress.close()

    def advanced_compress_pdf(self, input_path: str, output_path: str, dpi_color: int = 72, dpi_gray: int = 72, dpi_mono: int = 72, preserve_vector: bool = True):
        self._ghostscript_inline_attempted = False
        progress_message = self.t('progress_compress_adv')
        if input_path and output_path:
            progress_message = f"{progress_message}\n{os.path.basename(input_path)} → {os.path.basename(output_path)}"
        progress = QProgressDialog(progress_message, None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setCancelButton(None)
        progress.setWindowTitle(self.app_name)
        progress.setLabelText(progress_message)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        self.show_status(self.t('status_compressing'), busy=True)
        try:
            gs_path = self._resolve_ghostscript()
            if not gs_path:
                if not self._prompt_configure_ghostscript():
                    self.clear_status()
                    return
                gs_path = self._resolve_ghostscript()
                if not gs_path:
                    QMessageBox.warning(self, self.app_name, self.t('ghostscript_not_found'))
                    self.clear_status()
                    return
            gs_path = self._normalize_ghostscript_executable(gs_path)
            normalized_output = os.path.normpath(output_path)
            output_arg = f"-sOutputFile={normalized_output}"
            cmd = [
                gs_path,
                "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
                "-dPDFSETTINGS=/screen", "-dNOPAUSE", "-dQUIET", "-dBATCH",
                "-dDetectDuplicateImages=true", "-dCompressFonts=true",
                # Color images
                "-dDownsampleColorImages=true", "-dColorImageDownsampleType=/Bicubic",
                f"-dColorImageResolution={dpi_color}",
                # Grayscale images
                "-dDownsampleGrayImages=true", "-dGrayImageDownsampleType=/Bicubic",
                f"-dGrayImageResolution={dpi_gray}",
                # Monochrome images
                "-dDownsampleMonoImages=true", "-dMonoImageDownsampleType=/Bicubic",
                f"-dMonoImageResolution={dpi_mono}",
                output_arg,
                input_path
            ]
            if preserve_vector:
                cmd.extend(["-dPreserveEPSInfo=true", "-dColorConversionStrategy=/LeaveColorUnchanged"])
            try:
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            except OSError as os_err:
                if getattr(os_err, 'winerror', None) in (5, 740):
                    raise RuntimeError(self.t('compress_adv_permission_error')) from os_err
                raise RuntimeError(str(os_err)) from os_err
            if result.returncode != 0:
                stderr = (result.stderr or '').strip()
                stdout = (result.stdout or '').strip()
                combined_output = stderr or stdout
                lower_output = (combined_output or '').lower()
                if sys.platform.startswith('win') and ('error 740' in lower_output or 'win32 error 5' in lower_output or 'access is denied' in lower_output):
                    raise RuntimeError(self.t('compress_adv_permission_error'))
                raise RuntimeError(combined_output or f"exit code {result.returncode}")
            self._ghostscript_inline_attempted = False
            self.show_status(self.t('status_compress_done'))
        except Exception as e:
            perm_msg = self.t('compress_adv_permission_error')
            error_text = str(e).strip()
            if perm_msg and perm_msg in error_text:
                resume_payload = {
                    'type': 'advanced_compress',
                    'input': input_path,
                    'output': output_path,
                    'dpi_color': dpi_color,
                    'dpi_gray': dpi_gray,
                    'dpi_mono': dpi_mono,
                    'preserve_vector': preserve_vector
                }
                if sys.platform.startswith('win') and not self._ghostscript_inline_attempted:
                    self._ghostscript_inline_attempted = True
                    if self._ensure_bundled_ghostscript_local(show_feedback=True):
                        progress.close()
                        self.clear_status()
                        QTimer.singleShot(0, lambda: self.advanced_compress_pdf(
                            input_path,
                            output_path,
                            dpi_color=dpi_color,
                            dpi_gray=dpi_gray,
                            dpi_mono=dpi_mono,
                            preserve_vector=preserve_vector
                        ))
                        return
                progress.close()
                inline_ready = self._prompt_elevated_install(resume_payload, allow_inline_resume=True)
                self.clear_status()
                if inline_ready:
                    self._ghostscript_inline_attempted = False
                return
            QMessageBox.critical(self, self.app_name, f"{self.t('compress_adv_error')}\n{e}")
            self.clear_status()
        finally:
            progress.close()

    def update_current_page_on_scroll(self, value):
        if self._suppress_scroll_sync or not self.page_labels:
            return
        viewport_height = self.scroll_area.viewport().height()
        scroll_center = value + viewport_height / 2
        
        closest_page = min(
            range(len(self.page_labels)),
            key=lambda i: abs(
                self.page_labels[i].mapTo(self.document_container, QPoint(0, 0)).y()
                + self.page_labels[i].height() / 2 - scroll_center
            )
        )
        
        if self.current_page != closest_page:
            self.current_page = closest_page
            self.update_page_info()
            try:
                sel_model = self.thumbnail_widget.selectionModel()
                index = self.thumbnail_widget.model().index(self.current_page, 0)
                sel_model.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.NoUpdate)
            except Exception:
                pass

if __name__ == '__main__':
    app = QApplication(sys.argv)
    splash = _show_startup_splash(app)
    editor: Optional[PDFEditor] = None
    try:
        editor = PDFEditor()
        if splash:
            splash.showMessage(
                'PDF 문서를 준비하는 중입니다...',
                Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                QColor(72, 72, 72)
            )
            app.processEvents()

        editor.show()
        if splash:
            splash.raise_()
            splash.activateWindow()
            app.processEvents()

        if splash:
            def _finish_splash():
                if getattr(splash, '_closed', False):
                    return
                try:
                    splash.finish(editor)
                except Exception:
                    splash.close()
                splash._closed = True

            QTimer.singleShot(2000, _finish_splash)

        if RESUME_STATE_PATH:
            QTimer.singleShot(0, lambda: editor._handle_resume_state(RESUME_STATE_PATH))
        elif POST_INSTALL_STATE_PATH:
            QTimer.singleShot(0, lambda: editor._handle_post_install_state(POST_INSTALL_STATE_PATH))

    finally:
        if splash and not getattr(splash, '_closed', False):
            try:
                if editor is not None:
                    splash.finish(editor)
                else:
                    splash.close()
            except Exception:
                splash.close()
            splash._closed = True

    sys.exit(app.exec())
