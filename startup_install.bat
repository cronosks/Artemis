@echo off
cd /d "%~dp0"
if not exist "dist\Artemis.exe" (
 echo Artemis.exe nao encontrada. Rode .\build_exe.bat primeiro.
 pause
 exit /b 1
)
set "DIR=%LOCALAPPDATA%\Artemis"
if not exist "%DIR%" mkdir "%DIR%"
copy /Y "dist\Artemis.exe" "%DIR%\Artemis.exe" >nul
copy /Y "config.json" "%DIR%\config.json" >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$exe=Join-Path $env:LOCALAPPDATA 'Artemis\Artemis.exe'; $run='HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'; New-Item -Path $run -Force | Out-Null; New-ItemProperty -Path $run -Name Artemis -Value ('""'+$exe+'""') -PropertyType String -Force | Out-Null; $startup=[Environment]::GetFolderPath('Startup'); $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut((Join-Path $startup 'Artemis.lnk')); $s.TargetPath=$exe; $s.WorkingDirectory=(Split-Path $exe); $s.WindowStyle=7; $s.Save()"
echo [OK] Artemis instalada para iniciar com o Windows.
echo Verifique Configuracoes ^> Aplicativos ^> Inicializacao.
pause
