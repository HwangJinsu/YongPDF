#!/usr/bin/env bash
# ==============================================================================
# YongPDF macOS Packaging Script
# Builds .app bundles and .dmg installers for YongPDF Page and YongPDF Text.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# 1. PyInstaller 경로 탐색
PYINSTALLER=""
if [[ -x "/Library/Frameworks/Python.framework/Versions/3.12/bin/pyinstaller" ]]; then
    PYINSTALLER="/Library/Frameworks/Python.framework/Versions/3.12/bin/pyinstaller"
elif command -v pyinstaller >/dev/null 2>&1; then
    PYINSTALLER="$(command -v pyinstaller)"
fi

if [[ -z "${PYINSTALLER}" ]]; then
    echo "❌ 오류: PyInstaller를 찾을 수 없습니다."
    echo "   pip install pyinstaller 명령어로 설치하거나 가상환경을 활성화하세요."
    exit 1
fi

echo "📦 PyInstaller 경로: ${PYINSTALLER}"

# 2. 도움말 및 사용법
usage() {
    echo "사용법: $0 [page | text | all | dmg | page_dmg | text_dmg | clean]"
    echo ""
    echo "옵션:"
    echo "  page     : YongPDF Page (페이지 편집기, pdf_editor_v2_mac.spec) 빌드"
    echo "  text     : YongPDF Text (텍스트 편집기, main_codex1_mac.spec) 빌드"
    echo "  page_dmg : YongPDF Page 빌드 및 .dmg 생성"
    echo "  text_dmg : YongPDF Text 빌드 및 .dmg 생성"
    echo "  all      : 두 애플리케이션 모두 빌드 (기본값)"
    echo "  dmg      : 두 애플리케이션 빌드 후 .dmg 설치 디스크 이미지 생성"
    echo "  clean    : build 및 dist 폴더 정리"
    exit 0
}

TARGET="${1:-all}"

clean_build() {
    echo "🧹 이전 빌드 임시 파일 정리 중..."
    rm -rf build/
    echo "✅ 정리 완료"
}

sign_app() {
    local app_path="$1"
    if [[ -d "${app_path}" ]]; then
        echo "🔏 Ad-hoc 코드 서명 적용: ${app_path}"
        codesign --force --deep --sign - "${app_path}" || true
    fi
}

create_dmg() {
    local app_name="$1"
    local vol_name="$2"
    local dmg_name="$3"
    local app_path="dist/${app_name}.app"
    local dmg_path="dist/${dmg_name}.dmg"
    local staging="dist/dmg_staging_${app_name}"

    if [[ ! -d "${app_path}" ]]; then
        echo "❌ 오류: ${app_path} 가 존재하지 않아 DMG를 생성할 수 없습니다."
        return 1
    fi

    echo "💿 DMG 생성 중: ${dmg_path} ..."
    rm -rf "${staging}" "${dmg_path}"
    mkdir -p "${staging}"
    cp -R "${app_path}" "${staging}/"
    ln -s /Applications "${staging}/Applications"

    hdiutil create -volname "${vol_name}" \
                   -srcfolder "${staging}" \
                   -ov \
                   -format UDZO \
                   "${dmg_path}"

    rm -rf "${staging}"
    echo "✅ DMG 생성 완료: ${dmg_path} ($(du -sh "${dmg_path}" | cut -f1))"
}

build_page() {
    echo "=========================================================="
    echo "🚀 1. YongPDF Page (.app) 빌드 시작"
    echo "=========================================================="
    "${PYINSTALLER}" pdf_editor_v2_mac.spec --noconfirm
    sign_app "dist/YongPDF_page.app"
    echo "✅ YongPDF Page 빌드 완료: dist/YongPDF_page.app"
}

build_text() {
    echo "=========================================================="
    echo "🚀 2. YongPDF Text (.app) 빌드 시작"
    echo "=========================================================="
    "${PYINSTALLER}" main_codex1_mac.spec --noconfirm
    sign_app "dist/YongPDF_text.app"
    echo "✅ YongPDF Text 빌드 완료: dist/YongPDF_text.app"
}

case "${TARGET}" in
    clean)
        clean_build
        ;;
    page)
        build_page
        ;;
    text)
        build_text
        ;;
    all)
        build_page
        build_text
        echo ""
        echo "🎉 모든 앱 번들 빌드가 완료되었습니다!"
        echo "   - dist/YongPDF_page.app"
        echo "   - dist/YongPDF_text.app"
        ;;
    page_dmg|dmg_page)
        build_page
        echo ""
        echo "💿 YongPDF Page DMG 패키징 시작..."
        create_dmg "YongPDF_page" "YongPDF Page" "YongPDF_Page"
        ;;
    text_dmg|dmg_text)
        build_text
        echo ""
        echo "💿 YongPDF Text DMG 패키징 시작..."
        create_dmg "YongPDF_text" "YongPDF Text" "YongPDF_Text"
        ;;
    dmg)
        build_page
        build_text
        echo ""
        echo "💿 DMG 패키징 시작..."
        create_dmg "YongPDF_page" "YongPDF Page" "YongPDF_Page"
        create_dmg "YongPDF_text" "YongPDF Text" "YongPDF_Text"
        echo ""
        echo "🎉 모든 DMG 패키징이 완료되었습니다!"
        echo "   - dist/YongPDF_Page.dmg"
        echo "   - dist/YongPDF_Text.dmg"
        ;;
    *)
        usage
        ;;
esac
