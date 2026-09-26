@echo off
python -m pip install --upgrade pyinstaller
python -m PyInstaller --noconfirm --clean --windowed --name 24bit7 --icon 24bit7.ico --collect-data ytmusicapi --add-data "24bit7.ico;." --hidden-import pystray._win32 gui.pyw
echo.
echo Build complete: dist\24bit7
pause