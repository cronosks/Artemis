@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Artemis artemis.py
if errorlevel 1 (echo Falha criando EXE. & pause & exit /b 1)
copy /Y config.json dist\config.json >nul
echo [OK] dist\Artemis.exe criada.
pause
