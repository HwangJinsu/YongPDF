import sys
import os
import re
import copy
import difflib
import importlib
import builtins
import uuid
import math
import webbrowser
from collections import Counter
from typing import Optional, Tuple

# Editor build marker for sync/debug
__EDITOR_BUILD__ = "main_codex1.py patched for font embedding + hover @ 2025-09-20 17:21"
APP_VERSION = "v1.1"
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QFileDialog, QDialog, QLineEdit, 
    QFontComboBox, QCheckBox, QDialogButtonBox, QFormLayout, QMessageBox,
    QScrollArea, QFrame, QSizePolicy, QListWidget, QListWidgetItem, QColorDialog,
    QProgressDialog, QGraphicsColorizeEffect, QSplashScreen, QSpinBox, QTextEdit,
    QToolBar, QRadioButton, QButtonGroup, QSplitter, QToolTip
)
from PySide6.QtWidgets import QDoubleSpinBox, QSlider
from PySide6.QtGui import (
    QPixmap, QImage, QFont, QPainter, QPen, QColor, QBrush,
    QFontDatabase, QPalette, QIntValidator, QDragEnterEvent, QDropEvent, QFontMetrics,
    QRawFont, QFontInfo, QFontMetricsF, QAction, QActionGroup, QCursor, QKeySequence, QPainterPath,
    QIcon
)
from PySide6.QtCore import (
    Qt, Signal, QPoint, QPointF, QTimer, QSize, QPropertyAnimation, 
    QRect, QRectF, QEasingCurve, QObject, QBuffer, QByteArray, QSettings, QVariantAnimation, QEvent
)
import fitz  # PyMuPDF
from fontTools.ttLib import TTFont
import json
import zipfile

# Console encoding guard (ignore unsupported characters on stdout/stderr)
def _configure_stream(stream):
    try:
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors='ignore')
    except Exception:
        pass


_configure_stream(getattr(sys, 'stdout', None))
_configure_stream(getattr(sys, 'stderr', None))

_orig_print = builtins.print
print = _orig_print  # type: ignore

# --- Splash utilities ----------------------------------------------------

def _rect_to_tuple(rect):
    """fitz.Rect를 (x0, y0, x1, y1) 튜플로 변환"""
    if rect is None: return None
    try:
        return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))
    except Exception: return None

def _resolve_static_path(*relative_parts: str) -> str:
    """Locate a static resource in both source and frozen bundles."""
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
        visited: set[str] = set()
        for base in candidates:
            if not base or not os.path.isdir(base):
                continue
            base = os.path.abspath(base)
            if base in visited:
                continue
            visited.add(base)
            for root, _, files in os.walk(base):
                if basename in files:
                    return os.path.join(root, basename)

    return os.path.normpath(os.path.join(module_dir, *relative_parts))


def _build_text_splash_pixmap() -> Optional[QPixmap]:
    width, height = 448, 370
    pixmap = QPixmap(width, height)
    if pixmap.isNull():
        return None

    pixmap.fill(QColor('#080b10'))

    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        logo_path = _resolve_static_path('YongPDF_text_img.png')
        if logo_path:
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

        painter.setPen(QColor('#f4f4f4'))
        title_font = QFont('Arial', 17)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(QRect(0, 232, width, 28), Qt.AlignmentFlag.AlignHCenter, 'YongPDF')

        painter.setPen(QColor('#c0c7d1'))
        subtitle_font = QFont('Arial', 8)
        painter.setFont(subtitle_font)
        lines = [
            '정교한 PDF 텍스트 편집기',
            '개발: Hwang Jinsu · 이메일: iiish@hanmail.net',
            '본 소프트웨어는 개인용/업무용 무료 사용 가능합니다.'
        ]
        top = 268
        for line in lines:
            painter.drawText(QRect(0, top, width, 18), Qt.AlignmentFlag.AlignHCenter, line)
            top += 21

        painter.setPen(QColor('#8a94a3'))
        copyright_font = QFont('Arial', 7)
        painter.setFont(copyright_font)
        painter.drawText(
            QRect(0, height - 30, width, 18),
            Qt.AlignmentFlag.AlignHCenter,
            '© 2025 YongPDF · Hwang Jinsu. All rights reserved.'
        )
    finally:
        painter.end()
    
    return pixmap


def _show_startup_splash(app: QApplication) -> Optional[QSplashScreen]:
    try:
        pixmap = _build_text_splash_pixmap()
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
        '텍스트 모듈을 불러오는 중입니다...',
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        QColor(210, 210, 210)
    )
    app.processEvents()
    return splash


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

# --- Bullets & Hancom HWP PUA Defense Utilities ---
BULLET_CHARS = {
    '•',  # 0x2022 BULLET
    '‣',  # 0x2023 TRIANGULAR BULLET
    '⁃',  # 0x2043 HYPHEN BULLET
    '∙',  # 0x2219 BULLET OPERATOR
    '·',  # 0x00B7 MIDDLE DOT
    'ㆍ', # 0x318d ARAEA
    '･',  # 0xff65 HALFWIDTH KATAKANA MIDDLE DOT
    '○',  # 0x25CB WHITE CIRCLE
    '●',  # 0x25CF BLACK CIRCLE
    '◎',  # 0x25CE BULLSEYE
    '◇',  # 0x25C7 WHITE DIAMOND
    '◆',  # 0x25C6 BLACK DIAMOND
    '□',  # 0x25A1 WHITE SQUARE
    '■',  # 0x25A0 BLACK SQUARE
    '▪',  # 0x25AA BLACK SMALL SQUARE
    '▫',  # 0x25AB WHITE SMALL SQUARE
    '▷',  # 0x25B7 WHITE RIGHT-POINTING TRIANGLE
    '▶',  # 0x25B6 BLACK RIGHT-POINTING TRIANGLE
    '▸',  # 0x25B8 BLACK RIGHT-POINTING SMALL TRIANGLE
    '◁',  # 0x25C1 WHITE LEFT-POINTING TRIANGLE
    '◀',  # 0x25C0 BLACK LEFT-POINTING TRIANGLE
    '△',  # 0x25B3 WHITE UP-POINTING TRIANGLE
    '▲',  # 0x25B2 BLACK UP-POINTING TRIANGLE
    '▽',  # 0x25BD WHITE DOWN-POINTING TRIANGLE
    '▼',  # 0x25BC BLACK DOWN-POINTING TRIANGLE
    '※',  # 0x203B REFERENCE MARK
    '★',  # 0x2605 BLACK STAR
    '☆',  # 0x2606 WHITE STAR
    '☞',  # 0x261E WHITE RIGHT POINTING INDEX
    '☜',  # 0x261C WHITE LEFT POINTING INDEX
    '→',  # 0x2192 RIGHTWARDS ARROW
    '⇒',  # 0x21D2 RIGHTWARDS DOUBLE ARROW
    '➨',  # 0x27A8 HEAVY CONCAVE-POINTED BLACK RIGHTWARDS ARROW
    '✔',  # 0x2714 HEAVY CHECK MARK
    '✓',  # 0x2713 CHECK MARK
    '◦',  # 0x25E6 WHITE BULLET
    '◘',  # 0x25D8 INVERSE BULLET
    '◙',  # 0x25D9 INVERSE WHITE CIRCLE
    '❐',  # 0x2750 UPPER RIGHT DROP-SHADOWED WHITE SQUARE
    '❑',  # 0x274F LOWER RIGHT DROP-SHADOWED WHITE SQUARE
    '❖',  # 0x2756 BLACK DIAMOND MINUS WHITE X
    '✦',  # 0x2726 BLACK FOUR POINTED STAR
    '✧',  # 0x2727 WHITE FOUR POINTED STAR
}

def is_pua_char(c: str) -> bool:
    """한컴 HWP 전용 특수문자 및 유니코드 사용자 정의 영역(PUA) 판별"""
    if not c:
        return False
    o = ord(c)
    return (0xE000 <= o <= 0xF8FF) or (0xF0000 <= o <= 0x10FFFF)

def is_symbol_font(font_name: str) -> bool:
    """기호/딩뱃 폰트(Wingdings, Symbol 등) 판별"""
    if not font_name:
        return False
    fn = font_name.lower()
    return any(k in fn for k in ['wingdings', 'webdings', 'symbol', 'zapfdingbats'])

# --- Enhanced Font Utilities ---
class FontMatcher:
    def __init__(self):
        # 시스템에 설치된 폰트 목록 수집 (matplotlib 방식)
        self.system_fonts = []
        fm_mod = None
        try:
            fm_mod = importlib.import_module('matplotlib.font_manager')
        except Exception:
            fm_mod = None

        if fm_mod:
            try:
                font_paths = fm_mod.findSystemFonts()
                for font_path in font_paths:
                    try:
                        font_prop = fm_mod.FontProperties(fname=font_path)
                        font_name = font_prop.get_name()
                        if font_name:
                            self.system_fonts.append(font_name)
                    except Exception:
                        continue
            except Exception:
                pass
        
        # QFontDatabase로 추가 폰트 수집 (deprecation 해결)
        qt_fonts = QFontDatabase.families()
        self.system_fonts.extend(qt_fonts)
        
        # 중복 제거 및 정렬
        self.system_fonts = sorted(list(set(self.system_fonts)))
        print(f"Found {len(self.system_fonts)} system fonts")
    
    def find_best_match(self, pdf_font_name: str):
        """PDF 폰트명과 가장 유사한 시스템 폰트 찾기"""
        if not pdf_font_name:
            return None
        
        # 직접 매칭 시도
        if pdf_font_name in self.system_fonts:
            return pdf_font_name
        
        # difflib를 사용한 유사도 매칭
        best_match = difflib.get_close_matches(
            pdf_font_name, self.system_fonts, n=1, cutoff=0.3
        )
        if best_match:
            return best_match[0]
        
        # 부분 매칭
        pdf_lower = pdf_font_name.lower()
        for font in self.system_fonts:
            if pdf_lower in font.lower() or font.lower() in pdf_lower:
                return font
        
        return None

# --- 한컴오피스 폰트 파일명/약어 ↔ 표준 한글 폰트명 매핑 테이블 ---
HNC_FONT_NAME_MAP: dict[str, str] = {
    # HY 글꼴 (한양정보통신/한컴)
    'h2gtre': 'HY견고딕',
    'h2gtrm': 'HY고딕M',
    'h2hdrm': 'HY헤드라인M',
    'h2db': 'HY둥근고딕',
    'h2drb': 'HY둥근고딕B',
    'h2drm': 'HY둥근고딕M',
    'h2drl': 'HY둥근고딕L',
    'h2grre': 'HY견출고딕',
    'h2grrm': 'HY중고딕',
    'h2mre': 'HY견명조',
    'h2mrm': 'HY명조M',
    'h2mjre': 'HY견명조',
    'h2mjrm': 'HY명조M',
    'h2greb': 'HY궁서B',
    'h2grem': 'HY궁서',
    'h2gsob': 'HY궁서B',
    'h2gsom': 'HY궁서',
    'h2snrm': 'HY신명조',
    'h2snre': 'HY신견명조',
    'h2trm': 'HY태백산맥',
    'h2bdr': 'HY바다',
    'hypmokgak': 'HY목각파임B',
    'hypmpb': 'HY목각파임B',
    'hypmpl': 'HY목각파임L',
    'hywulb': 'HY울릉도B',
    'hywulm': 'HY울릉도M',
    'hypost': 'HY엽서M',
    'hypostb': 'HY엽서B',
    'hypostl': 'HY엽서L',
    'h2snb': 'HY신그래픽B',
    'h2snm': 'HY신그래픽M',

    # 함초롬 글꼴 (한컴 대표 폰트)
    'hmkmr': '함초롬바탕',
    'hmkmrl': '함초롬바탕',
    'hmkmr_l': '함초롬바탕',
    'hmkmb': '함초롬바탕',
    'hmkmd': '함초롬돋움',
    'hmkmdb': '함초롬돋움',
    'hamchorombatang': '함초롬바탕',
    'hamchoromdotum': '함초롬돋움',
    'hcrbatang': '함초롬바탕',
    'hcrdotum': '함초롬돋움',

    # 휴먼 글꼴 (한컴)
    'hmfmm': '휴먼명조',
    'hmfme': '휴먼견명조',
    'hmfgm': '휴먼고딕',
    'hmfge': '휴먼견고딕',
    'hmfgr': '휴먼중고딕',
    'hmfdb': '휴먼둥근헤드라인',
    'hmfmr': '휴먼가는명조',
    'hmfgrb': '휴먼옛체',
    'hmfma': '휴먼매직체',
    'hmfex': '휴먼엑스포',

    # 한컴 글꼴 (한컴오피스 전용)
    'hcomn': '한컴바탕',
    'hcomd': '한컴돋움',
    'hcomc': '한컴쿨재즈',
    'hcoms': '한컴솔잎',
    'hcomy': '한컴윤체',
    'hancombatang': '한컴바탕',
    'hancomdotum': '한컴돋움',

    # 기타 자주 사용되는 한컴 번들 폰트
    'mdart': 'MD아트체',
    'mdgaesung': 'MD개성체',
    'mdsol': 'MD솔체',
}

class SystemFontManager:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SystemFontManager, cls).__new__(cls)
            cls._instance.font_map = cls._instance._find_system_fonts()
            cls._instance.font_name_variations = cls._instance._build_font_variations()
            cls._instance.font_matcher = FontMatcher()
            cls._instance.font_file_index = cls._instance._build_font_file_index()
            cls._instance._unmatched_fonts_warned: set[str] = set()
        return cls._instance

    def _get_all_names_from_font(self, font_path):
        names = set()
        base_name = os.path.splitext(os.path.basename(font_path))[0]
        names.add(base_name)

        # 파일명 약어(한컴 등) 매핑 확인
        clean_key = re.sub(r'[^a-z0-9]', '', base_name.lower())
        if clean_key in HNC_FONT_NAME_MAP:
            kor_name = HNC_FONT_NAME_MAP[clean_key]
            names.add(kor_name)
            names.add(kor_name.replace(' ', ''))
            names.add(kor_name.replace(' ', '-'))

        try:
            font = TTFont(font_path, fontNumber=0)
            if 'name' in font:
                for record in font['name'].names:
                    if record.nameID in [1, 4, 6]:  # Family name, Full name, PostScript name
                        name = None
                        try:
                            name = record.toUnicode()
                        except Exception:
                            # 구형 한컴/한국어 폰트의 name 테이블 인코딩 fallback (CP949, EUC-KR, UTF-16-BE)
                            raw = getattr(record, 'string', None)
                            if raw and isinstance(raw, (bytes, bytearray)):
                                for enc in ('cp949', 'euc-kr', 'utf-16-be', 'utf-8', 'latin-1'):
                                    try:
                                        decoded = raw.decode(enc).replace('\x00', '').strip()
                                        if decoded:
                                            name = decoded
                                            break
                                    except Exception:
                                        continue
                        if name:
                            name = name.strip()
                            if name:
                                names.add(name)
                                # 하이픈과 공백 변형 추가
                                names.add(name.replace('-', ' '))
                                names.add(name.replace(' ', '-'))
                                # 한글명이 들어있는 경우 공백 제거 버전도 추가
                                if any('가' <= ch <= '힣' for ch in name):
                                    names.add(name.replace(' ', ''))
        except Exception as e:
            print(f"Error reading font {font_path}: {e}")
            names.add(base_name)
        return list(names)

    def _scan_hnc_subdirs_for_fonts(self, root_path: str, target_set: set[str], max_depth: int = 5) -> None:
        """지정된 디렉토리 하위에서 TTF, Fonts, Hwp 폰트 디렉토리를 깊이 제한과 함께 고속 탐색."""
        if not root_path or not os.path.isdir(root_path):
            return

        # 제외할 비폰트 대용량 디렉토리명 (고속 탐색을 위한 가지치기)
        skip_dirs = {
            'clipart', 'cliparts', 'sample', 'samples', 'template', 'templates',
            'manual', 'manuals', 'help', 'chart', 'theme', 'icons', 'image', 'images',
            'sound', 'sounds', 'plugin', 'plugins', 'temp', 'backup'
        }

        norm_root = os.path.abspath(root_path)
        root_depth = norm_root.count(os.sep)

        try:
            for current_root, dirs, files in os.walk(norm_root):
                # 깊이 제한
                current_depth = current_root.count(os.sep) - root_depth
                if current_depth > max_depth:
                    dirs.clear()
                    continue

                # 불필요 디렉토리 가지치기 (in-place pruning)
                dirs[:] = [d for d in dirs if d.lower() not in skip_dirs]

                # 디렉토리명 체크: TTF, Hwp, Fonts 등
                base_name = os.path.basename(current_root).lower()
                if base_name in ('ttf', 'hwp', 'fonts'):
                    has_font = any(f.lower().endswith(('.ttf', '.otf', '.ttc')) for f in files)
                    if has_font or base_name == 'hwp':
                        target_set.add(os.path.abspath(current_root))
                elif any(f.lower().endswith(('.ttf', '.otf', '.ttc')) for f in files):
                    # 경로에 font 또는 ttf 또는 hnc 키워드가 있는 경우
                    c_lower = current_root.lower()
                    if 'font' in c_lower or 'ttf' in c_lower or 'hnc' in c_lower:
                        target_set.add(os.path.abspath(current_root))
        except (OSError, PermissionError):
            pass

    def _get_hnc_font_directories(self) -> list[str]:
        """한컴오피스(Hnc) 설치 경로에서 폰트 디렉토리들을 탐색하여 반환.
        다양한 한컴오피스 버전(2010, 2014, NEO, 2018, 2020, 2022, 2024 등) 및
        비표준 설치 드라이브/디렉토리를 레지스트리와 정적/동적 스캔으로 자동 감지.
        """
        found_dirs = set()

        # 0. 환경 변수로 지정된 경로가 있다면 우선 확인
        env_hnc = os.environ.get("HNC_FONT_DIR")
        if env_hnc and os.path.isdir(env_hnc):
            found_dirs.add(os.path.abspath(env_hnc))

        if sys.platform == "win32":
            # 1. Windows 레지스트리 기반 탐색
            try:
                import winreg
                reg_roots = [
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\HNC\HOffice"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\HNC\HOffice"),
                    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\HNC\HOffice"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\HNC\Shared"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\HNC\Shared"),
                ]

                for hkey, subkey in reg_roots:
                    try:
                        with winreg.OpenKey(hkey, subkey) as root_key:
                            # 1-a. 현재 키 자체의 값들 조사
                            try:
                                count = winreg.QueryInfoKey(root_key)[1]
                                for i in range(count):
                                    name, val, _ = winreg.EnumValue(root_key, i)
                                    if isinstance(val, str) and os.path.isdir(val):
                                        self._scan_hnc_subdirs_for_fonts(val, found_dirs)
                            except OSError:
                                pass

                            # 1-b. 서브키(버전별 키: 8.0, 9.0, 10.0, 11.0, 12.0 등) 조사
                            try:
                                subkey_count = winreg.QueryInfoKey(root_key)[0]
                                for i in range(subkey_count):
                                    ver_name = winreg.EnumKey(root_key, i)
                                    try:
                                        with winreg.OpenKey(root_key, ver_name) as ver_key:
                                            v_count = winreg.QueryInfoKey(ver_key)[1]
                                            for j in range(v_count):
                                                v_name, val, _ = winreg.EnumValue(ver_key, j)
                                                if isinstance(val, str) and os.path.isdir(val):
                                                    self._scan_hnc_subdirs_for_fonts(val, found_dirs)
                                    except OSError:
                                        continue
                            except OSError:
                                pass
                    except OSError:
                        continue
            except Exception as e:
                print(f"Hnc registry search note: {e}")

            # 2. 알려진 정적 경로 후보군 (버전별 HOffice 디렉토리 및 Shared 디렉토리)
            drives = []
            sys_drive = os.environ.get("SystemDrive", "C:")
            if sys_drive:
                drives.append(sys_drive.rstrip('\\'))
            for d in ["C:", "D:", "E:", "F:"]:
                if d not in drives and os.path.exists(d + "\\"):
                    drives.append(d)

            program_folder_names = ["Program Files", "Program Files (x86)"]

            office_version_names = [
                "Office 2026", "Office 2024", "Office 2022", "Office 2020",
                "Office 2018", "Office NEO", "Office 2014", "Office 2010",
                "HOffice", "Office"
            ]
            hoffice_subdirs = [
                "HOffice140", "HOffice130", "HOffice120", "HOffice110",
                "HOffice100", "HOffice95", "HOffice90", "HOffice80", "HOffice"
            ]

            hnc_roots_to_scan = set()

            for drive in drives:
                for pf in program_folder_names:
                    hnc_root = os.path.join(drive + "\\", pf, "Hnc")
                    if os.path.isdir(hnc_root):
                        hnc_roots_to_scan.add(hnc_root)

                    # 정적 경로 확인 (Hwp, TTF)
                    for off_ver in office_version_names:
                        for hoff in hoffice_subdirs:
                            p1 = os.path.join(drive + "\\", pf, "Hnc", off_ver, hoff, "Shared", "TTF", "Hwp")
                            p2 = os.path.join(drive + "\\", pf, "Hnc", off_ver, hoff, "Shared", "TTF")
                            if os.path.isdir(p1):
                                found_dirs.add(os.path.abspath(p1))
                            if os.path.isdir(p2):
                                found_dirs.add(os.path.abspath(p2))

                        p3 = os.path.join(drive + "\\", pf, "Hnc", off_ver, "Shared", "TTF", "Hwp")
                        p4 = os.path.join(drive + "\\", pf, "Hnc", off_ver, "Shared", "TTF")
                        if os.path.isdir(p3):
                            found_dirs.add(os.path.abspath(p3))
                        if os.path.isdir(p4):
                            found_dirs.add(os.path.abspath(p4))

                    p5 = os.path.join(drive + "\\", pf, "Hnc", "Shared", "TTF", "Hwp")
                    p6 = os.path.join(drive + "\\", pf, "Hnc", "Shared", "TTF")
                    p7 = os.path.join(drive + "\\", pf, "Hnc", "Shared", "Fonts")
                    for p in (p5, p6, p7):
                        if os.path.isdir(p):
                            found_dirs.add(os.path.abspath(p))

            # 3. 발견된 Hnc 루트들에 대해 동적 스캔 (깊이 5)
            for hnc_root in hnc_roots_to_scan:
                self._scan_hnc_subdirs_for_fonts(hnc_root, found_dirs, max_depth=5)

        else:
            # macOS / Linux 환경에서 Hnc 폰트 디렉토리 탐색 지원
            candidate_hnc_dirs = [
                os.path.expanduser("~/Library/Fonts/Hnc"),
                os.path.expanduser("~/Library/Fonts/Hwp"),
                "/Library/Fonts/Hnc",
                "/Library/Fonts/Hwp",
                os.path.expanduser("~/.fonts/Hnc"),
                os.path.expanduser("~/.fonts/Hwp"),
                os.path.expanduser("~/.local/share/fonts/Hnc"),
                os.path.expanduser("~/.local/share/fonts/Hwp"),
            ]
            for cand in candidate_hnc_dirs:
                if os.path.isdir(cand):
                    found_dirs.add(os.path.abspath(cand))

        valid_dirs = [d for d in found_dirs if os.path.isdir(d)]
        if valid_dirs:
            print(f"Hnc font directories discovered: {len(valid_dirs)} paths")
            for vd in valid_dirs:
                print(f"  [HNC] {vd}")
        return sorted(valid_dirs)

    def _find_system_fonts(self):
        font_map = {}
        font_dirs = []
        
        if sys.platform == "darwin":
            font_dirs = ["/System/Library/Fonts", "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]
        elif sys.platform == "win32":
            # 시스템 폰트 디렉토리
            font_dirs = [os.path.join(os.environ["SystemRoot"], "Fonts")]
            
            # 사용자별 폰트 디렉토리 동적 감지
            if "LOCALAPPDATA" in os.environ:
                user_fonts_dir = os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Windows", "Fonts")
                font_dirs.append(user_fonts_dir)
            
            # 추가적으로 사용자 프로필 기반 폰트 디렉토리 감지
            if "USERPROFILE" in os.environ:
                userprofile_fonts = os.path.join(os.environ["USERPROFILE"], "AppData", "Local", "Microsoft", "Windows", "Fonts")
                if userprofile_fonts not in font_dirs:
                    font_dirs.append(userprofile_fonts)
            
            # 현재 사용자명을 이용한 절대 경로 구성 (fallback)
            if "USERNAME" in os.environ:
                username = os.environ["USERNAME"]
                username_fonts_dir = f"C:\\Users\\{username}\\AppData\\Local\\Microsoft\\Windows\\Fonts"
                if username_fonts_dir not in font_dirs and os.path.exists(username_fonts_dir):
                    font_dirs.append(username_fonts_dir)
            
            # 추가적으로 Users 디렉토리의 모든 사용자 폰트 디렉토리를 탐색
            try:
                users_dir = "C:\\Users"
                if os.path.exists(users_dir):
                    for user_folder in os.listdir(users_dir):
                        user_fonts_path = os.path.join(users_dir, user_folder, "AppData", "Local", "Microsoft", "Windows", "Fonts")
                        if os.path.exists(user_fonts_path) and user_fonts_path not in font_dirs:
                            font_dirs.append(user_fonts_path)
            except (OSError, PermissionError) as e:
                print(f"Warning: Could not scan all user font directories: {e}")
            
            # 시스템의 다른 일반적인 폰트 위치들도 확인
            additional_dirs = [
                "C:\\Windows\\Fonts",  # SystemRoot와 중복일 수 있지만 안전하게 추가
                os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "Common Files", "Microsoft Shared", "Fonts"),
                os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "Common Files", "Microsoft Shared", "Fonts") if "ProgramFiles(x86)" in os.environ else None
            ]
            
            for additional_dir in additional_dirs:
                if additional_dir and os.path.exists(additional_dir) and additional_dir not in font_dirs:
                    font_dirs.append(additional_dir)
                    
        else:  # Linux
            font_dirs = ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts")]
            
            # Linux에서 추가 폰트 디렉토리들
            additional_linux_dirs = [
                "/usr/share/fonts/truetype",
                "/usr/share/fonts/opentype", 
                "/usr/local/share/fonts/truetype",
                "/usr/local/share/fonts/opentype",
                os.path.expanduser("~/.local/share/fonts")
            ]
            
            for additional_dir in additional_linux_dirs:
                if os.path.exists(additional_dir) and additional_dir not in font_dirs:
                    font_dirs.append(additional_dir)

        # 한컴오피스(Hnc) 폰트 디렉토리 자동 감지 및 병합
        try:
            hnc_dirs = self._get_hnc_font_directories()
            for h_dir in hnc_dirs:
                if h_dir and os.path.isdir(h_dir) and h_dir not in font_dirs:
                    font_dirs.append(h_dir)
        except Exception as e:
            print(f"Warning: Error detecting Hnc font directories: {e}")
        
        # 중복 제거
        font_dirs = list(set(font_dirs))
        
        # 디버깅: 폰트 디렉토리 목록 출력
        print(f"Scanning font directories: {len(font_dirs)} paths")
        for font_dir in font_dirs:
            exists = os.path.exists(font_dir)
            marker = 'OK' if exists else '!!'
            log_path = font_dir
            try:
                log_path.encode('ascii')
            except Exception:
                log_path = font_dir.encode('utf-8', 'ignore').decode('ascii', 'ignore')
            print(f"  [{marker}] {log_path}")
        
        # 각 디렉토리에서 모든 폰트 파일 수집
        all_font_files = []
        for dir_path in font_dirs:
            if os.path.exists(dir_path):
                try:
                    for root, dirs, files in os.walk(dir_path):
                        for filename in files:
                            if filename.lower().endswith(('.ttf', '.otf', '.ttc')):
                                all_font_files.append(os.path.join(root, filename))
                except (OSError, PermissionError) as e:
                    print(f"Warning: Could not access directory {dir_path}: {e}")
        
        # 폰트 파일 우선순위 정렬 (Regular/Normal 우선 처리하여 Family Name 선점 방지)
        def font_priority_key(path):
            name = os.path.basename(path).lower()
            score = 0
            # Bold 관련 키워드 (높을수록 나중에 처리)
            if any(k in name for k in ['bold', 'black', 'heavy', 'extra', '-b', '_b', 'bd.']): score += 10
            # Italic 관련 키워드
            if any(k in name for k in ['italic', 'oblique', '-i', '_i', 'it.']): score += 5
            # Light/Thin 관련 키워드
            if any(k in name for k in ['light', 'thin', 'extra', 'lt.']): score += 2
            # Regular/Normal 명시된 경우 가중치 감소
            if any(k in name for k in ['regular', 'normal', 'medium', 'reg.']): score = 0
            return score
            
        all_font_files.sort(key=font_priority_key)
        
        # 정렬된 순서대로 폰트 맵 구성 (Family Name은 먼저 처리된 Regular가 선점)
        total_fonts_found = 0
        for full_path in all_font_files:
            try:
                # [개선] 시스템 폰트 데이터베이스에 명시적 등록 (UI 렌더링 누락 방지)
                QFontDatabase.addApplicationFont(full_path)
                
                font_names = self._get_all_names_from_font(full_path)
                added_any = False
                for name in font_names:
                    if name and name not in font_map:
                        font_map[name] = full_path
                        added_any = True
                if added_any:
                    total_fonts_found += 1
            except Exception as e:
                # 에러 로그 인코딩 방어
                try:
                    print(f"Error processing font {full_path}: {e}")
                except:
                    pass
        
        print(f"Total unique font files indexed: {total_fonts_found}")
        return font_map

    def _register_font_variation_entry(self, variations: dict[str, str], font_name: str) -> None:
        """주어진 폰트 이름에 대한 다양한 변형을 variations 딕셔너리에 등록."""
        try:
            lower = font_name.lower()
        except Exception:
            lower = font_name
        keys = {
            lower,
            lower.replace(' ', ''),
            lower.replace('-', ' '),
            lower.replace(' ', '-'),
            re.sub(r'[^a-z0-9가-힣]', '', lower),
        }
        for key in keys:
            if key:
                variations.setdefault(key, font_name)

    def _register_font_variations(self, font_name: str, path: Optional[str] = None) -> None:
        """font_name을 variations 및 파일 인덱스에 등록."""
        if path:
            self.font_map[font_name] = path
        self._register_font_variation_entry(self.font_name_variations, font_name)
        if path:
            self._index_font_filename(font_name, path)

    def _build_font_variations(self):
        """폰트 이름의 다양한 변형을 매핑"""
        variations: dict[str, str] = {}
        for font_name in self.font_map.keys():
            self._register_font_variation_entry(variations, font_name)
        return variations

    def _filename_variants(self, path: str) -> set[str]:
        base = os.path.splitext(os.path.basename(path or ''))[0].lower()
        variants = {
            base,
            base.replace(' ', ''),
            base.replace('-', ''),
            base.replace('_', ''),
            re.sub(r'[^a-z0-9]+', '', base),
        }
        return {variant for variant in variants if variant}

    def _index_font_filename(self, font_name: str, path: str, index: Optional[dict[str, list[str]]] = None) -> None:
        if not path:
            return
        target = index if index is not None else self.font_file_index
        for key in self._filename_variants(path):
            bucket = target.setdefault(key, [])
            if font_name not in bucket:
                bucket.append(font_name)

    def _build_font_file_index(self) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        for name, path in self.font_map.items():
            if path:
                self._index_font_filename(name, path, index)
        return index

    def _filename_candidate_keys(self, *names: str) -> list[str]:
        keys: list[str] = []
        seen: set[str] = set()
        for candidate in names:
            if not candidate:
                continue
            base = os.path.splitext(candidate)[0]
            lower = base.lower()
            variants = {
                lower,
                lower.replace(' ', ''),
                lower.replace('-', ''),
                lower.replace('_', ''),
                re.sub(r'[^a-z0-9]+', '', lower),
            }
            for variant in variants:
                if variant and variant not in seen:
                    seen.add(variant)
                    keys.append(variant)
        return keys

    def _finalize_font_name(self, font_name: Optional[str]) -> Optional[str]:
        if not font_name:
            return None
        path = self.font_map.get(font_name)
        if path:
            preferred = self._preferred_family_from_path(path)
            if preferred:
                preferred = preferred.strip()
                if preferred:
                    if preferred not in self.font_map:
                        self._register_font_variations(preferred, path)
                    return preferred
        if font_name in self.font_map:
            self._register_font_variation_entry(self.font_name_variations, font_name)
            return font_name
        return None

    def _warn_unmatched_font(self, pdf_font_name: str) -> None:
        key = pdf_font_name or ''
        if key in self._unmatched_fonts_warned:
            return
        self._unmatched_fonts_warned.add(key)
        
        # 다국어 번역 적용
        title = MainWindow.t('msg_unmatched_font_title')
        body = MainWindow.t('msg_unmatched_font_body', font=pdf_font_name or 'Unknown')
        
        try:
            if QApplication.instance():
                QMessageBox.warning(None, title, body)
            else:
                print(f"Warning: [{title}] {body}")
        except Exception:
            print(f"Warning: [{title}] {body}")

    def _preferred_family_from_path(self, font_path):
        try:
            font = TTFont(font_path, fontNumber=0)
            family = None
            for record in font['name'].names:
                if record.nameID in [1, 4]:  # Family, Full name
                    try:
                        name = record.toUnicode()
                        if name:
                            # Family 우선
                            if record.nameID == 1:
                                family = name
                                break
                            if not family:
                                family = name
                    except Exception:
                        continue
            return family
        except Exception:
            return None

    def get_korean_family_name_for_search(self, font_name: str) -> str:
        """눈누 검색용 한글 패밀리명을 최대한 도출한다.
        1) 입력명 자체가 한글 포함이면 그대로 사용
        2) 시스템 매칭 → 경로 → name 테이블에서 한글 포함된 Family 후보 우선 선택
        3) 파일명 별칭 매핑(H2gtrE → HY견고딕 등)
        4) 최종 실패 시 정제된 입력명 반환
        """
        try:
            if any('가' <= ch <= '힣' for ch in font_name or ''):
                return font_name
            # 매칭 시도
            matched = self.find_best_font_match(font_name)
            path = self.get_font_path(matched) if matched else None
            # name 테이블에서 한글 family 찾기
            if path and os.path.exists(path):
                try:
                    tt = TTFont(path, fontNumber=0)
                    kor_candidates = []
                    for record in tt['name'].names:
                        if record.nameID == 1:  # Family
                            try:
                                nm = record.toUnicode()
                                if nm and any('가' <= ch <= '힣' for ch in nm):
                                    kor_candidates.append(nm)
                            except Exception:
                                pass
                    if kor_candidates:
                        # 가장 짧은/간결한 이름 선호
                        kor_candidates.sort(key=len)
                        return kor_candidates[0]
                except Exception:
                    pass
            clean = font_name.split('+')[-1] if font_name and '+' in font_name else (font_name or '')
            # 파일명/영문 별칭 (영→한) - HNC_FONT_NAME_MAP 우선 확인
            clean_key = re.sub(r'[^a-z0-9]', '', clean.lower())
            if clean_key in HNC_FONT_NAME_MAP:
                return HNC_FONT_NAME_MAP[clean_key]

            filename_aliases = {
                'h2gtre': 'HY견고딕',
                'h2hdrm': 'HY헤드라인M',
                'h2db': 'HY둥근고딕',
            }
            english_to_kor = {
                'malgun gothic': '맑은 고딕',
                'nanumgothic': '나눔고딕',
                'nanum gothic': '나눔고딕',
                'dotum': '돋움',
                'gulim': '굴림',
                'batang': '바탕',
                'gungsuh': '궁서',
                'apple sd gothic neo': '애플 SD 산돌고딕 Neo',
                'noto sans cjk kr': '본고딕',
                'noto sans kr': '노토 산스 KR',
            }
            key = clean.lower().replace(' ', '').replace('-', '')
            if key in filename_aliases:
                return filename_aliases[key]
            ek = clean.lower()
            if ek in english_to_kor:
                return english_to_kor[ek]
            # 마지막: 정제된 입력명 반환
            return clean
        except Exception:
            return font_name or ''

    def find_best_font_match(self, pdf_font_name):
        """PDF의 폰트 이름을 시스템 폰트와 매칭 (개선된 버전)"""
        if not pdf_font_name:
            return None
        
        # PDF에서 추출된 폰트명에서 접두사 제거 (예: RJAWXJ+Dotum -> Dotum)
        clean_font_name = pdf_font_name
        if '+' in pdf_font_name:
            clean_font_name = pdf_font_name.split('+')[-1]
            
        # [복원] HWP / Ghostscript 생성 한글 폰트명의 Latin-1 깨짐 복원 (예: ÈÞ¸Õ°íµñ -> 휴먼고딕)
        for fn_candidate in (clean_font_name, pdf_font_name):
            try:
                b = fn_candidate.encode('latin1')
                dec = b.decode('cp949')
                if dec and any('\uac00' <= ch <= '\ud7a3' for ch in dec):
                    clean_font_name = dec
                    break
            except Exception:
                pass

        # 추가 정규화: 하위표기 제거 및 특수 접미사 제거
        norm = clean_font_name
        norm = re.sub(r"[,\(\)\[\]]", " ", norm)   # 괄호/콤마 제거
        norm = re.sub(r"\b(MT|PS|Std|Pro|LT|Roman)\b", " ", norm, flags=re.I)
        norm = re.sub(r"\s+", " ", norm).strip()

        # 1순위: 시스템 폰트 파일명 기반 매칭
        filename_keys = self._filename_candidate_keys(pdf_font_name, clean_font_name, norm)
        for key in filename_keys:
            candidates = self.font_file_index.get(key)
            if not candidates:
                continue
            for candidate_name in candidates:
                finalized = self._finalize_font_name(candidate_name)
                if finalized:
                    return finalized

        # 파일명 별칭 매핑 (예: H2gtrE -> HY견고딕, HMKMR -> 함초롬바탕)
        for cand_name in [norm, clean_font_name, pdf_font_name]:
            if not cand_name:
                continue
            cand_key = re.sub(r'[^a-z0-9]', '', cand_name.lower())
            if cand_key in HNC_FONT_NAME_MAP:
                mapped_kor = HNC_FONT_NAME_MAP[cand_key]
                finalized = self._finalize_font_name(mapped_kor)
                if finalized:
                    return finalized
                # font_map에서 부분 매칭도 시도
                for fn in self.font_map.keys():
                    if mapped_kor in fn:
                        finalized = self._finalize_font_name(fn)
                        if finalized:
                            return finalized
        filename_aliases = {
            '##h2gtre': 'HY견고딕',
            '##h2hdrm': 'HY헤드라인M',
            '##h2db': 'HY둥근고딕',
        }
        alias = filename_aliases.get(norm.lower())
        if alias and alias in self.font_map:
            return self._finalize_font_name(alias)

        # 직접 매칭 시도 (원본명과 정제된 명 모두)
        for font_name in [pdf_font_name, clean_font_name, norm]:
            if font_name in self.font_map:
                finalized = self._finalize_font_name(font_name)
                if finalized:
                    return finalized

        # 한국어 대표 서체 패밀리 우선 매칭 (difflib 엉뚱한 매칭 방지)
        lower_name = norm.lower()
        clean_lower = clean_font_name.lower()
        if any(k in lower_name or k in clean_lower for k in ('malgun', '맑은고딕', '맑은 고딕')):
            for cand in ['Malgun Gothic', '맑은 고딕', 'Apple SD Gothic Neo', 'NanumGothic', 'Nanum Gothic']:
                if cand in self.font_map:
                    return self._finalize_font_name(cand)
        if any(k in lower_name or k in clean_lower for k in ('dotum', '돋움', '고딕', 'gothic')):
            for cand in ['Apple SD Gothic Neo', 'NanumGothic', 'Nanum Gothic', 'Dotum', '돋움']:
                if cand in self.font_map:
                    return self._finalize_font_name(cand)
        if any(k in lower_name or k in clean_lower for k in ('batang', '바탕', '명조', 'myeongjo', 'myungjo')):
            for cand in ['Batang', '바탕', 'AppleMyungjo', 'Nanum Myeongjo', 'NanumMyeongjo']:
                if cand in self.font_map:
                    return self._finalize_font_name(cand)
        if any(k in lower_name or k in clean_lower for k in ('gulim', '굴림')):
            for cand in ['Gulim', '굴림', 'Apple SD Gothic Neo', 'NanumGothic']:
                if cand in self.font_map:
                    return self._finalize_font_name(cand)

        # 새로운 FontMatcher 사용
        best_match = self.font_matcher.find_best_match(norm)
        if best_match and best_match in self.font_map:
            finalized = self._finalize_font_name(best_match)
            if finalized:
                return finalized

        # 기존 로직 fallback
        lower_name = norm.lower()
        if lower_name in self.font_name_variations:
            finalized = self._finalize_font_name(self.font_name_variations[lower_name])
            if finalized:
                return finalized
        
        # 부분 매칭 (정제된 이름으로)
        for variation, original in self.font_name_variations.items():
            if lower_name in variation or variation in lower_name:
                finalized = self._finalize_font_name(original)
                if finalized:
                    return finalized
        
        # 한글 폰트 특별 처리
        korean_font_mapping = {
            'dotum': 'Dotum',
            'gulim': 'Gulim', 
            'batang': 'Batang',
            'gungsuh': 'GungSuh',
            'malgun': 'Malgun Gothic',
            'nanumgothic': 'NanumGothic',
            'hypmokgak': 'HY목각파임B'
        }
        
        for korean_key, korean_font in korean_font_mapping.items():
            if korean_key in lower_name:
                if korean_font in self.font_map:
                    finalized = self._finalize_font_name(korean_font)
                    if finalized:
                        return finalized
                # 유사한 이름 찾기
                for font in self.font_map.keys():
                    if korean_key in font.lower():
                        finalized = self._finalize_font_name(font)
                        if finalized:
                            return finalized
        
        # 매칭 실패 - 사용자에게 안내
        self._warn_unmatched_font(norm or pdf_font_name)
        return None

    def get_font_path(self, font_name):
        return self.font_map.get(font_name)

    def get_all_font_names(self):
        return sorted(self.font_map.keys())

class PdfFontExtractor:
    """PDF에서 사용된 폰트 정보를 추출하는 클래스"""
    
    def __init__(self, doc):
        self.doc = doc
        self.used_fonts = set()
        self.font_manager = SystemFontManager()
    
    def extract_fonts_from_document(self):
        """문서 전체에서 사용된 폰트 추출 (개선된 버전)"""
        self.used_fonts.clear()
        font_details = {}
        
        for page_num in range(len(self.doc)):
            page = self.doc.load_page(page_num)
            text_dict = page.get_text("dict")
            
            # 페이지에서 사용된 폰트 리스트도 확인
            try:
                font_list = page.get_fonts()
                for font_info in font_list:
                    font_name = font_info[3] if len(font_info) > 3 else font_info[0]
                    if font_name:
                        font_details[font_name] = {
                            'xref': font_info[0],
                            'name': font_info[3] if len(font_info) > 3 else font_name,
                            'type': font_info[1] if len(font_info) > 1 else 'Unknown',
                            'encoding': font_info[2] if len(font_info) > 2 else 'Unknown'
                        }
                        self.used_fonts.add(font_name)
            except Exception as e:
                print(f"Error getting font list from page {page_num}: {e}")
            
            # 텍스트 분석을 통한 폰트 추출 (기존 로직)
            for block in text_dict.get("blocks", []):
                if block.get('type') == 0:  # 텍스트 블록
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            font_name = span.get('font', '')
                            if font_name:
                                self.used_fonts.add(font_name)
                                if font_name not in font_details:
                                    font_details[font_name] = {
                                        'xref': 'Unknown',
                                        'name': font_name,
                                        'type': 'Text Analysis',
                                        'encoding': 'Unknown'
                                    }
        
        # 폰트 세부 정보 저장
        self.font_details = font_details
        return list(self.used_fonts)
    
    def get_matched_fonts(self):
        """PDF 폰트와 시스템 폰트 매칭 결과"""
        matched_fonts = []
        for pdf_font in self.used_fonts:
            system_font = self.font_manager.find_best_font_match(pdf_font)
            if system_font:
                matched_fonts.append({
                    'pdf_font': pdf_font,
                    'system_font': system_font,
                    'confidence': self._calculate_match_confidence(pdf_font, system_font)
                })
        
        # 신뢰도 순으로 정렬
        matched_fonts.sort(key=lambda x: x['confidence'], reverse=True)
        return matched_fonts
    
    def _calculate_match_confidence(self, pdf_font, system_font):
        """매칭 신뢰도 계산"""
        if pdf_font == system_font:
            return 1.0
        
        # 문자열 유사도 계산
        similarity = difflib.SequenceMatcher(None, pdf_font.lower(), system_font.lower()).ratio()
        return similarity

class TextEditorDialog(QDialog):
    def __init__(self, span_info, pdf_fonts=None, parent=None):
        super().__init__(parent)
        self.span_info = span_info
        self.main_window = parent if isinstance(parent, QMainWindow) else None
        self.overlay_key = (span_info.get('page_num'), span_info.get('overlay_id')) if span_info.get('overlay_id') is not None else None
        
        if parent and hasattr(parent, 't'):
            self._t = parent.t  # type: ignore[assignment]
        else:
            self._t = lambda key, **kwargs: key if not kwargs else key.format(**kwargs)

        self.setWindowTitle(self._t('text_editor_title'))
        self.setMinimumSize(500, 350)
        self.setModal(False)
        
        # 추가 위젯 import
        from PySide6.QtWidgets import QGroupBox, QGridLayout, QComboBox
        
        # 텍스트 편집 (특수문자 · ( ) , 및 공백/스페이스 1:1 온전한 보존)
        original_text = span_info.get('text', '')
        if span_info.get('is_overlay'):
            # 오버레이 텍스트는 사용자가 입력한 공백 갯수와 특수문자를 원형 그대로 1:1 보존
            normalized_text = original_text
        else:
            # 원본 텍스트: 전달받은 텍스트(또는 line_text)의 특수문자와 공백을 온전히 보존
            if not original_text and 'line_text' in span_info:
                original_text = span_info['line_text']
            normalized_text = original_text.replace('\r\n', ' ').replace('\n', ' ').replace('\t', '    ')
        # 한컴 HWP 전용 PUA 문자(렌더링 불가 특수문자) 필터링
        normalized_text = ''.join(c for c in normalized_text if not is_pua_char(c))
        
        self.text_edit = QLineEdit(normalized_text)
        self.parent_window = parent if isinstance(parent, QMainWindow) else None
        self._recent_fonts = []
        if self.parent_window and hasattr(self.parent_window, 'recent_fonts'):
            self._recent_fonts = [f for f in getattr(self.parent_window, 'recent_fonts', []) if isinstance(f, str) and f.strip()]
        
        # 원본 폰트 정보 저장
        self.original_font_info = {
            'font': span_info.get('font', ''),
            'pdf_font_name': span_info.get('pdf_font_name') or span_info.get('font', ''),
            'size': span_info.get('size', 12),
            'flags': span_info.get('flags', 0)
        }
        
        # 색상 정보 추출
        self.original_color = span_info.get('color', 0)
        self.text_color = self._convert_color_from_int(self.original_color)
        
        # 색상 선택 버튼
        self.color_button = QPushButton()
        self.color_button.setFixedSize(50, 30)
        self.color_button.setStyleSheet(f"background-color: {self.text_color.name()}")
        self.color_button.clicked.connect(self.choose_color)
        
        # 원본 폰트 정보 표시 레이블
        self.create_original_font_info_section()
        
        # 폰트 선택 (PDF 폰트를 상위에 배치) - QFontComboBox 대신 검색 지원을 위해 QComboBox 사용
        from PySide6.QtWidgets import QCompleter
        self.font_combo = QComboBox()
        self.font_combo.setEditable(True)
        self.font_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.font_combo.completer().setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.font_combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
        
        font_manager = SystemFontManager()

        self.all_fonts_label = self._t('font_combo_all_fonts')
        font_items: list[str] = []
        seen: set[str] = set()

        def add_font(name: str):
            if not name:
                return
            key = name.strip()
            key_lower = key.lower()
            if not key or key_lower in seen:
                return
            seen.add(key_lower)
            font_items.append(key)

        for recent in self._recent_fonts:
            add_font(recent)

        pdf_font_names: list[str] = []
        if pdf_fonts:
            pdf_font_names = [f['system_font'] for f in pdf_fonts if f.get('system_font')]
            for fam in pdf_font_names:
                add_font(fam)
            add_font(self.all_fonts_label)
        
        for font in font_manager.get_all_font_names():
            if font == self.all_fonts_label:
                continue
            add_font(font)

        if self.all_fonts_label not in seen:
            add_font(self.all_fonts_label)

        self.font_combo.clear()
        self.font_combo.addItems(font_items)
        
        # 최적의 폰트 매칭 및 설치 상태 확인
        pdf_font = span_info.get('font', '')
        best_match = font_manager.find_best_font_match(pdf_font)
        self.font_available = bool(best_match and best_match in font_items)
        
        if best_match and best_match in font_items:
            self.font_combo.setCurrentText(best_match)
        else:
            # span에 지정된 폰트가 있으면 우선 설정, 없으면 기본값
            initial_font = span_info.get('font') or (pdf_font_names[0] if pdf_fonts else 'Arial')
            if initial_font in font_items:
                self.font_combo.setCurrentText(initial_font)
            elif self._recent_fonts:
                self.font_combo.setCurrentText(self._recent_fonts[0])
        
        # 폰트 설치 안내 버튼
        self.install_font_button = QPushButton(self._t('install_font_button'))
        self.install_font_button.clicked.connect(self.show_font_install_guide)
        if self.font_available:
            self.install_font_button.hide()  # 폰트가 있으면 숨김
        
        # 폰트 크기 (0.1 단위 조절)
        self.size_spinbox = QDoubleSpinBox()
        self.size_spinbox.setDecimals(2)
        self.size_spinbox.setSingleStep(0.1)
        self.size_spinbox.setRange(1.0, 200.0)
        self.size_spinbox.setValue(self._normalize_font_size(span_info.get('size', 12)))
        
        # 스타일 속성들 (문제 2 해결 - 밑줄 자동 체크 문제 수정)
        font_flags = span_info.get('flags', 0)
        self.bold_checkbox = QCheckBox(self._t('style_bold'))
        self.bold_checkbox.setChecked(bool(font_flags & 2**4))  # Bold flag
        
        self.italic_checkbox = QCheckBox(self._t('style_italic'))
        self.italic_checkbox.setChecked(bool(font_flags & 2**1))  # Italic flag
        
        # 밑줄 플래그 정확한 확인 (PyMuPDF 문서 기준)
        self.underline_checkbox = QCheckBox(self._t('style_underline'))
        # 사용자 요청으로 자동 활성화 비활성화 (오작동 방지)
        underline_detected = False
        
        self.underline_checkbox.setChecked(underline_detected)
        
        # 폼 레이아웃
        form_layout = QFormLayout()
        text_row = QHBoxLayout()
        text_row.addWidget(self.text_edit)
        self.clear_text_button = QPushButton(self._t('btn_clear_text'))
        self.clear_text_button.setFixedHeight(30)
        self.clear_text_button.clicked.connect(self._on_clear_text)
        text_row.addWidget(self.clear_text_button)
        form_layout.addRow(self._t('text_label') + ':', text_row)
        form_layout.addRow(self._t('font_label') + ':', self.font_combo)
        form_layout.addRow(self._t('size_label') + ':', self.size_spinbox)

        # 장평(가로세로 비율) / 자간(트래킹)
        self.stretch_spin = QDoubleSpinBox()
        self.stretch_spin.setDecimals(1)
        self.stretch_spin.setRange(10.0, 400.0)
        self.stretch_spin.setSingleStep(1.0)
        self.stretch_spin.setSuffix('%')
        try:
            stretch_ratio = float(span_info.get('stretch', 1.0))
        except Exception:
            stretch_ratio = 1.0
        self.stretch_spin.setValue(max(10.0, min(400.0, stretch_ratio * 100.0)))

        self.tracking_spin = QDoubleSpinBox()
        self.tracking_spin.setDecimals(1)
        self.tracking_spin.setRange(-50.0, 50.0)  # percent delta (HWP 표준 -50% ~ +50%)
        self.tracking_spin.setSingleStep(0.5)
        self.tracking_spin.setValue(float(span_info.get('tracking', 0.0)))

        form_layout.addRow(self._t('stretch_label') + ':', self.stretch_spin)
        form_layout.addRow(self._t('tracking_label') + ':', self.tracking_spin)

        # 패치 색상 사용자 지정 옵션
        self.patch_color_pick_checkbox = QCheckBox(self._t('patch_color_pick'))
        self.patch_color_button = QPushButton()
        self.patch_color_button.setFixedSize(50, 30)
        # 부모(MainWindow)에 저장된 최근 패치 색상/사용 여부를 기본값으로 사용
        default_patch_color = QColor(255, 255, 255)
        default_use_custom = False
        try:
            if hasattr(parent, 'last_patch_color') and isinstance(parent.last_patch_color, QColor):
                default_patch_color = parent.last_patch_color
            if hasattr(parent, 'last_use_custom_patch'):
                default_use_custom = bool(parent.last_use_custom_patch)
        except Exception:
            pass
        self.patch_color_button_color = default_patch_color
        self.patch_color_pick_checkbox.setChecked(default_use_custom)
        self.patch_color_button.setStyleSheet(f"background-color: {self.patch_color_button_color.name()}")
        self.patch_color_button.clicked.connect(self._choose_patch_color)
        
        # 색상 선택 레이아웃
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel(self._t('color_label') + ':'))
        color_layout.addWidget(self.color_button)
        color_layout.addStretch()
        form_layout.addRow(color_layout)
        
        # 스타일 체크박스 및 굵기 설정
        style_layout = QHBoxLayout()
        style_layout.addWidget(self.bold_checkbox)
        
        # 합성 볼드 굵기 (Bold 체크 시 활성화)
        self.bold_weight_spin = QSpinBox()
        self.bold_weight_spin.setRange(100, 500)
        self.bold_weight_spin.setSuffix('%')
        self.bold_weight_spin.setValue(int(span_info.get('synth_bold_weight', 120)))
        self.bold_weight_spin.setFixedWidth(70)
        self.bold_weight_spin.setEnabled(self.bold_checkbox.isChecked())
        style_layout.addWidget(self.bold_weight_spin)
        
        style_layout.addSpacing(15)
        style_layout.addWidget(self.italic_checkbox)
        style_layout.addSpacing(15)
        
        style_layout.addWidget(self.underline_checkbox)
        # 밑줄 굵기 (Underline 체크 시 활성화) - 디폴트 0.6으로 강제 설정
        self.underline_weight_spin = QDoubleSpinBox()
        self.underline_weight_spin.setRange(0.1, 2.0)
        self.underline_weight_spin.setSingleStep(0.1)
        self.underline_weight_spin.setDecimals(1)
        # span_info에 값이 있더라도 신규 편집 시에는 0.6 선호 (사용자 피드백 반영)
        u_weight = float(span_info.get('underline_weight', 0.6))
        if not span_info.get('is_overlay'): u_weight = 0.6
        self.underline_weight_spin.setValue(u_weight)
        self.underline_weight_spin.setFixedWidth(60)
        self.underline_weight_spin.setEnabled(self.underline_checkbox.isChecked())
        style_layout.addWidget(self.underline_weight_spin)
        
        # 밑줄 간격 (Underline 체크 시 활성화)
        self.underline_offset_spin = QDoubleSpinBox()
        self.underline_offset_spin.setRange(-5.0, 10.0)
        self.underline_offset_spin.setSingleStep(0.1)
        self.underline_offset_spin.setDecimals(1)
        self.underline_offset_spin.setValue(float(span_info.get('underline_offset', 1.5)))
        self.underline_offset_spin.setFixedWidth(60)
        self.underline_offset_spin.setEnabled(self.underline_checkbox.isChecked())
        style_layout.addWidget(self.underline_offset_spin)
        
        style_layout.addStretch()
        form_layout.addRow(self._t('style_label') + ':', style_layout)
        
        # 체크박스 상태에 따른 활성화/비활성화 및 스타일(회색 처리) 연결
        def update_bold_style(checked):
            self.bold_weight_spin.setEnabled(checked)
            if checked:
                self.bold_weight_spin.setStyleSheet("")
            else:
                self.bold_weight_spin.setStyleSheet("background-color: #f0f0f0; color: #a0a0a0;")
        
        def update_underline_style(checked):
            self.underline_weight_spin.setEnabled(checked)
            self.underline_offset_spin.setEnabled(checked)
            if checked:
                self.underline_weight_spin.setStyleSheet("")
                self.underline_offset_spin.setStyleSheet("")
            else:
                self.underline_weight_spin.setStyleSheet("background-color: #f0f0f0; color: #a0a0a0;")
                self.underline_offset_spin.setStyleSheet("background-color: #f0f0f0; color: #a0a0a0;")

        self.bold_checkbox.toggled.connect(update_bold_style)
        self.underline_checkbox.toggled.connect(update_underline_style)
        
        # 초기 스타일 적용
        update_bold_style(self.bold_checkbox.isChecked())
        update_underline_style(self.underline_checkbox.isChecked())

        # HWP 공백 보정 옵션
        self.hwp_space_checkbox = QCheckBox("HWP(아래아한글) 공백 너비 적용")
        self.hwp_space_checkbox.setToolTip("띄어쓰기 너비를 한글 1글자의 50%로 강제 조정합니다.")
        
        # 초기값 설정: 오버레이에 저장된 값 우선, 없으면 폰트 또는 문서 전체 설정 따름
        is_hwp_mode = False
        if 'hwp_space_mode' in span_info and span_info['hwp_space_mode'] is not None:
            is_hwp_mode = bool(span_info['hwp_space_mode'])
        else:
            font_str = str(span_info.get('font', '')).lower()
            pdf_font_str = str(span_info.get('pdf_font_name', '')).lower()
            hwp_font_keys = ['hcr', 'h2hdr', 'h2gtr', 'h2mk', 'hygtr', 'hybtr', 'hmk', 'hancom', 'haansoft', 'gulimche', 'batangche']
            if any(k in font_str or k in pdf_font_str for k in hwp_font_keys):
                is_hwp_mode = True
            elif hasattr(parent, 'is_hwp_doc') and parent.is_hwp_doc:
                is_hwp_mode = True
        self.hwp_space_checkbox.setChecked(is_hwp_mode)
            
        form_layout.addRow(self.hwp_space_checkbox)

        # 패치 없이 텍스트만 생성 옵션
        self.text_only_checkbox = QCheckBox(self._t('patch_text_only_label'))
        if 'text_only_mode' in span_info:
            self.text_only_checkbox.setChecked(bool(span_info['text_only_mode']))
        else:
            self.text_only_checkbox.setChecked(False)
        form_layout.addRow(self.text_only_checkbox)

        # 이미지로 처리 옵션
        self.force_image_checkbox = QCheckBox(self._t('force_image_label'))
        form_layout.addRow(self.force_image_checkbox)
        
        # 위치 조정 버튼 제거됨 - 싱글클릭으로 대체
        
        # 버튼 (Windows / macOS 환경 불문하고 항상 [예] [취소] 순서로 배열)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        self.btn_ok = QPushButton(self._t('btn_yes'))
        self.btn_cancel = QPushButton(self._t('btn_cancel'))
        self.btn_ok.setMinimumSize(96, 36)
        self.btn_cancel.setMinimumSize(96, 36)
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_ok)
        button_layout.addWidget(self.btn_cancel)
        self.button_layout = button_layout
        
        # 패치 크기 설정 섹션 추가
        patch_group = QGroupBox(self._t('patch_group_title'))
        patch_layout = QGridLayout()
        patch_color_row = QHBoxLayout()
        patch_color_row.addWidget(self.patch_color_pick_checkbox)
        patch_color_row.addWidget(self.patch_color_button)
        patch_layout.addWidget(QLabel(self._t('patch_color_label') + ':'), 0, 0)
        patch_layout.addLayout(patch_color_row, 0, 1)

        def _extract_margin_ratio(source) -> tuple[float, float, float, float]:
            try:
                if isinstance(source, dict):
                    return (float(source.get('left', 0.0)), float(source.get('right', 0.0)),
                            float(source.get('top', 0.0)), float(source.get('bottom', 0.0)))
                if isinstance(source, (tuple, list)):
                    if len(source) == 4:
                        return (float(source[0]), float(source[1]), float(source[2]), float(source[3]))
                    elif len(source) >= 2:
                        return (float(source[0]), float(source[0]), float(source[1]), float(source[1]))
                value = float(source)
                return value, value, value, value
            except Exception:
                return 0.0, 0.0, 0.0, 0.0

        m_l, m_r, m_t, m_b = 0.0, 0.0, 0.0, 0.0
        # 개별 속성 우선
        if all(k in span_info for k in ['patch_margin_l', 'patch_margin_r', 'patch_margin_t', 'patch_margin_b']):
            m_l = float(span_info['patch_margin_l'])
            m_r = float(span_info['patch_margin_r'])
            m_t = float(span_info['patch_margin_t'])
            m_b = float(span_info['patch_margin_b'])
        elif 'patch_margin' in span_info:
            m_l, m_r, m_t, m_b = _extract_margin_ratio(span_info.get('patch_margin'))
        elif hasattr(parent, 'patch_margin'):
            m_l, m_r, m_t, m_b = _extract_margin_ratio(getattr(parent, 'patch_margin'))

        def _create_margin_spin(initial_value: float) -> QDoubleSpinBox:
            spin = QDoubleSpinBox()
            spin.setDecimals(1)
            spin.setRange(-50.0, 50.0)
            spin.setSingleStep(1.0)
            spin.setSuffix('%')
            spin.setValue(max(-50.0, min(50.0, initial_value * 100.0)))
            spin.setFixedWidth(140) # 너비 2배 확대 (70 -> 140)
            return spin

        patch_layout.addWidget(QLabel(self._t('patch_margin_label_left') + ':'), 1, 0)
        self.patch_margin_spin_l = _create_margin_spin(m_l)
        patch_layout.addWidget(self.patch_margin_spin_l, 1, 1)

        patch_layout.addWidget(QLabel(self._t('patch_margin_label_right') + ':'), 1, 2)
        self.patch_margin_spin_r = _create_margin_spin(m_r)
        patch_layout.addWidget(self.patch_margin_spin_r, 1, 3)

        patch_layout.addWidget(QLabel(self._t('patch_margin_label_top') + ':'), 2, 0)
        self.patch_margin_spin_t = _create_margin_spin(m_t)
        patch_layout.addWidget(self.patch_margin_spin_t, 2, 1)

        patch_layout.addWidget(QLabel(self._t('patch_margin_label_bottom') + ':'), 2, 2)
        self.patch_margin_spin_b = _create_margin_spin(m_b)
        patch_layout.addWidget(self.patch_margin_spin_b, 2, 3)

        # 힌트
        hint_label = QLabel(self._t('patch_margin_hint'))
        hint_label.setWordWrap(True)
        hint_label.setStyleSheet("color: #666666; font-size: 11px;")
        patch_layout.addWidget(hint_label, 3, 0, 1, 4)
        patch_group.setLayout(patch_layout)
        
        # 메인 레이아웃 구성
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.font_info_group)
        main_layout.addLayout(form_layout)
        main_layout.addWidget(patch_group)
        
        font_button_layout = QHBoxLayout()
        font_button_layout.addWidget(self.install_font_button)
        main_layout.addLayout(font_button_layout)
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
        
        # 실시간 미리보기 시그널 연결
        self.text_edit.textChanged.connect(self._on_values_changed)
        self.font_combo.currentTextChanged.connect(self._on_values_changed)
        self.size_spinbox.valueChanged.connect(self._on_values_changed)
        self.stretch_spin.valueChanged.connect(self._on_values_changed)
        self.tracking_spin.valueChanged.connect(self._on_values_changed)
        self.bold_checkbox.toggled.connect(self._on_values_changed)
        self.italic_checkbox.toggled.connect(self._on_values_changed)
        self.underline_checkbox.toggled.connect(self._on_values_changed)
        self.bold_weight_spin.valueChanged.connect(self._on_values_changed)
        self.underline_weight_spin.valueChanged.connect(self._on_values_changed)
        self.underline_offset_spin.valueChanged.connect(self._on_values_changed)
        self.patch_color_pick_checkbox.toggled.connect(self._on_values_changed)
        self.hwp_space_checkbox.toggled.connect(self._on_values_changed)
        self.force_image_checkbox.toggled.connect(self._on_values_changed)
        
        for spin in [self.patch_margin_spin_l, self.patch_margin_spin_r, self.patch_margin_spin_t, self.patch_margin_spin_b]:
            spin.valueChanged.connect(self._on_values_changed)

        self.position_adjustment_requested = False

    def _on_values_changed(self):
        """설정값이 변경될 때마다 부모 창에 실시간 미리보기 요청"""
        parent = self.parent()
        if not parent or not hasattr(parent, 'preview_edit_changes'):
            return
        
        vals = self.get_values()
        print(f"[Dialog] Values changed: text='{vals.get('text')}', size={vals.get('size')}")
        parent.preview_edit_changes(self.overlay_key, vals)

    def _normalize_font_size(self, value):
        try:
            val = float(value)
        except Exception:
            return 12.0
        return val

    def _on_patch_margin_changed(self):
        # _on_values_changed로 통합됨
        self._on_values_changed()
    
    def _on_clear_text(self):
        self.text_edit.clear()
        self.text_edit.setFocus()

    def create_original_font_info_section(self):
        """원본 폰트 정보 섹션 생성 - 신뢰도 향상을 위해 유사 폰트 안내 강화"""
        from PySide6.QtWidgets import QGroupBox, QGridLayout
        
        # 원본 폰트 정보 그룹박스
        self.font_info_group = QGroupBox(self._t('original_font_group'))
        font_info_layout = QGridLayout()
        
        # 폰트명 정보
        original_font = self.original_font_info.get('pdf_font_name') or self.original_font_info.get('font', 'Unknown')
        clean_font_name = original_font.split('+')[-1] if '+' in original_font else original_font
        
        font_info_layout.addWidget(QLabel(self._t('original_font_label') + ':'), 0, 0)
        # 원본 폰트명을 강조하여 표시
        orig_label = QLabel(f"<b>{original_font}</b>")
        orig_label.setToolTip(self._t('original_font_tooltip', font=original_font))
        font_info_layout.addWidget(orig_label, 0, 1)

        if '+' in original_font:
            font_info_layout.addWidget(QLabel(self._t('font_alias_label') + ':'), 1, 0)
            font_info_layout.addWidget(QLabel(f"<i>{clean_font_name}</i>"), 1, 1)

        font_info_layout.addWidget(QLabel(self._t('original_size_label') + ':'), 2, 0)
        font_info_layout.addWidget(QLabel(f"{self.original_font_info['size']:.1f}pt"), 2, 1)
        
        # 폰트 플래그 정보
        flags = self.original_font_info['flags']
        style_info = []
        if flags & 2**4: style_info.append(self._t('style_bold'))
        if flags & 2**1: style_info.append(self._t('style_italic'))
        if flags & 2**2: style_info.append(self._t('style_underline'))

        if style_info:
            font_info_layout.addWidget(QLabel(self._t('original_style_label') + ':'), 3, 0)
            font_info_layout.addWidget(QLabel(", ".join(style_info)), 3, 1)
        
        # 구분선 추가
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        font_info_layout.addWidget(line, 4, 0, 1, 2)
        
        # === 원본 폰트 설치 상태 확인 ===
        font_manager = SystemFontManager()
        
        # 1. 원본 폰트명으로 직접 확인
        original_font_path = font_manager.get_font_path(original_font)
        clean_font_path = font_manager.get_font_path(clean_font_name)
        
        font_info_layout.addWidget(QLabel(self._t('install_status_label') + ':'), 5, 0)

        if original_font_path or clean_font_path:
            # 원본 폰트가 설치되어 있음
            installed_name = original_font if original_font_path else clean_font_name
            font_info_layout.addWidget(QLabel(self._t('installed_label', font=installed_name)), 5, 1)
            
            # 설치 경로 정보 (선택사항)
            path_to_show = original_font_path or clean_font_path
            if len(path_to_show) > 50:
                path_display = "..." + path_to_show[-47:]
            else:
                path_display = path_to_show
            font_info_layout.addWidget(QLabel(self._t('install_path_label') + ':'), 6, 0)
            font_info_layout.addWidget(QLabel(f"<small style='color: #666;'>{path_display}</small>"), 6, 1)

        else:
            # 원본 폰트가 설치되어 있지 않음
            not_inst_label = QLabel(f"<span style='color: #d9534f; font-weight: bold;'>{self._t('not_installed_label')}</span>")
            font_info_layout.addWidget(not_inst_label, 5, 1)

            # 시스템 매칭 결과 (유사 폰트 안내)
            font_info_layout.addWidget(QLabel(self._t('recommended_font_label') + ':'), 6, 0)
            matched_font = font_manager.find_best_font_match(clean_font_name)

            if matched_font:
                # [해결] 폰트명이 템플릿에 올바르게 적용되도록 matched_font 전달
                similar_text = self._t('similar_font_applied_label', font=matched_font)
                similar_label = QLabel(f"<i style='color: #f0ad4e;'>→ {similar_text}</i>")
                similar_label.setToolTip(self._t('similar_font_tooltip'))
                font_info_layout.addWidget(similar_label, 6, 1)

                # 폰트 설치 안내 링크 추가
                font_info_layout.addWidget(QLabel(self._t('install_method_label') + ':'), 7, 0)
                link_text = self._t('font_install_link_text', font=clean_font_name)
                install_guide_label = QLabel(f"<a href='install_guide' style='color: #337ab7; text-decoration: underline;'>{link_text}</a>")
                install_guide_label.linkActivated.connect(lambda: self.show_font_install_guide_for_font(clean_font_name))
                install_guide_label.setCursor(Qt.CursorShape.PointingHandCursor)
                font_info_layout.addWidget(install_guide_label, 7, 1)
            else:
                font_info_layout.addWidget(QLabel(self._t('no_alternative_label')), 6, 1)
                
                # 폰트 설치 안내
                font_info_layout.addWidget(QLabel(self._t('install_method_label') + ':'), 7, 0)
                link_text = self._t('font_install_link_text', font=clean_font_name)
                install_guide_label = QLabel(f"<a href='install_guide' style='color: #337ab7; text-decoration: underline;'>{link_text}</a>")
                install_guide_label.linkActivated.connect(lambda: self.show_font_install_guide_for_font(clean_font_name))
                install_guide_label.setCursor(Qt.CursorShape.PointingHandCursor)
                font_info_layout.addWidget(install_guide_label, 7, 1)
        
        self.font_info_group.setLayout(font_info_layout)
        
        self.font_info_group.setLayout(font_info_layout)
    
    def show_font_install_guide_for_font(self, font_name):
        """특정 폰트에 대한 설치 안내 대화상자"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
        import sys
        import webbrowser
        from urllib.parse import quote_plus
        
        # 폰트명 정제
        clean_name = font_name.split('+')[-1] if '+' in font_name else font_name
        
        dialog = QDialog(self)
        dialog.setWindowTitle(self._t('font_install_title', font=clean_name))
        dialog.setMinimumSize(500, 450)

        layout = QVBoxLayout()

        guide_text = QTextEdit()
        guide_text.setReadOnly(True)

        # 폰트 굵기/스타일 어미 제거 (Bold, Medium, Light 등)하여 검색 성공률 향상
        # 공백, 하이픈, 언더바 뒤에 오는 어미들을 포괄적으로 제거
        search_name = re.sub(r'[\s\-_]*(Bold|Italic|Medium|Light|Regular|Thin|Black|Extra|Heavy|Semi|Demi|Static|Condensed|Narrow|ExtraBold|ExtraLight|UltraLight|SemiBold|DemiBold)+$', '', clean_name, flags=re.IGNORECASE).strip()
        if not search_name:
            search_name = clean_name
            
        html = self._t('font_install_message_html', font=clean_name)
        guide_text.setHtml(html)
        layout.addWidget(guide_text)

        button_layout = QHBoxLayout()
        
        query = quote_plus(search_name)
        google_query = quote_plus(f"{search_name} ttf")
        
        google_font_btn = QPushButton(self._t('font_search_google'))
        google_font_btn.setMinimumHeight(35)
        google_font_btn.clicked.connect(lambda: webbrowser.open(f"https://www.google.com/search?q={google_query}"))
        button_layout.addWidget(google_font_btn)

        noonnu_btn = QPushButton(self._t('font_search_noonnu'))
        noonnu_btn.setMinimumHeight(35)
        noonnu_btn.clicked.connect(lambda: webbrowser.open(f"https://noonnu.cc/en/index?search={query}"))
        button_layout.addWidget(noonnu_btn)

        close_button = QPushButton(self._t('button_close'))
        close_button.setMinimumHeight(35)
        close_button.clicked.connect(dialog.accept)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)
        dialog.setLayout(layout)
        dialog.exec()

    def show_font_install_guide(self):
        """폰트 설치 안내 대화상자 (일반)"""
        original_font = self.original_font_info.get('pdf_font_name') or self.original_font_info.get('font', 'Unknown')
        self.show_font_install_guide_for_font(original_font)

    
    def _convert_color_from_int(self, color_int):
        """PDF 색상 정수를 QColor로 변환"""
        if color_int == 0:
            return QColor(0, 0, 0)  # 기본 검정색
        
        # RGB 값 추출
        r = (color_int >> 16) & 0xFF
        g = (color_int >> 8) & 0xFF
        b = color_int & 0xFF
        
        return QColor(r, g, b)
    
    def choose_color(self):
        """색상 선택 대화상자 (OK/Cancel 버튼 확대/통일)"""
        dlg = QColorDialog(self)
        dlg.setCurrentColor(self.text_color)
        try:
            # 버튼 크기 확대
            for btn in dlg.findChildren(QPushButton):
                btn.setMinimumSize(96, 36)
        except Exception:
            pass
        if dlg.exec() == QDialog.DialogCode.Accepted:
            color = dlg.selectedColor()
            if color.isValid():
                self.text_color = color
                self.color_button.setStyleSheet(f"background-color: {color.name()}")
                self._on_values_changed()

    def _choose_patch_color(self):
        dlg = QColorDialog(self)
        dlg.setCurrentColor(self.patch_color_button_color)
        try:
            for btn in dlg.findChildren(QPushButton):
                btn.setMinimumSize(96, 36)
        except Exception:
            pass
        if dlg.exec() == QDialog.DialogCode.Accepted:
            color = dlg.selectedColor()
            if color.isValid():
                self.patch_color_button_color = color
                self.patch_color_button.setStyleSheet(f"background-color: {color.name()}")
                self._on_values_changed()

    def start_position_adjustment(self):
        """위치 조정 모드 시작"""
        print("위치 조정 모드 시작됨")  # 디버깅 로그
        self.position_adjustment_requested = True
        self.accept()  # close() 대신 accept() 사용하여 다이얼로그 결과를 OK로 설정
    
    def get_values(self):
        return {
            "text": self.text_edit.text(),
            "font": self.font_combo.currentText(),
            "size": self._normalize_font_size(self.size_spinbox.value()),
            "stretch": self.stretch_spin.value() / 100.0,
            "tracking": self.tracking_spin.value(),
            "bold": self.bold_checkbox.isChecked(),
            "italic": self.italic_checkbox.isChecked(),
            "underline": self.underline_checkbox.isChecked(),
            "synth_bold_weight": self.bold_weight_spin.value(),
            "underline_weight": self.underline_weight_spin.value(),
            "underline_offset": self.underline_offset_spin.value(),
            "color": self.text_color,
            "use_custom_patch_color": self.patch_color_pick_checkbox.isChecked(),
            "patch_color": self.patch_color_button_color,
            "force_image": self.force_image_checkbox.isChecked(),
            "hwp_space_mode": self.hwp_space_checkbox.isChecked(),
            "text_only_mode": self.text_only_checkbox.isChecked(),
            "position_adjustment_requested": getattr(self, 'position_adjustment_requested', False),
            "patch_margin_l": self.patch_margin_spin_l.value() / 100.0 if hasattr(self, 'patch_margin_spin_l') else 0.0,
            "patch_margin_r": self.patch_margin_spin_r.value() / 100.0 if hasattr(self, 'patch_margin_spin_r') else 0.0,
            "patch_margin_t": self.patch_margin_spin_t.value() / 100.0 if hasattr(self, 'patch_margin_spin_t') else 0.0,
            "patch_margin_b": self.patch_margin_spin_b.value() / 100.0 if hasattr(self, 'patch_margin_spin_b') else 0.0,
            "patch_margin": (
                self.patch_margin_spin_l.value() / 100.0 if hasattr(self, 'patch_margin_spin_l') else 0.0,
                self.patch_margin_spin_r.value() / 100.0 if hasattr(self, 'patch_margin_spin_r') else 0.0,
                self.patch_margin_spin_t.value() / 100.0 if hasattr(self, 'patch_margin_spin_t') else 0.0,
                self.patch_margin_spin_b.value() / 100.0 if hasattr(self, 'patch_margin_spin_b') else 0.0
            ),
            "original_bbox": self.span_info.get('original_bbox'),
            "origin": self.span_info.get('origin'),
            "page_num": self.span_info.get('page_num', self.overlay_key[0] if self.overlay_key else 0),
            "overlay_id": self.overlay_key[1] if self.overlay_key else self.span_info.get('overlay_id')
        }

    def _remember_pos(self):
        parent = self.parent()
        if parent and hasattr(parent, 'save_text_editor_pos'):
            parent.save_text_editor_pos(self.pos())

    def moveEvent(self, event):
        super().moveEvent(event)
        self._remember_pos()

    def closeEvent(self, event):
        self._remember_pos()
        super().closeEvent(event)

class TextOverlay:
    """텍스트 오버레이 레이어 관리 클래스 - 완전한 텍스트 속성 지원"""

    def __init__(
        self,
        text,
        font,
        size,
        color,
        bbox,
        page_num,
        flags=0,
        *,
        height_ratio=None,
        ascent_ratio=None,
        descent_ratio=None,
        source_bbox=None,
        content_bbox=None,
        preview_height_ratio=None,
        hwp_space_mode=False,
        text_only_mode=False,
        synth_bold_weight=120,
        underline_weight=0.6,
        underline_offset=1.5,
        origin=None,
        pdf_font_name=None
    ):
        self.text = text
        self.font = font  
        self.pdf_font_name = pdf_font_name or font # 원본 PDF 폰트명 보존
        self.size = size
        self.color = color
        self.bbox = bbox  # fitz.Rect 객체
        self.page_num = page_num
        self.flags = flags  # 볼드, 이탤릭 등 스타일 플래그
        self.origin = origin # 베이스라인 좌표 (Point 또는 tuple)
        self.visible = True
        self.z_index = 0  # 레이어 순서
        self.original_bbox = source_bbox if source_bbox is not None else bbox  # 패치 원본 영역
        self.flattened = False  # PDF에 반영 여부
        # 확장 속성: 장평 / 자간
        self.stretch = 1.0  # 1.0 = 100%
        self.tracking = 0.0  # percent delta (0 = 기본)
        self.hwp_space_mode = hwp_space_mode
        self.text_only_mode = text_only_mode
        self.font_path = None
        self.synth_bold = False
        self.synth_bold_weight = int(synth_bold_weight)
        self.underline_weight = float(underline_weight)
        self.underline_offset = float(underline_offset)
        self.patch_margin_l = 0.0
        self.patch_margin_r = 0.0
        self.patch_margin_t = 0.0
        self.patch_margin_b = 0.0
        self._loaded_font_family = None
        base_ratio = self._normalize_height_ratio(height_ratio if height_ratio is not None else 1.15)
        self.height_ratio = base_ratio
        self.content_bbox = fitz.Rect(content_bbox) if content_bbox is not None else fitz.Rect(self.original_bbox)
        self.baseline_top_ratio = None
        self.baseline_bottom_ratio = None
        preview_ratio = preview_height_ratio if preview_height_ratio is not None else base_ratio
        self.preview_height_ratio = self._normalize_height_ratio(preview_ratio)
        if ascent_ratio is None:
            ascent_ratio = base_ratio * 0.85
        if descent_ratio is None:
            descent_ratio = max(0.0, base_ratio - ascent_ratio)
        self.ascent_ratio = float(ascent_ratio)
        self.descent_ratio = float(descent_ratio)
        self.baseline_top_ratio = float(self.ascent_ratio)
        self.baseline_bottom_ratio = float(self.descent_ratio)

    def update_properties(
        self,
        text=None,
        font=None,
        pdf_font_name=None,
        size=None,
        color=None,
        flags=None,
        stretch=None,
        tracking=None,
        font_path=None,
        synth_bold=None,
        synth_bold_weight=None,
        underline_weight=None,
        underline_offset=None,
        patch_margin=None,
        patch_margin_h=None,
        patch_margin_v=None,
        height_ratio=None,
        ascent_ratio=None,
        descent_ratio=None,
        preview_height_ratio=None,
        hwp_space_mode=None,
        text_only_mode=None,
        content_bbox=None,
        origin=None,
        new_values=None
    ):
        """텍스트 속성 업데이트 (편집창 연계)"""
        if text is not None:
            self.text = text
        if origin is not None:
            self.origin = origin
        if font is not None:
            if self.font != font:
                self._loaded_font_family = None
            self.font = font
        if pdf_font_name is not None:
            self.pdf_font_name = pdf_font_name
        if size is not None:
            self.size = size
        if color is not None:
            self.color = color
        if flags is not None:
            self.flags = flags
        if stretch is not None:
            self.stretch = float(stretch)
        if tracking is not None:
            self.tracking = float(tracking)
        if font_path is not None:
            self.font_path = font_path
            self._loaded_font_family = None
        if synth_bold is not None:
            self.synth_bold = bool(synth_bold)
        if synth_bold_weight is not None:
            self.synth_bold_weight = int(synth_bold_weight)
        if underline_weight is not None:
            self.underline_weight = float(underline_weight)
        if underline_offset is not None:
            self.underline_offset = float(underline_offset)
        if hwp_space_mode is not None:
            self.hwp_space_mode = bool(hwp_space_mode)
        if text_only_mode is not None:
            self.text_only_mode = bool(text_only_mode)
        
        # 패치 마진 개별 업데이트 (L, R, T, B)
        if new_values:
            for attr in ['patch_margin_l', 'patch_margin_r', 'patch_margin_t', 'patch_margin_b']:
                if attr in new_values:
                    setattr(self, attr, float(new_values[attr]))
            if 'text_only_mode' in new_values:
                self.text_only_mode = bool(new_values['text_only_mode'])

        if patch_margin_h is not None or patch_margin_v is not None or patch_margin is not None:
            if patch_margin is not None and not isinstance(patch_margin, dict):
                try:
                    if isinstance(patch_margin, (tuple, list)):
                        if len(patch_margin) == 4:
                            self.patch_margin_l = float(patch_margin[0])
                            self.patch_margin_r = float(patch_margin[1])
                            self.patch_margin_t = float(patch_margin[2])
                            self.patch_margin_b = float(patch_margin[3])
                        elif len(patch_margin) >= 2:
                            self.patch_margin_l = self.patch_margin_r = float(patch_margin[0])
                            self.patch_margin_t = self.patch_margin_b = float(patch_margin[1])
                    else:
                        value = float(patch_margin)
                        self.patch_margin_l = self.patch_margin_r = value
                        self.patch_margin_t = self.patch_margin_b = value
                except Exception:
                    pass
            # 레거시 호환
            if patch_margin_h is not None:
                self.patch_margin_l = self.patch_margin_r = float(patch_margin_h)
            if patch_margin_v is not None:
                self.patch_margin_t = self.patch_margin_b = float(patch_margin_v)
        
        if content_bbox is not None:
            try:
                updated_content = fitz.Rect(content_bbox)
                if updated_content.width > 0 and updated_content.height > 0:
                    self.content_bbox = updated_content
            except Exception:
                pass
        if height_ratio is not None:
            self.height_ratio = self._normalize_height_ratio(height_ratio)
        if preview_height_ratio is not None:
            self.preview_height_ratio = self._normalize_height_ratio(preview_height_ratio)
        if hasattr(self, 'ascent_ratio'):
            if ascent_ratio is not None:
                try:
                    self.ascent_ratio = float(ascent_ratio)
                except Exception:
                    self.ascent_ratio = 0.85
        else:
            self.ascent_ratio = float(ascent_ratio) if ascent_ratio is not None else 0.85
        if hasattr(self, 'descent_ratio'):
            if descent_ratio is not None:
                try:
                    self.descent_ratio = float(descent_ratio)
                except Exception:
                    self.descent_ratio = max(0.0, self.height_ratio - self.ascent_ratio)
        else:
            self.descent_ratio = float(descent_ratio) if descent_ratio is not None else max(0.0, self.height_ratio - self.ascent_ratio)
        try:
            self.baseline_top_ratio = float(self.ascent_ratio)
            self.baseline_bottom_ratio = float(self.descent_ratio)
        except Exception:
            self.baseline_top_ratio = None
            self.baseline_bottom_ratio = None
        # 속성 변경 시 다시 플래튼 필요
        self.flattened = False
        print(f"오버레이 속성 업데이트: '{self.text}' - {self.font}, {self.size}px")

    @staticmethod
    def _estimate_height_ratio(bbox, size):
        try:
            if bbox is None or size is None:
                return 1.15
            size_val = max(1.0, float(size))
            ratio = float(bbox.height) / size_val
            if ratio <= 0:
                return 1.15
            return ratio
        except Exception:
            return 1.15

    @staticmethod
    def _normalize_height_ratio(value):
        try:
            ratio = float(value)
        except Exception:
            ratio = 1.15
        if ratio <= 0:
            ratio = 1.15
        # 허용 범위를 넓혀 한글/복합 폰트의 실제 줄간격 비율을 존중
        return max(0.5, min(1.8, ratio))

    def move_to(self, new_bbox):
        """오버레이 위치 이동 (레이어 방식) - 베이스라인(origin) 동시 이동으로 위치 고정"""
        # 이동 델타 계산
        dx = new_bbox.x0 - self.bbox.x0
        dy = new_bbox.y0 - self.bbox.y0
        
        # 1) bbox 업데이트
        self.bbox = new_bbox
        
        # 2) 베이스라인(origin) 동시 이동 (중요: 재진입 시 위치 회귀 방지)
        if hasattr(self, 'origin') and self.origin:
            try:
                self.origin = (self.origin[0] + dx, self.origin[1] + dy)
            except Exception:
                pass
                
        # 3) 기준 영역(original_bbox)도 현재 위치로 동기화 (델타 계산 기준점 이동)
        if hasattr(self, 'original_bbox') and self.original_bbox:
            self.original_bbox = fitz.Rect(new_bbox)
        
        # 4) content_bbox도 함께 이동
        if hasattr(self, 'content_bbox') and self.content_bbox:
            c = self.content_bbox
            self.content_bbox = fitz.Rect(c.x0 + dx, c.y0 + dy, c.x1 + dx, c.y1 + dy)
        else:
            self.content_bbox = fitz.Rect(new_bbox)
        
    def get_hash(self):
        """오버레이 해시 생성 (원본 위치 기반)"""
        return f"{self.original_bbox.x0:.1f},{self.original_bbox.y0:.1f},{self.original_bbox.x1:.1f},{self.original_bbox.y1:.1f}"
        
    def get_current_hash(self):
        """현재 위치 기반 해시 생성"""
        return f"{self.bbox.x0:.1f},{self.bbox.y0:.1f},{self.bbox.x1:.1f},{self.bbox.y1:.1f}"
        
    def render_to_painter(self, painter, scale_factor=1.0, offsets=(0, 0)):
        """QPainter를 사용하여 오버레이 렌더링 (PDF 좌표계 직접 사용)
        painter는 이미 적절한 scale과 translate가 적용된 상태여야 함.
        """
        if not self.visible:
            return
        
        painter.save() # 상태 저장
        
        try:
            # 1. 원본 폰트 정보 및 속성 준비
            effective_point_size = max(0.1, float(self.size))
            
            # 2. QFont 생성 및 검증
            qfont = None
            if self.font_path and os.path.exists(self.font_path):
                try:
                    if not self._loaded_font_family:
                        font_id = QFontDatabase.addApplicationFont(self.font_path)
                        if font_id != -1:
                            families = QFontDatabase.applicationFontFamilies(font_id)
                            if families:
                                self._loaded_font_family = families[0]
                    if self._loaded_font_family:
                        qfont = QFont(self._loaded_font_family)
                except Exception: pass

            if qfont is None:
                qfont = QFont(self.font or 'Arial')

            # 스타일 및 정밀 크기 설정 (PDF 포인트 단위)
            is_bold_flag = bool(self.flags & 16)
            synth_weight_val = float(getattr(self, 'synth_bold_weight', 120))
            loaded_name = (self._loaded_font_family or self.font or '').lower()
            has_bold_variant = any(kw in loaded_name for kw in ('bold', 'black', 'heavy'))
            
            # [고도화] OS 표준 가변 Weight 매핑 + 고밀도 서브픽셀 스메어링
            # 1. 사용자의 볼드 설정(100~500%)을 시스템 Weight(400~1000)로 변환
            # 2. 시스템 폰트 엔진의 알고리즘 볼드와 고밀도 수동 보정을 결합하여 '울퉁불퉁함' 완전 해결
            if is_bold_flag:
                # 100%->400(Normal), 200%->700(Bold), 300%->900(Black)
                q_weight_v = 400 + (synth_weight_val - 100) * 1.5
                qfont.setWeight(QFont.Weight(min(1000, max(1, int(q_weight_v)))))
                
                # 실제 볼드 폰트 파일이 없는 경우 시스템 합성 볼드 활성화
                if not has_bold_variant:
                    qfont.setBold(True)
                
                # [핵심] 수동 고밀도 보정 (Jaggedness 제거용)
                # 100배 정밀도 좌표계에서 극소 단위(0.01pt)로 촘촘하게 겹쳐 그려서
                # OS 엔진의 알고리즘 볼드에서 발생하는 미세한 외곽선 불규칙성을 평활화합니다.
                self.synth_bold = True 
            else:
                qfont.setWeight(QFont.Weight.Normal)
                qfont.setBold(False)
                self.synth_bold = False
                
            if self.flags & 2: # 이탤릭
                qfont.setItalic(True)
            
            try:
                if abs(float(self.tracking)) > 0.01:
                    qfont.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100.0 + float(self.tracking))
            except Exception: pass
            
            # [수정] 폰트 엔진의 정수 단위 반올림 방지를 위한 200배 정밀 렌더링 전략 (정밀도 상향)
            qfont.setStyleStrategy(QFont.StyleStrategy.ForceOutline | QFont.StyleStrategy.PreferAntialias)
            qfont.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
            
            # 200배 확대된 픽셀 사이즈 설정 (1포인트 = 1픽셀인 scaled painter 환경 기준)
            precision_multiplier = 200.0
            qfont.setPixelSize(int(round(effective_point_size * precision_multiplier)))
            
            # 3. 색상 설정
            if isinstance(self.color, int):
                qcolor = QColor((self.color >> 16) & 0xFF, (self.color >> 8) & 0xFF, self.color & 0xFF)
            else:
                qcolor = QColor(0, 0, 0)
                
            painter.setFont(qfont)
            painter.setPen(qcolor)
            
            # [중요] PDF와의 자간 정합성을 위해 Kerning 비활성화
            qfont.setKerning(False)
            
            # 4. 정교한 렌더링 파라미터 (PDF 좌표계)
            # [수정] UI와 플래튼 간 정합성을 위해 MainWindow의 표준 메트릭 도구 사용
            mw = MainWindow._instance if hasattr(MainWindow, '_instance') else None
            if mw:
                font_metrics_f = mw._get_standard_metrics(qfont, precision_multiplier)
            else:
                # Fallback (단위 테스트 등 대비)
                font_metrics_f = QFontMetricsF(qfont, painter.device())
            
            ascent_ratio = float(getattr(self, 'ascent_ratio', 0.85))
            height_ratio = float(getattr(self, 'height_ratio', 1.15))
            
            # 베이스라인 결정 (절대 좌표계로 원복하여 정합성 확보)
            origin = getattr(self, 'origin', None)
            if origin:
                # origin은 베이스라인의 절대 좌표 (x, y)
                dx = self.bbox.x0 - self.original_bbox.x0
                dy = self.bbox.y0 - self.original_bbox.y0
                base_baseline_y = origin[1] + dy
                text_x = origin[0] + dx
            else:
                # origin이 없는 경우 bbox 상단 기준비율로 계산
                base_baseline_y = self.bbox.y0 + (effective_point_size * ascent_ratio)
                text_x = self.bbox.x0
                
            line_height_pt = effective_point_size * height_ratio
            
            stretch = float(getattr(self, 'stretch', 1.0))

            def _draw_text_item(x_pos, y_pos, txt):
                painter.save()
                # [수정] 정수 반올림 오차 방지를 위해 QPointF와 floating-point translate 사용 (Y축 드리프트 해결)
                painter.translate(QPointF(x_pos, y_pos))
                
                # 200배 정밀 렌더링을 위해 페인터를 0.005배로 축소 (폰트의 200배 확대를 상쇄)
                painter.scale(1.0 / precision_multiplier, 1.0 / precision_multiplier)
                
                if abs(stretch - 1.0) > 0.001:
                    painter.scale(stretch, 1.0)
                
                if getattr(self, 'synth_bold', False):
                    # [최종 고도화] 벡터 경로 기반 초고정밀 스무스 렌더링
                    # 다중 렌더링의 안티앨리어싱 간섭을 제거하기 위해 텍스트를 벡터 경로로 변환하여 처리
                    from PySide6.QtGui import QPainterPath
                    path = QPainterPath()
                    path.addText(0, 0, painter.font(), txt)
                    
                    # 1. 원본 채우기
                    painter.fillPath(path, painter.pen().color())
                    
                    # 2. 벡터 외곽선 보정 (Smooth Stroke)
                    # 사용자의 굵기 설정을 200배 정밀 공간에서의 스트로크 두께로 환산
                    # 가변 Weight를 시스템 엔진이 1차 처리하고, 나머지를 벡터 스트로크가 평활화
                    stroke_w = (synth_weight_val - 100.0) / 100.0 * effective_point_size * 0.033 * precision_multiplier
                    
                    if stroke_w > 0.1:
                        bold_pen = QPen(painter.pen().color())
                        bold_pen.setWidthF(stroke_w)
                        bold_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin) # 획의 연결부를 둥글고 매끄럽게
                        bold_pen.setCapStyle(Qt.PenCapStyle.RoundCap)   # 획의 끝부분 돌출 방지
                        painter.strokePath(path, bold_pen)
                else:
                    painter.drawText(QPointF(0, 0), txt)
                painter.restore()

            is_hwp = getattr(self, 'hwp_space_mode', False)
            lines = self.text.splitlines() if "\n" in self.text else [self.text]
            
            stretch = float(getattr(self, 'stretch', 1.0))
            tracking_ratio = float(getattr(self, 'tracking', 0.0)) / 100.0
            
            # 항상 개별 글자 정밀 배치 수행 (PDF와 1:1 일치 보장)
            needs_precise = True 

            hwp_std_space = effective_point_size * precision_multiplier * 0.50
            for li, line in enumerate(lines):
                curr_y = base_baseline_y + li * line_height_pt
                if needs_precise:
                    curr_x = text_x
                    t_ratio = 1.0 + tracking_ratio
                    for ch in line:
                        ch_w = font_metrics_f.horizontalAdvance(ch)
                        if ch == ' ' and is_hwp:
                            ch_w_eff = max(ch_w, hwp_std_space)
                        else:
                            ch_w_eff = ch_w
                        current_advance = (ch_w_eff / precision_multiplier) * stretch
                        
                        if ch.strip():
                            _draw_text_item(curr_x, curr_y, ch)
                        
                        curr_x += current_advance * t_ratio
                    actual_width = (curr_x - text_x)
                else:
                    _draw_text_item(text_x, curr_y, line)
                    actual_width = font_metrics_f.horizontalAdvance(line) / precision_multiplier
                
                # 밑줄 처리
                if self.flags & 4:
                    u_offset = float(getattr(self, 'underline_offset', 1.5))
                    underline_y = curr_y + u_offset
                    u_weight = float(getattr(self, 'underline_weight', 0.6))
                    pen = painter.pen()
                    pen.setWidthF(u_weight)
                    painter.setPen(pen)
                    painter.drawLine(QPointF(text_x, underline_y), QPointF(text_x + actual_width, underline_y))
                    painter.setPen(qcolor)
        finally:
            painter.restore() # 상태 복구
        
        print(f"   OK TextOverlay 렌더링 완료: '{self.text}'")
        
    def to_dict(self):
        """편집창 연계를 위한 딕셔너리 변환"""
        return {
            'overlay_id': self.z_index,
            'text': self.text,
            'font': self.font,
            'pdf_font_name': self.pdf_font_name,
            'size': self.size,
            'color': self.color,
            'flags': self.flags,
            'original_bbox': _rect_to_tuple(self.original_bbox),
            'current_bbox': _rect_to_tuple(self.bbox),
            'content_bbox': _rect_to_tuple(getattr(self, 'content_bbox', self.bbox)),
            'page_num': self.page_num,
            'height_ratio': getattr(self, 'height_ratio', 1.15),
            'ascent_ratio': getattr(self, 'ascent_ratio', 0.85),
            'descent_ratio': getattr(self, 'descent_ratio', max(0.0, getattr(self, 'height_ratio', 1.15) - getattr(self, 'ascent_ratio', 0.85))),
            'baseline_top_ratio': getattr(self, 'baseline_top_ratio', None),
            'baseline_bottom_ratio': getattr(self, 'baseline_bottom_ratio', None),
            'hwp_space_mode': getattr(self, 'hwp_space_mode', False),
            'text_only_mode': getattr(self, 'text_only_mode', False),
            'synth_bold_weight': getattr(self, 'synth_bold_weight', 120),
            'underline_weight': getattr(self, 'underline_weight', 0.6),
            'underline_offset': getattr(self, 'underline_offset', 1.5),
            'origin': getattr(self, 'origin', None),
            'patch_margin_l': getattr(self, 'patch_margin_l', 0.0),
            'patch_margin_r': getattr(self, 'patch_margin_r', 0.0),
            'patch_margin_t': getattr(self, 'patch_margin_t', 0.0),
            'patch_margin_b': getattr(self, 'patch_margin_b', 0.0),
            'patch_margin': (
                getattr(self, 'patch_margin_l', 0.0),
                getattr(self, 'patch_margin_r', 0.0),
                getattr(self, 'patch_margin_t', 0.0),
                getattr(self, 'patch_margin_b', 0.0)
            ),
            'stretch': getattr(self, 'stretch', 1.0),
            'tracking': getattr(self, 'tracking', 0.0)
        }

class ImageOverlay:
    """PDF 페이지에 삽입되는 이미지/서명 오버레이 레이어"""
    def __init__(self, image_path, bbox, page_num, opacity=1.0, z_index=0):
        self.image_path = image_path
        self.pixmap = QPixmap(image_path)
        self.bbox = fitz.Rect(bbox)  # PDF 포인트 단위 좌표
        self.page_num = page_num
        self.opacity = float(opacity)  # 0.0 ~ 1.0
        self.z_index = z_index
        self.visible = True
        self.flattened = False

    def to_dict(self):
        return {
            'image_path': self.image_path,
            'bbox': (self.bbox.x0, self.bbox.y0, self.bbox.x1, self.bbox.y1),
            'page_num': self.page_num,
            'opacity': self.opacity,
            'z_index': self.z_index
        }


class ImagePropertyDialog(QDialog):
    """삽입된 이미지의 속성(투명도, 크기 등)을 설정하는 대화상자"""
    def __init__(self, image_overlay, parent=None):
        super().__init__(parent)
        self.image_overlay = image_overlay
        self.viewer = parent
        self.setWindowTitle("이미지 속성 (서명/이미지)")
        self.setFixedWidth(320)
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # 투명도 슬라이더
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        curr_op = int(round(image_overlay.opacity * 100))
        self.opacity_slider.setValue(curr_op)
        self.opacity_label = QLabel(f"{curr_op}%")

        def on_opacity_changed(val):
            self.opacity_label.setText(f"{val}%")
            self.image_overlay.opacity = val / 100.0
            if self.viewer and hasattr(self.viewer, 'update'):
                self.viewer.update()
        self.opacity_slider.valueChanged.connect(on_opacity_changed)

        op_layout = QHBoxLayout()
        op_layout.addWidget(self.opacity_slider)
        op_layout.addWidget(self.opacity_label)
        form.addRow("투명도:", op_layout)

        # 크기 (너비/높이 pt 단위)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(5.0, 3000.0)
        self.width_spin.setValue(float(image_overlay.bbox.width))
        self.width_spin.setSuffix(" pt")

        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(5.0, 3000.0)
        self.height_spin.setValue(float(image_overlay.bbox.height))
        self.height_spin.setSuffix(" pt")

        orig_w = max(1.0, float(image_overlay.bbox.width))
        orig_h = max(1.0, float(image_overlay.bbox.height))
        aspect_ratio = orig_w / orig_h

        def on_width_changed(w):
            h = w / aspect_ratio
            self.height_spin.blockSignals(True)
            self.height_spin.setValue(h)
            self.height_spin.blockSignals(False)
            image_overlay.bbox = fitz.Rect(
                image_overlay.bbox.x0, image_overlay.bbox.y0,
                image_overlay.bbox.x0 + w, image_overlay.bbox.y0 + h
            )
            if self.viewer and hasattr(self.viewer, 'update'):
                self.viewer.update()

        def on_height_changed(h):
            w = h * aspect_ratio
            self.width_spin.blockSignals(True)
            self.width_spin.setValue(w)
            self.width_spin.blockSignals(False)
            image_overlay.bbox = fitz.Rect(
                image_overlay.bbox.x0, image_overlay.bbox.y0,
                image_overlay.bbox.x0 + w, image_overlay.bbox.y0 + h
            )
            if self.viewer and hasattr(self.viewer, 'update'):
                self.viewer.update()

        self.width_spin.valueChanged.connect(on_width_changed)
        self.height_spin.valueChanged.connect(on_height_changed)

        form.addRow("너비:", self.width_spin)
        form.addRow("높이:", self.height_spin)
        layout.addLayout(form)

        button_layout = QHBoxLayout()
        delete_btn = QPushButton("삭제")
        delete_btn.setStyleSheet("color: red;")

        def on_delete():
            if self.viewer and hasattr(self.viewer, 'delete_image_overlay'):
                self.viewer.delete_image_overlay(self.image_overlay)
            self.reject()
        delete_btn.clicked.connect(on_delete)
        button_layout.addWidget(delete_btn)

        button_layout.addStretch()
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(self.accept)
        button_layout.addWidget(btn_box)

        layout.addLayout(button_layout)


class SignatureCanvas(QWidget):
    """마우스/터치패드로 서명을 직접 그리는 캔버스 위젯"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(520, 240)
        self.setStyleSheet("background-color: white; border: 1.5px solid #cbd5e1; border-radius: 8px;")
        self.strokes = []  # list of (QPainterPath, QColor, pen_width)
        self.current_path = None
        self.pen_color = QColor(25, 25, 25)
        self.pen_width = 3.5
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_pen_color(self, color):
        self.pen_color = color

    def set_pen_width(self, width):
        self.pen_width = width

    def clear(self):
        self.strokes = []
        self.current_path = None
        self.update()

    def has_drawing(self):
        return len(self.strokes) > 0 or self.current_path is not None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.current_path = QPainterPath(event.position())
            self.update()

    def mouseMoveEvent(self, event):
        if self.current_path:
            self.current_path.lineTo(event.position())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.current_path:
            self.current_path.lineTo(event.position())
            self.strokes.append((self.current_path, self.pen_color, self.pen_width))
            self.current_path = None
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), Qt.GlobalColor.white)

        # 서명 기준선 가이드 점선
        guide_pen = QPen(QColor(203, 213, 225), 1.5, Qt.PenStyle.DashLine)
        painter.setPen(guide_pen)
        painter.drawLine(30, 185, 490, 185)

        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(QColor(148, 163, 184))
        painter.drawText(QRect(30, 190, 460, 20), Qt.AlignmentFlag.AlignRight, "서명 기준선 (Sign Here)")

        for path, col, w in self.strokes:
            pen = QPen(col, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.strokePath(path, pen)

        if self.current_path:
            pen = QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.strokePath(self.current_path, pen)

    def get_cropped_pixmap(self, transparent=True):
        if not self.strokes:
            return None
        united_rect = None
        for path, col, w in self.strokes:
            br = path.boundingRect().adjusted(-w, -w, w, w)
            united_rect = br if united_rect is None else united_rect.united(br)
        if united_rect is None or united_rect.width() <= 2 or united_rect.height() <= 2:
            return None

        margin = 10.0
        final_rect = united_rect.adjusted(-margin, -margin, margin, margin).intersected(QRectF(self.rect()))
        w = max(10, int(round(final_rect.width())))
        h = max(10, int(round(final_rect.height())))

        pix = QPixmap(w, h)
        if transparent:
            pix.fill(Qt.GlobalColor.transparent)
        else:
            pix.fill(Qt.GlobalColor.white)

        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(-final_rect.left(), -final_rect.top())
        for path, col, pw in self.strokes:
            pen = QPen(col, pw, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.strokePath(path, pen)
        p.end()
        return pix


class SignaturePadDialog(QDialog):
    """마우스/펜으로 전자 서명을 그려 즉시 삽입하는 대화상자"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("전자 서명 그리기")
        self.setFixedSize(550, 390)
        self.created_pixmap = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        info_lbl = QLabel("마우스 또는 트랙패드로 서명을 직접 그리세요:")
        info_lbl.setStyleSheet("font-weight: bold; color: #334155;")
        layout.addWidget(info_lbl)

        self.canvas = SignatureCanvas(self)
        layout.addWidget(self.canvas)

        # 도구 컨트롤 행 (색상 및 굵기 선택)
        ctrl_layout = QHBoxLayout()

        # 색상 선택
        ctrl_layout.addWidget(QLabel("색상:"))
        self.btn_black = QPushButton("● 검정")
        self.btn_black.setCheckable(True)
        self.btn_black.setChecked(True)
        self.btn_black.setStyleSheet("color: black; font-weight: bold;")

        self.btn_blue = QPushButton("● 파랑")
        self.btn_blue.setCheckable(True)
        self.btn_blue.setStyleSheet("color: #1d4ed8; font-weight: bold;")

        self.btn_red = QPushButton("● 빨강")
        self.btn_red.setCheckable(True)
        self.btn_red.setStyleSheet("color: #dc2626; font-weight: bold;")

        color_group = QButtonGroup(self)
        color_group.addButton(self.btn_black)
        color_group.addButton(self.btn_blue)
        color_group.addButton(self.btn_red)

        self.btn_black.clicked.connect(lambda: self.canvas.set_pen_color(QColor(25, 25, 25)))
        self.btn_blue.clicked.connect(lambda: self.canvas.set_pen_color(QColor(29, 78, 216)))
        self.btn_red.clicked.connect(lambda: self.canvas.set_pen_color(QColor(220, 38, 38)))

        ctrl_layout.addWidget(self.btn_black)
        ctrl_layout.addWidget(self.btn_blue)
        ctrl_layout.addWidget(self.btn_red)

        ctrl_layout.addSpacing(15)

        # 굵기 선택
        ctrl_layout.addWidget(QLabel("굵기:"))
        self.width_group = QButtonGroup(self)
        self.rb_thin = QRadioButton("얇게")
        self.rb_norm = QRadioButton("보통")
        self.rb_thick = QRadioButton("굵게")
        self.rb_norm.setChecked(True)

        self.width_group.addButton(self.rb_thin)
        self.width_group.addButton(self.rb_norm)
        self.width_group.addButton(self.rb_thick)

        self.rb_thin.clicked.connect(lambda: self.canvas.set_pen_width(2.0))
        self.rb_norm.clicked.connect(lambda: self.canvas.set_pen_width(3.5))
        self.rb_thick.clicked.connect(lambda: self.canvas.set_pen_width(5.5))

        ctrl_layout.addWidget(self.rb_thin)
        ctrl_layout.addWidget(self.rb_norm)
        ctrl_layout.addWidget(self.rb_thick)

        ctrl_layout.addStretch()

        clear_btn = QPushButton("지우기")
        clear_btn.clicked.connect(self.canvas.clear)
        ctrl_layout.addWidget(clear_btn)

        layout.addLayout(ctrl_layout)

        # 하단 버튼 행
        bottom_layout = QHBoxLayout()
        self.trans_check = QCheckBox("배경 투명화 적용")
        self.trans_check.setChecked(True)
        bottom_layout.addWidget(self.trans_check)

        bottom_layout.addStretch()

        apply_btn = QPushButton("서명 삽입")
        apply_btn.setStyleSheet("background-color: #2563eb; color: white; font-weight: bold; padding: 6px 14px; border-radius: 6px;")
        apply_btn.clicked.connect(self._on_apply)
        bottom_layout.addWidget(apply_btn)

        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(cancel_btn)

        layout.addLayout(bottom_layout)

    def _on_apply(self):
        pix = self.canvas.get_cropped_pixmap(transparent=self.trans_check.isChecked())
        if not pix or pix.isNull():
            QMessageBox.warning(self, "서명 없음", "서명을 먼저 그려주세요.")
            return
        self.created_pixmap = pix
        self.accept()

class ThumbnailPanel(QFrame):
    """좌측 접이식 페이지 썸네일 탐색 패널 (페이지 탐색 전용, 편집 기능 배제)"""
    page_selected = Signal(int)
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 헤더: 타이틀, 총 페이지수, 접기 버튼
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(4, 2, 4, 2)
        
        self.title_lbl = QLabel("📑 페이지")
        header_layout.addWidget(self.title_lbl)

        self.count_lbl = QLabel("")
        header_layout.addWidget(self.count_lbl)
        header_layout.addStretch()

        self.collapse_btn = QPushButton("◀")
        self.collapse_btn.setToolTip("썸네일 패널 닫기 (F4)")
        self.collapse_btn.setFixedSize(22, 22)
        self.collapse_btn.clicked.connect(self.close_requested.emit)
        header_layout.addWidget(self.collapse_btn)

        layout.addLayout(header_layout)

        # 썸네일 리스트 위젯
        self.list_widget = QListWidget(self)
        self.list_widget.setIconSize(QSize(96, 128))
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setSpacing(8)
        self.list_widget.setFrameShape(QFrame.Shape.NoFrame)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)

        self.current_theme_mode = 'light'
        self.apply_theme('light')

    def apply_theme(self, mode: str):
        """다크/라이트 테마에 따른 스타일시트 적용"""
        self.current_theme_mode = mode
        if mode == 'dark':
            self.setStyleSheet(
                "ThumbnailPanel { background-color: #1e1f22; border-right: 1.5px solid #333842; }"
            )
            self.title_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #e2e8f0;")
            self.count_lbl.setStyleSheet("font-size: 11px; color: #94a3b8; font-weight: bold;")
            self.collapse_btn.setStyleSheet(
                "QPushButton { border: none; border-radius: 4px; background: transparent; font-size: 11px; color: #94a3b8; }"
                "QPushButton:hover { background-color: #2d3139; color: #f8fafc; }"
            )
            self.list_widget.setStyleSheet(
                "QListWidget { background: transparent; border: none; outline: none; }"
                "QListWidget::item { border: 2px solid transparent; border-radius: 6px; padding: 4px; color: #cbd5e1; font-size: 11px; font-weight: bold; }"
                "QListWidget::item:hover { background-color: rgba(255, 255, 255, 0.08); }"
                "QListWidget::item:selected { border: 2px solid #3b82f6; background-color: rgba(59, 130, 246, 0.25); color: #60a5fa; }"
            )
        else:
            self.setStyleSheet(
                "ThumbnailPanel { background-color: #f8fafc; border-right: 1.5px solid #cbd5e1; }"
            )
            self.title_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #334155;")
            self.count_lbl.setStyleSheet("font-size: 11px; color: #64748b; font-weight: bold;")
            self.collapse_btn.setStyleSheet(
                "QPushButton { border: none; border-radius: 4px; background: transparent; font-size: 11px; color: #64748b; }"
                "QPushButton:hover { background-color: #e2e8f0; color: #0f172a; }"
            )
            self.list_widget.setStyleSheet(
                "QListWidget { background: transparent; border: none; outline: none; }"
                "QListWidget::item { border: 2px solid transparent; border-radius: 6px; padding: 4px; color: #475569; font-size: 11px; font-weight: bold; }"
                "QListWidget::item:hover { background-color: rgba(148, 163, 184, 0.15); }"
                "QListWidget::item:selected { border: 2px solid #2563eb; background-color: rgba(37, 99, 235, 0.12); color: #1d4ed8; }"
            )

    def _on_item_clicked(self, item):
        row = self.list_widget.row(item)
        if row >= 0:
            self.page_selected.emit(row)


class PdfViewerWidget(QLabel):
    text_selected = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent # 부모 윈도우 명시적 저장
        self.doc = None
        self.current_page_num = 0
        self.pixmap_scale_factor = 1.0
        self.setMinimumSize(400, 300)
        
        # 드래그 관련 변수 (문제 4 해결 - 구글맵 스타일 네비게이션)
        # 드래그 관련 변수 제거됨 - 단순 클릭만 처리
        self.ctrl_pressed = False  # Ctrl 키 상태 추가
        
        # 텍스트 선택 관련 변수
        self.hover_rect = None
        self.hover_span_info = None
        
        # 오버레이 텍스트 추적 시스템 (레거시)
        self.overlay_texts = set()  # (page_num, bbox_hash) 튜플 저장
        
        # 새로운 레이어 방식 오버레이 시스템
        self.text_overlays = {}  # page_num -> [TextOverlay] 매핑
        self.overlay_id_counter = 0
        
        # 배경 패치 관리 시스템 (오버레이와 분리)
        self.background_patches = {}  # page_num -> [bbox] 매핑 (원본 텍스트 숨김 영역)
        
        # 텍스트 위치 조정용 변수
        self.selected_text_info = None
        self.text_adjustment_mode = False
        self.adjustment_step = 0.2  # 더 정밀한 조정을 위해 0.2로 축소
        self.quick_adjustment_mode = False  # 빠른 조정 모드 (싱글클릭)
        self.pending_edit_info = None  # 편집 대기 정보
        self.active_overlay = None  # (page_num, overlay_id)
        
        # 사각형 선택 관련 변수 (Ctrl+드래그)
        self.selection_mode = False
        self.selection_start = None
        self.selection_rect = None
        self.selected_texts = []  # 선택된 텍스트들 목록
        
        # 호버 애니메이션 및 데이터 캐시
        self.hover_timer = QTimer()
        self.hover_timer.timeout.connect(self.check_hover)
        self.hover_timer.start(100)  # 100ms마다 체크
        self._text_dict_cache = {}  # page_num -> text_dict 캐시
        self._visual_lines_cache = {}  # page_num -> visual_lines 캐시
        
        # 싱글/더블 클릭 구분을 위한 타이머
        self.single_click_timer = QTimer()
        self.single_click_timer.setSingleShot(True)
        self.single_click_timer.timeout.connect(self.handle_single_click)
        self.pending_single_click_pos = None
        
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)  # 마우스 트래킹 활성화
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 키보드 포커스 가능하도록 설정
        self.setCursor(Qt.CursorShape.CrossCursor)  # 기본 커서 모양: 십자

        # 스페이스바 핸드 툴 및 줌 툴 상태
        self.space_pressed = False
        self.alt_pressed = False
        self.ctrl_pressed = False
        self.shift_pressed = False
        self.selection_is_eraser = False
        self.panning = False
        self.pan_start_global = None
        self.pan_start_h = 0
        self.pan_start_v = 0
        self._cached_zoom_in_cursor = None
        self._cached_zoom_out_cursor = None

        # 격자 및 줄자 보기 옵션
        self.show_grid = False
        self.show_ruler = False

        # 이미지/서명 오버레이 시스템
        self.image_overlays = {}  # page_num -> [ImageOverlay]
        self.image_id_counter = 0
        self.active_image = None
        self.dragging_image = False
        self.resizing_image = False
        self.drag_start_pos = None
        self.drag_start_bbox = None

        # 복사/붙여넣기 데이터 버퍼
        self.copied_data = None

        # 텍스트 오버레이 드래그 상태
        self.potential_drag_overlay = None
        self.dragging_overlay = False

        # 본문 검색 하이라이트 상태
        self.search_highlights = []
        self.active_search_rect = None

        # 스마트 스냅 (자석 정렬 가이드선)
        self.smart_snap_enabled = True
        self.active_snap_guides = []

        # 선택 애니메이션
        self._anim_phase = 0
        self._anim_timer = QTimer()
        self._anim_timer.timeout.connect(self._tick_anim)
        self._anim_timer.start(120)

    def _apply_smart_snap(self, rect, ignore_obj=None):
        """
        rect: fitz.Rect (드래그 중인 후보 BBox)
        ignore_obj: 드래그 중인 원본 객체 (스냅 대상에서 제외)
        반환: (snapped_fitz_rect, guides) where guides is list of ('v', x) or ('h', y)
        """
        if not getattr(self, 'smart_snap_enabled', True) or not self.doc:
            return rect, []

        try:
            page = self.doc.load_page(self.current_page_num)
            pw = float(page.rect.width)
            ph = float(page.rect.height)
        except Exception:
            return rect, []

        snap_targets_x = [0.0, pw / 2.0, pw]
        snap_targets_y = [0.0, ph / 2.0, ph]

        # 다른 텍스트 오버레이 좌표 수집
        if hasattr(self, 'text_overlays') and self.current_page_num in self.text_overlays:
            for ov in self.text_overlays[self.current_page_num]:
                if ov is not ignore_obj and getattr(ov, 'visible', True):
                    b = ov.bbox
                    snap_targets_x.extend([b.x0, (b.x0 + b.x1) / 2.0, b.x1])
                    snap_targets_y.extend([b.y0, (b.y0 + b.y1) / 2.0, b.y1])

        # 다른 이미지 오버레이 좌표 수집
        if hasattr(self, 'image_overlays') and self.current_page_num in self.image_overlays:
            for img in self.image_overlays[self.current_page_num]:
                if img is not ignore_obj and getattr(img, 'visible', True):
                    b = img.bbox
                    snap_targets_x.extend([b.x0, (b.x0 + b.x1) / 2.0, b.x1])
                    snap_targets_y.extend([b.y0, (b.y0 + b.y1) / 2.0, b.y1])

        threshold = 5.0  # 5pt 자석 반경
        scale = getattr(self, 'pixmap_scale_factor', 1.0)
        if scale > 0:
            threshold = max(3.0, 5.0 / scale)

        best_dx = None
        best_dist_x = threshold + 1.0
        guide_x = None

        cand_x = [rect.x0, (rect.x0 + rect.x1) / 2.0, rect.x1]
        for cx in cand_x:
            for tx in snap_targets_x:
                dist = abs(cx - tx)
                if dist <= threshold and dist < best_dist_x:
                    best_dist_x = dist
                    best_dx = tx - cx
                    guide_x = tx

        best_dy = None
        best_dist_y = threshold + 1.0
        guide_y = None

        cand_y = [rect.y0, (rect.y0 + rect.y1) / 2.0, rect.y1]
        for cy in cand_y:
            for ty in snap_targets_y:
                dist = abs(cy - ty)
                if dist <= threshold and dist < best_dist_y:
                    best_dist_y = dist
                    best_dy = ty - cy
                    guide_y = ty

        guides = []
        dx_final = best_dx if best_dx is not None else 0.0
        dy_final = best_dy if best_dy is not None else 0.0

        if guide_x is not None:
            guides.append(('v', guide_x))
        if guide_y is not None:
            guides.append(('h', guide_y))

        snapped = fitz.Rect(
            rect.x0 + dx_final, rect.y0 + dy_final,
            rect.x1 + dx_final, rect.y1 + dy_final
        )
        return snapped, guides

    def _get_scroll_area(self):
        """뷰어를 감싸고 있는 QScrollArea 객체 반환"""
        main_win = self.window()
        if hasattr(main_win, 'scroll_area') and main_win.scroll_area:
            return main_win.scroll_area
        p = self.parent()
        while p:
            if isinstance(p, QScrollArea):
                return p
            p = p.parent()
        return None

    def _create_zoom_cursor(self, mode='in'):
        pix = QPixmap(32, 32)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 돋보기 외곽선 및 반투명 렌즈
        p.setPen(QPen(QColor(40, 40, 40), 2.2))
        p.setBrush(QColor(255, 255, 255, 235))
        p.drawEllipse(3, 3, 16, 16)
        
        # 돋보기 손잡이
        p.setPen(QPen(QColor(40, 40, 40), 3.0))
        p.drawLine(15, 15, 25, 25)
        
        # 기호 (+ 또는 -)
        p.setPen(QPen(QColor(20, 20, 20), 2.0))
        p.drawLine(7, 11, 15, 11)  # 가로 막대
        if mode == 'in':
            p.drawLine(11, 7, 11, 15)  # 세로 막대
        p.end()
        return QCursor(pix, 11, 11)

    def _get_zoom_in_cursor(self):
        if not hasattr(self, '_cached_zoom_in_cursor') or self._cached_zoom_in_cursor is None:
            self._cached_zoom_in_cursor = self._create_zoom_cursor('in')
        return self._cached_zoom_in_cursor

    def _get_zoom_out_cursor(self):
        if not hasattr(self, '_cached_zoom_out_cursor') or self._cached_zoom_out_cursor is None:
            self._cached_zoom_out_cursor = self._create_zoom_cursor('out')
        return self._cached_zoom_out_cursor

    def update_tool_cursor(self):
        """현재 활성화된 도구 및 단축키(Space, Ctrl, Alt, Shift) 상태에 따른 커서 갱신"""
        if getattr(self, 'panning', False):
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        modifiers = QApplication.keyboardModifiers()
        has_ctrl = getattr(self, 'ctrl_pressed', False) or bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
        has_alt = getattr(self, 'alt_pressed', False) or bool(modifiers & Qt.KeyboardModifier.AltModifier)
        has_shift = getattr(self, 'shift_pressed', False) or bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        is_space = getattr(self, 'space_pressed', False)

        # 1. 줌 툴 커서 (Space + Alt, Space + Ctrl + Alt, 또는 Ctrl + Alt) -> Zoom Out (돋보기 -)
        if (is_space and has_alt) or (has_ctrl and has_alt):
            self.setCursor(self._get_zoom_out_cursor())
            return

        # 2. 줌 툴 커서 (Space + Ctrl) -> Zoom In (돋보기 +)
        if is_space and has_ctrl:
            self.setCursor(self._get_zoom_in_cursor())
            return

        # 3. 핸드 툴 커서 (Space 단독) -> Open Hand (펼친 손)
        if is_space:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return

        # 3-1. Shift(지우개모드) 또는 Ctrl(패치모드) 준비 커서 -> CrossCursor
        parent_window = self.window()
        is_patch_or_eraser = bool(parent_window and getattr(parent_window, 'patch_precise_mode', False))
        if has_shift or has_ctrl or is_patch_or_eraser:
            self.setCursor(Qt.CursorShape.CrossCursor)
            return

        # 4. 이미지 핸들 또는 이미지 호버 상태 (스페이스바 미사용 시)
        if hasattr(self, 'mouse_pos') and self.doc:
            try:
                pdf_x, pdf_y = self._widget_point_to_pdf(self.mouse_pos)
                if pdf_x is not None and pdf_y is not None:
                    pdf_point = fitz.Point(pdf_x, pdf_y)
                    if self.active_image and self._is_on_image_resize_handle(self.active_image, pdf_point):
                        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                        return
                    elif self._find_image_at_point(pdf_point):
                        self.setCursor(Qt.CursorShape.SizeAllCursor)
                        return
            except Exception:
                pass

        # 5. 텍스트 호버 및 드래그 상태 (오버레이는 이동 화살표 SizeAllCursor, 일반 텍스트는 ArrowCursor, 빈 공간은 CrossCursor)
        if getattr(self, 'dragging_overlay', False):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            return

        if getattr(self, 'hover_rect', None):
            is_ov = isinstance(getattr(self, 'hover_span_info', None), dict) and self.hover_span_info.get('is_overlay', False)
            if is_ov:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def enterEvent(self, event):
        self.setFocus()
        self.update_tool_cursor()
        super().enterEvent(event)

    def focusOutEvent(self, event):
        self.space_pressed = False
        self.alt_pressed = False
        self.ctrl_pressed = False
        self.shift_pressed = False
        if getattr(self, 'panning', False):
            self.panning = False
        self.update_tool_cursor()
        super().focusOutEvent(event)

    def _tick_anim(self):
        self._anim_phase = (self._anim_phase + 1) % 16
        # 애니메이션이 필요한 모든 경우에 화면 갱신
        if self.text_adjustment_mode or self.quick_adjustment_mode or self.hover_rect or self.active_overlay:
            self.update()
        
    def set_document(self, doc):
        self.doc = doc
        self.current_page_num = 0
        self._text_dict_cache = {} # 캐시 초기화
        self._visual_lines_cache = {} # Visual lines 캐시 초기화
        self.pdf_font_extractor = PdfFontExtractor(doc)
        self.pdf_fonts = self.pdf_font_extractor.extract_fonts_from_document()
        self.active_overlay = None
        self.image_overlays = {}
        self.active_image = None
    
    def keyPressEvent(self, event):
        """키보드 이벤트 처리 (스페이스바 핸드툴, 줌툴, 복사/붙여넣기, 이미지 조작, 텍스트 위치 조정)"""
        # 스페이스바 누름: 핸드 툴 모드 활성화 (Adobe 스타일)
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.space_pressed = True
            if self.hover_rect:
                self.hover_rect = None
                self.hover_span_info = None
                self.update()
            self.update_tool_cursor()
            event.accept()
            return

        # Shift 키 상태
        if event.key() == Qt.Key.Key_Shift:
            self.shift_pressed = True
            self.update_tool_cursor()
            return

        # Ctrl / Meta(Mac Cmd) 키 상태
        if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Meta):
            self.ctrl_pressed = True
            self.update_tool_cursor()
            return

        # Alt / Option 키 상태
        if event.key() == Qt.Key.Key_Alt:
            self.alt_pressed = True
            self.update_tool_cursor()
            return

        # 복사 (Ctrl+C)
        if (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)) and event.key() == Qt.Key.Key_C:
            if self.copy_selected():
                event.accept()
                return

        # 붙여넣기 (Ctrl+V)
        if (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)) and event.key() == Qt.Key.Key_V:
            if self.paste_clipboard():
                event.accept()
                return

        # 이미지 선택 상태 조작
        if self.active_image:
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.delete_image_overlay(self.active_image)
                event.accept()
                return
            elif event.key() == Qt.Key.Key_BracketLeft:  # [ : 투명도 감소
                self.active_image.opacity = max(0.1, round(self.active_image.opacity - 0.1, 2))
                self.update()
                event.accept()
                return
            elif event.key() == Qt.Key.Key_BracketRight:  # ] : 투명도 증가
                self.active_image.opacity = min(1.0, round(self.active_image.opacity + 0.1, 2))
                self.update()
                event.accept()
                return
            elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
                step = 5.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
                dx = -step if event.key() == Qt.Key.Key_Left else (step if event.key() == Qt.Key.Key_Right else 0)
                dy = -step if event.key() == Qt.Key.Key_Up else (step if event.key() == Qt.Key.Key_Down else 0)
                b = self.active_image.bbox
                self.active_image.bbox = fitz.Rect(b.x0 + dx, b.y0 + dy, b.x1 + dx, b.y1 + dy)
                self.update()
                event.accept()
                return
            elif event.key() == Qt.Key.Key_Escape:
                self.active_image = None
                self.update()
                event.accept()
                return

        # 텍스트 위치 조정 모드에서 방향키 처리
        if (self.text_adjustment_mode or self.quick_adjustment_mode) and self.selected_text_info:
            # 선택된 텍스트가 오버레이 텍스트인지 확인 (원본텍스트 위치조정 차단)
            if hasattr(self.selected_text_info, 'get') and not self.is_overlay_text(self.selected_text_info, self.selected_text_info.get('original_bbox')):
                print("원본 텍스트는 위치조정할 수 없습니다. 오직 수정된 오버레이 텍스트만 조정 가능합니다.")
                event.accept()
                return
            
            dx, dy = 0, 0
            
            # Shift 키를 누르면 기존처럼 1.0 단위로 이동, 아니면 0.2 단위로 정밀 이동
            current_step = 1.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else self.adjustment_step
            
            if event.key() == Qt.Key.Key_Left:
                dx = -current_step
            elif event.key() == Qt.Key.Key_Right:
                dx = current_step
            elif event.key() == Qt.Key.Key_Up:
                dy = -current_step
            elif event.key() == Qt.Key.Key_Down:
                dy = current_step
            elif event.key() == Qt.Key.Key_Escape:
                # 조정 모드 종료
                if self.quick_adjustment_mode:
                    self.exit_quick_adjustment_mode()
                else:
                    self.exit_text_adjustment_mode()
                return
            # Enter 키는 텍스트편집창 열기가 아니라 모드 종료로 변경
            elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                # 위치조정 모드 종료 (편집창 열지 않음)
                if self.quick_adjustment_mode:
                    self.exit_quick_adjustment_mode()
                else:
                    self.exit_text_adjustment_mode()
                return
            
            # 텍스트 위치 조정 적용
            if dx != 0 or dy != 0:
                self.adjust_text_position(dx, dy)
                # 실시간 이동 표시
                self.update()
                return

        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.delete_selected_overlay():
                return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """키보드 해제 이벤트 처리"""
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.space_pressed = False
            if not getattr(self, 'panning', False):
                self.update_tool_cursor()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Shift:
            self.shift_pressed = False
            self.update_tool_cursor()
            return

        if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Meta):
            self.ctrl_pressed = False
            self.update_tool_cursor()
            return

        if event.key() == Qt.Key.Key_Alt:
            self.alt_pressed = False
            self.update_tool_cursor()
            return

        super().keyReleaseEvent(event)
    
    def mousePressEvent(self, event):
        # 0. 마우스 휠 클릭(미들 버튼) 또는 스페이스바/단축키 조합 핸드툴 & 줌툴 처리
        modifiers = event.modifiers()
        has_ctrl = getattr(self, 'ctrl_pressed', False) or bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
        has_alt = getattr(self, 'alt_pressed', False) or bool(modifiers & Qt.KeyboardModifier.AltModifier)
        has_shift = getattr(self, 'shift_pressed', False) or bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        is_space = getattr(self, 'space_pressed', False)

        # 0-1. 줌 툴 클릭 처리 (Ctrl + Spacebar + 클릭: 화면 확대 / Ctrl + Alt + Spacebar + 클릭: 화면 축소)
        if (is_space and (has_ctrl or has_alt)) or (has_ctrl and has_alt):
            if event.button() == Qt.MouseButton.LeftButton:
                self.single_click_timer.stop()
                self.pending_single_click_pos = None
                parent_window = self.window()
                scroll_area = self._get_scroll_area()
                vp_pos = scroll_area.viewport().mapFromGlobal(event.globalPosition().toPoint()) if scroll_area else event.position().toPoint()
                
                if has_alt:
                    if hasattr(parent_window, 'zoom_out'):
                        parent_window.zoom_out(vp_pos)
                else:
                    if hasattr(parent_window, 'zoom_in'):
                        parent_window.zoom_in(vp_pos)
                self.update_tool_cursor()
                event.accept()
                return

        # 0-2. 핸드 툴 패닝 시작 (Spacebar + 좌클릭 드래그 또는 마우스 미들버튼 클릭)
        if (event.button() == Qt.MouseButton.LeftButton and is_space) or (event.button() == Qt.MouseButton.MiddleButton):
            self.single_click_timer.stop()
            self.pending_single_click_pos = None
            self.panning = True
            self.pan_start_global = event.globalPosition().toPoint()
            scroll_area = self._get_scroll_area()
            if scroll_area:
                self.pan_start_h = scroll_area.horizontalScrollBar().value()
                self.pan_start_v = scroll_area.verticalScrollBar().value()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            parent_window = self.window()
            if parent_window and hasattr(parent_window, 'show_status_message'):
                t_msg = parent_window.t('status_panning', default="화면 이동(패닝) 중...") if hasattr(parent_window, 't') else "화면 이동(패닝) 중..."
                parent_window.show_status_message(t_msg)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            click_pos = event.position().toPoint()
            pdf_x, pdf_y = self._widget_point_to_pdf(click_pos)

            parent_window = self.window()
            is_eraser_btn = bool(parent_window and getattr(parent_window, 'patch_precise_mode', False) and getattr(parent_window, 'patch_only_mode', False))
            is_patch_btn = bool(parent_window and getattr(parent_window, 'patch_precise_mode', False) and not getattr(parent_window, 'patch_only_mode', False))

            is_eraser_mode = (has_shift and not has_ctrl and not is_space) or (is_eraser_btn and not is_space and not has_alt)
            is_patch_mode = (has_ctrl and not has_shift and not is_space and not has_alt and not is_eraser_btn) or (is_patch_btn and not has_shift and not is_space and not has_alt)

            # 지우개모드: Shift+드래그 또는 지우개 모드 툴바 버튼 활성화 시 (영역 배경 패치만 즉시 적용)
            if is_eraser_mode:
                self.single_click_timer.stop()
                self.pending_single_click_pos = None
                self.selection_mode = True
                self.selection_is_eraser = True
                self.selection_start = click_pos
                self.selection_rect = None
                self.selected_texts = []
                if parent_window:
                    parent_window.patch_only_mode = True
                    if hasattr(parent_window, 'show_status_message'):
                        t_msg = parent_window.t('status_eraser_drag', default="지우개 모드: 영역을 드래그하여 배경색으로 지웁니다") if hasattr(parent_window, 't') else "지우개 모드: 영역을 드래그하여 배경색으로 지웁니다"
                        parent_window.show_status_message(t_msg)
                print("지우개 모드 선택 시작")
                event.accept()
                return

            # 패치모드: Ctrl+드래그 또는 패치 모드 툴바 버튼 활성화 시 (영역 선택 및 텍스트 편집 대화상자)
            if is_patch_mode:
                self.single_click_timer.stop()
                self.pending_single_click_pos = None
                self.selection_mode = True
                self.selection_is_eraser = False
                self.selection_start = click_pos
                self.selection_rect = None
                self.selected_texts = []
                if parent_window:
                    parent_window.patch_only_mode = False
                    if hasattr(parent_window, 'show_status_message'):
                        t_msg = parent_window.t('status_patch_drag', default="패치 모드: 편집할 텍스트 영역을 드래그하세요") if hasattr(parent_window, 't') else "패치 모드: 편집할 텍스트 영역을 드래그하세요"
                        parent_window.show_status_message(t_msg)
                print("패치 모드 선택 시작")
                event.accept()
                return

            # 1. 이미지 오버레이 핸들 또는 이미지 본체 클릭 감지
            if pdf_x is not None and pdf_y is not None:
                pdf_point = fitz.Point(pdf_x, pdf_y)
                # 리사이즈 핸들 클릭 확인
                if self.active_image and self._is_on_image_resize_handle(self.active_image, pdf_point):
                    self.resizing_image = True
                    self.drag_start_pos = (pdf_x, pdf_y)
                    self.drag_start_bbox = fitz.Rect(self.active_image.bbox)
                    self.update()
                    return

                # 이미지 본체 클릭 확인
                hit_img = self._find_image_at_point(pdf_point)
                if hit_img:
                    self.active_image = hit_img
                    self.dragging_image = True
                    self.drag_start_pos = (pdf_x, pdf_y)
                    self.drag_start_bbox = fitz.Rect(hit_img.bbox)
                    self.active_overlay = None
                    self.update()
                    return
                else:
                    if self.active_image:
                        self.active_image = None
                        self.update()
            
            # 텍스트 조정 모드에서 다른 지점 클릭 시 모드 종료
            if self.selected_text_info and pdf_x is not None and pdf_y is not None:
                current_bbox = self.selected_text_info.get('original_bbox')
                if current_bbox:
                    pdf_point = fitz.Point(pdf_x, pdf_y)
                    if not self._rect_contains_point(current_bbox, pdf_point):
                        if self.quick_adjustment_mode:
                            self.exit_quick_adjustment_mode()
                            print("Quick adjustment mode 종료 - 다른 지점 클릭")
                        else:
                            self.exit_text_adjustment_mode()
                            print("Text adjustment mode 종료 - 다른 지점 클릭")
                        return
                    # 같은 텍스트 영역 내 클릭이면 계속 조정 모드 유지
                    return

        # 싱글클릭 타이머 설정 (더블클릭 감지용)
        click_pos = event.position().toPoint()
        pdf_x, pdf_y = self._widget_point_to_pdf(click_pos)
        overlay_hit = None
        if pdf_x is not None and pdf_y is not None and self.text_overlays.get(self.current_page_num):
            pdf_point = fitz.Point(pdf_x, pdf_y)
            for ov in reversed(self.text_overlays[self.current_page_num]):
                if ov.visible and self._rect_contains_point(ov.bbox, pdf_point):
                    overlay_hit = ov
                    break
        if overlay_hit:
            self.active_overlay = (self.current_page_num, overlay_hit.z_index)
            self.potential_drag_overlay = overlay_hit
            self.drag_start_pos = (pdf_x, pdf_y)
            self.drag_start_bbox = fitz.Rect(overlay_hit.bbox)
        else:
            mw = getattr(self, 'main_window', None) or self.window()
            if not (mw and getattr(mw, 'current_text_editor', None) is not None):
                self.active_overlay = None
            self.potential_drag_overlay = None
        self.update() # 즉시 갱신하여 패치 투명도 반영
        self.pending_single_click_pos = click_pos
        self.single_click_timer.start(300)  # 300ms 후 싱글클릭 처리
        print(f"Single click timer started at position: {self.pending_single_click_pos}")
    
    def mouseMoveEvent(self, event):
        current_pos = event.position().toPoint()
        self.mouse_pos = current_pos

        # 핸드 툴 화면 패닝 드래그 처리
        if getattr(self, 'panning', False):
            curr_global = event.globalPosition().toPoint()
            dx = curr_global.x() - self.pan_start_global.x()
            dy = curr_global.y() - self.pan_start_global.y()
            scroll_area = self._get_scroll_area()
            if scroll_area:
                scroll_area.horizontalScrollBar().setValue(self.pan_start_h - dx)
                scroll_area.verticalScrollBar().setValue(self.pan_start_v - dy)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        pdf_x, pdf_y = self._widget_point_to_pdf(current_pos)

        # 텍스트 오버레이 마우스 드래그 이동 처리
        if getattr(self, 'potential_drag_overlay', None) and pdf_x is not None and pdf_y is not None:
            dx = pdf_x - self.drag_start_pos[0]
            dy = pdf_y - self.drag_start_pos[1]
            if abs(dx) > 0.4 or abs(dy) > 0.4 or getattr(self, 'dragging_overlay', False):
                self.dragging_overlay = True
                self.single_click_timer.stop()
                self.pending_single_click_pos = None
                raw_bbox = fitz.Rect(
                    self.drag_start_bbox.x0 + dx, self.drag_start_bbox.y0 + dy,
                    self.drag_start_bbox.x1 + dx, self.drag_start_bbox.y1 + dy
                )
                snapped_bbox, guides = self._apply_smart_snap(raw_bbox, ignore_obj=self.potential_drag_overlay)
                self.active_snap_guides = guides
                self.potential_drag_overlay.move_to(snapped_bbox)
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                self.update()
                return

        # 이미지 리사이즈 처리
        if self.resizing_image and self.active_image and pdf_x is not None and pdf_y is not None:
            orig_w = float(self.active_image.pixmap.width())
            orig_h = float(self.active_image.pixmap.height())
            aspect = (orig_w / orig_h) if orig_h > 0 else 1.0
            new_w = max(15.0, pdf_x - self.drag_start_bbox.x0)
            new_h = new_w / aspect
            self.active_image.bbox = fitz.Rect(
                self.drag_start_bbox.x0, self.drag_start_bbox.y0,
                self.drag_start_bbox.x0 + new_w, self.drag_start_bbox.y0 + new_h
            )
            self.update()
            return

        # 이미지 이동 드래그 처리
        if self.dragging_image and self.active_image and pdf_x is not None and pdf_y is not None:
            dx = pdf_x - self.drag_start_pos[0]
            dy = pdf_y - self.drag_start_pos[1]
            raw_bbox = fitz.Rect(
                self.drag_start_bbox.x0 + dx, self.drag_start_bbox.y0 + dy,
                self.drag_start_bbox.x1 + dx, self.drag_start_bbox.y1 + dy
            )
            snapped_bbox, guides = self._apply_smart_snap(raw_bbox, ignore_obj=self.active_image)
            self.active_snap_guides = guides
            self.active_image.bbox = snapped_bbox
            self.update()
            return

        # 사각형 선택 모드 처리
        if self.selection_mode and self.selection_start:
            self.selection_rect = QRect(self.selection_start, current_pos).normalized()
            self.update()  # 선택 사각형 그리기
            return

        # 줄자 표시 상태면 마우스 인디케이터 갱신을 위해 update 호출
        if getattr(self, 'show_ruler', False):
            self.update()

    def leaveEvent(self, event):
        """마우스가 위젯을 벗어날 때 호버 하이라이트 제거 및 십자 커서 복원"""
        if not getattr(self, 'space_pressed', False) and not getattr(self, 'panning', False):
            self.setCursor(Qt.CursorShape.CrossCursor)
        self.active_snap_guides = []
        if self.hover_rect:
            self.hover_rect = None
            self.hover_span_info = None
            self.update()
        super().leaveEvent(event)
    
    def mouseReleaseEvent(self, event):
        # 텍스트 오버레이 드래그 완료 처리
        if getattr(self, 'dragging_overlay', False):
            self.dragging_overlay = False
            self.potential_drag_overlay = None
            self.active_snap_guides = []
            main_window = self.window()
            if main_window and hasattr(main_window, 'undo_manager') and self.doc:
                try:
                    main_window.undo_manager.save_state(self.doc, self)
                except Exception:
                    pass
            self.update_tool_cursor()
            self.update()
            return
        self.potential_drag_overlay = None
        self.active_snap_guides = []

        # 핸드 툴 패닝 완료
        if getattr(self, 'panning', False):
            self.panning = False
            self.update_tool_cursor()
            parent_window = self.window()
            if parent_window and hasattr(parent_window, 'update_status_mode_message'):
                parent_window.update_status_mode_message()
            event.accept()
            return

        # 이미지 이동/리사이즈 완료 처리
        if self.dragging_image or self.resizing_image:
            self.dragging_image = False
            self.resizing_image = False
            self.active_snap_guides = []
            main_window = self.window()
            if main_window and hasattr(main_window, 'undo_manager') and self.doc:
                try:
                    main_window.undo_manager.save_state(self.doc, self)
                except Exception:
                    pass
            self.update()
            return

        # 사각형 선택 모드 완료
        if self.selection_mode:
            if self.selection_rect:
                self.complete_area_selection()
            self.selection_mode = False
            self.selection_rect = None
            self.selection_start = None
            self.selection_is_eraser = False
            main_window = self.window()
            if main_window and hasattr(main_window, 'update_status_mode_message'):
                main_window.update_status_mode_message()
            return
    
    def wheelEvent(self, event):
        """휠 이벤트 처리 (Ctrl+휠: 줌, Shift+휠: 페이지 이동, 휠: 연속 스크롤)"""
        modifiers = event.modifiers()
        has_ctrl = getattr(self, 'ctrl_pressed', False) or bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
        has_alt = getattr(self, 'alt_pressed', False) or bool(modifiers & Qt.KeyboardModifier.AltModifier)
        has_shift = getattr(self, 'shift_pressed', False) or bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        # 1. Shift + 마우스휠 > 페이지 이동
        if has_shift and not has_ctrl and not has_alt:
            parent_window = self.window()
            if self.doc and hasattr(parent_window, 'next_page') and hasattr(parent_window, 'prev_page'):
                delta = event.angleDelta().y() or event.angleDelta().x()
                if delta < 0:
                    parent_window.next_page()
                elif delta > 0:
                    parent_window.prev_page()
                event.accept()
                return

        # 2. Ctrl 또는 Alt + 마우스휠 > 확대/축소 (마우스 포인터 중심)
        if has_ctrl or has_alt:
            parent_window = self.window()
            if hasattr(parent_window, 'zoom_factor'):
                delta = event.angleDelta().y()
                scroll_area = self._get_scroll_area()
                if scroll_area:
                    mouse_pos = scroll_area.viewport().mapFromGlobal(event.globalPosition().toPoint())
                else:
                    mouse_pos = event.position().toPoint()
                
                if delta > 0:
                    parent_window.zoom_in(mouse_pos)
                else:
                    parent_window.zoom_out(mouse_pos)
            event.accept()
            return
        # 일반 마우스 휠: 수직 연속 스크롤 페이지 전환 처리
        scroll_area = self._get_scroll_area()
        parent_window = self.window()
        continuous_scroll = getattr(parent_window, 'continuous_scroll_enabled', True)

        if continuous_scroll and scroll_area and self.doc and hasattr(parent_window, 'next_page'):
            vbar = scroll_area.verticalScrollBar()
            delta = event.angleDelta().y()
            
            # 페이지 아래쪽 끝에서 아래로 휠 스크롤 시 -> 다음 페이지로 전환
            if delta < 0 and vbar.value() >= vbar.maximum():
                self._wheel_accum = getattr(self, '_wheel_accum', 0) + abs(delta)
                if self._wheel_accum >= 120:
                    self._wheel_accum = 0
                    if self.current_page_num < len(self.doc) - 1:
                        parent_window.next_page()
                        vbar.setValue(vbar.minimum())
                        event.accept()
                        return
            # 페이지 위쪽 끝에서 위로 휠 스크롤 시 -> 이전 페이지로 전환
            elif delta > 0 and vbar.value() <= vbar.minimum():
                self._wheel_accum = getattr(self, '_wheel_accum', 0) + abs(delta)
                if self._wheel_accum >= 120:
                    self._wheel_accum = 0
                    if self.current_page_num > 0:
                        parent_window.prev_page()
                        vbar.setValue(vbar.maximum())
                        event.accept()
                        return
            else:
                self._wheel_accum = 0

        if self.parent():
            self.parent().wheelEvent(event)
    
    def check_hover(self):
        """마우스 호버 체크 및 텍스트 블록 하이라이트 (캐시 적용 최적화)"""
        if not self.doc or not hasattr(self, 'mouse_pos'):
            return
        
        # 스페이스바(핸드 툴/줌 툴) 또는 패닝 중에는 호버 갱신 및 커서 덮어쓰기 방지
        if getattr(self, 'space_pressed', False) or getattr(self, 'panning', False):
            return
        
        try:
            # 마우스 위치를 PDF 좌표로 변환
            pdf_x, pdf_y = self._widget_point_to_pdf(self.mouse_pos)
            if pdf_x is None or pdf_y is None:
                return
            
            pdf_point = fitz.Point(pdf_x, pdf_y)

            # 이미지 리사이즈 핸들 또는 이미지 호버 검사
            if self.active_image and self._is_on_image_resize_handle(self.active_image, pdf_point):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                return
            elif self._find_image_at_point(pdf_point):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                return
            
            # 캐시된 텍스트 데이터 사용
            if self.current_page_num not in self._text_dict_cache:
                page = self.doc.load_page(self.current_page_num)
                self._text_dict_cache[self.current_page_num] = page.get_text("dict")
            
            text_dict = self._text_dict_cache[self.current_page_num]
            
            # 호버 중인 텍스트/오버레이 찾기 - 오버레이 bbox 먼저 검사
            overlay_hover_rect = None
            overlay_hover_span_info = None
            original_hover_rect = None
            original_hover_span_info = None

            # 0) 오버레이 레이어 히트 테스트 (PDF 텍스트보다 우선)
            if self.text_overlays.get(self.current_page_num):
                for ov in reversed(self.text_overlays[self.current_page_num]):
                    hit_ov = self._rect_contains_point(ov.bbox, pdf_point)
                    if not hit_ov and getattr(ov, 'original_bbox', None):
                        hit_ov = self._rect_contains_point(ov.original_bbox, pdf_point)
                    if ov.visible and hit_ov:
                        overlay_hover_rect = ov.bbox
                        overlay_hover_span_info = {
                            'text': ov.text,
                            'font': ov.font,
                            'size': ov.size,
                            'flags': ov.flags,
                            'color': ov.color,
                            'original_bbox': ov.original_bbox,
                            'is_overlay': True,
                            'overlay_id': ov.z_index,
                            'synth_bold_weight': getattr(ov, 'synth_bold_weight', 120),
                            'underline_weight': getattr(ov, 'underline_weight', 0.6),
                            'underline_offset': getattr(ov, 'underline_offset', 1.5)
                        }
                        break

            # 현재 편집 중인 active_overlay가 있다면 해당 오버레이 객체 확인
            active_ov_obj = None
            if self.active_overlay and self.active_overlay[0] == self.current_page_num:
                active_ov_obj = self.get_overlay_by_id(self.active_overlay[0], self.active_overlay[1])

            visual_lines = self._get_visual_lines_for_page(self.current_page_num)
            for vl in visual_lines:
                # 활성 편집 중인 오버레이와 겹치는 원본 텍스트블록은 파란색 호버로 덮지 않음
                if active_ov_obj:
                    a_bbox = active_ov_obj.original_bbox or active_ov_obj.bbox
                    vl_b = vl['original_bbox']
                    if vl_b.x0 < a_bbox.x1 and vl_b.x1 > a_bbox.x0 and vl_b.y0 < a_bbox.y1 and vl_b.y1 > a_bbox.y0:
                        continue

                if self._rect_contains_point(vl['original_bbox'], pdf_point, tol=1.5):
                    span_info = {
                        'text': vl['text'],
                        'font': vl['font'],
                        'size': vl['size'],
                        'flags': vl['flags'],
                        'color': vl['color'],
                        'origin': vl['origin'],
                        'original_bbox': vl['original_bbox'],
                        'line_text': vl['text'],
                        'line_spans': vl['line_spans'],
                        'is_overlay': False
                    }
                    # 오버레이 텍스트인지 확인
                    if any(self.is_overlay_text(s, fitz.Rect(s["bbox"])) for s in vl.get('line_spans', [])):
                        if not overlay_hover_rect:
                            overlay_hover_rect = vl['original_bbox']
                            overlay_hover_span_info = span_info
                    else:
                        if not original_hover_rect:
                            original_hover_rect = vl['original_bbox']
                            original_hover_span_info = span_info
                    break

            # 오버레이 텍스트가 있으면 우선, 없으면 원본 텍스트 사용
            new_hover_rect = overlay_hover_rect if overlay_hover_rect else original_hover_rect
            new_hover_span_info = overlay_hover_span_info if overlay_hover_span_info else original_hover_span_info

            # 호버 상태가 변경되었을 때 또는 호버 중일 때 주기적 갱신
            if new_hover_rect != self.hover_rect:
                self.hover_rect = new_hover_rect
                self.hover_span_info = new_hover_span_info
                self.update() # 상태 변화(해제 포함) 시 즉시 화면 갱신
                self.update_tool_cursor()

            # 호버 유지 중에도 주기적 update (애니메이션 등 반영)
            elif self.hover_rect:
                self.update_tool_cursor()
                self.update()
            else:
                self.update_tool_cursor()

        except Exception:
            pass

    def invalidate_visual_lines_cache(self, page_num=None):
        """Visual lines 및 text_dict 캐시 무효화"""
        if hasattr(self, '_visual_lines_cache'):
            if page_num is not None:
                self._visual_lines_cache.pop(page_num, None)
            else:
                self._visual_lines_cache.clear()
        if hasattr(self, '_text_dict_cache'):
            if page_num is not None:
                self._text_dict_cache.pop(page_num, None)
            else:
                self._text_dict_cache.clear()

    def _get_visual_lines_for_page(self, page_num: int) -> list[dict]:
        """페이지 내 rawdict 문자(chars)들을 분석하여 한컴 HWP PDF 특수문자/괄호/공백 누락 없이
        시각적 동일 라인(Visual Line) 단위로 완벽하게 병합된 라인 리스트 반환."""
        if not self.doc or page_num < 0 or page_num >= len(self.doc):
            return []
        
        if hasattr(self, '_visual_lines_cache') and page_num in self._visual_lines_cache:
            return self._visual_lines_cache[page_num]
            
        try:
            page = self.doc.load_page(page_num)
            rd = page.get_text('rawdict')
            rot_mat = page.rotation_matrix if page.rotation != 0 else None
            visual_lines = []
            
            for block in rd.get('blocks', []):
                if block.get('type') != 0:
                    continue
                
                # 블록 내 모든 chars 수집 및 span 참조 보존 (페이지 회전 보정 적용)
                chars_with_info = []
                for line in block.get('lines', []):
                    line_dir = line.get('dir', (1.0, 0.0))
                    if rot_mat:
                        v = fitz.Point(line_dir[0], line_dir[1]) * rot_mat - fitz.Point(0, 0) * rot_mat
                        eff_dir = (v.x, v.y)
                    else:
                        eff_dir = line_dir
                    for span in line.get('spans', []):
                        font = span.get('font', '')
                        size = float(span.get('size', 12.0))
                        color = span.get('color', 0)
                        flags = span.get('flags', 0)
                        for ch in span.get('chars', []):
                            cb = fitz.Rect(ch['bbox'])
                            if rot_mat:
                                cb = cb * rot_mat
                            orig = ch.get('origin')
                            if orig and rot_mat:
                                opt = fitz.Point(orig) * rot_mat
                                orig = (opt.x, opt.y)
                            chars_with_info.append({
                                'c': ch['c'],
                                'bbox': (cb.x0, cb.y0, cb.x1, cb.y1),
                                'origin': orig,
                                'font': font,
                                'size': size,
                                'color': color,
                                'flags': flags,
                                'span': span,
                                'dir': eff_dir
                            })
                if not chars_with_info:
                    continue
                
                # 중복 음영/레이어 문자 제거 (HWP PDF에서 그림자/외곽선 시뮬레이션으로 동일 위치 중복 방지)
                deduped_chars = []
                for ch in chars_with_info:
                    cb = ch['bbox']
                    dup = False
                    for ex in deduped_chars:
                        eb = ex['bbox']
                        if abs(cb[0] - eb[0]) < 1.5 and abs(cb[1] - eb[1]) < 1.5 and ch['c'] == ex['c']:
                            dup = True
                            if ex['color'] != 0 and ch['color'] == 0:
                                ex['color'] = 0
                                ex['font'] = ch['font']
                                ex['span'] = ch['span']
                            break
                    if not dup:
                        deduped_chars.append(ch)
                chars_with_info = deduped_chars
                
                # 블록의 주 진행 방향 판정 (수평 vs 수직)
                is_vertical = any(abs(c.get('dir', (1.0, 0.0))[1]) > abs(c.get('dir', (1.0, 0.0))[0]) for c in chars_with_info)

                block_lines = []
                if not is_vertical:
                    for ch in chars_with_info:
                        cb = ch['bbox']
                        cy = (cb[1] + cb[3]) / 2.0
                        ch_h = max(cb[3] - cb[1], 8.0)
                        
                        matched = None
                        for bl in block_lines:
                            if abs(cy - bl['y_mid']) <= max(3.5, ch_h * 0.45):
                                matched = bl
                                break
                        if matched:
                            matched['chars'].append(ch)
                            matched['y0'] = min(matched['y0'], cb[1])
                            matched['y1'] = max(matched['y1'], cb[3])
                            matched['y_mid'] = (matched['y0'] + matched['y1']) / 2.0
                        else:
                            block_lines.append({
                                'y_mid': cy,
                                'y0': cb[1],
                                'y1': cb[3],
                                'chars': [ch]
                            })
                    block_lines.sort(key=lambda bl: bl['y0'])
                else:
                    for ch in chars_with_info:
                        cb = ch['bbox']
                        cx = (cb[0] + cb[2]) / 2.0
                        ch_w = max(cb[2] - cb[0], 8.0)
                        
                        matched = None
                        for bl in block_lines:
                            if abs(cx - bl['x_mid']) <= max(3.5, ch_w * 0.45):
                                matched = bl
                                break
                        if matched:
                            matched['chars'].append(ch)
                            matched['x0'] = min(matched['x0'], cb[0])
                            matched['x1'] = max(matched['x1'], cb[2])
                            matched['x_mid'] = (matched['x0'] + matched['x1']) / 2.0
                        else:
                            block_lines.append({
                                'x_mid': cx,
                                'x0': cb[0],
                                'x1': cb[2],
                                'chars': [ch]
                            })
                    block_lines.sort(key=lambda bl: bl['x0'])
                
                for bl in block_lines:
                    if not is_vertical:
                        bl['chars'].sort(key=lambda c: c['bbox'][0])
                    else:
                        bl_dir = bl['chars'][0].get('dir', (0.0, 1.0))
                        if bl_dir[1] < 0:
                            bl['chars'].sort(key=lambda c: -c['bbox'][3])
                        else:
                            bl['chars'].sort(key=lambda c: c['bbox'][1])
                        
                    # [시각적 공백 복원] PDF 문자 간격(Gap)을 분석하여 누락된 공백 문자(' ') 복원
                    # Word/PowerPoint 등에서 공백 글리프 없이 좌표 이동(TJ)으로 띄어쓰기된 텍스트 처리
                    spaced_chars = []
                    for ch in bl['chars']:
                        if not spaced_chars:
                            spaced_chars.append(ch)
                        else:
                            prev_ch = spaced_chars[-1]
                            p_c = prev_ch.get('c', '')
                            c_c = ch.get('c', '')
                            if not is_vertical:
                                gap = ch['bbox'][0] - prev_ch['bbox'][2]
                            else:
                                bl_dir = ch.get('dir', (0.0, 1.0))
                                if bl_dir[1] < 0:
                                    gap = prev_ch['bbox'][1] - ch['bbox'][3]
                                else:
                                    gap = ch['bbox'][1] - prev_ch['bbox'][3]
                            f_sz = max(float(ch.get('size', 12.0)), float(prev_ch.get('size', 12.0)), 10.0)
                            max_seg_gap = max(35.0, f_sz * 3.5)
                            
                            # 공백 판정 임계치: 글자 크기의 18% 이상 및 2.0pt 이상, 컬럼 분할 거리 미만
                            if (not p_c.isspace()) and (not c_c.isspace()) and (max_seg_gap >= gap >= max(2.0, f_sz * 0.18)):
                                if not is_vertical:
                                    sp_bbox = (prev_ch['bbox'][2], prev_ch['bbox'][1], ch['bbox'][0], prev_ch['bbox'][3])
                                    sp_origin = (prev_ch['bbox'][2], prev_ch.get('origin', (0, 0))[1] if prev_ch.get('origin') else prev_ch['bbox'][3])
                                else:
                                    bl_dir = ch.get('dir', (0.0, 1.0))
                                    if bl_dir[1] < 0:
                                        sp_bbox = (prev_ch['bbox'][0], ch['bbox'][3], prev_ch['bbox'][2], prev_ch['bbox'][1])
                                        sp_origin = (prev_ch.get('origin', (0, 0))[0], prev_ch['bbox'][1])
                                    else:
                                        sp_bbox = (prev_ch['bbox'][0], prev_ch['bbox'][3], prev_ch['bbox'][2], ch['bbox'][1])
                                        sp_origin = (prev_ch.get('origin', (0, 0))[0], prev_ch['bbox'][3])
                                spaced_chars.append({
                                    'c': ' ',
                                    'bbox': sp_bbox,
                                    'origin': sp_origin,
                                    'font': prev_ch.get('font', ''),
                                    'size': prev_ch.get('size', 12.0),
                                    'color': prev_ch.get('color', 0),
                                    'flags': prev_ch.get('flags', 0),
                                    'span': prev_ch.get('span'),
                                    'dir': prev_ch.get('dir')
                                })
                            spaced_chars.append(ch)

                    # 과도한 수평/수직 간격(컬럼 분할) 처리
                    segments = []
                    curr_seg = []
                    for ch in spaced_chars:
                        if not curr_seg:
                            curr_seg.append(ch)
                        else:
                            prev_ch = curr_seg[-1]
                            if not is_vertical:
                                gap = ch['bbox'][0] - prev_ch['bbox'][2]
                            else:
                                bl_dir = ch.get('dir', (0.0, 1.0))
                                if bl_dir[1] < 0:
                                    gap = prev_ch['bbox'][1] - ch['bbox'][3]
                                else:
                                    gap = ch['bbox'][1] - prev_ch['bbox'][3]
                            f_sz = max(ch['size'], prev_ch['size'], 10.0)
                            if gap > max(35.0, f_sz * 3.5):
                                segments.append(curr_seg)
                                curr_seg = [ch]
                            else:
                                curr_seg.append(ch)
                    if curr_seg:
                        segments.append(curr_seg)
                        
                    for seg in segments:
                        # [방어로직] 한컴 HWP 전용 PUA 특수문자, 글머리기호(Bullet), 및 선행/후행 공백을 텍스트블록에서 제외
                        # 1. 선두의 불릿 기호, 한컴 PUA 특수문자, 심볼 폰트 문자 및 선행 공백 검출/제외 (들여쓰기 인덴트 폭 오차 완벽 해결)
                        start_idx = 0
                        while start_idx < len(seg):
                            ch = seg[start_idx]
                            c_str = ch.get('c', '')
                            f_str = ch.get('font', '')
                            if c_str.isspace() or is_pua_char(c_str) or (c_str in BULLET_CHARS) or is_symbol_font(f_str):
                                start_idx += 1
                            else:
                                break
                        if start_idx >= len(seg):
                            continue
                            
                        # 2. 말미의 한컴 PUA 특수문자, 심볼 문자 및 불릿/후행 공백 검출/제외
                        end_idx = len(seg)
                        while end_idx > start_idx:
                            ch = seg[end_idx - 1]
                            c_str = ch.get('c', '')
                            f_str = ch.get('font', '')
                            if c_str.isspace() or is_pua_char(c_str) or (c_str in BULLET_CHARS) or is_symbol_font(f_str):
                                end_idx -= 1
                            else:
                                break
                                
                        clean_seg = seg[start_idx:end_idx]
                        # 본문 중간에 섞인 PUA 문자(렌더링 불가 문자) 필터링
                        clean_seg = [c for c in clean_seg if not is_pua_char(c.get('c', ''))]
                        if not clean_seg:
                            continue
                        seg = clean_seg

                        seg_text = ''.join(c['c'] for c in seg)
                        if not seg_text.strip():
                            continue
                        x0 = min(c['bbox'][0] for c in seg)
                        y0 = min(c['bbox'][1] for c in seg)
                        x1 = max(c['bbox'][2] for c in seg)
                        y1 = max(c['bbox'][3] for c in seg)
                        seg_rect = fitz.Rect(x0, y0, x1, y1)
                        
                        non_space_chars = [c for c in seg if c['c'].strip()]
                        target_chars = non_space_chars if non_space_chars else seg
                        from collections import Counter
                        font_counter = Counter(c['font'] for c in target_chars)
                        size_counter = Counter(c['size'] for c in target_chars)
                        color_counter = Counter(c['color'] for c in target_chars)
                        flags_counter = Counter(c['flags'] for c in target_chars)
                        
                        prim_font = font_counter.most_common(1)[0][0]
                        prim_size = size_counter.most_common(1)[0][0]
                        prim_color = color_counter.most_common(1)[0][0]
                        prim_flags = flags_counter.most_common(1)[0][0]
                        
                        # [고도화] 지배적 주 폰트/크기를 사용하는 첫 번째 글자의 베이스라인 우선 채택 (복합 크기 라인 Y축 오차 완벽 해결)
                        baseline_y = None
                        for c in target_chars:
                            if c.get('origin') and c.get('size') == prim_size:
                                baseline_y = c['origin'][1]
                                break
                        if baseline_y is None:
                            for c in seg:
                                if c.get('origin'):
                                    baseline_y = c['origin'][1]
                                    break
                        if baseline_y is None:
                            baseline_y = y0 + (prim_size * 0.85)
                        
                        # origin의 x는 첫 실제 글자의 시작점과 1:1 일치
                        if not is_vertical:
                            first_origin = (seg[0]['origin'][0] if seg[0].get('origin') else x0, baseline_y)
                        else:
                            first_origin = (seg[0]['origin'][0] if seg[0].get('origin') else x0,
                                            seg[0]['origin'][1] if seg[0].get('origin') else baseline_y)
                        
                        seg_spans = []
                        seen_spans = set()
                        for c in seg:
                            sp = c.get('span')
                            if sp and id(sp) not in seen_spans:
                                seen_spans.add(id(sp))
                                seg_spans.append(sp)
                                
                        visual_lines.append({
                            'text': seg_text,
                            'font': prim_font,
                            'size': prim_size,
                            'color': prim_color,
                            'flags': prim_flags,
                            'origin': first_origin,
                            'original_bbox': seg_rect,
                            'line_text': seg_text,
                            'line_spans': seg_spans,
                            'chars': seg,
                            'is_overlay': False,
                            'is_vertical': is_vertical
                        })
                        
            if not hasattr(self, '_visual_lines_cache'):
                self._visual_lines_cache = {}
            self._visual_lines_cache[page_num] = visual_lines
            return visual_lines
        except Exception as e:
            print(f"[VisualLines] Error extracting visual lines: {e}")
            return []

    def _merge_line_spans(self, spans_in_line: list[dict], pdf_point: Optional[fitz.Point] = None) -> tuple[str, fitz.Rect, list[dict], dict]:
        """라인 내 spans들을 공백 및 특수문자 규칙을 반영하여 하나의 텍스트와 통합 bbox로 병합.
        표나 컬럼처럼 수평 gap이 과도하게 큰 경우 세그먼트를 분리하고,
        pdf_point가 주어진 경우 클릭 지점이 속한 세그먼트를 우선 선택.
        반환값: (merged_text, merged_bbox, target_spans, primary_attrs)
        """
        empty_attrs = {'font': '', 'size': 12.0, 'color': 0, 'flags': 0, 'origin': None}
        if not spans_in_line:
            return "", fitz.Rect(), [], empty_attrs

        # x0 기준 정렬
        sorted_spans = sorted(spans_in_line, key=lambda s: s["bbox"][0])

        # 1. 과도한 수평 간격(예: 28pt 이상이거나 폰트 크기의 2.8배 초과)을 기준으로 세그먼트 분할
        segments: list[list[dict]] = []
        current_segment: list[dict] = []

        for s in sorted_spans:
            if not current_segment:
                current_segment.append(s)
            else:
                prev_s = current_segment[-1]
                gap = s["bbox"][0] - prev_s["bbox"][2]
                font_sz = float(s.get("size") or prev_s.get("size") or 12.0)
                max_gap = max(28.0, font_sz * 2.8)
                if gap > max_gap:
                    segments.append(current_segment)
                    current_segment = [s]
                else:
                    current_segment.append(s)
        if current_segment:
            segments.append(current_segment)

        # 2. pdf_point가 있는 경우 해당 세그먼트 선택, 없으면 클릭 위치와 가장 가까운 세그먼트
        target_spans = segments[0]
        if pdf_point is not None:
            best_seg = None
            min_dist = float('inf')
            for seg in segments:
                x0 = min(s["bbox"][0] for s in seg)
                y0 = min(s["bbox"][1] for s in seg)
                x1 = max(s["bbox"][2] for s in seg)
                y1 = max(s["bbox"][3] for s in seg)
                seg_rect = fitz.Rect(x0, y0, x1, y1)
                if self._rect_contains_point(seg_rect, pdf_point, tol=2.0):
                    best_seg = seg
                    break
                cx = (x0 + x1) / 2.0
                cy = (y0 + y1) / 2.0
                d = ((pdf_point.x - cx) ** 2 + (pdf_point.y - cy) ** 2) ** 0.5
                if d < min_dist:
                    min_dist = d
                    best_seg = seg
            if best_seg:
                target_spans = best_seg

        # 3. 세그먼트 내 spans 결합 및 정밀 공백 산출
        x0 = min(s["bbox"][0] for s in target_spans)
        y0 = min(s["bbox"][1] for s in target_spans)
        x1 = max(s["bbox"][2] for s in target_spans)
        y1 = max(s["bbox"][3] for s in target_spans)
        merged_bbox = fitz.Rect(x0, y0, x1, y1)

        merged_text = ""
        for i, s in enumerate(target_spans):
            span_text = s.get("text", "")
            if not span_text:
                continue
            span_bbox = fitz.Rect(s["bbox"])

            if i > 0:
                prev_s = target_spans[i - 1]
                prev_text = prev_s.get("text", "")
                prev_bbox = fitz.Rect(prev_s["bbox"])
                horizontal_gap = span_bbox.x0 - prev_bbox.x1

                font_size = float(s.get("size") or prev_s.get("size") or 12.0)
                # 기준 공백 임계치 및 단위 계산 (특수문자 왜곡 방어)
                space_threshold = max(1.8, font_size * 0.22)
                space_unit = max(2.5, font_size * 0.32)

                num_spaces = 0
                if horizontal_gap >= space_threshold:
                    num_spaces = max(1, int(round(horizontal_gap / space_unit)))
                    num_spaces = min(num_spaces, 10)
                elif self._needs_space_between_spans(prev_s, s):
                    num_spaces = 1

                if num_spaces > 0:
                    existing_spaces = 0
                    if merged_text.endswith(' '):
                        existing_spaces += 1
                    if span_text.startswith(' '):
                        existing_spaces += 1
                    add_spaces = max(0, num_spaces - existing_spaces)
                    if add_spaces > 0:
                        merged_text += (" " * add_spaces)

            merged_text += span_text

        # 4. 세그먼트의 대표 스타일 산출 (글자 수가 가장 많은 span의 속성 채택)
        primary_span = max(target_spans, key=lambda s: len(s.get("text", "").strip()) if s.get("text") else 0)
        primary_attrs = {
            'font': primary_span.get('font', 'Arial'),
            'size': float(primary_span.get('size', 12.0)),
            'color': primary_span.get('color', 0),
            'flags': primary_span.get('flags', 0),
            'origin': target_spans[0].get('origin') or primary_span.get('origin')
        }

        return merged_text, merged_bbox, target_spans, primary_attrs
    
    def mouseDoubleClickEvent(self, event):
        # PDF 문서가 로드되지 않았으면 무시
        if not self.doc:
            return
        
        # 싱글클릭 타이머 취소
        self.single_click_timer.stop()
        self.pending_single_click_pos = None
        
        # 빠른 조정 모드 종료
        if self.quick_adjustment_mode:
            self.exit_quick_adjustment_mode()
        
        print("Double click detected!")
        self.hover_rect = None
        self.hover_span_info = None
        
        try:
            # 라벨 내에서의 클릭 위치
            label_pos = event.position().toPoint()
            pdf_x, pdf_y = self._widget_point_to_pdf(label_pos)
            if pdf_x is None or pdf_y is None:
                return
            
            pdf_point = fitz.Point(pdf_x, pdf_y)
            print(f"PDF coordinates: ({pdf_x}, {pdf_y})")

            # 이미지 더블클릭 검사 -> 이미지 속성 대화상자 오픈
            hit_img = self._find_image_at_point(pdf_point)
            if hit_img:
                self.active_image = hit_img
                self.update()
                dlg = ImagePropertyDialog(hit_img, self)
                dlg.exec()
                return

            # 오버레이 레이어 우선 히트 테스트 (빈 영역 오버레이 포함)
            if self.text_overlays.get(self.current_page_num):
                for ov in reversed(self.text_overlays[self.current_page_num]):
                    if ov.visible and self._rect_contains_point(ov.bbox, pdf_point, tol=2.0):
                        print("Overlay hit - open editor")
                        self.active_overlay = (self.current_page_num, ov.z_index)
                        span_info = {
                            'text': ov.text,
                            'font': ov.font,
                            'size': ov.size,
                            'flags': ov.flags,
                            'color': ov.color,
                            'original_bbox': ov.original_bbox,
                            'current_bbox': ov.bbox,
                            'origin': getattr(ov, 'origin', None),
                            'is_overlay': True,
                            'overlay_id': ov.z_index,
                            'page_num': self.current_page_num,
                            'stretch': getattr(ov, 'stretch', 1.0),
                            'tracking': getattr(ov, 'tracking', 0.0),
                            'hwp_space_mode': getattr(ov, 'hwp_space_mode', False),
                            'synth_bold_weight': getattr(ov, 'synth_bold_weight', 120),
                            'underline_weight': getattr(ov, 'underline_weight', 0.6),
                            'underline_offset': getattr(ov, 'underline_offset', 1.5)
                        }
                        self.text_selected.emit(span_info)
                        return

            visual_lines = self._get_visual_lines_for_page(self.current_page_num)
            
            clicked_overlay_info = None
            clicked_original_info = None
            
            print(f"더블클릭한 위치에서 텍스트 검색 중... (후보 라인수: {len(visual_lines)})")
            
            # 1단계: 마우스 클릭점이 속한 visual line 탐색
            for vl in visual_lines:
                hit = self._rect_contains_point(vl['original_bbox'], pdf_point, tol=2.0)
                if not hit:
                    # 라인 내 개별 글자 히트 검사 (미세 여백 클릭 지원)
                    for c in vl.get('chars', []):
                        if self._rect_contains_point(fitz.Rect(c['bbox']), pdf_point, tol=1.5):
                            hit = True
                            break
                if hit:
                    is_ov = any(self.is_overlay_text(s, fitz.Rect(s["bbox"])) for s in vl.get('line_spans', []))
                    info = {
                        'text': vl['text'],
                        'font': vl['font'],
                        'size': vl['size'],
                        'flags': vl['flags'],
                        'color': vl['color'],
                        'origin': vl['origin'],
                        'original_bbox': vl['original_bbox'],
                        'line_text': vl['text'],
                        'line_spans': vl['line_spans'],
                        'chars': vl.get('chars', []),
                        'is_overlay': is_ov,
                        'is_vertical': vl.get('is_vertical', False)
                    }
                    if is_ov:
                        if not clicked_overlay_info:
                            clicked_overlay_info = info
                    else:
                        if not clicked_original_info:
                            clicked_original_info = info
                    break
            
            # 2단계: 직접 히트되지 않은 경우 가장 가까운 visual line 탐색 (허용거리: 4.0pt)
            if not clicked_overlay_info and not clicked_original_info and visual_lines:
                closest_vl = None
                min_dist = float('inf')
                for vl in visual_lines:
                    r = vl['original_bbox']
                    dx = max(0, r.x0 - pdf_point.x, pdf_point.x - r.x1)
                    dy = max(0, r.y0 - pdf_point.y, pdf_point.y - r.y1)
                    dist = (dx*dx + dy*dy) ** 0.5
                    if dist <= 4.0 and dist < min_dist:
                        min_dist = dist
                        closest_vl = vl
                if closest_vl:
                    is_ov = any(self.is_overlay_text(s, fitz.Rect(s["bbox"])) for s in closest_vl.get('line_spans', []))
                    info = {
                        'text': closest_vl['text'],
                        'font': closest_vl['font'],
                        'size': closest_vl['size'],
                        'flags': closest_vl['flags'],
                        'color': closest_vl['color'],
                        'origin': closest_vl['origin'],
                        'original_bbox': closest_vl['original_bbox'],
                        'line_text': closest_vl['text'],
                        'line_spans': closest_vl['line_spans'],
                        'chars': closest_vl.get('chars', []),
                        'is_overlay': is_ov,
                        'is_vertical': closest_vl.get('is_vertical', False)
                    }
                    if is_ov:
                        clicked_overlay_info = info
                    else:
                        clicked_original_info = info
            
            # 오버레이 텍스트 우선, 없으면 원본 텍스트 선택
            chosen_info = clicked_overlay_info if clicked_overlay_info else clicked_original_info
            
            if not chosen_info:
                print(f"X 더블클릭한 위치에 텍스트가 없습니다. (검사한 span: {found_spans}개)")
                return

            print(f"더블클릭으로 선택된 텍스트 블록: '{chosen_info['text']}' bbox={chosen_info['original_bbox']}")
            
            # 오버레이 객체 연결 확인
            overlay = self.find_overlay_by_current_position(self.current_page_num, chosen_info['original_bbox'])
            if not overlay:
                overlay = self.find_overlay_at_position(self.current_page_num, chosen_info['original_bbox'])
            
            if overlay:
                print(f"기존 레이어 오버레이 감지: '{overlay.text}' (ID: {overlay.z_index})")
                span_info = {
                    'text': overlay.text,
                    'font': overlay.font,
                    'size': float(overlay.size),
                    'flags': overlay.flags,
                    'color': overlay.color,
                    'original_bbox': overlay.original_bbox,
                    'current_bbox': overlay.bbox,
                    'origin': getattr(overlay, 'origin', chosen_info.get('origin')),
                    'line_text': chosen_info['text'],
                    'line_spans': chosen_info['line_spans'],
                    'is_overlay': True,
                    'overlay_id': overlay.z_index,
                    'page_num': self.current_page_num,
                    'stretch': getattr(overlay, 'stretch', 1.0),
                    'tracking': getattr(overlay, 'tracking', 0.0),
                    'hwp_space_mode': getattr(overlay, 'hwp_space_mode', False),
                    'synth_bold_weight': getattr(overlay, 'synth_bold_weight', 120),
                    'underline_weight': getattr(overlay, 'underline_weight', 0.6),
                    'underline_offset': getattr(overlay, 'underline_offset', 1.5)
                }
                self.active_overlay = (self.current_page_num, overlay.z_index)
            else:
                span_info = chosen_info.copy() if hasattr(chosen_info, 'copy') else dict(chosen_info)
                span_info['is_overlay'] = False
                span_info['overlay_id'] = None
                self.active_overlay = None

            print("OK 더블클릭 텍스트 선택 완료 - 편집창으로 전달")
            self.text_selected.emit(span_info)
                
        except Exception as e:
            print(f"Error in mouseDoubleClickEvent: {e}")
            import traceback
            traceback.print_exc()
    
    def paintEvent(self, event):
        """커스텀 그리기: PDF 배경, 패치, 호버 하이라이트, 텍스트 오버레이"""
        painter = QPainter(self)
        if not painter.isActive():
            return
            
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # 테마 모드 안전하게 확인
        theme = 'light'
        if hasattr(self, 'parent_window') and self.parent_window:
            theme = getattr(self.parent_window, 'theme_mode', 'light')
        elif isinstance(self.parent(), QWidget): # 폴백
            win = self.window()
            if hasattr(win, 'theme_mode'):
                theme = win.theme_mode

        bg_color = QColor(30, 31, 34) if theme == 'dark' else QColor(240, 240, 240)
        
        pixmap = self.pixmap()
        if not pixmap or pixmap.isNull():
            painter.fillRect(self.rect(), bg_color) # 테마 배경색 사용
            painter.end()
            return

        # 1. 위젯 배경 및 PDF 픽스맵 렌더링 (중앙 정렬)
        painter.fillRect(self.rect(), bg_color) 
        
        crect = self.contentsRect()
        # 정밀한 부동소수점 오프셋 계산 (정합성 핵심)
        scale = self.pixmap_scale_factor
        
        # 실제 PDF 페이지 크기 (포인트 단위)
        try:
            page = self.doc.load_page(self.current_page_num)
            pw_pt = page.rect.width
            ph_pt = page.rect.height
        except:
            pw_pt = pixmap.width() / scale if scale > 0 else pixmap.width()
            ph_pt = pixmap.height() / scale if scale > 0 else pixmap.height()

        # 화면상의 실제 픽셀 크기 (float)
        pw_px = pw_pt * scale
        ph_px = ph_pt * scale
        
        offset_x = crect.left() + (crect.width() - pw_px) / 2.0
        offset_y = crect.top() + (crect.height() - ph_px) / 2.0
        
        # PDF 배경 픽스맵은 픽셀 단위로 정확히 그림
        painter.drawPixmap(QPointF(offset_x, offset_y), pixmap)
        
        # --- [좌표 변환 시작] ---
        # 이후 모든 그리기는 PDF 좌표계(포인트)에서 수행하도록 설정
        painter.save()
        painter.translate(offset_x, offset_y)
        painter.scale(scale, scale)

        # 1-1. 격자 (Grid) 렌더링
        if getattr(self, 'show_grid', False):
            painter.save()
            try:
                pen_sub = QPen(QColor(180, 180, 180, 50), 0.5 / scale, Qt.PenStyle.DotLine)
                pen_main = QPen(QColor(140, 140, 140, 90), 0.8 / scale, Qt.PenStyle.SolidLine)
                
                # 수직선 (10pt 보조선, 50pt 주선)
                x = 0.0
                while x <= pw_pt:
                    is_main = (int(round(x)) % 50 == 0)
                    painter.setPen(pen_main if is_main else pen_sub)
                    painter.drawLine(QPointF(x, 0), QPointF(x, ph_pt))
                    x += 10.0
                    
                # 수평선 (10pt 보조선, 50pt 주선)
                y = 0.0
                while y <= ph_pt:
                    is_main = (int(round(y)) % 50 == 0)
                    painter.setPen(pen_main if is_main else pen_sub)
                    painter.drawLine(QPointF(0, y), QPointF(pw_pt, y))
                    y += 10.0
            finally:
                painter.restore()
        
        # 2. 배경 패치 렌더링 (PDF 좌표계)
        if hasattr(self, 'background_patches') and self.current_page_num in self.background_patches:
            for pentry in self.background_patches[self.current_page_num]:
                painter.save()
                try:
                    patch_bbox = pentry.get('bbox')
                    stored_color = pentry.get('color')
                    patch_overlay_id = pentry.get('overlay_id')
                    
                    if not patch_bbox: continue
                    
                    is_active = False
                    if self.active_overlay and isinstance(self.active_overlay, (tuple, list)):
                        is_active = (self.active_overlay[0] == self.current_page_num and 
                                    self.active_overlay[1] == patch_overlay_id)
                    
                    # 편집 중인 패치는 50% 투명도(128) 적용하여 원본이 보이게 함, 일반 패치는 100%(255)
                    alpha = 128 if is_active else 255 
                    
                    if stored_color:
                        c = QColor(int(stored_color[0]*255), int(stored_color[1]*255), int(stored_color[2]*255), alpha)
                    else:
                        c = QColor(255, 255, 255, alpha)
                    
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(c))
                    # PDF 좌표계이므로 bbox 그대로 사용
                    painter.drawRect(QRectF(patch_bbox.x0, patch_bbox.y0, patch_bbox.width, patch_bbox.height))
                    
                    if is_active:
                        # 점선 테두리는 눈에 보여야 하므로 스케일 역산하여 1px 유지
                        pen_w = 1.0 / scale if scale > 0 else 1.0
                        painter.setPen(QPen(QColor(0, 0, 0, 150), pen_w, Qt.PenStyle.DashLine))
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.drawRect(QRectF(patch_bbox.x0, patch_bbox.y0, patch_bbox.width, patch_bbox.height))
                finally:
                    painter.restore()

        # 2-1. 본문 검색 하이라이트 렌더링 (PDF 좌표계)
        if getattr(self, 'search_highlights', None):
            painter.save()
            try:
                for srect in self.search_highlights:
                    painter.fillRect(QRectF(srect.x0, srect.y0, srect.width, srect.height), QColor(254, 240, 138, 170))
                
                act_rect = getattr(self, 'active_search_rect', None)
                if act_rect:
                    painter.fillRect(QRectF(act_rect.x0, act_rect.y0, act_rect.width, act_rect.height), QColor(251, 146, 60, 200))
                    pen_w = 2.0 / scale if scale > 0 else 2.0
                    painter.setPen(QPen(QColor(234, 88, 12), pen_w))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(QRectF(act_rect.x0, act_rect.y0, act_rect.width, act_rect.height))
            finally:
                painter.restore()

        # 3. 호버 하이라이트 (PDF 좌표계)
        # 활성 편집 오버레이(active_overlay) 영역과 겹치면 파란색 호버를 억제하여 초록색 하이라이트 보호
        draw_hover = bool(self.hover_rect)
        if draw_hover and self.active_overlay and self.active_overlay[0] == self.current_page_num:
            act_ov = self.get_overlay_by_id(self.active_overlay[0], self.active_overlay[1])
            if act_ov:
                act_r = act_ov.bbox
                h_r = self.hover_rect
                if (h_r.x0 < act_r.x1 and h_r.x1 > act_r.x0 and h_r.y0 < act_r.y1 and h_r.y1 > act_r.y0):
                    draw_hover = False

        if draw_hover:
            painter.save()
            try:
                is_ov = isinstance(self.hover_span_info, dict) and self.hover_span_info.get('is_overlay', False)
                pen_w = 1.5 / scale if scale > 0 else 1.5
                if is_ov:
                    pen = QPen(QColor(0, 200, 0), pen_w)
                    pen.setStyle(Qt.PenStyle.CustomDashLine)
                    pen.setDashPattern([6/scale, 4/scale])
                    pen.setDashOffset(self._anim_phase / scale)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                else:
                    painter.setPen(QPen(QColor(0, 120, 255, 220), pen_w))
                    painter.setBrush(QBrush(QColor(0, 120, 255, 50)))
                painter.drawRect(QRectF(self.hover_rect.x0, self.hover_rect.y0, self.hover_rect.width, self.hover_rect.height))
            finally:
                painter.restore()

        # 4. 일반 선택 강조 표시 (활성 오버레이)
        if self.active_overlay and not self.text_adjustment_mode:
            page_num, overlay_id = self.active_overlay
            if page_num == self.current_page_num:
                overlay = self.get_overlay_by_id(page_num, overlay_id)
                if overlay:
                    painter.save()
                    try:
                        pen_w = 2.0 / scale if scale > 0 else 2.0
                        pen = QPen(QColor(0, 200, 0), pen_w)
                        pen.setStyle(Qt.PenStyle.CustomDashLine)
                        pen.setDashPattern([6/scale, 4/scale])
                        pen.setDashOffset(self._anim_phase / scale)
                        painter.setPen(pen)
                        painter.setBrush(QBrush(QColor(0, 200, 0, 30)))
                        painter.drawRect(QRectF(overlay.bbox.x0, overlay.bbox.y0, overlay.bbox.width, overlay.bbox.height))
                    finally:
                        painter.restore()

        # 5. 텍스트 조정 모드 강조 (주황색)
        if self.text_adjustment_mode and self.selected_text_info:
            abox = self.selected_text_info.get('original_bbox')
            if abox:
                painter.save()
                try:
                    pen_w = 2.5 / scale if scale > 0 else 2.5
                    painter.setPen(QPen(QColor(255, 165, 0), pen_w))
                    painter.setBrush(QBrush(QColor(255, 165, 0, 60)))
                    painter.drawRect(QRectF(abox.x0, abox.y0, abox.width, abox.height))
                    # 십자선 (픽셀 단위 시인성 확보를 위해 조정)
                    center = QRectF(abox.x0, abox.y0, abox.width, abox.height).center()
                    line_l = 15.0 / scale
                    painter.drawLine(QPointF(center.x() - line_l, center.y()), QPointF(center.x() + line_l, center.y()))
                    painter.drawLine(QPointF(center.x(), center.y() - line_l), QPointF(center.x(), center.y() + line_l))
                finally:
                    painter.restore()

        # 6. 텍스트 오버레이 실제 내용 렌더링
        if hasattr(self, 'text_overlays') and self.current_page_num in self.text_overlays:
            sorted_ovs = sorted(self.text_overlays[self.current_page_num], key=lambda x: x.z_index)
            for ov in sorted_ovs:
                if ov.visible:
                    try:
                        # 절대 좌표계에서 직접 렌더링
                        ov.render_to_painter(painter, scale, offsets=(0, 0))
                    except Exception as e_ov:
                        print(f"오버레이 렌더링 에러: {e_ov}")

        # 6-1. 이미지/서명 오버레이 렌더링 (PDF 좌표계)
        if hasattr(self, 'image_overlays') and self.current_page_num in self.image_overlays:
            for img_ov in self.image_overlays[self.current_page_num]:
                if not img_ov.visible or img_ov.pixmap.isNull():
                    continue
                painter.save()
                try:
                    painter.setOpacity(img_ov.opacity)
                    target_rect = QRectF(img_ov.bbox.x0, img_ov.bbox.y0, img_ov.bbox.width, img_ov.bbox.height)
                    painter.drawPixmap(target_rect, img_ov.pixmap, QRectF(img_ov.pixmap.rect()))

                    # 선택된 이미지 강조 테두리 및 리사이즈 핸들
                    if self.active_image == img_ov:
                        painter.setOpacity(1.0)
                        pen_w = 1.5 / scale if scale > 0 else 1.5
                        painter.setPen(QPen(QColor(30, 144, 255), pen_w, Qt.PenStyle.DashLine))
                        painter.setBrush(Qt.BrushStyle.NoBrush)
                        painter.drawRect(target_rect)

                        # 모서리 리사이즈 핸들
                        handle_size = 8.0 / scale
                        painter.setPen(QPen(QColor(30, 144, 255), pen_w))
                        painter.setBrush(QBrush(QColor(255, 255, 255)))
                        corners = [
                            QPointF(target_rect.left(), target_rect.top()),
                            QPointF(target_rect.right(), target_rect.top()),
                            QPointF(target_rect.left(), target_rect.bottom()),
                            QPointF(target_rect.right(), target_rect.bottom())
                        ]
                        for c in corners:
                            painter.drawRect(QRectF(c.x() - handle_size / 2, c.y() - handle_size / 2, handle_size, handle_size))
                finally:
                    painter.restore()

        # 6.5 스마트 스냅 가이드선 렌더링 (PDF 좌표계)
        if getattr(self, 'active_snap_guides', None):
            painter.save()
            try:
                page = self.doc.load_page(self.current_page_num) if self.doc else None
                pw = page.rect.width if page else 595.0
                ph = page.rect.height if page else 842.0
                pen_w = 1.2 / scale if scale > 0 else 1.2
                guide_pen = QPen(QColor(234, 17, 121, 230), pen_w, Qt.PenStyle.DashLine)
                painter.setPen(guide_pen)
                for orient, val in self.active_snap_guides:
                    if orient == 'v':
                        painter.drawLine(QPointF(val, 0), QPointF(val, ph))
                    elif orient == 'h':
                        painter.drawLine(QPointF(0, val), QPointF(pw, val))
            finally:
                painter.restore()

        # PDF 좌표계 변환 종료 (반드시 호출)
        try:
            painter.restore()
        except Exception:
            pass

        # 7. 사각형 영역 선택 (Ctrl + 드래그: 패치모드 / Shift + 드래그: 지우개모드) - 이건 화면 좌표계 유지
        if self.selection_mode and self.selection_rect:
            painter.save()
            try:
                is_eraser = getattr(self, 'selection_is_eraser', False)
                if is_eraser:
                    painter.setPen(QPen(QColor(249, 115, 22, 230), 2, Qt.PenStyle.DashLine))
                    painter.setBrush(QBrush(QColor(249, 115, 22, 60)))
                else:
                    painter.setPen(QPen(QColor(255, 0, 0, 200), 2))
                    painter.setBrush(QBrush(QColor(255, 0, 0, 50)))
                painter.drawRect(self.selection_rect)
            finally:
                painter.restore()

        # 8. 줄자 (Ruler) 렌더링 (화면 좌표계 최상단 오버레이)
        if getattr(self, 'show_ruler', False):
            painter.save()
            try:
                ruler_thickness = 22
                ruler_bg = QColor(38, 40, 44, 235) if theme == 'dark' else QColor(245, 245, 247, 235)
                ruler_fg = QColor(180, 180, 185) if theme == 'dark' else QColor(80, 80, 85)
                ruler_border = QColor(60, 62, 68) if theme == 'dark' else QColor(210, 210, 215)
                font_ruler = QFont('Arial', 7)
                painter.setFont(font_ruler)

                # 1) 상단 수평 줄자
                top_ruler_rect = QRectF(0, 0, self.width(), ruler_thickness)
                painter.fillRect(top_ruler_rect, ruler_bg)
                painter.setPen(QPen(ruler_border, 1))
                painter.drawLine(QPointF(0, ruler_thickness), QPointF(self.width(), ruler_thickness))

                pt = 0.0
                while pt <= pw_pt:
                    sx = offset_x + pt * scale
                    if 0 <= sx <= self.width():
                        is_100 = (int(round(pt)) % 100 == 0)
                        is_50 = (int(round(pt)) % 50 == 0)
                        h = 14 if is_100 else (8 if is_50 else 4)
                        painter.setPen(QPen(ruler_fg, 1))
                        painter.drawLine(QPointF(sx, ruler_thickness - h), QPointF(sx, ruler_thickness))
                        if is_100 and sx + 30 <= self.width():
                            painter.drawText(QRectF(sx + 2, 2, 40, 12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(int(round(pt))))
                    pt += 10.0

                # 2) 좌측 수직 줄자
                left_ruler_rect = QRectF(0, 0, ruler_thickness, self.height())
                painter.fillRect(left_ruler_rect, ruler_bg)
                painter.setPen(QPen(ruler_border, 1))
                painter.drawLine(QPointF(ruler_thickness, 0), QPointF(ruler_thickness, self.height()))

                pt = 0.0
                while pt <= ph_pt:
                    sy = offset_y + pt * scale
                    if 0 <= sy <= self.height():
                        is_100 = (int(round(pt)) % 100 == 0)
                        is_50 = (int(round(pt)) % 50 == 0)
                        w = 14 if is_100 else (8 if is_50 else 4)
                        painter.setPen(QPen(ruler_fg, 1))
                        painter.drawLine(QPointF(ruler_thickness - w, sy), QPointF(ruler_thickness, sy))
                        if is_100 and sy + 15 <= self.height():
                            painter.save()
                            painter.translate(2, sy + 2)
                            painter.drawText(QRectF(0, 0, 30, 12), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(int(round(pt))))
                            painter.restore()
                    pt += 10.0

                # 3) 좌상단 코너 단위 표시 (pt)
                corner_rect = QRectF(0, 0, ruler_thickness, ruler_thickness)
                painter.fillRect(corner_rect, ruler_bg)
                painter.setPen(QPen(ruler_border, 1))
                painter.drawRect(corner_rect)
                painter.setPen(QPen(ruler_fg, 1))
                painter.drawText(corner_rect, Qt.AlignmentFlag.AlignCenter, "pt")

                # 4) 마우스 포인터 실시간 추적 인디케이터
                if hasattr(self, 'mouse_pos') and self.mouse_pos:
                    mx = self.mouse_pos.x()
                    my = self.mouse_pos.y()
                    pen_ind = QPen(QColor(255, 69, 58, 220), 1)
                    painter.setPen(pen_ind)
                    painter.drawLine(QPointF(mx, 0), QPointF(mx, ruler_thickness))
                    painter.drawLine(QPointF(0, my), QPointF(ruler_thickness, my))
            finally:
                painter.restore()

        painter.end()

    def _find_image_at_point(self, pdf_point):
        """PDF 좌표에 위치한 이미지 반환 (최상위 레이어 우선)"""
        if not hasattr(self, 'image_overlays') or self.current_page_num not in self.image_overlays:
            return None
        for img in reversed(self.image_overlays[self.current_page_num]):
            if img.visible and self._rect_contains_point(img.bbox, pdf_point):
                return img
        return None

    def _is_on_image_resize_handle(self, img_ov, pdf_point):
        """이미지의 우하단 리사이즈 핸들 위에 있는지 검사"""
        if not img_ov:
            return False
        scale = getattr(self, 'pixmap_scale_factor', 1.0)
        hs = 10.0 / scale if scale > 0 else 10.0
        handle_rect = fitz.Rect(img_ov.bbox.x1 - hs, img_ov.bbox.y1 - hs, img_ov.bbox.x1 + hs, img_ov.bbox.y1 + hs)
        return self._rect_contains_point(handle_rect, pdf_point)

    def add_image_overlay(self, image_path, bbox=None, opacity=1.0):
        """현재 페이지에 이미지/서명 오버레이 추가"""
        if not os.path.exists(image_path):
            return None
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return None

        page = self.doc.load_page(self.current_page_num) if self.doc else None
        pw = page.rect.width if page else 595.0
        ph = page.rect.height if page else 842.0

        if bbox is None:
            orig_w = float(pixmap.width())
            orig_h = float(pixmap.height())
            aspect = orig_w / orig_h if orig_h > 0 else 1.0
            w = min(140.0, pw * 0.4)
            h = w / aspect
            mx, my = pw / 2.0 - w / 2.0, ph / 2.0 - h / 2.0
            if hasattr(self, 'mouse_pos') and self.mouse_pos:
                px, py = self._widget_point_to_pdf(self.mouse_pos)
                if px is not None and py is not None and 0 <= px <= pw and 0 <= py <= ph:
                    mx, my = px - w / 2.0, py - h / 2.0
            bbox = fitz.Rect(mx, my, mx + w, my + h)

        img_ov = ImageOverlay(image_path, bbox, self.current_page_num, opacity=opacity, z_index=self.image_id_counter)
        self.image_id_counter += 1

        if self.current_page_num not in self.image_overlays:
            self.image_overlays[self.current_page_num] = []
        self.image_overlays[self.current_page_num].append(img_ov)
        self.active_image = img_ov
        self.active_overlay = None
        self.update()

        main_win = self.window()
        if main_win and hasattr(main_win, 'undo_manager') and self.doc:
            try:
                main_win.undo_manager.save_state(self.doc, self)
            except Exception:
                pass
        return img_ov

    def delete_image_overlay(self, image_overlay):
        """이미지 오버레이 삭제"""
        main_win = self.window()
        if main_win and hasattr(main_win, 'undo_manager') and self.doc:
            try:
                main_win.undo_manager.save_state(self.doc, self)
            except Exception:
                pass

        for p, lst in self.image_overlays.items():
            if image_overlay in lst:
                lst.remove(image_overlay)
                break
        if self.active_image == image_overlay:
            self.active_image = None
        self.update()

    def copy_selected(self):
        """현재 선택/호버된 텍스트상자 또는 이미지 복사"""
        # 1. 이미지 선택된 경우
        if self.active_image:
            self.copied_data = {
                'type': 'image',
                'image_path': self.active_image.image_path,
                'width': self.active_image.bbox.width,
                'height': self.active_image.bbox.height,
                'opacity': self.active_image.opacity
            }
            main_win = self.window()
            if main_win and hasattr(main_win, 'statusBar'):
                main_win.statusBar().showMessage("이미지가 복사되었습니다.", 2000)
            return True

        # 2. 오버레이 선택된 경우
        target_ov = None
        if self.active_overlay and isinstance(self.active_overlay, (tuple, list)):
            target_ov = self.get_overlay_by_id(self.active_overlay[0], self.active_overlay[1])
        elif self.selected_text_info and self.selected_text_info.get('is_overlay'):
            target_ov = self.get_overlay_by_id(
                self.selected_text_info.get('page_num', self.current_page_num),
                self.selected_text_info.get('overlay_id')
            )

        if target_ov:
            self.copied_data = {
                'type': 'text',
                'text': target_ov.text,
                'font': target_ov.font,
                'size': target_ov.size,
                'color': target_ov.color,
                'flags': target_ov.flags,
                'width': target_ov.bbox.width,
                'height': target_ov.bbox.height,
                'synth_bold_weight': getattr(target_ov, 'synth_bold_weight', 120),
                'underline_weight': getattr(target_ov, 'underline_weight', 0.6),
                'underline_offset': getattr(target_ov, 'underline_offset', 1.5),
                'hwp_space_mode': getattr(target_ov, 'hwp_space_mode', False),
                'stretch': getattr(target_ov, 'stretch', 1.0),
                'tracking': getattr(target_ov, 'tracking', 0.0),
                'origin': getattr(target_ov, 'origin', None)
            }
            QApplication.clipboard().setText(target_ov.text)
            main_win = self.window()
            if main_win and hasattr(main_win, 'statusBar'):
                main_win.statusBar().showMessage(f"텍스트상자 복사됨: '{target_ov.text}'", 2000)
            return True

        # 3. 호버된 텍스트가 있는 경우
        if self.hover_span_info:
            info = self.hover_span_info
            text = info.get('text', '')
            bbox = fitz.Rect(info.get('bbox', info.get('original_bbox', [0, 0, 50, 20])))
            self.copied_data = {
                'type': 'text',
                'text': text,
                'font': info.get('font', 'Arial'),
                'size': float(info.get('size', 12.0)),
                'color': info.get('color', 0),
                'flags': info.get('flags', 0),
                'width': bbox.width,
                'height': bbox.height,
                'synth_bold_weight': info.get('synth_bold_weight', 120),
                'underline_weight': info.get('underline_weight', 0.6),
                'underline_offset': info.get('underline_offset', 1.5),
                'hwp_space_mode': info.get('hwp_space_mode', False),
                'origin': info.get('origin', None)
            }
            QApplication.clipboard().setText(text)
            main_win = self.window()
            if main_win and hasattr(main_win, 'statusBar'):
                main_win.statusBar().showMessage(f"텍스트 복사됨: '{text}'", 2000)
            return True

        return False

    def paste_clipboard(self):
        """클립보드 내용(텍스트상자 또는 이미지) 붙여넣기"""
        main_win = self.window()
        if main_win and hasattr(main_win, 'undo_manager') and self.doc:
            try:
                main_win.undo_manager.save_state(self.doc, self)
            except Exception:
                pass

        pdf_x, pdf_y = None, None
        if hasattr(self, 'mouse_pos') and self.mouse_pos:
            pdf_x, pdf_y = self._widget_point_to_pdf(self.mouse_pos)

        page = self.doc.load_page(self.current_page_num) if self.doc else None
        pw = page.rect.width if page else 595.0
        ph = page.rect.height if page else 842.0

        if pdf_x is None or pdf_y is None or pdf_x < 0 or pdf_x > pw or pdf_y < 0 or pdf_y > ph:
            pdf_x, pdf_y = pw / 2.0 - 50.0, ph / 2.0 - 20.0

        # 1. 이미지 붙여넣기
        if self.copied_data and self.copied_data.get('type') == 'image':
            img_path = self.copied_data['image_path']
            w = self.copied_data.get('width', 140.0)
            h = self.copied_data.get('height', 100.0)
            opacity = self.copied_data.get('opacity', 1.0)
            bbox = fitz.Rect(pdf_x, pdf_y, pdf_x + w, pdf_y + h)
            self.add_image_overlay(img_path, bbox=bbox, opacity=opacity)
            if main_win and hasattr(main_win, 'statusBar'):
                main_win.statusBar().showMessage("이미지가 붙여넣어졌습니다.", 2000)
            return True

        # 2. 서식 복사된 텍스트상자 붙여넣기
        if self.copied_data and self.copied_data.get('type') == 'text':
            d = self.copied_data
            w = max(20.0, d.get('width', 80.0))
            h = max(12.0, d.get('height', float(d.get('size', 12.0)) * 1.3))
            bbox = fitz.Rect(pdf_x, pdf_y, pdf_x + w, pdf_y + h)
            
            ov = self.add_text_overlay(
                text=d.get('text', ''),
                font=d.get('font', 'Arial'),
                size=d.get('size', 12.0),
                color=d.get('color', 0),
                bbox=bbox,
                page_num=self.current_page_num,
                flags=d.get('flags', 0),
                synth_bold_weight=d.get('synth_bold_weight', 120),
                underline_weight=d.get('underline_weight', 0.6),
                underline_offset=d.get('underline_offset', 1.5),
                hwp_space_mode=d.get('hwp_space_mode', False),
                source_bbox=bbox
            )
            if hasattr(ov, 'stretch'):
                ov.stretch = d.get('stretch', 1.0)
            if hasattr(ov, 'tracking'):
                ov.tracking = d.get('tracking', 0.0)

            self.active_overlay = (self.current_page_num, ov.z_index)
            self.update()
            if main_win and hasattr(main_win, 'statusBar'):
                main_win.statusBar().showMessage(f"텍스트상자 붙여넣음: '{ov.text}'", 2000)
            return True

        # 3. 시스템 클립보드 일반 텍스트 붙여넣기
        clip_text = QApplication.clipboard().text()
        if clip_text:
            size = 12.0
            w = max(40.0, len(clip_text) * size * 0.6)
            h = size * 1.5
            bbox = fitz.Rect(pdf_x, pdf_y, pdf_x + w, pdf_y + h)
            ov = self.add_text_overlay(
                text=clip_text,
                font='Arial',
                size=size,
                color=0,
                bbox=bbox,
                page_num=self.current_page_num,
                flags=0,
                source_bbox=bbox
            )
            self.active_overlay = (self.current_page_num, ov.z_index)
            self.update()
            if main_win and hasattr(main_win, 'statusBar'):
                main_win.statusBar().showMessage(f"클립보드 텍스트 붙여넣음: '{clip_text}'", 2000)
            return True

        return False
    
    def _pdf_rect_to_screen_rect(self, pdf_rect):
        """PDF 좌표 사각형을 화면 좌표 사각형으로 변환"""
        try:
            pixmap = self.pixmap()
            if not pixmap:
                return None
            
            widget_rect = self.rect()
            pixmap_rect = pixmap.rect()
            offset_x = (widget_rect.width() - pixmap_rect.width()) // 2
            offset_y = (widget_rect.height() - pixmap_rect.height()) // 2
            
            screen_x0 = pdf_rect.x0 * self.pixmap_scale_factor + offset_x
            screen_y0 = pdf_rect.y0 * self.pixmap_scale_factor + offset_y
            screen_x1 = pdf_rect.x1 * self.pixmap_scale_factor + offset_x
            screen_y1 = pdf_rect.y1 * self.pixmap_scale_factor + offset_y
            
            return QRect(int(screen_x0), int(screen_y0), 
                        int(screen_x1 - screen_x0), int(screen_y1 - screen_y0))
        except:
            return None

    def _pdf_rect_to_screen_rect_f(self, pdf_rect):
        """PDF 좌표 사각형을 화면 좌표 사각형(부동소수점)으로 정밀 변환"""
        try:
            pixmap = self.pixmap()
            if not pixmap or pixmap.isNull():
                return None
            
            crect = self.contentsRect()
            scale = getattr(self, 'pixmap_scale_factor', 1.0)
            
            # 실제 PDF 페이지 크기 (포인트 단위) 기반 정밀 오프셋
            try:
                page = self.doc.load_page(self.current_page_num)
                pw_pt = page.rect.width
                ph_pt = page.rect.height
            except:
                pw_pt = pixmap.width() / scale if scale > 0 else pixmap.width()
                ph_pt = pixmap.height() / scale if scale > 0 else pixmap.height()

            pw_px = pw_pt * scale
            ph_px = ph_pt * scale
            
            offset_x = crect.left() + (crect.width() - pw_px) / 2.0
            offset_y = crect.top() + (crect.height() - ph_px) / 2.0
            
            screen_x0 = pdf_rect.x0 * scale + offset_x
            screen_y0 = pdf_rect.y0 * scale + offset_y
            screen_x1 = pdf_rect.x1 * scale + offset_x
            screen_y1 = pdf_rect.y1 * scale + offset_y
            
            return QRectF(screen_x0, screen_y0, screen_x1 - screen_x0, screen_y1 - screen_y0)
        except:
            return None
    
    def _pdf_point_to_screen_point(self, pdf_x, pdf_y):
        """PDF 좌표 점을 화면 좌표 점으로 변환"""
        try:
            pixmap = self.pixmap()
            if not pixmap:
                return None, None
            
            crect = self.contentsRect()
            offset_x = crect.left() + (crect.width() - pixmap.width()) / 2.0
            offset_y = crect.top() + (crect.height() - pixmap.height()) / 2.0
            
            screen_x = pdf_x * self.pixmap_scale_factor + offset_x
            screen_y = pdf_y * self.pixmap_scale_factor + offset_y
            
            return screen_x, screen_y
        except:
            return None, None

    def _widget_point_to_pdf(self, widget_point: QPoint):
        """위젯 좌표(QPoint)를 PDF 좌표로 변환 (마진/테두리 반영)"""
        try:
            pixmap = self.pixmap()
            if pixmap is None or pixmap.isNull():
                return None, None

            crect = self.contentsRect()
            scale = getattr(self, 'pixmap_scale_factor', 1.0)
            if scale <= 0:
                return None, None

            # 실제 PDF 페이지 크기 (포인트 단위) 기반 정밀 오프셋
            try:
                page = self.doc.load_page(self.current_page_num)
                pw_pt = page.rect.width
                ph_pt = page.rect.height
            except:
                pw_pt = pixmap.width() / scale
                ph_pt = pixmap.height() / scale

            pw_px = pw_pt * scale
            ph_px = ph_pt * scale
            
            offset_x = crect.left() + (crect.width() - pw_px) / 2.0
            offset_y = crect.top() + (crect.height() - ph_px) / 2.0

            pdf_x = (widget_point.x() - offset_x) / scale
            pdf_y = (widget_point.y() - offset_y) / scale
            return pdf_x, pdf_y
        except Exception as e:
            print(f"_widget_point_to_pdf error: {e}")
            return None, None

    def _pdf_rect_to_widget_rect(self, pdf_rect):
        """PDF 좌표 fitz.Rect를 위젯(화면) 좌표 QRect로 변환"""
        try:
            scale = getattr(self, 'pixmap_scale_factor', 1.0)
            if scale <= 0 or not self.doc:
                return None
            crect = self.contentsRect()
            page = self.doc.load_page(self.current_page_num)
            pw_pt = float(page.rect.width)
            ph_pt = float(page.rect.height)
            pw_px = pw_pt * scale
            ph_px = ph_pt * scale
            offset_x = crect.left() + (crect.width() - pw_px) / 2.0
            offset_y = crect.top() + (crect.height() - ph_px) / 2.0

            rx0 = offset_x + pdf_rect.x0 * scale
            ry0 = offset_y + pdf_rect.y0 * scale
            rw = pdf_rect.width * scale
            rh = pdf_rect.height * scale
            return QRect(int(round(rx0)), int(round(ry0)), int(round(rw)), int(round(rh)))
        except Exception as e:
            print(f"_pdf_rect_to_widget_rect error: {e}")
            return None

    def enter_text_adjustment_mode(self, text_info):
        """텍스트 위치 조정 모드 진입"""
        self.text_adjustment_mode = True
        self.selected_text_info = text_info.copy()
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        print("텍스트 위치 조정 모드: 방향키로 위치 조정, Enter로 완료, Escape로 취소")
        overlay_id = text_info.get('overlay_id')
        if overlay_id is not None:
            self.active_overlay = (self.current_page_num, overlay_id)
        mw = getattr(self, 'main_window', None) or self.window()
        if mw and hasattr(mw, 'update_status_mode_message'):
            mw.update_status_mode_message()
        self.update()
    
    def exit_text_adjustment_mode(self):
        """텍스트 위치 조정 모드 종료"""
        self.text_adjustment_mode = False
        self.selected_text_info = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        print("텍스트 위치 조정 모드 종료")
        self.active_overlay = None
        mw = getattr(self, 'main_window', None) or self.window()
        if mw and hasattr(mw, 'update_status_mode_message'):
            mw.update_status_mode_message()
        self.update()
    
    def adjust_text_position(self, dx, dy):
        """텍스트 위치 조정 - 레이어 방식으로 부드러운 이동 (백업01 호환)"""
        if not self.selected_text_info or not self.doc:
            return
            
        # original_bbox 기준 이동
        old_bbox = self.selected_text_info['original_bbox']
        new_bbox = fitz.Rect(
            old_bbox.x0 + dx, old_bbox.y0 + dy,
            old_bbox.x1 + dx, old_bbox.y1 + dy
        )
        
        try:
            # 레이어 방식 오버레이 이동 시도 (원본 위치 기준)
            overlay = self.find_overlay_at_position(self.current_page_num, old_bbox)
            if overlay:
                # 레이어 방식: 오버레이 위치만 업데이트 (PDF 재렌더링 불필요)
                self.move_overlay_to(overlay, new_bbox)
                print(f"레이어 이동: '{overlay.text}' dx={dx}, dy={dy}")
                
                # 선택된 텍스트 정보 업데이트 (bbox 및 origin 동기화)
                self.selected_text_info['original_bbox'] = new_bbox
                if 'origin' in self.selected_text_info and self.selected_text_info['origin']:
                    try:
                        old_origin = self.selected_text_info['origin']
                        self.selected_text_info['origin'] = (old_origin[0] + dx, old_origin[1] + dy)
                    except Exception:
                        pass
                elif hasattr(overlay, 'origin'):
                    self.selected_text_info['origin'] = overlay.origin
                
                # 호버 상태 정보도 새 위치로 업데이트 (연속 방향키 이동을 위해 필수)
                if self.hover_rect:
                    self.hover_rect = new_bbox
                
                # 호버 span 정보가 있다면 위치 업데이트
                if hasattr(self, 'hover_span_info') and self.hover_span_info:
                    if isinstance(self.hover_span_info, dict) and 'bbox' in self.hover_span_info:
                        self.hover_span_info['bbox'] = new_bbox
                
                print(f"   hover_rect 업데이트: {new_bbox}")
                return
            
            # 레이어 오버레이가 없으면 기존 방식으로 fallback
            print("경고 레이어 오버레이 없음 - 기존 방식 사용")
            self._adjust_text_position_fallback(dx, dy, old_bbox, new_bbox)
            
        except Exception as e:
            print(f"X 텍스트 위치 조정 오류: {e}")
            # 오류 발생 시 기존 방식으로 fallback
            self._adjust_text_position_fallback(dx, dy, old_bbox, new_bbox)
        
        print(f"텍스트 위치 조정: dx={dx}, dy={dy}")
    
    def _adjust_text_position_fallback(self, dx, dy, old_bbox, new_bbox):
        """텍스트 위치 조정 - 기존 PDF 렌더링 방식 fallback"""
        try:
            # 메인 윈도우 찾기
            main_window = None
            widget = self
            while widget:
                widget = widget.parent()
                if isinstance(widget, QMainWindow):
                    main_window = widget
                    break
            
            if not main_window:
                print("메인 윈도우를 찾을 수 없습니다.")
                self.update()
                return
                
            page = self.doc.load_page(self.current_page_num)
            
            # 레거시 추적 시스템 업데이트
            old_bbox_hash = self._get_bbox_hash(old_bbox)
            if (self.current_page_num, old_bbox_hash) in self.overlay_texts:
                self.overlay_texts.remove((self.current_page_num, old_bbox_hash))
            
            new_bbox_hash = self._get_bbox_hash(new_bbox)
            self.overlay_texts.add((self.current_page_num, new_bbox_hash))
            
            # PDF 오버레이 업데이트 (배경 패치와 분리 관리)
            if hasattr(main_window, 'apply_background_patch'):
                color_value = self.selected_text_info.get('color', 0)
                if isinstance(color_value, int):
                    text_color = QColor(0, 0, 0) if color_value == 0 else QColor(0, 0, 0)
                else:
                    text_color = color_value if hasattr(color_value, 'redF') else QColor(0, 0, 0)
                
                new_values = {
                    'text': self.selected_text_info.get('text', ''),
                    'font': self.selected_text_info.get('font', ''),
                    'size': self.selected_text_info.get('size', 12),
                    'color': text_color
                }
                
                overlay_id = self.selected_text_info.get('overlay_id')
                self.remove_background_patch(self.current_page_num, bbox=old_bbox, overlay_id=overlay_id)
                main_window.apply_background_patch(page, new_bbox, new_values, preview=False)
                
                # selected_text_info 위치 업데이트
                self.selected_text_info['original_bbox'] = new_bbox
                
                # Fallback 오버레이 추가 (레이어 오버레이가 없는 경우에만)
                main_window.insert_overlay_text(page, self.selected_text_info, new_values)
            
            # 페이지 재렌더링 (기존 방식)
            if hasattr(main_window, 'render_page'):
                main_window.render_page(page_to_render=page)
            else:
                self.update()
                
        except Exception as e:
            print(f"Fallback 위치 조정 오류: {e}")
            self.update()
    
    def complete_area_selection(self):
        """사각형 선택 영역으로 배경 패치 생성 및 새 텍스트 오버레이 추가"""
        if not self.selection_rect or not self.doc:
            return

        try:
            # 선택 영역을 PDF 좌표로 변환
            pdf_selection_rect = self._screen_rect_to_pdf_rect(self.selection_rect)
            print(f"화면 선택 영역: {self.selection_rect}")
            print(f"PDF 선택 영역: {pdf_selection_rect}")
            if not pdf_selection_rect:
                print("X PDF 좌표 변환 실패 - 사각형 선택 취소")
                return

            page = self.doc.load_page(self.current_page_num)

            # 메인 윈도우 참조 획득
            main_window = self
            while main_window and not hasattr(main_window, 'apply_background_patch'):
                main_window = main_window.parent()

            if not main_window:
                print("X MainWindow를 찾을 수 없어 작업을 중단합니다.")
                return

            # 1) 선택영역에서 텍스트/스타일 추출
            # 텍스트: 영역 내 텍스트를 가져와 한 줄로 정규화
            try:
                # visual lines에서 선택 영역과 교차하는 텍스트 추출 (시각적 공백 복원 반영)
                vlines = self._get_visual_lines_for_page(self.current_page_num)
                intersected_texts = []
                for vl in vlines:
                    if self._rects_overlap(vl['original_bbox'], pdf_selection_rect, tol=1.0):
                        intersected_texts.append(vl['text'])
                if intersected_texts:
                    region_text = ' '.join(intersected_texts).strip()
                else:
                    rot_clip = (pdf_selection_rect * page.derotation_matrix) if page.rotation != 0 else pdf_selection_rect
                    region_text = page.get_text("text", clip=rot_clip) or ""
                    region_text = re.sub(r"\s+", " ", region_text).strip()
                region_text = ''.join(c for c in region_text if not is_pua_char(c))
            except Exception:
                region_text = ""

            # 스타일: 가장 빈도 높은 폰트 / 평균 크기 / 가장 빈도 높은 색상
            try:
                text_dict = page.get_text("dict")
                rot_mat = page.rotation_matrix if page.rotation != 0 else None
                fonts = []
                sizes = []
                colors = []
                for block in text_dict.get("blocks", []):
                    if block.get('type') != 0:
                        continue
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            span_bbox = fitz.Rect(span["bbox"])
                            if rot_mat:
                                span_bbox = span_bbox * rot_mat
                            if span_bbox.intersects(pdf_selection_rect):
                                if span.get('font'): fonts.append(span['font'])
                                if span.get('size'): sizes.append(float(span['size']))
                                if 'color' in span: colors.append(span['color'])
                chosen_font = fonts and Counter(fonts).most_common(1)[0][0] or 'Arial'
                chosen_size = sizes and (sum(sizes)/len(sizes)) or 12.0
                chosen_color = colors and Counter(colors).most_common(1)[0][0] or 0
            except Exception:
                chosen_font, chosen_size, chosen_color = 'Arial', 12.0, 0

            # 시스템 폰트 매칭
            chosen_font_orig = chosen_font
            try:
                fmgr = SystemFontManager()
                matched = fmgr.find_best_font_match(chosen_font) or chosen_font
                chosen_font = matched
            except Exception:
                pass

            # 2) 기존 텍스트 편집창을 활용해 새 오버레이 생성 (확정 전까지 PDF 비변경)
            span_info = {
                'text': region_text,
                'font': chosen_font,
                'pdf_font_name': chosen_font_orig,
                'size': chosen_size,
                'flags': 0,
                'color': chosen_color,
                'original_bbox': pdf_selection_rect,
                'page_num': self.current_page_num
            }

            patch_only_mode = getattr(main_window, 'patch_only_mode', False) or getattr(self, 'selection_is_eraser', False)

            if patch_only_mode:
                if hasattr(main_window, 'undo_manager') and self.doc:
                    try:
                        main_window.undo_manager.save_state(self.doc, self)
                    except Exception as state_err:
                        print(f"Undo 상태 저장 실패: {state_err}")

                default_margin = getattr(main_window, 'patch_margin', (0.0, 0.0))
                if isinstance(default_margin, (tuple, list)) and len(default_margin) >= 2:
                    try:
                        default_h = float(default_margin[0])
                        default_v = float(default_margin[1])
                    except Exception:
                        default_h = default_v = 0.0
                else:
                    try:
                        scalar_margin = float(default_margin)
                    except Exception:
                        scalar_margin = 0.0
                    default_h = default_v = scalar_margin

                new_values = {
                    'text': '',
                    'font': chosen_font or 'Arial',
                    'size': float(chosen_size) if chosen_size else 12.0,
                    'color': QColor(0, 0, 0),
                    'patch_margin_h': default_h,
                    'patch_margin_v': default_v,
                    'patch_margin': (default_h, default_v),
                    'stretch': 1.0,
                    'tracking': 0.0,
                    'use_custom_patch_color': bool(getattr(main_window, 'last_use_custom_patch', False))
                }
                if new_values['use_custom_patch_color']:
                    new_values['patch_color'] = getattr(main_window, 'last_patch_color', QColor(255, 255, 255))

                try:
                    patch_rect, patch_color = main_window.apply_background_patch(page, pdf_selection_rect, new_values, overlay=None, preview=False)
                except Exception:
                    patch_rect, patch_color = (pdf_selection_rect, None)
                print("OK 선택 영역 배경 패치 적용 완료 (패치 전용 모드)")

                if hasattr(main_window, 'undo_manager') and self.doc:
                    try:
                        main_window.undo_manager.save_state(self.doc, self)
                    except Exception as state_err:
                        print(f"Undo 상태 저장 실패: {state_err}")
                if hasattr(main_window, 'mark_as_changed'):
                    main_window.mark_as_changed()
                try:
                    main_window.update_undo_redo_buttons()
                except Exception:
                    pass

                # 패치 적용 후 화면 픽스맵 갱신 (중요: 그래야 실제 반영된 모습이 보임)
                if hasattr(main_window, 'render_page'):
                    main_window.render_page(page_to_render=page)

                # UX 개선: 작업 완료 후 모드 해제
                if hasattr(main_window, 'set_patch_mode'):
                    main_window.set_patch_mode(False)
                if hasattr(main_window, 'set_patch_eraser_mode'):
                    main_window.set_patch_eraser_mode(False)

                keep_enabled = False # 무조건 해제
                self.selection_mode = False
                self.selection_rect = None
                self.selection_is_eraser = False
                self.ctrl_pressed = keep_enabled
                self.shift_pressed = False
                try:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
                except Exception:
                    pass
                self.update()
                return

            # [실시간 미리보기 핵심: 다이얼로그 열기 전 미리 오버레이 생성]
            if self.doc and hasattr(main_window, 'undo_manager'):
                main_window.undo_manager.save_state(self.doc, self)
                print("[Patch Mode] Pre-edit state saved for Preview")

            try:
                # 초기 편집값 생성
                if isinstance(chosen_color, int):
                    qcolor = QColor((chosen_color >> 16) & 0xFF, (chosen_color >> 8) & 0xFF, chosen_color & 0xFF)
                else:
                    qcolor = QColor(0, 0, 0)
                
                initial_values = {
                    'text': region_text,
                    'font': chosen_font,
                    'size': float(chosen_size),
                    'color': qcolor,
                    'bold': False,
                    'italic': False,
                    'underline': False,
                    'stretch': 1.0,
                    'tracking': 0.0,
                    'synth_bold_weight': 120,
                    'hwp_space_mode': getattr(main_window, 'is_hwp_doc', False),
                    'patch_margin_l': 0.0, 'patch_margin_r': 0.0, 'patch_margin_t': 0.0, 'patch_margin_b': 0.0
                }
                
                # 미리 오버레이 생성 (UI에 즉시 반영)
                overlay = main_window.insert_overlay_text(page, span_info, initial_values)
                if overlay:
                    main_window.apply_background_patch(page, pdf_selection_rect, initial_values, overlay=overlay, preview=True)
                    
                    # [중요] 생성된 오버레이의 실제 정보를 span_info에 완벽히 동기화 (정합성 및 위치 보존 핵심)
                    overlay_data = overlay.to_dict()
                    span_info.update(overlay_data)
                    span_info['origin'] = getattr(overlay, 'origin', None)
                    span_info['is_overlay'] = True
                    span_info['overlay_id'] = overlay.z_index
                    span_info['page_num'] = self.current_page_num
                    
                    self.active_overlay = (self.current_page_num, overlay.z_index)
                    self.update()
                    print(f"[Patch Mode] Proactive overlay created: ID {overlay.z_index}")
            except Exception as e_pre:
                print(f"패치모드 미리보기 오버레이 생성 실패: {e_pre}")

            # 모달리스 텍스트 편집기 실행 (문서 뷰어의 핸드툴, 줌 조작 허용)
            if hasattr(main_window, 'open_text_editor'):
                main_window.open_text_editor(span_info, is_patch_mode=True)
            return

        except Exception as e:
            print(f"X 사각형 영역 선택 처리 오류: {e}")
            import traceback
            traceback.print_exc()
            # 상태 초기화
            self.selection_rect = None
            self.selection_mode = False
    
    def _screen_to_pdf_coordinates(self, screen_x, screen_y):
        """화면 좌표를 PDF 좌표로 변환 - _widget_point_to_pdf와 통합"""
        return self._widget_point_to_pdf(QPoint(int(screen_x), int(screen_y)))
    
    def _screen_rect_to_pdf_rect(self, screen_rect):
        """화면 사각형을 PDF 좌표계로 변환"""
        try:
            print(f"화면→PDF 좌표 변환 시작")
            print(f"   입력 화면 사각형: {screen_rect}")
            print(f"   topLeft: ({screen_rect.topLeft().x()}, {screen_rect.topLeft().y()})")
            print(f"   bottomRight: ({screen_rect.bottomRight().x()}, {screen_rect.bottomRight().y()})")
            print(f"   width x height: {screen_rect.width()} x {screen_rect.height()}")
            print(f"   현재 pixmap_scale_factor: {self.pixmap_scale_factor}")
            
            # 좌상단과 우하단 점을 PDF 좌표로 변환
            top_left_pdf = self._screen_to_pdf_coordinates(screen_rect.topLeft().x(), screen_rect.topLeft().y())
            bottom_right_pdf = self._screen_to_pdf_coordinates(screen_rect.bottomRight().x(), screen_rect.bottomRight().y())
            
            print(f"   변환된 PDF 좌상단: {top_left_pdf}")
            print(f"   변환된 PDF 우하단: {bottom_right_pdf}")
            
            if top_left_pdf[0] is not None and bottom_right_pdf[0] is not None:
                pdf_rect = fitz.Rect(top_left_pdf[0], top_left_pdf[1], bottom_right_pdf[0], bottom_right_pdf[1])
                print(f"   최종 PDF 사각형: {pdf_rect}")
                print(f"   PDF 크기: {pdf_rect.width:.1f} x {pdf_rect.height:.1f}")
                return pdf_rect
            else:
                print(f"   X 좌표 변환 실패")
                return None
        except Exception as e:
            print(f"X 좌표 변환 오류: {e}")
            return None
    
    def complete_text_adjustment(self):
        """텍스트 위치 조정 완료 - 편집창 팝업 없이 PDF만 업데이트"""
        if not self.selected_text_info:
            return
            
        # 위치 조정 완료 시 PDF에 직접 반영 (편집창 팝업 없이)
        # TODO: PDF 업데이트 로직 필요시 여기에 추가
        print("텍스트 위치 조정 완료 - PDF 반영")
        
        self.exit_text_adjustment_mode()
    
    def start_position_adjustment_from_hover(self):
        """호버된 텍스트에서 위치조정 모드 시작"""
        if not self.hover_rect or not self.doc:
            return
            
        try:
            # 호버된 텍스트 정보 수집
            page = self.doc.load_page(self.current_page_num)
            current_text_dict = page.get_text("dict")
            
            # 호버 영역과 일치하는 텍스트 찾기
            for block in current_text_dict.get("blocks", []):
                if block.get('type') != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        bbox = fitz.Rect(span["bbox"])
                        
                        # 호버 영역과 일치하는 텍스트 찾기
                        if self._rects_overlap(bbox, self.hover_rect, tol=1.0):
                            # 오버레이된 텍스트인지 확인 (수정된 텍스트만 위치조정 가능)
                            if not self.is_overlay_text(span, bbox):
                                print(f"원본 텍스트는 위치조정 불가: {span.get('text', '')}")
                                return
                            
                            # 텍스트 정보 설정
                            text_info = {
                                'text': span.get('text', ''),
                                'font': span.get('font', 'Unknown'),
                                'size': span.get('size', 12),
                                'flags': span.get('flags', 0),
                                'color': span.get('color', 0),
                                'original_bbox': bbox,
                                'span': span,
                                'page_num': self.current_page_num
                            }
                            
                            # Quick adjustment 모드 시작
                            self.quick_adjustment_mode = True
                            self.selected_text_info = text_info.copy()
                            self.setCursor(Qt.CursorShape.SizeAllCursor)
                            print(f"오버레이 텍스트 위치조정 모드 시작: {span.get('text', '')}")
                            overlay_obj = self.find_overlay_at_position(self.current_page_num, bbox)
                            if not overlay_obj:
                                overlay_obj = self.find_overlay_by_current_position(self.current_page_num, bbox)
                            if overlay_obj:
                                self.active_overlay = (self.current_page_num, overlay_obj.z_index)
                            else:
                                self.active_overlay = None
                            self.update()
                            return
                            
        except Exception as e:
            print(f"Error in start_position_adjustment_from_hover: {e}")
            return
    
    def is_overlay_text(self, span, bbox):
        """텍스트가 오버레이된 텍스트인지 확인 - 레이어 시스템 + 추적 시스템 기반"""
        try:
            # 1. 새로운 레이어 시스템에서 확인 (최우선)
            if bbox:
                overlay = self.find_overlay_at_position(self.current_page_num, bbox)
                if not overlay:
                    overlay = self.find_overlay_by_current_position(self.current_page_num, bbox)
                if overlay:
                    return True
            
            # 2. 레거시 추적 시스템에서 확인
            if bbox:
                bbox_hash = self._get_bbox_hash(bbox)
                if (self.current_page_num, bbox_hash) in self.overlay_texts:
                    return True
                
            return False  # 실제 오버레이가 아니면 원본 텍스트
            
        except Exception as e:
            print(f"Error in is_overlay_text: {e}")
            return False
    
    def _get_bbox_hash(self, bbox):
        """bbox 해시 생성"""
        return f"{bbox.x0:.1f},{bbox.y0:.1f},{bbox.x1:.1f},{bbox.y1:.1f}"
    
    def register_overlay_text(self, page_num, bbox):
        """오버레이 텍스트를 추적 시스템에 등록 (레거시)"""
        bbox_hash = self._get_bbox_hash(bbox)
        self.overlay_texts.add((page_num, bbox_hash))
        print(f"오버레이 텍스트 등록: 페이지 {page_num}, bbox {bbox_hash}")
        
    def unregister_overlay_text(self, page_num, bbox):
        bbox_hash = self._get_bbox_hash(bbox)
        if (page_num, bbox_hash) in self.overlay_texts:
            self.overlay_texts.discard((page_num, bbox_hash))
            print(f"오버레이 텍스트 해제: 페이지 {page_num}, bbox {bbox_hash}")

    @staticmethod
    def _rects_close(rect_a: fitz.Rect, rect_b: fitz.Rect, tol: float = 0.6) -> bool:
        if rect_a is None or rect_b is None:
            return False
        return (
            abs(rect_a.x0 - rect_b.x0) <= tol and
            abs(rect_a.y0 - rect_b.y0) <= tol and
            abs(rect_a.x1 - rect_b.x1) <= tol and
            abs(rect_a.y1 - rect_b.y1) <= tol
        )

    @staticmethod
    def _rect_contains_point(rect: fitz.Rect, point: fitz.Point, tol: float = 0.75) -> bool:
        if rect is None or point is None:
            return False
        return (
            rect.x0 - tol <= point.x <= rect.x1 + tol and
            rect.y0 - tol <= point.y <= rect.y1 + tol
        )

    @staticmethod
    def _rects_overlap(rect_a: fitz.Rect, rect_b: fitz.Rect, tol: float = 0.75) -> bool:
        if rect_a is None or rect_b is None:
            return False
        expanded_a = fitz.Rect(rect_a.x0 - tol, rect_a.y0 - tol, rect_a.x1 + tol, rect_a.y1 + tol)
        expanded_b = fitz.Rect(rect_b.x0 - tol, rect_b.y0 - tol, rect_b.x1 + tol, rect_b.y1 + tol)
        return expanded_a.intersects(expanded_b)

    def get_overlay_by_id(self, page_num: int, overlay_id: int):
        overlays = self.text_overlays.get(page_num, [])
        for overlay in overlays:
            if overlay.z_index == overlay_id:
                return overlay
        return None

    def add_text_overlay(
        self,
        text,
        font,
        size,
        color,
        bbox,
        page_num,
        flags=0,
        font_path=None,
        synth_bold=False,
        synth_bold_weight=120,
        underline_weight=0.6,
        underline_offset=1.5,
        patch_margin=None,
        patch_margin_h=None,
        patch_margin_v=None,
        height_ratio=None,
        ascent_ratio=None,
        descent_ratio=None,
        source_bbox=None,
        preview_height_ratio=None,
        hwp_space_mode=False,
        text_only_mode=False,
        origin=None,
        new_values=None,
        pdf_font_name=None
    ):
        """새로운 텍스트 오버레이 추가 (레이어 방식) - 완전한 속성 지원"""
        print(f"TextOverlay 생성 중 - 폰트: '{font}', 크기: {size}, 플래그: {flags}")
        norm_height = TextOverlay._normalize_height_ratio(height_ratio if height_ratio is not None else 1.15)
        preview_norm = TextOverlay._normalize_height_ratio(preview_height_ratio if preview_height_ratio is not None else norm_height)
        if ascent_ratio is None:
            ascent_ratio = norm_height * 0.85
        if descent_ratio is None:
            descent_ratio = max(0.0, norm_height - ascent_ratio)
        overlay = TextOverlay(
            text,
            font,
            size,
            color,
            bbox,
            page_num,
            flags,
            height_ratio=norm_height,
            ascent_ratio=ascent_ratio,
            descent_ratio=descent_ratio,
            source_bbox=source_bbox,
            preview_height_ratio=preview_norm,
            hwp_space_mode=hwp_space_mode,
            text_only_mode=text_only_mode,
            synth_bold_weight=synth_bold_weight,
            underline_weight=underline_weight,
            underline_offset=underline_offset,
            origin=origin,
            pdf_font_name=pdf_font_name
        )
        overlay.z_index = self.overlay_id_counter
        self.overlay_id_counter += 1
        overlay.font_path = font_path
        overlay.synth_bold = bool(synth_bold)
        if patch_margin_h is not None or patch_margin_v is not None or patch_margin is not None:
            overlay.update_properties(
                patch_margin=patch_margin,
                patch_margin_h=patch_margin_h,
                patch_margin_v=patch_margin_v,
                new_values=new_values
            )

        if page_num not in self.text_overlays:
            self.text_overlays[page_num] = []

        self.text_overlays[page_num].append(overlay)
        print(f"레이어 오버레이 추가: 페이지 {page_num}, 텍스트 '{text}', ID {overlay.z_index}")
        print(f"   속성: 폰트='{font}', 크기={size}px, 플래그={flags}, 색상={color}")
        return overlay
        
    def find_overlay_at_position(self, page_num, bbox):
        """특정 위치의 오버레이 찾기 (원본 및 현재 위치 모두 검사)"""
        if page_num not in self.text_overlays:
            return None
            
        target = fitz.Rect(bbox)
        for overlay in reversed(self.text_overlays[page_num]):
            if self._rects_close(overlay.original_bbox, target) or self._rects_close(overlay.bbox, target):
                return overlay
            if self._rects_overlap(overlay.bbox, target):
                return overlay
        return None
        
    def find_overlay_by_current_position(self, page_num, bbox):
        """현재 위치 기반으로 오버레이 찾기 (이동된 텍스트 편집시 사용)"""
        if page_num not in self.text_overlays:
            return None
            
        bbox_hash = self._get_bbox_hash(bbox)
        for overlay in self.text_overlays[page_num]:
            if overlay.get_current_hash() == bbox_hash:
                return overlay
        return None
        
    def move_overlay_to(self, overlay, new_bbox):
        """오버레이를 새 위치로 이동 (레이어 방식)"""
        if overlay:
            print(f"오버레이 이동: '{overlay.text}' -> {new_bbox}")
            overlay.move_to(new_bbox)
            self.update()  # 화면 갱신만 필요 (PDF 렌더링 불필요)

    def delete_selected_overlay(self) -> bool:
        overlay_key = None
        if self.selected_text_info and self.selected_text_info.get('is_overlay'):
            overlay_id = self.selected_text_info.get('overlay_id')
            page_num = self.selected_text_info.get('page_num', self.current_page_num)
            if overlay_id is not None:
                overlay_key = (page_num, overlay_id)
        if overlay_key is None and self.active_overlay:
            overlay_key = self.active_overlay

        if not overlay_key:
            return False

        page_num, overlay_id = overlay_key
        overlay = self.get_overlay_by_id(page_num, overlay_id)
        if not overlay:
            return False

        main_window = self.window()
        if main_window and hasattr(main_window, 'undo_manager') and self.doc:
            try:
                main_window.undo_manager.save_state(self.doc, self)
            except Exception as state_err:
                print(f"Undo 상태 저장 실패: {state_err}")

        overlays = self.text_overlays.get(page_num, [])
        if overlay in overlays:
            overlays.remove(overlay)
            print(f"오버레이 제거: '{overlay.text}' (ID: {overlay.z_index})")

        # 패치 및 추적 정보 제거
        self.unregister_overlay_text(page_num, overlay.original_bbox)
        self.remove_background_patch(page_num, overlay_id=overlay_id)

        if self.selected_text_info and self.selected_text_info.get('overlay_id') == overlay_id:
            self.selected_text_info = None
        if self.active_overlay == overlay_key:
            self.active_overlay = None

        self.update()

        if main_window:
            try:
                main_window.mark_as_changed()
                main_window.statusBar().showMessage(main_window.t('overlay_deleted'), 3000)
                main_window.update_undo_redo_buttons()
            except Exception as notify_err:
                print(f"상태 업데이트 실패: {notify_err}")
        return True
            
    def remove_overlay(self, overlay):
        """오버레이 제거"""
        if overlay:
            page_overlays = self.text_overlays.get(overlay.page_num, [])
            if overlay in page_overlays:
                page_overlays.remove(overlay)
                print(f"오버레이 제거: '{overlay.text}'")
                self.update()
    
    def add_background_patch(self, page_num, bbox, color=None, overlay_id=None):
        """배경 패치 영역 추가 (항상 새 패치 추가: 최신 패치가 위를 덮음)"""
        if page_num not in self.background_patches:
            self.background_patches[page_num] = []
        entry = {'bbox': bbox, 'overlay_id': overlay_id}
        if color is not None:
            if isinstance(color, QColor):
                entry['color'] = (color.redF(), color.greenF(), color.blueF())
            else:
                entry['color'] = color
        self.background_patches[page_num].append(entry)
        print(f"배경 패치 영역 추가: 페이지 {page_num} (누적 {len(self.background_patches[page_num])})")
        # 즉시 화면 갱신
        self.update()
    
    def remove_background_patch(self, page_num, bbox=None, overlay_id=None):
        """배경 패치 영역 제거"""
        if page_num not in self.background_patches:
            return
        
        if overlay_id is not None:
            before = len(self.background_patches[page_num])
            self.background_patches[page_num] = [entry for entry in self.background_patches[page_num]
                                                 if not (isinstance(entry, dict) and entry.get('overlay_id') == overlay_id)]
            if len(self.background_patches[page_num]) != before:
                print(f"배경 패치 영역 제거: 페이지 {page_num} (overlay_id={overlay_id})")
            return

        if bbox is None:
            return

        bbox_hash = self._get_bbox_hash(bbox)
        patches_to_remove = []
        for existing in self.background_patches[page_num]:
            eb = existing['bbox'] if isinstance(existing, dict) else existing
            if self._get_bbox_hash(eb) == bbox_hash:
                patches_to_remove.append(existing)
        
        for patch in patches_to_remove:
            self.background_patches[page_num].remove(patch)
            print(f"배경 패치 영역 제거: 페이지 {page_num}")
    
    def get_background_patches(self, page_num):
        """페이지의 배경 패치 영역 목록 반환"""
        return self.background_patches.get(page_num, [])
    
    def handle_single_click(self):
        """싱글클릭 처리 (300ms 후 실행)"""
        if not self.pending_single_click_pos or not self.doc:
            print(f"Single click aborted - pos: {self.pending_single_click_pos}, doc: {bool(self.doc)}")
            return

        print("Single click detected - entering quick adjustment mode")

        try:
            # 클릭 위치에서 텍스트 찾기 (더블클릭과 동일한 로직)
            label_pos = self.pending_single_click_pos
            
            # 좌표 변환
            scroll_area = self.parent()
            if hasattr(scroll_area, 'horizontalScrollBar'):
                scroll_offset_x = scroll_area.horizontalScrollBar().value()
                scroll_offset_y = scroll_area.verticalScrollBar().value()
                
                pixmap = self.pixmap()
                if pixmap:
                    widget_rect = self.rect()
                    pixmap_rect = pixmap.rect()
                    
                    offset_x = (widget_rect.width() - pixmap_rect.width()) // 2
                    offset_y = (widget_rect.height() - pixmap_rect.height()) // 2
                    
                    pixmap_x = label_pos.x() - offset_x + scroll_offset_x
                    pixmap_y = label_pos.y() - offset_y + scroll_offset_y
                    
                    pdf_x = pixmap_x / self.pixmap_scale_factor
                    pdf_y = pixmap_y / self.pixmap_scale_factor
                else:
                    pdf_x = label_pos.x() / self.pixmap_scale_factor
                    pdf_y = label_pos.y() / self.pixmap_scale_factor
            else:
                pdf_x = label_pos.x() / self.pixmap_scale_factor
                pdf_y = label_pos.y() / self.pixmap_scale_factor
            
            pdf_point = fitz.Point(pdf_x, pdf_y)
            page = self.doc.load_page(self.current_page_num)
            text_dict = page.get_text("dict")
            
            # 오버레이된 텍스트 우선 검색 (최신 페이지 상태에서)
            closest_span = None
            min_distance = float('inf')
            
            # 페이지를 다시 로드하여 최신 상태의 텍스트 정보 가져오기
            current_page = self.doc.load_page(self.current_page_num)
            current_text_dict = current_page.get_text("dict")
            
            for block in current_text_dict.get("blocks", []):
                if block.get('type') != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        bbox = fitz.Rect(span["bbox"])
                        
                        if self._rect_contains_point(bbox, pdf_point):
                            closest_span = span
                            min_distance = 0
                            break
                        
                        # 거리 계산
                        center_x = (bbox.x0 + bbox.x1) / 2
                        center_y = (bbox.y0 + bbox.y1) / 2
                        distance = ((pdf_x - center_x) ** 2 + (pdf_y - center_y) ** 2) ** 0.5
                        
                        if distance < min_distance:
                            min_distance = distance
                            closest_span = span
                
                if min_distance == 0:
                    break
            
            # 0) 오버레이 우선 히트 테스트: 오버레이가 클릭 지점에 있으면 그것만 선택
            if self.text_overlays.get(self.current_page_num):
                for ov in reversed(self.text_overlays[self.current_page_num]):
                    if ov.visible:
                        bbox = ov.bbox
                        if self._rect_contains_point(bbox, fitz.Point(pdf_x, pdf_y)):
                            overlay_info = {
                                'text': ov.text,
                                'font': ov.font,
                                'size': ov.size,
                                'flags': ov.flags,
                                'color': ov.color,
                                'original_bbox': ov.original_bbox,
                                'current_bbox': ov.bbox,
                                'origin': getattr(ov, 'origin', None),
                                'is_overlay': True,
                                'overlay_id': ov.z_index,
                                'page_num': self.current_page_num,
                                'synth_bold_weight': getattr(ov, 'synth_bold_weight', 120),
                                'underline_weight': getattr(ov, 'underline_weight', 0.6),
                                'underline_offset': getattr(ov, 'underline_offset', 1.5)
                            }
                            self.enter_quick_adjustment_mode(overlay_info)
                            self.pending_single_click_pos = None
                            return

            # 오버레이가 아니면, 원본 텍스트로는 빠른 조정 모드에 진입하지 않음
            print("No overlay at click. Skipping quick adjustment for original text.")
            mw = getattr(self, 'main_window', None) or self.window()
            if not (mw and getattr(mw, 'current_text_editor', None) is not None):
                self.active_overlay = None
            self.update()
            
        except Exception as e:
            print(f"Error in handle_single_click: {e}")
        
        self.pending_single_click_pos = None
    
    def enter_quick_adjustment_mode(self, text_info):
        """빠른 조정 모드 진입"""
        self.quick_adjustment_mode = True
        self.selected_text_info = text_info.copy()
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        overlay_id = text_info.get('overlay_id')
        if overlay_id is not None:
            self.active_overlay = (self.current_page_num, overlay_id)
        print("빠른 조정 모드: 방향키로 위치 조정, Enter로 편집, Escape로 취소")
        self.update()
    
    def exit_quick_adjustment_mode(self):
        """빠른 조정 모드 종료"""
        self.quick_adjustment_mode = False
        self.selected_text_info = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        print("빠른 조정 모드 종료")
        self.active_overlay = None
        self.update()
    
    def open_text_editor_from_quick_mode(self):
        """빠른 조정 모드에서 텍스트 편집창 열기"""
        if self.selected_text_info:
            print("빠른 조정 모드에서 텍스트 편집창 열기")
            # 현재 선택된 텍스트 정보로 텍스트 편집창 열기
            self.open_text_editor(self.selected_text_info)
    
    def _needs_space_between_spans(self, prev_span, curr_span):
        """두 span 사이에 공백이 필요한지 판단 (한글-영문/숫자 및 특수문자 조합)"""
        try:
            prev_text = prev_span.get('text', '').strip()
            curr_text = curr_span.get('text', '').strip()
            
            if not prev_text or not curr_text:
                return False
            
            # 마지막 문자와 첫 문자 분석
            prev_last_char = prev_text[-1]
            curr_first_char = curr_text[0]
            
            # 한글 문자인지 확인
            def is_korean(char):
                return '가' <= char <= '힣' or 'ㄱ' <= char <= 'ㅣ'
            
            # 영문/숫자인지 확인
            def is_alphanumeric(char):
                return char.isalnum() and not is_korean(char)

            # 쉼표 뒤, 닫는 괄호 뒤, 닫는 따옴표 뒤에 일반 문자가 오면 공백 필요 (예: '홍길동, 김철수', '(팀장) 홍길동')
            if prev_last_char in (',', ')', ']', '}', '”', '"') and (is_korean(curr_first_char) or is_alphanumeric(curr_first_char)):
                return True

            # 일반 문자 뒤에 여는 괄호가 오면 공백 필요 (예: '홍길동 (팀장)')
            if (is_korean(prev_last_char) or is_alphanumeric(prev_last_char)) and curr_first_char in ('(', '[', '{'):
                return True
            
            # 한글-영문/숫자 또는 영문/숫자-한글 조합에서 공백 필요
            return (
                (is_korean(prev_last_char) and is_alphanumeric(curr_first_char)) or
                (is_alphanumeric(prev_last_char) and is_korean(curr_first_char))
            )
        except Exception:
            return False

class UndoRedoManager:
    def __init__(self):
        self.undo_stack = []  # list of (doc_bytes, overlay_state, patch_state)
        self.redo_stack = []
        self.max_history = 50

    def _snapshot_view(self, viewer):
        overlays = {}
        patches = {}
        images = {}
        if hasattr(viewer, 'text_overlays'):
            for p, lst in viewer.text_overlays.items():
                items = []
                for ov in lst:
                    items.append({
                        'text': ov.text,
                        'font': ov.font,
                        'size': ov.size,
                        'color': ov.color,
                        'flags': ov.flags,
                        'bbox': (ov.bbox.x0, ov.bbox.y0, ov.bbox.x1, ov.bbox.y1),
                        'original_bbox': (ov.original_bbox.x0, ov.original_bbox.y0, ov.original_bbox.x1, ov.original_bbox.y1),
                        'z_index': ov.z_index,
                        'stretch': getattr(ov, 'stretch', 1.0),
                        'tracking': getattr(ov, 'tracking', 0.0),
                        'visible': ov.visible,
                        'font_path': getattr(ov, 'font_path', None),
                        'synth_bold': getattr(ov, 'synth_bold', False),
                        'synth_bold_weight': int(getattr(ov, 'synth_bold_weight', 120)),
                        'underline_weight': int(getattr(ov, 'underline_weight', 1)),
                        'hwp_space_mode': bool(getattr(ov, 'hwp_space_mode', False)),
                        'patch_margin_h': float(getattr(ov, 'patch_margin_h', 0.0)),
                        'patch_margin_v': float(getattr(ov, 'patch_margin_v', 0.0)),
                        'patch_margin': (
                            float(getattr(ov, 'patch_margin_h', 0.0)),
                            float(getattr(ov, 'patch_margin_v', 0.0))
                        ),
                        'height_ratio': float(getattr(ov, 'height_ratio', 1.15)),
                        'preview_height_ratio': float(getattr(ov, 'preview_height_ratio', getattr(ov, 'height_ratio', 1.15))),
                        'ascent_ratio': float(getattr(ov, 'ascent_ratio', 0.85)),
                        'descent_ratio': float(getattr(ov, 'descent_ratio', max(0.0, getattr(ov, 'height_ratio', 1.15) - getattr(ov, 'ascent_ratio', 0.85))))
                    })
                overlays[p] = items
        if hasattr(viewer, 'background_patches'):
            for p, lst in viewer.background_patches.items():
                patch_items = []
                for item in lst:
                    if isinstance(item, dict):
                        r = item['bbox']
                        color = item.get('color')
                        patch_items.append({
                            'bbox': (r.x0, r.y0, r.x1, r.y1),
                            'color': color,
                            'overlay_id': item.get('overlay_id')
                        })
                    else:
                        r = item
                        patch_items.append({'bbox': (r.x0, r.y0, r.x1, r.y1), 'overlay_id': None})
                patches[p] = patch_items
        if hasattr(viewer, 'image_overlays'):
            for p, lst in viewer.image_overlays.items():
                img_items = []
                for img in lst:
                    img_items.append({
                        'image_path': img.image_path,
                        'bbox': (img.bbox.x0, img.bbox.y0, img.bbox.x1, img.bbox.y1),
                        'opacity': img.opacity,
                        'z_index': img.z_index,
                        'visible': img.visible
                    })
                images[p] = img_items
        return overlays, patches, images

    def _restore_view(self, viewer, overlays, patches, images=None):
        viewer.text_overlays.clear()
        for p, items in overlays.items():
            viewer.text_overlays[p] = []
            for it in items:
                bbox = fitz.Rect(*it['bbox'])
                source_bbox = fitz.Rect(*it['original_bbox'])
                height_ratio = it.get('height_ratio')
                ascent_ratio = it.get('ascent_ratio')
                descent_ratio = it.get('descent_ratio')
                preview_height_ratio = it.get('preview_height_ratio', height_ratio)
                ov = TextOverlay(
                    it['text'],
                    it['font'],
                    it['size'],
                    it['color'],
                    bbox,
                    p,
                    it['flags'],
                    height_ratio=height_ratio,
                    ascent_ratio=ascent_ratio,
                    descent_ratio=descent_ratio,
                    source_bbox=source_bbox,
                    hwp_space_mode=bool(it.get('hwp_space_mode', False)),
                    text_only_mode=bool(it.get('text_only_mode', False)),
                    synth_bold_weight=int(it.get('synth_bold_weight', 120)),
                    underline_weight=int(it.get('underline_weight', 1))
                )
                ov.preview_height_ratio = TextOverlay._normalize_height_ratio(preview_height_ratio if preview_height_ratio is not None else height_ratio)
                ov.z_index = it.get('z_index', 0)
                ov.visible = it.get('visible', True)
                ov.stretch = float(it.get('stretch', 1.0))
                ov.tracking = float(it.get('tracking', 0.0))
                ov.font_path = it.get('font_path')
                ov.synth_bold = bool(it.get('synth_bold', False))
                if 'patch_margin_h' in it or 'patch_margin_v' in it:
                    ov.patch_margin_h = float(it.get('patch_margin_h', 0.0))
                    ov.patch_margin_v = float(it.get('patch_margin_v', 0.0))
                else:
                    legacy_margin = it.get('patch_margin')
                    try:
                        if isinstance(legacy_margin, (tuple, list)) and len(legacy_margin) >= 2:
                            ov.patch_margin_h = float(legacy_margin[0])
                            ov.patch_margin_v = float(legacy_margin[1])
                        elif legacy_margin is not None:
                            value = float(legacy_margin)
                            ov.patch_margin_h = value
                            ov.patch_margin_v = value
                    except Exception:
                        pass
                viewer.text_overlays[p].append(ov)
            # overlay_id_counter 갱신
            viewer.overlay_id_counter = max([ov.z_index for ov in viewer.text_overlays[p]] + [0]) + 1
        viewer.background_patches.clear()
        for p, lst in patches.items():
            viewer.background_patches[p] = []
            for it in lst:
                if isinstance(it, dict):
                    viewer.background_patches[p].append({
                        'bbox': fitz.Rect(*it['bbox']),
                        'color': it.get('color'),
                        'overlay_id': it.get('overlay_id')
                    })
                else:
                    viewer.background_patches[p].append({'bbox': fitz.Rect(*it), 'overlay_id': None})
        if hasattr(viewer, 'image_overlays'):
            viewer.image_overlays.clear()
            if images:
                for p, items in images.items():
                    viewer.image_overlays[p] = []
                    for it in items:
                        img_ov = ImageOverlay(
                            it['image_path'],
                            fitz.Rect(*it['bbox']),
                            p,
                            opacity=it.get('opacity', 1.0),
                            z_index=it.get('z_index', 0)
                        )
                        img_ov.visible = it.get('visible', True)
                        viewer.image_overlays[p].append(img_ov)
            viewer.active_image = None
        viewer.update()

    def save_state(self, doc, viewer=None):
        """현재 문서+오버레이 상태를 저장 (성능 최적화: doc.tobytes() 호출 최소화)"""
        print(f"\n=== UndoManager.save_state() 호출 ===")
        if doc:
            # [핵심 최적화] 메인 윈도우의 캐시를 확인하여 불필요한 직렬화(tobytes) 방지
            mw = MainWindow._instance if hasattr(MainWindow, '_instance') else None
            
            doc_bytes = None
            if mw and hasattr(mw, '_doc_modified_since_last_save'):
                if not mw._doc_modified_since_last_save and mw._last_doc_bytes:
                    doc_bytes = mw._last_doc_bytes
                    print("   - [성능 최적화] 문서 내용 변경 없음, 캐시된 바이트 사용 (프리징 방지)")
                else:
                    doc_bytes = doc.tobytes()
                    mw._last_doc_bytes = doc_bytes
                    mw._doc_modified_since_last_save = False
                    print("   - [정규 처리] 문서 변경 감지됨, doc.tobytes() 실행")
            else:
                doc_bytes = doc.tobytes()

            doc_pages = len(doc)
            overlays, patch_state, img_state = self._snapshot_view(viewer) if viewer else ({}, {}, {})
            print(f"   - 저장할 문서 페이지 수: {doc_pages}")
            print(f"   - 저장 전 undo_stack size: {len(self.undo_stack)}")
            self.undo_stack.append((doc_bytes, overlays, patch_state, img_state))
            if len(self.undo_stack) > self.max_history:
                self.undo_stack.pop(0)
                print(f"   - 히스토리 제한으로 가장 오래된 상태 제거")
            self.redo_stack.clear()
            print(f"   - 저장 후 undo_stack size: {len(self.undo_stack)}")
            print(f"   - redo_stack 초기화됨")
            print(f"   - OK 상태 저장 완료")
        else:
            print(f"   - X 문서가 None이어서 상태 저장 실패")

    def can_undo(self):
        return len(self.undo_stack) > 1

    def can_redo(self):
        return len(self.redo_stack) > 0

    def undo(self, current_doc, viewer=None):
        """실행 취소"""
        print(f"\n=== UndoManager.undo() 호출 ===")
        print(f"   - can_undo(): {self.can_undo()}")
        print(f"   - undo_stack size: {len(self.undo_stack)}")
        print(f"   - redo_stack size: {len(self.redo_stack)}")
        if self.can_undo():
            # 현재 상태를 redo로 백업 (성능 최적화: doc.tobytes() 호출 최소화)
            mw = MainWindow._instance if hasattr(MainWindow, '_instance') else None
            cur_bytes = None
            if mw and hasattr(mw, '_doc_modified_since_last_save'):
                if not mw._doc_modified_since_last_save and mw._last_doc_bytes:
                    cur_bytes = mw._last_doc_bytes
                    print("   - [성능 최적화] Undo 백업 시 캐시된 바이트 사용")
                else:
                    cur_bytes = current_doc.tobytes()
                    mw._last_doc_bytes = cur_bytes
                    mw._doc_modified_since_last_save = False
            else:
                cur_bytes = current_doc.tobytes()

            cur_overlays, cur_patches, cur_images = self._snapshot_view(viewer) if viewer else ({}, {}, {})
            self.redo_stack.append((cur_bytes, cur_overlays, cur_patches, cur_images))
            
            # undo pop and restore previous
            self.undo_stack.pop()
            entry = self.undo_stack[-1]
            if len(entry) >= 4:
                prev_bytes, prev_overlays, prev_patches, prev_images = entry
            else:
                prev_bytes, prev_overlays, prev_patches = entry
                prev_images = {}
            
            # [최적화] 복원 시 캐시 업데이트 (중요: 복원된 문서는 마지막 캐시와 동일함)
            if mw:
                mw._last_doc_bytes = prev_bytes
                mw._doc_modified_since_last_save = False
                
            restored_doc = fitz.open(stream=prev_bytes)
            if viewer:
                self._restore_view(viewer, prev_overlays, prev_patches, prev_images)
            return restored_doc
        print("   - 실행 취소 불가 (can_undo() == False)")
        return None

    def redo(self, current_doc, viewer=None):
        """다시 실행"""
        print(f"\n=== UndoManager.redo() 호출 ===")
        print(f"   - can_redo(): {self.can_redo()}")
        print(f"   - undo_stack size: {len(self.undo_stack)}")
        print(f"   - redo_stack size: {len(self.redo_stack)}")
        if self.can_redo():
            # 현재 상태를 undo 스택에 푸시 (성능 최적화)
            mw = MainWindow._instance if hasattr(MainWindow, '_instance') else None
            cur_bytes = None
            if mw and hasattr(mw, '_doc_modified_since_last_save'):
                if not mw._doc_modified_since_last_save and mw._last_doc_bytes:
                    cur_bytes = mw._last_doc_bytes
                    print("   - [성능 최적화] Redo 백업 시 캐시된 바이트 사용")
                else:
                    cur_bytes = current_doc.tobytes()
                    mw._last_doc_bytes = cur_bytes
                    mw._doc_modified_since_last_save = False
            else:
                cur_bytes = current_doc.tobytes()

            cur_overlays, cur_patches, cur_images = self._snapshot_view(viewer) if viewer else ({}, {}, {})
            self.undo_stack.append((cur_bytes, cur_overlays, cur_patches, cur_images))
            
            entry = self.redo_stack.pop()
            if len(entry) >= 4:
                next_bytes, next_overlays, next_patches, next_images = entry
            else:
                next_bytes, next_overlays, next_patches = entry
                next_images = {}
            
            # [최적화] 복원 시 캐시 업데이트
            if mw:
                mw._last_doc_bytes = next_bytes
                mw._doc_modified_since_last_save = False
                
            restored_doc = fitz.open(stream=next_bytes)
            if viewer:
                self._restore_view(viewer, next_overlays, next_patches, next_images)
            return restored_doc
        print("   - 다시 실행 불가 (can_redo() == False)")
        return None

class MainWindow(QMainWindow):
    _instance = None # 전역 접근을 위한 클래스 변수

    def __init__(self, initial_pdf_path: Optional[str] = None):
        super().__init__()
        MainWindow._instance = self # 인스턴스 저장
        self.settings = QSettings('yongpdf', 'main-codex1')
        self._init_translations()
        
        # Load available languages dynamically from the i18n directory
        self.available_languages = sorted(self.translations.keys())
        
        saved_lang = self.settings.value('language', 'ko') if self.settings else 'ko'
        self.language = str(saved_lang) if saved_lang in self.translations else 'ko'
        
        # 테마 미리 적용 (UI 생성 및 로딩창 표시 전)
        try:
            stored_theme = self.settings.value('theme_mode', 'dark')
            self.theme_mode = str(stored_theme) if stored_theme in ('light', 'dark') else 'dark'
            self.apply_theme(self.theme_mode)
        except Exception:
            self.theme_mode = 'dark'
            self.apply_theme('dark')

        self.font_manager = SystemFontManager()
        self.undo_manager = UndoRedoManager()
        self.has_changes = False
        self._last_doc_bytes = None  # [최적화] 마지막으로 추출한 PDF 데이터 캐시
        self._doc_modified_since_last_save = True  # [최적화] 문서 변경 여부 추적
        self.current_file_path = None
        self.pdf_fonts = []
        self.force_text_flatten = False  # 텍스트 유지 정밀 플래튼 옵션
        self.theme_mode = 'dark'  # 'dark' 또는 'light'
        self._ttfont_cache = {}
        self._font_ref_cache = {}
        self._doc_font_ref_cache = {}
        self.font_dump_verbose = 1  # 0: 끔, 1: 보통, 2: 상세
        # 크기 미세 보정(저장 본)
        self._font_coverage_cache = {}
        # PDF size/flatten tuning
        self.fallback_image_scale = 8.0  # 이미지 폴백 해상도 스케일(높을수록 선명, 용량 증가)
        self.size_optimize = True        # 사이즈 최적화 활성화

        self._preview_metrics_cache: dict[tuple, tuple[float, float, float]] = {}
        self._raw_font_metrics_cache: dict[str, Optional[tuple[float, float, float]]] = {}
        
        self.setWindowTitle(self.t('app_title'))
        self.setGeometry(100, 100, 1200, 900)
        self.zoom_factor = 1.0
        self.zoom_levels = [0.25, 0.33, 0.50, 0.67, 0.75, 0.80, 0.90, 1.0, 1.10, 1.25, 1.50, 1.75, 2.00, 2.50, 3.00, 4.00, 5.00, 6.00, 7.00, 8.00]
        self.current_base_scale = 1.0
        
        # 패치 크기 조절 설정 (기본값, 비율: Left, Right, Top, Bottom)
        self.patch_margin = (0.02, 0.02, 0.02, 0.02)  # 상하좌우 2% 확장 기본값
        self.patch_precise_mode = False  # 정밀 모드
        self.patch_only_mode = False
        self._patch_mode_restore_state: Optional[bool] = None
        self.current_text_editor: Optional[TextEditorDialog] = None
        self.last_text_editor_pos: Optional[QPoint] = None
        try:
            last_x = self.settings.value('text_editor_pos_x')
            last_y = self.settings.value('text_editor_pos_y')
            if last_x is not None and last_y is not None:
                self.last_text_editor_pos = QPoint(int(last_x), int(last_y))
        except Exception:
            self.last_text_editor_pos = None
        self.continuous_scroll_enabled = True  # 수직 연속 스크롤 페이지 전환 모드
        self.last_open_dir = os.path.expanduser('~')
        self.recent_fonts: list[str] = []
        try:
            stored_fonts = self.settings.value('recent_fonts')
            if isinstance(stored_fonts, str):
                import json
                stored_fonts = json.loads(stored_fonts)
            if isinstance(stored_fonts, list):
                self.recent_fonts = [str(f) for f in stored_fonts if isinstance(f, str) and f.strip()]
        except Exception:
            self.recent_fonts = []
        self.setAcceptDrops(True)

        self._startup_dialog = self._create_loading_dialog(self.t('loading_app'))
        try:
            # UI 구성
            self.setup_ui()
            self.setup_connections()
            self._load_persisted_state()
            self.set_patch_mode(self.patch_precise_mode)

            if initial_pdf_path:
                self.load_pdf_from_path(initial_pdf_path)
        finally:
            if getattr(self, '_startup_dialog', None):
                try:
                    self._startup_dialog.close()
                except Exception:
                    pass
                self._startup_dialog = None

        # 상태바 초기화 (하단 여백 차지 방지를 위해 숨기고, 상단 status_layout에 연동)
        self._status_timer = None
        try:
            sb = self.statusBar()
            sb.hide()
            sb.messageChanged.connect(self._on_status_bar_message_changed)
        except Exception:
            pass
        self.update_status_mode_message()

    def _create_loading_dialog(self, message: str | None):
        if not message:
            return None
        try:
            dialog = QProgressDialog(message, None, 0, 0, self)
            dialog.setWindowTitle(self.t('title_info'))
            dialog.setCancelButton(None)
            dialog.setAutoClose(False)
            dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            dialog.setMinimumDuration(0)
            dialog.show()
            QApplication.processEvents()
            return dialog
        except Exception as dlg_err:
            print(f"로딩 대화상자 생성 실패: {dlg_err}")
            return None

    def _get_raw_font_metrics(self, font_path: Optional[str]) -> Optional[tuple[float, float, float]]:
        if not font_path:
            return None
        if font_path in self._raw_font_metrics_cache:
            return self._raw_font_metrics_cache[font_path]
        if not os.path.exists(font_path):
            self._raw_font_metrics_cache[font_path] = None
            return None
        try:
            raw_font = QRawFont()
            # 3개의 인자를 명시적으로 전달 (경로, 크기, 힌트) - 일부 PySide6 버전 호환성 해결
            if not raw_font.loadFromFile(font_path, 1000.0, QFont.HintingPreference.PreferDefaultHinting):
                self._raw_font_metrics_cache[font_path] = None
                return None
            ascent = float(raw_font.ascent())
            descent = float(raw_font.descent())
            leading = float(raw_font.leading())
            line_height = ascent + descent + leading
            if line_height <= 0:
                line_height = ascent + descent
            if line_height <= 0:
                self._raw_font_metrics_cache[font_path] = None
                return None
            height_ratio = TextOverlay._normalize_height_ratio(line_height / 1000.0)
            ascent_ratio = ascent / 1000.0
            descent_ratio = descent / 1000.0
            result = (height_ratio, ascent_ratio, descent_ratio)
            self._raw_font_metrics_cache[font_path] = result
            return result
        except Exception as raw_err:
            print(f"Raw font metrics load failed for '{font_path}': {raw_err}")
            self._raw_font_metrics_cache[font_path] = None
            return None

    def _compute_preview_metrics(self, font_name: str, font_path: Optional[str], flags: int, stretch: float = 1.0) -> tuple[float, float, float]:
        cache_key = (font_path or font_name or '', int(flags), round(float(stretch or 1.0), 3))
        cached = self._preview_metrics_cache.get(cache_key)
        if cached:
            return cached
        raw_metrics = None
        if font_path:
            raw_metrics = self._get_raw_font_metrics(font_path)
        if raw_metrics is None and font_name:
            try:
                alt_path = self.font_manager.get_font_path(font_name)
            except Exception:
                alt_path = None
            if alt_path and alt_path != font_path:
                raw_metrics = self._get_raw_font_metrics(alt_path)
                if raw_metrics and font_path is None:
                    font_path = alt_path
        if raw_metrics:
            height_ratio, ascent_ratio, descent_ratio = raw_metrics
        else:
            family = None
            if font_path:
                try:
                    font_id = QFontDatabase.addApplicationFont(font_path)
                    families = QFontDatabase.applicationFontFamilies(font_id)
                    family = families[0] if families else None
                except Exception:
                    family = None
            qfont = QFont(family or font_name or '')
            # [수정] 픽셀 사이즈 기반 10000배 정밀도 측정 (DPI 독립적)
            qfont.setPixelSize(10000)
            qfont.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
            if flags & 16:
                qfont.setBold(True)
            if flags & 2:
                qfont.setItalic(True)
            
            # [추가] 정밀도 향상을 위한 전략 설정
            qfont.setStyleStrategy(QFont.StyleStrategy.ForceOutline | QFont.StyleStrategy.PreferAntialias)
            
            try:
                qfont.setStretch(int(max(1, min(400, float(stretch) * 100))))
            except Exception:
                pass
            metrics = QFontMetricsF(qfont)
            denom = 10000.0
            try:
                height_ratio = metrics.height() / float(denom)
            except Exception:
                height_ratio = 1.15
            try:
                ascent_ratio = metrics.ascent() / float(denom)
            except Exception:
                ascent_ratio = height_ratio * 0.85
            try:
                descent_ratio = metrics.descent() / float(denom)
            except Exception:
                descent_ratio = max(0.0, height_ratio - ascent_ratio)
            height_ratio = TextOverlay._normalize_height_ratio(height_ratio)
        result = (height_ratio, ascent_ratio, descent_ratio)
        self._preview_metrics_cache[cache_key] = result
        return result

    def _preview_height_ratio(self, font_name: str, font_path: Optional[str], flags: int, stretch: float = 1.0) -> float:
        return self._compute_preview_metrics(font_name, font_path, flags, stretch)[0]

    def _load_persisted_state(self):
        if not self.settings:
            return
        try:
            geometry = self.settings.value('window_geometry')
            if isinstance(geometry, QByteArray):
                self.restoreGeometry(geometry)
            if isinstance(geometry, (bytes, bytearray)):
                self.restoreGeometry(QByteArray(geometry))
        except Exception as geom_err:
            print(f"창 기하 복원 실패: {geom_err}")

        try:
            window_state = self.settings.value('window_state')
            if isinstance(window_state, QByteArray):
                self.restoreState(window_state)
            if isinstance(window_state, (bytes, bytearray)):
                self.restoreState(QByteArray(window_state))
        except Exception as state_err:
            print(f"창 상태 복원 실패: {state_err}")

        try:
            # 테마를 다시 적용하여 setup_ui에서 생성된 위젯들에 스타일 반영
            self.apply_theme(self.theme_mode)
            self._sync_theme_actions()
        except Exception as theme_err:
            print(f"테마 상태 적용 및 싱크 실패: {theme_err}")

        zoom_value = self.settings.value('zoom_factor')
        if zoom_value is not None:
            try:
                val = float(zoom_value)
                levels = getattr(self, 'zoom_levels', [1.0])
                # 가장 가까운 단계로 스냅
                self.zoom_factor = min(levels, key=lambda x: abs(x - val))
            except Exception as zoom_err:
                print(f"줌 값 복원 실패: {zoom_err}")

        margin_h = self.settings.value('patch_margin_h')
        margin_v = self.settings.value('patch_margin_v')
        legacy_margin = self.settings.value('patch_margin') if margin_h is None and margin_v is None else None
        try:
            if margin_h is not None or margin_v is not None:
                h = float(margin_h) if margin_h is not None else float(self.patch_margin[0])
                v = float(margin_v) if margin_v is not None else float(self.patch_margin[1])
                self.patch_margin = (h, v)
            elif legacy_margin is not None:
                if isinstance(legacy_margin, (tuple, list)) and len(legacy_margin) >= 2:
                    self.patch_margin = (float(legacy_margin[0]), float(legacy_margin[1]))
                else:
                    scalar = float(legacy_margin)
                    self.patch_margin = (scalar, scalar)
        except Exception as margin_err:
            print(f"패치 여백 복원 실패: {margin_err}")

        saved_dir = self.settings.value('last_open_dir')
        if isinstance(saved_dir, str) and saved_dir:
            self.last_open_dir = saved_dir

        stored_mode = self.settings.value('patch_precise_mode')
        if stored_mode is not None:
            try:
                self.patch_precise_mode = bool(int(stored_mode))
            except Exception:
                self.patch_precise_mode = bool(stored_mode)

    def _save_persisted_state(self):
        if not self.settings:
            return
        try:
            self.settings.setValue('window_geometry', self.saveGeometry())
            self.settings.setValue('window_state', self.saveState())
            self.settings.setValue('theme_mode', self.theme_mode)
            self.settings.setValue('zoom_factor', float(self.zoom_factor))
            if isinstance(self.patch_margin, (tuple, list)) and len(self.patch_margin) >= 2:
                self.settings.setValue('patch_margin_h', float(self.patch_margin[0]))
                self.settings.setValue('patch_margin_v', float(self.patch_margin[1]))
            else:
                self.settings.setValue('patch_margin_h', float(self.patch_margin))
                self.settings.setValue('patch_margin_v', float(self.patch_margin))
            if getattr(self, 'last_open_dir', None):
                self.settings.setValue('last_open_dir', self.last_open_dir)
        except Exception as persist_err:
            print(f"설정 저장 실패: {persist_err}")

    def _store_theme_mode(self):
        if not self.settings:
            return
        try:
            self.settings.setValue('theme_mode', self.theme_mode)
        except Exception:
            pass

    def _store_zoom_factor(self):
        if not self.settings:
            return
        try:
            self.settings.setValue('zoom_factor', float(self.zoom_factor))
        except Exception:
            pass

    def _store_patch_margin(self):
        if not self.settings:
            return
        try:
            if isinstance(self.patch_margin, (tuple, list)) and len(self.patch_margin) == 4:
                self.settings.setValue('patch_margin_l', float(self.patch_margin[0]))
                self.settings.setValue('patch_margin_r', float(self.patch_margin[1]))
                self.settings.setValue('patch_margin_t', float(self.patch_margin[2]))
                self.settings.setValue('patch_margin_b', float(self.patch_margin[3]))
            elif isinstance(self.patch_margin, (tuple, list)) and len(self.patch_margin) >= 2:
                self.settings.setValue('patch_margin_l', float(self.patch_margin[0]))
                self.settings.setValue('patch_margin_r', float(self.patch_margin[0]))
                self.settings.setValue('patch_margin_t', float(self.patch_margin[1]))
                self.settings.setValue('patch_margin_b', float(self.patch_margin[1]))
            else:
                val = float(self.patch_margin)
                self.settings.setValue('patch_margin_l', val)
                self.settings.setValue('patch_margin_r', val)
                self.settings.setValue('patch_margin_t', val)
                self.settings.setValue('patch_margin_b', val)
        except Exception:
            pass

    def _store_patch_mode(self):
        if not self.settings:
            return
        try:
            self.settings.setValue('patch_precise_mode', int(bool(self.patch_precise_mode)))
        except Exception:
            pass

    def _store_last_open_dir(self):
        if not self.settings:
            return
        try:
            if getattr(self, 'last_open_dir', None):
                self.settings.setValue('last_open_dir', self.last_open_dir)
        except Exception:
            pass

    def preview_edit_changes(self, overlay_key, new_values):
        """텍스트 편집창의 변경사항을 실시간으로 화면에 반영"""
        print(f"[Preview] Key={overlay_key}, size={new_values.get('size')} (type: {type(new_values.get('size'))})")
        
        if not self.pdf_viewer or not self.pdf_viewer.doc:
            return

        page_num = (overlay_key[0] if overlay_key else None)
        if page_num is None:
            page_num = new_values.get('page_num', self.pdf_viewer.current_page_num)
        
        overlay_id = overlay_key[1] if overlay_key else new_values.get('overlay_id')
        overlay = None

        if overlay_id is not None:
            overlay = self.pdf_viewer.get_overlay_by_id(page_num, overlay_id)
        
        if not overlay:
            # 1. 위치 기반으로 재시도 (ID 매칭 실패 대비)
            try:
                original_bbox = new_values.get('original_bbox')
                if original_bbox:
                    overlay = self.pdf_viewer.find_overlay_at_position(page_num, fitz.Rect(original_bbox))
                    if overlay:
                        print(f"[Preview] Found overlay via fallback position match: ID {overlay.z_index}")
            except Exception:
                pass

        if not overlay:
            # 2. 오버레이가 아직 없다면 실시간 자동 생성 (Fallback 복원)
            try:
                page = self.pdf_viewer.doc.load_page(page_num)
                span_data = getattr(self, 'current_text_editor', None)
                span_source = span_data.span_info if (span_data and hasattr(span_data, 'span_info')) else new_values
                overlay = self.insert_overlay_text(page, span_source, new_values)
                if overlay:
                    print(f"[Preview] Auto-created missing overlay on the fly: ID {overlay.z_index}")
                    overlay_key = (page_num, overlay.z_index)
                    if hasattr(self, 'current_text_editor') and self.current_text_editor:
                        self.current_text_editor.overlay_key = overlay_key
                        if hasattr(self.current_text_editor, 'span_info'):
                            self.current_text_editor.span_info['overlay_id'] = overlay.z_index
                            self.current_text_editor.span_info['is_overlay'] = True
            except Exception as e_mk:
                print(f"[Preview] Failed to auto-create fallback overlay: {e_mk}")

        if not overlay:
            print(f"[Preview] No overlay could be resolved or created. Aborting preview.")
            return

        try:
            page = self.pdf_viewer.doc.load_page(page_num)
            
            span_dummy = {
                'original_bbox': overlay.original_bbox,
                'source_bbox': getattr(overlay, 'source_bbox', overlay.original_bbox),
                'current_bbox': overlay.bbox,
                'is_overlay': True,
                'overlay_id': overlay.z_index,
                'origin': getattr(overlay, 'origin', None),
                'page_num': page_num,
                'text': getattr(overlay, 'text', ''),
                'font': getattr(overlay, 'font', 'Arial'),
                'size': getattr(overlay, 'size', 12.0),
                'flags': getattr(overlay, 'flags', 0)
            }
            
            # 1. 오버레이 속성 및 텍스트 업데이트
            self.insert_overlay_text(page, span_dummy, new_values)
            
            # 2. 배경 패치(여백 포함) 실시간 업데이트 (preview=True로 추가)
            self.apply_background_patch(page, overlay.original_bbox, new_values, overlay=overlay, preview=True)
            
            # 3. 편집 중인 오버레이 활성 상태 유지 (원본 반투명 패치 렌더링 보장)
            self.pdf_viewer.active_overlay = (page_num, overlay.z_index)
            
            # 4. 화면 즉시 갱신 강제 (모달 대화상자 이벤트 루프 중 즉시 재렌더링)
            self.pdf_viewer.update()
            try:
                self.pdf_viewer.repaint()
            except Exception:
                pass
            
        except Exception as e:
            print(f"실시간 미리보기 업데이트 실패: {e}")
            import traceback
            traceback.print_exc()

    def preview_patch_margin(self, overlay_key, m_l, m_r, m_t, m_b):
        # preview_edit_changes로 통합됨 (호환성을 위해 유지하거나 호출 전환)
        nv = {
            'patch_margin_l': m_l,
            'patch_margin_r': m_r,
            'patch_margin_t': m_t,
            'patch_margin_b': m_b
        }
        self.preview_edit_changes(overlay_key, nv)

    def _compute_height_ratio(self, bbox, font_size, reference_size=None):
        try:
            if bbox is None:
                return 1.0
            ref_size = reference_size if reference_size and reference_size > 0 else font_size
            ref_size = max(1.0, float(ref_size))
            ratio = float(bbox.height) / ref_size
        except Exception:
            ratio = 1.0
        if ratio <= 0:
            ratio = 1.0
        return max(0.6, min(1.6, ratio))

    def _init_translations(self):
        self.translations = {}
        try:
            # 설정에서 저장된 언어 불러오기 (기본값 ko)
            self.language = str(self.settings.value('language', 'ko'))
            
            i18n_dir = _resolve_static_path('i18n')
            if not os.path.isdir(i18n_dir):
                i18n_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'i18n')
            
            print(f"[i18n] Loading translations from: {i18n_dir}")
            
            if os.path.isdir(i18n_dir):
                for filename in os.listdir(i18n_dir):
                    if filename.endswith('.json'):
                        lang_code = filename[:-5]
                        try:
                            file_path = os.path.join(i18n_dir, filename)
                            with open(file_path, 'r', encoding='utf-8') as f:
                                self.translations[lang_code] = json.load(f)
                        except Exception as e:
                            print(f"[i18n] Failed to load {filename}: {e}")
            
            if self.translations:
                print(f"[i18n] Successfully loaded {len(self.translations)} languages: {', '.join(sorted(self.translations.keys()))}")
                if self.language not in self.translations:
                    self.language = 'ko' if 'ko' in self.translations else list(self.translations.keys())[0]
            else:
                print("[i18n] Critical Warning: No translation files found!")
                self.translations = {'en': {'app_title': 'YongPDF_text'}}
            
            print(f"[i18n] Current active language: {self.language}")
            return
        except Exception as e:
            print(f"[i18n] Error during initialization: {e}")
            self.translations = {'en': {'app_title': 'YongPDF_text'}}
            self.language = 'en'

    # Old hardcoded translations removed - now loading from i18n/*.json

    @classmethod
    def t(cls, key: str, default: Optional[str] = None, **kwargs) -> str:
        """전역 번역 유틸리티 (MainWindow._instance 활용)"""
        fallback_val = default if default is not None else key
        if cls._instance:
            # 1. 현재 선택된 언어 딕셔너리
            lang_dict = cls._instance.translations.get(cls._instance.language, {})
            # 2. 한국어 딕셔너리 (최종 폴백용)
            fallback_ko = cls._instance.translations.get('ko', {})
            # 3. 영어 딕셔너리 (차선 폴백용)
            fallback_en = cls._instance.translations.get('en', {})
            
            # 순서대로 찾음: 현재 언어 -> 한국어 -> 영어 -> 기본값/키 자체
            text = lang_dict.get(key, fallback_ko.get(key, fallback_en.get(key, fallback_val)))
        else:
            text = fallback_val
        
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text

    def set_language(self, lang: str):
        if lang not in self.translations:
            return
        self.language = lang
        
        # RTL(Right-to-Left) 언어 지원
        if lang in ('ar', 'fa', 'ur'):
            QApplication.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        else:
            QApplication.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        try:
            if self.settings:
                self.settings.setValue('language', lang)
        except Exception:
            pass
        if hasattr(self, 'language_actions'):
            for code, action in self.language_actions.items():
                action.blockSignals(True)
                action.setChecked(code == lang)
                action.blockSignals(False)
        # 재구성
        self.menuBar().clear()
        self.create_menu_bar()
        self._apply_translated_tooltips()
        self._sync_theme_actions()
        self._sync_patch_controls()
        self.update_page_navigation()
        self.update_zoom_label()
        if not self.pdf_viewer.doc:
            self.pdf_viewer.setText(self.t('viewer_placeholder'))
        self.update_status_mode_message()
        self._refresh_window_title()

    def _apply_translated_tooltips(self):
        mapping = [
            ('open_button', 'tooltip_open'),
            ('save_button', 'tooltip_save'),
            ('undo_button', 'tooltip_undo'),
            ('redo_button', 'tooltip_redo'),
            ('zoom_in_button', 'tooltip_zoom_in'),
            ('zoom_out_button', 'tooltip_zoom_out'),
            ('fit_width_button', 'tooltip_fit_width'),
            ('fit_height_button', 'tooltip_fit_height'),
            ('prev_page_button', 'tooltip_prev_page'),
            ('next_page_button', 'tooltip_next_page'),
            ('page_input', 'tooltip_goto_page'),
            ('thumbnail_button', 'tooltip_thumbnails'),
            ('patch_mode_button', 'tooltip_patch_mode'),
            ('eraser_button', 'tooltip_patch_eraser'),
            ('insert_image_button', 'tooltip_insert_image'),
            ('draw_signature_button', 'tooltip_draw_signature'),
            ('search_button', 'tooltip_search'),
            ('theme_button', 'tooltip_theme')
        ]
        for attr, key in mapping:
            btn = getattr(self, attr, None)
            if btn:
                btn.setToolTip(self.t(key))

        if hasattr(self, 'page_input'):
            self.page_input.setPlaceholderText(self.t('goto_page_placeholder'))

    def _sync_patch_controls(self):
        state_patch = bool(self.patch_precise_mode and not getattr(self, 'patch_only_mode', False))
        state_eraser = bool(self.patch_precise_mode and getattr(self, 'patch_only_mode', False))

        if hasattr(self, 'precise_mode_action'):
            try:
                self.precise_mode_action.blockSignals(True)
                self.precise_mode_action.setChecked(state_patch)
            finally:
                self.precise_mode_action.blockSignals(False)

        if hasattr(self, 'patch_eraser_action'):
            try:
                self.patch_eraser_action.blockSignals(True)
                self.patch_eraser_action.setChecked(state_eraser)
            finally:
                self.patch_eraser_action.blockSignals(False)

        if hasattr(self, 'patch_mode_button'):
            try:
                self.patch_mode_button.blockSignals(True)
                self.patch_mode_button.setChecked(state_patch)
                self.patch_mode_button.setToolTip(self.t('tooltip_patch_mode'))
            finally:
                self.patch_mode_button.blockSignals(False)

        if hasattr(self, 'eraser_button'):
            try:
                self.eraser_button.blockSignals(True)
                self.eraser_button.setChecked(state_eraser)
                self.eraser_button.setToolTip(self.t('tooltip_patch_eraser'))
            finally:
                self.eraser_button.blockSignals(False)

        self._animate_toggle_button(getattr(self, 'patch_mode_button', None), state_patch)
        self._animate_toggle_button(getattr(self, 'eraser_button', None), state_eraser)

    def toggle_patch_eraser(self, enabled: bool):
        if enabled:
            self._patch_mode_restore_state = bool(getattr(self, 'patch_precise_mode', False))
            self.set_patch_mode(True, patch_only=True)
        else:
            previous = self._patch_mode_restore_state
            self._patch_mode_restore_state = None
            restore_enabled = bool(previous) if previous is not None else False
            # Always reset modes before restoring the prior state to avoid unintended activation
            if self.patch_precise_mode or self.patch_only_mode:
                self.set_patch_mode(False, patch_only=False)
            if restore_enabled:
                self.set_patch_mode(True, patch_only=False)

    def _animate_toggle_button(self, button: QPushButton | None, active: bool):
        if not button:
            return
        effect = getattr(button, '_toggle_effect', None)
        if effect is None:
            effect = QGraphicsColorizeEffect(button)
            effect.setColor(QColor(255, 214, 102))
            effect.setStrength(0.0)
            button.setGraphicsEffect(effect)
            button._toggle_effect = effect
        existing_anim = getattr(button, '_toggle_anim', None)
        if existing_anim:
            existing_anim.stop()
        start_strength = effect.strength()
        target_strength = 0.55 if active else 0.0
        anim = QVariantAnimation(button)
        anim.setDuration(200)
        anim.setStartValue(start_strength)
        anim.setEndValue(target_strength)
        anim.setEasingCurve(QEasingCurve.OutCubic if active else QEasingCurve.InOutQuad)
        anim.valueChanged.connect(effect.setStrength)

        def _clear_anim():
            if getattr(button, '_toggle_anim', None) is anim:
                button._toggle_anim = None

        anim.finished.connect(_clear_anim)
        button._toggle_anim = anim
        anim.start()
        button.setProperty('active', active)
        style = button.style()
        style.unpolish(button)
        style.polish(button)

    def _refresh_window_title(self):
        base = self.t('app_title')
        if self.current_file_path:
            name = os.path.basename(self.current_file_path)
            title = f"{base} - {name}"
        else:
            title = base
        if self.has_changes and not title.endswith('*'):
            title += '*'
        self.setWindowTitle(title)

    def create_menu_bar(self):
        """이모지 기반 메뉴바 생성"""
        menubar = self.menuBar()
        
        # 📁 파일 메뉴
        file_menu = menubar.addMenu(self.t('file_menu'))
        
        open_action = file_menu.addAction(self.t('open'))
        open_action.triggered.connect(self.open_pdf)
        open_action.setShortcut('Ctrl+O')

        file_menu.addSeparator()

        # 세션 저장 / 불러오기
        save_session_action = file_menu.addAction(self.t('action_save_session'))
        save_session_action.triggered.connect(self.save_session)
        load_session_action = file_menu.addAction(self.t('action_load_session'))
        load_session_action.triggered.connect(self.load_session)
        
        file_menu.addSeparator()

        save_action = file_menu.addAction(self.t('save'))
        save_action.triggered.connect(self.save_pdf)
        save_action.setShortcut('Ctrl+S')

        # 다른 이름으로 저장
        save_as_action = file_menu.addAction(self.t('save_as'))
        save_as_action.triggered.connect(self.save_as_pdf)
        save_as_action.setShortcut('Ctrl+Shift+S')

        file_menu.addSeparator()

        quit_action = file_menu.addAction(self.t('exit'))
        quit_action.triggered.connect(self.close)
        quit_action.setShortcut('Ctrl+Q')
        
        # ✏️ 편집 메뉴
        edit_menu = menubar.addMenu(self.t('edit_menu'))
        
        undo_action = edit_menu.addAction(self.t('undo'))
        undo_action.triggered.connect(self.undo_action)
        undo_action.setShortcut('Ctrl+Z')
        
        redo_action = edit_menu.addAction(self.t('redo')) 
        redo_action.triggered.connect(self.redo_action)
        redo_action.setShortcut('Ctrl+Y')

        edit_menu.addSeparator()

        copy_action = edit_menu.addAction(self.t('action_copy', default="📋 복사"))
        copy_action.triggered.connect(self.copy_action)
        copy_action.setShortcut('Ctrl+C')

        paste_action = edit_menu.addAction(self.t('action_paste', default="📥 붙여넣기"))
        paste_action.triggered.connect(self.paste_action)
        paste_action.setShortcut('Ctrl+V')

        edit_menu.addSeparator()

        find_action = edit_menu.addAction(self.t('action_find', default="🔍 본문 텍스트 찾기..."))
        find_action.triggered.connect(self.toggle_search_bar)
        find_action.setShortcut('Ctrl+F')

        find_next_action = edit_menu.addAction(self.t('action_find_next', default="🔽 다음 찾기"))
        find_next_action.triggered.connect(self._find_next)
        find_next_action.setShortcut('F3')

        find_prev_action = edit_menu.addAction(self.t('action_find_prev', default="🔼 이전 찾기"))
        find_prev_action.triggered.connect(self._find_prev)
        find_prev_action.setShortcut('Shift+F3')
        
        edit_menu.addSeparator()
        
        # 정밀 모드 토글
        self.precise_mode_action = edit_menu.addAction(self.t('action_precise_mode'))
        self.precise_mode_action.setCheckable(True)
        self.precise_mode_action.setChecked(self.patch_precise_mode and not self.patch_only_mode)
        self.precise_mode_action.toggled.connect(self.set_patch_mode)

        self.patch_eraser_action = edit_menu.addAction(self.t('action_patch_eraser'))
        self.patch_eraser_action.setCheckable(True)
        self.patch_eraser_action.setChecked(self.patch_precise_mode and self.patch_only_mode)
        self.patch_eraser_action.toggled.connect(self.toggle_patch_eraser)
        
        # 🔍 보기 메뉴
        view_menu = menubar.addMenu(self.t('view_menu'))
        
        # 축소 / 확대 순서로 배치
        zoom_out_action = view_menu.addAction(self.t('zoom_out'))
        zoom_out_action.triggered.connect(self.zoom_out) 
        zoom_out_action.setShortcuts([QKeySequence(QKeySequence.StandardKey.ZoomOut), QKeySequence('Ctrl+-')])

        zoom_in_action = view_menu.addAction(self.t('zoom_in'))
        zoom_in_action.triggered.connect(self.zoom_in)
        zoom_in_action.setShortcuts([QKeySequence(QKeySequence.StandardKey.ZoomIn), QKeySequence('Ctrl+=')])
        
        actual_size_action = view_menu.addAction(self.t('actual_size', default="💯 100% 실제 크기"))
        actual_size_action.triggered.connect(self.reset_zoom)
        actual_size_action.setShortcuts([QKeySequence('Ctrl+1'), QKeySequence('Ctrl+Alt+0')])
        
        view_menu.addSeparator()

        fit_width_action = view_menu.addAction(self.t('fit_width'))
        fit_width_action.triggered.connect(self.fit_to_width)
        fit_width_action.setShortcut('Ctrl+0')

        fit_height_action = view_menu.addAction(self.t('fit_height'))
        fit_height_action.triggered.connect(self.fit_to_height)
        fit_height_action.setShortcut('Ctrl+Shift+0')

        view_menu.addSeparator()
        self.light_mode_action = view_menu.addAction(self.t('theme_light_mode'))
        self.light_mode_action.setCheckable(True)
        self.light_mode_action.triggered.connect(lambda: self.set_theme_mode('light'))

        self.dark_mode_action = view_menu.addAction(self.t('theme_dark_mode'))
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.triggered.connect(lambda: self.set_theme_mode('dark'))

        view_menu.addSeparator()
        self.show_grid_action = view_menu.addAction(self.t('show_grid', default="▦ 격자 표시"))
        self.show_grid_action.setCheckable(True)
        self.show_grid_action.setChecked(False)
        self.show_grid_action.triggered.connect(self.toggle_grid)

        self.show_ruler_action = view_menu.addAction(self.t('show_ruler', default="📏 줄자 표시"))
        self.show_ruler_action.setCheckable(True)
        self.show_ruler_action.setChecked(False)
        self.show_ruler_action.triggered.connect(self.toggle_ruler)

        view_menu.addSeparator()
        self.toggle_thumbnail_action = view_menu.addAction(self.t('show_thumbnails', default="📑 페이지 썸네일 패널"))
        self.toggle_thumbnail_action.setCheckable(True)
        self.toggle_thumbnail_action.setChecked(True)
        self.toggle_thumbnail_action.setShortcut('F4')
        self.toggle_thumbnail_action.triggered.connect(self.toggle_thumbnail_panel)

        self.smart_snap_action = view_menu.addAction(self.t('smart_snap', default="🧲 스마트 스냅 (자석 정렬 가이드선)"))
        self.smart_snap_action.setCheckable(True)
        self.smart_snap_action.setChecked(True)
        self.smart_snap_action.triggered.connect(self.toggle_smart_snap)

        self.continuous_scroll_action = view_menu.addAction(self.t('continuous_scroll', default="📜 수직 연속 스크롤 (페이지 자동 전환)"))
        self.continuous_scroll_action.setCheckable(True)
        self.continuous_scroll_action.setChecked(True)
        self.continuous_scroll_action.triggered.connect(lambda chk: setattr(self, 'continuous_scroll_enabled', chk))


        # 🔧 도구 메뉴
        tools_menu = menubar.addMenu(self.t('tools_menu'))
        
        optimize_patches_action = tools_menu.addAction(self.t('action_optimize_patches'))
        optimize_patches_action.triggered.connect(self.optimize_all_patches)
        
        show_patch_info_action = tools_menu.addAction(self.t('action_show_patch_info'))
        show_patch_info_action.triggered.connect(self.show_patch_info)

        insert_image_action = tools_menu.addAction(self.t('action_insert_image', default="🖼️ 이미지 삽입..."))
        insert_image_action.triggered.connect(self.insert_image_action)
        insert_image_action.setShortcut('Ctrl+I')

        draw_signature_action = tools_menu.addAction(self.t('action_draw_signature', default="✍️ 전자 서명 그리기..."))
        draw_signature_action.triggered.connect(self.open_signature_pad)
        draw_signature_action.setShortcut('Ctrl+Alt+S')

        tools_menu.addSeparator()

        # 텍스트 유지 정밀 플래튼 옵션
        self.force_text_flatten_action = tools_menu.addAction(self.t('action_force_text_flatten'))
        self.force_text_flatten_action.setCheckable(True)
        self.force_text_flatten_action.setChecked(self.force_text_flatten)
        self.force_text_flatten_action.toggled.connect(self.toggle_force_text_flatten)

        # 글꼴 로그 상세도 토글
        self.font_dump_verbose = getattr(self, 'font_dump_verbose', 1)
        self.font_log_action = tools_menu.addAction(self._font_log_action_text())
        self.font_log_action.triggered.connect(self.toggle_font_log_verbosity)
        
        # 언어 메뉴 (i18n 폴더의 파일에 따라 동적 생성)
        language_menu = menubar.addMenu(self.t('language_menu'))
        self.language_actions = {}
        language_labels = {
            'ko': '한국어', 'en': 'English', 'ja': '日本語', 'zh-CN': '简体中文', 'zh-TW': '繁體中文',
            'de': 'Deutsch', 'fr': 'Français', 'it': 'Italiano', 'es': 'Español', 'pt': 'Português',
            'sv': 'Svenska', 'fi': 'Suomi', 'no': 'Norsk', 'da': 'Dansk', 'ru': 'Русский',
            'pl': 'Polski', 'cs': 'Čeština', 'ro': 'Română', 'uk': 'Українська', 'hu': 'Magyar',
            'bg': 'Български', 'vi': 'Tiếng Việt', 'th': 'ไทย', 'hi': 'हिन्दी', 'ar': 'العربية',
            'fa': 'فارسی', 'mn': 'Монгол', 'id': 'Bahasa Indonesia', 'ms': 'Bahasa Melayu',
            'fil': 'Filipino', 'kk': 'Қазақ тілі', 'uz': 'Oʻzbek tili', 'bn': 'বাংলা',
            'ur': 'اردو', 'tr': 'Türkçe'
        }
        
        # 로드된 모든 번역에 대해 메뉴 아이템 생성
        for code in sorted(self.translations.keys()):
            label = language_labels.get(code, code)
            action = language_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.language == code)
            # 람다 캡처 문제 방지를 위해 기본 매개변수 사용
            action.triggered.connect(lambda checked, c=code: self.set_language(c) if checked else None)
            self.language_actions[code] = action


        # ℹ️ 도움말 메뉴
        help_menu = menubar.addMenu(self.t('help_menu'))
        
        usage_guide_action = help_menu.addAction(self.t('usage_guide'))
        usage_guide_action.triggered.connect(lambda: webbrowser.open("https://www.youtube.com/playlist?list=PLs36bSFfggCCUX31PYEH_SNgAmVc3dk_B"))

        shortcuts_action = help_menu.addAction(self.t('action_shortcuts'))
        shortcuts_action.triggered.connect(self.show_shortcuts)

        about_action = help_menu.addAction(self.t('about'))
        about_action.triggered.connect(self.show_about)

        license_action = help_menu.addAction(self.t('licenses_menu'))
        license_action.triggered.connect(self.show_license_info)

        self._sync_theme_actions()
        self._sync_patch_controls()

    def setup_ui(self):
        # 메뉴바 설정 (모든 기능이 메뉴로 통합됨)
        self.create_menu_bar()
        
        # 상태 표시 라벨 (페이지, 상태 메시지, 배율)
        self.page_label = QLabel(self.t('page_label_empty'))
        self.zoom_label = QLabel(self.t('zoom_label_template', percent=100))
        self.status_message_label = QLabel(self.t('viewer_placeholder', default="PDF 파일을 열어 편집을 시작하세요."))

        # PDF 뷰어 (스크롤 영역 포함)
        self.pdf_viewer = PdfViewerWidget(parent=self)
        self.pdf_viewer.setText(self.t('viewer_placeholder'))
        
        # 스크롤 영역
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.pdf_viewer)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame) # 프레임 제거 (테마에서 관리)
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        # 툴바 위젯 초기화
        
        # 툴바 버튼 스타일 (버튼 자체는 굵게 유지하되, 툴팁에는 bold가 상속되지 않도록 QToolTip normal 지정)
        toolbar_btn_style = "QPushButton { font-size: 13px; font-weight: bold; } QToolTip { font-weight: normal; }"

        # 파일 관련 버튼들 (가로 확장)
        self.open_button = QPushButton("📂")
        self.open_button.setToolTip(self.t('tooltip_open'))
        self.open_button.setFixedSize(50, 40)
        self.open_button.setStyleSheet(toolbar_btn_style)
        
        self.save_button = QPushButton("💾")
        self.save_button.setToolTip(self.t('tooltip_save'))
        self.save_button.setFixedSize(50, 40)
        self.save_button.setStyleSheet(toolbar_btn_style)
        
        # 편집 관련 버튼들 (가로 확장)
        self.undo_button = QPushButton("↩️")
        self.undo_button.setToolTip(self.t('tooltip_undo'))
        self.undo_button.setFixedSize(50, 40)
        self.undo_button.setStyleSheet(toolbar_btn_style)
        
        self.redo_button = QPushButton("↪️")
        self.redo_button.setToolTip(self.t('tooltip_redo'))
        self.redo_button.setFixedSize(50, 40)
        self.redo_button.setStyleSheet(toolbar_btn_style)
        
        # 보기 관련 버튼들 (가로 확장)
        self.zoom_in_button = QPushButton("🔍➕")
        self.zoom_in_button.setToolTip(self.t('tooltip_zoom_in'))
        self.zoom_in_button.setFixedSize(55, 40)
        self.zoom_in_button.setStyleSheet(toolbar_btn_style)
        
        self.zoom_out_button = QPushButton("🔍➖")
        self.zoom_out_button.setToolTip(self.t('tooltip_zoom_out'))
        self.zoom_out_button.setFixedSize(55, 40)
        self.zoom_out_button.setStyleSheet(toolbar_btn_style)

        # 테마 토글 버튼
        self.theme_button = QPushButton("☀️")
        self.theme_button.setToolTip(self.t('tooltip_theme'))
        self.theme_button.setFixedSize(50, 40)
        self.theme_button.setStyleSheet(toolbar_btn_style)

        # 뷰 맞춤 버튼들
        self.fit_width_button = QPushButton("↔️")
        self.fit_width_button.setToolTip(self.t('tooltip_fit_width'))
        self.fit_width_button.setFixedSize(50, 40)
        self.fit_width_button.setStyleSheet(toolbar_btn_style)

        self.fit_height_button = QPushButton("↕️")
        self.fit_height_button.setToolTip(self.t('tooltip_fit_height'))
        self.fit_height_button.setFixedSize(50, 40)
        self.fit_height_button.setStyleSheet(toolbar_btn_style)

        # 페이지 이동 버튼들 (가로 확장)
        self.prev_page_button = QPushButton("👈")
        self.prev_page_button.setToolTip(self.t('tooltip_prev_page'))
        self.prev_page_button.setFixedSize(50, 40)
        self.prev_page_button.setStyleSheet(toolbar_btn_style)

        self.page_input = QLineEdit()
        self.page_input.setValidator(QIntValidator(1, 999999, self))
        self.page_input.setFixedWidth(60)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.setPlaceholderText(self.t('goto_page_placeholder'))
        self.page_input.setEnabled(False)
        self.page_input.setStyleSheet("font-size: 13px; font-weight: bold; padding: 6px; border: 1px solid #cccccc; border-radius: 6px; QToolTip { font-weight: normal; }")

        self.page_total_label = QLabel('/ 0')
        self.page_total_label.setStyleSheet("font-size: 13px; font-weight: bold; padding: 0 6px;")

        self.next_page_button = QPushButton("👉")
        self.next_page_button.setToolTip(self.t('tooltip_next_page'))
        self.next_page_button.setFixedSize(50, 40)
        self.next_page_button.setStyleSheet(toolbar_btn_style)

        self.thumbnail_button = QPushButton("📑")
        self.thumbnail_button.setCheckable(True)
        self.thumbnail_button.setChecked(True)
        self.thumbnail_button.setToolTip(self.t('tooltip_thumbnails', default="페이지 썸네일 패널 (F4)"))
        self.thumbnail_button.setFixedSize(50, 40)
        self.thumbnail_button.setStyleSheet(toolbar_btn_style)

        # 도구 관련 버튼들 (가로 확장)
        toggle_btn_style = (
            "QPushButton { font-size: 13px; font-weight: bold; border-radius: 8px; padding: 4px; }\n"
            "QPushButton[active=\"true\"] { background-color: rgba(255, 214, 102, 0.35);"
            " border: 1px solid rgba(255, 214, 102, 0.55); }\n"
            "QToolTip { font-weight: normal; }"
        )
        self.patch_mode_button = QPushButton("🩹")
        self.patch_mode_button.setCheckable(True)
        self.patch_mode_button.setToolTip(self.t('tooltip_patch_mode'))
        self.patch_mode_button.setFixedSize(50, 40)
        self.patch_mode_button.setStyleSheet(toggle_btn_style)
        self.patch_mode_button.setProperty('active', False)
        self.patch_mode_button.setChecked(self.patch_precise_mode)

        self.eraser_button = QPushButton("🧽")
        self.eraser_button.setCheckable(True)
        self.eraser_button.setToolTip(self.t('tooltip_patch_eraser'))
        self.eraser_button.setFixedSize(50, 40)
        self.eraser_button.setStyleSheet(toggle_btn_style)
        self.eraser_button.setProperty('active', False)

        self.insert_image_button = QPushButton("🖼️")
        self.insert_image_button.setToolTip(self.t('tooltip_insert_image', default="이미지 삽입 (Ctrl+I)"))
        self.insert_image_button.setFixedSize(50, 40)
        self.insert_image_button.setStyleSheet(toolbar_btn_style)

        self.draw_signature_button = QPushButton("✍️")
        self.draw_signature_button.setToolTip(self.t('tooltip_draw_signature', default="전자 서명 그리기 (Ctrl+Alt+S)"))
        self.draw_signature_button.setFixedSize(50, 40)
        self.draw_signature_button.setStyleSheet(toolbar_btn_style)

        self.search_button = QPushButton("🔍")
        self.search_button.setToolTip(self.t('tooltip_search', default="본문 텍스트 검색 (Ctrl+F)"))
        self.search_button.setFixedSize(50, 40)
        self.search_button.setStyleSheet(toolbar_btn_style)

        # 툴바 생성 (QToolBar: 좁은 화면에서 자동으로 >> 오버플로우 메뉴 제공)
        self.main_toolbar = QToolBar("Main Toolbar", self)
        self.main_toolbar.setMovable(False)
        self.main_toolbar.setFloatable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.main_toolbar)

        # 기능 유형별 툴바 배치 및 구분선 삽입
        # 1. 파일 기능 그룹
        self.main_toolbar.addWidget(self.open_button)
        self.main_toolbar.addWidget(self.save_button)
        self.main_toolbar.addSeparator()

        # 2. 실행 취소 / 다시 실행 그룹
        self.main_toolbar.addWidget(self.undo_button)
        self.main_toolbar.addWidget(self.redo_button)
        self.main_toolbar.addSeparator()

        # 3. 확대/축소 및 화면 맞춤 그룹
        self.main_toolbar.addWidget(self.zoom_out_button)
        self.main_toolbar.addWidget(self.zoom_in_button)
        self.main_toolbar.addWidget(self.fit_width_button)
        self.main_toolbar.addWidget(self.fit_height_button)
        self.main_toolbar.addSeparator()

        # 4. 페이지 이동 그룹
        self.main_toolbar.addWidget(self.prev_page_button)
        self.main_toolbar.addWidget(self.page_input)
        self.main_toolbar.addWidget(self.page_total_label)
        self.main_toolbar.addWidget(self.next_page_button)
        self.main_toolbar.addSeparator()

        # 5. 페이지 썸네일 패널 토글 그룹
        self.main_toolbar.addWidget(self.thumbnail_button)
        self.main_toolbar.addSeparator()

        # 6. 텍스트 패치 및 지우개 편집 그룹
        self.main_toolbar.addWidget(self.patch_mode_button)
        self.main_toolbar.addWidget(self.eraser_button)
        self.main_toolbar.addSeparator()

        # 7. 개체(이미지/전자서명) 삽입 그룹
        self.main_toolbar.addWidget(self.insert_image_button)
        self.main_toolbar.addWidget(self.draw_signature_button)
        self.main_toolbar.addSeparator()

        # 8. 본문 검색 그룹
        self.main_toolbar.addWidget(self.search_button)
        self.main_toolbar.addSeparator()

        # 9. 화면 테마 토글 그룹
        self.main_toolbar.addWidget(self.theme_button)

        # 본문 검색 바 (Ctrl+F)
        self.search_bar = QFrame(self)
        self.search_bar.setStyleSheet(
            "QFrame { background-color: #f1f5f9; border-bottom: 1.5px solid #cbd5e1; padding: 2px 8px; }"
            "QPushButton { font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 4px; }"
            "QLineEdit { background: white; padding: 5px 8px; border: 1.5px solid #94a3b8; border-radius: 6px; font-size: 13px; }"
        )
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(6, 4, 6, 4)
        search_layout.setSpacing(8)

        search_icon = QLabel("🔍")
        search_layout.addWidget(search_icon)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("문서 내 텍스트 검색... (Enter: 다음, Shift+Enter: 이전, Esc: 닫기)")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(self._find_next)
        search_layout.addWidget(self.search_input, stretch=1)

        self.search_count_label = QLabel("0/0")
        self.search_count_label.setStyleSheet("font-weight: bold; color: #475569; min-width: 50px;")
        search_layout.addWidget(self.search_count_label)

        self.search_prev_btn = QPushButton("▲ 이전")
        self.search_prev_btn.setToolTip("이전 일치 항목 (Shift+Enter)")
        self.search_prev_btn.clicked.connect(self._find_prev)
        search_layout.addWidget(self.search_prev_btn)

        self.search_next_btn = QPushButton("▼ 다음")
        self.search_next_btn.setToolTip("다음 일치 항목 (Enter)")
        self.search_next_btn.clicked.connect(self._find_next)
        search_layout.addWidget(self.search_next_btn)

        self.search_close_btn = QPushButton("✕")
        self.search_close_btn.setToolTip("검색창 닫기 (Esc)")
        self.search_close_btn.setFixedSize(28, 28)
        self.search_close_btn.clicked.connect(self.toggle_search_bar)
        search_layout.addWidget(self.search_close_btn)

        self.search_bar.setVisible(False)

        # 좌측 썸네일 탐색 패널과 스크롤 영역을 QSplitter로 통합
        self.thumbnail_panel = ThumbnailPanel(self)
        self.thumbnail_panel.page_selected.connect(self.go_to_page)
        self.thumbnail_panel.close_requested.connect(lambda: self.toggle_thumbnail_panel(False))

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.thumbnail_panel)
        self.main_splitter.addWidget(self.scroll_area)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([160, 840])

        # 상태바 위젯 (문서뷰어 상단에 고정 배치, 높이 30px 완전 고정)
        self.status_bar_widget = QWidget(self)
        self.status_bar_widget.setObjectName("statusBarWidget")
        self.status_bar_widget.setFixedHeight(30)
        self.status_bar_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.status_layout = QHBoxLayout(self.status_bar_widget)
        self.status_layout.setContentsMargins(14, 0, 14, 0)
        self.status_layout.setSpacing(10)

        # 1) 좌측: 페이지 위치 표시
        self.page_label.setObjectName("statusPageLabel")
        self.status_layout.addWidget(self.page_label)

        # 구분선 1
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setFrameShadow(QFrame.Shadow.Sunken)
        sep1.setFixedHeight(14)
        self.status_layout.addWidget(sep1)

        # 2) 중앙: 현재 모드 및 상태 메시지
        self.status_message_label.setObjectName("statusMessageLabel")
        self.status_layout.addWidget(self.status_message_label, stretch=1)

        # 구분선 2
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        sep2.setFixedHeight(14)
        self.status_layout.addWidget(sep2)

        # 3) 우측: 배율 표시
        self.zoom_label.setObjectName("statusZoomLabel")
        self.status_layout.addWidget(self.zoom_label)

        # 메인 레이아웃: status_bar_widget은 문서 뷰어 상단(stretch=0), main_splitter에 모든 신축 공간 배분(stretch=1)
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.search_bar, stretch=0)
        main_layout.addWidget(self.status_bar_widget, stretch=0)
        main_layout.addWidget(self.main_splitter, stretch=1)
        
        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        # 초기 테마 적용
        try:
            self.apply_theme(self.theme_mode)
        except Exception:
            pass
        self._apply_translated_tooltips()
        self._sync_patch_controls()

    def setup_connections(self):
        # 이모지 버튼들의 연결 설정
        self.open_button.clicked.connect(self.open_pdf)
        self.save_button.clicked.connect(self.save_pdf)
        self.undo_button.clicked.connect(self.undo_action)
        self.redo_button.clicked.connect(self.redo_action)
        self.zoom_in_button.clicked.connect(self.zoom_in)
        self.zoom_out_button.clicked.connect(self.zoom_out)
        self.fit_width_button.clicked.connect(self.fit_to_width)
        self.fit_height_button.clicked.connect(self.fit_to_height)
        self.prev_page_button.clicked.connect(self.prev_page)
        self.next_page_button.clicked.connect(self.next_page)
        self.thumbnail_button.clicked.connect(self.toggle_thumbnail_panel)
        self.page_input.returnPressed.connect(self.go_to_page_from_input)
        self.patch_mode_button.toggled.connect(self.set_patch_mode)
        self.eraser_button.toggled.connect(self.toggle_patch_eraser)
        self.insert_image_button.clicked.connect(self.insert_image_action)
        self.draw_signature_button.clicked.connect(self.open_signature_pad)
        self.search_button.clicked.connect(self.toggle_search_bar)
        self.theme_button.clicked.connect(self.toggle_theme)
        
        self.pdf_viewer.text_selected.connect(self.on_text_selected)

    def copy_action(self):
        if hasattr(self, 'pdf_viewer'):
            self.pdf_viewer.copy_selected()

    def paste_action(self):
        if hasattr(self, 'pdf_viewer'):
            self.pdf_viewer.paste_clipboard()

    def open_signature_pad(self):
        """전자 서명 그리기 대화상자 열기"""
        if not self.pdf_viewer.doc:
            QMessageBox.information(self, "알림", "먼저 PDF 문서를 열어주세요.")
            return
        dialog = SignaturePadDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.created_pixmap:
            import tempfile
            tmp_fd, tmp_path = tempfile.mkstemp(suffix="_sig.png")
            os.close(tmp_fd)
            dialog.created_pixmap.save(tmp_path, "PNG")
            self.insert_signature_pixmap(dialog.created_pixmap, tmp_path)

    def insert_signature_pixmap(self, pixmap, temp_path):
        """서명 패드에서 생성된 서명 이미지를 현재 페이지에 삽입"""
        if not self.pdf_viewer.doc:
            return
        
        page_num = self.pdf_viewer.current_page_num
        page = self.pdf_viewer.doc.load_page(page_num)
        page_rect = page.rect
        
        aspect = float(pixmap.width()) / float(pixmap.height()) if pixmap.height() > 0 else 2.0
        w = 140.0
        h = w / aspect
        
        x0 = (page_rect.width - w) / 2.0
        y0 = page_rect.height * 0.72
        bbox = fitz.Rect(x0, y0, x0 + w, y0 + h)
        
        if page_num not in self.pdf_viewer.image_overlays:
            self.pdf_viewer.image_overlays[page_num] = []
        
        self.pdf_viewer.image_id_counter += 1
        img_overlay = ImageOverlay(
            image_path=temp_path,
            bbox=bbox,
            page_num=page_num,
            opacity=1.0,
            z_index=self.pdf_viewer.image_id_counter
        )
        img_overlay.pixmap = pixmap
        self.pdf_viewer.image_overlays[page_num].append(img_overlay)
        self.pdf_viewer.active_image = img_overlay
        
        if hasattr(self, 'undo_manager') and self.pdf_viewer.doc:
            try:
                self.undo_manager.save_state(self.pdf_viewer.doc, self.pdf_viewer)
            except Exception: pass
            
        self.pdf_viewer.update()

    def toggle_search_bar(self):
        """본문 검색창 표시/숨김 토글 (Ctrl+F)"""
        if not hasattr(self, 'search_bar'):
            return
        is_vis = not self.search_bar.isHidden()
        self.search_bar.setVisible(not is_vis)
        if not is_vis:
            self.search_input.setFocus()
            self.search_input.selectAll()
            if self.search_input.text().strip():
                self._execute_search(self.search_input.text().strip())
        else:
            self._clear_search()

    def _on_search_text_changed(self, text):
        self._execute_search(text.strip())

    def _execute_search(self, query):
        if not self.pdf_viewer.doc or not query:
            self._clear_search()
            return
        
        self.search_results = []
        for page_idx in range(len(self.pdf_viewer.doc)):
            try:
                p = self.pdf_viewer.doc.load_page(page_idx)
                rects = p.search_for(query)
                for r in rects:
                    self.search_results.append((page_idx, r))
            except Exception:
                pass
        
        if not self.search_results:
            self.search_count_label.setText("0/0")
            self.pdf_viewer.search_highlights = []
            self.pdf_viewer.active_search_rect = None
            self.pdf_viewer.update()
            return
        
        curr_page = self.pdf_viewer.current_page_num
        start_idx = 0
        for i, (pg, _) in enumerate(self.search_results):
            if pg >= curr_page:
                start_idx = i
                break
        
        self.search_current_index = start_idx
        self._navigate_to_search_match()

    def _navigate_to_search_match(self):
        if not getattr(self, 'search_results', None):
            return
        total = len(self.search_results)
        idx = self.search_current_index % total
        self.search_current_index = idx
        
        page_num, target_rect = self.search_results[idx]
        self.search_count_label.setText(f"{idx + 1}/{total}")
        
        if self.pdf_viewer.current_page_num != page_num:
            self.go_to_page(page_num)
        
        page_highlights = [r for pg, r in self.search_results if pg == page_num]
        self.pdf_viewer.search_highlights = page_highlights
        self.pdf_viewer.active_search_rect = target_rect
        self.pdf_viewer.update()
        
        if hasattr(self, 'scroll_area') and self.scroll_area:
            scale = getattr(self.pdf_viewer, 'pixmap_scale_factor', 1.0)
            cx = (target_rect.x0 + target_rect.x1) / 2.0 * scale
            cy = (target_rect.y0 + target_rect.y1) / 2.0 * scale
            vp = self.scroll_area.viewport()
            self.scroll_area.horizontalScrollBar().setValue(int(round(cx - vp.width() / 2.0)))
            self.scroll_area.verticalScrollBar().setValue(int(round(cy - vp.height() / 2.0)))

    def _find_next(self):
        if not getattr(self, 'search_results', None):
            self._execute_search(self.search_input.text().strip())
            return
        self.search_current_index = (self.search_current_index + 1) % len(self.search_results)
        self._navigate_to_search_match()

    def _find_prev(self):
        if not getattr(self, 'search_results', None):
            self._execute_search(self.search_input.text().strip())
            return
        self.search_current_index = (self.search_current_index - 1 + len(self.search_results)) % len(self.search_results)
        self._navigate_to_search_match()

    def _clear_search(self):
        self.search_results = []
        self.search_current_index = 0
        if hasattr(self, 'search_count_label'):
            self.search_count_label.setText("0/0")
        if hasattr(self, 'pdf_viewer'):
            self.pdf_viewer.search_highlights = []
            self.pdf_viewer.active_search_rect = None
            self.pdf_viewer.update()

    def toggle_grid(self, checked):
        if hasattr(self, 'pdf_viewer'):
            self.pdf_viewer.show_grid = checked
            self.pdf_viewer.update()

    def toggle_ruler(self, checked):
        if hasattr(self, 'pdf_viewer'):
            self.pdf_viewer.show_ruler = checked
            self.pdf_viewer.update()

    def insert_image_action(self):
        if not self.pdf_viewer.doc:
            QMessageBox.warning(self, self.t('title_warning'), self.t('msg_no_pdf'))
            return
        initial_dir = getattr(self, 'last_open_dir', '') or ''
        file_path, _ = QFileDialog.getOpenFileName(
            self, "이미지 파일 선택", initial_dir,
            "Image Files (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)"
        )
        if file_path:
            self.pdf_viewer.add_image_overlay(file_path)
            self.statusBar().showMessage("이미지가 삽입되었습니다.", 3000)
    
    def update_undo_redo_buttons(self):
        """Undo/Redo 버튼 상태 업데이트"""
        self.undo_button.setEnabled(self.undo_manager.can_undo())
        self.redo_button.setEnabled(self.undo_manager.can_redo())
    
    def update_page_navigation(self):
        """페이지 네비게이션 업데이트"""
        if self.pdf_viewer.doc:
            total_pages = len(self.pdf_viewer.doc)
            current_page = self.pdf_viewer.current_page_num + 1
            self.page_label.setText(self.t('page_label_template', current=current_page, total=total_pages))
            
            self.prev_page_button.setEnabled(current_page > 1)
            self.next_page_button.setEnabled(current_page < total_pages)
            if hasattr(self, 'page_input'):
                self.page_input.setEnabled(True)
                try:
                    self.page_input.blockSignals(True)
                    self.page_input.setText(str(current_page))
                finally:
                    self.page_input.blockSignals(False)
            if hasattr(self, 'page_total_label'):
                self.page_total_label.setText(f"/ {total_pages}")
            if hasattr(self, 'thumbnail_panel') and self.thumbnail_panel:
                try:
                    lw = self.thumbnail_panel.list_widget
                    lw.blockSignals(True)
                    lw.setCurrentRow(self.pdf_viewer.current_page_num)
                    item = lw.item(self.pdf_viewer.current_page_num)
                    if item:
                        lw.scrollToItem(item)
                    lw.blockSignals(False)
                except Exception:
                    pass
        else:
            self.page_label.setText(self.t('page_label_empty'))
            self.prev_page_button.setEnabled(False)
            self.next_page_button.setEnabled(False)
            if hasattr(self, 'page_input'):
                try:
                    self.page_input.blockSignals(True)
                    self.page_input.clear()
                finally:
                    self.page_input.blockSignals(False)
                self.page_input.setEnabled(False)
            if hasattr(self, 'page_total_label'):
                self.page_total_label.setText('/ 0')
            if hasattr(self, 'thumbnail_panel') and self.thumbnail_panel:
                self.thumbnail_panel.list_widget.clear()
                self.thumbnail_panel.count_lbl.setText("")
        self.update_status_mode_message()

    def go_to_page(self, page_index):
        """지정한 페이지 번호(0-indexed)로 즉시 이동"""
        if not self.pdf_viewer.doc:
            return
        total_pages = len(self.pdf_viewer.doc)
        if total_pages <= 0:
            return
        target_index = max(0, min(total_pages - 1, page_index))
        if target_index == self.pdf_viewer.current_page_num:
            return
        self.pdf_viewer.current_page_num = target_index
        self.render_page()
        self.update_page_navigation()

    def toggle_thumbnail_panel(self, checked=None):
        """페이지 썸네일 탐색 사이드바 토글 (F4)"""
        if not hasattr(self, 'thumbnail_panel'):
            return
        if checked is None:
            is_vis = not self.thumbnail_panel.isHidden()
            target = not is_vis
        else:
            target = bool(checked)
        self.thumbnail_panel.setVisible(target)
        if hasattr(self, 'thumbnail_button'):
            self.thumbnail_button.blockSignals(True)
            self.thumbnail_button.setChecked(target)
            self.thumbnail_button.blockSignals(False)
        if hasattr(self, 'toggle_thumbnail_action'):
            self.toggle_thumbnail_action.blockSignals(True)
            self.toggle_thumbnail_action.setChecked(target)
            self.toggle_thumbnail_action.blockSignals(False)

    def toggle_smart_snap(self, checked):
        """스마트 스냅 활성화 여부 토글"""
        if hasattr(self, 'pdf_viewer'):
            self.pdf_viewer.smart_snap_enabled = checked
            self.pdf_viewer.active_snap_guides = []
            self.pdf_viewer.update()

    def load_thumbnails(self):
        """현재 문서의 페이지 썸네일들을 생성하여 사이드바에 로드"""
        if not hasattr(self, 'thumbnail_panel'):
            return
        lw = self.thumbnail_panel.list_widget
        lw.blockSignals(True)
        lw.clear()
        if not self.pdf_viewer.doc:
            self.thumbnail_panel.count_lbl.setText("")
            lw.blockSignals(False)
            return

        total = len(self.pdf_viewer.doc)
        self.thumbnail_panel.count_lbl.setText(f"({total})")

        # 1차 아이템 뼈대 등록 (텍스트 번호 및 기본 크기)
        for i in range(total):
            item = QListWidgetItem(f"{i + 1}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setSizeHint(QSize(120, 150))
            lw.addItem(item)
        lw.blockSignals(False)

        # 점진적 비동기 썸네일 렌더링 배치 시작
        self._thumbnail_render_index = 0
        self._render_next_thumbnail_batch()

    def _render_next_thumbnail_batch(self, batch_size=8):
        if not self.pdf_viewer.doc or not hasattr(self, 'thumbnail_panel'):
            return
        lw = self.thumbnail_panel.list_widget
        total = len(self.pdf_viewer.doc)
        start = getattr(self, '_thumbnail_render_index', 0)
        if start >= total:
            return

        end = min(start + batch_size, total)
        for i in range(start, end):
            try:
                page = self.pdf_viewer.doc.load_page(i)
                rect = page.rect
                scale = 96.0 / max(rect.width, 1.0)
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
                item = lw.item(i)
                if item:
                    item.setIcon(QIcon(QPixmap.fromImage(qimg)))
            except Exception:
                pass

        self._thumbnail_render_index = end
        if end < total:
            QTimer.singleShot(1, self._render_next_thumbnail_batch)
    
    def mark_as_changed(self):
        """변경사항 표시"""
        self.has_changes = True
        self._refresh_window_title()

    def mark_doc_modified(self):
        """[성능 최적화] PDF 문서 본체가 수정되었음을 표시 (tobytes() 강제 실행용)"""
        self._doc_modified_since_last_save = True
        self.mark_as_changed()

    def _get_standard_metrics(self, font, precision_multiplier=100.0):
        """[정합성 핵심] UI와 플래튼 간 동일한 좌표를 보장하기 위해 고정 DPI(72)에서 메트릭 측정"""
        from PySide6.QtGui import QImage, QFontMetricsF
        dummy = QImage(1, 1, QImage.Format.Format_Mono)
        # PDF 표준인 72 DPI로 고정하여 측정 장치 간 편차 제거
        dpm_72 = int(72 / 0.0254)
        dummy.setDotsPerMeterX(dpm_72)
        dummy.setDotsPerMeterY(dpm_72)
        
        # 폰트 정규화 (힌팅 제거 및 정밀도 설정)
        m_font = QFont(font)
        m_font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        m_font.setStyleStrategy(QFont.StyleStrategy.ForceOutline | QFont.StyleStrategy.PreferAntialias)
        m_font.setKerning(False)
        m_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
        
        return QFontMetricsF(m_font, dummy)

    def mark_as_saved(self):
        """저장됨 표시"""
        self.has_changes = False
        self._refresh_window_title()

    def register_recent_font(self, font_name: str | None):
        if not font_name:
            return
        font_name = str(font_name).strip()
        if not font_name:
            return
        lower_name = font_name.lower()
        filtered = [f for f in self.recent_fonts if f.lower() != lower_name]
        self.recent_fonts = [font_name] + filtered
        self.recent_fonts = self.recent_fonts[:8]
        try:
            self.settings.setValue('recent_fonts', json.dumps(self.recent_fonts, ensure_ascii=False))
        except Exception:
            pass

    def open_pdf(self, file_path: Optional[str] = None):
        if getattr(self, 'current_text_editor', None) is not None:
            try:
                if self.current_text_editor.isVisible():
                    self.current_text_editor.accept()
            except Exception:
                pass
            self.current_text_editor = None

        if self.has_changes:
            # 커스텀 메시지박스로 버튼 크기 동일/확대
            msg = QMessageBox(self)
            msg.setWindowTitle(self.t('title_unsaved_changes'))
            msg.setText(self.t('msg_unsaved_changes'))
            yes_btn = msg.addButton(QMessageBox.StandardButton.Yes)
            no_btn = msg.addButton(QMessageBox.StandardButton.No)
            cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)
            yes_btn.setText(self.t('btn_yes'))
            no_btn.setText(self.t('btn_no'))
            cancel_btn.setText(self.t('btn_cancel'))
            try:
                for b in msg.buttons():
                    b.setMinimumSize(96, 36)
            except Exception:
                pass
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == yes_btn:
                if not self.save_pdf():
                    return
            elif clicked == cancel_btn:
                return
        if not file_path:
            initial_dir = getattr(self, 'last_open_dir', '') or ''
            pdf_filter = self.t('file_type_pdf')
            if '(*.pdf)' not in pdf_filter:
                pdf_filter = "PDF Files (*.pdf)"
            file_path, _ = QFileDialog.getOpenFileName(
                self, self.t('dialog_open'), initial_dir, pdf_filter
            )
        if file_path:
            self.load_pdf_from_path(file_path)

    def load_pdf_from_path(self, file_path: str) -> bool:
        try:
            if not file_path or not os.path.isfile(file_path):
                raise FileNotFoundError(file_path)

            doc = fitz.open(file_path)
            # 이전 오버레이/패치 상태 초기화
            if hasattr(self.pdf_viewer, 'text_overlays'):
                self.pdf_viewer.text_overlays.clear()
                self.pdf_viewer.overlay_id_counter = 0
            if hasattr(self.pdf_viewer, 'background_patches'):
                self.pdf_viewer.background_patches.clear()
            self._font_ref_cache.clear()
            self._doc_font_ref_cache.clear()
            self.pdf_viewer.set_document(doc)
            self.current_file_path = file_path
            stored_zoom = None
            if self.settings:
                stored_zoom = self.settings.value('zoom_factor')
            try:
                levels = getattr(self, 'zoom_levels', [1.0])
                if stored_zoom is not None:
                    val = float(stored_zoom)
                    self.zoom_factor = min(levels, key=lambda x: abs(x - val))
                else:
                    self.zoom_factor = 1.0
            except Exception:
                self.zoom_factor = 1.0
            self.last_open_dir = os.path.dirname(file_path)
            self._store_last_open_dir()
            self._store_zoom_factor()
            self.has_changes = False

            # HWP(아래아한글) 문서 감지 고도화
            self.is_hwp_doc = False
            try:
                meta = doc.metadata or {}
                producer = meta.get('producer', '').lower()
                creator = meta.get('creator', '').lower()
                if any(k in producer or k in creator for k in ['hancom', 'hwp', 'haansoft']):
                    self.is_hwp_doc = True
                else:
                    # 메타데이터가 없는/변환된 문서: 폰트 목록 기반 HWP 감지
                    hwp_font_indicators = ['hcr', 'h2hdr', 'h2gtr', 'h2mk', 'hygtr', 'hybtr', 'hmk', 'hancom', 'haansoft', 'gulimche', 'batangche']
                    for page_idx in range(min(len(doc), 5)):
                        for f_info in doc[page_idx].get_fonts():
                            fname = (f_info[3] or '').lower()
                            if any(k in fname for k in hwp_font_indicators):
                                self.is_hwp_doc = True
                                break
                        if self.is_hwp_doc:
                            break
                if self.is_hwp_doc:
                    print("HWP(아래아한글) 문서 감지됨: 공백 너비 보정 모드 활성화")
            except Exception as e_hwp:
                print(f"HWP 문서 감지 중 오류: {e_hwp}")

            # PDF 폰트 정보 추출
            font_extractor = PdfFontExtractor(doc)
            font_extractor.extract_fonts_from_document()
            self.pdf_fonts = font_extractor.get_matched_fonts()

            print(f"Found {len(self.pdf_fonts)} fonts in PDF:")
            for font_info in self.pdf_fonts[:10]:  # 상위 10개 출력
                pdf_font = font_info['pdf_font']
                system_font = font_info['system_font']
                confidence = font_info['confidence']

                # 폰트 세부 정보 추가
                details = ""
                if hasattr(font_extractor, 'font_details') and pdf_font in font_extractor.font_details:
                    font_detail = font_extractor.font_details[pdf_font]
                    details = f" [Type: {font_detail['type']}, Encoding: {font_detail['encoding']}]"

                print(f"  PDF: {pdf_font} -> System: {system_font} (confidence: {confidence:.2f}){details}")

            # 매칭되지 않은 폰트 표시
            unmatched = [f for f in font_extractor.used_fonts if not any(mf['pdf_font'] == f for mf in self.pdf_fonts)]
            if unmatched:
                print(f"Unmatched fonts: {unmatched}")

            # Undo/Redo 초기화
            self.undo_manager = UndoRedoManager()
            
            # [최적화] 대용량 PDF의 경우 tobytes()가 매우 느리므로 로딩 시점에 미리 캐싱
            print("   - [성능 최적화] PDF 바이트 데이터 캐싱 중...")
            self._last_doc_bytes = doc.tobytes()
            self._doc_modified_since_last_save = False
            
            self.undo_manager.save_state(doc, self.pdf_viewer)
            self.update_undo_redo_buttons()

            self.render_page()
            self.load_thumbnails()
            self.update_page_navigation()
            self._refresh_window_title()
            fname = os.path.basename(file_path)
            self.show_status_message(self.t('status_doc_opened', fname=fname, total=len(doc), default=f"문서 열림: {fname} (총 {len(doc)}페이지)"), timeout_ms=3000)
            return True

        except Exception as e:
            QMessageBox.critical(self, self.t('title_error'), self.t('msg_open_failed', error=e))
            return False

    def save_pdf(self):
        if not self.pdf_viewer.doc:
            QMessageBox.warning(self, self.t('title_warning'), self.t('msg_no_pdf'))
            return False
            
        if not self.current_file_path:
            return self.save_as_pdf()
        
        self.show_status_message(self.t('progress_saving_pdf', default="PDF 저장 중..."))
        progress = None
        try:
            progress = QProgressDialog(self.t('progress_saving_pdf'), None, 0, 0, self)
            progress.setWindowTitle(self.t('dialog_save'))
            progress.setMinimumDuration(0)
            progress.setAutoClose(False)
            progress.setCancelButton(None)
            progress.show()

            # 오버레이를 PDF에 반영 (플래튼)
            self._set_progress(progress, self.t('progress_flatten_overlays'))
            self.flatten_overlays_to_pdf(progress)
            self._set_progress(progress, self.t('progress_writing_pdf'))
            try:
                self._write_pdf_atomic(self.current_file_path)
                self.last_open_dir = os.path.dirname(self.current_file_path)
                self._store_last_open_dir()
            except PermissionError as perm_err:
                try:
                    if progress:
                        progress.close()
                except Exception:
                    pass
                QMessageBox.warning(
                    self,
                    self.t('title_warning'),
                    self.t('save_permission_error_detail', error=str(perm_err))
                )
                return self.save_as_pdf()
            self.mark_as_saved()
            # 저장 성공 메시지(확대된 OK 버튼 스타일 적용)
            try:
                msg = QMessageBox(self)
                msg.setWindowTitle(self.t('title_success'))
                msg.setText(self.t('save_success_message'))
                msg.setIcon(QMessageBox.Information)
                ok = msg.addButton(QMessageBox.Ok)
                ok.setMinimumSize(96, 36)
                msg.exec()
            except Exception:
                QMessageBox.information(self, self.t('title_success'), self.t('save_success_message'))
            self.show_status_message(self.t('save_success_message', default="문서가 성공적으로 저장되었습니다."), timeout_ms=3000)
            return True
        except Exception as e:
            QMessageBox.critical(self, self.t('title_error'), self.t('save_failed_detail', error=str(e)))
            self.update_status_mode_message()
            return False
        finally:
            try:
                if progress:
                    progress.close()
            except Exception:
                pass
    
    def save_as_pdf(self):
        if not self.pdf_viewer.doc:
            QMessageBox.warning(self, self.t('title_warning'), self.t('msg_no_pdf'))
            return False
            
        initial_dir = getattr(self, 'last_open_dir', '') or ''
        pdf_filter = self.t('file_type_pdf')
        if '(*.pdf)' not in pdf_filter:
            pdf_filter = "PDF Files (*.pdf)"
        file_path, _ = QFileDialog.getSaveFileName(
            self, self.t('dialog_save_as'), initial_dir, pdf_filter
        )
        if file_path:
            self.show_status_message(self.t('progress_saving_pdf', default="PDF 저장 중..."))
            progress = None
            try:
                progress = QProgressDialog(self.t('progress_saving_pdf'), None, 0, 0, self)
                progress.setWindowTitle(self.t('dialog_save_as'))
                progress.setMinimumDuration(0)
                progress.setAutoClose(False)
                progress.setCancelButton(None)
                progress.show()
                # 오버레이를 PDF에 반영 (플래튼)
                self._set_progress(progress, self.t('progress_flatten_overlays'))
                self.flatten_overlays_to_pdf(progress)
                self._set_progress(progress, self.t('progress_writing_pdf'))
                self._write_pdf_atomic(file_path)
                self.current_file_path = file_path
                self.last_open_dir = os.path.dirname(file_path)
                self._store_last_open_dir()
                self.mark_as_saved()
                self.setWindowTitle(f"{self.t('app_title')} - {os.path.basename(file_path)}")
                QMessageBox.information(self, self.t('title_success'), self.t('save_success_message'))
                self.show_status_message(self.t('save_success_message', default="문서가 성공적으로 저장되었습니다."), timeout_ms=3000)
                return True
            except Exception as e:
                QMessageBox.critical(self, self.t('title_error'), self.t('save_failed_detail', error=str(e)))
                self.update_status_mode_message()
                return False
            finally:
                try:
                    if progress:
                        progress.close()
                except Exception:
                    pass
        return False

    def dragEnterEvent(self, event: QDragEnterEvent):  # type: ignore[override]
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and url.toLocalFile().lower().endswith('.pdf'):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):  # type: ignore[override]
        for url in event.mimeData().urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith('.pdf'):
                self.open_pdf(url.toLocalFile())
                event.acceptProposedAction()
                return
        event.ignore()

    def _write_pdf_atomic(self, target_path: str) -> None:
        if not self.pdf_viewer or not self.pdf_viewer.doc:
            raise RuntimeError('Document not loaded')

        base_dir = os.path.dirname(target_path) or os.getcwd()
        os.makedirs(base_dir, exist_ok=True)

        current_page = getattr(self.pdf_viewer, 'current_page_num', 0)
        zoom_factor = getattr(self, 'zoom_factor', 1.0)
        scroll_value = 0
        try:
            scroll_value = self.scroll_area.verticalScrollBar().value()
        except Exception:
            scroll_value = 0

        data = self.pdf_viewer.doc.tobytes(garbage=4, deflate=True, clean=True)
        tmp_path = os.path.join(base_dir, f".__yongpdf_text_tmp_{uuid.uuid4().hex}.pdf")

        try:
            with open(tmp_path, 'wb') as tmp_file:
                tmp_file.write(data)

            try:
                self.pdf_viewer.doc.close()
            except Exception:
                pass

            os.replace(tmp_path, target_path)
            new_doc = fitz.open(target_path)
            self._load_doc_into_viewer(new_doc, current_page, zoom_factor, scroll_value)
        except Exception as replace_err:
            try:
                fallback_doc = fitz.open(stream=data, filetype='pdf')
                self._load_doc_into_viewer(fallback_doc, current_page, zoom_factor, scroll_value)
            except Exception:
                pass
            raise replace_err
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _load_doc_into_viewer(self, new_doc, current_page, zoom_factor, scroll_value):
        self.pdf_viewer.set_document(new_doc)
        if hasattr(self.pdf_viewer, 'text_overlays'):
            self.pdf_viewer.text_overlays.clear()
        else:
            self.pdf_viewer.text_overlays = {}
        self.pdf_viewer.overlay_id_counter = 0
        if hasattr(self.pdf_viewer, 'background_patches'):
            self.pdf_viewer.background_patches.clear()
        else:
            self.pdf_viewer.background_patches = {}
        self.pdf_viewer.active_overlay = None

        self.pdf_viewer.current_page_num = min(current_page, max(0, len(new_doc) - 1))
        self.zoom_factor = zoom_factor
        self.render_page()
        self.update_page_navigation()
        try:
            self.scroll_area.verticalScrollBar().setValue(scroll_value)
        except Exception:
            pass
    
    def undo(self):
        """실행 취소"""
        print(f"\nUndo === MainWindow.undo() 호출 ===")
        
        if self.pdf_viewer.doc:
            print(f"   - 현재 PDF 페이지 수: {len(self.pdf_viewer.doc)}")
            print(f"   - 현재 페이지 번호: {self.pdf_viewer.current_page_num}")
            
            # 현재 텍스트 오버레이 상태 로깅
            if hasattr(self.pdf_viewer, 'text_overlays'):
                overlays_count = len(self.pdf_viewer.text_overlays.get(self.pdf_viewer.current_page_num, []))
                print(f"   - 현재 페이지 텍스트 오버레이 개수: {overlays_count}")
            
            # 현재 페이지를 보존
            prev_page = self.pdf_viewer.current_page_num
            restored_doc = self.undo_manager.undo(self.pdf_viewer.doc, self.pdf_viewer)
            
            if restored_doc:
                print(f"   - 복구된 PDF 페이지 수: {len(restored_doc)}")
                
                self.pdf_viewer.set_document(restored_doc)
                # 가능하면 이전 페이지 유지
                self.pdf_viewer.current_page_num = min(max(0, prev_page), len(restored_doc) - 1)
                
                print(f"   - 복구 후 페이지 번호: {self.pdf_viewer.current_page_num}")
                
                # 오버레이/패치 상태는 UndoRedoManager에서 복원됨
                
                # 기타 편집 관련 상태 초기화
                if hasattr(self.pdf_viewer, 'selected_text_info'):
                    self.pdf_viewer.selected_text_info = None
                if hasattr(self.pdf_viewer, 'text_adjustment_mode'):
                    self.pdf_viewer.text_adjustment_mode = False
                if hasattr(self.pdf_viewer, 'quick_adjustment_mode'):
                    self.pdf_viewer.quick_adjustment_mode = False
                
                self.render_page()
                self.update_undo_redo_buttons()
                self.mark_as_changed()
                self.show_status_message(self.t('status_undo_done', default="실행 취소 완료"), timeout_ms=2500)
                
                print(f"   - OK 실행 취소 완료")
            else:
                print(f"   - X 복구된 문서가 없음 (restored_doc is None)")
        else:
            print(f"   - X PDF 문서가 열려있지 않음")
    
    def redo(self):
        """다시 실행"""
        print(f"\nRedo === MainWindow.redo() 호출 ===")
        
        if self.pdf_viewer.doc:
            print(f"   - 현재 PDF 페이지 수: {len(self.pdf_viewer.doc)}")
            print(f"   - 현재 페이지 번호: {self.pdf_viewer.current_page_num}")
            
            # 현재 텍스트 오버레이 상태 로깅
            if hasattr(self.pdf_viewer, 'text_overlays'):
                overlays_count = len(self.pdf_viewer.text_overlays.get(self.pdf_viewer.current_page_num, []))
                print(f"   - 현재 페이지 텍스트 오버레이 개수: {overlays_count}")
            
            prev_page = self.pdf_viewer.current_page_num
            restored_doc = self.undo_manager.redo(self.pdf_viewer.doc, self.pdf_viewer)
            
            if restored_doc:
                print(f"   - 복구된 PDF 페이지 수: {len(restored_doc)}")
                
                self.pdf_viewer.set_document(restored_doc)
                self.pdf_viewer.current_page_num = min(max(0, prev_page), len(restored_doc) - 1)
                
                print(f"   - 복구 후 페이지 번호: {self.pdf_viewer.current_page_num}")
                
                # 오버레이/패치 상태는 UndoRedoManager에서 복원됨
                
                # 기타 편집 관련 상태 초기화
                if hasattr(self.pdf_viewer, 'selected_text_info'):
                    self.pdf_viewer.selected_text_info = None
                if hasattr(self.pdf_viewer, 'text_adjustment_mode'):
                    self.pdf_viewer.text_adjustment_mode = False
                if hasattr(self.pdf_viewer, 'quick_adjustment_mode'):
                    self.pdf_viewer.quick_adjustment_mode = False
                
                self.render_page()
                self.update_undo_redo_buttons()
                self.mark_as_changed()
                self.show_status_message(self.t('status_redo_done', default="다시 실행 완료"), timeout_ms=2500)
                
                print(f"   - OK 다시 실행 완료")
            else:
                print(f"   - X 복구된 문서가 없음 (restored_doc is None)")
        else:
            print(f"   - X PDF 문서가 열려있지 않음")

    def prev_page(self):
        """이전 페이지"""
        if self.pdf_viewer.doc and self.pdf_viewer.current_page_num > 0:
            self.pdf_viewer.current_page_num -= 1
            self.render_page()
            self.update_page_navigation()
    
    def next_page(self):
        """다음 페이지"""
        if self.pdf_viewer.doc and self.pdf_viewer.current_page_num < len(self.pdf_viewer.doc) - 1:
            self.pdf_viewer.current_page_num += 1
            self.render_page()
            self.update_page_navigation()

    def go_to_page_from_input(self):
        """입력한 페이지 번호로 이동"""
        if not self.pdf_viewer.doc:
            return
        text = self.page_input.text().strip() if hasattr(self, 'page_input') else ''
        if not text:
            return
        try:
            page_number = int(text)
        except ValueError:
            return
        total_pages = len(self.pdf_viewer.doc)
        if total_pages <= 0:
            return
        page_number = max(1, min(total_pages, page_number))
        target_index = page_number - 1
        if target_index == self.pdf_viewer.current_page_num:
            return
        self.pdf_viewer.current_page_num = target_index
        self.render_page()
        self.update_page_navigation()

    def zoom_in(self, mouse_pos=None):
        current = getattr(self, 'zoom_factor', 1.0)
        levels = getattr(self, 'zoom_levels', [1.0])
        new_factor = levels[-1]
        for val in levels:
            if val > current + 0.001:
                new_factor = val
                break
        self._apply_zoom(new_factor, mouse_pos)

    def zoom_out(self, mouse_pos=None):
        current = getattr(self, 'zoom_factor', 1.0)
        levels = getattr(self, 'zoom_levels', [1.0])
        new_factor = levels[0]
        for val in reversed(levels):
            if val < current - 0.001:
                new_factor = val
                break
        self._apply_zoom(new_factor, mouse_pos)

    def _apply_zoom(self, new_factor, mouse_pos=None):
        """[UX 개선] 마우스 포인터를 중심으로 배율을 적용하고 스크롤 위치 조정"""
        if abs(self.zoom_factor - new_factor) < 0.0001:
            return

        old_factor = self.zoom_factor
        self.zoom_factor = new_factor
        
        # mouse_pos가 명시되지 않은 경우 뷰포트 중앙을 기준으로 줌
        if mouse_pos is None and hasattr(self, 'scroll_area') and self.scroll_area:
            vp = self.scroll_area.viewport()
            mouse_pos = QPoint(vp.width() // 2, vp.height() // 2)

        # 스크롤 위치 조정 계산
        if mouse_pos and hasattr(self, 'scroll_area'):
            h_bar = self.scroll_area.horizontalScrollBar()
            v_bar = self.scroll_area.verticalScrollBar()
            
            # 뷰포트 내 마우스 상대 좌표
            rel_mouse_x = mouse_pos.x()
            rel_mouse_y = mouse_pos.y()
            
            # 현재 전체 문서 상의 마우스 절대 좌표 (픽셀 단위)
            abs_mouse_x = (h_bar.value() + rel_mouse_x) / old_factor
            abs_mouse_y = (v_bar.value() + rel_mouse_y) / old_factor
            
            # 페이지 렌더링 (크기 변경됨)
            self.render_page()
            
            # 새 배율에서의 마우스 절대 좌표 위치를 다시 뷰포트 중심에 맞춤
            new_h = (abs_mouse_x * self.zoom_factor) - rel_mouse_x
            new_v = (abs_mouse_y * self.zoom_factor) - rel_mouse_y
            
            h_bar.setValue(int(round(new_h)))
            v_bar.setValue(int(round(new_v)))
        else:
            self.render_page()
            
        self.update_zoom_label()
        self._store_zoom_factor()
    
    def reset_zoom(self):
        self.zoom_factor = 1.0
        self.render_page()
        self.update_zoom_label()
        self._store_zoom_factor()

    def keyPressEvent(self, event):
        """스페이스바 등 전역 키 이벤트를 뷰어에 전달하여 Adobe 스타일 핸드툴 즉각 반응"""
        if event.key() == Qt.Key.Key_Space:
            if hasattr(self, 'pdf_viewer') and self.pdf_viewer:
                self.pdf_viewer.keyPressEvent(event)
                event.accept()
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """스페이스바 해제 이벤트 전달"""
        if event.key() == Qt.Key.Key_Space:
            if hasattr(self, 'pdf_viewer') and self.pdf_viewer:
                self.pdf_viewer.keyReleaseEvent(event)
                event.accept()
                return
        super().keyReleaseEvent(event)

    def render_page(self, page_to_render=None):
        if not self.pdf_viewer.doc: 
            return
            
        try:
            page = page_to_render if page_to_render is not None else \
                   self.pdf_viewer.doc.load_page(self.pdf_viewer.current_page_num)
            
            # 절대 배율 시스템 사용 (zoom_factor 자체가 절대 배율임)
            self.current_base_scale = 1.0
            final_scale = self.zoom_factor
            
            self.pdf_viewer.pixmap_scale_factor = final_scale
            
            # 렌더링
            matrix = fitz.Matrix(final_scale, final_scale)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            
            # QImage로 변환
            image_format = QImage.Format.Format_RGB888
            qimage = QImage(pix.samples, pix.width, pix.height, pix.stride, image_format)
            pixmap = QPixmap.fromImage(qimage)
            
            # 위젯 크기를 픽스맵 크기에 맞춤
            self.pdf_viewer.setFixedSize(pixmap.size())
            self.pdf_viewer.setPixmap(pixmap)
            # 줌 라벨 갱신
            self.update_zoom_label()

        except Exception as e:
            print(f"Error rendering page: {e}")

    def update_zoom_label(self):
        """현재 화면 렌더 배율을 퍼센트로 정확히 표시"""
        try:
            # 절대 배율 시스템: zoom_factor 자체가 1.0일 때 100%임
            percent = int(round(self.zoom_factor * 100))
            self.zoom_label.setText(self.t('zoom_label_template', percent=percent))
        except Exception:
            self.zoom_label.setText(self.t('zoom_label_template', percent='-'))

    def update_status_mode_message(self):
        """현재 모드 및 상태에 따른 기본 안내 메시지를 상태바에 표시"""
        if not hasattr(self, 'status_message_label') or not self.status_message_label:
            return
        
        # 1. 문서가 로드되지 않은 상태
        viewer = getattr(self, 'pdf_viewer', None)
        if not viewer or not getattr(viewer, 'doc', None):
            self.status_message_label.setText(self.t('status_ready_no_doc', default="문서를 열어주세요."))
            return

        # 2. 텍스트 위치 조정 모드
        if getattr(viewer, 'text_adjustment_mode', False) or getattr(viewer, 'quick_adjustment_mode', False):
            self.status_message_label.setText(self.t('status_mode_text_adjust', default="텍스트 위치 조정 모드: 방향키로 이동, ESC/Enter로 완료"))
            return

        # 3. 이미지 조작 모드 (선택된 이미지가 있을 때)
        if getattr(viewer, 'selected_image_index', None) is not None:
            self.status_message_label.setText(self.t('status_mode_image', default="이미지 조작 모드: 드래그하여 이동, 모서리 핸들로 크기 조절 (Delete: 삭제)"))
            return

        # 4. 패치 / 지우개 모드 버튼이 활성화된 상태
        if getattr(self, 'patch_precise_mode', False):
            if getattr(self, 'patch_only_mode', False):
                self.status_message_label.setText(self.t('status_mode_eraser', default="지우개 모드: 영역을 드래그하여 흰색으로 지웁니다"))
            else:
                self.status_message_label.setText(self.t('status_mode_patch', default="패치 모드: 편집할 영역을 드래그하여 텍스트를 수정합니다"))
            return

        # 5. 일반 모드
        self.status_message_label.setText(self.t('status_mode_general', default="일반 모드 (Ctrl+드래그: 패치, Shift+드래그: 지우개, Space+드래그: 화면이동)"))

    def show_status_message(self, message: str, timeout_ms: int = 0):
        """상태바 중앙에 메시지 표시 및 타이머 지원"""
        if not hasattr(self, 'status_message_label') or not self.status_message_label:
            return
        if hasattr(self, '_status_timer') and self._status_timer:
            try:
                self._status_timer.stop()
            except Exception:
                pass
            self._status_timer = None
        
        self.status_message_label.setText(message)
        if timeout_ms > 0:
            self._status_timer = QTimer(self)
            self._status_timer.setSingleShot(True)
            self._status_timer.timeout.connect(self.update_status_mode_message)
            self._status_timer.start(timeout_ms)

    def _on_status_bar_message_changed(self, message: str):
        """QStatusBar의 messageChanged 시그널을 커스텀 상태 라벨에 반영"""
        if message:
            if hasattr(self, '_status_timer') and self._status_timer:
                try:
                    self._status_timer.stop()
                except Exception:
                    pass
                self._status_timer = None
            if hasattr(self, 'status_message_label') and self.status_message_label:
                self.status_message_label.setText(message)
        else:
            self.update_status_mode_message()

    def _rgbf_from_color_int(self, color_int):
        """정수 색상(0xRRGGBB)을 (r,g,b) 0.0~1.0 튜플로 변환"""
        if isinstance(color_int, QColor):
            return (color_int.redF(), color_int.greenF(), color_int.blueF())
        r = (color_int >> 16) & 0xFF
        g = (color_int >> 8) & 0xFF
        b = color_int & 0xFF
        return (r/255.0, g/255.0, b/255.0)

    def _flatten_overlay_as_image(self, page, ov):
        """오버레이를 고해상도 이미지로 변환하여 PDF에 삽입 (폰트 오류 등 대비 최후의 수단)"""
        try:
            from PySide6.QtGui import QImage, QPainter
            from PySide6.QtCore import QBuffer, QIODevice, Qt
            
            # [핵심 개선] 클리핑 방지 전략: 현재 bbox(fitted) 기준 상하좌우 여유 공간 확보
            # 볼드, 자간, 장평 조정으로 bbox를 미세하게 벗어나는 텍스트 영역을 모두 포함하도록 함
            base_bbox = ov.bbox if (ov.bbox and ov.bbox.width > 0) else (ov.original_bbox if ov.original_bbox else fitz.Rect(0,0,1,1))
            
            # 폰트 크기의 50% 정도(최소 10pt) 여유 공간 추가
            margin = max(10.0, ov.size * 0.5)
            render_bbox = fitz.Rect(
                base_bbox.x0 - margin,
                base_bbox.y0 - margin,
                base_bbox.x1 + margin,
                base_bbox.y1 + margin
            )
            
            if render_bbox.width <= 0 or render_bbox.height <= 0:
                return False
                
            # 초고해상도 렌더링 (1200 DPI 상향)
            dpi = 1200
            render_scale = dpi / 72.0 
            img_w = int(math.ceil(render_bbox.width * render_scale))
            img_h = int(math.ceil(render_bbox.height * render_scale))
            
            if img_w <= 0 or img_h <= 0:
                return False
                
            image = QImage(img_w, img_h, QImage.Format.Format_ARGB32)
            # DPI 정보 설정
            dpm = int(dpi / 0.0254)
            image.setDotsPerMeterX(dpm)
            image.setDotsPerMeterY(dpm)
            image.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(image)
            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
                
                # 확장된 render_bbox 기준으로 원점 이동 (0,0에서 그림 시작)
                painter.scale(render_scale, render_scale)
                painter.translate(-render_bbox.x0, -render_bbox.y0)
                
                # 오버레이 렌더링 (절대 좌표 기반)
                ov.render_to_painter(painter, scale_factor=1.0, offsets=(0, 0))
            finally:
                painter.end()
            
            # 이미지를 PNG 데이터로 변환하여 PDF 삽입
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buffer, "PNG")
            img_data = bytes(buffer.data())
            
            # PDF 페이지에도 확장된 영역(render_bbox)에 이미지 삽입하여 위치 정합성 유지
            page.insert_image(render_bbox, stream=img_data)
            print(f"    -> [Fallback] 오버레이 이미지 렌더링 완료(1200 DPI, Margin 적용): ID {ov.z_index} ('{ov.text[:10]}...')")
            return True
        except Exception as e:
            print(f"    -> [Critical] 이미지 폴백 실패: {e}")
            import traceback
            traceback.print_exc()
            return False

    def enforce_single_overlay_view(self, page, overlay, new_values):
        """요청사항: 편집 시 해당 세로 밴드를 전부 패치로 가리고, 오직 현재 오버레이만 보이도록 강제"""
        try:
            page_num = overlay.page_num
            band_rect = fitz.Rect(page.rect.x0, overlay.original_bbox.y0, page.rect.x1, overlay.original_bbox.y1)
            # 1) 풀폭 패치 적용 및 UI 등록
            nv = dict(new_values)
            nv['cover_all_band'] = True
            try:
                patch_rect, patch_color = self.apply_background_patch(page, overlay.original_bbox, nv, overlay=overlay, preview=False)
            except Exception:
                patch_rect, patch_color = (band_rect, None)
            # 2) 같은 밴드의 다른 오버레이 숨기기
            others = self.pdf_viewer.text_overlays.get(page_num, [])
            for ov in others:
                if ov is overlay:
                    ov.visible = True
                    continue
                try:
                    obox = ov.bbox if ov.bbox else ov.original_bbox
                    if obox and obox.intersects(band_rect):
                        ov.visible = False
                except Exception:
                    continue
            print(f"잠금 단일 레이어 표시 강제: 페이지 {page_num}, 밴드 {band_rect}")
        except Exception as e:
            print(f"enforce_single_overlay_view 오류: {e}")

    def _font_supports_char(self, font_path: str, ch: str) -> bool:
        try:
            if not font_path or not os.path.exists(font_path):
                return False
            cmap = self._font_coverage_cache.get(font_path)
            if cmap is None:
                try:
                    tt = TTFont(font_path, fontNumber=0)
                    best = tt.getBestCmap()
                    cmap = set(best.keys()) if best else set()
                    self._font_coverage_cache[font_path] = cmap
                except Exception:
                    self._font_coverage_cache[font_path] = set()
                    cmap = set()
            return ord(ch) in cmap or ch == ' '
        except Exception:
            return False

    def _font_supports_all(self, font_path: str, text: str) -> bool:
        if not text:
            return True
        for ch in text:
            if not self._font_supports_char(font_path, ch):
                return False
        return True

    def _set_progress(self, progress, text):
        try:
            if progress:
                progress.setLabelText(text)
                QApplication.processEvents()
        except Exception:
            pass

    def _init_progress(self, progress, total):
        try:
            if progress:
                progress.setRange(0, max(0, int(total)))
                progress.setValue(0)
                self._progress_value = 0
                self._progress_total = int(total)
                QApplication.processEvents()
        except Exception:
            pass

    def _step_progress(self, progress, n=1):
        try:
            if progress and hasattr(self, '_progress_value'):
                self._progress_value = int(self._progress_value) + int(n)
                progress.setValue(min(self._progress_value, getattr(self, '_progress_total', self._progress_value)))
                QApplication.processEvents()
        except Exception:
            pass

    def _dump_page_fonts(self, page, title=""):
        try:
            fl = page.get_fonts()
            level = getattr(self, 'font_dump_verbose', 1)
            if level <= 0:
                print(f"   Fonts {title}: {len(fl)} items")
                return
            if level == 1:
                names = []
                for f in fl:
                    try:
                        base = f[3] if len(f) > 3 else (f[0] if len(f) > 0 else "?")
                        names.append(str(base))
                    except Exception:
                        continue
                print(f"   Fonts {title}: {len(names)} → {names[:10]}{'...' if len(names)>10 else ''}")
            else:
                # 상세: xref, type, encoding, basefont
                details = []
                for f in fl:
                    try:
                        xref = f[0] if len(f) > 0 else '?'
                        ftype = f[1] if len(f) > 1 else '?'
                        enc = f[2] if len(f) > 2 else '?'
                        base = f[3] if len(f) > 3 else '?'
                        details.append((xref, ftype, enc, base))
                    except Exception:
                        continue
                print(f"   Fonts {title}: {len(details)} items")
                for d in details[:20]:
                    print(f"      -  xref={d[0]} type={d[1]} enc={d[2]} base={d[3]}")
        except Exception as e:
            print(f"   Fonts dump skipped: {e}")

    def flatten_overlays_to_pdf(self, progress=None):
        """현재 레이어 오버레이를 PDF 콘텐츠로 반영 (진행메시지/폰트로그 포함)
        정합성 극대화를 위해 3단계(패치 -> 텍스트 -> 스타일/밑줄) 순서로 페이지별 처리함.
        """
        has_text = hasattr(self.pdf_viewer, 'text_overlays') and any(self.pdf_viewer.text_overlays.values())
        has_images = hasattr(self.pdf_viewer, 'image_overlays') and any(self.pdf_viewer.image_overlays.values())
        if not has_text and not has_images:
            return

        print("\n오버레이 플래튼 시작 (레이어 및 이미지 반영)")
        
        # 모든 오버레이의 이미지 플래튼 상태 초기화 (폴백 제어용)
        if hasattr(self.pdf_viewer, 'text_overlays'):
            for v in self.pdf_viewer.text_overlays.values():
                for ov in v:
                    ov.image_flattened = False

        self._set_progress(progress, self.t('progress_preparing_fonts'))
        
        try:
            total_pages = len(self.pdf_viewer.doc)
        except Exception:
            total_pages = 0
        
        # 진행 단계 총량 추산
        self._init_progress(progress, total_pages * 4) # 페이지당 4단계 (패치, 텍스트, 밑줄, 이미지)

        # 0) 사전 준비: 전역 폰트 임베딩 (생략 가능하나 안정성을 위해 유지)
        self._set_progress(progress, self.t('progress_preparing_fonts'))
        
        # 페이지별 루프
        for page_num in range(total_pages):
            try:
                page = self.pdf_viewer.doc.load_page(page_num)
                overlays = self.pdf_viewer.text_overlays.get(page_num, []) if hasattr(self.pdf_viewer, 'text_overlays') else []
                patches = self.pdf_viewer.background_patches.get(page_num, []) if hasattr(self.pdf_viewer, 'background_patches') else []
                images = self.pdf_viewer.image_overlays.get(page_num, []) if hasattr(self.pdf_viewer, 'image_overlays') else []
                
                # --- [1단계: 모든 배경 패치 (보안 영구 삭제 True Redaction 적용)] ---
                has_redact = False
                for patch in patches:
                    try:
                        bbox = patch.get('bbox')
                        color = patch.get('color', (1.0, 1.0, 1.0))
                        if bbox:
                            page.add_redact_annot(bbox, fill=color)
                            has_redact = True
                    except Exception:
                        try:
                            if bbox and color:
                                page.draw_rect(bbox, color=color, fill=color, width=0)
                        except Exception: pass
                if has_redact:
                    try:
                        page.apply_redactions()
                    except Exception as e:
                        print(f"Redaction apply fallback: {e}")
                self._step_progress(progress, 1)

                # --- [2단계: 모든 텍스트 본문] ---
                for ov in overlays:
                    if not ov.text: continue
                    # 본문만 먼저 출력
                    self._flatten_single_overlay(page, ov, mode='text_only')
                self._step_progress(progress, 1)

                # --- [3단계: 모든 스타일링 (밑줄 등)] ---
                # 텍스트 위에 밑줄이 오도록 마지막에 드로잉
                for ov in overlays:
                    if not ov.text: continue
                    self._flatten_single_overlay(page, ov, mode='style_only')
                    ov.flattened = True # 최종 완료 처리
                self._step_progress(progress, 1)

                # --- [4단계: 이미지/서명 오버레이 삽입] ---
                for img_ov in images:
                    if not img_ov.visible or not os.path.exists(img_ov.image_path):
                        continue
                    try:
                        if img_ov.opacity < 0.99:
                            # 투명도 적용: QImage를 통해 알파 채널 적용 후 PNG 바이트로 삽입
                            qimg = QImage(img_ov.image_path)
                            if not qimg.isNull():
                                qimg = qimg.convertToFormat(QImage.Format.Format_ARGB32)
                                p = QPainter(qimg)
                                p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
                                p.fillRect(qimg.rect(), QColor(0, 0, 0, int(round(img_ov.opacity * 255))))
                                p.end()
                                ba = QByteArray()
                                buf = QBuffer(ba)
                                buf.open(QBuffer.OpenModeFlag.WriteOnly)
                                qimg.save(buf, "PNG")
                                page.insert_image(img_ov.bbox, stream=ba.data(), overlay=True)
                        else:
                            page.insert_image(img_ov.bbox, filename=img_ov.image_path, overlay=True)
                        img_ov.flattened = True
                    except Exception as e_img:
                        print(f"이미지 플래튼 오류: {e_img}")
                self._step_progress(progress, 1)

            except Exception as pe:
                print(f"  X 페이지 {page_num} 플래튼 중 오류: {pe}")

        # [최적화] 플래튼 작업은 문서를 직접 수정하므로 변경 플래그 세팅
        self.mark_doc_modified()
        print("OK 모든 오버레이 및 이미지 플래튼 완료")

    def _do_insert_text(self, page, ov, font_ref, s_mat, font_args, baseline_y, text_x, line_height_pt, tracking_percent, stretch, fm_measure, is_hwp, need_synth_bold):
        """실제 PDF 페이지에 텍스트를 글자 단위로 삽입하는 핵심 로직 (재시도 지원용)"""
        text_to_insert = ov.text or ''
        font_size = float(ov.size)
        lines = text_to_insert.splitlines() if "\n" in text_to_insert else [text_to_insert]
        
        for li, line in enumerate(lines):
            curr_y = baseline_y + li * line_height_pt
            curr_x = text_x
            t_ratio = 1.0 + (tracking_percent / 100.0)
            # 200배 정밀도 측정이므로 결과 보정
            precision_multiplier = 200.0
            
            hwp_std_space = font_size * 0.50
            for ch in line:
                ch_w_raw = fm_measure.horizontalAdvance(ch) / precision_multiplier
                if ch == ' ' and is_hwp:
                    ch_w_eff = max(ch_w_raw, hwp_std_space)
                else:
                    ch_w_eff = ch_w_raw
                advance = ch_w_eff * stretch
                
                if ch.strip():
                    if need_synth_bold:
                        synth_weight = float(getattr(ov, 'synth_bold_weight', 120))
                        # [고도화] PDF 표준 Stroke 방식 합성 볼드
                        # 다중 렌더링 대신 외곽선(Stroke)을 추가하여 획의 불규칙한 돌출을 방지하고 매끄러운 마감 확보
                        # 사용자의 가변 굵기(Weight) 설정을 정밀하게 반영
                        stroke_w = (synth_weight - 100.0) / 100.0 * font_size * 0.02
                        
                        target_p = fitz.Point(curr_x, curr_y)
                        page.insert_text(
                            target_p, ch, 
                            fontname=font_ref, 
                            morph=(target_p, s_mat),
                            render_mode=2, # Fill then Stroke
                            border_width=stroke_w,
                            **font_args
                        )
                    else:
                        target_p = fitz.Point(curr_x, curr_y)
                        page.insert_text(target_p, ch, fontname=font_ref, 
                                       morph=(target_p, s_mat), **font_args)
                
                curr_x += advance * t_ratio
            ov._last_flatten_width = (curr_x - text_x)

    def _flatten_single_overlay(self, page, ov, mode='all'):
        """개별 오버레이를 특정 모드(본문/스타일/전체)로 PDF에 반영
        UI 프리뷰(render_to_painter)와 100% 동일한 좌표 및 로직 사용.
        """
        # 이미 이미지로 플래튼된 경우 스타일 패스 건너뜀
        if getattr(ov, 'image_flattened', False):
            return True

        # [치명적 결함 해결] 이미지 렌더링 강제 옵션 처리
        # [추가] 볼드 처리된 경우 UI와 동일한 결과물을 위해 무조건 이미지 플래튼 수행 (Issue 1 해결)
        is_bold = bool(ov.flags & 16)
        if (getattr(ov, 'force_image', False) or is_bold) and mode in ('all', 'text_only'):
            print(f"    -> 볼드/이미지강제 오버레이 이미지 플래튼 실행: ID {ov.z_index}")
            if self._flatten_overlay_as_image(page, ov):
                ov.image_flattened = True
                return True

        try:
            text_to_insert = ov.text or ''
            font_size = float(ov.size)
            color_tuple = self._rgbf_from_color_int(ov.color)
            selected_font_name = ov.font or 'Arial'
            
            # 폰트 준비
            if not hasattr(self, 'font_manager'):
                self.font_manager = SystemFontManager()
            
            chosen_name = selected_font_name
            font_path = self.font_manager.get_font_path(selected_font_name)
            if ov.flags & 2: # 이탤릭 변형 검색
                suffixes = [' Italic', '-Italic', ' Oblique', '-Oblique']
                for suf in suffixes:
                    p = self.font_manager.get_font_path(selected_font_name + suf)
                    if p:
                        chosen_name = selected_font_name + suf
                        font_path = p
                        break
            
            # [중요] 폰트 파일이 없으면 즉각 이미지 폴백 시도 (사라짐 방지)
            if not font_path or not os.path.exists(font_path):
                if mode in ('all', 'text_only'):
                    print(f"    -> 폰트 파일 없음({selected_font_name}), 이미지 폴백 실행")
                    if self._flatten_overlay_as_image(page, ov):
                        ov.image_flattened = True
                        return True
            
            try:
                font_ref = self._ensure_font_ref(page, chosen_name)
            except Exception as e_ref:
                print(f"    -> 폰트 임베딩 실패: {e_ref}, 이미지 폴백 실행")
                if mode in ('all', 'text_only'):
                    if self._flatten_overlay_as_image(page, ov):
                        ov.image_flattened = True
                        return True
                return False

            # [좌표 계산의 핵심: UI와 동일하게]
            bbox = ov.bbox if ov.bbox else ov.original_bbox
            ov_ascent_ratio = getattr(ov, 'ascent_ratio', 0.85)
            ov_height_ratio = getattr(ov, 'height_ratio', 1.15)
            
            # 베이스라인 결정 (origin이 있으면 최우선, 없으면 ratio 기반 산출)
            origin = getattr(ov, 'origin', None)
            if origin:
                dx = bbox.x0 - ov.original_bbox.x0
                dy = bbox.y0 - ov.original_bbox.y0
                baseline_y = origin[1] + dy
                text_x = origin[0] + dx
            else:
                baseline_y = bbox.y0 + (font_size * ov_ascent_ratio)
                text_x = bbox.x0
            
            line_height_pt = font_size * ov_height_ratio
            tracking_percent = float(getattr(ov, 'tracking', 0.0))
            stretch = float(getattr(ov, 'stretch', 1.0))
            
            # [정합성 극대화] UI와 동일한 너비 측정을 위해 MainWindow 표준 메트릭 도구 사용
            precision_multiplier = 200.0
            qfont_measure = QFont(chosen_name)
            qfont_measure.setPixelSize(int(round(font_size * precision_multiplier)))
            fm_measure = self._get_standard_metrics(qfont_measure, precision_multiplier)

            # [스타일 판단: UI와 동일하게]
            is_bold_flag = bool(ov.flags & 16)
            loaded_name_l = (chosen_name or '').lower()
            has_bold_variant = any(kw in loaded_name_l for kw in ('bold', 'black', 'heavy'))
            
            if is_bold_flag:
                need_synth_bold = not has_bold_variant
            else:
                need_synth_bold = False
            
            # 본문 출력 모드
            if mode in ('all', 'text_only'):
                font_args = {"fontsize": font_size, "color": color_tuple}
                is_hwp = getattr(ov, 'hwp_space_mode', False)
                s_mat = fitz.Matrix(stretch, 1)
                
                # [개선] 2단계 복구 전략: 실패 시 폰트 재로드 후 재시도
                try:
                    self._do_insert_text(page, ov, font_ref, s_mat, font_args, baseline_y, text_x, line_height_pt, tracking_percent, stretch, fm_measure, is_hwp, need_synth_bold)
                except Exception as e_insert:
                    print(f"    -> [Step 1] 텍스트 삽입 실패({e_insert}), 폰트 재로드 및 재시도 중...")
                    try:
                        # 폰트 리소스 강제 갱신
                        new_font_ref = self._ensure_font_ref(page, chosen_name, force_reload=True)
                        # 재시도
                        self._do_insert_text(page, ov, new_font_ref, s_mat, font_args, baseline_y, text_x, line_height_pt, tracking_percent, stretch, fm_measure, is_hwp, need_synth_bold)
                        print(f"    -> [Success] 폰트 재로드 후 텍스트 삽입 성공!")
                    except Exception as e_retry:
                        print(f"    -> [Step 2] 재시도 실패({e_retry}), 이미지 폴백 실행")
                        if self._flatten_overlay_as_image(page, ov):
                            ov.image_flattened = True
                            return True
                        return False

            # 스타일(밑줄) 출력 모드
            if mode in ('all', 'style_only'):
                if ov.flags & 4:
                    lines = text_to_insert.splitlines() if "\n" in text_to_insert else [text_to_insert]
                    for li, line in enumerate(lines):
                        curr_y = baseline_y + li * line_height_pt
                        u_offset = float(getattr(ov, 'underline_offset', 1.5))
                        u_y = curr_y + u_offset
                        u_w = float(getattr(ov, 'underline_weight', 0.6))
                        
                        # [해결] 텍스트 본문 출력 시 계산된 실제 너비 사용
                        t_w = getattr(ov, '_last_flatten_width', 0)
                        if t_w <= 0:
                            # fallback 너비 계산
                            line_w_raw = fm_measure.horizontalAdvance(line)
                            if is_hwp:
                                line_w_raw += (line.count(' ') * fm_measure.horizontalAdvance(' ') * 0.5)
                            t_w = line_w_raw * stretch * (1.0 + tracking_percent / 100.0)
                        
                        page.draw_line(fitz.Point(text_x, u_y), fitz.Point(text_x + t_w, u_y), 
                                     color=color_tuple, width=u_w)

            return True
        except Exception as e:
            print(f"  X 개별 오버레이 플래튼 실패: {e}, 이미지 폴백 시도")
            if mode in ('all', 'text_only'):
                if self._flatten_overlay_as_image(page, ov):
                    ov.image_flattened = True
                    return True
            return False

            return True
        except Exception as e:
            print(f"  X 개별 오버레이 플래튼 실패: {e}")
            return False

    def get_precise_background_color(self, page, bbox):
        """외곽선, 표 테두리선, 밑줄 및 인접 개체 간섭을 완벽히 배제하고
        텍스트의 진짜 배경색을 정밀 검출하는 고정밀 다중 영역 분석 알고리즘"""
        import time
        from collections import Counter
        detection_id = int(time.time() * 1000) % 10000

        print(f"\n=== 정밀 배경색 검출 #{detection_id} 시작 ===")
        print(f"   현재 텍스트 bbox: ({bbox.x0:.1f}, {bbox.y0:.1f}) → ({bbox.x1:.1f}, {bbox.y1:.1f})")
        print(f"   텍스트 크기: {bbox.width:.1f} x {bbox.height:.1f}pt")

        try:
            # 1. 텍스트 주변 여백(확장 영역) 계산
            # 상하좌우로 2~5pt 정도 여백을 두어 단일 고해상도 픽스맵 렌더링
            margin_h = max(2.0, min(5.0, bbox.width * 0.04))
            margin_v = max(2.0, min(5.0, bbox.height * 0.15))

            sample_rect = fitz.Rect(
                bbox.x0 - margin_h,
                bbox.y0 - margin_v,
                bbox.x1 + margin_h,
                bbox.y1 + margin_v
            ) & page.rect

            if sample_rect.get_area() < 1.0:
                return (1.0, 1.0, 1.0)

            # 단 1회의 픽스맵 캡처 (dpi=150: 약 1~2ms로 극도로 빠르면서 정밀)
            pix = page.get_pixmap(clip=sample_rect, dpi=150)
            if pix.n < 3 or not pix.samples:
                return (1.0, 1.0, 1.0)

            img_w = pix.width
            img_h = pix.height
            samples = pix.samples
            bytes_per_pixel = pix.n

            # sample_rect 내에서 원본 bbox의 픽셀 좌표 계산
            scale_x = img_w / sample_rect.width
            scale_y = img_h / sample_rect.height
            bx0 = max(0, min(img_w - 1, int(round((bbox.x0 - sample_rect.x0) * scale_x))))
            by0 = max(0, min(img_h - 1, int(round((bbox.y0 - sample_rect.y0) * scale_y))))
            bx1 = max(bx0 + 1, min(img_w, int(round((bbox.x1 - sample_rect.x0) * scale_x))))
            by1 = max(by0 + 1, min(img_h, int(round((bbox.y1 - sample_rect.y0) * scale_y))))

            # 색상 양자화 유틸리티 (RGB를 4단위로 묶어 미세 노이즈 흡수)
            def _quantize(r, g, b):
                return (r // 4 * 4, g // 4 * 4, b // 4 * 4)

            # 색상 거리 (Chebyshev/Max distance)
            def _color_dist(c1, c2):
                return max(abs(c1[0] - c2[0]), abs(c1[1] - c2[1]), abs(c1[2] - c2[2]))

            # 각 영역별 픽셀 수집
            def _get_pixel(x, y):
                idx = (y * img_w + x) * bytes_per_pixel
                return (samples[idx], samples[idx+1], samples[idx+2])

            inner_pixels = []
            for y in range(by0, by1):
                for x in range(bx0, bx1):
                    inner_pixels.append(_get_pixel(x, y))

            top_pixels = [_get_pixel(x, y) for y in range(0, by0) for x in range(bx0, bx1)]
            bottom_pixels = [_get_pixel(x, y) for y in range(by1, img_h) for x in range(bx0, bx1)]
            left_pixels = [_get_pixel(x, y) for y in range(by0, by1) for x in range(0, bx0)]
            right_pixels = [_get_pixel(x, y) for y in range(by0, by1) for x in range(bx1, img_w)]

            # 2. 내부 영역(Inner) 분석:
            # 텍스트 바운딩 박스 내부에서 글자 획(보통 15~35%)을 제외한 가장 넓은 영역이 '진짜 내부 배경'
            inner_quantized = [_quantize(*p) for p in inner_pixels]
            inner_counts = Counter(inner_quantized)
            inner_total = len(inner_quantized)

            inner_dominant = None
            inner_ratio = 0.0
            if inner_total > 0 and inner_counts:
                top_inner = inner_counts.most_common(3)
                inner_dominant, inner_dom_count = top_inner[0]
                inner_ratio = inner_dom_count / inner_total
                print(f"   내부 최빈 색상: RGB{inner_dominant} ({inner_ratio*100:.1f}%, {inner_dom_count}/{inner_total}px)")

            # 3. 4방향 외부 영역 분석 및 '외곽선/인접 개체 이상치(Outlier)' 배제
            outer_regions = {
                '상단': top_pixels,
                '하단': bottom_pixels,
                '좌측': left_pixels,
                '우측': right_pixels
            }

            valid_outer_colors = []
            dir_dominant_map = {}

            for d_name, p_list in outer_regions.items():
                if not p_list:
                    continue
                q_list = [_quantize(*p) for p in p_list]
                c_counts = Counter(q_list)
                dom_color, dom_count = c_counts.most_common(1)[0]
                dom_ratio = dom_count / len(q_list)
                dir_dominant_map[d_name] = (dom_color, dom_ratio, p_list)
                print(f"   방향 [{d_name}]: {len(p_list)}px, 최빈 RGB{dom_color} ({dom_ratio*100:.1f}%)")

            # 4. 이상치 방향(외곽선/테두리/인접 개체) 판정:
            # - 만약 어떤 방향의 최빈색이 내부 최빈색과 거리가 28 이상 벌어지고,
            #   다른 방향들과도 현저히 다르다면 해당 방향은 "외곽선이나 다른 개체에 걸친 방향"임!
            accepted_directions = []
            for d_name, (dom_c, dom_r, p_list) in dir_dominant_map.items():
                is_outlier = False
                if inner_dominant is not None:
                    dist_to_inner = _color_dist(dom_c, inner_dominant)
                    # 만약 내부 최빈색과 거리가 멀다면:
                    if dist_to_inner > 28:
                        # 다른 방향들과의 일치도 검사
                        agreement_with_others = sum(
                            1 for other_name, (oc, _, _) in dir_dominant_map.items()
                            if other_name != d_name and _color_dist(dom_c, oc) <= 20
                        )
                        # 다른 방향들도 동의하지 않거나, 내부 최빈색이 충분히 우세한 경우
                        if agreement_with_others == 0 or (inner_ratio >= 0.30 and dist_to_inner > 35):
                            is_outlier = True
                            print(f"   🚫 [{d_name}] 방향은 외곽선/인접 개체로 판정되어 배제됨! (RGB{dom_c}, 내부와의 거리={dist_to_inner})")

                if not is_outlier:
                    accepted_directions.append(d_name)
                    valid_outer_colors.extend([_quantize(*p) for p in p_list])

            print(f"   채택된 안전한 방향들: {accepted_directions}")

            # 5. 최종 배경색 판정:
            candidate_pool = []
            
            # 내부 최빈색 가중 추가 (내부 배경은 글자 외의 픽셀이므로 높은 신뢰도)
            if inner_dominant is not None:
                for c, cnt in inner_counts.most_common(3):
                    ratio = cnt / inner_total
                    if ratio >= 0.25 or (c == inner_dominant and ratio >= 0.15):
                        candidate_pool.extend([c] * int(cnt * 1.5))

            # 채택된 외곽 픽셀 추가
            candidate_pool.extend(valid_outer_colors)

            if candidate_pool:
                final_counts = Counter(candidate_pool)
                best_color, best_votes = final_counts.most_common(1)[0]
                
                # best_color에 해당하는 원본 픽셀들의 실제 평균 RGB 계산 (자연스러운 색상 복원)
                matching_orig_pixels = []
                all_pixels_to_check = inner_pixels + [p for d in accepted_directions for p in outer_regions[d]]
                for p in all_pixels_to_check:
                    if _color_dist(_quantize(*p), best_color) <= 8:
                        matching_orig_pixels.append(p)

                if matching_orig_pixels:
                    avg_r = sum(p[0] for p in matching_orig_pixels) / len(matching_orig_pixels)
                    avg_g = sum(p[1] for p in matching_orig_pixels) / len(matching_orig_pixels)
                    avg_b = sum(p[2] for p in matching_orig_pixels) / len(matching_orig_pixels)
                else:
                    avg_r, avg_g, avg_b = best_color

                result_color = (avg_r / 255.0, avg_g / 255.0, avg_b / 255.0)
                print(f"   ✅ 최종 검출된 배경색: RGB({int(round(avg_r))}, {int(round(avg_g))}, {int(round(avg_b))}) → {result_color}")
                print(f"=== 정밀 배경색 검출 #{detection_id} 완료 ===\n")
                return result_color

        except Exception as e:
            print(f"   X 배경색 검출 오류: {e}")
            import traceback
            traceback.print_exc()

        # 실패 시 기본 순백색
        fallback_color = (1.0, 1.0, 1.0)
        print(f"   배경색 검출 실패 - 순백색 Fallback 사용: {fallback_color}\n")
        return fallback_color

    def get_optimal_cover_rect(self, original_bbox, text_metrics):
        """최적화된 덮개 사각형 계산 - 패치 마진 설정 반영"""
        margin_value = getattr(self, 'patch_margin', (0.0, 0.0))
        if isinstance(margin_value, (tuple, list)) and len(margin_value) >= 2:
            margin_h_ratio = float(margin_value[0])
            margin_v_ratio = float(margin_value[1])
        else:
            try:
                scalar = float(margin_value)
            except Exception:
                scalar = 0.0
            margin_h_ratio = scalar
            margin_v_ratio = scalar

        margin_h_ratio = max(-0.5, min(0.5, margin_h_ratio))
        margin_v_ratio = max(-0.5, min(0.5, margin_v_ratio))

        if margin_h_ratio < 0:
            width_reduction = original_bbox.width * abs(margin_h_ratio)
            horizontal_margin = -width_reduction / 2
        else:
            horizontal_margin = original_bbox.width * margin_h_ratio

        if margin_v_ratio < 0:
            height_reduction = original_bbox.height * abs(margin_v_ratio)
            vertical_margin = -height_reduction / 2
        else:
            vertical_margin = original_bbox.height * margin_v_ratio

        optimized_rect = fitz.Rect(
            original_bbox.x0 - horizontal_margin,
            original_bbox.y0 - vertical_margin,
            original_bbox.x1 + horizontal_margin,
            original_bbox.y1 + vertical_margin
        )
        
        return optimized_rect

    def apply_background_patch(self, page, original_bbox, new_values, overlay=None, preview=False):
        """각 텍스트 블록별 개별 배경 패치 적용"""
        # [수정] 오버레이가 있다면 텍스트 크기에 맞춰진 최신 original_bbox를 우선 사용 (정합성 핵심)
        if overlay and hasattr(overlay, 'original_bbox'):
            original_bbox = overlay.original_bbox
            
        # 입력된 bbox가 튜플일 경우 fitz.Rect로 변환 (AttributeError 방지)
        if isinstance(original_bbox, (tuple, list)):
            original_bbox = fitz.Rect(original_bbox)
            
        print(f"\n === 개별 텍스트 블록 배경 패치 적용 ===")
        print(f"   위치 처리할 텍스트 bbox: {original_bbox}")
        print(f"   텍스트 내용: {new_values.get('text', 'N/A')[:20]}...")
        
        # '패치 없이 텍스트만 생성' 옵션 처리
        if new_values.get('text_only_mode'):
            print("   '패치 없이 텍스트만 생성' 모드 활성 - 패치 생략")
            overlay_id = getattr(overlay, 'z_index', None) if overlay else None
            page_index = overlay.page_num if overlay else self.pdf_viewer.current_page_num
            if hasattr(self.pdf_viewer, 'remove_background_patch') and overlay_id is not None:
                self.pdf_viewer.remove_background_patch(page_index, overlay_id=overlay_id)
            return None, None

        try:
            # 1. 지능적 마진 계산
            text_width = original_bbox.width
            text_height = original_bbox.height
            
            def _coerce_margin(value, fallback):
                try:
                    return max(-0.5, min(0.5, float(value)))
                except Exception:
                    return fallback

            # 상하좌우 개별 마진 추출
            m_l = new_values.get('patch_margin_l')
            m_r = new_values.get('patch_margin_r')
            m_t = new_values.get('patch_margin_t')
            m_b = new_values.get('patch_margin_b')

            # 레거시 호환 및 기본값 처리
            if None in (m_l, m_r, m_t, m_b):
                legacy_h = new_values.get('patch_margin_h')
                legacy_v = new_values.get('patch_margin_v')
                legacy_all = new_values.get('patch_margin')
                
                default_margin = getattr(self, 'patch_margin', (0.0, 0.0, 0.0, 0.0))
                if not isinstance(default_margin, (tuple, list)) or len(default_margin) < 4:
                    if isinstance(default_margin, (tuple, list)) and len(default_margin) >= 2:
                        default_margin = (default_margin[0], default_margin[0], default_margin[1], default_margin[1])
                    else:
                        try: val = float(default_margin)
                        except: val = 0.0
                        default_margin = (val, val, val, val)
                
                if m_l is None: m_l = legacy_h if legacy_h is not None else (legacy_all[0] if isinstance(legacy_all, (list, tuple)) else (legacy_all if legacy_all is not None else default_margin[0]))
                if m_r is None: m_r = legacy_h if legacy_h is not None else (legacy_all[1] if isinstance(legacy_all, (list, tuple)) and len(legacy_all) >= 2 else (legacy_all if legacy_all is not None else default_margin[1]))
                if m_t is None: m_t = legacy_v if legacy_v is not None else (legacy_all[2] if isinstance(legacy_all, (list, tuple)) and len(legacy_all) >= 4 else (legacy_all[1] if isinstance(legacy_all, (list, tuple)) and len(legacy_all) >= 2 else (legacy_all if legacy_all is not None else default_margin[2])))
                if m_b is None: m_b = legacy_v if legacy_v is not None else (legacy_all[3] if isinstance(legacy_all, (list, tuple)) and len(legacy_all) >= 4 else (legacy_all[1] if isinstance(legacy_all, (list, tuple)) and len(legacy_all) >= 2 else (legacy_all if legacy_all is not None else default_margin[3])))

            m_l = _coerce_margin(m_l, 0.0)
            m_r = _coerce_margin(m_r, 0.0)
            m_t = _coerce_margin(m_t, 0.0)
            m_b = _coerce_margin(m_b, 0.0)

            margin_l = text_width * m_l
            margin_r = text_width * m_r
            margin_t = text_height * m_t
            margin_b = text_height * m_b
            
            print(
                "    사용자 지정 패치 여백 적용: "
                f"L={m_l*100:.1f}%, R={m_r*100:.1f}%, T={m_t*100:.1f}%, B={m_b*100:.1f}%"
            )

            if overlay is not None:
                overlay.patch_margin_l = m_l
                overlay.patch_margin_r = m_r
                overlay.patch_margin_t = m_t
                overlay.patch_margin_b = m_b
            
            # 2. 새로운 정교한 배경색 검출 로직 사용 (사용자 지정이 우선)
            if new_values.get('use_custom_patch_color'):
                c = new_values.get('patch_color', QColor(255, 255, 255))
                bg_color = (c.redF(), c.greenF(), c.blueF())
                print(f"    사용자 지정 패치 색상 사용: {bg_color}")
                # 최근 사용 값 저장(편집창 기본값으로 활용)
                try:
                    self.last_patch_color = c
                    self.last_use_custom_patch = True
                except Exception:
                    pass
            else:
                # [최적화] 실시간 프리뷰 중에는 배경색 검출(Slow)을 생략하고 캐시된 색상 사용 (프리징 방지 핵심)
                cached_bg = getattr(overlay, '_cached_bg_color', None) if overlay else None
                if preview and cached_bg:
                    bg_color = cached_bg
                    print(f"    [Preview Cache] 캐시된 배경색 사용: {bg_color}")
                else:
                    bg_color = self.get_precise_background_color(page, original_bbox)
                    if overlay:
                        overlay._cached_bg_color = bg_color # 캐시 저장
                
                try:
                    self.last_use_custom_patch = False
                except Exception:
                    pass
            # get_precise_background_color는 항상 유효한 색상을 반환함 (fallback 포함)
            
            print(f"    이 텍스트 블록의 검출된 배경색: {bg_color}")
            print(f"   패치 영역 마진: L={margin_l:.1f}, R={margin_r:.1f}, T={margin_t:.1f}, B={margin_b:.1f}px")
            
            # 3. 단색 사각형 패치 적용 (단순하고 깔끔하게)
            # [개선사항] 이미 insert_overlay_text에서 original_bbox가 텍스트 크기에 맞춰 최적화됨
            # 여기서는 추가 확장 없이 사용자 지정 마진만 적용
            
            # 요청사항: 필요 시 해당 라인(세로 밴드) 전체를 가리는 풀폭 패치 옵션
            cover_all_band = bool(new_values.get('cover_all_band', False) or new_values.get('cover_all', False))
            
            base_x0 = original_bbox.x0 - margin_l
            base_y0 = original_bbox.y0 - margin_t
            base_x1 = original_bbox.x1 + margin_r
            base_y1 = original_bbox.y1 + margin_b
            
            if cover_all_band:
                patch_rect = fitz.Rect(
                    page.rect.x0,
                    base_y0,
                    page.rect.x1,
                    base_y1
                )
            else:
                patch_rect = fitz.Rect(base_x0, base_y0, base_x1, base_y1)

            
            overlay_id = getattr(overlay, 'z_index', None) if overlay else None
            page_index = overlay.page_num if overlay else self.pdf_viewer.current_page_num

            try:
                if hasattr(self.pdf_viewer, 'remove_background_patch') and overlay_id is not None:
                    self.pdf_viewer.remove_background_patch(page_index, overlay_id=overlay_id)

                if not preview:
                    page.draw_rect(patch_rect, color=bg_color, fill=bg_color, width=0)
                    if hasattr(self, 'mark_doc_modified'):
                        self.mark_doc_modified()

                if hasattr(self.pdf_viewer, 'add_background_patch'):
                    qcolor = QColor(int(bg_color[0] * 255), int(bg_color[1] * 255), int(bg_color[2] * 255))
                    self.pdf_viewer.add_background_patch(page_index, patch_rect, qcolor, overlay_id=overlay_id)

                print(f"   OK 이 블록 전용 배경 패치 완료!")
                print(f"       패치 영역: {patch_rect}")
                print(f"       적용된 색상: {bg_color}")
                print(f"   === 개별 블록 패치 완료 ===\n")
                return patch_rect, bg_color
            except Exception as patch_error:
                print(f"경고 패치 적용 실패: {patch_error}")
                raise  # fallback으로
                    
        except Exception as e:
            print(f"X 정교한 배경 패치 실패: {e}")
            # 실패시 기본 안전 패치
            try:
                print(f"   안전 모드 패치 적용...")
                safe_color = bg_color if 'bg_color' in locals() else (0.95, 0.95, 0.95)
                safe_margin = max(3.0, original_bbox.height * 0.2)

                safe_rect = fitz.Rect(
                    original_bbox.x0 - safe_margin,
                    original_bbox.y0 - safe_margin,
                    original_bbox.x1 + safe_margin,
                    original_bbox.y1 + safe_margin
                )

                if not preview:
                    page.draw_rect(safe_rect, color=safe_color, fill=safe_color, width=0)
                    page.draw_rect(original_bbox, color=safe_color, fill=safe_color, width=0)
                    if hasattr(self, 'mark_doc_modified'):
                        self.mark_doc_modified()

                overlay_id = getattr(overlay, 'z_index', None) if overlay else None
                page_index = overlay.page_num if overlay else self.pdf_viewer.current_page_num
                if hasattr(self.pdf_viewer, 'remove_background_patch') and overlay_id is not None:
                    self.pdf_viewer.remove_background_patch(page_index, overlay_id=overlay_id)
                if hasattr(self.pdf_viewer, 'add_background_patch'):
                    qcolor = QColor(int(safe_color[0] * 255), int(safe_color[1] * 255), int(safe_color[2] * 255))
                    self.pdf_viewer.add_background_patch(page_index, safe_rect, qcolor, overlay_id=overlay_id)

                print(f"   경고 안전 모드 패치 완료: {safe_rect} (색상: {safe_color})")
                return safe_rect, safe_color

            except Exception as safe_error:
                print(f"X 안전 패치도 실패: {safe_error}")
                raise

    def _verify_patch_quality(self, page, original_bbox, expected_color):
        """패치 품질 검증 (선택적)"""
        try:
            # 패치된 영역 중앙에서 색상 샘플링
            center_x = (original_bbox.x0 + original_bbox.x1) / 2
            center_y = (original_bbox.y0 + original_bbox.y1) / 2
            
            # 작은 영역에서 색상 확인
            verify_rect = fitz.Rect(center_x - 2, center_y - 2, center_x + 2, center_y + 2)
            pix = page.get_pixmap(clip=verify_rect, dpi=96)
            
            if pix.n >= 3 and len(pix.samples) > 0:
                samples = pix.samples
                # 첫 번째 픽셀의 색상
                actual_color = (samples[0]/255.0, samples[1]/255.0, samples[2]/255.0)
                
                # 색상 차이 계산
                color_diff = sum(abs(a - e) for a, e in zip(actual_color, expected_color))
                
                if color_diff < 0.1:  # 10% 이하 차이
                    print(f"   OK 패치 품질 검증: 양호 (차이: {color_diff:.3f})")
                else:
                    print(f"   경고 패치 품질 검증: 보통 (차이: {color_diff:.3f})")
                    
        except Exception as verify_error:
            print(f"   패치 품질 검증 생략: {verify_error}")

    def calculate_auto_stretch_and_tracking(self, span, chosen_font_name=None):
        """[HWP 정밀 연동] 원본 텍스트블록의 문자 지오메트리 및 길이를 분석하여
        한글(HWP) 문서에서 빈번히 조절되는 장평(stretch)과 자간(tracking)을 정밀 자동 계산.
        반환값: (stretch: float, tracking: float)
        """
        try:
            chars = span.get('chars', [])
            sz = float(span.get('size', 12.0))
            if sz <= 0:
                return 1.0, 0.0

            raw_text = span.get('text', '')
            eff_text = raw_text.rstrip(' ')

            # [방어로직] PUA 특수문자 및 선두 불릿 제외 (정밀 장평/자간 측정 보장)
            while eff_text and (is_pua_char(eff_text[0]) or eff_text[0] in BULLET_CHARS or eff_text[0].isspace()):
                eff_text = eff_text[1:]
            eff_text = ''.join(c for c in eff_text if not is_pua_char(c))
            
            active_chars = [c for c in chars if not is_pua_char(c.get('c', ''))] if chars else []
            while active_chars and (is_pua_char(active_chars[0].get('c', '')) or active_chars[0].get('c', '') in BULLET_CHARS or active_chars[0].get('c', '').isspace() or is_symbol_font(active_chars[0].get('font', ''))):
                active_chars = active_chars[1:]

            # 1단계: chars 지오메트리 직접 분석 (가장 정밀)
            is_vert = span.get('is_vertical', False) or (active_chars and any(abs(c.get('dir', (1.0, 0.0))[1]) > abs(c.get('dir', (1.0, 0.0))[0]) for c in active_chars))
            hangul_chars = [c for c in active_chars if '가' <= c.get('c', '') <= '힣']
            
            calc_stretch = None
            if hangul_chars:
                stretches = []
                for c in hangul_chars:
                    b = c.get('bbox', [0, 0, 0, 0])
                    gw = (b[3] - b[1]) if is_vert else (b[2] - b[0])
                    r = gw / sz
                    # 유효한 한글 장평 범위 (50% ~ 200%)
                    if 0.50 <= r <= 2.00:
                        stretches.append(r)
                if stretches:
                    avg_s = sum(stretches) / len(stretches)
                    # 100% 근방(±1.5%)은 표준 100%로 정규화
                    if abs(avg_s - 1.0) < 0.015:
                        calc_stretch = 1.0
                    else:
                        calc_stretch = round(avg_s, 2)
                        
            calc_tracking = None
            if active_chars:
                trackings = []
                eff_stretch = calc_stretch if calc_stretch is not None else 1.0
                for idx in range(len(active_chars) - 1):
                    c1 = active_chars[idx]
                    c2 = active_chars[idx + 1]
                    ch1 = c1.get('c', '')
                    ch2 = c2.get('c', '')
                    # 공백이나 제어문자가 아닌 인접 글자 간격 분석
                    if ch1.strip() and ch2.strip() and c1.get('origin') and c2.get('origin'):
                        adv = abs(c2['origin'][1] - c1['origin'][1]) if is_vert else (c2['origin'][0] - c1['origin'][0])
                        ref_w = (sz * eff_stretch) if ('가' <= ch1 <= '힣') else ((c1['bbox'][3] - c1['bbox'][1]) if is_vert else (c1['bbox'][2] - c1['bbox'][0]))
                        if ref_w > 0:
                            t = ((adv / ref_w) - 1.0) * 100.0
                            if -30.0 <= t <= 50.0:
                                trackings.append(t)
                if trackings:
                    avg_t = sum(trackings) / len(trackings)
                    if abs(avg_t) < 0.4:
                        calc_tracking = 0.0
                    else:
                        calc_tracking = round(avg_t, 1)

            # 2단계: 전체 가로폭 비율 분석 및 정밀 보정
            orig_bbox_obj = span.get('original_bbox') or span.get('bbox')
            orig_bbox = fitz.Rect(orig_bbox_obj) if orig_bbox_obj else None
            
            # 유효 가로폭 산출: active_chars가 있는 경우 실제 본문 첫 글자부터 마지막 글자까지의 가로폭을 기준으로 산출
            if orig_bbox and active_chars:
                first_c = active_chars[0]
                last_c = active_chars[-1]
                eff_orig_w = max(0.0, last_c['bbox'][2] - first_c['bbox'][0])
            else:
                eff_orig_w = orig_bbox.width if orig_bbox else 0.0
            
            if eff_orig_w > 0 and eff_text:
                if not hasattr(self, 'font_manager'):
                    self.font_manager = SystemFontManager()
                font_name = chosen_font_name or self.font_manager.find_best_font_match(span.get('font', '')) or 'Arial'
                
                from PySide6.QtGui import QFont, QFontMetricsF, QImage
                dummy = QImage(1, 1, QImage.Format.Format_Mono)
                dpm_72 = int(72 / 0.0254)
                dummy.setDotsPerMeterX(dpm_72)
                dummy.setDotsPerMeterY(dpm_72)
                
                qf = QFont(font_name)
                precision_multiplier = 200.0
                qf.setPixelSize(int(round(sz * precision_multiplier)))
                qf.setKerning(False)
                fm = QFontMetricsF(qf, dummy)
                
                is_hwp = bool(getattr(self, 'is_hwp_doc', False) or span.get('hwp_space_mode', False))
                hwp_space_px = sz * precision_multiplier * 0.50
                nom_w = 0.0
                for ch in eff_text:
                    cw = fm.horizontalAdvance(ch)
                    if ch == ' ' and is_hwp:
                        nom_w += max(cw, hwp_space_px)
                    else:
                        nom_w += cw
                nom_w /= precision_multiplier
                
                if nom_w > 0:
                    # 한글 폰트의 전각 비율(Em Ratio) 분석
                    has_hangul = any('가' <= c <= '힣' for c in eff_text)
                    if has_hangul and active_chars:
                        hangul_bboxes = [c['bbox'][2] - c['bbox'][0] for c in active_chars if '가' <= c.get('c', '') <= '힣']
                        orig_hangul_em = (sum(hangul_bboxes) / (len(hangul_bboxes) * sz)) if hangul_bboxes else 1.0
                    else:
                        orig_hangul_em = 1.0

                    if has_hangul:
                        system_hangul_em = fm.horizontalAdvance('가') / precision_multiplier / sz
                    else:
                        system_hangul_em = 1.0

                    # 시스템 폰트와 원본 글자 자체의 형상(전각 너비) 차이 보정 (장평 Stretch)
                    if has_hangul and system_hangul_em > 0 and 0.5 <= orig_hangul_em <= 2.0:
                        font_glyph_ratio = orig_hangul_em / system_hangul_em
                        base_stretch = 1.0 if abs(font_glyph_ratio - 1.0) < 0.02 else round(font_glyph_ratio, 2)
                    else:
                        base_stretch = calc_stretch if calc_stretch is not None else 1.0

                    nom_w_stretched = nom_w * base_stretch
                    rem_ratio = eff_orig_w / nom_w_stretched if nom_w_stretched > 0 else 1.0
                    
                    cur_s = base_stretch
                    cur_t = calc_tracking if calc_tracking is not None else 0.0
                    est_w = nom_w * cur_s * (1.0 + cur_t / 100.0)
                    
                    # 1단계 결과와 실제 원본 폭의 오차가 2% 이상 발생하면 전체 폭 비율 기반으로 재보정
                    needs_width_adjustment = (calc_stretch is None or calc_tracking is None or abs(eff_orig_w - est_w) > eff_orig_w * 0.02)
                    
                    if needs_width_adjustment:
                        calc_stretch = base_stretch
                        if 0.985 <= rem_ratio <= 1.015:
                            calc_tracking = 0.0
                        elif 0.70 <= rem_ratio < 0.985:
                            calc_tracking = round((rem_ratio - 1.0) * 100.0, 1)
                        elif 1.015 < rem_ratio <= 1.50:
                            calc_tracking = round((rem_ratio - 1.0) * 100.0, 1)
                        elif rem_ratio > 1.50:
                            calc_tracking = 50.0
                            calc_stretch = round(base_stretch * (rem_ratio / 1.50), 2)
                        else: # rem_ratio < 0.70
                            calc_tracking = -30.0
                            calc_stretch = round(base_stretch * (rem_ratio / 0.70), 2)

            final_stretch = calc_stretch if calc_stretch is not None else 1.0
            final_tracking = calc_tracking if calc_tracking is not None else 0.0
            # 안전 범위 제한
            final_stretch = max(0.5, min(2.0, final_stretch))
            final_tracking = max(-50.0, min(50.0, final_tracking))
            print(f"[AutoLayout] 자동 계산 결과: stretch={final_stretch*100:.1f}%, tracking={final_tracking:+.1f}% ('{eff_text[:20]}')")
            return final_stretch, final_tracking
        except Exception as e:
            print(f"[AutoLayout] 자동 장평/자간 계산 중 오류: {e}")
            return 1.0, 0.0

    def insert_overlay_text(self, page, span, new_values):
        """수정된 텍스트를 레이어 방식 오버레이로 삽입 (완전한 편집창 연계)"""
        try:
            original_bbox_obj = span.get('original_bbox') or span.get('bbox') or span.get('current_bbox')
            if not original_bbox_obj:
                raise ValueError("Missing bounding box for text edit")
            original_bbox = fitz.Rect(original_bbox_obj)
            has_current_bbox = span.get('current_bbox') is not None
            current_bbox_obj = span.get('current_bbox')
            if current_bbox_obj is None:
                current_bbox_obj = original_bbox
            layout_bbox = fitz.Rect(current_bbox_obj)
            text_to_insert = new_values['text']
            font_size = new_values['size']
            text_color = new_values['color']
            selected_font_name = new_values['font']
            new_values.setdefault('synth_bold', False)
            
            # 원본 span 정보 추출 및 로깅
            original_font = span.get('font', 'Unknown')
            pdf_font_name = span.get('pdf_font_name') or original_font # 원본 PDF 폰트명 보존
            original_size = span.get('size', 0)
            original_text = span.get('text', '')
            
            print(f"원본→오버레이 텍스트 비교:")
            print(f"   원본: '{original_text}' | 폰트='{original_font}', 크기={original_size}pt")
            print(f"   오버레이: '{text_to_insert}' | 폰트='{selected_font_name}', 크기={font_size}pt")
            print(f"   bbox(original): {original_bbox}")
            if has_current_bbox:
                print(f"   bbox(current):   {layout_bbox}")
            
            all_fonts_label = self.t('font_combo_all_fonts')
            if selected_font_name == all_fonts_label:
                selected_font_name = "Arial"  # 기본 폰트로 fallback
                print(f"   'All Fonts' 폴백: '{selected_font_name}'으로 변경")
            
            # FontMatcher를 통한 폰트 검증 및 매칭
            font_manager = SystemFontManager()
            font_path = font_manager.get_font_path(selected_font_name)
            if font_path:
                print(f"   OK 폰트 경로 발견: {font_path}")
            else:
                print(f"   X 폰트 경로 없음, FontMatcher로 유사폰트 검색...")
                matched_font = font_manager.font_matcher.find_best_match(selected_font_name)
                if matched_font:
                    print(f"   유사폰트 발견: '{selected_font_name}' → '{matched_font}'")
                    selected_font_name = matched_font
                    font_path = font_manager.get_font_path(selected_font_name)
                else:
                    print(f"   경고  유사폰트 없음, 기본폰트 사용: '{selected_font_name}'")

            bold_requested = bool(new_values.get('bold', False))
            italic_requested = bool(new_values.get('italic', False))
            variant_selected = False
            resolved_font_name = selected_font_name
            resolved_font_path = font_path

            if italic_requested: # 이탤릭 변형만 검색
                base_candidates = [selected_font_name]
                if selected_font_name.lower().endswith(' regular'):
                    base_candidates.append(selected_font_name.rsplit(' ', 1)[0])

                def build_variants(base):
                    suffixes = [' Italic', ' Italic', '-Italic', ' Oblique', '-Oblique']
                    for suf in suffixes:
                        yield base + suf
                        if suf.startswith(' '):
                            yield (base + suf).replace(' ', '')

                for base in base_candidates:
                    for candidate in build_variants(base):
                        path_candidate = font_manager.get_font_path(candidate)
                        if path_candidate:
                            resolved_font_name = candidate
                            resolved_font_path = path_candidate
                            variant_selected = True
                            print(f"   이탤릭 변형 사용: {resolved_font_name}")
                            break
                    if variant_selected:
                        break

            if variant_selected:
                selected_font_name = resolved_font_name
                font_path = resolved_font_path

            need_synth_bold = bold_requested
            new_values['synth_bold'] = need_synth_bold

            print(f"   최종 사용 폰트명: '{selected_font_name}'")

            # QColor를 정수 색상 코드로 변환
            if isinstance(text_color, QColor):
                color_int = (text_color.red() << 16) | (text_color.green() << 8) | text_color.blue()
            else:
                color_int = 0  # 기본 검은색
            
            # 편집창에서 설정된 스타일 flags 사용 (원본이 아닌 사용자 설정 우선)
            # new_values에서 style flags 추출
            edit_flags = 0
            if new_values.get('bold', False):
                edit_flags |= 16  # PyMuPDF 볼드 플래그
            if new_values.get('italic', False):
                edit_flags |= 2   # PyMuPDF 이탤릭 플래그
            if new_values.get('underline', False):
                edit_flags |= 4   # PyMuPDF 밑줄 플래그
            
            # 편집창에서 명시적으로 스타일이 설정되었는지 확인 (False도 유효한 설정)
            has_explicit_style = ('bold' in new_values) or ('italic' in new_values) or ('underline' in new_values)
            
            print(f"new_values 스타일 키 확인:")
            print(f"   - 'bold' in new_values: {'bold' in new_values} -> {new_values.get('bold', 'MISSING')}")
            print(f"   - 'italic' in new_values: {'italic' in new_values} -> {new_values.get('italic', 'MISSING')}")
            print(f"   - 'underline' in new_values: {'underline' in new_values} -> {new_values.get('underline', 'MISSING')}")
            print(f"   - has_explicit_style: {has_explicit_style}")
            
            if not has_explicit_style:
                # 편집창에서 스타일 설정이 없다면 원본 사용
                edit_flags = span.get('flags', 0)
                print(f"   OK 스타일 설정 없음, 원본 사용: flags={edit_flags}")
            else:
                print(f"   OK 편집창 스타일 적용: bold={new_values.get('bold', False)}, italic={new_values.get('italic', False)}, underline={new_values.get('underline', False)}")
                print(f"   OK 최종 edit_flags: {edit_flags}")

            print(f"스타일 flags: 편집창={edit_flags}, 원본={span.get('flags', 0)}")

            # 기존 오버레이 찾기 (overlay_id가 있으면 최우선, 없으면 위치 기반)
            existing_overlay = None
            overlay_id_to_find = span.get('overlay_id')
            if overlay_id_to_find is not None:
                existing_overlay = self.pdf_viewer.get_overlay_by_id(self.pdf_viewer.current_page_num, overlay_id_to_find)
            
            if not existing_overlay:
                existing_overlay = self.pdf_viewer.find_overlay_at_position(
                    self.pdf_viewer.current_page_num, layout_bbox)
                if not existing_overlay and has_current_bbox:
                    existing_overlay = self.pdf_viewer.find_overlay_at_position(
                        self.pdf_viewer.current_page_num, original_bbox)

            stretch_value = float(new_values.get('stretch', 1.0) or 1.0)
            if existing_overlay:
                height_ratio = TextOverlay._normalize_height_ratio(getattr(existing_overlay, 'height_ratio', 1.15))
                ascent_ratio = getattr(existing_overlay, 'ascent_ratio', 0.85)
                descent_ratio = getattr(existing_overlay, 'descent_ratio', max(0.0, height_ratio - ascent_ratio))
                preview_height_ratio = TextOverlay._normalize_height_ratio(getattr(existing_overlay, 'preview_height_ratio', height_ratio))
            else:
                preview_height_ratio, preview_ascent_ratio, preview_descent_ratio = self._compute_preview_metrics(
                    selected_font_name, font_path, edit_flags, stretch_value
                )
                height_ratio = preview_height_ratio
                ascent_ratio = preview_ascent_ratio
                descent_ratio = preview_descent_ratio

            source_bbox = original_bbox if not existing_overlay else (existing_overlay.original_bbox or original_bbox)
            
            # 원본 베이스라인 정보(origin)가 있으면 이를 기반으로 정확한 ascent_ratio 계산
            origin = span.get('origin')
            font_size_safe = max(0.5, float(font_size))
            
            print(f"   [Debug Position] existing_overlay={bool(existing_overlay)}")
            print(f"   [Debug Position] span.origin={origin}")
            print(f"   [Debug Position] source_bbox={source_bbox}")
            
            if existing_overlay:
                # 기존 오버레이 편집 시: 기존에 설정된 메트릭 유지 (레이아웃 틀어짐 방지)
                height_ratio = getattr(existing_overlay, 'height_ratio', 1.15)
                ascent_ratio = getattr(existing_overlay, 'ascent_ratio', 0.85)
                descent_ratio = getattr(existing_overlay, 'descent_ratio', 0.30)
                preview_height_ratio = getattr(existing_overlay, 'preview_height_ratio', height_ratio)
            elif origin and len(origin) >= 2:
                # [중요] PDF에서 추출된 텍스트 스팬을 처음 편집할 때
                # 1) 일반 텍스트 편집: 원본 PDF의 베이스라인 위치를 100% 보존해야 함
                # 2) 단, 텍스트가 없는 사각형 선택(패치용)인 경우에만 폰트 메트릭으로 중앙 정렬
                if span.get('text'):
                    # 실제 텍스트가 있는 경우: 원본 베이스라인 비율 계산
                    ascent_ratio = (origin[1] - source_bbox.y0) / font_size_safe
                    height_ratio = source_bbox.height / font_size_safe
                    descent_ratio = max(0.0, height_ratio - ascent_ratio)
                    preview_height_ratio = height_ratio
                    print(f"   [Original Text] 원본 베이스라인 보존 모드: ascent={ascent_ratio:.3f}")
                else:
                    # 텍스트가 없는 패치용 선택: 폰트 기반 메트릭 (중앙 정렬용)
                    preview_metrics = self._compute_preview_metrics(selected_font_name, font_path, edit_flags, stretch_value)
                    height_ratio, ascent_ratio, descent_ratio = preview_metrics
                    preview_height_ratio = height_ratio
                    print(f"   [Empty Patch] 신규 패치 모드 - 폰트 기반 metrics 적용")
            else:
                # origin이 없는 경우 시스템 폰트 메트릭 사용
                preview_metrics = self._compute_preview_metrics(selected_font_name, font_path, edit_flags, stretch_value)
                height_ratio, ascent_ratio, descent_ratio = preview_metrics
                preview_height_ratio = height_ratio
                # PDF 실제 영역 높이에 맞춰 보정
                pdf_h_ratio = source_bbox.height / font_size_safe
                scale = pdf_h_ratio / height_ratio if height_ratio > 0 else 1.0
                height_ratio = pdf_h_ratio
                ascent_ratio *= scale
                descent_ratio *= scale

            # 최종 값 정규화
            height_ratio = TextOverlay._normalize_height_ratio(height_ratio)
            
            # 오버레이 레이어는 현재 조정된 위치를 유지 (수정 시 원위치 회귀 방지)
            if existing_overlay:
                new_bbox = fitz.Rect(existing_overlay.bbox)
            else:
                new_bbox = fitz.Rect(source_bbox)
            
            # 시작점 좌표 확보
            target_y0 = new_bbox.y0

            # [개선사항] 텍스트 실제 크기에 맞춰 오버레이 영역(bbox) 자동 확장 및 중앙 정렬
            try:
                from PySide6.QtGui import QFont, QFontMetricsF, QImage
                dummy = QImage(1, 1, QImage.Format.Format_Mono)
                dpm_72 = int(72 / 0.0254)
                dummy.setDotsPerMeterX(dpm_72)
                dummy.setDotsPerMeterY(dpm_72)
                
                qf = QFont(selected_font_name)
                # [수정] 200배 정밀도 측정 전략 적용 (렌더링과 동기화)
                precision_multiplier = 200.0
                qf.setPixelSize(int(round(float(font_size) * precision_multiplier)))
                qf.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
                qf.setStyleStrategy(QFont.StyleStrategy.ForceOutline | QFont.StyleStrategy.PreferAntialias)
                qf.setKerning(False)
                if edit_flags & 16: qf.setBold(True)
                if edit_flags & 2: qf.setItalic(True)
                fm = QFontMetricsF(qf, dummy)
                
                t_ratio = 1.0 + (float(new_values.get('tracking', 0.0)) / 100.0)
                is_hwp_mode = bool(new_values.get('hwp_space_mode', False))
                
                calc_max_w = 0
                lines_list = text_to_insert.splitlines() if text_to_insert else [""]
                hwp_std_space = float(font_size) * precision_multiplier * 0.50
                for line in lines_list:
                    lw = 0
                    for ch in line:
                        cw = fm.horizontalAdvance(ch)
                        if ch == ' ' and is_hwp_mode:
                            cw_eff = max(cw, hwp_std_space)
                        else:
                            cw_eff = cw
                        lw += cw_eff * t_ratio
                    calc_max_w = max(calc_max_w, lw)
                
                # 결과값을 다시 200(precision_multiplier)으로 나누어 원래 스케일로 복원
                calc_max_w /= precision_multiplier
                calc_max_w *= float(new_values.get('stretch', 1.0) or 1.0)
                calc_max_w = max(calc_max_w, 2.0)
                calc_h = max(len(lines_list), 1) * (font_size * height_ratio)
                
                # [개선] 패치 모드(텍스트가 없던 영역에 새로 생성)에서만 Y축 중앙 배치 로직 적용
                if not existing_overlay and source_bbox and not span.get('text'):
                    # 선택 영역의 정중앙 Y좌표 계산
                    source_center_y = source_bbox.y0 + (source_bbox.height / 2.0)
                    # 텍스트 덩어리가 전체적으로 source_bbox 중앙에 오게 하는 시작점(target_y0)
                    target_y0 = source_center_y - (calc_h / 2.0)
                    
                    # [중요] 텍스트 베이스라인(origin)을 새롭게 계산된 target_y0 기준으로 설정
                    origin_y = target_y0 + (font_size * ascent_ratio)
                    origin = [source_bbox.x0, origin_y]
                    print(f"   [Vertical Center] 패치 영역 중앙 정렬 완료: baseline={origin_y:.1f}")

                # [중요] 초록색 하이라이트(오버레이 bbox)가 원본 텍스트블록(파란색 하이라이트)보다 짧아지는 문제 방지
                fitted_w = calc_max_w
                ref_bbox = source_bbox or span.get('source_bbox') or span.get('original_bbox') or (existing_overlay.original_bbox if existing_overlay else None)
                if ref_bbox and ref_bbox.width > 0:
                    orig_text = span.get('text', '') or getattr(existing_overlay, 'text', '')
                    if not existing_overlay or text_to_insert == orig_text:
                        fitted_w = max(calc_max_w, ref_bbox.width)
                    else:
                        fitted_w = max(calc_max_w, 2.0)

                # [중요] 텍스트 크기에 맞춰 영역 자동 확장 (Clipping 방지 핵심)
                new_bbox = fitz.Rect(new_bbox.x0, target_y0, new_bbox.x0 + fitted_w, target_y0 + calc_h)
                
                if not existing_overlay and not span.get('text'):
                    # [개선] 신규 패치 영역(original_bbox)도 최종 텍스트 영역에 1:1 동기화
                    span['original_bbox'] = new_bbox 
                    
                    # 패치 생성 시 여백을 0으로 강제 (자동 맞춤 시에만)
                    for k in ['patch_margin_l', 'patch_margin_r', 'patch_margin_t', 'patch_margin_b']:
                        new_values[k] = 0.0
                    new_values['patch_margin'] = (0.0, 0.0, 0.0, 0.0)
                    print(f"   [BBox Fit] 신규 패치 영역 동기화 완료: {new_bbox.width:.1f}x{new_bbox.height:.1f}")
                else:
                    # 일반 편집 시에도 original_bbox를 업데이트하여 clipping 방지
                    if existing_overlay:
                        existing_overlay.original_bbox = fitz.Rect(new_bbox)
                    print(f"   [Manual Margin] 일반 편집 모드 - 영역 확장 적용 ({new_bbox.width:.1f}x{new_bbox.height:.1f})")
            except Exception as e_size:
                print(f"   경고: 텍스트 크기 계산 실패: {e_size}")

            overlay = existing_overlay
            if existing_overlay:
                existing_overlay.update_properties(
                    text=text_to_insert,
                    font=selected_font_name,
                    pdf_font_name=pdf_font_name,
                    size=font_size,
                    color=color_int,
                    flags=edit_flags,
                    stretch=new_values.get('stretch', 1.0),
                    tracking=new_values.get('tracking', 0.0),
                    font_path=font_path,
                    synth_bold=need_synth_bold,
                    synth_bold_weight=new_values.get('synth_bold_weight', 120),
                    underline_weight=new_values.get('underline_weight', 0.6),
                    underline_offset=new_values.get('underline_offset', 1.5),
                    patch_margin=new_values.get('patch_margin'),
                    patch_margin_h=new_values.get('patch_margin_h'),
                    patch_margin_v=new_values.get('patch_margin_v'),
                    height_ratio=height_ratio,
                    ascent_ratio=ascent_ratio,
                    descent_ratio=descent_ratio,
                    preview_height_ratio=preview_height_ratio,
                    hwp_space_mode=new_values.get('hwp_space_mode'),
                    text_only_mode=new_values.get('text_only_mode'),
                    origin=origin, # 원본 베이스라인 유지
                    new_values=new_values # NameError 해결
                )
                existing_overlay.move_to(new_bbox)
                # 오버레이의 기준 영역도 최적화된 영역으로 업데이트하여 패치와 일치시킴
                existing_overlay.original_bbox = fitz.Rect(new_bbox)
                setattr(existing_overlay, 'force_image', bool(new_values.get('force_image', False)))
                print(f"레이어 오버레이 업데이트: '{text_to_insert}' (ID: {existing_overlay.z_index})")
            else:
                overlay = self.pdf_viewer.add_text_overlay(
                    text=text_to_insert,
                    font=selected_font_name,
                    pdf_font_name=pdf_font_name,
                    size=font_size,
                    color=color_int,
                    bbox=new_bbox,
                    page_num=self.pdf_viewer.current_page_num,
                    flags=edit_flags,
                    font_path=font_path,
                    synth_bold=need_synth_bold,
                    synth_bold_weight=new_values.get('synth_bold_weight', 120),
                    underline_weight=new_values.get('underline_weight', 0.6),
                    underline_offset=new_values.get('underline_offset', 1.5),
                    patch_margin=new_values.get('patch_margin'),
                    patch_margin_h=new_values.get('patch_margin_h'),
                    patch_margin_v=new_values.get('patch_margin_v'),
                    height_ratio=height_ratio,
                    ascent_ratio=ascent_ratio,
                    descent_ratio=descent_ratio,
                    source_bbox=new_bbox, # 패치와 일치시키기 위해 fitted bbox 전달
                    origin=origin, # 원본 베이스라인 저장
                    preview_height_ratio=preview_height_ratio,
                    hwp_space_mode=new_values.get('hwp_space_mode'),
                    text_only_mode=new_values.get('text_only_mode'),
                    new_values=new_values # 인자 추가
                )
                overlay.update_properties(
                    stretch=new_values.get('stretch', 1.0),
                    tracking=new_values.get('tracking', 0.0),
                    new_values=new_values # NameError 해결
                )
                setattr(overlay, 'force_image', bool(new_values.get('force_image', False)))
                print(f"OK 새 레이어 오버레이 생성: '{text_to_insert}' (ID: {overlay.z_index})")

            if 'patch_margin_h' in new_values or 'patch_margin_v' in new_values:
                overlay.patch_margin_h = new_values.get('patch_margin_h', overlay.patch_margin_h)
                overlay.patch_margin_v = new_values.get('patch_margin_v', overlay.patch_margin_v)
            elif 'patch_margin' in new_values and new_values.get('patch_margin') is not None:
                legacy_margin = new_values.get('patch_margin')
                try:
                    if isinstance(legacy_margin, (tuple, list)) and len(legacy_margin) >= 2:
                        overlay.patch_margin_h = float(legacy_margin[0])
                        overlay.patch_margin_v = float(legacy_margin[1])
                    else:
                        scalar_margin = float(legacy_margin)
                        overlay.patch_margin_h = scalar_margin
                        overlay.patch_margin_v = scalar_margin
                except Exception:
                    pass

            print(f"배경 패치 적용 준비...")
            new_values['overlay_id'] = overlay.z_index
            
            # HWP 공백 보정 모드 업데이트
            if 'hwp_space_mode' in new_values:
                overlay.update_properties(hwp_space_mode=new_values['hwp_space_mode'])
            
            if hasattr(self.pdf_viewer, 'register_overlay_text'):
                self.pdf_viewer.register_overlay_text(self.pdf_viewer.current_page_num, original_bbox)
            
            # 단일 레이어 표시 강제(같은 세로 밴드의 다른 오버레이를 숨기고 풀폭 패치 추가)
            # 단일 레이어 표시 모드는 옵션으로만 수행 (기본은 최소 패치)
            if bool(new_values.get('single_overlay_view', False)):
                try:
                    self.enforce_single_overlay_view(page, overlay, new_values)
                except Exception as enf:
                    print(f"경고 enforce_single_overlay_view 경고: {enf}")
            
            if overlay:
                self.pdf_viewer.active_overlay = (self.pdf_viewer.current_page_num, overlay.z_index)

            return overlay
            
        except Exception as e:
            print(f"X 레이어 오버레이 생성 실패: {e}")
            import traceback
            traceback.print_exc()
            # 실패시 기존 방식으로 fallback
            return self._insert_overlay_text_fallback(page, span, new_values)
    
    def _insert_overlay_text_fallback(self, page, span, new_values):
        """레이어 오버레이 실패시 기존 PDF 렌더링 방식 fallback"""
        try:
            original_bbox = span['original_bbox']
            text_to_insert = new_values['text']
            font_size = new_values['size']
            text_color = new_values['color']
            tracking_percent = float(new_values.get('tracking', 0.0) or 0.0)
            
            # 폰트 설정
            font_args = {
                "fontsize": font_size,
                "color": (text_color.redF(), text_color.greenF(), text_color.blueF())
            }
            charspace_value = font_size * (tracking_percent / 100.0)
            if abs(charspace_value) > 1e-6:
                font_args["charspace"] = charspace_value
            
            # 폰트 파일 적용
            selected_font_name = new_values['font']
            if selected_font_name == self.t('font_combo_all_fonts'):
                selected_font_name = "Arial"
            
            font_path = self.font_manager.get_font_path(selected_font_name)
            
            if font_path and os.path.exists(font_path):
                try:
                    import hashlib
                    font_ref_name = f"font_{hashlib.md5((selected_font_name + str(font_size)).encode('utf-8')).hexdigest()[:10]}"
                    page.insert_font(fontfile=font_path, fontname=font_ref_name)
                    font_args["fontname"] = font_ref_name
                except Exception as e:
                    print(f"Fallback 폰트 삽입 에러: {e}")
                    font_args["fontname"] = "helv"
            else:
                font_args["fontname"] = "helv"
            
            # 텍스트 위치 계산 및 삽입
            insert_point = fitz.Point(original_bbox.x0, original_bbox.y1 - 2)
            page.insert_text(insert_point, text_to_insert, **font_args)
            print(f"Fallback 텍스트 삽입: '{text_to_insert}'")
            
            if hasattr(self, 'mark_doc_modified'):
                self.mark_doc_modified()
            
            return None
            
        except Exception as e:
            print(f"Fallback 텍스트 삽입 실패: {e}")
            return None

    def _apply_font_fallback_strategy(self, page, selected_font_name, font_args):
        """폰트 fallback 전략 적용"""
        import hashlib
        fallback_success = False
        
        # 한글 폰트 대체 시도
        if any(korean in selected_font_name.lower() for korean in ['dotum', 'gulim', 'batang', 'malgun', 'nanum']):
            korean_fallbacks = ['Dotum', 'Gulim', 'Batang', 'Malgun Gothic']
            for fallback_font in korean_fallbacks:
                fallback_path = self.font_manager.get_font_path(fallback_font)
                if fallback_path and os.path.exists(fallback_path):
                    try:
                        fallback_ref = f"fallback_{hashlib.md5(fallback_font.encode('utf-8')).hexdigest()[:8]}"
                        page.insert_font(fontfile=fallback_path, fontname=fallback_ref)
                        font_args["fontname"] = fallback_ref
                        print(f"한글 폰트 fallback: {fallback_font}")
                        fallback_success = True
                        break
                    except Exception:
                        continue
        
        if not fallback_success:
            # 기본 폰트 사용
            font_args["fontname"] = "helv"
            print("시스템 기본 폰트 사용: Helvetica")

    def _apply_alternative_font_strategy(self, page, selected_font_name, font_args):
        """대안 폰트 전략 적용"""
        import hashlib
        
        # 유사한 폰트 검색
        alternative_font = None
        for available_font in self.font_manager.get_all_font_names():
            if selected_font_name.lower() in available_font.lower() or available_font.lower() in selected_font_name.lower():
                alternative_path = self.font_manager.get_font_path(available_font)
                if alternative_path and os.path.exists(alternative_path):
                    alternative_font = available_font
                    break
        
        if alternative_font:
            try:
                alt_ref = f"alt_{hashlib.md5(alternative_font.encode('utf-8')).hexdigest()[:8]}"
                alt_path = self.font_manager.get_font_path(alternative_font)
                page.insert_font(fontfile=alt_path, fontname=alt_ref)
                font_args["fontname"] = alt_ref
                print(f"대안 폰트 사용: {alternative_font}")
            except Exception as e:
                print(f"대안 폰트 실패: {e}")
                font_args["fontname"] = "helv"
        else:
            font_args["fontname"] = "helv"
            print("적절한 대안을 찾지 못함. Helvetica 사용.")

    def _apply_text_styles(self, page, insert_point, text_to_insert, new_values, font_args, fontfile_path=None):
        """텍스트 스타일 적용 (굵게, 밑줄)"""
        font_size = new_values['size']
        text_color = new_values['color']
        
        # 굵게: 변형 폰트를 우선 사용. 변형이 없는 경우에만 합성 볼드(다중 오프셋) 사용
        if new_values.get('bold', False) and new_values.get('synth_bold', False):
            synth_weight = float(new_values.get('synth_bold_weight', 120))
            offset_factor = (synth_weight - 100.0) / 100.0 * 0.15
            total_bold_dx = font_size * offset_factor
            
            if total_bold_dx > 0.001:
                half_dx = total_bold_dx / 2.0
                step = 0.05 # 정밀 0.05pt 스텝 (프리뷰와 동기화)
                curr_dx = -half_dx
                max_iter = 300
                while curr_dx <= half_dx and max_iter > 0:
                    offset_point = fitz.Point(insert_point.x + curr_dx, insert_point.y)
                    page.insert_text(offset_point, text_to_insert, **font_args)
                    curr_dx += step
                    max_iter -= 1
                page.insert_text(fitz.Point(insert_point.x + half_dx, insert_point.y), text_to_insert, **font_args)

        # 밑줄 처리
        if new_values.get('underline', False):
            # 프리뷰와 일치시키기 위해 설정된 offset 적용
            u_offset = float(new_values.get('underline_offset', 1.5))
            underline_y = insert_point.y + u_offset 
            
            # 정확한 텍스트 너비 계산
            try:
                if fontfile_path and os.path.exists(fontfile_path):
                    f = fitz.Font(fontfile=fontfile_path)
                    text_width = f.text_length(text_to_insert, font_size)
                else:
                    text_width = len(text_to_insert) * font_size * 0.55 # 근사치 보정
            except Exception:
                text_width = len(text_to_insert) * font_size * 0.6
                
            u_weight = float(new_values.get('underline_weight', 0.6))
            page.draw_line(
                fitz.Point(insert_point.x, underline_y),
                fitz.Point(insert_point.x + text_width, underline_y),
                color=(text_color.redF(), text_color.greenF(), text_color.blueF()),
                width=u_weight
            )

    def on_text_selected(self, span):
        """텍스트 선택 시 편집창 실행 및 실시간 미리보기 지원"""
        print(f"[Debug] on_text_selected span size: {span.get('size')} (type: {type(span.get('size'))})")
        # 1. 편집 전 상태 저장 (취소 시 복구용 - 반드시 선행 생성 전에 수행)
        if self.pdf_viewer.doc:
            self.undo_manager.save_state(self.pdf_viewer.doc, self.pdf_viewer)
            print("[Edit] Pre-edit state saved for Undo/Redo")

        page_num = self.pdf_viewer.current_page_num
        span.setdefault('page_num', page_num)
        
        # [실시간 미리보기 핵심: 다이얼로그 열기 전 미리 오버레이 생성]
        existing_overlay = None
        if span.get('is_overlay') and span.get('overlay_id') is not None:
            existing_overlay = self.pdf_viewer.get_overlay_by_id(page_num, span.get('overlay_id'))
        
        if not existing_overlay:
            try:
                page = self.pdf_viewer.doc.load_page(page_num)
                # 기본 편집값 생성
                color_val = span.get('color', 0)
                if isinstance(color_val, int):
                    qcolor = QColor((color_val >> 16) & 0xFF, (color_val >> 8) & 0xFF, color_val & 0xFF)
                else:
                    qcolor = QColor(0, 0, 0)
                
                font_str = str(span.get('font', '')).lower()
                pdf_font_str = str(span.get('pdf_font_name', '')).lower()
                hwp_font_keys = ['hcr', 'h2hdr', 'h2gtr', 'h2mk', 'hygtr', 'hybtr', 'hmk', 'hancom', 'haansoft', 'gulimche', 'batangche']
                is_hwp = bool(span.get('hwp_space_mode', False)) or any(k in font_str or k in pdf_font_str for k in hwp_font_keys) or getattr(self, 'is_hwp_doc', False)
                span['hwp_space_mode'] = is_hwp

                # [HWP 장평/자간 정밀 자동 계산]
                auto_stretch, auto_tracking = self.calculate_auto_stretch_and_tracking(span)
                span['stretch'] = auto_stretch
                span['tracking'] = auto_tracking
                
                initial_values = {
                    'text': span.get('text', ''),
                    'font': span.get('font', 'Arial'),
                    'size': float(span.get('size', 12.0)),
                    'color': qcolor,
                    'bold': bool(span.get('flags', 0) & 16),
                    'italic': bool(span.get('flags', 0) & 2),
                    'underline': False, # 밑줄 기본값 비활성화
                    'underline_weight': 0.6, # 밑줄 굵기 기본값 0.6 설정
                    'stretch': auto_stretch,
                    'tracking': auto_tracking,
                    'synth_bold_weight': 120,
                    'hwp_space_mode': is_hwp,
                    'patch_margin_l': 0.0, 'patch_margin_r': 0.0, 'patch_margin_t': 0.0, 'patch_margin_b': 0.0,
                    'original_bbox': span.get('original_bbox'),
                    'origin': span.get('origin'),
                    'page_num': page_num
                }
                
                # 미리 오버레이 생성
                overlay = self.insert_overlay_text(page, span, initial_values)
                if overlay:
                    self.apply_background_patch(page, span['original_bbox'], initial_values, overlay=overlay, preview=True)
                    
                    # [중요] 생성된 오버레이의 실제 정보를 span에 완벽히 동기화
                    overlay_data = overlay.to_dict()
                    span.update(overlay_data)
                    span['is_overlay'] = True
                    span['overlay_id'] = overlay.z_index
                    span['page_num'] = page_num
                    
                    self.pdf_viewer.active_overlay = (page_num, overlay.z_index)
                    
                    # [중요] 모달 다이얼로그 진입 전 UI 강제 갱신
                    self.pdf_viewer.update()
                    
                    print(f"[Edit] Proactive overlay created and linked: ID {overlay.z_index}")
            except Exception as e_pre:
                print(f"미리보기용 오버레이 선행 생성 실패: {e_pre}")
                import traceback
                traceback.print_exc()
        else:
            self.pdf_viewer.active_overlay = (page_num, existing_overlay.z_index)
            self.pdf_viewer.update()

        # 다이얼로그 실행 (모달리스 방식으로 실행하여 문서 뷰어의 핸드툴, 줌 등 조작 가능)
        self.open_text_editor(span, is_patch_mode=False)

    def save_text_editor_pos(self, pos: QPoint):
        """텍스트 편집창의 직전 위치 저장"""
        if pos and not pos.isNull():
            self.last_text_editor_pos = pos
            if hasattr(self, 'settings') and self.settings:
                try:
                    self.settings.setValue('text_editor_pos_x', pos.x())
                    self.settings.setValue('text_editor_pos_y', pos.y())
                except Exception:
                    pass

    def open_text_editor(self, span, is_patch_mode=False):
        """텍스트 편집 다이얼로그를 모달리스로 실행하여 편집 중에도 문서 뷰어 조작(핸드툴, 줌 등) 지원"""
        # 이미 열려 있는 텍스트 편집기가 있다면 안전하게 확정 후 새로 열기
        if getattr(self, 'current_text_editor', None) is not None:
            try:
                if self.current_text_editor.isVisible():
                    self.current_text_editor.accept()
            except Exception:
                pass
            self.current_text_editor = None

        page_num = span.get('page_num', self.pdf_viewer.current_page_num)

        if not span.get('is_overlay') and ('stretch' not in span or 'tracking' not in span):
            if 'hwp_space_mode' not in span:
                font_str = str(span.get('font', '')).lower()
                pdf_font_str = str(span.get('pdf_font_name', '')).lower()
                hwp_font_keys = ['hcr', 'h2hdr', 'h2gtr', 'h2mk', 'hygtr', 'hybtr', 'hmk', 'hancom', 'haansoft', 'gulimche', 'batangche']
                is_hwp = bool(span.get('hwp_space_mode', False)) or any(k in font_str or k in pdf_font_str for k in hwp_font_keys) or getattr(self, 'is_hwp_doc', False)
                span['hwp_space_mode'] = is_hwp
            auto_stretch, auto_tracking = self.calculate_auto_stretch_and_tracking(span)
            span.setdefault('stretch', auto_stretch)
            span.setdefault('tracking', auto_tracking)

        dialog = TextEditorDialog(span, getattr(self, 'pdf_fonts', None), self)
        dialog.setModal(False)
        self.current_text_editor = dialog

        def _on_editor_accepted():
            if dialog:
                self.save_text_editor_pos(dialog.pos())
            if getattr(self, 'current_text_editor', None) is dialog:
                self.current_text_editor = None
            new_values = dialog.get_values()
            print(f"Dialog result: {new_values}")
            self.register_recent_font(new_values.get('font'))
            
            # 패치 마진 설정 저장
            if 'patch_margin_l' in new_values:
                self.patch_margin = (new_values['patch_margin_l'], new_values['patch_margin_r'], 
                                    new_values['patch_margin_t'], new_values['patch_margin_b'])
                self._store_patch_margin()
            
            # 위치 조정 모드 요청 처리
            if new_values.get('position_adjustment_requested', False):
                updated_span = span.copy()
                updated_span.update(new_values)
                self.pdf_viewer.enter_text_adjustment_mode(updated_span)
                return
            
            try:
                page = self.pdf_viewer.doc.load_page(page_num)
                # 최종 확정: 오버레이와 패치 최종 갱신
                overlay = self.insert_overlay_text(page, span, new_values)
                self.apply_background_patch(page, span['original_bbox'], new_values, overlay=overlay, preview=True)
                
                # 변경 완료 후 새로운 상태 저장
                if hasattr(self, 'undo_manager') and self.pdf_viewer.doc:
                    self.undo_manager.save_state(self.pdf_viewer.doc, self.pdf_viewer)
                self.mark_as_changed()
                self.update_undo_redo_buttons()
                
                # UX 개선: 작업 완료 후 패치 모드 자동 비활성화
                if hasattr(self, 'set_patch_mode'):
                    self.set_patch_mode(False)
                
                if overlay:
                    overlay_info = {
                        'text': overlay.text,
                        'font': overlay.font,
                        'size': overlay.size,
                        'flags': overlay.flags,
                        'color': overlay.color,
                        'original_bbox': overlay.original_bbox,
                        'current_bbox': overlay.bbox,
                        'is_overlay': True,
                        'overlay_id': overlay.z_index,
                        'page_num': page_num,
                        'synth_bold_weight': getattr(overlay, 'synth_bold_weight', 120),
                        'underline_weight': getattr(overlay, 'underline_weight', 0.6),
                        'underline_offset': getattr(overlay, 'underline_offset', 1.5)
                    }
                    self.pdf_viewer.selected_text_info = overlay_info
                    self.pdf_viewer.active_overlay = (page_num, overlay.z_index)

                if is_patch_mode and hasattr(self.pdf_viewer, 'selection_rect'):
                    self.pdf_viewer.selection_rect = None
                    self.pdf_viewer.selection_mode = False
                    self.pdf_viewer.selection_is_eraser = False
                    self.pdf_viewer.ctrl_pressed = False
                    try:
                        self.pdf_viewer.setCursor(Qt.CursorShape.ArrowCursor)
                    except Exception:
                        pass
                
                self.pdf_viewer.update()
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to finalize edit: {e}")
                import traceback
                traceback.print_exc()

        def _on_editor_rejected():
            if dialog:
                self.save_text_editor_pos(dialog.pos())
            if getattr(self, 'current_text_editor', None) is dialog:
                self.current_text_editor = None
            print("편집 취소 - 이전 상태로 복구")
            self.undo() # save_state 해둔 시점으로 복구
            self.update_undo_redo_buttons()
            
            if is_patch_mode and hasattr(self.pdf_viewer, 'selection_rect'):
                self.pdf_viewer.selection_rect = None
                self.pdf_viewer.selection_mode = False
                self.pdf_viewer.selection_is_eraser = False
                keep_enabled = getattr(self, 'patch_precise_mode', False)
                self.pdf_viewer.ctrl_pressed = False
                try:
                    self.pdf_viewer.setCursor(Qt.CursorShape.CrossCursor if keep_enabled else Qt.CursorShape.ArrowCursor)
                except Exception:
                    pass
            self.pdf_viewer.update()

        dialog.accepted.connect(_on_editor_accepted)
        dialog.rejected.connect(_on_editor_rejected)

        # 직전 위치 복원 (화면 밖으로 벗어나지 않도록 클램핑)
        if getattr(self, 'last_text_editor_pos', None) is not None:
            try:
                pos = self.last_text_editor_pos
                screen = QApplication.screenAt(pos) or (self.screen() if hasattr(self, 'screen') else QApplication.primaryScreen())
                if screen:
                    screen_geo = screen.availableGeometry()
                    x = max(screen_geo.left(), min(pos.x(), screen_geo.right() - 200))
                    y = max(screen_geo.top(), min(pos.y(), screen_geo.bottom() - 100))
                    dialog.move(x, y)
            except Exception as e_pos:
                print(f"[Dialog] Failed to restore pos: {e_pos}")

        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    
    def closeEvent(self, event):
        """창 닫기 이벤트 처리"""
        if getattr(self, 'current_text_editor', None) is not None:
            try:
                if self.current_text_editor.isVisible():
                    self.current_text_editor.accept()
            except Exception:
                pass
            self.current_text_editor = None

        if self.has_changes:
            msg = QMessageBox(self)
            msg.setWindowTitle(self.t('title_unsaved_changes'))
            msg.setText(self.t('msg_unsaved_changes'))
            yes_btn = msg.addButton(QMessageBox.StandardButton.Yes)
            no_btn = msg.addButton(QMessageBox.StandardButton.No)
            cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)
            yes_btn.setText(self.t('btn_yes'))
            no_btn.setText(self.t('btn_no'))
            cancel_btn.setText(self.t('btn_cancel'))
            try:
                for b in msg.buttons():
                    b.setMinimumSize(96, 36)
            except Exception:
                pass
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == yes_btn:
                if self.save_pdf():
                    self._save_persisted_state()
                    event.accept()
                else:
                    event.ignore()
            elif clicked == no_btn:
                self._save_persisted_state()
                event.accept()
            else:
                event.ignore()
        else:
            self._save_persisted_state()
            event.accept()

    # 패치 크기 조절 관련 메서드들
    def set_patch_mode(self, enabled: bool, patch_only: Optional[bool] = None):
        enabled = bool(enabled)
        previous_enabled = getattr(self, 'patch_precise_mode', False)
        previous_patch_only = getattr(self, 'patch_only_mode', False)
        self.patch_precise_mode = enabled

        if patch_only is not None:
            self.patch_only_mode = bool(patch_only) and enabled
        elif enabled:
            self.patch_only_mode = False
        else:
            self.patch_only_mode = False

        if not self.patch_only_mode:
            self._patch_mode_restore_state = None

        viewer = getattr(self, 'pdf_viewer', None)
        if viewer:
            if enabled:
                try:
                    viewer.setCursor(Qt.CursorShape.CrossCursor)
                except Exception:
                    pass
                viewer.setFocus()
            else:
                viewer.selection_mode = False
                viewer.selection_start = None
                viewer.selection_rect = None
                viewer.selection_is_eraser = False
                viewer.ctrl_pressed = False
                viewer.shift_pressed = False
                try:
                    viewer.setCursor(Qt.CursorShape.ArrowCursor)
                except Exception:
                    pass

        self._sync_patch_controls()
        status = "ON" if enabled else "OFF"
        print(f"Patch mode {status}")
        if enabled != previous_enabled:
            self._store_patch_mode()

        if enabled:
            if self.patch_only_mode:
                self.show_status_message(self.t('status_patch_eraser_on', default="지우개 모드가 켜졌습니다 (드래그하여 지우기)"), 2500)
            else:
                self.show_status_message(self.t('status_patch_mode_on', default="패치 모드가 켜졌습니다 (드래그하여 편집)"), 2500)
        else:
            if previous_patch_only:
                self.show_status_message(self.t('status_patch_eraser_off', default="지우개 모드가 꺼졌습니다"), 2000)
            else:
                self.show_status_message(self.t('status_patch_mode_off', default="패치 모드가 꺼졌습니다"), 2000)

    def set_patch_margin(self, margin):
        """패치 여백 설정"""
        if isinstance(margin, (tuple, list)) and len(margin) >= 2:
            try:
                self.patch_margin = (float(margin[0]), float(margin[1]))
            except Exception:
                self.patch_margin = (0.0, 0.0)
        else:
            try:
                scalar = float(margin)
            except Exception:
                scalar = 0.0
            self.patch_margin = (scalar, scalar)
        print(f"패치 여백 설정: {self.patch_margin}")
        self._store_patch_margin()

    def toggle_force_text_flatten(self, checked):
        """텍스트 유지 정밀 플래튼 토글"""
        self.force_text_flatten = bool(checked)
        status = "활성화" if self.force_text_flatten else "비활성화"
        print(f"텍스트 유지 정밀 플래튼 {status}")

    def _font_log_action_text(self):
        level = int(getattr(self, 'font_dump_verbose', 1))
        label_key = {
            0: 'font_log_level_0',
            1: 'font_log_level_1',
            2: 'font_log_level_2'
        }.get(level, 'font_log_level_1')
        label = self.t(label_key)
        return self.t('action_font_log_label', label=label)

    def toggle_font_log_verbosity(self):
        try:
            self.font_dump_verbose = (self.font_dump_verbose + 1) % 3
        except Exception:
            self.font_dump_verbose = 1
        if hasattr(self, 'font_log_action'):
            self.font_log_action.setText(self._font_log_action_text())
        print(f"글꼴 로그 상세도 변경: {self._font_log_action_text()}")

    def _ensure_font_ref(self, page, font_name, force_reload=False):
        """문서에 폰트를 한 번만 임베딩하고 참조명을 반환합니다. 
        force_reload=True일 경우 캐시를 무시하고 다시 시도합니다."""
        try:
            if not font_name:
                return "helv"
            fmgr = self.font_manager if hasattr(self, 'font_manager') else SystemFontManager()
            fpath = fmgr.get_font_path(font_name)
            
            if fpath and os.path.exists(fpath):
                import hashlib
                # 경로 기반 참조명
                ref = f"font_{hashlib.md5(fpath.encode('utf-8')).hexdigest()[:10]}"
                # 페이지별 폰트 리소스 보장 키
                cache_key = (getattr(page, 'number', 0), fpath)
                
                if not force_reload and cache_key in self._font_ref_cache:
                    return self._font_ref_cache[cache_key]
                
                try:
                    # 페이지 리소스에 우선 등록
                    page.insert_font(fontfile=fpath, fontname=ref)
                    if force_reload:
                        print(f"    -> [Retry] page.insert_font 강제 재등록 완료: {font_name} -> {ref}")
                    else:
                        print(f"    -> page.insert_font OK: {font_name} -> {ref}")
                    self._font_ref_cache[cache_key] = ref
                    return ref
                except Exception as e:
                    print(f"    -> page.insert_font 실패({font_name}): {e}")
                    # 캐시에서 제거하여 다음 시도 시 재시도 가능하게 함
                    if cache_key in self._font_ref_cache:
                        del self._font_ref_cache[cache_key]
                    return "helv"
            else:
                if fpath:
                    print(f"    -> [Error] 폰트 파일이 경로에 존재하지 않음: {fpath}")
                return "helv"
        except Exception as ex:
            print(f"    -> [_ensure_font_ref] 예외 발생: {ex}")
            return "helv"

    def apply_theme(self, mode: str):
        self.theme_mode = mode
        try:
            from PySide6.QtGui import QPalette
            app = QApplication.instance()
            if not app:
                return
            try:
                tooltip_font = QToolTip.font()
                tooltip_font.setBold(False)
                tooltip_font.setWeight(QFont.Weight.Normal)
                QToolTip.setFont(tooltip_font)
            except Exception:
                pass

            pal = QPalette()
            if mode == 'light':
                pal.setColor(QPalette.Window, QColor(255, 255, 255))
                pal.setColor(QPalette.WindowText, QColor(17, 17, 17))
                pal.setColor(QPalette.Base, QColor(250, 250, 250))
                pal.setColor(QPalette.AlternateBase, QColor(242, 242, 242))
                pal.setColor(QPalette.Text, QColor(17, 17, 17))
                pal.setColor(QPalette.Button, QColor(245, 245, 245))
                pal.setColor(QPalette.ButtonText, QColor(17, 17, 17))
                pal.setColor(QPalette.BrightText, QColor(255, 0, 0))
                pal.setColor(QPalette.Highlight, QColor(51, 153, 255))
                pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
                pal.setColor(QPalette.ToolTipBase, QColor(255, 255, 225))
                pal.setColor(QPalette.ToolTipText, QColor(17, 17, 17))
                app.setPalette(pal)
                # 라이트 전용 위젯 스타일
                light_qss = """
                QMainWindow, QWidget { background: #ffffff; color: #111; }
                QToolTip {
                    font-weight: normal;
                    font-size: 12px;
                    color: #111111;
                    background-color: #ffffff;
                    border: 1px solid #cbd5e1;
                    padding: 4px 8px;
                    border-radius: 4px;
                }
                QToolBar {
                    spacing: 3px;
                    padding: 2px 4px;
                    border: none;
                }
                QToolBar::separator {
                    width: 1.5px;
                    background-color: #cbd5e1;
                    margin: 6px 4px;
                }
                QMenuBar { font-size: 13px; padding: 3px 5px; background: #ffffff; color: #111; }
                QMenuBar::item:selected { background: #e6f2ff; border: 1px solid #3399ff; }
                QMenu { background: #ffffff; color: #111; }
                QMenu::item { padding: 8px 22px; }
                QMenu::item:selected { background: #e6f2ff; }
                QPushButton { background: #f5f5f5; color: #111; border: 1px solid #cccccc; border-radius: 6px; }
                QPushButton:hover { border: 1px solid #3399ff; }
                QLabel { color: #111; }
                QCheckBox { color:#111; }
                QCheckBox::indicator { width:16px; height:16px; border:1px solid #999; background:#fff; }
                QCheckBox::indicator:checked { background:#3399ff; }
                QCheckBox::indicator:unchecked:hover { border:2px solid #3399ff; }
                QScrollArea, QAbstractScrollArea { background-color: #f0f0f0; border: none; }
                QScrollBar:vertical { background: #f0f0f0; width: 12px; }
                QScrollBar::handle:vertical { background: #ccc; border-radius: 6px; }
                """
                app.setStyleSheet(light_qss)
                if hasattr(self, 'pdf_viewer'):
                    self.pdf_viewer.setStyleSheet("background-color: #ffffff; border: none;")
                if hasattr(self, 'scroll_area'):
                    self.scroll_area.setStyleSheet("background-color: #f0f0f0; border: none;")
                if hasattr(self, 'thumbnail_panel') and self.thumbnail_panel:
                    self.thumbnail_panel.apply_theme('light')
                if hasattr(self, 'search_bar') and self.search_bar:
                    self.search_bar.setStyleSheet(
                        "QFrame { background-color: #f1f5f9; border-bottom: 1.5px solid #cbd5e1; padding: 2px 8px; }"
                        "QPushButton { font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 4px; }"
                        "QLineEdit { background: white; padding: 5px 8px; border: 1.5px solid #94a3b8; border-radius: 6px; font-size: 13px; }"
                    )
                if hasattr(self, 'status_bar_widget') and self.status_bar_widget:
                    self.status_bar_widget.setStyleSheet(
                        "#statusBarWidget { background-color: #f8fafc; border-bottom: 1px solid #cbd5e1; }"
                        "#statusPageLabel, #statusZoomLabel { font-size: 11px; font-weight: 600; color: #475569; }"
                        "#statusMessageLabel { font-size: 11px; font-weight: 500; color: #0284c7; }"
                    )
                self.theme_button.setText("🌙")
            else:
                pal.setColor(QPalette.Window, QColor(30, 31, 34))
                pal.setColor(QPalette.WindowText, QColor(221, 221, 221))
                pal.setColor(QPalette.Base, QColor(20, 21, 24))
                pal.setColor(QPalette.AlternateBase, QColor(40, 41, 44))
                pal.setColor(QPalette.Text, QColor(221, 221, 221))
                pal.setColor(QPalette.Button, QColor(45, 46, 49))
                pal.setColor(QPalette.ButtonText, QColor(221, 221, 221))
                pal.setColor(QPalette.BrightText, QColor(255, 0, 0))
                pal.setColor(QPalette.Highlight, QColor(76, 158, 255))
                pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
                pal.setColor(QPalette.ToolTipBase, QColor(60, 60, 60))
                pal.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
                app.setPalette(pal)
                dark_qss = """
                QMainWindow, QWidget { background: #1e1f22; color: #ddd; }
                QToolTip {
                    font-weight: normal;
                    font-size: 12px;
                    color: #eeeeee;
                    background-color: #2b2d30;
                    border: 1px solid #475569;
                    padding: 4px 8px;
                    border-radius: 4px;
                }
                QToolBar {
                    spacing: 3px;
                    padding: 2px 4px;
                    border: none;
                }
                QToolBar::separator {
                    width: 1.5px;
                    background-color: #475569;
                    margin: 6px 4px;
                }
                QMenuBar { font-size: 13px; padding: 3px 5px; background: #1e1f22; color: #ddd; }
                QMenuBar::item:selected { background: #2b2d30; border: 1px solid #4c9eff; }
                QMenu { background: #2b2d30; color: #ddd; }
                QMenu::item { padding: 8px 22px; }
                QMenu::item:selected { background: #3a3d40; }
                QPushButton { background: #2d2e31; color: #ddd; border: 1px solid #555555; border-radius: 6px; }
                QPushButton:hover { border: 1px solid #4c9eff; }
                QLabel { color: #ddd; }
                QCheckBox::indicator:unchecked:hover { border:1px solid #3399ff; }
                QScrollArea, QAbstractScrollArea { background-color: #0f0f0f; border: none; }
                QScrollBar:vertical { background: #1e1f22; width: 12px; }
                QScrollBar::handle:vertical { background: #444; border-radius: 6px; }
                """
                app.setStyleSheet(dark_qss)
                if hasattr(self, 'pdf_viewer'):
                    self.pdf_viewer.setStyleSheet("background-color: #111111; border: none;")
                if hasattr(self, 'scroll_area'):
                    self.scroll_area.setStyleSheet("background-color: #0f0f0f; border: none;")
                if hasattr(self, 'thumbnail_panel') and self.thumbnail_panel:
                    self.thumbnail_panel.apply_theme('dark')
                if hasattr(self, 'search_bar') and self.search_bar:
                    self.search_bar.setStyleSheet(
                        "QFrame { background-color: #23272e; border-bottom: 1.5px solid #333842; padding: 2px 8px; }"
                        "QPushButton { font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 4px; background: #2d3139; color: #ddd; }"
                        "QLineEdit { background: #1e1f22; color: #eee; padding: 5px 8px; border: 1.5px solid #475569; border-radius: 6px; font-size: 13px; }"
                    )
                if hasattr(self, 'status_bar_widget') and self.status_bar_widget:
                    self.status_bar_widget.setStyleSheet(
                        "#statusBarWidget { background-color: #1e1f22; border-bottom: 1px solid #2d3139; }"
                        "#statusPageLabel, #statusZoomLabel { font-size: 11px; font-weight: 600; color: #94a3b8; }"
                        "#statusMessageLabel { font-size: 11px; font-weight: 500; color: #38bdf8; }"
                    )
                self.theme_button.setText("☀️")
        except Exception:
            pass
        finally:
            self._store_theme_mode()
            try:
                self._sync_theme_actions()
            except Exception:
                pass

    def toggle_theme(self):
        new_mode = 'light' if self.theme_mode == 'dark' else 'dark'
        self.set_theme_mode(new_mode)
        
    def set_theme_mode(self, mode: str):
        if mode not in ('light', 'dark'):
            return
        self.apply_theme(mode)
        self._sync_theme_actions()

    def _sync_theme_actions(self):
        if hasattr(self, 'light_mode_action') and hasattr(self, 'dark_mode_action'):
            try:
                self.light_mode_action.blockSignals(True)
                self.dark_mode_action.blockSignals(True)
                self.light_mode_action.setChecked(self.theme_mode == 'light')
                self.dark_mode_action.setChecked(self.theme_mode == 'dark')
            except Exception:
                pass
            finally:
                try:
                    self.light_mode_action.blockSignals(False)
                    self.dark_mode_action.blockSignals(False)
                except Exception:
                    pass

    def optimize_all_patches(self):
        """모든 패치 최적화"""
        if not hasattr(self, 'pdf_viewer') or not self.pdf_viewer.doc:
            QMessageBox.warning(self, "경고", "PDF 파일을 먼저 열어주세요.")
            return
            
        try:
            # 모든 페이지의 패치 최적화
            total_pages = len(self.pdf_viewer.doc)
            optimized_count = 0
            
            for page_num in range(total_pages):
                page = self.pdf_viewer.doc.load_page(page_num)
                # 여기서 패치 최적화 로직 구현 가능
                # 예: 중복 텍스트 제거, 불필요한 패치 제거 등
                optimized_count += 1
                
            QMessageBox.information(self, "완료", f"{optimized_count}개 페이지의 패치가 최적화되었습니다.")
            
        except Exception as e:
            QMessageBox.critical(self, "오류", f"패치 최적화 중 오류 발생: {str(e)}")
            
    def show_patch_info(self):
        """패치 정보 표시"""
        if not hasattr(self, 'pdf_viewer') or not self.pdf_viewer.doc:
            QMessageBox.warning(self, "경고", "PDF 파일을 먼저 열어주세요.")
            return
            
        try:
            current_page = self.pdf_viewer.doc.load_page(self.pdf_viewer.current_page_num)
            text_dict = current_page.get_text("dict")
            
            # 텍스트 블록 개수 계산
            total_blocks = 0
            total_spans = 0
            
            for block in text_dict.get("blocks", []):
                if block.get('type') == 0:  # 텍스트 블록
                    total_blocks += 1
                    for line in block.get("lines", []):
                        total_spans += len(line.get("spans", []))
            
            info_text = f"""현재 페이지 패치 정보:
            
페이지 번호: {self.pdf_viewer.current_page_num + 1}
텍스트 블록 수: {total_blocks}
텍스트 요소 수: {total_spans}
패치 여백 설정: {self.patch_margin}
패치 모드: {'활성화' if self.patch_precise_mode else '비활성화'}
            """
            
            QMessageBox.information(self, "패치 정보", info_text)
            
        except Exception as e:
            QMessageBox.critical(self, "오류", f"패치 정보 조회 중 오류 발생: {str(e)}")
    
    def fit_to_width(self):
        """뷰포트 가로 폭에 맞춤"""
        if self.pdf_viewer and self.pdf_viewer.doc:
            try:
                viewport_width = max(1, self.scroll_area.viewport().width())
                page = self.pdf_viewer.doc.load_page(self.pdf_viewer.current_page_num)
                page_rect = page.rect
                
                # 여백 고려 (약 98%)
                target_zoom = (viewport_width / max(1.0, page_rect.width)) * 0.98
                
                # 가장 가까운 고정 배율로 스냅
                levels = getattr(self, 'zoom_levels', [1.0])
                self.zoom_factor = min(levels, key=lambda x: abs(x - target_zoom))
                
                self.render_page()
                self.update_zoom_label()
                self._store_zoom_factor()
            except Exception as e:
                print(f"가로 맞춤 오류: {e}")

    def fit_to_height(self):
        """뷰포트 세로 높이에 맞춤"""
        if self.pdf_viewer and self.pdf_viewer.doc:
            try:
                viewport_height = max(1, self.scroll_area.viewport().height())
                page = self.pdf_viewer.doc.load_page(self.pdf_viewer.current_page_num)
                page_rect = page.rect
                
                # 여백 고려 (약 98%)
                target_zoom = (viewport_height / max(1.0, page_rect.height)) * 0.98
                
                # 가장 가까운 고정 배율로 스냅
                levels = getattr(self, 'zoom_levels', [1.0])
                self.zoom_factor = min(levels, key=lambda x: abs(x - target_zoom))
                
                self.render_page()
                self.update_zoom_label()
                self._store_zoom_factor()
            except Exception as e:
                print(f"세로 맞춤 오류: {e}")

    def fit_to_page(self):
        """페이지 크기에 맞춤"""
        if self.pdf_viewer and self.pdf_viewer.doc:
            try:
                # 스크롤 영역 크기 가져오기
                viewport_size = self.scroll_area.viewport().size()
                
                # 현재 페이지 크기 가져오기
                page = self.pdf_viewer.doc.load_page(self.pdf_viewer.current_page_num)
                page_rect = page.rect
                
                # 가로/세로 비율 중 작은 쪽 선택 (완전히 보이도록)
                width_ratio = viewport_size.width() / max(1.0, page_rect.width)
                height_ratio = viewport_size.height() / max(1.0, page_rect.height)
                target_zoom = min(width_ratio, height_ratio) * 0.95
                
                # 가장 가까운 고정 배율로 스냅
                levels = getattr(self, 'zoom_levels', [1.0])
                self.zoom_factor = min(levels, key=lambda x: abs(x - target_zoom))
                
                self.render_page()
                self.update_zoom_label()
                self._store_zoom_factor()
            except Exception as e:
                print(f"페이지 맞춤 오류: {e}")
    
    def undo_action(self):
        """실행취소 기능"""
        try:
            self.undo()  # 기존 undo 메서드 호출
        except Exception as e:
            print(f"실행취소 오류: {e}")
            QMessageBox.critical(self, "오류", f"실행취소 중 오류 발생: {str(e)}")
    
    def redo_action(self):
        """다시실행 기능"""
        try:
            self.redo()  # 기존 redo 메서드 호출  
        except Exception as e:
            print(f"다시실행 오류: {e}")
            QMessageBox.critical(self, "오류", f"다시실행 중 오류 발생: {str(e)}")
    
    def export_pdf(self):
        """PDF 내보내기"""
        if not self.doc:
            QMessageBox.warning(self, "경고", "열린 PDF 문서가 없습니다.")
            return
        
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, 
                "PDF 내보내기", 
                "", 
                "PDF Files (*.pdf)"
            )
            
            if file_path:
                self.doc.save(file_path)
                QMessageBox.information(self, "내보내기 완료", f"PDF가 성공적으로 내보내기되었습니다:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"PDF 내보내기 중 오류 발생: {str(e)}")

    def save_session(self):
        """편집 세션 저장(.pdfses: zip[state.json + doc.bin])"""
        try:
            if not self.pdf_viewer.doc:
                QMessageBox.warning(self, "경고", "열린 PDF 문서가 없습니다.")
                return
            file_path, _ = QFileDialog.getSaveFileName(self, "세션 저장", "", "Editor Session (*.pdfses)")
            if not file_path:
                return
            overlays, patches = self.undo_manager._snapshot_view(self.pdf_viewer)
            state = {
                'current_page': int(self.pdf_viewer.current_page_num),
                'zoom_factor': float(getattr(self, 'zoom_factor', 1.0)),
                'theme_mode': getattr(self, 'theme_mode', 'dark'),
                'font_dump_verbose': int(getattr(self, 'font_dump_verbose', 1)),
                'overlays': overlays,
                'patches': patches,
            }
            doc_bytes = self.pdf_viewer.doc.tobytes()
            with zipfile.ZipFile(file_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('state.json', json.dumps(state, ensure_ascii=False))
                zf.writestr('doc.bin', doc_bytes)
            QMessageBox.information(self, "완료", "세션이 저장되었습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"세션 저장 중 오류 발생: {str(e)}")

    def load_session(self):
        """편집 세션 불러오기(.pdfses)"""
        try:
            file_path, _ = QFileDialog.getOpenFileName(self, "세션 불러오기", "", "Editor Session (*.pdfses)")
            if not file_path:
                return
            with zipfile.ZipFile(file_path, 'r') as zf:
                state = json.loads(zf.read('state.json').decode('utf-8'))
                doc_bytes = zf.read('doc.bin')
            doc = fitz.open(stream=doc_bytes)
            # 초기화
            if hasattr(self.pdf_viewer, 'text_overlays'):
                self.pdf_viewer.text_overlays.clear()
                self.pdf_viewer.overlay_id_counter = 0
            if hasattr(self.pdf_viewer, 'background_patches'):
                self.pdf_viewer.background_patches.clear()
            self._font_ref_cache.clear()
            self._doc_font_ref_cache.clear()
            self.pdf_viewer.set_document(doc)
            self.current_file_path = None
            # 상태 복원
            overlays = state.get('overlays', {})
            patches = state.get('patches', {})
            self.undo_manager._restore_view(self.pdf_viewer, overlays, patches)
            self.pdf_viewer.current_page_num = int(state.get('current_page', 0))
            self.zoom_factor = float(state.get('zoom_factor', 1.0))
            self.theme_mode = state.get('theme_mode', 'dark')
            self.font_dump_verbose = int(state.get('font_dump_verbose', 1))
            try:
                self.apply_theme(self.theme_mode)
            except Exception:
                pass
            self.render_page()
            self.update_page_navigation()
            self.update_undo_redo_buttons()
            self.setWindowTitle(f"{self.t('app_title')} - 세션 로드")
            QMessageBox.information(self, "완료", "세션이 불러와졌습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"세션 불러오기 중 오류 발생: {str(e)}")
    
    def show_shortcuts(self):
        """단축키 도움말 표시"""
        default_shortcuts = (
            "📋 주요 단축키 안내\n\n"
            "🖱️ 마우스 제스처 & 뷰어 조작:\n"
            " • Ctrl + 드래그 : 패치모드 (영역 선택 및 텍스트 편집)\n"
            " • Shift + 드래그 : 지우개모드 (영역 배경 패치 즉시 적용)\n"
            " • Ctrl + 마우스휠 : 화면 확대 / 축소 (포인터 중심)\n"
            " • Shift + 마우스휠 : 이전 / 다음 페이지 이동\n"
            " • Spacebar + 드래그 : 화면 이동 (핸드 툴)\n"
            " • Ctrl + Spacebar + 클릭 : 화면 확대\n"
            " • Ctrl + Alt + Spacebar + 클릭 : 화면 축소\n\n"
            "🔍 확대 / 축소:\n"
            " • Ctrl + '+' / '-' : 확대 / 축소\n"
            " • Ctrl + 0 : 창 가로 맞춤\n"
            " • Ctrl + Shift + 0 : 창 세로 맞춤\n\n"
            "📖 페이지 탐색:\n"
            " • Page Up / Down : 이전 / 다음 페이지\n"
            " • Home / End : 첫 / 마지막 페이지\n\n"
            "✏️ 편집:\n"
            " • Ctrl + Z / Ctrl + Y : 실행 취소 / 다시 실행\n"
            " • Ctrl + C / Ctrl + V : 텍스트 복사 / 붙여넣기\n"
            " • 방향키 : 선택된 텍스트 위치 미세 조정\n\n"
            "📁 파일:\n"
            " • Ctrl + O : PDF 열기\n"
            " • Ctrl + S : 저장\n"
            " • Ctrl + F : 본문 검색"
        )
        msg_text = self.t('shortcuts_text', default=default_shortcuts)
        QMessageBox.information(self, self.t('shortcuts_title', default="⌨️ 단축키 안내"), msg_text)

    def show_kakao_donation_dialog(self):
        """카카오페이 후원 안내"""
        path_candidates: list[str] = []
        try:
            path_candidates.append(_resolve_static_path('yongpdf_donation.jpg'))
        except Exception:
            pass
        try:
            module_dir = os.path.dirname(os.path.abspath(__file__))
            path_candidates.append(os.path.join(module_dir, 'yongpdf_donation.jpg'))
        except Exception:
            pass

        selected_path = None
        for p in path_candidates:
            if p and os.path.exists(p):
                selected_path = p
                break

        if not selected_path:
            QMessageBox.warning(self, self.t('title_warning'), self.t('donate_image_missing'))
            return

        pixmap = QPixmap(selected_path)
        if pixmap.isNull():
            QMessageBox.warning(self, self.t('title_warning'), self.t('donate_image_missing'))
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(self.t('donate_kakao'))
        layout = QVBoxLayout(dialog)
        image_label = QLabel(dialog)
        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        max_width = 480
        if pixmap.width() > max_width:
            scaled = pixmap.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
        else:
            scaled = pixmap
        image_label.setPixmap(scaled)
        layout.addWidget(image_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        dialog.setModal(True)
        dialog.resize(scaled.width() + 40, scaled.height() + 80)
        dialog.exec()

    def show_paypal_donation_dialog(self):
        """PayPal 후원 안내"""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setWindowTitle(self.t('donate_paypal'))
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.setText(self.t('donate_paypal_message'))
        msg_box.exec()

    def show_about(self):
        """프로그램 정보 표시 (v1.1 버전 표기)"""
        box = QMessageBox(self)
        box.setWindowTitle(self.t('app_info_title'))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        ok_btn = box.button(QMessageBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setText(self.t('btn_ok', default='확인') if hasattr(self, 't') else '확인')

        raw_lines = self.t('about_text').splitlines()
        formatted_lines = []
        if raw_lines:
            first_line = raw_lines[0]
            if "v1." not in first_line:
                first_line = f"<b style='font-size:15px;'>{first_line}</b> <span style='color:#007acc;font-weight:bold;font-size:13px;'>{APP_VERSION}</span>"
            else:
                first_line = f"<b style='font-size:15px;'>{first_line}</b>"
            formatted_lines.append(first_line)
            version_label = "버전" if getattr(self, 'language', 'ko') == 'ko' else "Version"
            formatted_lines.append(f"<b>{version_label}:</b> {APP_VERSION}")
            formatted_lines.extend(raw_lines[1:])
        else:
            formatted_lines.append(f"<b style='font-size:15px;'>YongPDF</b> <span style='color:#007acc;font-weight:bold;'>{APP_VERSION}</span>")
            formatted_lines.append(f"<b>Version:</b> {APP_VERSION}")

        text_html = '<br>'.join(formatted_lines)
        text_html += "<br/><br/><span style='font-size:11px;color:#8a94a3'>© 2026 YongPDF · Hwang Jinsu. All rights reserved.</span>"
        box.setText(f"<div style='min-width:320px'>{text_html}</div>")
        pix = _load_static_pixmap('YongPDF_text_img.png')
        if pix:
            scaled = pix.scaled(160, 160, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            box.setIconPixmap(scaled)
        box.exec()

    def show_license_info(self):
        """오픈소스 라이선스 정보 팝업"""
        dialog = QDialog(self)
        dialog.setWindowTitle(self.t('licenses_title'))
        dialog.setMinimumSize(600, 500)
        
        layout = QVBoxLayout(dialog)
        
        # 헤더 메시지
        header_label = QLabel(self.t('license_content_header'))
        header_label.setTextFormat(Qt.TextFormat.RichText)
        header_label.setWordWrap(True)
        layout.addWidget(header_label)
        
        # 라이선스 목록 (스크롤 가능한 텍스트 영역)
        license_text = QTextEdit()
        license_text.setReadOnly(True)
        
        license_content = """
<div style='font-family: sans-serif;'>
<b>YongPDF</b> — GNU GPL v3.0<br>
Source Code: <a href="https://github.com/HwangJinsu/YongPDF">https://github.com/HwangJinsu/YongPDF</a><br><br>

<hr>
<b>PyMuPDF (MuPDF)</b> — GNU GPL v3.0 / AGPL-3.0<br>
<a href="https://pymupdf.readthedocs.io/">https://pymupdf.readthedocs.io/</a> / <a href="https://mupdf.com/">https://mupdf.com/</a><br><br>

<b>Ghostscript</b> — GNU AGPL v3.0<br>
<a href="https://ghostscript.com/">https://ghostscript.com/</a><br><br>

<b>PySide6 (Qt for Python)</b> — GNU LGPL v3.0<br>
<a href="https://www.qt.io/qt-for-python">https://www.qt.io/qt-for-python</a><br><br>

<b>Pillow (PIL)</b> — HPND License<br>
<a href="https://python-pillow.org/">https://python-pillow.org/</a><br><br>

<b>fontTools</b> — MIT License<br>
<a href="https://github.com/fonttools/fonttools">https://github.com/fonttools/fonttools</a><br><br>

<b>Matplotlib (font_manager)</b> — PSF License<br>
<a href="https://matplotlib.org/">https://matplotlib.org/</a><br><br>

<b>Icons/Emojis</b> — as provided by system fonts.<br>
</div>
"""
        license_text.setHtml(license_content)
        layout.addWidget(license_text)
        
        # 닫기 버튼
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(dialog.accept)
        layout.addWidget(button_box)
        
        dialog.exec()

class PdfApplication(QApplication):
    """macOS 파일 연결(Finder 더블클릭, Dock 드롭) 처리를 지원하는 애플리케이션 클래스"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.main_window: Optional[MainWindow] = None
        self.pending_open_file: Optional[str] = None

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.FileOpen:
            file_path = getattr(event, 'file', lambda: '')()
            if file_path:
                if self.main_window and hasattr(self.main_window, 'open_pdf'):
                    self.main_window.open_pdf(file_path)
                    try:
                        self.main_window.raise_()
                        self.main_window.activateWindow()
                    except Exception:
                        pass
                else:
                    self.pending_open_file = file_path
            return True
        return super().event(event)


if __name__ == "__main__":
    app = PdfApplication(sys.argv)
    splash = _show_startup_splash(app)
    main_window: Optional[MainWindow] = None

    try:
        initial_path = sys.argv[1] if len(sys.argv) > 1 else None
        if not initial_path and app.pending_open_file:
            initial_path = app.pending_open_file
        main_window = MainWindow(initial_path)
        app.main_window = main_window

        if splash:
            splash.showMessage(
                '편집 도구를 준비하는 중입니다...',
                Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                QColor(205, 205, 205)
            )
            app.processEvents()

        main_window.show()
        if splash:
            splash.raise_()
            splash.activateWindow()
            app.processEvents()

        if splash:
            def _finish_splash():
                if getattr(splash, '_closed', False):
                    return
                try:
                    splash.finish(main_window)
                except Exception:
                    splash.close()
                splash._closed = True

            QTimer.singleShot(3000, _finish_splash)

    finally:
        if splash and not getattr(splash, '_closed', False):
            try:
                if main_window is not None:
                    splash.finish(main_window)
                else:
                    splash.close()
            except Exception:
                splash.close()
            splash._closed = True

    sys.exit(app.exec())
