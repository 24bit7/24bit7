@echo off
setlocal
cd /d "%~dp0"

rem Close the packaged 24bit7 before building, or its files can't be replaced.

rem --- 1. Back up settings and history (a rebuild deletes dist\24bit7) ---
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set STAMP=%%i
set BK=backups\%STAMP%
mkdir "%BK%\script" 2>nul
mkdir "%BK%\app" 2>nul
if exist ".env" copy /y ".env" "%BK%\script\" >nul
if exist "24bit7.db" copy /y "24bit7.db" "%BK%\script\" >nul
if exist "dist\24bit7\.env" copy /y "dist\24bit7\.env" "%BK%\app\" >nul
if exist "dist\24bit7\24bit7.db" copy /y "dist\24bit7\24bit7.db" "%BK%\app\" >nul
echo Backed up settings and history to %BK%

rem --- 2. Build ---
python -m pip install --upgrade pyinstaller
python -m PyInstaller --noconfirm --clean --windowed --name 24bit7 --icon 24bit7.ico --collect-data ytmusicapi --add-data "24bit7.ico;." --hidden-import pystray._win32 gui.pyw
if errorlevel 1 (
    echo.
    echo Build FAILED. Your settings and history are safe in %BK%
    pause
    exit /b 1
)

rem --- 3. Release zip, made from the clean build before anything is put back ---
for /f %%v in ('powershell -NoProfile -Command "(Select-String -Path engine.py -Pattern '^VERSION\s*=\s*.([0-9.]+)').Matches[0].Groups[1].Value"') do set VER=%%v
set ZIP=releases\24bit7-v%VER%.zip
mkdir releases 2>nul
powershell -NoProfile -Command "Compress-Archive -Path 'dist\24bit7' -DestinationPath '%ZIP%' -Force"
powershell -NoProfile -Command "Add-Type -AssemblyName System.IO.Compression.FileSystem; $z = [IO.Compression.ZipFile]::OpenRead('%ZIP%'); $bad = @($z.Entries | Where-Object { $_.Name -in '.env', '24bit7.db' }); $z.Dispose(); if ($bad.Count) { exit 1 }"
if errorlevel 1 (
    del "%ZIP%"
    echo WARNING: the build folder held a .env or 24bit7.db, so no release zip was made.
) else (
    echo Release zip: %ZIP% ^(checked: no .env or database^)
)

rem --- 4. Put the packaged app's settings and history back, for your own use ---
if exist "%BK%\app\.env" copy /y "%BK%\app\.env" "dist\24bit7\" >nul
if exist "%BK%\app\24bit7.db" copy /y "%BK%\app\24bit7.db" "dist\24bit7\" >nul

rem --- 5. Keep the ten most recent backups ---
powershell -NoProfile -Command "Get-ChildItem backups -Directory | Sort-Object Name -Descending | Select-Object -Skip 10 | Remove-Item -Recurse -Force"

echo.
echo Build complete. Share %ZIP%, never a zip of dist\24bit7.
pause
