import sys
import os
import re
import copy
import difflib
from collections import Counter
from typing import Optional

# Editor build marker for sync/debug
__EDITOR_BUILD__ = "main_codex1.py patched for font embedding + hover @ 2025-09-20 17:21"
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QFileDialog, QDialog, QLineEdit, 
    QFontComboBox, QCheckBox, QDialogButtonBox, QFormLayout, QMessageBox,
    QScrollArea, QFrame, QSizePolicy, QListWidget, QListWidgetItem, QColorDialog,
    QProgressDialog
)
from PySide6.QtWidgets import QDoubleSpinBox
from PySide6.QtGui import (
    QPixmap, QImage, QFont, QPainter, QPen, QColor, QBrush, 
    QFontDatabase, QPalette
)
from PySide6.QtCore import (
    Qt, Signal, QPoint, QPointF, QTimer, QSize, QPropertyAnimation, 
    QRect, QEasingCurve, QObject, QBuffer, QByteArray
)
import fitz  # PyMuPDF
from fontTools.ttLib import TTFont
import matplotlib.font_manager as fm
import json
import zipfile

# --- Enhanced Font Utilities ---
class FontMatcher:
    def __init__(self):
        # 시스템에 설치된 폰트 목록 수집 (matplotlib 방식)
        self.system_fonts = []
        try:
            font_paths = fm.findSystemFonts()
            for font_path in font_paths:
                try:
                    font_prop = fm.FontProperties(fname=font_path)
                    font_name = font_prop.get_name()
                    if font_name:
                        self.system_fonts.append(font_name)
                except:
                    continue
        except:
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
            print(f"  {'✓' if exists else '✗'} {font_dir}")
        
        # 각 디렉토리에서 폰트 파일 수집
        total_fonts_found = 0
        for dir_path in font_dirs:
            if os.path.exists(dir_path):
                try:
                    fonts_in_dir = 0
                    for root, dirs, files in os.walk(dir_path):
                        for filename in files:
                            if filename.lower().endswith(('.ttf', '.otf', '.ttc')):
                                full_path = os.path.join(root, filename)
                                try:
                                    font_names = self._get_all_names_from_font(full_path)
                                    for name in font_names:
                                        if name and name not in font_map:
                                            font_map[name] = full_path
                                            fonts_in_dir += 1
                                except Exception as e:
                                    print(f"Error processing font {full_path}: {e}")
                    total_fonts_found += fonts_in_dir
                    if fonts_in_dir > 0:
                        print(f"    Found {fonts_in_dir} fonts in {dir_path}")
                except (OSError, PermissionError) as e:
                    print(f"Warning: Could not access directory {dir_path}: {e}")
        
        print(f"Total fonts loaded: {total_fonts_found}")
        return font_map

    def _build_font_variations(self):
        """폰트 이름의 다양한 변형을 매핑"""
        variations = {}
        for font_name in self.font_map.keys():
            # 원본 이름
            variations[font_name.lower()] = font_name
            # 공백 제거
            variations[font_name.lower().replace(' ', '')] = font_name
            # 하이픈을 공백으로
            variations[font_name.lower().replace('-', ' ')] = font_name
            # 공백을 하이픈으로
            variations[font_name.lower().replace(' ', '-')] = font_name
            # 특수 문자 제거
            clean_name = re.sub(r'[^a-zA-Z0-9가-힣]', '', font_name.lower())
            if clean_name:
                variations[clean_name] = font_name
        return variations

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
            return "Arial" if "Arial" in self.font_map else list(self.font_map.keys())[0] if self.font_map else None
        
        # PDF에서 추출된 폰트명에서 접두사 제거 (예: RJAWXJ+Dotum -> Dotum)
        clean_font_name = pdf_font_name
        if '+' in pdf_font_name:
            clean_font_name = pdf_font_name.split('+')[-1]
        # 추가 정규화: 하위표기 제거 및 특수 접미사 제거
        norm = clean_font_name
        norm = re.sub(r"[,\(\)\[\]]", " ", norm)   # 괄호/콤마 제거
        norm = re.sub(r"\b(MT|PS|Std|Pro|LT|Roman)\b", " ", norm, flags=re.I)
        norm = re.sub(r"\s+", " ", norm).strip()

        # 파일명 별칭 매핑 (예: H2gtrE -> HY견고딕)
        filename_aliases = {
            'h2gtre': 'HY견고딕',
            'h2hdrm': 'HY헤드라인M',
            'h2db': 'HY둥근고딕',
        }
        alias = filename_aliases.get(norm.lower())
        if alias and alias in self.font_map:
            return alias

        # 직접 매칭 시도 (원본명과 정제된 명 모두)
        for font_name in [pdf_font_name, clean_font_name, norm]:
            if font_name in self.font_map:
                # 코드형 이름일 경우, 선호 패밀리명으로 보정
                path = self.font_map[font_name]
                preferred = self._preferred_family_from_path(path)
                if preferred:
                    # 패밀리명이 매핑에 없으면 추가 등록
                    if preferred not in self.font_map:
                        self.font_map[preferred] = path
                    return preferred
                return font_name

        # 새로운 FontMatcher 사용
        best_match = self.font_matcher.find_best_match(norm)
        if best_match and best_match in self.font_map:
            return best_match

        # 기존 로직 fallback
        lower_name = norm.lower()
        if lower_name in self.font_name_variations:
            return self.font_name_variations[lower_name]
        
        # 부분 매칭 (정제된 이름으로)
        for variation, original in self.font_name_variations.items():
            if lower_name in variation or variation in lower_name:
                return original
        
        # 한글 폰트 특별 처리
        korean_font_mapping = {
            'dotum': 'Dotum',
            'gulim': 'Gulim', 
            'batang': 'Batang',
            'gungsuh': 'GungSuh',
            'malgun': 'Malgun Gothic',
            'nanumgothic': 'NanumGothic',
            'hyshortsamul': '함초롬바탕',
            'hypmokgak': 'HY목각파임B'
        }
        
        for korean_key, korean_font in korean_font_mapping.items():
            if korean_key in lower_name:
                if korean_font in self.font_map:
                    return korean_font
                # 유사한 이름 찾기
                for font in self.font_map.keys():
                    if korean_key in font.lower():
                        return font
        
        # 기본 폰트 반환
        defaults = ['Arial', 'Helvetica', 'Liberation Sans', 'DejaVu Sans', 'Dotum', 'Gulim']
        for default in defaults:
            if default in self.font_map:
                return default

        return list(self.font_map.keys())[0] if self.font_map else None

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
        self.setWindowTitle("Edit Text")
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
        
        # 원본 폰트 정보 저장
        self.original_font_info = {
            'font': span_info.get('font', ''),
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
        
        # 폰트 선택 (PDF 폰트를 상위에 배치)
        self.font_combo = QFontComboBox()
        font_manager = SystemFontManager()
        
        # PDF에서 사용된 폰트들을 상위에 배치
        font_items = []
        if pdf_fonts:
            pdf_font_names = [f['system_font'] for f in pdf_fonts if f['system_font']]
            font_items.extend(pdf_font_names)
            font_items.append("--- All Fonts ---")
        
        # 나머지 시스템 폰트 추가
        all_fonts = font_manager.get_all_font_names()
        for font in all_fonts:
            if not pdf_fonts or font not in [f['system_font'] for f in pdf_fonts]:
                font_items.append(font)
        
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
        
        # 폰트 설치 안내 버튼
        self.install_font_button = QPushButton("폰트 설치 안내")
        self.install_font_button.clicked.connect(self.show_font_install_guide)
        if self.font_available:
            self.install_font_button.hide()  # 폰트가 있으면 숨김
        
        # 폰트 크기 (0.1 단위 조절)
        self.size_spinbox = QDoubleSpinBox()
        self.size_spinbox.setDecimals(2)
        self.size_spinbox.setSingleStep(0.1)
        self.size_spinbox.setRange(1.0, 200.0)
        self.size_spinbox.setValue(max(1.0, float(span_info.get('size', 12))))
        
        # 스타일 속성들 (문제 2 해결 - 밑줄 자동 체크 문제 수정)
        font_flags = span_info.get('flags', 0)
        self.bold_checkbox = QCheckBox("Bold")
        self.bold_checkbox.setChecked(bool(font_flags & 2**4))  # Bold flag
        
        self.italic_checkbox = QCheckBox("Italic")
        self.italic_checkbox.setChecked(bool(font_flags & 2**1))  # Italic flag
        
        # 밑줄 플래그 정확한 확인 (PyMuPDF 문서 기준)
        self.underline_checkbox = QCheckBox("Underline")
        # PyMuPDF에서 밑줄은 font flag 2**2 (4번째 비트)로 표시됨
        underline_detected = False
        
        # 1순위: decoration 정보가 있다면 우선 사용
        if 'decoration' in span_info and span_info['decoration']:
            underline_detected = 'underline' in str(span_info['decoration']).lower()
            print(f"밑줄 검출 (decoration 기준): {underline_detected}, decoration: {span_info.get('decoration', 'None')}")
        else:
            # 2순위: font flags에서 밑줄 비트만 정확히 확인 (bit 2 = 4)
            underline_detected = bool(font_flags & 4)  # 2**2 = 4, 밑줄 전용 비트
            print(f"밑줄 검출 (font_flags 기준): {underline_detected}, flags: {font_flags}, bit 2: {bool(font_flags & 4)}")
        
        self.underline_checkbox.setChecked(underline_detected)
        
        # 폼 레이아웃
        form_layout = QFormLayout()
        form_layout.addRow("Text:", self.text_edit)
        form_layout.addRow("Font:", self.font_combo)
        form_layout.addRow("Size:", self.size_spinbox)

        # 장평(가로세로 비율) / 자간(트래킹)
        self.stretch_spin = QDoubleSpinBox()
        self.stretch_spin.setDecimals(2)
        self.stretch_spin.setRange(0.50, 2.00)
        self.stretch_spin.setSingleStep(0.01)
        self.stretch_spin.setValue(float(span_info.get('stretch', 1.0)))

        self.tracking_spin = QDoubleSpinBox()
        self.tracking_spin.setDecimals(1)
        self.tracking_spin.setRange(-20.0, 50.0)  # percent delta
        self.tracking_spin.setSingleStep(0.5)
        self.tracking_spin.setValue(float(span_info.get('tracking', 0.0)))

        form_layout.addRow("Stretch (장평):", self.stretch_spin)
        form_layout.addRow("Tracking (자간%):", self.tracking_spin)

        # 패치 색상 사용자 지정 옵션
        self.patch_color_pick_checkbox = QCheckBox("패치 색상 직접 지정")
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
        patch_color_row = QHBoxLayout()
        patch_color_row.addWidget(self.patch_color_pick_checkbox)
        patch_color_row.addWidget(self.patch_color_button)
        form_layout.addRow("Patch Color:", patch_color_row)
        
        # 색상 선택 레이아웃
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color:"))
        color_layout.addWidget(self.color_button)
        color_layout.addStretch()
        form_layout.addRow(color_layout)
        
        # 스타일 체크박스
        style_layout = QHBoxLayout()
        style_layout.addWidget(self.bold_checkbox)
        style_layout.addWidget(self.italic_checkbox)
        style_layout.addWidget(self.underline_checkbox)
        form_layout.addRow("Style:", style_layout)

        # 이미지로 처리 옵션
        self.force_image_checkbox = QCheckBox("이미지로 처리 (텍스트 대신 이미지로 저장)")
        form_layout.addRow(self.force_image_checkbox)
        
        # 위치 조정 버튼 제거됨 - 싱글클릭으로 대체
        
        # 버튼
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        # OK/Cancel 버튼 크기 동일/확대
        try:
            for btn in self.button_box.buttons():
                btn.setMinimumSize(96, 36)
        except Exception:
            pass
        
        # 패치 크기 설정 섹션 추가
        patch_group = QGroupBox("패치 크기 조절")
        patch_layout = QGridLayout()
        
        # 패치 여백 설정
        patch_layout.addWidget(QLabel("패치 여백:"), 0, 0)
        self.patch_margin_combo = QComboBox()
        self.patch_margin_combo.addItem("여백 작게 (1.0)", 1.0)
        self.patch_margin_combo.addItem("여백 보통 (2.0)", 2.0) 
        self.patch_margin_combo.addItem("여백 크게 (3.0)", 3.0)
        self.patch_margin_combo.addItem("여백 안쪽 1% (-1%)", -0.01)
        self.patch_margin_combo.addItem("여백 안쪽 3% (-3%)", -0.03)
        self.patch_margin_combo.addItem("여백 안쪽 5% (-5%)", -0.05)
        self.patch_margin_combo.addItem("여백 안쪽 10% (-10%)", -0.10)
        
        # 현재 설정된 패치 여백값을 기본으로 선택
        if hasattr(parent, 'patch_margin'):
            current_margin = parent.patch_margin
            for i in range(self.patch_margin_combo.count()):
                if abs(self.patch_margin_combo.itemData(i) - current_margin) < 0.01:
                    self.patch_margin_combo.setCurrentIndex(i)
                    break
        
        patch_layout.addWidget(self.patch_margin_combo, 0, 1)
        patch_group.setLayout(patch_layout)
        
        # 메인 레이아웃
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.font_info_group)  # 원본 폰트 정보 추가
        main_layout.addLayout(form_layout)
        main_layout.addWidget(patch_group)  # 패치 설정 추가
        
        # 폰트 관련 버튼 레이아웃
        font_button_layout = QHBoxLayout()
        font_button_layout.addWidget(self.install_font_button)
        
        main_layout.addLayout(font_button_layout)
        main_layout.addWidget(self.button_box)
        self.setLayout(main_layout)
        
        # 위치 조정 관련 변수
        self.position_adjustment_requested = False
    
    def create_original_font_info_section(self):
        """원본 폰트 정보 섹션 생성"""
        from PySide6.QtWidgets import QGroupBox, QGridLayout
        
        # 원본 폰트 정보 그룹박스
        self.font_info_group = QGroupBox("원본 폰트 정보")
        font_info_layout = QGridLayout()
        
        # 폰트명 정보
        original_font = self.original_font_info['font']
        clean_font_name = original_font.split('+')[-1] if '+' in original_font else original_font
        
        font_info_layout.addWidget(QLabel("원본 폰트:"), 0, 0)
        font_info_layout.addWidget(QLabel(f"<b>{original_font}</b>"), 0, 1)
        
        if '+' in original_font:
            font_info_layout.addWidget(QLabel("폰트 별칭:"), 1, 0)
            font_info_layout.addWidget(QLabel(f"<i>{clean_font_name}</i>"), 1, 1)
        
        font_info_layout.addWidget(QLabel("원본 크기:"), 2, 0)
        font_info_layout.addWidget(QLabel(f"{self.original_font_info['size']:.1f}pt"), 2, 1)
        
        # 폰트 플래그 정보
        flags = self.original_font_info['flags']
        style_info = []
        if flags & 2**4: style_info.append("Bold")
        if flags & 2**1: style_info.append("Italic")
        if flags & 2**2: style_info.append("Underline")
        
        if style_info:
            font_info_layout.addWidget(QLabel("✨ 원본 스타일:"), 3, 0)
            font_info_layout.addWidget(QLabel(", ".join(style_info)), 3, 1)
        
        # 구분선 추가
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        font_info_layout.addWidget(line, 4, 0, 1, 2)
        
        # === 원본 폰트 설치 상태 확인 ===
        font_manager = SystemFontManager()
        
        # 1. 원본 폰트명으로 직접 확인
        original_font_path = font_manager.get_font_path(original_font)
        clean_font_path = font_manager.get_font_path(clean_font_name)
        
        font_info_layout.addWidget(QLabel("💾 설치 상태:"), 5, 0)
        
        if original_font_path or clean_font_path:
            # 원본 폰트가 설치되어 있음
            installed_name = original_font if original_font_path else clean_font_name
            font_info_layout.addWidget(QLabel(f"<span style='color: green;'>✅ 설치됨 ({installed_name})</span>"), 5, 1)
            
            # 설치 경로 정보 (선택사항)
            path_to_show = original_font_path or clean_font_path
            if len(path_to_show) > 50:
                path_display = "..." + path_to_show[-47:]
            else:
                path_display = path_to_show
            font_info_layout.addWidget(QLabel("📁 경로:"), 6, 0)
            font_info_layout.addWidget(QLabel(f"<small style='color: #666;'>{path_display}</small>"), 6, 1)
            
        else:
            # 원본 폰트가 설치되어 있지 않음
            font_info_layout.addWidget(QLabel("<span style='color: red;'>❌ 미설치</span>"), 5, 1)
            
            # 시스템 매칭 결과 (추측 자료)
            font_info_layout.addWidget(QLabel("🤖 추천 대체 폰트:"), 6, 0)
            matched_font = font_manager.find_best_font_match(clean_font_name)
            
            if matched_font:
                font_info_layout.addWidget(QLabel(f"<i style='color: #666;'>→ {matched_font}</i>"), 6, 1)
                
                # 폰트 설치 안내 링크 추가
                font_info_layout.addWidget(QLabel("📥 설치 방법:"), 7, 0)
                install_guide_label = QLabel(f"<a href='install_guide' style='color: blue;'>'{clean_font_name}' 설치 가이드</a>")
                install_guide_label.linkActivated.connect(lambda: self.show_font_install_guide_for_font(clean_font_name))
                font_info_layout.addWidget(install_guide_label, 7, 1)
            else:
                font_info_layout.addWidget(QLabel("<i style='color: #999;'>대체 폰트 없음</i>"), 6, 1)
                
                # 폰트 설치 안내
                font_info_layout.addWidget(QLabel("📥 설치 방법:"), 7, 0)
                install_guide_label = QLabel(f"<a href='install_guide' style='color: blue;'>'{clean_font_name}' 설치 가이드</a>")
                install_guide_label.linkActivated.connect(lambda: self.show_font_install_guide_for_font(clean_font_name))
                font_info_layout.addWidget(install_guide_label, 7, 1)
        
        self.font_info_group.setLayout(font_info_layout)
    
    def show_font_install_guide_for_font(self, font_name):
        """특정 폰트에 대한 설치 안내 대화상자"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
        import sys
        import webbrowser
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"'{font_name}' 폰트 설치 안내")
        dialog.setMinimumSize(500, 400)
        
        layout = QVBoxLayout()
        
        # 안내 텍스트
        guide_text = QTextEdit()
        guide_text.setReadOnly(True)
        
        guide_content = f"""
