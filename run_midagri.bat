@echo off
setlocal EnableExtensions EnableDelayedExpansion
title MIDAGRI Runner

rem === CONFIGURACION PRINCIPAL ===
set "PROJECT_DIR=C:\ServerServices\Midagri"
set "VENV_DIR=venv"
set "PYTHON_BASE=C:\Python\Python313"
set "PYTHON_EXE=%PROJECT_DIR%\%VENV_DIR%\Scripts\python.exe"
set "MAIN_SCRIPT=run.py"
set "REQ_FILE=requirements.txt"
set "LOGS_DIR=%PROJECT_DIR%\logs"

rem === LIMPIEZA Y ENTORNO ===
set "PYTHONHOME="
set "PYTHONPATH="
set "PATH=%PYTHON_BASE%;%PYTHON_BASE%\Scripts;%PATH%"
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem === CREAR CARPETA DE LOGS ===
if not exist "%PROJECT_DIR%" (
    echo [ERROR] Missing project folder: %PROJECT_DIR%
    pause
    exit /b 1
)
if not exist "%LOGS_DIR%" (
    echo [INFO] Creating logs folder...
    mkdir "%LOGS_DIR%" 2>nul
    if not exist "%LOGS_DIR%" (
        echo [ERROR] Could not create logs folder: %LOGS_DIR%
        pause
        exit /b 2
    )
)

for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%I"
set "LOG_FILE=%LOGS_DIR%\midagri_%TS%.log"

(
    echo ========================================
    echo MIDAGRI - EXECUTION START
    echo Date/Time: %DATE% %TIME%
    echo Project: %PROJECT_DIR%
    echo Log: %LOG_FILE%
    echo ========================================
) > "%LOG_FILE%"

cd /d "%PROJECT_DIR%" || (
    echo [ERROR] Cannot change to project directory >>"%LOG_FILE%"
    exit /b 3
)

rem === CREAR ENTORNO VIRTUAL SI NO EXISTE ===
if not exist "%PYTHON_EXE%" (
    echo [INFO] Creating virtual environment...>>"%LOG_FILE%"
    "%PYTHON_BASE%\python.exe" -m venv "%VENV_DIR%" >>"%LOG_FILE%" 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment. >>"%LOG_FILE%"
        exit /b 5
    )
)

rem === ACTUALIZAR PIP Y DEPENDENCIAS ===
echo [INFO] Checking dependencies...>>"%LOG_FILE%"
if exist "%REQ_FILE%" (
    if not exist "%PROJECT_DIR%\%VENV_DIR%\Lib\site-packages\pyodbc.pyd" (
        echo [INFO] Installing packages...>>"%LOG_FILE%"
        "%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel >>"%LOG_FILE%" 2>&1
        "%PYTHON_EXE%" -m pip install -r "%REQ_FILE%" >>"%LOG_FILE%" 2>&1
        if %errorlevel% neq 0 (
            echo [ERROR] Failed to install dependencies. >>"%LOG_FILE%"
            exit /b 8
        )
    ) else (
        echo [INFO] Dependencies already installed.>>"%LOG_FILE%"
    )
) else (
    echo [WARN] Missing %REQ_FILE%. Continuing...>>"%LOG_FILE%"
)

rem === EJECUTAR PROGRAMA PRINCIPAL ===
if not exist "%MAIN_SCRIPT%" (
    echo [ERROR] Missing main script: %MAIN_SCRIPT% >>"%LOG_FILE%"
    exit /b 9
)

echo [INFO] Running MIDAGRI...>>"%LOG_FILE%"
"%PYTHON_EXE%" "%PROJECT_DIR%\%MAIN_SCRIPT%" >>"%LOG_FILE%" 2>&1
set "EXIT_CODE=%errorlevel%"

(
    echo ========================================
    if %EXIT_CODE% EQU 0 (
        echo [OK] EXECUTION COMPLETED SUCCESSFULLY
    ) else (
        echo [ERROR] EXECUTION FAILED - Code: %EXIT_CODE%
    )
    echo End time: %DATE% %TIME%
    echo ========================================
) >>"%LOG_FILE%"

exit /b %EXIT_CODE%
