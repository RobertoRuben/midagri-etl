<#
.SYNOPSIS
    Lanza el ETL: POST /etl/runs con {"trigger": "cron"}. Lo ejecuta la tarea programada diaria.

.DESCRIPTION
    Lee MIDAGRI_API_KEY del .env del proyecto (la clave no se copia en la tarea). Sin fechas ni mercados, la API
    usa los ultimos MIDAGRI_ETL_DEFAULT_WINDOW_DAYS dias y todos los mercados activos de BM_Market.
    La API responde 202 al instante y el ETL corre en segundo plano; el resultado llega por correo y queda en
    GET /etl/runs/{id}/logs. Codigos de salida: 0 aceptado o ya habia una ejecucion en curso (409, no se
    reintenta para no lanzar otra), 1 error (la tarea reintenta).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File deploy\windows\trigger_etl.ps1
#>
[CmdletBinding()]
param(
    [string]$ProjectDir = "",   # por defecto, la carpeta del proyecto (dos niveles arriba de este script)
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Trigger = "cron"
)

$ErrorActionPreference = "Stop"
# En Windows PowerShell 5.1, $PSScriptRoot esta vacio en los valores por defecto de param().
if (-not $ProjectDir) { $ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
$logsDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
$logFile = Join-Path $logsDir "etl_trigger.log"

function Log([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Host $line
}

$envFile = Join-Path $ProjectDir ".env"
$keyLine = Get-Content $envFile -Encoding UTF8 -ErrorAction SilentlyContinue |
    Where-Object { $_ -match '^\s*MIDAGRI_API_KEY\s*=' } | Select-Object -First 1
if (-not $keyLine) { Log "[ERROR] No se encontro MIDAGRI_API_KEY en $envFile"; exit 1 }
$apiKey = ($keyLine -split "=", 2)[1].Trim().Trim('"').Trim("'")

$body = @{ trigger = $Trigger } | ConvertTo-Json -Compress
try {
    $response = Invoke-WebRequest -Uri "$BaseUrl/etl/runs" -Method Post -UseBasicParsing -TimeoutSec 60 `
        -Headers @{ "X-API-Key" = $apiKey } -ContentType "application/json" -Body $body
    Log "[OK] $($response.StatusCode) ETL aceptado: $($response.Content)"
    exit 0
} catch {
    $status = $null
    if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
    if ($status -eq 409) {
        Log "[AVISO] 409 ya hay una ejecucion en curso; no se lanzo otra."
        exit 0
    }
    Log "[ERROR] No se pudo lanzar el ETL ($status): $($_.Exception.Message)"
    exit 1
}