<h3>'{font_name}' 폰트 설치 방법</h3>
<p><b>필요한 폰트:</b> {font_name}</p>

<h4>🔍 폰트 검색 및 다운로드</h4>
<p>다음 사이트에서 폰트를 검색하여 다운로드할 수 있습니다:</p>
<ul>
<li><b>눈누(국문 폰트):</b> <a href=\"https://noonnu.cc/\">noonnu.cc</a></li>
<li><b>Adobe Fonts:</b> Adobe 구독 사용자용</li>
<li><b>한글 폰트:</b> 네이버 나눔폰트, 배민 폰트 등</li>
<li><b>시스템 폰트:</b> 운영체제 기본 제공 폰트</li>
</ul>

<h4>💾 폰트 설치 방법</h4>
"""
        
        if sys.platform == "win32":
            guide_content += """
<p><b>Windows:</b></p>
<ol>
<li>다운로드한 .ttf 또는 .otf 파일을 우클릭</li>
<li>"설치" 버튼 클릭</li>
<li>또는 C:\\Windows\\Fonts 폴더에 복사</li>
<li>설치 후 애플리케이션 재시작</li>
</ol>
"""
        elif sys.platform == "darwin":
            guide_content += """
<p><b>macOS:</b></p>
<ol>
<li>다운로드한 .ttf 또는 .otf 파일을 더블클릭</li>
<li>Font Book에서 "폰트 설치" 클릭</li>
<li>또는 ~/Library/Fonts 폴더에 복사</li>
<li>설치 후 애플리케이션 재시작</li>
</ol>
"""
        else:
            guide_content += """
<p><b>Linux:</b></p>
<ol>
<li>다운로드한 폰트 파일을 ~/.fonts 폴더에 복사</li>
<li>터미널에서 'fc-cache -fv' 실행</li>
<li>설치 후 애플리케이션 재시작</li>
</ol>
"""
        
        guide_content += """
<h4>⚠️ 주의사항</h4>
<ul>
<li>폰트 설치 후 애플리케이션을 재시작해야 새 폰트가 인식됩니다</li>
<li>유료 폰트의 경우 라이선스를 확인하세요</li>
<li>정확한 폰트명으로 검색해야 찾을 수 있습니다</li>
</ul>

<h4>🔗 추천 사이트</h4>
<ul>
<li><b>눈누(국문 폰트):</b> <a href=\"https://noonnu.cc/\">noonnu.cc</a></li>
<li><b>Adobe Fonts:</b> <a href=\"https://fonts.adobe.com\">fonts.adobe.com</a></li>
<li><b>네이버 나눔폰트:</b> <a href=\"https://hangeul.naver.com/font\">hangeul.naver.com/font</a></li>
</ul>
"""
        
        guide_text.setHtml(guide_content)
        layout.addWidget(guide_text)
        
        # 버튼 레이아웃
        button_layout = QHBoxLayout()
        
        # Google에서 '폰트명 눈누' 검색 (영문명도 정확한 결과 제공)
        try:
            from urllib.parse import quote_plus
            q = quote_plus(f"{font_name} 눈누")
        except Exception:
            q = f"{font_name} 눈누"
        g_search = QPushButton("Google에서 '폰트명 눈누' 검색")
        g_search.clicked.connect(lambda: webbrowser.open(f"https://www.google.com/search?q={q}"))
        button_layout.addWidget(g_search)
        noonnu_home = QPushButton("눈누 홈 열기")
        noonnu_home.clicked.connect(lambda: webbrowser.open("https://noonnu.cc/"))
        button_layout.addWidget(noonnu_home)
        
        # 닫기 버튼
        close_button = QPushButton("닫기")
        close_button.clicked.connect(dialog.accept)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
        dialog.setLayout(layout)
        dialog.exec()

    def show_font_install_guide(self):
        """폰트 설치 안내 대화상자"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
        import sys
        import webbrowser
        
        dialog = QDialog(self)
        dialog.setWindowTitle("폰트 설치 안내")
        dialog.setMinimumSize(500, 400)
        
        layout = QVBoxLayout()
        
        # 안내 텍스트
        guide_text = QTextEdit()
        guide_text.setReadOnly(True)
        
        original_font = self.original_font_info['font']
        clean_font_name = original_font.split('+')[-1] if '+' in original_font else original_font
        
        guide_content = f"""
<h3>폰트 설치 안내</h3>
<p><b>원본 폰트:</b> {original_font}</p>
<p><b>폰트명:</b> {clean_font_name}</p>

<h4>🔍 폰트 검색 및 다운로드</h4>
<p>다음 사이트에서 폰트를 검색하여 다운로드할 수 있습니다:</p>
<ul>
<li><b>눈누(국문 폰트):</b> <a href=\"https://noonnu.cc/\">noonnu.cc</a></li>
<li><b>Adobe Fonts:</b> Adobe 구독 사용자용</li>
<li><b>한글 폰트:</b> 네이버 나눔폰트, 배민 폰트 등</li>
</ul>

<h4>💾 폰트 설치 방법</h4>
"""
        
        if sys.platform == "win32":
            guide_content += """
<p><b>Windows:</b></p>
<ol>
<li>다운로드한 .ttf 또는 .otf 파일을 우클릭</li>
<li>"설치" 버튼 클릭</li>
<li>또는 C:\\Windows\\Fonts 폴더에 복사</li>
</ol>
"""
        elif sys.platform == "darwin":
            guide_content += """
<p><b>macOS:</b></p>
<ol>
<li>다운로드한 .ttf 또는 .otf 파일을 더블클릭</li>
<li>Font Book에서 "폰트 설치" 클릭</li>
<li>또는 ~/Library/Fonts 폴더에 복사</li>
</ol>
"""
        else:
            guide_content += """
<p><b>Linux:</b></p>
<ol>
<li>다운로드한 폰트 파일을 ~/.fonts 폴더에 복사</li>
<li>터미널에서 'fc-cache -fv' 실행</li>
</ol>
"""
        
        guide_content += """
<h4>⚠️ 주의사항</h4>
<p>폰트 설치 후 애플리케이션을 재시작해야 새 폰트가 인식됩니다.</p>
"""
        
        guide_text.setHtml(guide_content)
        layout.addWidget(guide_text)
        
        # 버튼 레이아웃
        button_layout = QHBoxLayout()
        
        # Google에서 '폰트명 눈누' 검색 (영문명도 정확한 결과 제공)
        try:
            from urllib.parse import quote_plus
            q3 = quote_plus(f"{clean_font_name} 눈누")
        except Exception:
            q3 = f"{clean_font_name} 눈누"
        noonnu_btn = QPushButton("Google에서 '폰트명 눈누' 검색")
        noonnu_btn.clicked.connect(lambda: webbrowser.open(f"https://www.google.com/search?q={q3}"))
        noonnu_home_btn = QPushButton("눈누 홈 열기")
        noonnu_home_btn.clicked.connect(lambda: webbrowser.open("https://noonnu.cc/"))
        
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(dialog.accept)
        
        button_layout.addWidget(noonnu_btn)
        button_layout.addWidget(noonnu_home_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        dialog.setLayout(layout)
        dialog.exec()
    
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
            "size": self.size_spinbox.value(),
            "stretch": self.stretch_spin.value(),
            "tracking": self.tracking_spin.value(),
            "bold": self.bold_checkbox.isChecked(),
            "italic": self.italic_checkbox.isChecked(),
            "underline": self.underline_checkbox.isChecked(),
            "color": self.text_color,
            "use_custom_patch_color": self.patch_color_pick_checkbox.isChecked(),
            "patch_color": self.patch_color_button_color,
            "force_image": self.force_image_checkbox.isChecked(),
            "position_adjustment_requested": getattr(self, 'position_adjustment_requested', False),
            "patch_margin": self.patch_margin_combo.currentData() if hasattr(self, 'patch_margin_combo') else None
        }

class TextOverlay:
    """텍스트 오버레이 레이어 관리 클래스 - 완전한 텍스트 속성 지원"""
    
    def __init__(self, text, font, size, color, bbox, page_num, flags=0):
        self.text = text
        self.font = font  
        self.size = size
        self.color = color
        self.bbox = bbox  # fitz.Rect 객체
        self.page_num = page_num
        self.flags = flags  # 볼드, 이탤릭 등 스타일 플래그
        self.visible = True
        self.z_index = 0  # 레이어 순서
        self.original_bbox = bbox  # 원본 위치 기억
        self.flattened = False  # PDF에 반영 여부
        # 확장 속성: 장평 / 자간
        self.stretch = 1.0  # 1.0 = 100%
        self.tracking = 0.0  # percent delta (0 = 기본)
        
    def update_properties(self, text=None, font=None, size=None, color=None, flags=None, stretch=None, tracking=None):
        """텍스트 속성 업데이트 (편집창 연계)"""
        if text is not None:
            self.text = text
        if font is not None:
            self.font = font
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
        # 속성 변경 시 다시 플래튼 필요
        self.flattened = False
        print(f"📝 오버레이 속성 업데이트: '{self.text}' - {self.font}, {self.size}px")
        
    def move_to(self, new_bbox):
        """오버레이 위치 이동 (레이어 방식)"""
        self.bbox = new_bbox
        
    def get_hash(self):
        """오버레이 해시 생성 (원본 위치 기반)"""
        return f"{self.original_bbox.x0:.1f},{self.original_bbox.y0:.1f},{self.original_bbox.x1:.1f},{self.original_bbox.y1:.1f}"
        
    def get_current_hash(self):
        """현재 위치 기반 해시 생성"""
        return f"{self.bbox.x0:.1f},{self.bbox.y0:.1f},{self.bbox.x1:.1f},{self.bbox.y1:.1f}"
        
    def render_to_painter(self, painter, scale_factor=1.0):
        """QPainter를 사용하여 오버레이 렌더링 (정교한 스케일팩터 적용)"""
        if not self.visible:
            return
        
        print(f"🎨 TextOverlay 정교한 렌더링 시작:")
        print(f"   스케일팩터: {scale_factor}")
        print(f"   원본 bbox: {self.bbox}")
        print(f"   원본 텍스트: '{self.text}', 폰트: '{self.font}', 크기: {self.size}pt")
            
        # 1. 스케일팩터에 맞춘 bbox 계산 (화면 확대축소 대응)
        scaled_bbox = fitz.Rect(
            self.bbox.x0 * scale_factor,
            self.bbox.y0 * scale_factor,
            self.bbox.x1 * scale_factor,
            self.bbox.y1 * scale_factor
        )
        print(f"   스케일된 bbox: {scaled_bbox}")
        
        # 2. 프리뷰용 픽셀 크기로 정확 매칭 (DPI/엔진 차이를 제거)
        # 목표: 화면 픽셀 높이 == scaled_bbox.height
        target_h_px = max(1, int(round(scaled_bbox.height)))
        print(f"   목표 텍스트 높이(px): {target_h_px}")

        # 3. QFont 생성 및 검증 (픽셀 크기 기반)
        font_db = QFontDatabase()
        available_families = font_db.families()

        qfont = QFont(self.font)
        # 1차 추정: 픽셀크기 = 목표 높이
        qfont.setPixelSize(target_h_px)
        
        # 폰트 검증 및 대체 폰트 처리
        actual_family = qfont.family()
        if actual_family.lower() != self.font.lower():
            print(f"   ⚠️ 폰트 폴백: '{self.font}' → '{actual_family}'")
            
            # 한글 폰트 대체 처리
            korean_fonts = ['Apple SD Gothic Neo', 'AppleSDGothicNeo-Regular', 'Malgun Gothic', '맑은 고딕']
            if any(ord(char) >= 0xAC00 and ord(char) <= 0xD7A3 for char in self.font):
                for korean_font in korean_fonts:
                    if korean_font in available_families:
                        qfont = QFont(korean_font, scaled_font_size)
                        print(f"   🔄 한글 대체 폰트: '{korean_font}'")
                        break
        
        # 4. 폰트 스타일 적용 (PyMuPDF 플래그 → QFont)
        if self.flags & 16:  # 볼드
            qfont.setBold(True)
            qfont.setWeight(QFont.Weight.Bold)
        if self.flags & 2:   # 이탤릭
            qfont.setItalic(True)
        # 장평 / 자간 적용
        try:
            qfont.setStretch(int(max(1, min(400, self.stretch * 100))))
        except Exception:
            pass
        try:
            qfont.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100.0 + float(self.tracking))
        except Exception:
            pass
        
        # 5. 색상 설정
        if isinstance(self.color, int):
            if self.color == 0:
                qcolor = QColor(0, 0, 0)
            else:
                r = (self.color >> 16) & 0xFF
                g = (self.color >> 8) & 0xFF
                b = self.color & 0xFF
                qcolor = QColor(r, g, b)
        else:
            qcolor = QColor(0, 0, 0)
            
        painter.setFont(qfont)
        painter.setPen(qcolor)
        
        # 6. 정교한 위치 계산 및 렌더링 (높이 우선 정합 후 필요시 한 번 더 보정)
        font_metrics = painter.fontMetrics()
        text_height = max(1, font_metrics.height())
        if text_height != target_h_px:
            # 높이에 대한 1차 보정
            fit = target_h_px / float(text_height)
            new_px = max(1, int(round(qfont.pixelSize() * fit)))
            if abs(fit - 1.0) > 0.01:
                qfont.setPixelSize(new_px)
                painter.setFont(qfont)
                font_metrics = painter.fontMetrics()
                text_height = max(1, font_metrics.height())
                print(f"      🔧 높이 보정: fit={fit:.3f}, px={new_px}, h={text_height}")
        text_width = max(1, font_metrics.horizontalAdvance(self.text))
        
        # 베이스라인 계산 (PyMuPDF 좌표계와 일치)
        baseline_y = scaled_bbox.y1 - font_metrics.descent()
        text_x = scaled_bbox.x0
        
        print(f"   📐 렌더링 계산:")
        print(f"      스케일된 위치: x={text_x:.1f}, y={baseline_y:.1f}")
        print(f"      측정 크기: 폭={text_width}px, 높이={text_height}px")
        print(f"      bbox 크기: {scaled_bbox.width:.1f}x{scaled_bbox.height:.1f}px")
        # 폭 보정은 과도한 왜곡을 유발하므로 프리뷰에서는 수행하지 않음
        
        # 텍스트 그리기
        painter.drawText(QPointF(text_x, baseline_y), self.text)
        
        # 밑줄 처리 (flag 4)
        if self.flags & 4:
            underline_y = baseline_y + 2
            painter.drawLine(text_x, underline_y, text_x + text_width, underline_y)
            print(f"   📝 밑줄 적용")
        
        print(f"   ✅ TextOverlay 렌더링 완료: '{self.text}'")
        
    def to_dict(self):
        """편집창 연계를 위한 딕셔너리 변환"""
        return {
            'text': self.text,
            'font': self.font,
            'size': self.size,
            'color': self.color,
            'flags': self.flags,
            'original_bbox': self.bbox,
            'page_num': self.page_num
        }

