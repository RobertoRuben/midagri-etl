@echo off
rem Asistente de despliegue de la API MIDAGRI (QAS o PRD). Va en la raiz del paquete descomprimido.
rem Pide permisos de administrador y abre deploy\windows\deploy_package.ps1, que pregunta el entorno,
rem el puerto, la configuracion (.env), las migraciones y la hora del ETL.
setlocal
chcp 65001 >nul

net session >nul 2>&1
if errorlevel 1 (
    echo Solicitando permisos de administrador...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\windows\deploy_package.ps1" %*
set "CODE=%errorlevel%"
echo.
if "%CODE%"=="0" (echo Despliegue terminado.) else (echo El despliegue termino con errores ^(codigo %CODE%^).)
pause
exit /b %CODE%
