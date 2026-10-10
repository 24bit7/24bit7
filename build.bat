@echo off
setlocal
cd /d "%~dp0"

rem Close the packaged 24bit7 before building, or its files can't be replaced.

rem --- 0. Full test suite: a failure stops the release before anything else happens ---
echo Running the tests (a few minutes)...
python -m pytest -q
if errorlevel 1 (
    echo.
    echo Tests FAILED, so nothing was built. Fix them and run build.bat again.
    pause
    exit /b 1
)
echo.

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
python -m PyInstaller --noconfirm --clean --windowed --name 24bit7 --icon 24bit7.ico --collect-data ytmusicapi --add-data "24bit7.ico;." --add-data "source_test_*.json;." --hidden-import pystray._win32 gui.pyw
if errorlevel 1 (
    echo.
    echo Build FAILED. Your settings and history are safe in %BK%
    pause
    exit /b 1
)

rem --- 3. Release zip, made from the clean build before anything is put back ---
for /f %%v in ('powershell -NoProfile -Command "(Select-String -Path engine.py -Pattern '^VERSION\s*=\s*.([0-9.]+)').Matches[0].Groups[1].Value"') do set VER=%%v
set ZIP=releases\24bit7-v%VER%-windows.zip
mkdir releases 2>nul

rem --- 3a. User manual PDF, beside 24bit7.exe so it goes out in the zip ---
python build_manual.py "dist\24bit7\24bit7_Manual.pdf"
if errorlevel 1 (
    echo.
    echo The user manual PDF couldn't be made, so this release would go out without it.
    choice /c SC /m "S to stop the release, C to carry on without the manual"
    if errorlevel 2 (
        echo Carrying on without the manual.
    ) else (
        if exist "%ZIP%" del "%ZIP%"
        echo Stopped before the zip. Putting your settings and history back.
        goto restore
    )
)
powershell -NoProfile -Command "$ok = $false; for ($i = 1; $i -le 6 -and -not $ok; $i++) { try { Compress-Archive -Path 'dist\24bit7' -DestinationPath '%ZIP%' -Force -ErrorAction Stop; $ok = $true } catch { Write-Host ('  A file is busy, usually Windows Defender scanning the new build. Retrying in 5 seconds, try ' + $i + ' of 6'); Start-Sleep -Seconds 5 } }; if (-not $ok) { exit 2 }"
if errorlevel 2 (
    if exist "%ZIP%" del "%ZIP%"
    echo Couldn't make the release zip: a file was still in use. Run build.bat again.
    goto restore
)
powershell -NoProfile -Command "Add-Type -AssemblyName System.IO.Compression.FileSystem; $z = [IO.Compression.ZipFile]::OpenRead('%ZIP%'); $bad = @($z.Entries | Where-Object { $_.Name -in '.env', '24bit7.db' }); $z.Dispose(); if ($bad.Count) { exit 1 }"
if errorlevel 1 (
    del "%ZIP%"
    echo WARNING: the build folder held a .env or 24bit7.db, so no release zip was made.
) else (
    echo Release zip: %ZIP% ^(checked: no .env or database^)
)

:restore
rem --- 4. Put the packaged app's settings and history back, for your own use ---
if exist "%BK%\app\.env" copy /y "%BK%\app\.env" "dist\24bit7\" >nul
if exist "%BK%\app\24bit7.db" copy /y "%BK%\app\24bit7.db" "dist\24bit7\" >nul

rem --- 5. Keep the ten most recent backups ---
powershell -NoProfile -Command "Get-ChildItem backups -Directory | Sort-Object Name -Descending | Select-Object -Skip 10 | Remove-Item -Recurse -Force"

rem --- 6. Publish to GitHub (release.ps1), only reached once tests, build and zip have all worked ---
if exist "%ZIP%" powershell -NoProfile -ExecutionPolicy Bypass -File release.ps1 -Version %VER% -Zip "%ZIP%"

echo.
echo Build complete.
pause
