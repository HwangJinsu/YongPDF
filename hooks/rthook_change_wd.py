# hooks/rthook_change_wd.py
import sys
import os

def resource_path(relative_path):
    """
    PyInstaller onefile 또는 onedir 모드에 따른 리소스 파일의 절대 경로를 반환합니다.
    """
    try:
        # PyInstaller가 생성한 임시 폴더 경로를 우선 사용
        base_path = sys._MEIPASS
    except AttributeError:
        # 개발 환경이나 일반 실행의 경우
        base_path = os.path.dirname(sys.executable)
    
    return os.path.join(base_path, relative_path)

# 현재 실행 모드 확인 및 로깅
is_bundled = getattr(sys, 'frozen', False)
current_path = os.getcwd()
meipass_path = getattr(sys, '_MEIPASS', 'Not bundled')

print(f"현재 실행 모드: {'Bundled' if is_bundled else 'Regular'}")
print(f"현재 작업 디렉토리: {current_path}")
print(f"MEIPASS 경로: {meipass_path}")

try:
    # 실행 파일 디렉토리로 변경
    exe_dir = os.path.dirname(sys.executable)
    os.chdir(exe_dir)
    print(f"작업 디렉토리를 변경했습니다: {exe_dir}")
except Exception as e:
    print(f"작업 디렉토리 변경 중 오류 발생: {e}")