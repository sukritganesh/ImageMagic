@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "desktop\build.ps1"
if errorlevel 1 (
    pause
    exit /b 1
)
start "" "%~dp0ImageMagic.exe"
