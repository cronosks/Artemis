@echo off
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.11+ nao encontrado. & pause & exit /b 1)
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (echo Falha na instalacao. & pause & exit /b 1)
echo [OK] Dependencias instaladas.
echo Agora execute .\build_exe.bat
pause
