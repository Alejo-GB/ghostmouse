@echo off
cd /d "%~dp0"
if exist "dist\GhostMouse.exe" (
    start "" "%~dp0dist\GhostMouse.exe"
) else (
    echo No se encontro la app en dist\GhostMouse.exe
    echo Ejecuta primero: build_portable.bat
    pause
)
