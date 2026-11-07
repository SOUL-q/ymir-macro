@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title ymir - build

echo ============================================
echo   Building ymir (main.py -> ymir.exe)
echo ============================================
echo.

rem ---- find Python ----
set PY=py
%PY% --version >nul 2>&1
if errorlevel 1 (
    set PY=python
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python was not found. Install it from python.org and tick "Add to PATH".
        pause
        exit /b 1
    )
)

rem ---- install what the script and the compiler need ----
echo [1/3] Installing requirements...
%PY% -m pip install --upgrade pip
%PY% -m pip install pyinstaller mss opencv-python numpy pydirectinput keyboard
if errorlevel 1 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

rem ---- bundle every image that exists next to main.py ----
echo.
echo [2/3] Collecting images...
set DATA=
for %%F in (ymir_logo_app.png ymir.ico retry_text.png mission_start.png result_completed.png result_failed.png loot_scroll.png loot_body.png loot_defence.png loot_offence.png loot_support.png grabbed_text.png) do (
    if exist "%%F" (
        set DATA=!DATA! --add-data "%%F;."
        echo   + %%F
    ) else (
        echo   - %%F  ^(missing, skipped^)
    )
)

set ICON=
if exist "ymir.ico" set ICON=--icon "ymir.ico"

rem ---- compile ----
echo.
echo [3/3] Compiling...
%PY% -m PyInstaller --noconfirm --clean --onefile --noconsole --uac-admin --name ymir !ICON! !DATA! main.py
if errorlevel 1 (
    echo.
    echo [ERROR] The build failed. Read the messages above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Done!  Your exe is here:  dist\ymir.exe
echo ============================================
echo Tip: images placed next to ymir.exe override the bundled copies.
echo      aotr_stats.json is saved next to the exe.
echo.
pause
