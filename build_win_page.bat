@echo off
setlocal enabledelayedexpansion

echo =======================================================================
echo   YongPDF_page Windows Build Script (onedir + Inno Setup)
echo =======================================================================
echo.

REM 1. Check Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found in PATH.
    pause
    exit /b 1
)

REM 2. Check PyInstaller
pyinstaller --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] PyInstaller not found. Please install: pip install pyinstaller
    pause
    exit /b 1
)

echo [1/2] Building with PyInstaller (onedir mode)...
pyinstaller --clean --noconfirm pdf_editor_v2_win.spec
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] PyInstaller build failed!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [1/2] PyInstaller build completed: dist\YongPDF_page\
echo.

REM 3. Search for Inno Setup compiler (ISCC.exe)
echo [2/2] Checking Inno Setup 6...
set "ISCC="

if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramW6432%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramW6432%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    where ISCC >nul 2>&1
    if !ERRORLEVEL! EQU 0 set "ISCC=ISCC"
)

if not defined ISCC goto :no_inno

echo Running Inno Setup Compiler: "!ISCC!"
"!ISCC!" YongPDF_page_win.iss
if !ERRORLEVEL! EQU 0 (
    echo.
    echo =======================================================================
    echo   [SUCCESS] Setup installer created successfully!
    echo   Installer: dist\YongPDF_page_Setup_v1.1.exe
    echo =======================================================================
) else (
    echo.
    echo [ERROR] Inno Setup compilation failed!
)
goto :build_done

:no_inno
echo.
echo [NOTICE] Inno Setup 6 compiler ISCC.exe was not found on your system.
echo  - Onedir build files are available in: dist\YongPDF_page\
echo  - To build Setup.exe installer, download and install Inno Setup 6:
echo    https://jrsoftware.org/isdl.php
echo    Then open YongPDF_page_win.iss and click [Compile].

:build_done
echo.
pause
