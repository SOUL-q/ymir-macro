@echo off
setlocal
cd /d "%~dp0"

echo ==== ymir build ====

if not exist "main.py" (
    echo main.py not found next to build.bat
    pause
    exit /b 1
)
if not exist "image\" (
    echo The "image" folder was not found next to build.bat
    pause
    exit /b 1
)

echo Installing / updating requirements...
python -m pip install --upgrade pip
python -m pip install pyinstaller mss opencv-python numpy pydirectinput keyboard
if errorlevel 1 (
    echo Could not install the requirements.
    pause
    exit /b 1
)

echo Building...
python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin ^
    --name ymir ^
    --icon "image\ymir.ico" ^
    --add-data "image;image" ^
    main.py
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Done! Your exe is in the "dist" folder: dist\ymir.exe
echo (The "image" folder is bundled inside it. Stats are saved in Documents\Ymir Macro.)
pause
