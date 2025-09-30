import os
import sys
import tempfile
import traceback
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
import fitz
import io
import subprocess

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QMenu, QMenuBar,
    QStatusBar, QToolBar, QFileDialog, QDialog, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QMessageBox, QFrame, QLineEdit,
    QDialogButtonBox, QRubberBand, QSlider, QCheckBox, QProgressDialog, QRadioButton, QTextEdit
)
from PyQt6.QtCore import Qt, QSize, QPoint, QRect, QEvent, QTimer, QItemSelectionModel, QItemSelection, QSettings, QFileSystemWatcher, QProcess
from PyQt6.QtGui import QImage, QPixmap, QIcon, QAction, QTextCursor, QPainter, QColor, QWheelEvent, QActionGroup, QKeySequence, QShortcut


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
        self.app_name = "용PDF"
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
        # Scroll sync guard to prevent jumps during rerender
        self._suppress_scroll_sync = False
        
        self.setup_ui()
        self.update_page_info()
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

        self.scroll_area = PDFScrollArea(self)
        self.scroll_area.setWidget(self.document_container)
        
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
        exit_action = QAction(self.t('exit'), self)
        exit_action.triggered.connect(self.close)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        file_menu.addActions([save_action, save_as_action])
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
        tools_menu.addActions([compress_action, launch_editor_action])

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
        statusbar.addWidget(self.status_page_label)
        statusbar.addPermanentWidget(self.status_zoom_label)

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
                'file_menu': '📄 파일',
                'open': '📂 열기',
                'save': '💾 저장',
                'save_as': '📑 다른 이름으로 저장',
                'exit': '🚪 종료',
                'page_menu': '📖 페이지',
                'add_page': '🙏 페이지 추가',
                'delete_page': '🗑️ 페이지 삭제',
                'cm_delete_selected': '🗑️ 선택한 페이지 삭제',
                'cm_save_selected': '💾 선택한 페이지 별도 저장',
                'move_up': '👆 위로 이동',
                'move_down': '👇 아래로 이동',
                'rotate_left': '⤴️ 왼쪽으로 회전',
                'rotate_right': '⤵️ 오른쪽으로 회전',
                'view_menu': '🎨 보기',
                'tools_menu': '🛠️ 도구',
                'compress_pdf': '📦 PDF 압축',
                'edit_menu': '✏️ 편집',
                'undo': '↩️ 실행 취소',
                'redo': '↪️ 다시 실행',
                'language_menu': '🌐 언어',
                'korean': '한글',
                'english': 'English',
                'help_menu': '❓ 도움말', 'licenses_menu': '📜 오픈소스 라이선스', 'licenses_title': '오픈소스 라이선스',
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
                'about_text': '용PDF\n개발: Hwang Jinsu\n메일: iiish@hanmail.net\n라이선스: 프리웨어\n본 소프트웨어는 개인/업무용 무료 사용을 허용합니다.',
                'info_compress': '압축 방식을 선택하세요.\n- 일반 압축: 구조 최적화 (무손실)\n- 고급 압축: 이미지 DPI 다운샘플',
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
                'unsaved_changes': 'There are unsaved changes. Save?',
                'file_menu': '📄 File',
                'open': '📂 Open',
                'save': '💾 Save',
                'save_as': '📑 Save As',
                'exit': '🚪 Exit',
                'page_menu': '📖 Pages',
                'add_page': '🙏 Add Page',
                'delete_page': '🗑️ Delete Page',
                'cm_delete_selected': '🗑️ Delete Selected Pages',
                'cm_save_selected': '💾 Save Selected Pages',
                'move_up': '👆 Move Up',
                'move_down': '👇 Move Down',
                'rotate_left': '⤴️ Rotate Left',
                'rotate_right': '⤵️ Rotate Right',
                'view_menu': '🎨 View',
                'tools_menu': '🛠️ Tools',
                'compress_pdf': '📦 Compress PDF',
                'edit_menu': '✏️ Edit',
                'undo': '↩️ Undo',
                'redo': '↪️ Redo',
                'language_menu': '🌐 Language',
                'korean': 'Korean',
                'english': 'English',
                'help_menu': '❓ Help', 'licenses_menu': '📜 Open-Source Licenses', 'licenses_title': 'Open-Source Licenses',
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
                'err_editor_missing': 'main_codex1.py not found.',
                'err_editor_launch': 'Failed to launch external editor',
                'progress_compress': 'Compressing PDF...',
                'progress_compress_adv': 'Advanced PDF compression...',
                'compress_done': 'PDF compression completed',
                'compress_error': 'Error occurred during PDF compression',
                'compress_adv_done': 'Advanced PDF compression completed',
                'gs_missing': 'Ghostscript executable not found.\nInstall Ghostscript and add it to PATH.',
                'compress_adv_error': 'Error occurred during advanced PDF compression'
            },
            'ja': {
                'alert_no_pdf': '圧縮するPDFが開かれていません。',
                'unsaved_changes': '未保存の変更があります。保存しますか？',
                'btn_yes': 'はい', 'btn_save_as': '名前を付けて保存', 'btn_no': 'いいえ', 'btn_cancel': 'キャンセル',
                'zoom_in': '➕ 拡大', 'zoom_out': '➖ 縮小',
                'theme_light': '☀️ ライト', 'theme_dark': '🌙 ダーク',
                'theme_light_mode': '☀️ ライトモード', 'theme_dark_mode': '🌙 ダークモード',
                'status_page': 'ページ', 'status_zoom': '倍率',
                'file_menu': '📄 ファイル', 'open': '📂 開く', 'save': '💾 保存', 'save_as': '📑 名前を付けて保存', 'exit': '🚪 終了',
                'page_menu': '📖 ページ', 'add_page': '🙏 ページ追加', 'delete_page': '🗑️ ページ削除', 'cm_delete_selected': '🗑️ 選択ページを削除', 'cm_save_selected': '💾 選択ページを保存',
                'move_up': '👆 上へ移動', 'move_down': '👇 下へ移動', 'rotate_left': '⤴️ 左回転', 'rotate_right': '⤵️ 右回転',
                'view_menu': '🎨 表示', 'tools_menu': '🛠️ ツール', 'compress_pdf': '📦 PDF圧縮',
                'edit_menu': '✏️ 編集', 'undo': '↩️ 元に戻す', 'redo': '↪️ やり直し', 'language_menu': '🌐 言語', 'korean': '韓国語', 'english': '英語', 'help_menu': '❓ ヘルプ', 'about': 'ℹ️ 情報',
                'prev': '👈 前へ', 'next': '👉 次へ', 'add_short': '🙏 追加', 'delete_short': '🗑️ 削除', 'move_up_short': '👆 上へ', 'move_down_short': '👇 下へ', 'rotate_left_short': '⤴️ 左回転', 'rotate_right_short': '⤵️ 右回転', 'edit_short': '✏️ 編集',
                'about_text': 'YongPDF\n開発者: Hwang Jinsu\nメール: iiish@hanmail.net\nライセンス: フリーウェア\n本ソフトは個人/業務利用とも無料です。',
                'info_compress': '圧縮モードを選択してください。\n- 一般: 構造最適化(ロスレス)\n- 高度: 画像をDPIでダウンサンプル', 'general_compress': '一般(ロスレス、構造最適化)', 'advanced_compress': '高度(画像DPI調整)',
                'color_dpi_label': 'カラー画像 DPI (10段階)', 'gray_dpi_label': 'グレースケール画像 DPI', 'mono_dpi_label': 'モノクロ画像 DPI', 'preserve_vector': 'テキスト/ベクターを保持(画像のみ処理)',
                'estimate_prefix': '推定サイズ', 'selected_dpi': '選択DPI', 'estimate_unavailable': '推定不可', 'current': '現在', 'color': 'カラー', 'gray': 'グレー', 'mono': 'モノ'
            },
            'zh-CN': {
                'alert_no_pdf': '未打开要压缩的PDF。', 'unsaved_changes': '存在未保存的更改，是否保存？', 'btn_yes': '是', 'btn_save_as': '另存为', 'btn_no': '否', 'btn_cancel': '取消',
                'zoom_in': '➕ 放大', 'zoom_out': '➖ 缩小', 'theme_light': '☀️ 亮色', 'theme_dark': '🌙 暗色', 'theme_light_mode': '☀️ 亮色模式', 'theme_dark_mode': '🌙 暗色模式',
                'status_page': '页面', 'status_zoom': '缩放', 'file_menu': '📄 文件', 'open': '📂 打开', 'save': '💾 保存', 'save_as': '📑 另存为', 'exit': '🚪 退出',
                'page_menu': '📖 页面', 'add_page': '🙏 添加页面', 'delete_page': '🗑️ 删除页面', 'cm_delete_selected': '🗑️ 删除所选页面', 'cm_save_selected': '💾 保存所选页面',
                'move_up': '👆 上移', 'move_down': '👇 下移', 'rotate_left': '⤴️ 向左旋转', 'rotate_right': '⤵️ 向右旋转', 'view_menu': '🎨 视图', 'tools_menu': '🛠️ 工具', 'compress_pdf': '📦 压缩PDF',
                'edit_menu': '✏️ 编辑', 'undo': '↩️ 撤销', 'redo': '↪️ 重做', 'language_menu': '🌐 语言', 'korean': '韩文', 'english': '英文', 'help_menu': '❓ 帮助', 'about': 'ℹ️ 关于',
                'prev': '👈 上一页', 'next': '👉 下一页', 'add_short': '🙏 添加', 'delete_short': '🗑️ 删除', 'move_up_short': '👆 上移', 'move_down_short': '👇 下移', 'rotate_left_short': '⤴️ 左旋转', 'rotate_right_short': '⤵️ 右旋转', 'edit_short': '✏️ 编辑',
                'about_text': 'YongPDF\n开发者: Hwang Jinsu\n邮箱: iiish@hanmail.net\n许可: 免费软件\n本软件可免费用于个人/工作用途。',
                'info_compress': '请选择压缩模式。\n- 一般: 结构优化(无损)\n- 高级: 按DPI降采样图像', 'general_compress': '一般(无损, 结构优化)', 'advanced_compress': '高级(图像DPI调节)',
                'color_dpi_label': '彩色图像 DPI (10级)', 'gray_dpi_label': '灰度图像 DPI', 'mono_dpi_label': '黑白图像 DPI', 'preserve_vector': '保留文本/矢量(仅处理图像)',
                'estimate_prefix': '预计大小', 'selected_dpi': '选择的DPI', 'estimate_unavailable': '无法估计', 'current': '当前', 'color': '彩色', 'gray': '灰度', 'mono': '黑白'
            },
            'zh-TW': {
                'alert_no_pdf': '未開啟要壓縮的PDF。', 'unsaved_changes': '有未儲存的變更，是否儲存？', 'btn_yes': '是', 'btn_save_as': '另存新檔', 'btn_no': '否', 'btn_cancel': '取消',
                'zoom_in': '➕ 放大', 'zoom_out': '➖ 縮小', 'theme_light': '☀️ 亮色', 'theme_dark': '🌙 暗色', 'theme_light_mode': '☀️ 亮色模式', 'theme_dark_mode': '🌙 暗色模式',
                'status_page': '頁面', 'status_zoom': '縮放', 'file_menu': '📄 檔案', 'open': '📂 開啟', 'save': '💾 儲存', 'save_as': '📑 另存新檔', 'exit': '🚪 結束',
                'page_menu': '📖 頁面', 'add_page': '🙏 新增頁面', 'delete_page': '🗑️ 刪除頁面', 'cm_delete_selected': '🗑️ 刪除所選頁面', 'cm_save_selected': '💾 儲存所選頁面',
                'move_up': '👆 上移', 'move_down': '👇 下移', 'rotate_left': '⤴️ 向左旋轉', 'rotate_right': '⤵️ 向右旋轉', 'view_menu': '🎨 檢視', 'tools_menu': '🛠️ 工具', 'compress_pdf': '📦 壓縮PDF',
                'edit_menu': '✏️ 編輯', 'undo': '↩️ 復原', 'redo': '↪️ 取消復原', 'language_menu': '🌐 語言', 'korean': '韓文', 'english': '英文', 'help_menu': '❓ 說明', 'about': 'ℹ️ 關於',
                'prev': '👈 上一頁', 'next': '👉 下一頁', 'add_short': '🙏 新增', 'delete_short': '🗑️ 刪除', 'move_up_short': '👆 上移', 'move_down_short': '👇 下移', 'rotate_left_short': '⤴️ 左旋轉', 'rotate_right_short': '⤵️ 右旋轉', 'edit_short': '✏️ 編輯',
                'about_text': 'YongPDF\n開發者: Hwang Jinsu\n信箱: iiish@hanmail.net\n授權: 免費軟體\n本軟體可免費用於個人/商務。',
                'info_compress': '請選擇壓縮模式。\n- 一般: 結構最佳化(無損)\n- 進階: 依DPI降採樣影像', 'general_compress': '一般(無損, 結構最佳化)', 'advanced_compress': '進階(影像DPI調整)',
                'color_dpi_label': '彩色影像 DPI (10級)', 'gray_dpi_label': '灰階影像 DPI', 'mono_dpi_label': '黑白影像 DPI', 'preserve_vector': '保留文字/向量(僅處理影像)',
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
                return

            # mark reordering to suppress view side-effects
            self._reordering_in_progress = True
            # store selection offsets for precise multi-select preservation
            try:
                self._last_moved_offsets = [i - source_rows[0] for i in source_rows]
            except Exception:
                self._last_moved_offsets = list(range(len(moved_items)))
            self._perform_reordering_and_update_ui(new_order, true_dest_row, len(moved_items))

        except Exception as e:
            print(f"Reordering failed: {e}")
            traceback.print_exc()

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

        if sys.platform.startswith('win'):
            candidates.extend([
                (os.path.join(base_dir, 'main_codex1.exe'), False),
                (os.path.join(source_dir, 'main_codex1.exe'), False),
                (os.path.join(exec_dir, 'main_codex1.exe'), False),
            ])
        else:
            candidates.extend([
                (os.path.join(base_dir, 'main_codex1'), False),
                (os.path.join(source_dir, 'main_codex1'), False),
                (os.path.join(exec_dir, 'main_codex1'), False),
            ])

        candidates.append((os.path.join(base_dir, 'main_codex1.py'), True))
        if base_dir != source_dir:
            candidates.append((os.path.join(source_dir, 'main_codex1.py'), True))
        if exec_dir not in (base_dir, source_dir):
            candidates.append((os.path.join(exec_dir, 'main_codex1.py'), True))

        for path, is_script in candidates:
            if not os.path.isfile(path):
                continue
            if is_script:
                interpreter = sys.executable or sys.argv[0]
                if not interpreter:
                    continue
                return interpreter, [path, target_path]
            if sys.platform.startswith('win') or os.access(path, os.X_OK):
                return path, [target_path]
        return None

    def save_file(self):
        if self.pdf_document and self.current_file:
            try:
                self.pdf_document.save(self.current_file, incremental=True)
                self.has_unsaved_changes = False
                self.setWindowTitle(f"PDF Editor - {os.path.basename(self.current_file)}")
                try:
                    self.statusBar().showMessage(self.t('saved') if self.language!='en' else 'Saved', 3000)
                except Exception:
                    pass
            except Exception as e:
                # Fallback: save to temp and replace
                try:
                    base, ext = os.path.splitext(self.current_file)
                    tmp_path = base + ".tmp_save" + ext
                    self.pdf_document.save(tmp_path, garbage=4, deflate=True)
                    os.replace(tmp_path, self.current_file)
                    self.has_unsaved_changes = False
                    self.setWindowTitle(f"PDF Editor - {os.path.basename(self.current_file)}")
                    try:
                        self.statusBar().showMessage(self.t('saved') if self.language!='en' else 'Saved', 3000)
                    except Exception:
                        pass
                except Exception as e2:
                    print(f"Error saving file: {e2}")

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
        last_dir = str(self.settings.value('last_dir', os.path.dirname(self.current_file) if self.current_file else os.getcwd())) if hasattr(self, 'settings') else ''
        default_name = self.current_file or os.path.join(last_dir, "Untitled.pdf")
        file_path, _ = QFileDialog.getSaveFileName(self, self.t('save_as'), default_name, "PDF 파일 (*.pdf)")
        if file_path:
            try:
                self.pdf_document.save(file_path, garbage=4, deflate=True)
                self.current_file = file_path
                self.has_unsaved_changes = False
                self.setWindowTitle(f"PDF Editor - {os.path.basename(self.current_file)}")
                try:
                    self.statusBar().showMessage(self.t('saved_as') if self.language!='en' else 'Saved As', 3000)
                except Exception:
                    pass
                if hasattr(self, 'settings'):
                    self.settings.setValue('last_dir', os.path.dirname(file_path))
            except Exception as e:
                print(f"Error saving as file: {e}")

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
            self.document_layout.addWidget(page_label)
            self.page_labels.append(page_label)
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

    def goto_page(self):
        try:
            page_num = int(self.page_input.text()) - 1
            if 0 <= page_num < self.pdf_document.page_count:
                self.scroll_to_page(page_num)
        except (ValueError, AttributeError):
            self.update_page_info()

    def zoom_in(self):
        if self.pdf_document:
            self.zoom_level = min(5.0, self.zoom_level * 1.25)
            self._page_cache.clear()
            self.load_document_view()
            QTimer.singleShot(0, lambda: self.scroll_to_page(self.current_page))

    def zoom_out(self):
        if self.pdf_document:
            self.zoom_level = max(0.25, self.zoom_level / 1.25)
            self._page_cache.clear()
            self.load_document_view()
            QTimer.singleShot(0, lambda: self.scroll_to_page(self.current_page))

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
            QMessageBox.information(self, "알림", "편집할 PDF 파일이 열려있지 않습니다.")
            return
        if self._external_editor_process and self._external_editor_process.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, "알림", "외부 편집기가 이미 실행 중입니다.")
            return

        if self.has_unsaved_changes:
            choice = self._prompt_save_changes()
            if choice == 'yes':
                self.save_file()
            elif choice == 'saveas':
                self.save_as_file()
            elif choice == 'cancel':
                return
            # 'no' continues without saving; document will reopen from last saved version
            if choice in ('yes', 'saveas') and self.has_unsaved_changes:
                QMessageBox.critical(self, "오류", "변경사항을 저장하지 못해 외부 편집을 취소합니다.")
                return

        target_path = self.current_file
        try:
            resolved = self._resolve_external_editor_command(target_path)
            if not resolved:
                QMessageBox.critical(self, "오류", "main_codex1 실행 파일을 찾을 수 없습니다. 패키지와 함께 배포되었는지 확인하세요.")
                return
            program, arguments = resolved

            self._pending_reopen_path = target_path
            self._external_previous_title = self.windowTitle()
            self._disable_external_watch()
            self._unload_document(preserve_current_file=True)
            self.setWindowTitle(f"PDF Editor - {os.path.basename(target_path)} (외부 편집 중)")
            self.statusBar().showMessage("외부 편집기를 실행하는 중입니다...", 4000)

            process = QProcess(self)
            process.setProgram(program)
            process.setArguments(arguments)
            process.finished.connect(self._on_external_editor_finished)
            process.errorOccurred.connect(self._on_external_editor_error)
            process.started.connect(lambda: self.statusBar().showMessage("외부 편집기를 열었습니다.", 5000))
            self._external_editor_process = process
            process.start()
        except Exception as e:
            self._external_editor_process = None
            QMessageBox.critical(self, "오류", f"외부 편집기 실행 실패: {e}")
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
            self.statusBar().showMessage("외부 편집 저장을 감지하여 문서를 새로고침했습니다.", 6000)
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
        self._external_editor_process = None
        success = (exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0)
        self._reopen_after_external(success)

    def _on_external_editor_error(self, error: QProcess.ProcessError):
        self._external_editor_process = None
        error_messages = {
            QProcess.ProcessError.FailedToStart: "외부 편집기를 시작하지 못했습니다. Python 실행 경로를 확인하세요.",
            QProcess.ProcessError.Crashed: "외부 편집기가 예기치 않게 종료되었습니다.",
            QProcess.ProcessError.Timedout: "외부 편집기 실행이 시간 초과되었습니다.",
            QProcess.ProcessError.WriteError: "외부 편집기와 통신 중 오류가 발생했습니다.",
            QProcess.ProcessError.ReadError: "외부 편집기 출력 읽기 중 오류가 발생했습니다.",
        }
        message = error_messages.get(error, "외부 편집기 실행 중 알 수 없는 문제가 발생했습니다.")
        self.statusBar().showMessage(message, 6000)
        QMessageBox.critical(self, "오류", message)
        self._reopen_after_external(success=False)

    def _reopen_after_external(self, success: bool):
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
                self.advanced_compress_pdf(
                    self.current_file, output_pdf,
                    dpi_color=settings['dpi_color'],
                    dpi_gray=settings['dpi_gray'],
                    dpi_mono=settings['dpi_mono'],
                    preserve_vector=settings.get('preserve_vector', True)
                )

    def show_about_dialog(self):
        QMessageBox.information(self, self.app_name, self.t('about_text'))

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
        progress = QProgressDialog("PDF 압축 중...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()
        
        try:
            doc = fitz.open(input_path)
            doc.save(output_path, garbage=garbage, deflate=deflate, clean=clean)
            doc.close()
            self.statusBar().showMessage("PDF 압축 완료", 5000)
        except Exception as e:
            self.statusBar().showMessage("PDF 압축 중 오류 발생", 5000)
        finally:
            progress.close()

    def advanced_compress_pdf(self, input_path: str, output_path: str, dpi_color: int = 72, dpi_gray: int = 72, dpi_mono: int = 72, preserve_vector: bool = True):
        progress = QProgressDialog("고급 PDF 압축 중...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()

        try:
            gs_path = "gs"
            cmd = [
                gs_path, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
                "-dPDFSETTINGS=/screen", "-dNOPAUSE", "-dQUIET", "-dBATCH",
                # Color images
                "-dDownsampleColorImages=true", "-dColorImageDownsampleType=/Bicubic",
                f"-dColorImageResolution={dpi_color}",
                # Grayscale images
                "-dDownsampleGrayImages=true", "-dGrayImageDownsampleType=/Bicubic",
                f"-dGrayImageResolution={dpi_gray}",
                # Monochrome images
                "-dDownsampleMonoImages=true", "-dMonoImageDownsampleType=/Bicubic",
                f"-dMonoImageResolution={dpi_mono}",
                f"-sOutputFile={output_path}", input_path
            ]
            subprocess.call(cmd)
            self.statusBar().showMessage("고급 PDF 압축 완료", 5000)
        except FileNotFoundError:
            QMessageBox.critical(self, "오류", "Ghostscript 실행 파일을 찾을 수 없습니다.\n시스템에 Ghostscript를 설치하고 PATH에 추가해주세요.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"고급 PDF 압축 중 오류가 발생했습니다: {e}")
        finally:
            progress.close()

    def update_current_page_on_scroll(self, value):
        if self._suppress_scroll_sync or not self.page_labels:
            return
        viewport_height = self.scroll_area.viewport().height()
        scroll_center = value + viewport_height / 2
        
        closest_page = min(range(len(self.page_labels)), key=lambda i: abs(self.page_labels[i].y() + self.page_labels[i].height() / 2 - scroll_center))
        
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
    editor = PDFEditor()
    editor.show()
    sys.exit(app.exec())
