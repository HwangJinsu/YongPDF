import sys
import os

# PyInstaller 번들 환경이면 현재 작업 디렉터리를 _MEIPASS로 변경합니다.
if hasattr(sys, '_MEIPASS'):
    os.chdir(sys._MEIPASS) 