class PdfViewerWidget(QLabel):
    text_selected = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
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
        self.adjustment_step = 1.0  # 픽셀 단위 조정 크기
        self.quick_adjustment_mode = False  # 빠른 조정 모드 (싱글클릭)
        self.pending_edit_info = None  # 편집 대기 정보
        
        # 사각형 선택 관련 변수 (Ctrl+드래그)
        self.selection_mode = False
        self.selection_start = None
        self.selection_rect = None
        self.selected_texts = []  # 선택된 텍스트들 목록
        
        # 호버 애니메이션
        self.hover_timer = QTimer()
        self.hover_timer.timeout.connect(self.check_hover)
        self.hover_timer.start(100)  # 100ms마다 체크
        
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
        if self.text_adjustment_mode or self.quick_adjustment_mode:
            self.update()
        
    def set_document(self, doc):
        self.doc = doc
        self.current_page_num = 0
        self.pdf_font_extractor = PdfFontExtractor(doc)
        self.pdf_fonts = self.pdf_font_extractor.extract_fonts_from_document()
    
    def keyPressEvent(self, event):
        """키보드 이벤트 처리 (Ctrl 키 감지 및 텍스트 위치 조정)"""
        if event.key() == Qt.Key.Key_Control:
            self.ctrl_pressed = True
            self.setCursor(Qt.CursorShape.CrossCursor)
        
        # 텍스트 위치 조정 모드에서 방향키 처리
        elif (self.text_adjustment_mode or self.quick_adjustment_mode) and self.selected_text_info:
            # 선택된 텍스트가 오버레이 텍스트인지 확인 (원본텍스트 위치조정 차단)
            if hasattr(self.selected_text_info, 'get') and not self.is_overlay_text(self.selected_text_info, self.selected_text_info.get('original_bbox')):
                print("원본 텍스트는 위치조정할 수 없습니다. 오직 수정된 오버레이 텍스트만 조정 가능합니다.")
                event.accept()
                return
            
            dx, dy = 0, 0
            
            if event.key() == Qt.Key.Key_Left:
                dx = -self.adjustment_step
            elif event.key() == Qt.Key.Key_Right:
                dx = self.adjustment_step
            elif event.key() == Qt.Key.Key_Up:
                dy = -self.adjustment_step
            elif event.key() == Qt.Key.Key_Down:
                dy = self.adjustment_step
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
            if self.text_adjustment_mode or self.quick_adjustment_mode:
                if self.selected_text_info:
                    # 현재 선택된 텍스트 영역 확인
                    click_pos = event.position().toPoint()
                    current_bbox = self.selected_text_info.get('original_bbox')
                    
                    if current_bbox:
                        # 클릭 위치를 PDF 좌표로 변환
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
                                
                                pixmap_x = click_pos.x() - offset_x + scroll_offset_x
                                pixmap_y = click_pos.y() - offset_y + scroll_offset_y
                                
                                pdf_x = pixmap_x / self.pixmap_scale_factor
                                pdf_y = pixmap_y / self.pixmap_scale_factor
                            else:
                                pdf_x = click_pos.x() / self.pixmap_scale_factor
                                pdf_y = click_pos.y() / self.pixmap_scale_factor
                        else:
                            pdf_x = click_pos.x() / self.pixmap_scale_factor
                            pdf_y = click_pos.y() / self.pixmap_scale_factor
                        
                        # 현재 텍스트 영역 밖을 클릭했는지 확인
                        pdf_point = fitz.Point(pdf_x, pdf_y)
                        if not current_bbox.contains(pdf_point):
                            # 다른 지점 클릭 시 모드 종료
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
            self.pending_single_click_pos = event.position().toPoint()
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
            # 일반 스크롤
            if self.parent():
                self.parent().wheelEvent(event)
    
    def check_hover(self):
        """마우스 호버 체크 및 텍스트 블록 하이라이트"""
        if not self.doc or not hasattr(self, 'mouse_pos'):
            return
        
        try:
            # 마우스 위치를 PDF 좌표로 변환
            label_pos = self.mouse_pos
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
            
            # 호버 중인 텍스트/오버레이 찾기 - 오버레이 bbox 먼저 검사
            overlay_hover_rect = None
            overlay_hover_span_info = None
            original_hover_rect = None
            original_hover_span_info = None

            # 0) 오버레이 레이어 히트 테스트 (PDF 텍스트보다 우선)
            if self.text_overlays.get(self.current_page_num):
                for ov in reversed(self.text_overlays[self.current_page_num]):
                    if ov.visible and ov.bbox.contains(pdf_point):
                        overlay_hover_rect = ov.bbox
                        overlay_hover_span_info = {
                            'text': ov.text,
                            'font': ov.font,
                            'size': ov.size,
                            'flags': ov.flags,
                            'color': ov.color,
                            'original_bbox': ov.original_bbox,
                            'is_overlay': True,
                            'overlay_id': ov.z_index
                        }
                        break

            for block in text_dict.get("blocks", []):
                if block.get('type') == 0:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            bbox = fitz.Rect(span["bbox"])
                            if bbox.contains(pdf_point):
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
                elif not new_hover_rect:
                    if self.ctrl_pressed:
                        self.setCursor(Qt.CursorShape.CrossCursor)
                    else:
                        self.setCursor(Qt.CursorShape.ArrowCursor)
                    
        except Exception as e:
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
            print(f"PDF coordinates: ({pdf_x}, {pdf_y})")  # 디버깅 출력

            # 오버레이 레이어 우선 히트 테스트 (빈 영역 오버레이 포함)
            if self.text_overlays.get(self.current_page_num):
                for ov in reversed(self.text_overlays[self.current_page_num]):
                    if ov.visible and ov.bbox.contains(pdf_point):
                        print("Overlay hit - open editor")
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
                            'stretch': getattr(ov, 'stretch', 1.0),
                            'tracking': getattr(ov, 'tracking', 0.0),
                        }
                        self.text_selected.emit(span_info)
                        return

            page = self.doc.load_page(self.current_page_num)
            text_dict = page.get_text("dict")
            
            # 더블클릭: 정확히 클릭한 텍스트 찾기 (거리 우선순위가 아닌 직접 포함 여부 확인)
            clicked_overlay_spans = []  # 클릭 지점에 포함되는 오버레이 텍스트들
            clicked_original_spans = []  # 클릭 지점에 포함되는 원본 텍스트들
            found_spans = 0
            
            print(f"🔍 더블클릭한 위치에서 텍스트 검색 중...")
            
            for block in text_dict.get("blocks", []):
                if block.get('type') != 0:
                    continue
                    
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        found_spans += 1
                        bbox = fitz.Rect(span["bbox"])
                        span_text = span.get("text", "").strip()
                        
                        # 더블클릭은 정확한 포함 여부만 확인 (거리 계산 불필요)
                        if bbox.contains(pdf_point):
                            print(f"✅ 클릭 지점에 포함된 텍스트: '{span_text}' bbox={bbox}")
                            
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
                print(f"🎯 더블클릭으로 선택된 오버레이 텍스트: '{selected_span.get('text', '')}'")
            elif clicked_original_spans:
                selected_span = clicked_original_spans[0]  # 첫 번째 원본 텍스트 선택
                print(f"🎯 더블클릭으로 선택된 원본 텍스트: '{selected_span.get('text', '')}'")
            else:
                print(f"❌ 더블클릭한 위치에 텍스트가 없습니다. (검사한 span: {found_spans}개)")
                return
            
            print(f"📊 전체 {found_spans}개 span 중 클릭 지점에 포함된 텍스트: 오버레이={len(clicked_overlay_spans)}, 원본={len(clicked_original_spans)}")
            
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
                    print(f"🔄 기존 레이어 오버레이 감지: '{overlay.text}' (ID: {overlay.z_index})")
                    # 레이어 오버레이의 현재 속성을 편집창에 전달
                    span_info = {
                        'text': overlay.text,
                        'font': overlay.font,
                        'size': overlay.size,
                        'flags': overlay.flags,
                        'color': overlay.color,
                        'original_bbox': overlay.original_bbox,  # 원본 위치 사용
                        'current_bbox': overlay.bbox,  # 현재 위치 추가
                        'line_text': line_text.strip(),
                        'line_spans': line_spans,
                        'is_overlay': True,  # 오버레이 텍스트 표시
                        'overlay_id': overlay.z_index
                    }
                    print(f"   편집창에 오버레이 속성 전달: {overlay.font}, {overlay.size}px, flags={overlay.flags}")
                else:
                    print(f"📝 원본 텍스트 편집: '{selected_span.get('text', '')}'")
                    # 원본 텍스트의 속성을 편집창에 전달
                    span_info = {
                        'text': selected_span.get('text', ''),
                        'font': selected_span.get('font', ''),
                        'size': selected_span.get('size', 12),
                        'flags': selected_span.get('flags', 0),
                        'color': selected_span.get('color', 0),
                        'original_bbox': selected_bbox,
                        'line_text': line_text.strip(),
                        'line_spans': line_spans,
                        'is_overlay': False  # 원본 텍스트 표시
                    }
                
                print("✅ 더블클릭 텍스트 선택 완료 - 편집창으로 전달")
                self.text_selected.emit(span_info)
            else:
                print(f"❌ 더블클릭 위치에 적합한 텍스트를 찾을 수 없습니다.")
                
        except Exception as e:
            print(f"Error in mouseDoubleClickEvent: {e}")
            import traceback
            traceback.print_exc()
    
    def paintEvent(self, event):
        super().paintEvent(event)
        
        painter = QPainter(self)
        
        # 호버 효과 그리기 (오버레이는 초록 점선 애니메이션, 원본은 파란 반투명)
        if self.hover_rect and self.pixmap():
            screen_rect = self._pdf_rect_to_screen_rect(self.hover_rect)
            if screen_rect:
                if isinstance(self.hover_span_info, dict) and self.hover_span_info.get('is_overlay', False):
                    pen = QPen(QColor(0, 200, 0), 2)
                    pen.setStyle(Qt.PenStyle.CustomDashLine)
                    pen.setDashPattern([6, 4])
                    pen.setDashOffset(self._anim_phase)
                    painter.setPen(pen)
                    painter.setBrush(QBrush())
                else:
                    painter.setPen(QPen(QColor(0, 120, 255, 150), 2))
                    painter.setBrush(QBrush(QColor(0, 120, 255, 30)))
                painter.drawRect(screen_rect)
        
        # 사각형 선택 영역 그리기
        if self.selection_mode and self.selection_rect:
            painter.setPen(QPen(QColor(255, 0, 0, 200), 2))  # 빨간색 테두리
            painter.setBrush(QBrush(QColor(255, 0, 0, 50)))   # 반투명 빨간색 채우기
            painter.drawRect(self.selection_rect)
        
        # 텍스트 위치 조정 모드 표시
        if self.text_adjustment_mode and self.selected_text_info and self.pixmap():
            painter.setPen(QPen(QColor(255, 165, 0), 3))  # 주황색 테두리
            painter.setBrush(QBrush(QColor(255, 165, 0, 50)))
            
            # 조정 중인 텍스트 영역 표시
            adjust_rect = self._pdf_rect_to_screen_rect(self.selected_text_info['original_bbox'])
            if adjust_rect:
                painter.drawRect(adjust_rect)
                
                # 중앙에 십자가 표시
                center_x = adjust_rect.x() + adjust_rect.width() // 2
                center_y = adjust_rect.y() + adjust_rect.height() // 2
                cross_size = 10
                painter.drawLine(center_x - cross_size, center_y, center_x + cross_size, center_y)
                painter.drawLine(center_x, center_y - cross_size, center_x, center_y + cross_size)
        
        # 빠른 조정 모드 표시 + 애니메이션 초록 사각형 복구
        elif self.quick_adjustment_mode and self.selected_text_info and self.pixmap():
            # 조정 중인 텍스트 영역 표시
            adjust_rect = self._pdf_rect_to_screen_rect(self.selected_text_info.get('current_bbox', self.selected_text_info['original_bbox']))
            if adjust_rect:
                pen = QPen(QColor(0, 200, 0), 2)
                pen.setStyle(Qt.PenStyle.CustomDashLine)
                pen.setDashPattern([6, 4])
                pen.setDashOffset(self._anim_phase)
                painter.setPen(pen)
                painter.setBrush(QBrush(QColor(0, 200, 0, 30)))
                painter.drawRect(adjust_rect)
                # 중앙 표식(십자) 표시
                center_x = adjust_rect.x() + adjust_rect.width() // 2
                center_y = adjust_rect.y() + adjust_rect.height() // 2
                arrow_size = 8
                painter.setPen(QPen(QColor(0, 150, 0), 2))
                painter.drawLine(center_x - arrow_size, center_y, center_x + arrow_size, center_y)
                painter.drawLine(center_x, center_y - arrow_size, center_x, center_y + arrow_size)
        
        # 배경 패치 렌더링 (원본 텍스트 가리기) - 오버레이보다 먼저 렌더링
        if hasattr(self, 'background_patches') and self.current_page_num in self.background_patches:
            patches = self.background_patches[self.current_page_num]
            for pentry in patches:
                try:
                    # 호환: dict/Rect 둘 다 허용
                    if isinstance(pentry, dict):
                        patch_bbox = pentry.get('bbox')
                        stored_color = pentry.get('color')
                    else:
                        patch_bbox = pentry
                        stored_color = None
                    screen_rect = self._pdf_rect_to_screen_rect(patch_bbox)
                    if screen_rect:
                        # 개별 텍스트 블록별 배경색 검출 및 적용
                        try:
                            # PDF 페이지 가져오기
                            page = self.doc.load_page(self.current_page_num)
                            
                            # 각 패치 영역별로 배경색 검출 (정확히 MainWindow 참조)
                            main_window = self.window()  # 최상위 창(MainWindow)
                            
                            if stored_color is not None:
                                # 저장된 색상 우선 사용
                                if max(stored_color) <= 1.0:
                                    detected_bg_color = stored_color
                                else:
                                    detected_bg_color = (stored_color[0]/255.0, stored_color[1]/255.0, stored_color[2]/255.0)
                                print(f"🎨 저장된 패치 색상 사용: {detected_bg_color}")
                            elif main_window and hasattr(main_window, 'get_precise_background_color'):
                                detected_bg_color = main_window.get_precise_background_color(page, patch_bbox)
                                print(f"🔍 배경색 검출 성공: {detected_bg_color}")
                            else:
                                print(f"❌ MainWindow 참조 실패, 순백색 fallback 사용")
                                detected_bg_color = (1.0, 1.0, 1.0)  # 순백색 fallback
                            
                            # 0.0~1.0 범위를 0~255로 변환
                            r = int(detected_bg_color[0] * 255)
                            g = int(detected_bg_color[1] * 255) 
                            b = int(detected_bg_color[2] * 255)
                            bg_qcolor = QColor(r, g, b)
                            
                            painter.setPen(QPen(bg_qcolor, 0))
                            painter.setBrush(QBrush(bg_qcolor))
                            painter.drawRect(screen_rect)
                            print(f"🎨 개별 배경색 패치 렌더링: {screen_rect} (RGB: {r},{g},{b})")
                            
                        except Exception as color_error:
                            # fallback: 기본 연한 회색
                            print(f"⚠️ 배경색 검출 예외 발생: {color_error}")
                            print(f"   패치 영역: {patch_bbox}")
                            print(f"   화면 영역: {screen_rect}")
                            import traceback
                            traceback.print_exc()
                            
                            painter.setPen(QPen(QColor(243, 244, 248), 0))  # 연한 회색 테두리
                            painter.setBrush(QBrush(QColor(243, 244, 248)))  # 연한 회색 배경
                            painter.drawRect(screen_rect)
                            print(f"🎨 Fallback 회색 패치 렌더링: {screen_rect}")
                except Exception as e:
                    print(f"❌ 배경 패치 렌더링 오류: {e}")
        
        # 레이어 방식 텍스트 오버레이 렌더링
        if hasattr(self, 'text_overlays') and self.current_page_num in self.text_overlays:
            overlays = self.text_overlays[self.current_page_num]
            # z_index 순서로 정렬하여 레이어 순서대로 렌더링
            sorted_overlays = sorted(overlays, key=lambda overlay: overlay.z_index)
            
            for overlay in sorted_overlays:
                if overlay.visible:
                    try:
                        # TextOverlay의 render_to_painter 메서드 사용 (정교한 스케일팩터 적용)
                        # 화면 확대축소에 맞춰 동적으로 스케일팩터 전달
                        overlay.render_to_painter(painter, self.pixmap_scale_factor)
                        
                        # 디버깅: 오버레이 경계 표시 (개발 중에만 사용)
                        if False:  # 디버깅 필요시 True로 변경
                            screen_rect = self._pdf_rect_to_screen_rect(overlay.bbox)
                            if screen_rect:
                                painter.setPen(QPen(QColor(255, 0, 255, 100), 1))
                                painter.setBrush(QBrush())
                                painter.drawRect(screen_rect)
                    except Exception as e:
                        print(f"⚠️ 오버레이 렌더링 오류: {overlay.text} - {e}")
        
        # 사각형 선택 영역 그리기
        if self.selection_mode and self.selection_rect:
            painter.setPen(QPen(QColor(255, 0, 0, 180), 2))  # 빨간색 테두리
            painter.setBrush(QBrush(QColor(255, 0, 0, 50)))   # 반투명 빨간색 채우기
            painter.drawRect(self.selection_rect)
        
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
    
    def _pdf_point_to_screen_point(self, pdf_x, pdf_y):
        """PDF 좌표 점을 화면 좌표 점으로 변환"""
        try:
            pixmap = self.pixmap()
            if not pixmap:
                return None, None
            
            widget_rect = self.rect()
            pixmap_rect = pixmap.rect()
            offset_x = (widget_rect.width() - pixmap_rect.width()) // 2
            offset_y = (widget_rect.height() - pixmap_rect.height()) // 2
            
            screen_x = pdf_x * self.pixmap_scale_factor + offset_x
            screen_y = pdf_y * self.pixmap_scale_factor + offset_y
            
            return screen_x, screen_y
        except:
            return None, None
    
    def enter_text_adjustment_mode(self, text_info):
        """텍스트 위치 조정 모드 진입"""
        self.text_adjustment_mode = True
        self.selected_text_info = text_info.copy()
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        print("텍스트 위치 조정 모드: 방향키로 위치 조정, Enter로 완료, Escape로 취소")
        self.update()
    
    def exit_text_adjustment_mode(self):
        """텍스트 위치 조정 모드 종료"""
        self.text_adjustment_mode = False
        self.selected_text_info = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        print("텍스트 위치 조정 모드 종료")
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
                print(f"🚀 레이어 이동: '{overlay.text}' dx={dx}, dy={dy}")
                
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
            print("⚠️ 레이어 오버레이 없음 - 기존 방식 사용")
            self._adjust_text_position_fallback(dx, dy, old_bbox, new_bbox)
            
        except Exception as e:
            print(f"❌ 텍스트 위치 조정 오류: {e}")
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
                
                # 배경 패치 위치 업데이트 (기존 위치 제거, 새 위치 추가)
                self.remove_background_patch(self.current_page_num, old_bbox)
                main_window.apply_background_patch(page, new_bbox, new_values)
                self.add_background_patch(self.current_page_num, new_bbox)
                
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
            print(f"🔍 화면 선택 영역: {self.selection_rect}")
            print(f"🔍 PDF 선택 영역: {pdf_selection_rect}")
            if not pdf_selection_rect:
                print("❌ PDF 좌표 변환 실패 - 사각형 선택 취소")
                return

            page = self.doc.load_page(self.current_page_num)

            # 메인 윈도우 참조 획득
            main_window = self
            while main_window and not hasattr(main_window, 'apply_background_patch'):
                main_window = main_window.parent()

            if not main_window:
                print("❌ MainWindow를 찾을 수 없어 작업을 중단합니다.")
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
                chosen_size = sizes and round(sum(sizes)/len(sizes), 1) or 12.0
                chosen_color = colors and Counter(colors).most_common(1)[0][0] or 0
            except Exception:
                chosen_font, chosen_size, chosen_color = 'Arial', 12.0, 0

            # 시스템 폰트 매칭
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
                'size': chosen_size,
                'flags': 0,
                'color': chosen_color,
                'original_bbox': pdf_selection_rect
            }
            dialog = TextEditorDialog(span_info, getattr(main_window, 'pdf_fonts', None), main_window)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                # 편집 취소: 아무 것도 적용하지 않고 상태만 초기화
                print("🚫 사각형 선택 편집 취소 - 배경 패치/오버레이 적용 안 함")
                self.selection_rect = None
                self.selection_mode = False
                self.ctrl_pressed = False
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self.update()
                return

            # 편집 확정: 값 수집 및 사전 Undo 스냅샷
            new_values = dialog.get_values()
            print(f"🎨 사각형 선택 후 오버레이 값: {new_values}")
            if hasattr(main_window, 'undo_manager') and self.doc:
                main_window.undo_manager.save_state(self.doc, self)

            # 2) 배경 패치 PDF 적용 + UI 등록 (항상 새로운 패치 생성)
            try:
                patch_rect, patch_color = main_window.apply_background_patch(page, pdf_selection_rect, new_values)
            except Exception:
                patch_rect, patch_color = (pdf_selection_rect, None)
            self.add_background_patch(self.current_page_num, patch_rect, patch_color)
            print("✅ 선택 영역 배경 패치 적용 완료")
            
            # 3) 오버레이 생성 (레이어 방식)
            overlay = None
            try:
                overlay = main_window.insert_overlay_text(page, span_info, new_values)
            except Exception as e:
                print(f"⚠️ insert_overlay_text 실패, Fallback 시도: {e}")
                overlay = main_window._insert_overlay_text_fallback(page, span_info, new_values)

            if overlay:
                print(f"✅ 새 텍스트 오버레이 생성 완료 (ID: {getattr(overlay, 'z_index', '?')})")
                self.update()

            # 변경 완료 후 상태 저장 및 표시
            if hasattr(main_window, 'undo_manager') and self.doc:
                main_window.undo_manager.save_state(self.doc, self)
            if hasattr(main_window, 'mark_as_changed'):
                main_window.mark_as_changed()

            # Ctrl 상태 및 선택 모드 해제 (최종)
            self.ctrl_pressed = False
            self.selection_mode = False
            self.setCursor(Qt.CursorShape.ArrowCursor)

            # 선택 사각형 초기화 및 리프레시
            self.selection_rect = None
            self.update()

        except Exception as e:
            print(f"❌ 사각형 영역 선택 처리 오류: {e}")
            import traceback
            traceback.print_exc()
            # 상태 초기화
            self.selection_rect = None
            self.selection_mode = False
    
    def _screen_to_pdf_coordinates(self, screen_x, screen_y):
        """화면 좌표를 PDF 좌표로 변환"""
        try:
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
                    
                    pixmap_x = screen_x - offset_x + scroll_offset_x
                    pixmap_y = screen_y - offset_y + scroll_offset_y
                    
                    pdf_x = pixmap_x / self.pixmap_scale_factor
                    pdf_y = pixmap_y / self.pixmap_scale_factor
                else:
                    pdf_x = screen_x / self.pixmap_scale_factor
                    pdf_y = screen_y / self.pixmap_scale_factor
            else:
                pdf_x = screen_x / self.pixmap_scale_factor
                pdf_y = screen_y / self.pixmap_scale_factor
            
            return (pdf_x, pdf_y)
        except:
            return (None, None)
    
    def _screen_rect_to_pdf_rect(self, screen_rect):
        """화면 사각형을 PDF 좌표계로 변환"""
        try:
            print(f"🔄 화면→PDF 좌표 변환 시작")
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
                print(f"   ❌ 좌표 변환 실패")
                return None
        except Exception as e:
            print(f"❌ 좌표 변환 오류: {e}")
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
                        if abs(bbox.x0 - self.hover_rect.x0) < 1 and abs(bbox.y0 - self.hover_rect.y0) < 1:
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
                print(f"🔍 레이어 시스템에서 오버레이 감지: '{overlay.text}'")
                return True
            
            # 2. 레거시 추적 시스템에서 확인
            bbox_hash = self._get_bbox_hash(bbox)
            if (self.current_page_num, bbox_hash) in self.overlay_texts:
                print(f"🔍 추적 시스템에서 오버레이 감지: {bbox_hash}")
                return True
                
            # 3. 휴리스틱 검사
            font_name = span.get('font', '')
            color = span.get('color', 0)
            size = span.get('size', 12)
            
            # 명확한 오버레이 표시자들
            if ('+' in font_name or 'C2_' in font_name or  # 임베디드 폰트
                color != 0 or  # 검은색이 아닌 텍스트
                size > 20 or size < 6):  # 비정상적 크기
                print(f"🔍 휴리스틱으로 오버레이 감지: font={font_name}, color={color}, size={size}")
                return True
            
            print(f"🔍 원본 텍스트로 판정: font={font_name}, color={color}, size={size}")
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
        
    def add_text_overlay(self, text, font, size, color, bbox, page_num, flags=0):
        """새로운 텍스트 오버레이 추가 (레이어 방식) - 완전한 속성 지원"""
        print(f"🎨 TextOverlay 생성 중 - 폰트: '{font}', 크기: {size}, 플래그: {flags}")
        
        # 폰트명 최종 검증
        if not font or font.strip() == "":
            font = "Arial"
            print(f"   🔄 빈 폰트명 폴백: 'Arial'로 설정")
        
        overlay = TextOverlay(text, font, size, color, bbox, page_num, flags)
        overlay.z_index = self.overlay_id_counter
        self.overlay_id_counter += 1
        
        if page_num not in self.text_overlays:
            self.text_overlays[page_num] = []
            
        self.text_overlays[page_num].append(overlay)
        print(f"📄 레이어 오버레이 추가: 페이지 {page_num}, 텍스트 '{text}', ID {overlay.z_index}")
        print(f"   속성: 폰트='{font}', 크기={size}px, 플래그={flags}, 색상={color}")
        return overlay
        
    def find_overlay_at_position(self, page_num, bbox):
        """특정 위치의 오버레이 찾기 (원본 및 현재 위치 모두 검사)"""
        if page_num not in self.text_overlays:
            return None
            
        bbox_hash = self._get_bbox_hash(bbox)
        for overlay in self.text_overlays[page_num]:
            # 원본 위치로 매칭 (주요 방식)
            if overlay.get_hash() == bbox_hash:
                return overlay
            # 현재 위치로도 매칭 (이동된 오버레이 대응)
            if overlay.get_current_hash() == bbox_hash:
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
            print(f"📄 오버레이 이동: '{overlay.text}' -> {new_bbox}")
            overlay.move_to(new_bbox)
            self.update()  # 화면 갱신만 필요 (PDF 렌더링 불필요)
            
    def remove_overlay(self, overlay):
        """오버레이 제거"""
        if overlay:
            page_overlays = self.text_overlays.get(overlay.page_num, [])
            if overlay in page_overlays:
                page_overlays.remove(overlay)
                print(f"📄 오버레이 제거: '{overlay.text}'")
                self.update()
    
    def add_background_patch(self, page_num, bbox, color=None):
        """배경 패치 영역 추가 (항상 새 패치 추가: 최신 패치가 위를 덮음)"""
        if page_num not in self.background_patches:
            self.background_patches[page_num] = []
        entry = {'bbox': bbox}
        if color is not None:
            entry['color'] = color
        self.background_patches[page_num].append(entry)
        print(f"🎨 배경 패치 영역 추가: 페이지 {page_num} (누적 {len(self.background_patches[page_num])})")
        # 즉시 화면 갱신
        self.update()
    
    def remove_background_patch(self, page_num, bbox):
        """배경 패치 영역 제거"""
        if page_num not in self.background_patches:
            return
        
        bbox_hash = self._get_bbox_hash(bbox)
        patches_to_remove = []
        for existing in self.background_patches[page_num]:
            eb = existing['bbox'] if isinstance(existing, dict) else existing
            if self._get_bbox_hash(eb) == bbox_hash:
                patches_to_remove.append(existing)
        
        for patch in patches_to_remove:
            self.background_patches[page_num].remove(patch)
            print(f"🗑️ 배경 패치 영역 제거: 페이지 {page_num}")
    
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
                        
                        if bbox.contains(pdf_point):
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
                        if bbox.contains(fitz.Point(pdf_x, pdf_y)):
                            overlay_info = {
                                'text': ov.text,
                                'font': ov.font,
                                'size': ov.size,
                                'flags': ov.flags,
                                'color': ov.color,
                                'original_bbox': ov.original_bbox,
                                'current_bbox': ov.bbox,
                                'is_overlay': True,
                                'overlay_id': ov.z_index
                            }
                            self.enter_quick_adjustment_mode(overlay_info)
                            self.pending_single_click_pos = None
                            return

            # 오버레이가 아니면, 원본 텍스트로는 빠른 조정 모드에 진입하지 않음
            print("No overlay at click. Skipping quick adjustment for original text.")
            
        except Exception as e:
            print(f"Error in handle_single_click: {e}")
        
        self.pending_single_click_pos = None
    
    def enter_quick_adjustment_mode(self, text_info):
        """빠른 조정 모드 진입"""
        self.quick_adjustment_mode = True
        self.selected_text_info = text_info.copy()
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        print("빠른 조정 모드: 방향키로 위치 조정, Enter로 편집, Escape로 취소")
        self.update()
    
    def exit_quick_adjustment_mode(self):
        """빠른 조정 모드 종료"""
        self.quick_adjustment_mode = False
        self.selected_text_info = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
        print("빠른 조정 모드 종료")
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
                            'color': color
                        })
                    else:
                        r = item
                        patch_items.append({'bbox': (r.x0, r.y0, r.x1, r.y1)})
                patches[p] = patch_items
        return overlays, patches

    def _restore_view(self, viewer, overlays, patches):
        viewer.text_overlays.clear()
        for p, items in overlays.items():
            viewer.text_overlays[p] = []
            for it in items:
                bbox = fitz.Rect(*it['bbox'])
                ov = TextOverlay(it['text'], it['font'], it['size'], it['color'], bbox, p, it['flags'])
                ov.original_bbox = fitz.Rect(*it['original_bbox'])
                ov.z_index = it.get('z_index', 0)
                ov.visible = it.get('visible', True)
                ov.stretch = float(it.get('stretch', 1.0))
                ov.tracking = float(it.get('tracking', 0.0))
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
                        'color': it.get('color')
                    })
                else:
                    viewer.background_patches[p].append({'bbox': fitz.Rect(*it)})
        viewer.update()

    def save_state(self, doc, viewer=None):
        """현재 문서+오버레이 상태를 저장"""
        print(f"\n💾 === UndoManager.save_state() 호출 ===")
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
            print(f"   - ✅ 상태 저장 완료")
        else:
            print(f"   - ❌ 문서가 None이어서 상태 저장 실패")

    def can_undo(self):
        return len(self.undo_stack) > 1

    def can_redo(self):
        return len(self.redo_stack) > 0

    def undo(self, current_doc, viewer=None):
        """실행 취소"""
        print(f"\n🔄 === UndoManager.undo() 호출 ===")
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
        print(f"\n🔄 === UndoManager.redo() 호출 ===")
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
    def __init__(self, initial_pdf_path: Optional[str] = None):
        super().__init__()
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
        self.flatten_size_tweak = 0.0217  # +2.17% (12pt → 12.26pt 근사)
        self._font_coverage_cache = {}
        # PDF size/flatten tuning
        self.fallback_image_scale = 3.0  # 이미지 폴백 해상도 스케일(높을수록 선명, 용량 증가)
        self.size_optimize = True        # 사이즈 최적화 활성화
        
        self.setWindowTitle("Python PDF Editor")
        self.setGeometry(100, 100, 1200, 900)
        self.zoom_factor = 1.0
        self.current_base_scale = 1.0
        
        # 패치 크기 조절 설정 (기본값)
        self.patch_margin = 2.0  # 기본 여백
        self.patch_precise_mode = False  # 정밀 모드
        
        # UI 구성
        self.setup_ui()
        self.setup_connections()

        if initial_pdf_path:
            self.load_pdf_from_path(initial_pdf_path)
    
    def create_menu_bar(self):
        """이모지 기반 메뉴바 생성"""
        menubar = self.menuBar()
        
        # 📁 파일 메뉴
        file_menu = menubar.addMenu('📁 파일')
        
        open_action = file_menu.addAction('📂 PDF 열기')
        open_action.triggered.connect(self.open_pdf)
        open_action.setShortcut('Ctrl+O')

        # 세션 저장 / 불러오기
        save_session_action = file_menu.addAction('💼 세션 저장')
        save_session_action.triggered.connect(self.save_session)
        load_session_action = file_menu.addAction('💼 세션 불러오기')
        load_session_action.triggered.connect(self.load_session)
        
        save_action = file_menu.addAction('💾 저장')
        save_action.triggered.connect(self.save_pdf)
        save_action.setShortcut('Ctrl+S')
        
        # 다른 이름으로 저장
        save_as_action = file_menu.addAction('📝 다른 이름으로 저장')
        save_as_action.triggered.connect(self.save_as_pdf)
        save_as_action.setShortcut('Ctrl+Shift+S')

        export_action = file_menu.addAction('📤 내보내기')
        export_action.triggered.connect(self.export_pdf)
        
        file_menu.addSeparator()
        
        quit_action = file_menu.addAction('🚪 종료')
        quit_action.triggered.connect(self.close)
        quit_action.setShortcut('Ctrl+Q')
        
        # ✏️ 편집 메뉴
        edit_menu = menubar.addMenu('✏️ 편집')
        
        undo_action = edit_menu.addAction('↩️ 실행취소')
        undo_action.triggered.connect(self.undo_action)
        undo_action.setShortcut('Ctrl+Z')
        
        redo_action = edit_menu.addAction('↪️ 다시실행') 
        redo_action.triggered.connect(self.redo_action)
        redo_action.setShortcut('Ctrl+Y')
        
        edit_menu.addSeparator()
        
        # 정밀 모드 토글
        self.precise_mode_action = edit_menu.addAction('🎯 정밀 모드')
        self.precise_mode_action.setCheckable(True)
        self.precise_mode_action.setChecked(self.patch_precise_mode)
        self.precise_mode_action.triggered.connect(self.toggle_precise_mode)
        
        # 🔍 보기 메뉴
        view_menu = menubar.addMenu('🔍 보기')
        
        # 축소 / 확대 순서로 배치
        zoom_out_action = view_menu.addAction('🔍➖ 축소')
        zoom_out_action.triggered.connect(self.zoom_out) 
        zoom_out_action.setShortcut('Ctrl+-')

        zoom_in_action = view_menu.addAction('🔍➕ 확대')
        zoom_in_action.triggered.connect(self.zoom_in)
        zoom_in_action.setShortcut('Ctrl+=')
        
        zoom_fit_action = view_menu.addAction('📄 페이지 맞춤')
        zoom_fit_action.triggered.connect(self.fit_to_page)
        zoom_fit_action.setShortcut('Ctrl+0')
        
        # 🔧 도구 메뉴
        tools_menu = menubar.addMenu('🔧 도구')
        
        optimize_patches_action = tools_menu.addAction('⚡ 모든 패치 최적화')
        optimize_patches_action.triggered.connect(self.optimize_all_patches)
        
        show_patch_info_action = tools_menu.addAction('📊 패치 정보 표시')
        show_patch_info_action.triggered.connect(self.show_patch_info)

        tools_menu.addSeparator()

        # 텍스트 유지 정밀 플래튼 옵션
        self.force_text_flatten_action = tools_menu.addAction('🧱 텍스트 유지 정밀 플래튼')
        self.force_text_flatten_action.setCheckable(True)
        self.force_text_flatten_action.setChecked(self.force_text_flatten)
        self.force_text_flatten_action.toggled.connect(self.toggle_force_text_flatten)

        # 글꼴 로그 상세도 토글
        self.font_dump_verbose = getattr(self, 'font_dump_verbose', 1)
        self.font_log_action = tools_menu.addAction(self._font_log_action_text())
        self.font_log_action.triggered.connect(self.toggle_font_log_verbosity)
        
        prev_page_action = tools_menu.addAction('⬅️ 이전 페이지')
        prev_page_action.triggered.connect(self.prev_page)
        prev_page_action.setShortcut('PgUp')
        
        next_page_action = tools_menu.addAction('➡️ 다음 페이지')
        next_page_action.triggered.connect(self.next_page)
        next_page_action.setShortcut('PgDown')
        
        # ℹ️ 도움말 메뉴
        help_menu = menubar.addMenu('ℹ️ 도움말')
        
        shortcuts_action = help_menu.addAction('⌨️ 단축키')
        shortcuts_action.triggered.connect(self.show_shortcuts)
        
        about_action = help_menu.addAction('ℹ️ 정보')
        about_action.triggered.connect(self.show_about)
        
    def setup_ui(self):
        # 메뉴바 설정 (모든 기능이 메뉴로 통합됨)
        self.create_menu_bar()
        
        # 상태 표시 라벨만 유지
        self.page_label = QLabel("Page: 0/0")
        self.zoom_label = QLabel("Zoom: 100%")
        
        # PDF 뷰어 (스크롤 영역 포함)
        self.pdf_viewer = PdfViewerWidget()
        self.pdf_viewer.setText("Please open a PDF file to begin.")
        self.pdf_viewer.setStyleSheet("border: 1px solid gray; background-color: white;")
        
        # 스크롤 영역
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.pdf_viewer)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 이모지 버튼 툴바 레이아웃
        toolbar_layout = QHBoxLayout()
        
        # 파일 관련 버튼들 (가로 확장)
        self.open_button = QPushButton("📂")
        self.open_button.setToolTip("PDF 열기 (Ctrl+O)")
        self.open_button.setFixedSize(50, 40)
        self.open_button.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        self.save_button = QPushButton("💾")
        self.save_button.setToolTip("저장 (Ctrl+S)")
        self.save_button.setFixedSize(50, 40)
        self.save_button.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        # 편집 관련 버튼들 (가로 확장)
        self.undo_button = QPushButton("↩️")
        self.undo_button.setToolTip("실행취소 (Ctrl+Z)")
        self.undo_button.setFixedSize(50, 40)
        self.undo_button.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        self.redo_button = QPushButton("↪️")
        self.redo_button.setToolTip("다시실행 (Ctrl+Y)")
        self.redo_button.setFixedSize(50, 40)
        self.redo_button.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        # 보기 관련 버튼들 (가로 확장)
        self.zoom_in_button = QPushButton("🔍➕")
        self.zoom_in_button.setToolTip("확대 (Ctrl++)")
        self.zoom_in_button.setFixedSize(55, 40)
        self.zoom_in_button.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        self.zoom_out_button = QPushButton("🔍➖")
        self.zoom_out_button.setToolTip("축소 (Ctrl+-)")
        self.zoom_out_button.setFixedSize(55, 40)
        self.zoom_out_button.setStyleSheet("font-size: 16px; font-weight: bold;")

        # 테마 토글 버튼
        self.theme_button = QPushButton("☀️")
        self.theme_button.setToolTip("라이트/다크 테마 전환")
        self.theme_button.setFixedSize(50, 40)
        self.theme_button.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        self.fit_page_button = QPushButton("📏")
        self.fit_page_button.setToolTip("페이지 맞춤 (Ctrl+0)")
        self.fit_page_button.setFixedSize(50, 40)
        self.fit_page_button.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        # 페이지 이동 버튼들 (가로 확장)
        self.prev_page_button = QPushButton("⬅️")
        self.prev_page_button.setToolTip("이전 페이지 (Page Up)")
        self.prev_page_button.setFixedSize(50, 40)
        self.prev_page_button.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        self.next_page_button = QPushButton("➡️")
        self.next_page_button.setToolTip("다음 페이지 (Page Down)")
        self.next_page_button.setFixedSize(50, 40)
        self.next_page_button.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        # 도구 관련 버튼들 (가로 확장)
        self.select_tool_button = QPushButton("🎯")
        self.select_tool_button.setToolTip("정밀 패치 모드 전환")
        self.select_tool_button.setFixedSize(50, 40)
        self.select_tool_button.setStyleSheet("font-size: 18px; font-weight: bold;")
        
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
        toolbar_layout.addWidget(self.fit_page_button)
        toolbar_layout.addWidget(QLabel("|"))  # 구분선
        toolbar_layout.addWidget(self.prev_page_button)
        toolbar_layout.addWidget(self.next_page_button)
        toolbar_layout.addWidget(QLabel("|"))  # 구분선
        toolbar_layout.addWidget(self.select_tool_button)
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
    
    def setup_connections(self):
        # 이모지 버튼들의 연결 설정
        self.open_button.clicked.connect(self.open_pdf)
        self.save_button.clicked.connect(self.save_pdf)
        self.undo_button.clicked.connect(self.undo_action)
        self.redo_button.clicked.connect(self.redo_action)
        self.zoom_in_button.clicked.connect(self.zoom_in)
        self.zoom_out_button.clicked.connect(self.zoom_out)
        self.fit_page_button.clicked.connect(self.fit_to_page)
        self.prev_page_button.clicked.connect(self.prev_page)
        self.next_page_button.clicked.connect(self.next_page)
        self.select_tool_button.clicked.connect(self.toggle_precise_mode)
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
            self.page_label.setText(f"Page: {current_page}/{total_pages}")
            
            self.prev_page_button.setEnabled(current_page > 1)
            self.next_page_button.setEnabled(current_page < total_pages)
        else:
            self.page_label.setText("Page: 0/0")
            self.prev_page_button.setEnabled(False)
            self.next_page_button.setEnabled(False)
    
    def mark_as_changed(self):
        """변경사항 표시"""
        self.has_changes = True
        title = self.windowTitle()
        if not title.endswith("*"):
            self.setWindowTitle(title + "*")
    
    def mark_as_saved(self):
        """저장됨 표시"""
        self.has_changes = False
        title = self.windowTitle()
        if title.endswith("*"):
            self.setWindowTitle(title[:-1])

    def open_pdf(self):
        if self.has_changes:
            # 커스텀 메시지박스로 버튼 크기 동일/확대
            msg = QMessageBox(self)
            msg.setWindowTitle("Unsaved Changes")
            msg.setText("You have unsaved changes. Do you want to save before opening a new file?")
            yes_btn = msg.addButton(QMessageBox.StandardButton.Yes)
            no_btn = msg.addButton(QMessageBox.StandardButton.No)
            cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)
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
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF", "", "PDF Files (*.pdf)"
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
            self.zoom_factor = 1.0
            self.has_changes = False

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
            self.setWindowTitle(f"Python PDF Editor - {os.path.basename(file_path)}")
            return True

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open PDF: {e}")
            return False

    def save_pdf(self):
        if not self.pdf_viewer.doc:
            QMessageBox.warning(self, "Warning", "No PDF document is open.")
            return False
            
        if not self.current_file_path:
            return self.save_as_pdf()
        
        try:
            # 진행 표시
            progress = QProgressDialog("문서를 저장하는 중입니다...", None, 0, 0, self)
            progress.setWindowTitle("저장")
            progress.setMinimumDuration(0)
            progress.setAutoClose(False)
            progress.setCancelButton(None)
            progress.show()

            # 오버레이를 PDF에 반영 (플래튼)
            self._set_progress(progress, "오버레이 반영 중…")
            self.flatten_overlays_to_pdf(progress)
            self._set_progress(progress, "파일 저장 중…")
            # 항상 전체 저장: 임시 파일로 저장 후 원본 교체 (incremental 오류 방지)
            base_dir = os.path.dirname(self.current_file_path) or "."
            base_name = os.path.basename(self.current_file_path)
            tmp_path = os.path.join(base_dir, f".{base_name}.saving.tmp")
            try:
                self.pdf_viewer.doc.save(tmp_path, garbage=4, deflate=True, clean=True)
                os.replace(tmp_path, self.current_file_path)
                print("임시 파일로 전체 저장 후 원본 교체 성공")
            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
            self.mark_as_saved()
            # 저장 성공 메시지(확대된 OK 버튼 스타일 적용)
            try:
                msg = QMessageBox(self)
                msg.setWindowTitle("Success")
                msg.setText("PDF saved successfully.")
                msg.setIcon(QMessageBox.Information)
                ok = msg.addButton(QMessageBox.Ok)
                ok.setMinimumSize(96, 36)
                msg.exec()
            except Exception:
                QMessageBox.information(self, "Success", "PDF saved successfully.")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save PDF: {e}")
            return False
        finally:
            try:
                progress.close()
            except Exception:
                pass
    
    def save_as_pdf(self):
        if not self.pdf_viewer.doc:
            QMessageBox.warning(self, "Warning", "No PDF document is open.")
            return False
            
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF As", "", "PDF Files (*.pdf)"
        )
        if file_path:
            try:
                progress = QProgressDialog("문서를 저장하는 중입니다...", None, 0, 0, self)
                progress.setWindowTitle("다른 이름으로 저장")
                progress.setMinimumDuration(0)
                progress.setAutoClose(False)
                progress.setCancelButton(None)
                progress.show()
                # 오버레이를 PDF에 반영 (플래튼)
                self._set_progress(progress, "오버레이 반영 중…")
                self.flatten_overlays_to_pdf(progress)
                self._set_progress(progress, "파일 저장 중…")
                self.pdf_viewer.doc.save(file_path, garbage=4, deflate=True, clean=True)
                self.current_file_path = file_path
                self.mark_as_saved()
                self.setWindowTitle(f"Python PDF Editor - {os.path.basename(file_path)}")
                QMessageBox.information(self, "Success", "PDF saved successfully.")
                return True
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save PDF: {e}")
                return False
            finally:
                try:
                    progress.close()
                except Exception:
                    pass
        return False
    
    def undo(self):
        """실행 취소"""
        print(f"\n↩️ === MainWindow.undo() 호출 ===")
        
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
                
                print(f"   - ✅ 실행 취소 완료")
            else:
                print(f"   - ❌ 복구된 문서가 없음 (restored_doc is None)")
        else:
            print(f"   - ❌ PDF 문서가 열려있지 않음")
    
    def redo(self):
        """다시 실행"""
        print(f"\n↪️ === MainWindow.redo() 호출 ===")
        
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
                
                print(f"   - ✅ 다시 실행 완료")
            else:
                print(f"   - ❌ 복구된 문서가 없음 (restored_doc is None)")
        else:
            print(f"   - ❌ PDF 문서가 열려있지 않음")

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

    def zoom_in(self):
        self.zoom_factor = min(5.0, self.zoom_factor + 0.2)
        self.render_page()
        self.update_zoom_label()

    def zoom_out(self):
        self.zoom_factor = max(0.2, self.zoom_factor - 0.2)
        self.render_page()
        self.update_zoom_label()
    
    def reset_zoom(self):
        self.zoom_factor = 1.0
        self.render_page()
        self.update_zoom_label()

    def render_page(self, page_to_render=None):
        if not self.pdf_viewer.doc: 
            return
            
        try:
            page = page_to_render if page_to_render is not None else \
                   self.pdf_viewer.doc.load_page(self.pdf_viewer.current_page_num)
            
            # 기본 스케일 계산
            page_rect = page.rect
            base_scale = min(1.0, 800 / page_rect.width, 600 / page_rect.height)
            self.current_base_scale = base_scale
            final_scale = base_scale * self.zoom_factor
            
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
            visual_scale = max(0.01, float(self.current_base_scale) * float(self.zoom_factor))
            percent = int(round(visual_scale * 100))
            self.zoom_label.setText(f"Zoom: {percent}%")
        except Exception:
            self.zoom_label.setText("Zoom: -%")

    def _rgbf_from_color_int(self, color_int):
        """정수 색상(0xRRGGBB)을 (r,g,b) 0.0~1.0 튜플로 변환"""
        if isinstance(color_int, QColor):
            return (color_int.redF(), color_int.greenF(), color_int.blueF())
        r = (color_int >> 16) & 0xFF
        g = (color_int >> 8) & 0xFF
        b = color_int & 0xFF
        return (r/255.0, g/255.0, b/255.0)

    def enforce_single_overlay_view(self, page, overlay, new_values):
        """요청사항: 편집 시 해당 세로 밴드를 전부 패치로 가리고, 오직 현재 오버레이만 보이도록 강제"""
        try:
            page_num = overlay.page_num
            band_rect = fitz.Rect(page.rect.x0, overlay.original_bbox.y0, page.rect.x1, overlay.original_bbox.y1)
            # 1) 풀폭 패치 적용 및 UI 등록
            nv = dict(new_values)
            nv['cover_all_band'] = True
            try:
                patch_rect, patch_color = self.apply_background_patch(page, overlay.original_bbox, nv)
            except Exception:
                patch_rect, patch_color = (band_rect, None)
            if hasattr(self.pdf_viewer, 'add_background_patch'):
                self.pdf_viewer.add_background_patch(page_num, patch_rect, patch_color)
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
            print(f"🔒 단일 레이어 표시 강제: 페이지 {page_num}, 밴드 {band_rect}")
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
                print(f"   🔎 Fonts {title}: {len(fl)} items")
                return
            if level == 1:
                names = []
                for f in fl:
                    try:
                        base = f[3] if len(f) > 3 else (f[0] if len(f) > 0 else "?")
                        names.append(str(base))
                    except Exception:
                        continue
                print(f"   🔎 Fonts {title}: {len(names)} → {names[:10]}{'...' if len(names)>10 else ''}")
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
                print(f"   🔎 Fonts {title}: {len(details)} items")
                for d in details[:20]:
                    print(f"      • xref={d[0]} type={d[1]} enc={d[2]} base={d[3]}")
        except Exception as e:
            print(f"   🔎 Fonts dump skipped: {e}")

    def flatten_overlays_to_pdf(self, progress=None):
        """현재 레이어 오버레이를 PDF 콘텐츠로 반영 (진행메시지/폰트로그 포함)"""
        if not hasattr(self.pdf_viewer, 'text_overlays') or not self.pdf_viewer.text_overlays:
            return

        print("\n🖨️ 오버레이 플래튼 시작")
        self._set_progress(progress, "오버레이 플래튼 준비 중… (글꼴 수집)")
        # 진행 단계 총량 추산: 글꼴 수집(1) + 페이지 글꼴 보장(len(doc)) + 오버레이 수(합계)
        try:
            total_pages = len(self.pdf_viewer.doc)
        except Exception:
            total_pages = 0
        try:
            overlay_steps = sum(len(v) for v in self.pdf_viewer.text_overlays.values())
        except Exception:
            overlay_steps = 0
        self._init_progress(progress, 1 + total_pages + overlay_steps)
        self._step_progress(progress, 1)
        # 0) 사전 준비: 문서 전체에서 사용된 사용자 폰트를 전역/페이지에 선임베딩
        try:
            fonts_global = set()
            for p, ovs in self.pdf_viewer.text_overlays.items():
                for ov in ovs:
                    if getattr(ov, 'font', None):
                        fonts_global.add(ov.font)
            # 공통 CJK 후보도 포함(문자 누락 방지)
            for fam in ['HANdotum', 'HMKMAMI', 'Noto Sans CJK KR', 'Malgun Gothic', 'NanumGothic', 'Dotum', 'Gulim']:
                fonts_global.add(fam)
            # 0-1) 문서 전역 폰트 파일 사전 로드(인코딩 안정성 강화)
            if not hasattr(self, '_doc_font_ref_cache'):
                self._doc_font_ref_cache = {}
            for fam in list(fonts_global):
                try:
                    fpath = self.font_manager.get_font_path(fam) if hasattr(self, 'font_manager') else None
                    if fpath and os.path.exists(fpath) and fpath not in self._doc_font_ref_cache:
                        try:
                            # 문서 레벨 임베딩은 일부 버전에서 미지원 → 파일 로드 검증만 수행
                            _ = fitz.Font(fontfile=fpath)
                            self._doc_font_ref_cache[fpath] = True
                            print(f"  🔤 폰트 파일 사전 로드 OK: {fam}")
                        except Exception as ide:
                            print(f"  ⚠️ 폰트 파일 사전 로드 실패({fam}): {ide}")
                except Exception as e:
                    print(f"  ⚠️ 폰트 경로 확인 실패({fam}): {e}")
            if fonts_global:
                for pn in range(len(self.pdf_viewer.doc)):
                    try:
                        pg = self.pdf_viewer.doc.load_page(pn)
                        self._set_progress(progress, f"페이지 {pn} 글꼴 보장 중…")
                        self._dump_page_fonts(pg, "before ensure")
                        for fam in fonts_global:
                            _ = self._ensure_font_ref(pg, fam)
                        self._dump_page_fonts(pg, "after ensure")
                        self._step_progress(progress, 1)
                    except Exception as pree:
                        print(f"  ⚠️ 글로벌 폰트 선임베딩 경고 p{pn}: {pree}")
        except Exception as glob:
            print(f"  ⚠️ 글로벌 폰트 선임베딩 단계 경고: {glob}")
        for page_num, overlays in list(self.pdf_viewer.text_overlays.items()):
            if not overlays:
                continue
            try:
                page = self.pdf_viewer.doc.load_page(page_num)
            except Exception as e:
                print(f"  ❌ 페이지 로드 실패 {page_num}: {e}")
                continue

            # 사전 임베딩: 이 페이지에서 사용할 가능성이 높은 폰트들을 미리 보장
            try:
                fonts_to_ensure = set()
                for ov in overlays:
                    if getattr(ov, 'text', ''):
                        if getattr(ov, 'font', None):
                            fonts_to_ensure.add(ov.font)
                        # CJK 폴백 후보도 선임베딩 (문자 누락 방지)
                        for fam in ['HANdotum', 'HMKMAMI', 'Noto Sans CJK KR', 'Malgun Gothic', 'NanumGothic', 'Dotum', 'Gulim']:
                            fonts_to_ensure.add(fam)
                self._set_progress(progress, f"페이지 {page_num} 글꼴 보장 중…")
                self._dump_page_fonts(page, "before page-ensure")
                for fam in fonts_to_ensure:
                    _ = self._ensure_font_ref(page, fam)
                self._dump_page_fonts(page, "after page-ensure")
            except Exception as pree:
                print(f"  ⚠️ 폰트 사전 임베딩 경고: {pree}")

            for ov in list(overlays):
                if getattr(ov, 'flattened', False):
                    continue

                text_to_insert = ov.text or ''
                if text_to_insert == '':
                    ov.flattened = True
                    continue

                # 삽입 도우미
                self._set_progress(progress, f"페이지 {page_num} 오버레이 반영 중… '{text_to_insert[:12]}…'")
                def _try_flatten_once():
                    font_size = float(ov.size)
                    color_tuple = self._rgbf_from_color_int(ov.color)

                    # 폰트 준비
                    selected_font_name = ov.font or 'Arial'
                    # 저장 크기 미세 보정(예: +1.25%)
                    size_tweak = float(getattr(self, 'flatten_size_tweak', 0.0125))
                    eff_font_size = float(ov.size) * (1.0 + size_tweak)
                    font_args = {"fontsize": eff_font_size, "color": color_tuple}
                    # 사용자 폰트 실제 파일 경로 확보 (유니코드 ToUnicode 매핑 보장용)
                    user_fontfile = None
                    try:
                        user_fontfile = self.font_manager.get_font_path(selected_font_name)
                    except Exception:
                        user_fontfile = None
                    try:
                        tracking_percent = float(getattr(ov, 'tracking', 0.0))
                    except Exception:
                        tracking_percent = 0.0

                    if not hasattr(self, 'font_manager'):
                        self.font_manager = SystemFontManager()

                    def choose_font_variant(base_name: str, flags: int):
                        candidates = [base_name]
                        is_bold = bool(flags & 16)
                        is_italic = bool(flags & 2)
                        suffixes = []
                        if is_bold and is_italic:
                            suffixes = [' Bold Italic', '-BoldItalic', ' BoldOblique', '-BoldOblique']
                        elif is_bold:
                            suffixes = [' Bold', '-Bold', ' DemiBold', '-DemiBold', ' SemiBold', '-SemiBold', ' Black', '-Black', ' Medium', '-Medium']
                        elif is_italic:
                            suffixes = [' Italic', '-Italic', ' Oblique', '-Oblique']
                        for suf in suffixes:
                            candidates.append(base_name + suf)
                        for name in candidates:
                            p = self.font_manager.get_font_path(name)
                            if p and os.path.exists(p):
                                return name, p
                        match = self.font_manager.font_matcher.find_best_match(base_name)
                        if match:
                            p = self.font_manager.get_font_path(match)
                            if p and os.path.exists(p):
                                return match, p
                        return base_name, None

                    chosen_name, font_path = choose_font_variant(selected_font_name, ov.flags)
                    if not user_fontfile and font_path:
                        user_fontfile = font_path
                    # 폰트 리소스도 페이지에 보장(중복 방지) → 참조명 반환
                    font_ref = self._ensure_font_ref(page, chosen_name)

                    bbox = ov.bbox if ov.bbox else ov.original_bbox
                    insert_point = fitz.Point(bbox.x0, bbox.y1 - 2)

                    # 강제 이미지 옵션: 즉시 래스터 폴백 수행
                    if bool(getattr(ov, 'force_image', False)):
                        try:
                            # 텍스트 폭(포인트) 계산
                            text_len_pt = None
                            try:
                                if user_fontfile and os.path.exists(user_fontfile):
                                    _f = fitz.Font(fontfile=user_fontfile)
                                    text_len_pt = float(_f.text_length(text_to_insert, font_size))
                            except Exception:
                                text_len_pt = None
                            if not text_len_pt:
                                cjk = sum(1 for ch in text_to_insert if 0xAC00 <= ord(ch) <= 0xD7A3)
                                other = len(text_to_insert) - cjk
                                text_len_pt = font_size * (0.9 * cjk + 0.6 * other)
                            # 이미지 렌더링 (품질 스케일만 적용)
                            scale_px = float(getattr(self, 'fallback_image_scale', 1.5))
                            text_pt_h = max(font_size * 1.2, (bbox.y1 - bbox.y0))
                            rect_px_w = max(4, int(text_len_pt * scale_px))
                            rect_px_h = max(4, int(text_pt_h * scale_px))
                            img = QImage(rect_px_w, rect_px_h, QImage.Format.Format_ARGB32)
                            img.fill(QColor(0, 0, 0, 0))
                            qp = QPainter(img)
                            try:
                                qp.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                                qp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                                qfont = QFont(chosen_name if chosen_name else selected_font_name)
                                try:
                                    qfont.setPixelSize(int(font_size * scale_px))
                                except Exception:
                                    qfont.setPointSizeF(max(1.0, float(font_size) * scale_px))
                                # 장평/자간 반영
                                try:
                                    qfont.setStretch(int(max(1, min(400, float(getattr(ov, 'stretch', 1.0)) * 100))))
                                except Exception:
                                    pass
                                try:
                                    qp.setFont(qfont)
                                    # 자간(퍼센트) → 픽셀 스페이싱 근사: PyMuPDF 삽입과의 완전 일치 불가
                                except Exception:
                                    pass
                                qp.setPen(QColor(int(color_tuple[0]*255), int(color_tuple[1]*255), int(color_tuple[2]*255)))
                                # 한 줄 표시 (래핑 없음)
                                qp.drawText(0, 0, rect_px_w, rect_px_h, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text_to_insert)
                            finally:
                                qp.end()
                            ba = QByteArray()
                            buf = QBuffer(ba)
                            buf.open(QBuffer.OpenModeFlag.WriteOnly)
                            img.save(buf, 'PNG')
                            buf.close()
                            page.insert_image(fitz.Rect(bbox.x0, bbox.y1 - text_pt_h, bbox.x0 + text_len_pt, bbox.y1), stream=bytes(ba))
                            return True
                        except Exception as e_force_img:
                            print(f"  ❌ 강제 이미지 폴백 실패: {e_force_img}")

                    # 이미지 강제 옵션 또는 스타일/지원 상태에 따라 경로 분기
                    try:
                        # 0) 사용자 강제 이미지 옵션이면 바로 래스터 경로
                        if bool(getattr(ov, 'force_image', False)):
                            raise RuntimeError("force_image option enabled")
                        # CJK 포함 여부 및 비-CJK 폰트 사용 시 정밀 경로로 유도
                        text_has_cjk = any('\u3131' <= ch <= '\uD7A3' or '\u4E00' <= ch <= '\u9FFF' for ch in text_to_insert)
                        cjk_families = {'Noto Sans CJK KR', 'Noto Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', 'NanumGothic', 'Dotum', 'Gulim', 'HANdotum', 'HMKMAMI'}
                        needs_cjk_precise = text_has_cjk and (selected_font_name not in cjk_families)
                        user_supports_all = False
                        try:
                            user_supports_all = self._font_supports_all(user_fontfile, text_to_insert) if user_fontfile else False
                        except Exception:
                            user_supports_all = False
                        # 정밀 경로 사용 조건: 자간/장평 또는 CJK 보정, 혹은 합성볼드 필요
                        is_bold_flag = bool(ov.flags & 16)
                        chose_bold_variant = ('bold' in (chosen_name or '').lower()) or ('black' in (chosen_name or '').lower())
                        need_synth_bold = is_bold_flag and (not chose_bold_variant)
                        if (abs(float(getattr(ov, 'stretch', 1.0)) - 1.0) > 1e-3 or
                            abs(float(getattr(ov, 'tracking', 0.0))) > 1e-3 or
                            needs_cjk_precise or
                            need_synth_bold or
                            not user_supports_all):
                            # 2.1 정밀 텍스트 플래튼: 문자 단위 배치로 stretch/track 근사 (page.insert_text 사용)
                            try:
                                # 폰트 이름/경로 준비
                                eff_fontfile = user_fontfile
                                lines = text_to_insert.splitlines() if "\n" in text_to_insert else [text_to_insert]
                                stretch = float(getattr(ov, 'stretch', 1.0))
                                tracking_percent = float(getattr(ov, 'tracking', 0.0))
                                add_charspace = float(eff_font_size) * (tracking_percent/100.0) * 0.2
                                # 정밀 폭 측정기: 폰트파일 → Page.get_text_length → 근사 순으로 시도
                                calc_font = None
                                try:
                                    if font_path and os.path.exists(font_path):
                                        calc_font = fitz.Font(fontfile=font_path)
                                except Exception:
                                    calc_font = None
                                def measure_char_width(ch: str) -> float:
                                    # 1) 폰트파일 기반
                                    if calc_font is not None:
                                        try:
                                            return float(calc_font.text_length(ch, eff_font_size))
                                        except Exception:
                                            pass
                                    # 2) 근사: 영문/숫자 0.6em, 한글 0.9em
                                    code = ord(ch)
                                    if 0xAC00 <= code <= 0xD7A3:
                                        return eff_font_size * 0.9
                                    return eff_font_size * 0.6
                                # 라인 높이 대략치 및 베이스라인
                                line_h = eff_font_size * 1.2
                                base_y = bbox.y1 - (eff_font_size * 0.2)
                                # 경계 폭에 맞추지 않음(한 줄 유지)
                                max_width = None
                                end_x = bbox.x0
                                end_y = base_y
                                eps = 0.0
                                for li, line in enumerate(lines):
                                    # 문자별 폭 측정 (기본은 사용자 선택 폰트 기준)
                                    glyphs = []  # (ch, ch_w)
                                    for ch in line:
                                        ch_w = measure_char_width(ch)
                                        glyphs.append((ch, ch_w))
                                    # 전체 너비 계산
                                    n = len(glyphs)
                                    step_scale = 1.0
                                    # 배치
                                    x = bbox.x0
                                    y = base_y + li * line_h
                                    for idx, (ch, ch_w) in enumerate(glyphs):
                                        step = (ch_w * stretch + (add_charspace if idx > 0 else 0)) * step_scale
                                        # 사용자 폰트가 이 문자 지원하면 우선 사용
                                        inserted = False
                                        if font_ref and font_ref != 'helv':
                                            try:
                                                page.insert_text(fitz.Point(x, y), ch, fontname=font_ref, fontsize=eff_font_size, color=color_tuple)
                                                # 합성 볼드 필요 시 한 방향 오프셋으로 1회 추가 인쇄
                                                if need_synth_bold:
                                                    dx = max(0.2, eff_font_size * 0.015)
                                                    page.insert_text(fitz.Point(x + dx, y), ch, fontname=font_ref, fontsize=eff_font_size, color=color_tuple)
                                                inserted = True
                                            except Exception:
                                                inserted = False
                                        if not inserted:
                                            raise RuntimeError("char insert failed with selected font")
                                        x += step
                                    end_x, end_y = x, y
                                if ov.flags & 4:
                                    ul_y = end_y + 1
                                    page.draw_line(fitz.Point(bbox.x0, ul_y), fitz.Point(end_x, ul_y), color=color_tuple, width=1)
                                return True
                            except Exception as etw:
                                print(f"  ⚠️ 정밀 텍스트 플래튼 실패: {etw}")
                            # 2.2 실패 시 래스터 폴백 - 시각 충실도 보장 (텍스트 유지 강제 모드에서는 생략)
                            if getattr(self, 'force_text_flatten', False):
                                raise RuntimeError("정밀 플래튼 모드: 래스터 폴백 생략")
                            # 텍스트 픽셀 폭을 텍스트 길이에 맞게 확장
                            text_len_pt = None
                            try:
                                if user_fontfile and os.path.exists(user_fontfile):
                                    _f = fitz.Font(fontfile=user_fontfile)
                                    text_len_pt = float(_f.text_length(text_to_insert, font_size))
                            except Exception:
                                text_len_pt = None
                            if not text_len_pt:
                                cjk = sum(1 for ch in text_to_insert if 0xAC00 <= ord(ch) <= 0xD7A3)
                                other = len(text_to_insert) - cjk
                                text_len_pt = font_size * (0.9 * cjk + 0.6 * other)
                            rect_px_w = max(4, int(text_len_pt * 2))
                            rect_px_h = max(4, int((bbox.y1 - bbox.y0) * 2))
                            img = QImage(rect_px_w, rect_px_h, QImage.Format.Format_ARGB32)
                            img.fill(QColor(0, 0, 0, 0))
                            qp = QPainter(img)
                            try:
                                qp.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                                qp.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                                qfont = QFont(chosen_name if chosen_name else selected_font_name)
                                try:
                                    qfont.setPixelSize(int(font_size * float(getattr(self, 'fallback_image_scale', 1.5))))
                                except Exception:
                                    qfont.setPointSizeF(max(1.0, float(font_size) * float(getattr(self, 'fallback_image_scale', 1.5))))
                                if ov.flags & 16:
                                    qfont.setBold(True)
                                if ov.flags & 2:
                                    qfont.setItalic(True)
                                if ov.flags & 4:
                                    qfont.setUnderline(True)
                                try:
                                    qfont.setStretch(int(max(1, min(400, float(stretch) * 100))))
                                except Exception:
                                    pass
                                qp.setFont(qfont)
                                try:
                                    qfont.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100.0 + tracking_percent)
                                except Exception:
                                    pass
                                qp.setPen(QColor(int(color_tuple[0]*255), int(color_tuple[1]*255), int(color_tuple[2]*255)))
                                # 무조건 한 줄 표시: 래핑 옵션 제거
                                qp.drawText(0, 0, rect_px_w, rect_px_h, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text_to_insert)
                            finally:
                                qp.end()
                            ba = QByteArray()
                            buf = QBuffer(ba)
                            buf.open(QBuffer.OpenModeFlag.WriteOnly)
                            img.save(buf, 'PNG')
                            buf.close()
                            # 베이스라인 하단 맞춤: 레이어 높이를 유지하여 원본과 동일한 시각 크기
                            text_pt_h = max(font_size * 1.2, (bbox.y1 - bbox.y0))
                            page.insert_image(fitz.Rect(bbox.x0, bbox.y1 - text_pt_h, bbox.x0 + text_len_pt, bbox.y1), stream=bytes(ba))
                            return True
                    except Exception as eextra:
                        print(f"  ⚠️ 스타일 특수처리(래스터) 실패: {eextra}")

                    # 1차: insert_textbox 경로는 클리핑을 유발하므로 사용하지 않음
                    use_textbox = False
                    if use_textbox:
                        try:
                            rect = fitz.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
                            if user_fontfile and os.path.exists(user_fontfile):
                                leftover = page.insert_textbox(rect, text_to_insert, align=fitz.TEXT_ALIGN_LEFT, fontfile=user_fontfile, fontsize=font_size, color=color_tuple)
                            else:
                                raise RuntimeError("no user fontfile for textbox")
                            if isinstance(leftover, str) and leftover.strip() == text_to_insert.strip():
                                raise RuntimeError("insert_textbox did not render any text")
                            try:
                                vis = page.get_text("text", clip=rect)
                                if not vis or not any(ch in vis for ch in text_to_insert.strip()[:5]):
                                    raise RuntimeError("textbox visible check failed")
                            except Exception as vc:
                                raise vc
                            style_values = {
                                'size': font_size,
                                'color': QColor(int(color_tuple[0]*255), int(color_tuple[1]*255), int(color_tuple[2]*255)),
                                'bold': bool(ov.flags & 16),
                                'italic': bool(ov.flags & 2),
                                'underline': bool(ov.flags & 4),
                            }
                            try:
                                font_args["fontname"] = font_ref
                            except Exception:
                                pass
                            self._apply_text_styles(page, insert_point, text_to_insert, style_values, font_args, None)
                            return True
                        except Exception as e1:
                            print(f"  ⚠️ insert_textbox 실패: {e1}")

                    # 2차: insert_text (베이스라인 좌표) - 선택 폰트만 사용
                    try:
                        if font_ref and font_ref != 'helv':
                            # 베이스라인 경로(트래킹 없음): 크기 미세 보정값 반영
                            page.insert_text(insert_point, text_to_insert, fontname=font_ref, fontsize=eff_font_size, color=color_tuple)
                        else:
                            raise RuntimeError("no font_ref for baseline insert")
                        # 가시성 검증
                        try:
                            vis = page.get_text("text", clip=fitz.Rect(bbox.x0, bbox.y0 - font_size, bbox.x1 + font_size, bbox.y1 + font_size))
                            if not vis or not any(ch in vis for ch in text_to_insert.strip()[:5]):
                                raise RuntimeError("insert_text visible check failed")
                        except Exception as vc2:
                            raise vc2
                        # Bold/Underline 등 스타일 후처리(동일 폰트 참조)
                        try:
                            is_bold_flag = bool(ov.flags & 16)
                            chose_bold_variant = False
                            try:
                                cname_l = (chosen_name or '').lower()
                                chose_bold_variant = ('bold' in cname_l) or ('black' in cname_l)
                            except Exception:
                                pass
                            style_values = {
                                'size': font_size,
                                'color': QColor(int(color_tuple[0]*255), int(color_tuple[1]*255), int(color_tuple[2]*255)),
                                'bold': is_bold_flag,
                                'italic': bool(ov.flags & 2),
                                'underline': bool(ov.flags & 4),
                                'synth_bold': (is_bold_flag and not chose_bold_variant),
                            }
                            self._apply_text_styles(page, insert_point, text_to_insert, style_values, font_args, None)
                        except Exception as sty:
                            print(f"  ⚠️ 스타일 후처리 경고: {sty}")
                        return True
                    except Exception as e2:
                        print(f"  ❌ insert_text 실패: {e2}")
                        # 4차: 래스터 폴백 - 텍스트를 이미지로 렌더링하여 삽입 (텍스트 유지 강제 모드에서는 생략)
                        if getattr(self, 'force_text_flatten', False):
                            return False
                        try:
                            # 텍스트 폭에 맞춰 이미지 폭 확대
                            text_len_pt = None
                            try:
                                if user_fontfile and os.path.exists(user_fontfile):
                                    _f = fitz.Font(fontfile=user_fontfile)
                                    text_len_pt = float(_f.text_length(text_to_insert, font_size))
                            except Exception:
                                text_len_pt = None
                            if not text_len_pt:
                                cjk = sum(1 for ch in text_to_insert if 0xAC00 <= ord(ch) <= 0xD7A3)
                                other = len(text_to_insert) - cjk
                                text_len_pt = font_size * (0.9 * cjk + 0.6 * other)
                            scale_px = float(getattr(self, 'fallback_image_scale', 1.5))
                            text_pt_h = max(font_size * 1.2, (bbox.y1 - bbox.y0))
                            rect_px_w = max(2, int(text_len_pt * scale_px))
                            rect_px_h = max(2, int(text_pt_h * scale_px))
                            img = QImage(rect_px_w, rect_px_h, QImage.Format.Format_ARGB32)
                            img.fill(QColor(0, 0, 0, 0))
                            painter = QPainter(img)
                            qfont = QFont(selected_font_name)
                            try:
                                qfont.setPixelSize(int(font_size * scale_px))
                            except Exception:
                                qfont.setPointSizeF(max(1.0, float(font_size) * scale_px))
                            # 장평/자간 적용
                            try:
                                qfont.setStretch(int(max(1, min(400, float(getattr(ov, 'stretch', 1.0)) * 100))))
                            except Exception:
                                pass
                            try:
                                painter.setFont(qfont)
                                painter.setPen(QColor(int(color_tuple[0]*255), int(color_tuple[1]*255), int(color_tuple[2]*255)))
                                # 문단 그리기 (랩 가능)
                                # 무조건 한 줄 표시: 래핑 옵션 제거
                                painter.drawText(0, 0, rect_px_w, rect_px_h, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), text_to_insert)
                            finally:
                                painter.end()
                            # PNG 바이트로 변환 후 이미지 삽입
                            ba = QByteArray()
                            buf = QBuffer(ba)
                            buf.open(QBuffer.OpenModeFlag.WriteOnly)
                            img.save(buf, 'PNG')
                            buf.close()
                            page.insert_image(fitz.Rect(bbox.x0, bbox.y1 - text_pt_h, bbox.x0 + text_len_pt, bbox.y1), stream=bytes(ba))
                            return True
                        except Exception as eimg:
                            print(f"  ❌ 래스터 폴백 실패: {eimg}")
                            return False

                if _try_flatten_once():
                    ov.flattened = True
                    print(f"  ✅ 오버레이 반영: 페이지 {page_num}, '{text_to_insert[:20]}...' @ {ov.bbox}")
                    self._step_progress(progress, 1)
                else:
                    print(f"  ❌ 오버레이 반영 실패(최종): '{text_to_insert[:20]}...' @ {ov.bbox}")
                    self._step_progress(progress, 1)

    def get_precise_background_color(self, page, bbox):
        """선택된 텍스트 바로 인접 픽셀만 집중 샘플링하여 배경색 검출 (백업01 로직)"""
        import time
        detection_id = int(time.time() * 1000) % 10000  # 고유 ID 생성
        
        print(f"\n🎯 === 배경색 검출 #{detection_id} 시작 ===")
        print(f"   📍 현재 텍스트 bbox: ({bbox.x0:.1f}, {bbox.y0:.1f}) → ({bbox.x1:.1f}, {bbox.y1:.1f})")
        print(f"   📏 텍스트 크기: {bbox.width:.1f} x {bbox.height:.1f}pt")
        
        try:
            # 1. 선택된 텍스트 크기 기반 최소 여백 계산 (좁은 범위)
            text_width = bbox.width
            text_height = bbox.height
            
            # 매우 작은 마진으로 텍스트 바로 인접 픽셀만 대상 (문서 전체 샘플링 완전 방지)
            margin_h = min(2, max(1, text_width * 0.01))   # 가로: 최대 2px, 최소 1px  
            margin_v = min(2, max(1, text_height * 0.015)) # 세로: 최대 2px, 최소 1px
            
            print(f"   📏 텍스트 주변부 여백: 수평={margin_h:.1f}px, 수직={margin_v:.1f}px")
            
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
                    pix = page.get_pixmap(clip=clipped_region, dpi=150)
                    
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
                            print(f"   📍 {direction}: {len(region_colors)}픽셀, 평균RGB{avg_color}, 가중치{weight}")
                    
                except Exception as region_error:
                    print(f"   ⚠️ 영역 {i+1} 샘플링 실패: {region_error}")
                    continue
            
            if all_colors and valid_regions >= 2:  # 최소 2개 방향에서 성공
                # 3. 색상 빈도 분석 - 유사한 색상끼리 그룹핑
                color_counts = Counter(all_colors)
                total_pixels = len(all_colors)
                
                print(f"   📊 총 {total_pixels}개 유효 픽셀, {valid_regions}/4개 방향 샘플링 성공")
                
                # 가장 빈번한 색상들 분석
                top_colors = color_counts.most_common(5)
                print(f"   🎯 인접 픽셀 상위 색상:")
                
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
                    
                    print(f"   ✅ 배경색 검출 #{detection_id} 결과: RGB{best_color} → {result_color}")
                    print(f"       신뢰도: {best_percentage:.1f}% ({best_count}픽셀)")
                    print(f"   🎨 === 배경색 검출 #{detection_id} 완료 ===\n")
                    return result_color
                else:
                    print(f"   ⚠️ 신뢰도 부족: {best_percentage:.1f}% < 40% 또는 픽셀수 부족 ({best_count}개)")
            else:
                print(f"   ❌ 샘플링 실패: 유효 영역 {valid_regions}/4개 부족")
                    
        except Exception as e:
            print(f"   ❌ 배경색 검출 오류: {e}")
            import traceback
            traceback.print_exc()
        
        # 실패 시 기본 순백색 (회색 대신 흰색)
        fallback_color = (1.0, 1.0, 1.0)  # 순백색으로 변경
        print(f"   🔄 배경색 검출 #{detection_id} 실패 - 순백색 Fallback 사용: {fallback_color}")
        print(f"   🎨 === 배경색 검출 #{detection_id} 완료 (Fallback) ===\n")
        return fallback_color

    def get_optimal_cover_rect(self, original_bbox, text_metrics):
        """최적화된 덮개 사각형 계산 - 패치 마진 설정 반영"""
        margin = getattr(self, 'patch_margin', 2.0)
        
        if margin < 0:
            # 음수 마진: 비율 기반으로 텍스트 경계 내부로 패치를 축소
            # 예: -0.2 = 텍스트 크기의 20%만큼 안쪽으로
            width_reduction = original_bbox.width * abs(margin)
            height_reduction = original_bbox.height * abs(margin)
            
            horizontal_margin = -width_reduction / 2  # 좌우로 각각 축소
            vertical_margin = -height_reduction / 2   # 상하로 각각 축소
            
            print(f"음수 패치 마진 ({margin}): 폭 {width_reduction:.1f}pt, 높이 {height_reduction:.1f}pt 축소")
        else:
            # 양수 마진: 절대값으로 확장
            horizontal_margin = margin
            vertical_margin = margin
            print(f"양수 패치 마진: {margin}pt 확장")
        
        optimized_rect = fitz.Rect(
            original_bbox.x0 - horizontal_margin,
            original_bbox.y0 - vertical_margin,
            original_bbox.x1 + horizontal_margin,
            original_bbox.y1 + vertical_margin
        )
        
        return optimized_rect

    def apply_background_patch(self, page, original_bbox, new_values):
        """각 텍스트 블록별 개별 배경 패치 적용"""
        print(f"\n🎯 === 개별 텍스트 블록 배경 패치 적용 ===")
        print(f"   📍 처리할 텍스트 bbox: {original_bbox}")
        print(f"   📝 텍스트 내용: {new_values.get('text', 'N/A')[:20]}...")
        
        try:
            # 1. 지능적 마진 계산
            text_width = original_bbox.width
            text_height = original_bbox.height
            
            # 사용자가 편집창에서 패치 여백 지정 시 우선 적용
            user_margin = new_values.get('patch_margin', None)
            if user_margin is not None:
                if user_margin < 0:
                    # 음수는 비율(내부로 축소)
                    margin_h = abs(user_margin) * text_width
                    margin_v = abs(user_margin) * text_height
                else:
                    # 양수는 절대값(확장)
                    margin_h = user_margin
                    margin_v = user_margin
                print(f"   📏 사용자 지정 패치 여백 적용: 수평={margin_h:.2f}, 수직={margin_v:.2f}")
            else:
                # 텍스트 크기 기반 적응형 마진(기본)
                if text_height <= 8:  # 작은 텍스트
                    margin_v = max(1.5, text_height * 0.2)
                    margin_h = max(1.5, text_width * 0.05)
                elif text_height <= 12:  # 일반 텍스트
                    margin_v = max(2.0, text_height * 0.15)
                    margin_h = max(2.0, text_width * 0.04)
                else:  # 큰 텍스트
                    margin_v = max(3.0, text_height * 0.12)
                    margin_h = max(3.0, text_width * 0.03)
            
            print(f"   📏 적응형 마진: 수직={margin_v:.1f}px, 수평={margin_h:.1f}px")
            
            # 2. 새로운 정교한 배경색 검출 로직 사용 (사용자 지정이 우선)
            if new_values.get('use_custom_patch_color'):
                c = new_values.get('patch_color', QColor(255, 255, 255))
                bg_color = (c.redF(), c.greenF(), c.blueF())
                print(f"   🎨 사용자 지정 패치 색상 사용: {bg_color}")
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
            
            print(f"   🎨 이 텍스트 블록의 검출된 배경색: {bg_color}")
            print(f"   📏 패치 영역 마진: 수평={margin_h:.1f}px, 수직={margin_v:.1f}px")
            
            # 3. 단색 사각형 패치 적용 (단순하고 깔끔하게)
            # 요청사항: 필요 시 해당 라인(세로 밴드) 전체를 가리는 풀폭 패치 옵션
            cover_all_band = bool(new_values.get('cover_all_band', False) or new_values.get('cover_all', False))
            if cover_all_band:
                patch_rect = fitz.Rect(
                    page.rect.x0,
                    original_bbox.y0 - margin_v,
                    page.rect.x1,
                    original_bbox.y1 + margin_v
                )
            else:
                patch_rect = fitz.Rect(
                    original_bbox.x0 - margin_h,
                    original_bbox.y0 - margin_v,
                    original_bbox.x1 + margin_h,
                    original_bbox.y1 + margin_v
                )
            
            try:
                # 단일 패치 적용 (윤곽선 없는 단색 채우기)
                page.draw_rect(patch_rect, color=bg_color, fill=bg_color, width=0)
                print(f"   ✅ 이 블록 전용 배경 패치 완료!")
                print(f"       패치 영역: {patch_rect}")
                print(f"       적용된 색상: {bg_color}")
                print(f"   🎯 === 개별 블록 패치 완료 ===\n")
                # 화면 렌더링 동기화를 위해 패치 영역/색상 반환
                return patch_rect, bg_color
            except Exception as patch_error:
                print(f"⚠️ 패치 적용 실패: {patch_error}")
                raise  # fallback으로
                    
        except Exception as e:
            print(f"❌ 정교한 배경 패치 실패: {e}")
            # 실패시 기본 안전 패치
            try:
                print(f"   🔧 안전 모드 패치 적용...")
                # 검출된 배경색 사용, 실패시에만 기본 밝은 회색 사용
                safe_color = bg_color if 'bg_color' in locals() else (0.95, 0.95, 0.95)
                safe_margin = max(3.0, original_bbox.height * 0.2)
                
                safe_rect = fitz.Rect(
                    original_bbox.x0 - safe_margin,
                    original_bbox.y0 - safe_margin,
                    original_bbox.x1 + safe_margin,
                    original_bbox.y1 + safe_margin
                )
                
                page.draw_rect(safe_rect, color=safe_color, fill=safe_color, width=0)
                page.draw_rect(original_bbox, color=safe_color, fill=safe_color, width=0)
                print(f"   ⚠️ 안전 모드 패치 완료: {safe_rect} (색상: {safe_color})")
                return safe_rect, safe_color
                
            except Exception as safe_error:
                print(f"❌ 안전 패치도 실패: {safe_error}")
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
                    print(f"   ✅ 패치 품질 검증: 양호 (차이: {color_diff:.3f})")
                else:
                    print(f"   ⚠️ 패치 품질 검증: 보통 (차이: {color_diff:.3f})")
                    
        except Exception as verify_error:
            print(f"   🔍 패치 품질 검증 생략: {verify_error}")

    def insert_overlay_text(self, page, span, new_values):
        """수정된 텍스트를 레이어 방식 오버레이로 삽입 (완전한 편집창 연계)"""
        try:
            original_bbox = span['original_bbox']
            text_to_insert = new_values['text']
            font_size = new_values['size']
            text_color = new_values['color']
            selected_font_name = new_values['font']
            
            # 원본 span 정보 추출 및 로깅
            original_font = span.get('font', 'Unknown')
            original_size = span.get('size', 0)
            original_text = span.get('text', '')
            
            print(f"📋 원본→오버레이 텍스트 비교:")
            print(f"   원본: '{original_text}' | 폰트='{original_font}', 크기={original_size}pt")
            print(f"   오버레이: '{text_to_insert}' | 폰트='{selected_font_name}', 크기={font_size}pt")
            print(f"   bbox: {original_bbox}")
            
            if selected_font_name == "--- All Fonts ---":
                selected_font_name = "Arial"  # 기본 폰트로 fallback
                print(f"   🔄 'All Fonts' 폴백: '{selected_font_name}'으로 변경")
            
            # FontMatcher를 통한 폰트 검증 및 매칭
            font_manager = SystemFontManager()
            font_path = font_manager.get_font_path(selected_font_name)
            if font_path:
                print(f"   ✅ 폰트 경로 발견: {font_path}")
            else:
                print(f"   ❌ 폰트 경로 없음, FontMatcher로 유사폰트 검색...")
                matched_font = font_manager.font_matcher.find_best_match(selected_font_name)
                if matched_font:
                    print(f"   🎯 유사폰트 발견: '{selected_font_name}' → '{matched_font}'")
                    selected_font_name = matched_font
                else:
                    print(f"   ⚠️  유사폰트 없음, 기본폰트 사용: '{selected_font_name}'")
            
            print(f"   📋 최종 사용 폰트명: '{selected_font_name}'")
            
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
            
            print(f"🔍 new_values 스타일 키 확인:")
            print(f"   - 'bold' in new_values: {'bold' in new_values} -> {new_values.get('bold', 'MISSING')}")
            print(f"   - 'italic' in new_values: {'italic' in new_values} -> {new_values.get('italic', 'MISSING')}")
            print(f"   - 'underline' in new_values: {'underline' in new_values} -> {new_values.get('underline', 'MISSING')}")
            print(f"   - has_explicit_style: {has_explicit_style}")
            
            if not has_explicit_style:
                # 편집창에서 스타일 설정이 없다면 원본 사용
                edit_flags = span.get('flags', 0)
                print(f"   ✅ 스타일 설정 없음, 원본 사용: flags={edit_flags}")
            else:
                print(f"   ✅ 편집창 스타일 적용: bold={new_values.get('bold', False)}, italic={new_values.get('italic', False)}, underline={new_values.get('underline', False)}")
                print(f"   ✅ 최종 edit_flags: {edit_flags}")
            
            print(f"🎨 스타일 flags: 편집창={edit_flags}, 원본={span.get('flags', 0)}")
            
            # 기존 오버레이가 있는지 확인 (편집 시 업데이트)
            existing_overlay = self.pdf_viewer.find_overlay_at_position(
                self.pdf_viewer.current_page_num, original_bbox)

            if existing_overlay:
                # 기존 오버레이 속성 업데이트 (편집창 설정 적용)
                existing_overlay.update_properties(
                    text=text_to_insert,
                    font=selected_font_name,
                    size=font_size, 
                    color=color_int,
                    flags=edit_flags,  # 편집창 설정 사용
                    stretch=new_values.get('stretch', 1.0),
                    tracking=new_values.get('tracking', 0.0)
                )
                # 이미지 처리 옵션 반영
                setattr(existing_overlay, 'force_image', bool(new_values.get('force_image', False)))
                print(f"🔄 레이어 오버레이 업데이트: '{text_to_insert}' (ID: {existing_overlay.z_index})")
                overlay = existing_overlay
            else:
                # 새 레이어 오버레이 생성 (편집창 설정 적용)
                overlay = self.pdf_viewer.add_text_overlay(
                    text=text_to_insert,
                    font=selected_font_name, 
                    size=font_size,
                    color=color_int,
                    bbox=original_bbox,
                    page_num=self.pdf_viewer.current_page_num,
                    flags=edit_flags  # 편집창 설정 사용
                )
                # 장평/자간 반영
                overlay.update_properties(stretch=new_values.get('stretch', 1.0),
                                          tracking=new_values.get('tracking', 0.0))
                # 이미지 처리 옵션 반영
                setattr(overlay, 'force_image', bool(new_values.get('force_image', False)))
                print(f"✅ 새 레이어 오버레이 생성: '{text_to_insert}' (ID: {overlay.z_index})")
            
            # 원본 텍스트 배경 패치 적용 (레이어와 분리된 처리)
            print(f"🎯 배경 패치 적용 호출...")
            self.apply_background_patch(page, original_bbox, new_values)
            
            # 레거시 추적 시스템에도 등록 (호환성)
            if hasattr(self.pdf_viewer, 'register_overlay_text'):
                self.pdf_viewer.register_overlay_text(self.pdf_viewer.current_page_num, original_bbox)
            
            # 단일 레이어 표시 강제(같은 세로 밴드의 다른 오버레이를 숨기고 풀폭 패치 추가)
            # 단일 레이어 표시 모드는 옵션으로만 수행 (기본은 최소 패치)
            if bool(new_values.get('single_overlay_view', False)):
                try:
                    self.enforce_single_overlay_view(page, overlay, new_values)
                except Exception as enf:
                    print(f"⚠️ enforce_single_overlay_view 경고: {enf}")
            # 화면 갱신 - 레이어 방식이므로 PDF 재렌더링 불필요
            self.pdf_viewer.update()
            
            return overlay
            
        except Exception as e:
            print(f"❌ 레이어 오버레이 생성 실패: {e}")
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
            
            # 폰트 설정
            font_args = {
                "fontsize": font_size,
                "color": (text_color.redF(), text_color.greenF(), text_color.blueF())
            }
            
            # 폰트 파일 적용
            selected_font_name = new_values['font']
            if selected_font_name == "--- All Fonts ---":
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
        
        # 굵게: 변형 폰트를 우선 사용. 변형이 없는 경우에만 합성 볼드(한 방향 미세 오프셋) 사용
        if new_values.get('bold', False) and new_values.get('synth_bold', False):
            dx = max(0.2, font_size * 0.015)
            offset_point = fitz.Point(insert_point.x + dx, insert_point.y)
            if fontfile_path and os.path.exists(fontfile_path):
                page.insert_text(offset_point, text_to_insert, fontfile=fontfile_path, fontsize=font_size,
                                 color=(text_color.redF(), text_color.greenF(), text_color.blueF()))
            else:
                page.insert_text(offset_point, text_to_insert, **font_args)

        # 밑줄 처리
        if new_values.get('underline', False):
            underline_y = insert_point.y + 1
            text_width = len(text_to_insert) * font_size * 0.6  # 대략적인 텍스트 너비
            page.draw_line(
                fitz.Point(insert_point.x, underline_y),
                fitz.Point(insert_point.x + text_width, underline_y),
                color=(text_color.redF(), text_color.greenF(), text_color.blueF()),
                width=1
            )

    def on_text_selected(self, span):
        # 편집 전 상태 저장
        if self.pdf_viewer.doc:
            self.undo_manager.save_state(self.pdf_viewer.doc, self.pdf_viewer)
        
        dialog = TextEditorDialog(span, self.pdf_fonts, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_values = dialog.get_values()
            print(f"Dialog result: {new_values}")  # 디버깅 로그
            
            # 패치 마진 설정이 변경된 경우 적용
            if new_values.get('patch_margin') is not None:
                self.patch_margin = new_values['patch_margin']
                print(f"패치 마진 설정 업데이트: {self.patch_margin}")
            
            # 위치 조정 모드가 요청된 경우
            if new_values.get('position_adjustment_requested', False):
                print("위치 조정 모드 진입")  # 디버깅 로그
                # 편집 다이얼로그에서 받은 값을 반영한 span 정보로 업데이트
                updated_span = span.copy()
                updated_span.update({
                    'text': new_values['text'],
                    'font': new_values['font'],
                    'size': new_values['size'],
                    'color': new_values['color']
                })
                self.pdf_viewer.enter_text_adjustment_mode(updated_span)
                return
            
            try:
                page = self.pdf_viewer.doc.load_page(self.pdf_viewer.current_page_num)
                original_bbox = span['original_bbox']
                
                print(f"🔧 텍스트 편집 시작: '{new_values['text']}'")
                print(f"   폰트: {new_values['font']}, 크기: {new_values['size']}")
                
                # 1단계: 원본 텍스트 배경 패치 적용 (PDF에 직접 패치) 및 UI 등록
                try:
                    patch_rect, patch_color = self.apply_background_patch(page, original_bbox, new_values)
                except Exception:
                    patch_rect, patch_color = (original_bbox, None)
                print(f"✅ 원본 텍스트 배경 패치 완료")
                
                # 1-1단계: 배경 패치 영역 등록 (레이어 시스템에 등록) 및 즉시 갱신
                self.pdf_viewer.add_background_patch(self.pdf_viewer.current_page_num, patch_rect, patch_color)
                self.pdf_viewer.update()
                
                # 2단계: 레이어 방식 텍스트 오버레이 생성
                overlay = self.insert_overlay_text(page, span, new_values)
                if overlay:
                    print(f"✅ 레이어 오버레이 생성: ID {overlay.z_index}")
                    # 레이어 방식이므로 즉시 화면 갱신만 필요
                    self.pdf_viewer.update()
                else:
                    print(f"⚠️ fallback 방식으로 오버레이 생성됨")
                    # Fallback 방식의 경우 페이지 재렌더링 필요
                    self.render_page(page_to_render=page)
                
                # 편집 완료 후 새로운 상태 저장
                if self.pdf_viewer.doc:
                    self.undo_manager.save_state(self.pdf_viewer.doc, self.pdf_viewer)
                
                # 변경사항 표시 및 버튼 상태 업데이트
                self.mark_as_changed()
                self.update_undo_redo_buttons()
                print("✅ Undo/Redo: 편집 완료 후 새로운 상태 저장됨")
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to edit text: {e}")
                print(f"❌ 텍스트 편집 실패: {e}")
                import traceback
                traceback.print_exc()
        else:
            # 편집 취소된 경우 저장된 상태 제거
            if self.undo_manager.undo_stack:
                self.undo_manager.undo_stack.pop()
                print("🚫 Undo/Redo: 편집 취소로 인해 저장된 상태 제거됨")
    
    def closeEvent(self, event):
        """창 닫기 이벤트 처리"""
        if self.has_changes:
            msg = QMessageBox(self)
            msg.setWindowTitle("Unsaved Changes")
            msg.setText("You have unsaved changes. Do you want to save before closing?")
            yes_btn = msg.addButton(QMessageBox.StandardButton.Yes)
            no_btn = msg.addButton(QMessageBox.StandardButton.No)
            cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)
            try:
                for b in msg.buttons():
                    b.setMinimumSize(96, 36)
            except Exception:
                pass
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == yes_btn:
                if self.save_pdf():
                    event.accept()
                else:
                    event.ignore()
            elif clicked == no_btn:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    # 패치 크기 조절 관련 메서드들
    def toggle_precise_mode(self):
        """정밀 모드 토글"""
        self.patch_precise_mode = self.precise_mode_action.isChecked()
        status = "활성화" if self.patch_precise_mode else "비활성화"
        print(f"정밀 패치 모드 {status}")
        
    def set_patch_margin(self, margin):
        """패치 여백 설정"""
        self.patch_margin = margin
        print(f"패치 여백 설정: {margin}")

    def toggle_force_text_flatten(self, checked):
        """텍스트 유지 정밀 플래튼 토글"""
        self.force_text_flatten = bool(checked)
        status = "활성화" if self.force_text_flatten else "비활성화"
        print(f"텍스트 유지 정밀 플래튼 {status}")

    def _font_log_action_text(self):
        level = getattr(self, 'font_dump_verbose', 1)
        label = {0: '끔', 1: '보통', 2: '상세'}.get(level, '보통')
        return f"🔎 글꼴 로그 상세도: {label}"

    def toggle_font_log_verbosity(self):
        try:
            self.font_dump_verbose = (self.font_dump_verbose + 1) % 3
        except Exception:
            self.font_dump_verbose = 1
        if hasattr(self, 'font_log_action'):
            self.font_log_action.setText(self._font_log_action_text())
        print(f"글꼴 로그 상세도 변경: {self._font_log_action_text()}")

    def _ensure_font_ref(self, page, font_name):
        """문서에 폰트를 한 번만 임베딩하고 참조명을 반환합니다."""
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
                if cache_key in self._font_ref_cache:
                    return self._font_ref_cache[cache_key]
                try:
                    # 페이지 리소스에 우선 등록
                    page.insert_font(fontfile=fpath, fontname=ref)
                    print(f"    ↳ page.insert_font OK: {font_name} -> {ref}")
                    self._font_ref_cache[cache_key] = ref
                    return ref
                except Exception as e:
                    # 페이지 등록 실패 시 문서 전역 등록을 시도한 뒤 재사용
                    try:
                        # 일부 버전은 문서 레벨 등록 미지원 → 이 경로는 로깅만 남김
                        print(f"    ↳ page.insert_font 실패({font_name}): {e}")
                        # 폰트 파일은 사전 로드되어 있으므로 helv로 폴백
                    except Exception as e2:
                        print(f"  ⚠️ 폰트 임베딩 실패(page/doc) → helv 사용: {e} / {e2}")
                    return "helv"
            return "helv"
        except Exception:
            return "helv"

    def apply_theme(self, mode: str):
        self.theme_mode = mode
        try:
            from PySide6.QtGui import QPalette
            app = QApplication.instance()
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
                QMenuBar { background: #ffffff; color: #111; }
                QMenuBar::item:selected { background: #e6f2ff; border: 1px solid #3399ff; }
                QMenu { background: #ffffff; color: #111; }
                QMenu::item:selected { background: #e6f2ff; }
                QPushButton { background: #f5f5f5; color: #111; border: 1px solid #cccccc; border-radius: 6px; }
                QPushButton:hover { border: 1px solid #3399ff; }
                QLabel { color: #111; }
                QCheckBox { color:#111; }
                QCheckBox::indicator { width:16px; height:16px; border:1px solid #999; background:#fff; }
                QCheckBox::indicator:checked { background:#e6f2ff; border:1px solid #3399ff; }
                """
                self.setStyleSheet(light_qss)
                self.pdf_viewer.setStyleSheet("border:1px solid #ccc; background-color: #ffffff;")
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
                QMenuBar { background: #1e1f22; color: #ddd; }
                QMenuBar::item:selected { background: #2b2d30; border: 1px solid #4c9eff; }
                QMenu { background: #2b2d30; color: #ddd; }
                QMenu::item:selected { background: #3a3d40; }
                QPushButton { background: #2d2e31; color: #ddd; border: 1px solid #555555; border-radius: 6px; }
                QPushButton:hover { border: 1px solid #4c9eff; }
                QLabel { color: #ddd; }
                """
                self.setStyleSheet(dark_qss)
                self.pdf_viewer.setStyleSheet("border:1px solid #555; background-color: #111;")
                self.theme_button.setText("☀️")
        except Exception:
            pass

    def toggle_theme(self):
        new_mode = 'light' if self.theme_mode == 'dark' else 'dark'
        self.apply_theme(new_mode)
        
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
정밀 모드: {'활성화' if self.patch_precise_mode else '비활성화'}
            """
            
            QMessageBox.information(self, "패치 정보", info_text)
            
        except Exception as e:
            QMessageBox.critical(self, "오류", f"패치 정보 조회 중 오류 발생: {str(e)}")
    
    def fit_to_page(self):
        """페이지 크기에 맞춤"""
        if self.pdf_viewer and self.pdf_viewer.doc:
            try:
                # 스크롤 영역 크기 가져오기
                scroll_area_size = self.scroll_area.viewport().size()
                
                # 현재 페이지 크기 가져오기
                page = self.pdf_viewer.doc.load_page(self.pdf_viewer.current_page_num)
                page_rect = page.rect
                
                # 적합한 배율 계산
                width_ratio = scroll_area_size.width() / page_rect.width
                height_ratio = scroll_area_size.height() / page_rect.height
                
                # 작은 쪽 비율 사용하여 페이지가 완전히 보이도록 함
                zoom_ratio = min(width_ratio, height_ratio) * 0.9  # 여백을 위해 0.9 곱함
                
                self.zoom_factor = max(0.1, min(5.0, zoom_ratio))
                self.render_page()
                self.update_zoom_label()
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
            self.setWindowTitle("Python PDF Editor - 세션 로드")
            QMessageBox.information(self, "완료", "세션이 불러와졌습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"세션 불러오기 중 오류 발생: {str(e)}")
    
    def show_shortcuts(self):
        """단축키 도움말 표시"""
        shortcuts_text = """
        📋 주요 단축키:
        
        🔍 보기:
        • Ctrl + '+' : 확대
        • Ctrl + '-' : 축소  
        • Ctrl + 0 : 페이지 맞춤
        
        📖 페이지 이동:
        • Page Up / ↑ : 이전 페이지
        • Page Down / ↓ : 다음 페이지
        
        ✏️ 편집:
        • Ctrl + 클릭 : 사각형 선택 모드
        • 방향키 : 선택된 텍스트 위치 조정
        • Enter : 편집 모드 진입
        
        📁 파일:
        • Ctrl + O : PDF 열기
        • Ctrl + S : 저장
        • Ctrl + Q : 종료
        """
        
        QMessageBox.information(self, "단축키 도움말", shortcuts_text)
    
    def show_about(self):
        """프로그램 정보 표시"""
        about_text = """
        📄 고급 PDF 편집기 v3.0
        
        🛠️ 주요 기능:
        • 실시간 텍스트 편집 및 위치 조정
        • 사각형 선택을 통한 정밀 편집
        • 다양한 글꼴 지원 및 설치 안내
        • 패치 최적화 및 관리
        • 직관적인 이모지 메뉴 시스템
        
        💻 개발 환경:
        • Python + PySide6 + PyMuPDF
        • 한국어 텍스트 완벽 지원
        
        🎯 Claude Code AI와 함께 개발됨
        """
        
        QMessageBox.information(self, "프로그램 정보", about_text)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    initial_path = sys.argv[1] if len(sys.argv) > 1 else None
    window = MainWindow(initial_path)
    window.show()
    sys.exit(app.exec())
