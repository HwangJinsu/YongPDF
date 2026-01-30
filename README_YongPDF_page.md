# 📄 YongPDF_page (용PDF 페이지 에디터)

**YongPDF_page**는 PDF 문서의 페이지를 쉽고 직관적으로 관리할 수 있는 전문 도구입니다. 
페이지 순서 변경, 회전, 추가, 삭제, 추출, 압축 등 문서 구조 편집에 최적화되어 있으며, 썸네일과 드래그앤드롭 및 우클릭과 같이 편리하고 직관적인 UI/UX를 제공합니다.

---

## ✨ 핵심 기능

### 1. "딸깍" 직관적인 페이지 관리
*   **썸네일 뷰**: 문서 전체 구조를 한눈에 파악할 수 있는 썸네일 미리보기를 제공하며, 자유로운 크기 조절(창 크기, 페이지 크기)이 가능합니다.
*   **드래그 앤 드롭 순서 변경**: 썸네일 뷰에서 페이지를 마우스로 끌어다 놓는 것만으로 손쉽게 순서를 바꿀 수 있습니다. (페이지 추가도 가능)
*   **다중 선택 지원**: 썸네일 뷰에서 여러 페이지를 한 번에 선택하여 "우클릭"으로 삭제, 이동, 회전할 수 있습니다.

### 2. 필수 편집 도구
*   **페이지 삭제**: 불필요한 페이지를 제거할 수 있습니다.
*   **페이지 회전**: 페이지 방향을 왼쪽/오른쪽으로 90도씩 회전시킬 수 있습니다.
*   **페이지 추가**: 외부 PDF 파일을 드래그하여 현재 문서의 원하는 위치에 바로 삽입할 수 있습니다.
*   **페이지 저장**: 원하는 페이지만 골라서 별도의 PDF 파일로 저장(추출)하는 기능을 제공합니다.

### 3. 고급 기능
*   **PDF 압축**: Ghostscript를 활용한 강력한 PDF 압축 기능을 제공하여 파일 용량을 최적화할 수 있습니다. (일반/고급 모드 지원)
*   **YongPDF_text 연동**: 현재 페이지 내용을 수정하고 싶을 때 **YongPDF_text**를 바로 실행하여 텍스트를 수정할 수 있습니다.
*   **인쇄 지원**: 편집된 문서를 바로 프린터로 출력할 수 있습니다.

### 4. 사용자 편의성
*   **다크 모드 지원**: 눈이 편안한 다크 테마와 깔끔한 라이트 테마를 제공합니다.
*   **다국어 지원**: 한국어, 영어, 일본어, 중국어(간체/번체) 등 다양한 언어 환경을 지원합니다.
*   **단축키 지원**: 키보드 단축키를 통해 빠른 작업이 가능합니다.

---

## 🚀 설치 및 실행

*   **단일 패키지**: 별도의 설치 과정 없이 `YongPDF_page.exe` (또는 해당 OS 실행 파일)를 실행하면 즉시 사용할 수 있습니다.
*   **무설치 실행**: 필요한 모든 라이브러리가 포함된 단일 실행 파일 형태로 배포됩니다.

---

## ⌨️ 주요 단축키

| 기능 | 단축키 |
| :--- | :--- |
| **PDF 열기** | `Ctrl + O` |
| **PDF 저장** | `Ctrl + S` |
| **페이지 추가** | `Insert` |
| **페이지 삭제** | `Delete` |
| **위로 이동** | `Ctrl + Shift + ↑` |
| **아래로 이동** | `Ctrl + Shift + ↓` |
| **왼쪽 회전** | `Ctrl + Shift + ←` |
| **오른쪽 회전** | `Ctrl + Shift + →` |
| **실행 취소 / 다시 실행** | `Ctrl + Z` / `Ctrl + Y` |
| **확대 / 축소** | `Ctrl + +` / `Ctrl + -` |

---

## 🌐 다국어 지원
현재 다음 언어를 지원합니다:
*   한국어 (Default)
*   English
*   日本語
*   简体中文 / 繁體中文

---

## ❣️ 개발자 후원
프로그램이 도움이 되셨다면 상단 메뉴의 **[❣️개발자 후원하기❣️]**를 통해 따뜻한 마음을 전해주세요. 
후원금은 더 나은 기능 개발과 유지보수를 위해 소중히 사용됩니다.

---

## ⚖️ 오픈소스 라이선스
본 앱은 다음 오픈소스 프로젝트를 사용합니다:

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