@echo off
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v Artemis /f >nul 2>nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Artemis.lnk" >nul 2>nul
echo Artemis removida da inicializacao.
pause
