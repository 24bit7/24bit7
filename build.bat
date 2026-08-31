@echo off
python -m pip install --upgrade pyinstaller
python -m PyInstaller --noconfirm --clean --windowed --name 24bit7 --icon 24bit7.ico gui.pyw
echo.
echo Build complete: dist\24bit7
pause