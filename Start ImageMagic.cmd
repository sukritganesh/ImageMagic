@echo off
cd /d "%~dp0"
if not exist "ComfyUI_windows_portable\python_embeded\python.exe" (
    echo Run setup.ps1 first. See README.md for installation.
    pause
    exit /b 1
)
"ComfyUI_windows_portable\python_embeded\python.exe" -s launch_studio.py
if errorlevel 1 pause
