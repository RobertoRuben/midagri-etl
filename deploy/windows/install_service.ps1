<#
.SYNOPSIS
    Instala o actualiza la API MIDAGRI como servicio de Windows (NSSM). Idempotente: se puede volver a correr
    en cada despliegue. Normalmente lo llama deploy_package.ps1 (el asistente), que pregunta entorno y puerto.

.DESCRIPTION
    1. Verifica administrador, .env, uv y NSSM. Con -Environment, exige que MIDAGRI_ENVIRONMENT del .env coincida.
    2. Instala Python 3.14 (.python-version) y las dependencias con uv en rutas de maquina, para que el
       servicio (LocalSystem) las encuentre aunque uv se haya instalado con otro usuario.
    3. Valida el .env cargando la configuracion de la API (falla con el nombre del campo que falta).
    4. Aplica las migraciones de PostgreSQL (alembic upgrade head) y muestra la revision antes y despues.
       SQL Server NO se toca (scripts de sql/).
    5. Registra el servicio: .venv\Scripts\python.exe -m fastapi run, en la carpeta del proyecto (lee .env y
       [tool.fastapi] de pyproject.toml), con reinicio automatico y logs rotados en logs\.
    6. Arranca el servicio y espera a que /health responda.

    Un solo proceso (sin --workers): el ETL corre en segundo plano dentro de la API y solo puede haber una
    ejecucion a la vez.

.EXAMPLE
    # PowerShell como administrador, en la carpeta del entorno:
    powershell -ExecutionPolicy Bypass -File deploy\windows\install_service.ps1 -Environment qas -Port 8001 -OpenFirewall
#>
[CmdletBinding()]
param(
    [string]$ProjectDir = "",   # por defecto, la carpeta del proyecto (dos niveles arriba de este script)
    [ValidateSet("qas", "prd")]
    [string]$Environment,
    [string]$ServiceName = "",  # por defecto, MidagriApi-QAS / MidagriApi-PRD segun -Environment
    [string]$NssmPath = "nssm.exe",
    [string]$UvHome = "C:\ServerServices\uv",
    [string]$ListenHost = "0.0.0.0",
    [int]$Port = 8000,
    [switch]$SkipMigrations,
    [switch]$OpenFirewall   # crea o actualiza la regla de entrada "MIDAGRI API <ENTORNO>" para el puerto
)

$ErrorActionPreference = "Stop"
# En Windows PowerShell 5.1, $PSScriptRoot esta vacio en los valores por defecto de param().
if (-not $ProjectDir) { $ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
$envLabel = if ($Environment) { $Environment.ToUpper() } else { "" }
if (-not $ServiceName) { $ServiceName = if ($envLabel) { "MidagriApi-$envLabel" } else { "MidagriApi" } }
$firewallRule = ("MIDAGRI API $envLabel").Trim()

function Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Fail([string]$Message) { Write-Host "[ERROR] $Message" -ForegroundColor Red; exit 1 }
function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { Fail "Fallo: $Exe $($Arguments -join ' ') (codigo $LASTEXITCODE)" }
}

# --- 1. Requisitos ---------------------------------------------------------------------------------------------
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail "Ejecute PowerShell como administrador."
}
if (-not (Test-Path (Join-Path $ProjectDir "pyproject.toml"))) { Fail "No es la carpeta del proyecto: $ProjectDir" }
$envFile = Join-Path $ProjectDir ".env"
if (-not (Test-Path $envFile)) { Fail "Falta $envFile (use deploy_package.ps1, que lo arma, o copie .env.example)." }
if ($Environment) {
    $envLine = Get-Content $envFile | Where-Object { $_ -match '^\s*MIDAGRI_ENVIRONMENT\s*=' } | Select-Object -First 1
    $configured = if ($envLine) { ($envLine -split "=", 2)[1].Trim().Trim('"').Trim("'") } else { "" }
    if ($configured -ne $Environment) {
        Fail "El .env dice MIDAGRI_ENVIRONMENT=$configured pero se pidio instalar $envLabel. Revise $envFile."
    }
}

$uv = (Get-Command uv.exe -ErrorAction SilentlyContinue).Source
if (-not $uv) { Fail "No se encontro uv. Instalelo: powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`"" }
$nssm = (Get-Command $NssmPath -ErrorAction SilentlyContinue).Source
if (-not $nssm) { Fail "No se encontro NSSM ($NssmPath). Descarguelo de https://nssm.cc y pase -NssmPath." }

$odbc = Get-OdbcDriver -Name "ODBC Driver 17 for SQL Server" -ErrorAction SilentlyContinue
if (-not $odbc) { Write-Warning "No se encontro 'ODBC Driver 17 for SQL Server': la API no podra conectarse a SQL Server." }

# Python y cache de uv en rutas de maquina: el .venv apunta a este Python y el servicio corre como LocalSystem.
$env:UV_PYTHON_INSTALL_DIR = Join-Path $UvHome "python"
$env:UV_CACHE_DIR = Join-Path $UvHome "cache"
$env:PYTHONUTF8 = "1"
New-Item -ItemType Directory -Force -Path $env:UV_PYTHON_INSTALL_DIR, $env:UV_CACHE_DIR | Out-Null
$logsDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

Set-Location $ProjectDir

# --- 2. Detener el servicio si ya existe (libera el .venv) ------------------------------------------------------
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing -and $existing.Status -ne "Stopped") {
    Step "Deteniendo el servicio $ServiceName"
    Stop-Service -Name $ServiceName -Force
    $existing.WaitForStatus("Stopped", (New-TimeSpan -Seconds 60))
}

