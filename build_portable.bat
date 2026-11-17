@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo No se encontro el entorno virtual .venv.
    echo Crea o activa un entorno antes de compilar.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo No se pudieron instalar las dependencias.
    pause
    exit /b 1
)
python -m PyInstaller --clean --noconfirm "InterfazMediaPipe.spec"
if errorlevel 1 (
    echo No se pudo compilar el ejecutable unico.
    pause
    exit /b 1
)

if exist "dist\GhostMouse.exe" (
    echo.
    echo Ejecutable unico creado en dist\GhostMouse.exe
) else (
    echo.
    echo No se pudo generar el ejecutable unico.
    exit /b 1
)
pause
