@echo off
REM ============================================================
REM  Builds FolderMaker.exe from FolderMaker.py
REM  Put this file in the SAME folder as FolderMaker.py,
REM  then double-click it.
REM
REM  Releasing: the exe's version comes from APP_VERSION in
REM  FolderMaker.py. To publish an update, bump APP_VERSION,
REM  rebuild, then create a GitHub release tagged v<major.minor>
REM  (e.g. v1.2) and attach dist\FolderMaker.exe as an asset
REM  named exactly "FolderMaker.exe". The running app will then
REM  offer the update automatically.
REM ============================================================

cd /d "%~dp0"

echo.
echo === Checking for Python ===
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo Python was not found on this PC.
    echo Install it from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during setup.
    echo.
    pause
    exit /b 1
)
python --version

echo.
echo === Installing PyInstaller (skipped if already present) ===
python -m pip install --upgrade pyinstaller
if errorlevel 1 (
    echo.
    echo pip failed. Check your internet connection.
    pause
    exit /b 1
)

echo.
echo === Building ===
python -m PyInstaller --onefile --windowed --name FolderMaker --clean --icon FolderMaker.ico --add-data "FolderMaker.ico;." FolderMaker.py
if errorlevel 1 (
    echo.
    echo Build failed. Scroll up to see the error.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Done. Your program is at:
echo     %cd%\dist\FolderMaker.exe
echo.
echo  You can move that .exe anywhere. The "build" folder and
echo  FolderMaker.spec are leftovers and can be deleted.
echo ============================================================
echo.
pause