# --- 3. Python y dependencias -----------------------------------------------------------------------------------
Step "Instalando Python (.python-version) y dependencias (uv.lock, sin las de desarrollo)"
Invoke-Checked $uv @("python", "install")
Invoke-Checked $uv @("sync", "--frozen", "--no-dev")
$python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { Fail "No se creo $python" }

# --- 4. Validacion del .env -------------------------------------------------------------------------------------
Step "Validando la configuracion (.env)"
& $python -c "from app.modules.common.config import base_config as c; print(f'    ambiente={c.environment}  sql_server={c.mssql_host}/{c.mssql_database}  postgres={c.pg_host}/{c.pg_database}')"
if ($LASTEXITCODE -ne 0) { Fail "El .env esta incompleto o tiene valores invalidos (arriba, el campo). Revise $envFile." }

# --- 5. Migraciones de PostgreSQL -------------------------------------------------------------------------------
if ($SkipMigrations) {
    Write-Warning "Migraciones omitidas (-SkipMigrations)."
} else {
    Step "Migraciones de PostgreSQL: revision actual"
    Invoke-Checked $python @("-m", "alembic", "current")
    Step "Aplicando migraciones (alembic upgrade head)"
    Invoke-Checked $python @("-m", "alembic", "upgrade", "head")
    Step "Revision despues de migrar"
    Invoke-Checked $python @("-m", "alembic", "current")
}

# --- 6. Servicio NSSM -------------------------------------------------------------------------------------------
if (-not $existing) {
    Step "Registrando el servicio $ServiceName"
    Invoke-Checked $nssm @("install", $ServiceName, $python)
} else {
    Step "Actualizando la configuracion del servicio $ServiceName"
}
$displayName = ("MIDAGRI API $envLabel (ETL SISAP)") -replace "\s+", " "
$settings = @(
    @("Application", $python),
    @("AppParameters", "-m fastapi run --host $ListenHost --port $Port"),
    @("AppDirectory", $ProjectDir),
    @("DisplayName", $displayName),
    @("Description", "API ETL de precios SISAP - MIDAGRI $envLabel. Puerto $Port. Logs en $logsDir."),
    @("Start", "SERVICE_AUTO_START"),
    @("AppEnvironmentExtra", "PYTHONUTF8=1", "PYTHONIOENCODING=utf-8"),
    @("AppStdout", (Join-Path $logsDir "api.log")),
    @("AppStderr", (Join-Path $logsDir "api.log")),
    @("AppRotateFiles", "1"),
    @("AppRotateOnline", "1"),
    @("AppRotateBytes", "10485760"),
    @("AppExit", "Default", "Restart"),
    @("AppRestartDelay", "10000"),
    @("AppStopMethodConsole", "30000")   # Ctrl+C y 30 s para cerrar: las corridas en curso quedan 'failed'
)
foreach ($setting in $settings) {
    Invoke-Checked $nssm (@("set", $ServiceName) + $setting)
}

# --- 7. Arranque y verificacion ---------------------------------------------------------------------------------
Step "Iniciando el servicio"
Start-Service -Name $ServiceName
$healthUrl = "http://localhost:$Port/health"
$deadline = (Get-Date).AddSeconds(90)
$health = $null
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 30
        break
    } catch { }
}
if (-not $health) {
    Get-Content (Join-Path $logsDir "api.log") -Tail 40 -ErrorAction SilentlyContinue
    Fail "La API no respondio en $healthUrl. Revise $logsDir\api.log (arriba, las ultimas lineas)."
}
$color = if ($health.status -eq "ok") { "Green" } else { "Yellow" }
Write-Host "    /health: status=$($health.status)  sql_server=$($health.mssql)  postgres=$($health.postgres)  sisap=$($health.sisap)" -ForegroundColor $color
if ($health.status -ne "ok") { Write-Warning "La API arranco pero alguna dependencia fallo. Detalle: $($health.details | ConvertTo-Json -Compress)" }

if ($OpenFirewall) {
    if (Get-NetFirewallRule -DisplayName $firewallRule -ErrorAction SilentlyContinue) {
        Set-NetFirewallRule -DisplayName $firewallRule -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow
    } else {
        New-NetFirewallRule -DisplayName $firewallRule -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow | Out-Null
    }
    Write-Host "    Firewall: regla '$firewallRule' abierta para el puerto TCP $Port."
}

Write-Host ""
Write-Host "[OK] $ServiceName corriendo en el puerto $Port  (salud: $healthUrl, documentacion: /docs)" -ForegroundColor Green
Write-Host "     Logs: $logsDir\api.log  |  Detener: Stop-Service $ServiceName"

exit 0
