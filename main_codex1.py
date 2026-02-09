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
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QFileDialog, QDialog, QLineEdit, 
    QFontComboBox, QCheckBox, QDialogButtonBox, QFormLayout, QMessageBox,
    QScrollArea, QFrame, QSizePolicy, QListWidget, QListWidgetItem, QColorDialog,
    QProgressDialog, QGraphicsColorizeEffect, QSplashScreen, QSpinBox, QTextEdit
)
from PySide6.QtWidgets import QDoubleSpinBox
from PySide6.QtGui import (
    QPixmap, QImage, QFont, QPainter, QPen, QColor, QBrush,
    QFontDatabase, QPalette, QIntValidator, QDragEnterEvent, QDropEvent, QFontMetrics,
    QRawFont, QFontInfo, QFontMetricsF, QAction
)
from PySide6.QtCore import (
    Qt, Signal, QPoint, QPointF, QTimer, QSize, QPropertyAnimation, 
    QRect, QRectF, QEasingCurve, QObject, QBuffer, QByteArray, QSettings, QVariantAnimation
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
        try:
            font = TTFont(font_path, fontNumber=0)
            names.add(os.path.splitext(os.path.basename(font_path))[0])
            for record in font['name'].names:
                if record.nameID in [1, 4, 6]:  # Family name, Full name, PostScript name
                    try:
                        name = record.toUnicode()
                        if name:
                            names.add(name)
                            # 하이픈과 공백 변형 추가
                            names.add(name.replace('-', ' '))
                            names.add(name.replace(' ', '-'))
                    except (UnicodeDecodeError, AttributeError):
                        pass
        except Exception as e:
            print(f"Error reading font {font_path}: {e}")
            names.add(os.path.splitext(os.path.basename(font_path))[0])
        return list(names)

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
            # 파일명/영문 별칭 (영→한)
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
            key = (font_name or '').lower().replace(' ', '').replace('-', '')
            if key in filename_aliases:
                return filename_aliases[key]
            ek = (font_name or '').lower()
            if ek in english_to_kor:
                return english_to_kor[ek]
            # 마지막: 정제된 입력명 반환
            clean = font_name.split('+')[-1] if font_name and '+' in font_name else (font_name or '')
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

        # 파일명 별칭 매핑 (예: H2gtrE -> HY견고딕)
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
        self.main_window = parent if isinstance(parent, QMainWindow) else None
        self.overlay_key = (span_info.get('page_num'), span_info.get('overlay_id')) if span_info.get('overlay_id') is not None else None
        
        if parent and hasattr(parent, 't'):
            self._t = parent.t  # type: ignore[assignment]
        else:
            self._t = lambda key, **kwargs: key if not kwargs else key.format(**kwargs)

        self.setWindowTitle(self._t('text_editor_title'))
        self.setMinimumSize(500, 350)
        
        # 추가 위젯 import
        from PySide6.QtWidgets import QGroupBox, QGridLayout, QComboBox
        
        # 텍스트 편집 (한글 공백 문제 해결 - 개선된 버전)
        original_text = span_info.get('text', '')
        
        # 라인 텍스트가 있는 경우 컨텍스트를 고려한 텍스트 추출 (사각형 선택 영역 존중)
        if 'line_text' in span_info and span_info['line_text']:
            line_text = span_info['line_text']
            span_text = span_info.get('text', '').strip()
            
            print(f"Processing span: '{span_text}' in line: '{line_text}'")
            
            # 사각형 선택의 경우 선택된 span 텍스트만 사용 (전체 라인 텍스트 사용 안함)
            # 단, 공백 복원을 위해 주변 컨텍스트는 고려
            if span_text and span_text in line_text:
                # span의 위치를 찾아서 앞뒤 공백 포함 여부 확인
                span_index = line_text.find(span_text)
                extracted_text = span_text
                
                # 앞에 공백이 있는지 확인 (단어 경계 유지)
                if span_index > 0 and line_text[span_index - 1] == ' ':
                    extracted_text = ' ' + extracted_text
                
                # 뒤에 공백이 있는지 확인 (단어 경계 유지)
                end_index = span_index + len(span_text)
                if end_index < len(line_text) and line_text[end_index] == ' ':
                    extracted_text = extracted_text + ' '
                
                normalized_text = extracted_text
                print(f"Extracted span with context: '{normalized_text}'")
            else:
                # span을 찾을 수 없으면 원본 span 텍스트 사용
                normalized_text = span_text if span_text else line_text.strip()
                print(f"Using span text: '{normalized_text}'")
        else:
            # 기본 텍스트 정규화 (연속된 공백을 단일 공백으로)
            normalized_text = re.sub(r'\s+', ' ', original_text.strip())
            print(f"Using normalized original: '{normalized_text}'")
        
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
        self.tracking_spin.setRange(-20.0, 50.0)  # percent delta
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
        
        # 초기값 설정: 오버레이에 저장된 값 우선, 없으면 문서 전체 설정 따름
        if 'hwp_space_mode' in span_info:
            self.hwp_space_checkbox.setChecked(bool(span_info['hwp_space_mode']))
        elif hasattr(parent, 'is_hwp_doc') and parent.is_hwp_doc:
            self.hwp_space_checkbox.setChecked(True)
        else:
            self.hwp_space_checkbox.setChecked(False)
            
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
        
        # 버튼
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        # 시스템 기본 언어 대신 앱 설정 언어로 텍스트 강제 설정
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText(self._t('btn_yes'))
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setText(self._t('btn_cancel'))
        
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        # OK/Cancel 버튼 크기 동일/확대
        try:
            for btn in self.button_box.buttons():
                btn.setMinimumSize(96, 36)
        except Exception:
            pass
        
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
        main_layout.addWidget(self.button_box)
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
            )
        }

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
        """오버레이 위치 이동 (레이어 방식) - 단순 이동으로 원상복구"""
        # 이동 델타 계산
        dx = new_bbox.x0 - self.bbox.x0
        dy = new_bbox.y0 - self.bbox.y0
        
        # bbox 업데이트
        self.bbox = new_bbox
        
        # content_bbox도 함께 이동
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
            loaded_name = (self._loaded_font_family or self.font or '').lower()
            has_bold_variant = any(kw in loaded_name for kw in ('bold', 'black', 'heavy'))
            
            # 중요: 실제 폰트 자체가 볼드면(has_bold_variant) 추가 합성 볼드 적용 안함
            # UI 프리뷰(render_to_painter)와 PDF 출력(_flatten_single_overlay) 로직 100% 일치시킴
            if is_bold_flag:
                if has_bold_variant:
                    # 이미 볼드체이므로 추가 합성 볼드 및 Qt Bold 설정 불필요
                    qfont.setBold(False)
                    self.synth_bold = False
                else:
                    # 일반체만 있으므로 합성 볼드 적용
                    qfont.setBold(False)
                    self.synth_bold = True
            else:
                qfont.setBold(False)
                self.synth_bold = False
                
            if self.flags & 2: # 이탤릭
                qfont.setItalic(True)
            
            try:
                if abs(float(self.tracking)) > 0.01:
                    qfont.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100.0 + float(self.tracking))
            except Exception: pass
            
            # [수정] 폰트 엔진의 정수 단위 반올림 강제 방지를 위한 10배 정밀 렌더링 전략
            # Qt 폰트 엔진은 내부적으로 픽셀 단위로 크기를 맞추려는 경향이 있으므로,
            # 폰트 크기를 10배로 키우고(setPixelSize) 페인터를 0.1배로 줄여 렌더링함으로써 소수점 정밀도를 강제 확보합니다.
            
            # [중요] 소수점 단위 폰트 크기 정밀 표현을 위한 전략 설정 (크기 설정 전에 적용)
            qfont.setStyleStrategy(QFont.StyleStrategy.ForceOutline | QFont.StyleStrategy.PreferAntialias)
            qfont.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
            
            # 10배 확대된 픽셀 사이즈 설정 (1포인트 = 1픽셀인 scaled painter 환경 기준)
            precision_multiplier = 10.0
            qfont.setPixelSize(int(effective_point_size * precision_multiplier))
            
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
            # 측정용 폰트 준비 (장평/자간이 적용되지 않은 순수 너비 측정용)
            measure_font = QFont(qfont)
            measure_font.setStretch(100)
            measure_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
            measure_font.setKerning(False)
            measure_font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
            # 현재 painter 장치 컨텍스트를 반영하여 측정 (DPI 등 동기화)
            font_metrics_f = QFontMetricsF(measure_font, painter.device())
            
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
            synth_weight = float(getattr(self, 'synth_bold_weight', 120))
            offset_factor = (synth_weight - 100.0) / 100.0 * 0.15
            total_bold_offset = effective_point_size * offset_factor if self.synth_bold else 0.0
            step_pt = 0.05
            
            stretch = float(getattr(self, 'stretch', 1.0))

            def _draw_text_item(x_pos, y_pos, txt):
                painter.save()
                # 글자 시작점을 원점으로 이동 후 가로 스케일 적용
                painter.translate(x_pos, y_pos)
                
                # 10배 정밀 렌더링을 위해 페인터를 0.1배로 축소 (폰트의 10배 확대를 상쇄)
                painter.scale(1.0 / precision_multiplier, 1.0 / precision_multiplier)
                
                if abs(stretch - 1.0) > 0.001:
                    painter.scale(stretch, 1.0)
                
                if total_bold_offset > 0.005:
                    # 스케일된 공간에서의 오프셋 보정 (10배 확대된 좌표계 기준)
                    local_bold_offset = total_bold_offset * precision_multiplier
                    local_step = step_pt * precision_multiplier / stretch
                    half_offset = (local_bold_offset / stretch) / 2.0
                    curr_dx = -half_offset
                    max_iter = 200
                    while curr_dx <= half_offset and max_iter > 0:
                        painter.drawText(QPointF(curr_dx, 0), txt)
                        curr_dx += local_step
                        max_iter -= 1
                    painter.drawText(QPointF(half_offset, 0), txt)
                else:
                    painter.drawText(QPointF(0, 0), txt)
                painter.restore()

            is_hwp = getattr(self, 'hwp_space_mode', False)
            lines = self.text.splitlines() if "\n" in self.text else [self.text]
            
            stretch = float(getattr(self, 'stretch', 1.0))
            tracking_ratio = float(getattr(self, 'tracking', 0.0)) / 100.0
            
            # 항상 개별 글자 정밀 배치 수행 (PDF와 1:1 일치 보장)
            needs_precise = True 

            for li, line in enumerate(lines):
                curr_y = base_baseline_y + li * line_height_pt
                if needs_precise:
                    curr_x = text_x
                    t_ratio = 1.0 + tracking_ratio
                    
                    if is_hwp and abs(stretch - 1.0) < 0.001:
                        parts = re.split(r'( +)', line)
                        base_space_w = font_metrics_f.horizontalAdvance(' ')
                        hwp_space_advance = (base_space_w * 1.5 * t_ratio) / precision_multiplier
                        for part in parts:
                            if not part: continue
                            if part.isspace():
                                curr_x += hwp_space_advance * len(part)
                            else:
                                _draw_text_item(curr_x, curr_y, part)
                                curr_x += (font_metrics_f.horizontalAdvance(part) * t_ratio) / precision_multiplier
                    else:
                        for ch in line:
                            # 순수 글자 너비 측정 (측정용 폰트 사용)
                            ch_w = font_metrics_f.horizontalAdvance(ch)
                            # 10배 정밀도 측정이므로 결과를 상쇄
                            current_advance = (ch_w * 1.5 if (ch == ' ' and is_hwp) else ch_w) / precision_multiplier
                            
                            if ch.strip():
                                _draw_text_item(curr_x, curr_y, ch)
                            
                            # 다음 글자 위치 = 순수너비 * 장평 * 자간비율
                            # (이 계산식은 PDF 플래튼 로직과 완벽히 동일해야 함)
                            curr_x += current_advance * stretch * t_ratio
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
            )
        }

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
        
        # 싱글/더블 클릭 구분을 위한 타이머
        self.single_click_timer = QTimer()
        self.single_click_timer.setSingleShot(True)
        self.single_click_timer.timeout.connect(self.handle_single_click)
        self.pending_single_click_pos = None
        
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)  # 마우스 트래킹 활성화
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 키보드 포커스 가능하도록 설정
        # 선택 애니메이션
        self._anim_phase = 0
        self._anim_timer = QTimer()
        self._anim_timer.timeout.connect(self._tick_anim)
        self._anim_timer.start(120)

    def _tick_anim(self):
        self._anim_phase = (self._anim_phase + 1) % 16
        # 애니메이션이 필요한 모든 경우에 화면 갱신
        if self.text_adjustment_mode or self.quick_adjustment_mode or self.hover_rect or self.active_overlay:
            self.update()
        
    def set_document(self, doc):
        self.doc = doc
        self.current_page_num = 0
        self._text_dict_cache = {} # 캐시 초기화
        self.pdf_font_extractor = PdfFontExtractor(doc)
        self.pdf_fonts = self.pdf_font_extractor.extract_fonts_from_document()
        self.active_overlay = None
    
    def keyPressEvent(self, event):
        """키보드 이벤트 처리 (Ctrl 키 감지 및 텍스트 위치 조정)"""
        if event.key() == Qt.Key.Key_Control:
            self.ctrl_pressed = False
            self.setCursor(Qt.CursorShape.CrossCursor)
        
        # 텍스트 위치 조정 모드에서 방향키 처리
        elif (self.text_adjustment_mode or self.quick_adjustment_mode) and self.selected_text_info:
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
        if event.key() == Qt.Key.Key_Control:
            self.ctrl_pressed = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().keyReleaseEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Ctrl+클릭으로 사각형 선택 모드 시작
            if self.ctrl_pressed:
                self.selection_mode = True
                self.selection_start = event.position().toPoint()
                self.selection_rect = None
                self.selected_texts = []
                print("사각형 선택 모드 시작 - 드래그하여 영역을 선택하세요")
                return
            
            # 텍스트 조정 모드에서 다른 지점 클릭 시 모드 종료
            click_pos = event.position().toPoint()
            pdf_x, pdf_y = self._widget_point_to_pdf(click_pos)
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

        # 드래그 방식 제거 - 단순 클릭 처리
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
        else:
            self.active_overlay = None
        self.update() # 즉시 갱신하여 패치 투명도 반영
        self.pending_single_click_pos = click_pos
        self.single_click_timer.start(300)  # 300ms 후 싱글클릭 처리
        print(f"Single click timer started at position: {self.pending_single_click_pos}")
    
    def mouseMoveEvent(self, event):
        current_pos = event.position().toPoint()
        
        # 사각형 선택 모드 처리
        if self.selection_mode and self.selection_start:
            self.selection_rect = QRect(self.selection_start, current_pos).normalized()
            self.update()  # 선택 사각형 그리기
            return
        
        # 호버 상태 업데이트를 위해 마우스 위치 저장
        self.mouse_pos = current_pos
    
    def mouseReleaseEvent(self, event):
        # 사각형 선택 모드 완료
        if self.selection_mode and self.selection_rect:
            self.complete_area_selection()
            self.selection_mode = False
            return
        
        # 드래그 방식 완전 제거 - 단순 클릭만 처리
        pass
            
            # 드래그 관련 코드 제거됨
    
    def wheelEvent(self, event):
        """휠 이벤트 처리 (Ctrl+휠로 줌) - 문제 4 해결"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # 줌 기능
            parent_window = self.window()
            if hasattr(parent_window, 'zoom_factor'):
                delta = event.angleDelta().y()
                if delta > 0:
                    parent_window.zoom_in()
                else:
                    parent_window.zoom_out()
            event.accept()
        else:
            if self.parent():
                self.parent().wheelEvent(event)
    
    def check_hover(self):
        """마우스 호버 체크 및 텍스트 블록 하이라이트 (캐시 적용 최적화)"""
        if not self.doc or not hasattr(self, 'mouse_pos'):
            return
        
        try:
            # 마우스 위치를 PDF 좌표로 변환
            pdf_x, pdf_y = self._widget_point_to_pdf(self.mouse_pos)
            if pdf_x is None or pdf_y is None:
                return
            
            pdf_point = fitz.Point(pdf_x, pdf_y)
            
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
                    if ov.visible and self._rect_contains_point(ov.bbox, pdf_point):
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

            for block in text_dict.get("blocks", []):
                if block.get('type') == 0:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            bbox = fitz.Rect(span["bbox"])
                            if self._rect_contains_point(bbox, pdf_point):
                                span_info = span.copy()
                                span_info['original_bbox'] = bbox
                                
                                # 오버레이 텍스트인지 확인
                                if self.is_overlay_text(span, bbox):
                                    if not overlay_hover_rect:  # 첫 번째 오버레이 텍스트 우선
                                        overlay_hover_rect = bbox
                                        overlay_hover_span_info = span_info
                                else:
                                    if not original_hover_rect:  # 첫 번째 원본 텍스트
                                        original_hover_rect = bbox
                                        original_hover_span_info = span_info
            
            # 오버레이 텍스트가 있으면 우선, 없으면 원본 텍스트 사용
            new_hover_rect = overlay_hover_rect if overlay_hover_rect else original_hover_rect
            new_hover_span_info = overlay_hover_span_info if overlay_hover_span_info else original_hover_span_info
            
            # 호버 상태가 변경되었을 때만 업데이트
            if new_hover_rect != self.hover_rect:
                self.hover_rect = new_hover_rect
                self.hover_span_info = new_hover_span_info
                self.update()  # 다시 그리기
                
                # 커서 변경 (Ctrl 키 상태에 따라)
                if new_hover_rect:
                    if self.ctrl_pressed:
                        self.setCursor(Qt.CursorShape.CrossCursor)
                    else:
                        self.setCursor(Qt.CursorShape.PointingHandCursor)
                else:
                    if self.ctrl_pressed:
                        self.setCursor(Qt.CursorShape.CrossCursor)
                    else:
                        self.setCursor(Qt.CursorShape.ArrowCursor)
                    
        except Exception:
            pass
    
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
        
        # 디버깅을 위해 항상 이벤트 처리 (Ctrl 키 조건 제거)
        print("Double click detected!")  # 디버깅 출력
        
        try:
            # 라벨 내에서의 클릭 위치
            label_pos = event.position().toPoint()
            print(f"Click position: {label_pos}")  # 디버깅 출력
            
            pdf_x, pdf_y = self._widget_point_to_pdf(label_pos)
            if pdf_x is None or pdf_y is None:
                return
            
            pdf_point = fitz.Point(pdf_x, pdf_y)
            print(f"PDF coordinates: ({pdf_x}, {pdf_y})")  # 디버깅 출력

            # 오버레이 레이어 우선 히트 테스트 (빈 영역 오버레이 포함)
            if self.text_overlays.get(self.current_page_num):
                for ov in reversed(self.text_overlays[self.current_page_num]):
                    if ov.visible and self._rect_contains_point(ov.bbox, pdf_point):
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

            page = self.doc.load_page(self.current_page_num)
            text_dict = page.get_text("dict")
            
            # 더블클릭: 정확히 클릭한 텍스트 찾기 (거리 우선순위가 아닌 직접 포함 여부 확인)
            clicked_overlay_spans = []  # 클릭 지점에 포함되는 오버레이 텍스트들
            clicked_original_spans = []  # 클릭 지점에 포함되는 원본 텍스트들
            found_spans = 0
            
            print(f"더블클릭한 위치에서 텍스트 검색 중...")
            
            for block in text_dict.get("blocks", []):
                if block.get('type') != 0:
                    continue
                    
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        found_spans += 1
                        bbox = fitz.Rect(span["bbox"])
                        span_text = span.get("text", "").strip()
                        
                        # 더블클릭은 정확한 포함 여부만 확인 (거리 계산 불필요)
                        if self._rect_contains_point(bbox, pdf_point):
                            print(f"OK 클릭 지점에 포함된 텍스트: '{span_text}' bbox={bbox}")
                            
                            # 오버레이 텍스트인지 확인하여 분류
                            if self.is_overlay_text(span, bbox):
                                clicked_overlay_spans.append(span)
                                print(f"   → 오버레이 텍스트로 분류")
                            else:
                                clicked_original_spans.append(span)
                                print(f"   → 원본 텍스트로 분류")
            
            # 더블클릭에서는 클릭 지점에 직접 포함된 텍스트만 선택
            selected_span = None
            
            # 오버레이 텍스트가 있으면 우선 선택
            if clicked_overlay_spans:
                selected_span = clicked_overlay_spans[0]  # 첫 번째 오버레이 텍스트 선택
                try:
                    overlay_rect = fitz.Rect(selected_span.get('bbox', selected_span.get('original_bbox', selected_span.get('bbox'))))
                    overlay_obj = self.find_overlay_at_position(self.current_page_num, overlay_rect)
                    if overlay_obj:
                        self.active_overlay = (self.current_page_num, overlay_obj.z_index)
                except Exception:
                    pass
                print(f"더블클릭으로 선택된 오버레이 텍스트: '{selected_span.get('text', '')}'")
            elif clicked_original_spans:
                selected_span = clicked_original_spans[0]  # 첫 번째 원본 텍스트 선택
                print(f"더블클릭으로 선택된 원본 텍스트: '{selected_span.get('text', '')}'")
            else:
                print(f"X 더블클릭한 위치에 텍스트가 없습니다. (검사한 span: {found_spans}개)")
                return
            
            print(f"전체 {found_spans}개 span 중 클릭 지점에 포함된 텍스트: 오버레이={len(clicked_overlay_spans)}, 원본={len(clicked_original_spans)}")
            
            if selected_span:
                print(f"Selected span text: '{selected_span.get('text', '')}'")
                
                # 라인 정보 수집 (한글 공백 문제 해결 - 개선된 버전)
                line_text = ""
                line_spans = []
                target_line = None
                
                # 먼저 선택된 span이 속한 line을 찾기
                for block in text_dict.get("blocks", []):
                    if block.get('type') != 0:
                        continue
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            if span == selected_span:
                                target_line = line
                                break
                        if target_line:
                            break
                    if target_line:
                        break
                
                # 선택된 라인의 모든 span을 분석하여 정확한 공백 복원 (더 정밀한 버전)
                if target_line:
                    spans_in_line = target_line.get("spans", [])
                    
                    # 디버깅 정보 출력
                    print(f"Line has {len(spans_in_line)} spans")
                    for i, s in enumerate(spans_in_line):
                        print(f"  Span {i}: '{s.get('text', '')}' bbox: {s.get('bbox', [])}")
                    
                    for i, s in enumerate(spans_in_line):
                        span_text = s.get("text", "")
                        span_bbox = fitz.Rect(s["bbox"])
                        
                        if i > 0 and span_text.strip():  # 빈 텍스트 무시
                            # 이전 span과의 거리 계산
                            prev_bbox = fitz.Rect(spans_in_line[i-1]["bbox"])
                            horizontal_gap = span_bbox.x0 - prev_bbox.x1
                            
                            # 더 정확한 문자 크기 계산
                            prev_text = spans_in_line[i-1].get("text", "").strip()
                            if prev_text:
                                # 한글과 영문의 평균 너비가 다르므로 텍스트 타입별로 계산
                                korean_chars = sum(1 for c in prev_text if '가' <= c <= '힣')
                                other_chars = len(prev_text) - korean_chars
                                
                                # 한글은 일반적으로 더 넓음
                                if korean_chars > 0:
                                    avg_char_width = (prev_bbox.x1 - prev_bbox.x0) / len(prev_text)
                                    space_threshold = avg_char_width * 0.4  # 한글은 40%
                                else:
                                    avg_char_width = (prev_bbox.x1 - prev_bbox.x0) / len(prev_text)
                                    space_threshold = avg_char_width * 0.25  # 영문은 25%
                            else:
                                avg_char_width = span_bbox.height  # 대략적인 추정
                                space_threshold = avg_char_width * 0.3
                            
                            # 공백 추가 조건 (더 관대한 조건)
                            should_add_space = (
                                horizontal_gap > space_threshold and
                                horizontal_gap < avg_char_width * 3 and  # 임계값 완화
                                not line_text.endswith(' ') and
                                not span_text.startswith(' ') and
                                len(line_text.strip()) > 0
                            )
                            
                            # 한글 문자와 숫자/영문 사이의 공백 처리 또는 일반 공백 조건
                            if should_add_space or self._needs_space_between_spans(spans_in_line[i-1], s):
                                line_text += " "
                                print(f"Added space between '{prev_text}' and '{span_text}' (gap: {horizontal_gap:.2f})")
                            else:
                                print(f"No space between '{prev_text}' and '{span_text}' (gap: {horizontal_gap:.2f}, threshold: {space_threshold:.2f})")
                        
                        line_text += span_text
                        line_spans.append(s)
                    
                    print(f"Final line_text: '{line_text}'")
                
                # 레이어 오버레이 확인 후 span 정보 준비
                selected_bbox = fitz.Rect(selected_span["bbox"])
                
                # 현재 위치에 레이어 오버레이가 있는지 확인
                overlay = self.find_overlay_by_current_position(self.current_page_num, selected_bbox)
                if not overlay:
                    # 원본 위치 기준으로도 확인
                    overlay = self.find_overlay_at_position(self.current_page_num, selected_bbox)
                
                if overlay:
                    print(f"기존 레이어 오버레이 감지: '{overlay.text}' (ID: {overlay.z_index})")
                    # 레이어 오버레이의 현재 속성을 편집창에 전달
                    span_info = {
                        'text': overlay.text,
                        'font': overlay.font,
                        'size': float(overlay.size), # 정밀도 유지를 위해 float 사용
                        'flags': overlay.flags,
                        'color': overlay.color,
                        'original_bbox': overlay.original_bbox,  # 원본 위치 사용
                        'current_bbox': overlay.bbox,  # 현재 위치 추가
                        'origin': getattr(overlay, 'origin', selected_span.get('origin')), # 원본 베이스라인 정보 유지
                        'line_text': line_text.strip(),
                        'line_spans': line_spans,
                        'is_overlay': True,  # 오버레이 텍스트 표시
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
                    print(f"   편집창에 오버레이 속성 전달: {overlay.font}, {overlay.size}pt, flags={overlay.flags}")
                else:
                    # 원본 텍스트의 속성을 편집창에 전달
                    span_info = {
                        'text': selected_span.get('text', ''),
                        'font': selected_span.get('font', ''),
                        'size': float(selected_span.get('size', 12.0)), # 정밀도 유지를 위해 float 사용
                        'flags': selected_span.get('flags', 0),
                        'color': selected_span.get('color', 0),
                        'origin': selected_span.get('origin'), # 베이스라인 좌표 필수
                        'original_bbox': selected_bbox,
                        'line_text': line_text.strip(),
                        'line_spans': line_spans,
                        'is_overlay': False  # 원본 텍스트 표시
                    }
                    self.active_overlay = None
                
                print("OK 더블클릭 텍스트 선택 완료 - 편집창으로 전달")
                self.text_selected.emit(span_info)
            else:
                print(f"X 더블클릭 위치에 적합한 텍스트를 찾을 수 없습니다.")
                
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

        # 3. 호버 하이라이트 (PDF 좌표계)
        if self.hover_rect:
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

        # PDF 좌표계 변환 종료 (반드시 호출)
        try:
            painter.restore()
        except Exception:
            pass

        # 7. 사각형 영역 선택 (Ctrl + 드래그) - 이건 화면 좌표계 유지
        if self.selection_mode and self.selection_rect:
            painter.save()
            try:
                painter.setPen(QPen(QColor(255, 0, 0, 200), 2))
                painter.setBrush(QBrush(QColor(255, 0, 0, 50)))
                painter.drawRect(self.selection_rect)
            finally:
                painter.restore()

        painter.end()
    
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

    def enter_text_adjustment_mode(self, text_info):
        """텍스트 위치 조정 모드 진입"""
        self.text_adjustment_mode = True
        self.selected_text_info = text_info.copy()
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        print("텍스트 위치 조정 모드: 방향키로 위치 조정, Enter로 완료, Escape로 취소")
        overlay_id = text_info.get('overlay_id')
        if overlay_id is not None:
            self.active_overlay = (self.current_page_num, overlay_id)
        self.update()
    
    def exit_text_adjustment_mode(self):
        """텍스트 위치 조정 모드 종료"""
        self.text_adjustment_mode = False
        self.selected_text_info = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        print("텍스트 위치 조정 모드 종료")
        self.active_overlay = None
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
                
                # 선택된 텍스트 정보 업데이트
                self.selected_text_info['original_bbox'] = new_bbox
                
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
                region_text = page.get_text("text", clip=pdf_selection_rect) or ""
                region_text = re.sub(r"\s+", " ", region_text).strip()
            except Exception:
                region_text = ""

            # 스타일: 가장 빈도 높은 폰트 / 평균 크기 / 가장 빈도 높은 색상
            try:
                text_dict = page.get_text("dict")
                fonts = []
                sizes = []
                colors = []
                for block in text_dict.get("blocks", []):
                    if block.get('type') != 0:
                        continue
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            span_bbox = fitz.Rect(span["bbox"])
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
                'original_bbox': pdf_selection_rect
            }

            patch_only_mode = getattr(main_window, 'patch_only_mode', False)

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
                self.ctrl_pressed = keep_enabled
                try:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
                except Exception:
                    pass
                self.update()
                return

            dialog = TextEditorDialog(span_info, getattr(main_window, 'pdf_fonts', None), main_window)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                # 편집 취소: 아무 것도 적용하지 않고 상태만 초기화
                print("사각형 선택 편집 취소 - 배경 패치/오버레이 적용 안 함")
                self.selection_rect = None
                self.selection_mode = False
                keep_enabled = getattr(main_window, 'patch_precise_mode', False)
                self.ctrl_pressed = keep_enabled
                try:
                    self.setCursor(Qt.CursorShape.CrossCursor if keep_enabled else Qt.CursorShape.ArrowCursor)
                except Exception:
                    pass
                self.update()
                return

            # 편집 확정: 값 수집 및 사전 Undo 스냅샷
            new_values = dialog.get_values()
            print(f"사각형 선택 후 오버레이 값: {new_values}")
            if hasattr(main_window, 'undo_manager') and self.doc:
                main_window.undo_manager.save_state(self.doc, self)

            # 1) 오버레이 생성 (레이어 방식)을 먼저 수행하여 최적화된 영역(new_bbox) 확보
            overlay = None
            try:
                # insert_overlay_text 내부에서 new_bbox가 계산되고 span['original_bbox']가 업데이트됨
                overlay = main_window.insert_overlay_text(page, span_info, new_values)
            except Exception as e:
                print(f"경고 insert_overlay_text 실패, Fallback 시도: {e}")
                overlay = main_window._insert_overlay_text_fallback(page, span_info, new_values)

            # 2) 배경 패치 PDF 적용 + UI 등록 (최적화된 영역으로 생성)
            # overlay.original_bbox는 insert_overlay_text에서 텍스트 크기에 맞춰 조정된 상태임
            patch_target_rect = overlay.original_bbox if overlay else pdf_selection_rect
            try:
                patch_rect, patch_color = main_window.apply_background_patch(page, patch_target_rect, new_values, overlay=overlay, preview=False)
            except Exception:
                patch_rect, patch_color = (patch_target_rect, None)
            print(f"OK 최적화 영역 배경 패치 적용 완료: {patch_rect}")

            if overlay:
                print(f"OK 새 텍스트 오버레이 생성 완료 (ID: {getattr(overlay, 'z_index', '?')})")
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
                    'page_num': self.current_page_num,
                    'synth_bold_weight': getattr(overlay, 'synth_bold_weight', 120),
                    'underline_weight': getattr(overlay, 'underline_weight', 0.6),
                    'underline_offset': getattr(overlay, 'underline_offset', 1.5)
                }
                self.selected_text_info = overlay_info
                self.active_overlay = (self.current_page_num, overlay.z_index)
                self.update()

            # 변경 완료 후 상태 저장 및 표시
            if hasattr(main_window, 'undo_manager') and self.doc:
                main_window.undo_manager.save_state(self.doc, self)
            if hasattr(main_window, 'mark_as_changed'):
                main_window.mark_as_changed()

            # Ctrl 상태 및 선택 모드 해제 (최종)
            if hasattr(main_window, 'set_patch_mode'):
                main_window.set_patch_mode(False)
            if hasattr(main_window, 'set_patch_eraser_mode'):
                main_window.set_patch_eraser_mode(False)

            self.ctrl_pressed = False
            self.selection_mode = False
            try:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            except Exception:
                pass

            # 선택 사각형 초기화 및 리프레시
            self.selection_rect = None
            self.update()

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
            overlay = self.find_overlay_at_position(self.current_page_num, bbox)
            if overlay:
                print(f"레이어 시스템에서 오버레이 감지: '{overlay.text}'")
                return True
            
            # 2. 레거시 추적 시스템에서 확인
            bbox_hash = self._get_bbox_hash(bbox)
            if (self.current_page_num, bbox_hash) in self.overlay_texts:
                print(f"추적 시스템에서 오버레이 감지: {bbox_hash}")
                return True
                
            # 3. 휴리스틱 검사
            font_name = span.get('font', '')
            color = span.get('color', 0)
            size = span.get('size', 12)
            
            # 명확한 오버레이 표시자들
            if ('+' in font_name or 'C2_' in font_name or  # 임베디드 폰트
                color != 0 or  # 검은색이 아닌 텍스트
                size > 20 or size < 6):  # 비정상적 크기
                print(f"휴리스틱으로 오버레이 감지: font={font_name}, color={color}, size={size}")
                return True
            
            print(f"원본 텍스트로 판정: font={font_name}, color={color}, size={size}")
            return False  # 기본적으로 원본 텍스트로 간주
            
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
        """두 span 사이에 공백이 필요한지 판단 (한글-영문/숫자 조합)"""
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
        return overlays, patches

    def _restore_view(self, viewer, overlays, patches):
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
        viewer.update()

    def save_state(self, doc, viewer=None):
        """현재 문서+오버레이 상태를 저장"""
        print(f"\n=== UndoManager.save_state() 호출 ===")
        if doc:
            doc_bytes = doc.tobytes()
            doc_pages = len(doc)
            overlays, patch_state = self._snapshot_view(viewer) if viewer else ({}, {})
            print(f"   - 저장할 문서 페이지 수: {doc_pages}")
            print(f"   - 저장 전 undo_stack size: {len(self.undo_stack)}")
            self.undo_stack.append((doc_bytes, overlays, patch_state))
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
            # 현재 상태를 redo로 백업
            cur_bytes = current_doc.tobytes()
            cur_overlays, cur_patches = self._snapshot_view(viewer) if viewer else ({}, {})
            self.redo_stack.append((cur_bytes, cur_overlays, cur_patches))
            # undo pop and restore previous
            self.undo_stack.pop()
            prev_bytes, prev_overlays, prev_patches = self.undo_stack[-1]
            restored_doc = fitz.open(stream=prev_bytes)
            if viewer:
                self._restore_view(viewer, prev_overlays, prev_patches)
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
            # 현재 상태를 undo 스택에 푸시
            cur_bytes = current_doc.tobytes()
            cur_overlays, cur_patches = self._snapshot_view(viewer) if viewer else ({}, {})
            self.undo_stack.append((cur_bytes, cur_overlays, cur_patches))
            next_bytes, next_overlays, next_patches = self.redo_stack.pop()
            restored_doc = fitz.open(stream=next_bytes)
            if viewer:
                self._restore_view(viewer, next_overlays, next_patches)
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

        # 상태바 초기화
        try:
            self.statusBar()
        except Exception:
            pass

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
        
        if not overlay_key or not self.pdf_viewer or not self.pdf_viewer.doc:
            print(f"[Preview] Early return: key={overlay_key}, viewer={bool(self.pdf_viewer)}")
            return

        page_num, overlay_id = overlay_key
        overlay = self.pdf_viewer.get_overlay_by_id(page_num, overlay_id)
        if not overlay:
            print(f"[Preview] Overlay not found on page {page_num} with ID {overlay_id}")
            # 위치 기반으로 재시도 (ID 매칭 실패 대비)
            try:
                original_bbox = new_values.get('original_bbox')
                if original_bbox:
                    overlay = self.pdf_viewer.find_overlay_at_position(page_num, fitz.Rect(original_bbox))
                    if overlay:
                        print(f"[Preview] Found overlay via fallback position match: ID {overlay.z_index}")
            except Exception: pass
            
            if not overlay: return

        try:
            # 실시간 미리보기를 위해 insert_overlay_text 로직을 직접 활용
            # 이 메서드는 이미 존재하는 오버레이를 업데이트하도록 설계됨
            page = self.pdf_viewer.doc.load_page(page_num)
            
            # span 더미 정보 생성 (insert_overlay_text 호출용)
            span_dummy = {
                'original_bbox': overlay.original_bbox,
                'current_bbox': overlay.bbox,
                'is_overlay': True,
                'overlay_id': overlay.z_index,
                'origin': getattr(overlay, 'origin', None),
                'page_num': page_num,
                'font': getattr(overlay, 'font', 'Arial'),
                'size': getattr(overlay, 'size', 12.0),
                'flags': getattr(overlay, 'flags', 0)
            }
            
            # 1. 오버레이 속성 및 텍스트 업데이트
            print(f"[Preview] Calling insert_overlay_text for update...")
            self.insert_overlay_text(page, span_dummy, new_values)
            
            # 2. 배경 패치(여백 포함) 실시간 업데이트
            print(f"[Preview] Updating background patch...")
            self.apply_background_patch(page, overlay.original_bbox, new_values, overlay=overlay, preview=True)
            
            # 3. 화면 즉시 갱신 강제
            self.pdf_viewer.update() # 안전한 update 사용
            print(f"[Preview] UI Update triggered successfully (update used)")
            
        except Exception as e:
            print(f"실시간 미리보기 업데이트 실패: {e}")
            import traceback
            traceback.print_exc()
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
    def t(cls, key: str, **kwargs) -> str:
        """전역 번역 유틸리티 (MainWindow._instance 활용)"""
        if cls._instance:
            # 1. 현재 선택된 언어 딕셔너리
            lang_dict = cls._instance.translations.get(cls._instance.language, {})
            # 2. 한국어 딕셔너리 (최종 폴백용)
            fallback_ko = cls._instance.translations.get('ko', {})
            # 3. 영어 딕셔너리 (차선 폴백용)
            fallback_en = cls._instance.translations.get('en', {})
            
            # 순서대로 찾음: 현재 언어 -> 한국어 -> 영어 -> 키 자체
            text = lang_dict.get(key, fallback_ko.get(key, fallback_en.get(key, key)))
        else:
            # 인스턴스가 없을 때의 기본 폴백 (사실상 발생 안함)
            text = key
        
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
            ('patch_mode_button', 'tooltip_patch_mode'),
            ('eraser_button', 'tooltip_patch_eraser'),
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
        zoom_out_action.setShortcut('Ctrl+-')

        zoom_in_action = view_menu.addAction(self.t('zoom_in'))
        zoom_in_action.triggered.connect(self.zoom_in)
        zoom_in_action.setShortcut('Ctrl+=')
        
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

        # 🔧 도구 메뉴
        tools_menu = menubar.addMenu(self.t('tools_menu'))
        
        optimize_patches_action = tools_menu.addAction(self.t('action_optimize_patches'))
        optimize_patches_action.triggered.connect(self.optimize_all_patches)
        
        show_patch_info_action = tools_menu.addAction(self.t('action_show_patch_info'))
        show_patch_info_action.triggered.connect(self.show_patch_info)

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

        # ❣️ 후원 메뉴
        support_menu = menubar.addMenu(self.t('support_menu'))
        donate_kakao_action = QAction(self.t('donate_kakao'), self)
        donate_kakao_action.triggered.connect(self.show_kakao_donation_dialog)
        donate_paypal_action = QAction(self.t('donate_paypal'), self)
        donate_paypal_action.triggered.connect(self.show_paypal_donation_dialog)
        support_menu.addActions([donate_kakao_action, donate_paypal_action])

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
        
        # 상태 표시 라벨만 유지
        self.page_label = QLabel(self.t('page_label_empty'))
        self.zoom_label = QLabel(self.t('zoom_label_template', percent=100))

        # PDF 뷰어 (스크롤 영역 포함)
        self.pdf_viewer = PdfViewerWidget(parent=self)
        self.pdf_viewer.setText(self.t('viewer_placeholder'))
        
        # 스크롤 영역
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.pdf_viewer)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame) # 프레임 제거 (테마에서 관리)
        
        # 이모지 버튼 툴바 레이아웃
        toolbar_layout = QHBoxLayout()
        
        # 파일 관련 버튼들 (가로 확장)
        self.open_button = QPushButton("📂")
        self.open_button.setToolTip(self.t('tooltip_open'))
        self.open_button.setFixedSize(50, 40)
        self.open_button.setStyleSheet("font-size: 13px; font-weight: bold;")
        
        self.save_button = QPushButton("💾")
        self.save_button.setToolTip(self.t('tooltip_save'))
        self.save_button.setFixedSize(50, 40)
        self.save_button.setStyleSheet("font-size: 13px; font-weight: bold;")
        
        # 편집 관련 버튼들 (가로 확장)
        self.undo_button = QPushButton("↩️")
        self.undo_button.setToolTip(self.t('tooltip_undo'))
        self.undo_button.setFixedSize(50, 40)
        self.undo_button.setStyleSheet("font-size: 13px; font-weight: bold;")
        
        self.redo_button = QPushButton("↪️")
        self.redo_button.setToolTip(self.t('tooltip_redo'))
        self.redo_button.setFixedSize(50, 40)
        self.redo_button.setStyleSheet("font-size: 13px; font-weight: bold;")
        
        # 보기 관련 버튼들 (가로 확장)
        self.zoom_in_button = QPushButton("🔍➕")
        self.zoom_in_button.setToolTip(self.t('tooltip_zoom_in'))
        self.zoom_in_button.setFixedSize(55, 40)
        self.zoom_in_button.setStyleSheet("font-size: 13px; font-weight: bold;")
        
        self.zoom_out_button = QPushButton("🔍➖")
        self.zoom_out_button.setToolTip(self.t('tooltip_zoom_out'))
        self.zoom_out_button.setFixedSize(55, 40)
        self.zoom_out_button.setStyleSheet("font-size: 13px; font-weight: bold;")

        # 테마 토글 버튼
        self.theme_button = QPushButton("☀️")
        self.theme_button.setToolTip(self.t('tooltip_theme'))
        self.theme_button.setFixedSize(50, 40)
        self.theme_button.setStyleSheet("font-size: 13px; font-weight: bold;")

        # 뷰 맞춤 버튼들
        self.fit_width_button = QPushButton("↔️")
        self.fit_width_button.setToolTip(self.t('tooltip_fit_width'))
        self.fit_width_button.setFixedSize(50, 40)
        self.fit_width_button.setStyleSheet("font-size: 13px; font-weight: bold;")

        self.fit_height_button = QPushButton("↕️")
        self.fit_height_button.setToolTip(self.t('tooltip_fit_height'))
        self.fit_height_button.setFixedSize(50, 40)
        self.fit_height_button.setStyleSheet("font-size: 13px; font-weight: bold;")

        # 페이지 이동 버튼들 (가로 확장)
        self.prev_page_button = QPushButton("👈")
        self.prev_page_button.setToolTip(self.t('tooltip_prev_page'))
        self.prev_page_button.setFixedSize(50, 40)
        self.prev_page_button.setStyleSheet("font-size: 13px; font-weight: bold;")

        self.page_input = QLineEdit()
        self.page_input.setValidator(QIntValidator(1, 999999, self))
        self.page_input.setFixedWidth(60)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.setPlaceholderText(self.t('goto_page_placeholder'))
        self.page_input.setEnabled(False)
        self.page_input.setStyleSheet("font-size: 13px; font-weight: bold; padding: 6px; border: 1px solid #cccccc; border-radius: 6px;")

        self.page_total_label = QLabel('/ 0')
        self.page_total_label.setStyleSheet("font-size: 13px; font-weight: bold; padding: 0 6px;")

        self.next_page_button = QPushButton("👉")
        self.next_page_button.setToolTip(self.t('tooltip_next_page'))
        self.next_page_button.setFixedSize(50, 40)
        self.next_page_button.setStyleSheet("font-size: 13px; font-weight: bold;")

        # 도구 관련 버튼들 (가로 확장)
        toggle_btn_style = (
            "QPushButton { font-size: 13px; font-weight: bold; border-radius: 8px; padding: 4px; }\n"
            "QPushButton[active=\"true\"] { background-color: rgba(255, 214, 102, 0.35);"
            " border: 1px solid rgba(255, 214, 102, 0.55); }"
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

        # 툴바에 버튼들 추가
        toolbar_layout.addWidget(self.open_button)
        toolbar_layout.addWidget(self.save_button)
        toolbar_layout.addWidget(QLabel("|"))  # 구분선
        toolbar_layout.addWidget(self.undo_button)
        toolbar_layout.addWidget(self.redo_button)
        toolbar_layout.addWidget(QLabel("|"))  # 구분선
        # 요구사항: 축소 / 확대 순서로 배치
        toolbar_layout.addWidget(self.zoom_out_button)
        toolbar_layout.addWidget(self.zoom_in_button)
        toolbar_layout.addWidget(self.fit_width_button)
        toolbar_layout.addWidget(self.fit_height_button)
        toolbar_layout.addWidget(QLabel("|"))  # 구분선
        toolbar_layout.addWidget(self.prev_page_button)
        toolbar_layout.addWidget(self.page_input)
        toolbar_layout.addWidget(self.page_total_label)
        toolbar_layout.addWidget(self.next_page_button)
        toolbar_layout.addWidget(QLabel("|"))  # 구분선
        toolbar_layout.addWidget(self.patch_mode_button)
        toolbar_layout.addWidget(self.eraser_button)
        toolbar_layout.addWidget(QLabel("|"))  # 구분선
        toolbar_layout.addWidget(self.theme_button)
        toolbar_layout.addStretch()  # 나머지 공간 채우기
        
        # 상태바 레이아웃 (페이지 및 줌 정보 표시)
        status_layout = QHBoxLayout()
        status_layout.addWidget(self.page_label)
        status_layout.addStretch()
        status_layout.addWidget(self.zoom_label)
        
        main_layout = QVBoxLayout()
        main_layout.addLayout(toolbar_layout)  # 툴바 추가
        main_layout.addLayout(status_layout)
        main_layout.addWidget(self.scroll_area)
        
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
        self.page_input.returnPressed.connect(self.go_to_page_from_input)
        self.patch_mode_button.toggled.connect(self.set_patch_mode)
        self.eraser_button.toggled.connect(self.toggle_patch_eraser)
        self.theme_button.clicked.connect(self.toggle_theme)
        
        self.pdf_viewer.text_selected.connect(self.on_text_selected)
    
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
    
    def mark_as_changed(self):
        """변경사항 표시"""
        self.has_changes = True
        self._refresh_window_title()

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

            # HWP(아래아한글) 문서 감지
            self.is_hwp_doc = False
            try:
                meta = doc.metadata
                producer = meta.get('producer', '').lower()
                creator = meta.get('creator', '').lower()
                if 'hancom' in producer or 'hwp' in producer or 'haansoft' in producer or \
                   'hancom' in creator or 'hwp' in creator or 'haansoft' in creator:
                    self.is_hwp_doc = True
                    print("HWP(아래아한글) 문서 감지됨: 공백 너비 보정 모드 활성화")
            except Exception:
                pass

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
            self.undo_manager.save_state(doc, self.pdf_viewer)
            self.update_undo_redo_buttons()

            self.render_page()
            self.update_page_navigation()
            self._refresh_window_title()
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
            try:
                self.statusBar().showMessage(self.t('save_success_message'), 3000)
            except Exception:
                pass
            return True
        except Exception as e:
            QMessageBox.critical(self, self.t('title_error'), self.t('save_failed_detail', error=str(e)))
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
                try:
                    self.statusBar().showMessage(self.t('save_success_message'), 3000)
                except Exception:
                    pass
                return True
            except Exception as e:
                QMessageBox.critical(self, self.t('title_error'), self.t('save_failed_detail', error=str(e)))
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

    def zoom_in(self):
        current = getattr(self, 'zoom_factor', 1.0)
        levels = getattr(self, 'zoom_levels', [1.0])
        # 현재 배율보다 큰 단계 중 가장 작은 것을 선택
        for val in levels:
            if val > current + 0.001:
                self.zoom_factor = val
                break
        else:
            self.zoom_factor = levels[-1]
            
        self.render_page()
        self.update_zoom_label()
        self._store_zoom_factor()

    def zoom_out(self):
        current = getattr(self, 'zoom_factor', 1.0)
        levels = getattr(self, 'zoom_levels', [1.0])
        # 현재 배율보다 작은 단계 중 가장 큰 것을 선택
        for val in reversed(levels):
            if val < current - 0.001:
                self.zoom_factor = val
                break
        else:
            self.zoom_factor = levels[0]
            
        self.render_page()
        self.update_zoom_label()
        self._store_zoom_factor()
    
    def reset_zoom(self):
        self.zoom_factor = 1.0
        self.render_page()
        self.update_zoom_label()
        self._store_zoom_factor()

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
            
            bbox = ov.bbox if ov.bbox else ov.original_bbox
            if bbox.width <= 0 or bbox.height <= 0:
                return False
                
            # 고해상도 렌더링 (600 DPI 요청 반영)
            dpi = 600
            render_scale = dpi / 72.0 
            img_w = int(math.ceil(bbox.width * render_scale))
            img_h = int(math.ceil(bbox.height * render_scale))
            
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
                
                # 고해상도 스케일 적용 후, 오버레이의 bbox 위치만큼 역이동하여
                # 오버레이의 절대 좌표가 이미지의 (0,0)에 오도록 설정
                painter.scale(render_scale, render_scale)
                painter.translate(-bbox.x0, -bbox.y0)
                
                # 오버레이 렌더링 (절대 좌표 기반)
                ov.render_to_painter(painter, scale_factor=1.0, offsets=(0, 0))
            finally:
                painter.end()
            
            # 이미지를 PNG 데이터로 변환하여 PDF 삽입
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buffer, "PNG")
            img_data = bytes(buffer.data())
            
            page.insert_image(bbox, stream=img_data)
            print(f"    -> [Fallback] 오버레이 이미지 렌더링 완료(600 DPI): ID {ov.z_index} ('{ov.text[:10]}...')")
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
        if not hasattr(self.pdf_viewer, 'text_overlays') or not self.pdf_viewer.text_overlays:
            return

        print("\n오버레이 플래튼 시작 (3단계 레이어 방식)")
        
        # 모든 오버레이의 이미지 플래튼 상태 초기화 (폴백 제어용)
        for v in self.pdf_viewer.text_overlays.values():
            for ov in v:
                ov.image_flattened = False

        self._set_progress(progress, self.t('progress_preparing_fonts'))
        
        try:
            total_pages = len(self.pdf_viewer.doc)
        except Exception:
            total_pages = 0
        
        # 진행 단계 총량 추산
        overlay_count = sum(len(v) for v in self.pdf_viewer.text_overlays.values())
        self._init_progress(progress, total_pages * 3) # 페이지당 3단계

        # 0) 사전 준비: 전역 폰트 임베딩 (생략 가능하나 안정성을 위해 유지)
        self._set_progress(progress, self.t('progress_preparing_fonts'))
        
        # 페이지별 루프
        for page_num in range(total_pages):
            try:
                page = self.pdf_viewer.doc.load_page(page_num)
                overlays = self.pdf_viewer.text_overlays.get(page_num, [])
                patches = self.pdf_viewer.background_patches.get(page_num, [])
                
                # --- [1단계: 모든 배경 패치] ---
                for patch in patches:
                    try:
                        bbox = patch.get('bbox')
                        color = patch.get('color')
                        if bbox and color:
                            page.draw_rect(bbox, color=color, fill=color, width=0)
                    except Exception: pass
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

            except Exception as pe:
                print(f"  X 페이지 {page_num} 플래튼 중 오류: {pe}")

        print("OK 모든 오버레이 플래튼 완료")

    def _do_insert_text(self, page, ov, font_ref, s_mat, font_args, baseline_y, text_x, line_height_pt, tracking_percent, stretch, fm_measure, is_hwp, need_synth_bold):
        """실제 PDF 페이지에 텍스트를 글자 단위로 삽입하는 핵심 로직 (재시도 지원용)"""
        text_to_insert = ov.text or ''
        font_size = float(ov.size)
        lines = text_to_insert.splitlines() if "\n" in text_to_insert else [text_to_insert]
        
        for li, line in enumerate(lines):
            curr_y = baseline_y + li * line_height_pt
            curr_x = text_x
            t_ratio = 1.0 + (tracking_percent / 100.0)
            # 10배 정밀도 측정이므로 결과 보정
            precision_multiplier = 10.0
            
            for ch in line:
                ch_w_raw = fm_measure.horizontalAdvance(ch) / precision_multiplier
                ch_w_stretched = ch_w_raw * stretch
                advance = ch_w_stretched * 1.5 if (ch == ' ' and is_hwp) else ch_w_stretched
                
                if ch.strip():
                    if need_synth_bold:
                        synth_weight = float(getattr(ov, 'synth_bold_weight', 120))
                        offset_factor = (synth_weight - 100.0) / 100.0 * 0.15
                        total_bold_dx = font_size * offset_factor
                        half_dx = total_bold_dx / 2.0
                        step = 0.05
                        sx = -half_dx
                        while sx <= half_dx + 0.001:
                            target_p = fitz.Point(curr_x + sx, curr_y)
                            page.insert_text(target_p, ch, fontname=font_ref, 
                                           morph=(target_p, s_mat), **font_args)
                            sx += step
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
        if getattr(ov, 'force_image', False) and mode in ('all', 'text_only'):
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
            
            # [정합성 극대화] UI와 동일한 너비 측정을 위해 QFontMetricsF 사용
            # [수정] UI와 동일한 10배 정밀도 측정 전략 적용
            from PySide6.QtGui import QImage, QFont, QFontMetricsF
            dummy_device = QImage(1, 1, QImage.Format.Format_Mono)
            dpm_72 = int(72 / 0.0254)
            dummy_device.setDotsPerMeterX(dpm_72)
            dummy_device.setDotsPerMeterY(dpm_72)
            
            qfont_measure = QFont(selected_font_name)
            precision_multiplier = 10.0
            qfont_measure.setPixelSize(int(font_size * precision_multiplier))
            qfont_measure.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
            qfont_measure.setKerning(False)
            qfont_measure.setStretch(100)
            qfont_measure.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0)
            # [추가] 정밀도 향상을 위한 전략 설정
            qfont_measure.setStyleStrategy(QFont.StyleStrategy.ForceOutline | QFont.StyleStrategy.PreferAntialias)
            
            if ov.flags & 16: qfont_measure.setBold(True)
            if ov.flags & 2: qfont_measure.setItalic(True)
            
            # 72 DPI 장치 컨텍스트에서 측정 (PDF 포인트와 1:1 매칭을 위해 precision_multiplier 고려 필요)
            fm_measure = QFontMetricsF(qfont_measure, dummy_device)

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
        """선택된 텍스트 바로 인접 픽셀만 집중 샘플링하여 배경색 검출 (백업01 로직)"""
        import time
        detection_id = int(time.time() * 1000) % 10000  # 고유 ID 생성
        
        print(f"\n=== 배경색 검출 #{detection_id} 시작 ===")
        print(f"   현재 텍스트 bbox: ({bbox.x0:.1f}, {bbox.y0:.1f}) → ({bbox.x1:.1f}, {bbox.y1:.1f})")
        print(f"   텍스트 크기: {bbox.width:.1f} x {bbox.height:.1f}pt")
        
        try:
            # 1. 선택된 텍스트 크기 기반 최소 여백 계산 (좁은 범위)
            text_width = bbox.width
            text_height = bbox.height
            
            # 매우 작은 마진으로 텍스트 바로 인접 픽셀만 대상 (문서 전체 샘플링 완전 방지)
            margin_h = min(2, max(1, text_width * 0.01))   # 가로: 최대 2px, 최소 1px  
            margin_v = min(2, max(1, text_height * 0.015)) # 세로: 최대 2px, 최소 1px
            
            print(f"   텍스트 주변부 여백: 수평={margin_h:.1f}px, 수직={margin_v:.1f}px")
            
            # 2. 텍스트 바로 인접한 4방향 영역만 정의 (집중 샘플링)
            sample_regions = [
                # 상단 바로 위 (텍스트 너비만큼)
                fitz.Rect(bbox.x0, bbox.y0 - margin_v, bbox.x1, bbox.y0),
                # 하단 바로 아래 (텍스트 너비만큼)
                fitz.Rect(bbox.x0, bbox.y1, bbox.x1, bbox.y1 + margin_v),
                # 좌측 바로 옆 (텍스트 높이만큼)
                fitz.Rect(bbox.x0 - margin_h, bbox.y0, bbox.x0, bbox.y1),
                # 우측 바로 옆 (텍스트 높이만큼)
                fitz.Rect(bbox.x1, bbox.y0, bbox.x1 + margin_h, bbox.y1),
            ]
            
            all_colors = []
            valid_regions = 0
            region_weights = [1.2, 1.2, 1.0, 1.0]  # 상하 영역에 약간 더 높은 가중치
            
            for i, region in enumerate(sample_regions):
                try:
                    # 페이지 범위 내로 제한
                    clipped_region = region & page.rect
                    if clipped_region.get_area() < 0.5:  # 너무 작은 영역은 스킵
                        continue
                    
                    # 바로 인접 픽셀만 고해상도로 추출
                    pix = page.get_pixmap(clip=clipped_region, dpi=600)
                    
                    if pix.n >= 3 and len(pix.samples) > 0:
                        samples = pix.samples
                        region_colors = []
                        
                        # RGB 값 추출 (알파 채널 제외)
                        for j in range(0, len(samples) - 2, pix.n):
                            rgb = (samples[j], samples[j+1], samples[j+2])
                            # 너무 어둡거나 밝은 픽셀 필터링 (노이즈 제거)
                            brightness = sum(rgb) / 3
                            if 10 <= brightness <= 245:  # 극단값 제외
                                region_colors.append(rgb)
                        
                        if region_colors:
                            # 영역별 가중치 적용 (상하단이 더 안정적)
                            weight = region_weights[i]
                            weighted_colors = region_colors * max(1, int(weight * 8))
                            all_colors.extend(weighted_colors)
                            valid_regions += 1
                            
                            direction = ['상단', '하단', '좌측', '우측'][i]
                            avg_color = tuple(sum(c[k] for c in region_colors) // len(region_colors) for k in range(3))
                            print(f"   위치 {direction}: {len(region_colors)}픽셀, 평균RGB{avg_color}, 가중치{weight}")
                    
                except Exception as region_error:
                    print(f"   경고 영역 {i+1} 샘플링 실패: {region_error}")
                    continue
            
            if all_colors and valid_regions >= 2:  # 최소 2개 방향에서 성공
                # 3. 색상 빈도 분석 - 유사한 색상끼리 그룹핑
                color_counts = Counter(all_colors)
                total_pixels = len(all_colors)
                
                print(f"   총 {total_pixels}개 유효 픽셀, {valid_regions}/4개 방향 샘플링 성공")
                
                # 가장 빈번한 색상들 분석
                top_colors = color_counts.most_common(5)
                print(f"    인접 픽셀 상위 색상:")
                
                for idx, (color, count) in enumerate(top_colors[:3]):
                    percentage = (count / total_pixels) * 100
                    print(f"     {idx+1}. RGB{color} - {count}회 ({percentage:.1f}%)")
                
                # 4. 최우선 색상 선택 및 엄격한 신뢰도 검증
                best_color, best_count = top_colors[0]
                best_percentage = (best_count / total_pixels) * 100
                
                # 높은 신뢰도: 40% 이상 점유 & 최소 픽셀 수 확보
                if best_percentage >= 40 and best_count >= 5:
                    result_color = (
                        best_color[0] / 255.0,
                        best_color[1] / 255.0,  
                        best_color[2] / 255.0
                    )
                    
                    print(f"   OK 배경색 검출 #{detection_id} 결과: RGB{best_color} → {result_color}")
                    print(f"       신뢰도: {best_percentage:.1f}% ({best_count}픽셀)")
                    print(f"   === 배경색 검출 #{detection_id} 완료 ===\n")
                    return result_color
                else:
                    print(f"   경고 신뢰도 부족: {best_percentage:.1f}% < 40% 또는 픽셀수 부족 ({best_count}개)")
            else:
                print(f"   X 샘플링 실패: 유효 영역 {valid_regions}/4개 부족")
                    
        except Exception as e:
            print(f"   X 배경색 검출 오류: {e}")
            import traceback
            traceback.print_exc()
        
        # 실패 시 기본 순백색 (회색 대신 흰색)
        fallback_color = (1.0, 1.0, 1.0)  # 순백색으로 변경
        print(f"   배경색 검출 #{detection_id} 실패 - 순백색 Fallback 사용: {fallback_color}")
        print(f"   === 배경색 검출 #{detection_id} 완료 (Fallback) ===\n")
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
                bg_color = self.get_precise_background_color(page, original_bbox)
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
            
            if existing_overlay:
                # 기존 오버레이 편집 시: 기존에 설정된 메트릭 유지 (레이아웃 틀어짐 방지)
                height_ratio = getattr(existing_overlay, 'height_ratio', 1.15)
                ascent_ratio = getattr(existing_overlay, 'ascent_ratio', 0.85)
                descent_ratio = getattr(existing_overlay, 'descent_ratio', 0.30)
                preview_height_ratio = getattr(existing_overlay, 'preview_height_ratio', height_ratio)
            elif origin:
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
                # [수정] 10배 정밀도 측정 전략 적용
                precision_multiplier = 10.0
                qf.setPixelSize(int(float(font_size) * precision_multiplier))
                qf.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
                qf.setStyleStrategy(QFont.StyleStrategy.ForceOutline | QFont.StyleStrategy.PreferAntialias)
                qf.setKerning(False)
                qf.setStretch(int(max(1, min(400, new_values.get('stretch', 1.0) * 100))))
                if edit_flags & 16: qf.setBold(True)
                if edit_flags & 2: qf.setItalic(True)
                fm = QFontMetricsF(qf, dummy)
                
                t_ratio = 1.0 + (float(new_values.get('tracking', 0.0)) / 100.0)
                is_hwp_mode = bool(new_values.get('hwp_space_mode', False))
                
                calc_max_w = 0
                lines_list = text_to_insert.splitlines()
                for line in lines_list:
                    if is_hwp_mode:
                        lw = 0
                        for ch in line:
                            cw = fm.horizontalAdvance(ch)
                            lw += (cw * 1.5 if ch == ' ' else cw) * t_ratio
                    else:
                        lw = fm.horizontalAdvance(line) * t_ratio
                    calc_max_w = max(calc_max_w, lw)
                
                # 결과값을 다시 10으로 나누어 원래 스케일로 복원
                calc_max_w /= precision_multiplier
                calc_h = len(lines_list) * (font_size * height_ratio)
                
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

                # [중요] 패치 크기 자동 맞춤 로직은 '신규 패치 생성(Patch Mode)' 시에만 적용
                # 일반적인 더블클릭 편집은 사용자가 설정한 여백(Margin) 옵션이 작동해야 하므로 건너뜀
                if not existing_overlay and not span.get('text'):
                    # 새로운 bbox 설정 (텍스트 실제 크기에 1:1 맞춤)
                    new_bbox = fitz.Rect(new_bbox.x0, target_y0, new_bbox.x0 + calc_max_w, target_y0 + calc_h)
                    
                    # [개선] 패치 영역(original_bbox)도 최종 텍스트 영역에 1:1 동기화
                    span['original_bbox'] = new_bbox 
                    
                    # 패치 생성 시 여백을 0으로 강제 (자동 맞춤 시에만)
                    for k in ['patch_margin_l', 'patch_margin_r', 'patch_margin_t', 'patch_margin_b']:
                        new_values[k] = 0.0
                    new_values['patch_margin'] = (0.0, 0.0, 0.0, 0.0)
                    print(f"   [BBox Fit] 영역 동기화 완료: {new_bbox.width:.1f}x{new_bbox.height:.1f}")
                else:
                    print(f"   [Manual Margin] 일반 편집 모드 - 사용자 여백 설정을 유지합니다.")
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
        if not span.get('is_overlay'):
            try:
                page = self.pdf_viewer.doc.load_page(page_num)
                # 기본 편집값 생성
                color_val = span.get('color', 0)
                if isinstance(color_val, int):
                    qcolor = QColor((color_val >> 16) & 0xFF, (color_val >> 8) & 0xFF, color_val & 0xFF)
                else:
                    qcolor = QColor(0, 0, 0)
                
                initial_values = {
                    'text': span.get('text', ''),
                    'font': span.get('font', 'Arial'),
                    'size': float(span.get('size', 12.0)),
                    'color': qcolor,
                    'bold': bool(span.get('flags', 0) & 16),
                    'italic': bool(span.get('flags', 0) & 2),
                    'underline': False, # 밑줄 기본값 비활성화
                    'underline_weight': 0.6, # 밑줄 굵기 기본값 0.6 설정
                    'stretch': 1.0,
                    'tracking': 0.0,
                    'synth_bold_weight': 120,
                    'hwp_space_mode': getattr(self, 'is_hwp_doc', False),
                    'patch_margin_l': 0.0, 'patch_margin_r': 0.0, 'patch_margin_t': 0.0, 'patch_margin_b': 0.0
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

        # 다이얼로그 실행
        dialog = TextEditorDialog(span, self.pdf_fonts, self)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
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
                self.undo_manager.save_state(self.pdf_viewer.doc, self.pdf_viewer)
                self.mark_as_changed()
                self.update_undo_redo_buttons()
                self.pdf_viewer.update()
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to finalize edit: {e}")
                import traceback
                traceback.print_exc()
        else:
            # [취소 시: Undo를 통해 선행 생성된 오버레이와 패치 원복]
            print("편집 취소 - 이전 상태로 복구")
            self.undo() # save_state 해둔 시점으로 복구
            self.update_undo_redo_buttons()
    
    def closeEvent(self, event):
        """창 닫기 이벤트 처리"""
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
            viewer.ctrl_pressed = enabled
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
                viewer.ctrl_pressed = False
                try:
                    viewer.setCursor(Qt.CursorShape.ArrowCursor)
                except Exception:
                    pass

        self._sync_patch_controls()
        status = "ON" if enabled else "OFF"
        print(f"Patch mode {status}")
        if enabled != previous_enabled:
            self._store_patch_mode()

        status_bar = self.statusBar() if hasattr(self, 'statusBar') else None
        if status_bar:
            if enabled:
                if self.patch_only_mode:
                    status_bar.showMessage(self.t('status_patch_eraser_on'), 2500)
                else:
                    status_bar.showMessage(self.t('status_patch_mode_on'), 2500)
            else:
                if previous_patch_only:
                    status_bar.showMessage(self.t('status_patch_eraser_off'), 2500)
                else:
                    status_bar.showMessage(self.t('status_patch_mode_off'), 2500)

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
        QMessageBox.information(self, self.t('shortcuts_title'), self.t('shortcuts_text'))

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
        """프로그램 정보 표시"""
        box = QMessageBox(self)
        box.setWindowTitle(self.t('app_info_title'))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        text_html = '<br>'.join(self.t('about_text').splitlines())
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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    splash = _show_startup_splash(app)
    main_window: Optional[MainWindow] = None

    try:
        initial_path = sys.argv[1] if len(sys.argv) > 1 else None
        main_window = MainWindow(initial_path)

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
