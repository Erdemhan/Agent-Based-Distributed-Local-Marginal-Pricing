@echo off
setlocal enabledelayedexpansion
set PYTHONIOENCODING=utf-8
chcp 65001 > nul

SET WORK_DIR=%~dp0
cd /d "%WORK_DIR%"

:: Create the virtual environment in a shorter path to avoid Windows MAX_PATH (WinError 206) issues
:: %USERPROFILE% automatically resolves to C:\Users\<Username> on any Windows machine
SET VENV_DIR=%USERPROFILE%\venv_abm-dlmp

echo ==================================================
echo   DLMP Agent-Based Simulation Launcher
echo ==================================================

:: Detect Python executable dynamically
SET PYTHON_CMD=

where python >nul 2>nul
if %errorlevel% equ 0 SET PYTHON_CMD=python

where py >nul 2>nul
if %errorlevel% equ 0 if not defined PYTHON_CMD SET PYTHON_CMD=py

if not defined PYTHON_CMD (
    for %%P in (
        "%USERPROFILE%\AppData\Local\Programs\Python\Python313\python.exe"
        "%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"
        "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"
        "%USERPROFILE%\AppData\Local\Programs\Python\Python310\python.exe"
        "%USERPROFILE%\Anaconda3\python.exe"
        "%USERPROFILE%\miniconda3\python.exe"
        "C:\Program Files\Python313\python.exe"
        "C:\Program Files\Python312\python.exe"
        "C:\Program Files\Python311\python.exe"
        "C:\Program Files\Python310\python.exe"
        "C:\ProgramData\Anaconda3\python.exe"
    ) do (
        if exist "%%~P" SET PYTHON_CMD="%%~P"
    )
)

if not defined PYTHON_CMD (
    echo [ERROR] Python could not be detected on this system!
    echo Lütfen Python'un yüklü ve PATH'e ekli olduğundan emin olun.
    pause
    exit /b 1
)

:: Check if virtual environment and python executable exist
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [INFO] Creating virtual environment in a short path: %VENV_DIR%
    "%PYTHON_CMD%" -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b !errorlevel!
    )
    
    echo [INFO] Virtual environment created successfully.
    echo [INFO] Installing required libraries from requirements.txt...
    "%VENV_DIR%\Scripts\pip" install --upgrade pip
    "%VENV_DIR%\Scripts\pip" install -r "%WORK_DIR%requirements.txt"
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to install requirements.
        pause
        exit /b !errorlevel!
    )
    echo [INFO] Installation completed successfully.
)

:: Start fastapi application with uvicorn
echo [INFO] Starting FastAPI Web Application...
"%VENV_DIR%\Scripts\python" -m uvicorn services.backend:app --host localhost --port 8501 --reload

if !errorlevel! neq 0 (
    echo [ERROR] Application crashed or could not start.
    pause
)
