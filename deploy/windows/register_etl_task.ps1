<#
.SYNOPSIS
    Crea (o actualiza) la tarea programada que lanza el ETL de la API todos los dias.

.DESCRIPTION
    La tarea ejecuta trigger_etl.ps1 como SYSTEM a la hora indicada (por defecto 18:00, el horario del legado).
    NO deshabilita la tarea del script legado (run_midagri.bat): el legado y la API nunca deben correr los dos
    (SPEC-price-ingestion.md, runbook del corte). Si encuentra una tarea que ejecuta run_midagri.bat, avisa y se
    detiene, salvo que se pase -AllowLegacyTask (p. ej. en QAS, donde el legado no escribe en la base de la API).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File deploy\windows\register_etl_task.ps1
    powershell -ExecutionPolicy Bypass -File deploy\windows\register_etl_task.ps1 -At 06:30
#>
[CmdletBinding()]
param(
    [string]$ProjectDir = "",   # por defecto, la carpeta del proyecto (dos niveles arriba de este script)
    [string]$TaskName = "MIDAGRI API - ETL diario",
    [string]$At = "18:00",
    [string]$BaseUrl = "http://localhost:8000",
    [switch]$AllowLegacyTask
)

$ErrorActionPreference = "Stop"
# En Windows PowerShell 5.1, $PSScriptRoot esta vacio en los valores por defecto de param().
if (-not $ProjectDir) { $ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "[ERROR] Ejecute PowerShell como administrador." -ForegroundColor Red
    exit 1
}

$legacy = Get-ScheduledTask | Where-Object {
    $_.State -ne "Disabled" -and ($_.Actions | Where-Object { "$($_.Execute) $($_.Arguments)" -match "run_midagri" })
}
if ($legacy -and -not $AllowLegacyTask) {
    Write-Host "[ALTO] La tarea del script legado sigue activa: $($legacy.TaskName -join ', ')" -ForegroundColor Yellow
    Write-Host "       Deshabilitela primero (runbook del corte) o pase -AllowLegacyTask si sabe lo que hace:"
    Write-Host "       Disable-ScheduledTask -TaskName '$($legacy[0].TaskName)'"
    exit 1
}

$script = Join-Path $ProjectDir "deploy\windows\trigger_etl.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -WorkingDirectory $ProjectDir `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -BaseUrl $BaseUrl"
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
$runAs = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Principal $runAs -Description "POST /etl/runs {trigger: cron} a la API MIDAGRI. Log: logs\etl_trigger.log" `
    -Force | Out-Null

Write-Host "[OK] Tarea '$TaskName' registrada: todos los dias a las $At." -ForegroundColor Green
Write-Host "     Probar ahora: Start-ScheduledTask -TaskName '$TaskName'  (ver logs\etl_trigger.log)"

exit 0
