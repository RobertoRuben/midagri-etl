<#
.SYNOPSIS
    Asistente de despliegue de la API MIDAGRI en Windows Server: primera instalacion, actualizacion o rollback,
    para QAS o PRD. Pregunta el entorno, la carpeta, el puerto, la configuracion (.env) y la hora del ETL.

.DESCRIPTION
    Cada entorno es independiente y pueden convivir en el mismo servidor:

        Entorno  Carpeta                            Servicio         Puerto  ETL    Bases por defecto
        QAS      C:\ServerServices\MidagriApi\qas   MidagriApi-QAS   8001    19:00  BDFarmex_Agri / midagri_qas
        PRD      C:\ServerServices\MidagriApi\prd   MidagriApi-PRD   8000    18:00  BDFARMEX      / midagri_prd

    Pasos:
    1. Pregunta entorno, carpeta, puerto (muestra los ocupados y recomienda uno libre) y firewall.
    2. Arma o revisa el .env del entorno: bases, correo, alta automatica; genera MIDAGRI_API_KEY si falta.
       Lo guarda en UTF-8 y con permisos solo para Administradores y SYSTEM.
    3. Pregunta si aplicar las migraciones de PostgreSQL y a que hora correr el ETL.
    4. Muestra un resumen y pide confirmacion (en PRD hay que escribir PRD).
    5. Detiene el servicio, respalda el codigo en backups\<fecha> (quedan 5), copia el codigo nuevo (no toca
       .env, logs ni .venv) y llama a install_service.ps1 (dependencias, migraciones, servicio y /health).
    6. Registra la tarea programada del ETL (register_etl_task.ps1).

    El codigo sale del paquete descomprimido donde esta este script (o de -Package <zip>). Si se ejecuta desde la
    carpeta ya instalada, solo reconfigura (puerto, .env, hora) y reinstala.

    El script legado (run_midagri.bat) NO se toca, salvo que en PRD se elija hacer el corte y se confirme
    escribiendo CORTE: entonces se deshabilita su tarea programada (nunca corren los dos).

.EXAMPLE
    # Doble clic en desplegar.cmd (pide administrador), o en PowerShell como administrador:
    powershell -ExecutionPolicy Bypass -File C:\Temp\midagri-api_0.1.0_20260930_1700\deploy\windows\deploy_package.ps1

.EXAMPLE
    # Sin preguntas (el .env del entorno ya debe estar completo):
    powershell -ExecutionPolicy Bypass -File .\deploy\windows\deploy_package.ps1 -Environment qas -Port 8001 -EtlTime 19:00 -NonInteractive

.EXAMPLE
    # Volver al respaldo anterior (no revierte migraciones de PostgreSQL):
    powershell -ExecutionPolicy Bypass -File C:\ServerServices\MidagriApi\qas\deploy\windows\deploy_package.ps1 -Environment qas -Rollback
#>
[CmdletBinding()]
param(
    [ValidateSet("qas", "prd")]
    [string]$Environment,
    [string]$Package = "",       # zip de build_package.ps1; por defecto, la carpeta donde esta este script
    [string]$ProjectDir = "",
    [int]$Port = 0,
    [string]$EtlTime = "",
    [switch]$SkipEtlTask,
    [switch]$SkipMigrations,
    [switch]$OpenFirewall,
    [switch]$Rollback,
    [switch]$NonInteractive,
    [string]$NssmPath = "nssm.exe",
    [int]$KeepBackups = 5
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "deploy_common.ps1")

$profiles = @{
    qas = @{ Label = "QAS (pruebas)"; Dir = "C:\ServerServices\MidagriApi\qas"; Port = 8001; EtlTime = "19:00"
             MssqlDatabase = "BDFarmex_Agri"; PgDatabase = "midagri_qas" }
    prd = @{ Label = "PRD (produccion)"; Dir = "C:\ServerServices\MidagriApi\prd"; Port = 8000; EtlTime = "18:00"
             MssqlDatabase = "BDFARMEX"; PgDatabase = "midagri_prd" }
}
# Lo que pertenece al paquete. Todo lo demas de la carpeta (.env, logs, .venv, backups) se conserva.
$codeItems = @("src", "alembic", "alembic.ini", "pyproject.toml", "uv.lock", ".python-version", "README.md",
    ".env.example", "deploy", "VERSION.txt", "desplegar.cmd")
$timePattern = '^([01]?\d|2[0-3]):[0-5]\d$'

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host "   MIDAGRI API - asistente de despliegue en Windows Server" -ForegroundColor Cyan
Write-Host "  ============================================================" -ForegroundColor Cyan

# --- 1. Requisitos del servidor --------------------------------------------------------------------------------
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail "Ejecute como administrador (clic derecho en desplegar.cmd > Ejecutar como administrador)."
}
if (-not (Get-Command uv.exe -ErrorAction SilentlyContinue)) {
    Fail "Falta uv. Instalelo y abra una consola nueva: powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`""
}
$nssm = (Get-Command $NssmPath -ErrorAction SilentlyContinue).Source
if (-not $nssm) {
    Warn "No se encontro nssm.exe en el PATH (se descarga de https://nssm.cc)."
    $nssm = Ask "Ruta completa de nssm.exe" "" { param($a) Test-Path $a -PathType Leaf } "No existe ese archivo."
}
if (-not (Get-OdbcDriver -Name "ODBC Driver 17 for SQL Server" -ErrorAction SilentlyContinue)) {
    Warn "No esta instalado 'ODBC Driver 17 for SQL Server': la API no podra conectarse a SQL Server."
    if (-not (AskYesNo "Continuar de todos modos?" $false)) { exit 1 }
}

# --- 2. Entorno y carpeta --------------------------------------------------------------------------------------
Step "Entorno"
if (-not $Environment) {
    $choice = AskChoice "Seleccione el entorno" @(
        "QAS - pruebas     (SQL Server BDFarmex_Agri, PostgreSQL de QAS)",
        "PRD - produccion  (SQL Server BDFARMEX, PostgreSQL de produccion)") 0
    $Environment = @("qas", "prd")[$choice - 1]
}
$envProfile = $profiles[$Environment]
$envLabel = $Environment.ToUpper()
$serviceName = "MidagriApi-$envLabel"
$taskName = "MIDAGRI API $envLabel - ETL diario"
$otherEnv = if ($Environment -eq "qas") { "prd" } else { "qas" }
$otherService = "MidagriApi-$($otherEnv.ToUpper())"
Info "Entorno: $($envProfile.Label)  |  servicio: $serviceName"

if (-not $ProjectDir) {
    $ProjectDir = Ask "Carpeta de instalacion" $envProfile.Dir { param($a) [IO.Path]::IsPathRooted($a) } "Use una ruta completa, p. ej. $($envProfile.Dir)."
}
$ProjectDir = [IO.Path]::GetFullPath($ProjectDir).TrimEnd("\")
if ((Test-Path (Join-Path $ProjectDir "run_midagri.bat")) -or (Test-Path (Join-Path $ProjectDir "system"))) {
    Fail "$ProjectDir es la carpeta del script legado. La API va en otra carpeta (p. ej. $($envProfile.Dir))."
}
$backupsDir = Join-Path $ProjectDir "backups"
$envFile = Join-Path $ProjectDir ".env"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

# --- Rollback: restaura el ultimo respaldo y reinstala con la misma configuracion ------------------------------
if ($Rollback) {
    $backup = Get-ChildItem $backupsDir -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending |
        Select-Object -First 1
    if (-not $backup) { Fail "No hay respaldos en $backupsDir" }
    $rollbackPort = Get-ServicePort $serviceName
    if (-not $rollbackPort) { $rollbackPort = $envProfile.Port }
    Info "Respaldo: $($backup.FullName)  |  puerto: $rollbackPort  |  sin migraciones"
    if (-not (AskYesNo "Restaurar este respaldo en ${envLabel}?" $false)) { exit 1 }
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($service -and $service.Status -ne "Stopped") { Stop-Service $serviceName -Force; $service.WaitForStatus("Stopped", (New-TimeSpan -Seconds 60)) }
    foreach ($item in $codeItems) {
        $target = Join-Path $ProjectDir $item
        if (Test-Path (Join-Path $backup.FullName $item)) {
            if (Test-Path $target) { Remove-Item $target -Recurse -Force }
            Copy-Item (Join-Path $backup.FullName $item) $target -Recurse -Force
        }
    }
    & (Join-Path $ProjectDir "deploy\windows\install_service.ps1") -ProjectDir $ProjectDir -Environment $Environment `
        -ServiceName $serviceName -NssmPath $nssm -Port $rollbackPort -SkipMigrations
    exit $LASTEXITCODE
}

# --- 3. Origen del codigo --------------------------------------------------------------------------------------
$packageRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\..")).TrimEnd("\")
$tempSource = $null
if ($Package) {
    if (-not (Test-Path $Package)) { Fail "No existe el paquete: $Package" }
    $tempSource = Join-Path ([IO.Path]::GetTempPath()) "midagri-api_$stamp"
    Expand-Archive -Path $Package -DestinationPath $tempSource -Force
    $source = $tempSource
} else {
    $source = $packageRoot
}
if (-not (Test-Path (Join-Path $source "pyproject.toml"))) { Fail "$source no es un paquete de la API (falta pyproject.toml)." }
if ((Test-Path (Join-Path $source "run_midagri.bat")) -or (Test-Path (Join-Path $source "system"))) {
    Fail "$source es el repositorio completo, no un paquete. Genere el zip con build_package.ps1."
}
$sameDir = $source -ieq $ProjectDir
$versionFile = Join-Path $source "VERSION.txt"
$version = if (Test-Path $versionFile) { (Get-Content $versionFile -TotalCount 2) -join " | " } else { "(sin VERSION.txt)" }
$installed = Join-Path $ProjectDir "VERSION.txt"
Step "Codigo"
Info "Origen: $source"
Info "Version a instalar: $version"
if ($sameDir) { Info "Se ejecuta desde la carpeta instalada: solo se reconfigura y reinstala." }
elseif (Test-Path $installed) { Info "Version instalada:  $((Get-Content $installed -TotalCount 2) -join ' | ')" }
else { Info "Primera instalacion en $ProjectDir." }

# --- 4. Puerto -------------------------------------------------------------------------------------------------
Step "Puerto HTTP de la API"
$currentPort = Get-ServicePort $serviceName
$otherPort = Get-ServicePort $otherService
$listening = @(Get-ListeningPorts 8000 8099)
$busy = @{}
foreach ($entry in $listening) { $busy[$entry.Port] = $entry.Owner }
if ($currentPort) { $busy.Remove($currentPort) }   # lo ocupa esta misma API: se puede reutilizar
if ($otherPort) { $busy[$otherPort] = "$otherService (la API de $($otherEnv.ToUpper()))" }

$recommended = if ($currentPort) { $currentPort } else { $envProfile.Port }
while ($busy.ContainsKey($recommended)) { $recommended++ }

Info "Convencion: PRD usa 8000 y QAS 8001; si conviven en el servidor, deben ser distintos."
if ($currentPort) { Info "Este servicio ya usa el puerto $currentPort." }
if ($busy.Count) {
    Info "Ocupados en este servidor (8000-8099):"
    foreach ($p in ($busy.Keys | Sort-Object)) { Info "   $p  $($busy[$p])" }
} else {
    Info "No hay otros puertos ocupados entre 8000 y 8099."
}
Info "Recomendado para ${envLabel}: $recommended. La tarea del ETL llama a http://localhost:<puerto>."
$portDefault = if ($Port) { "$Port" } else { "$recommended" }
$Port = [int](Ask "Puerto" $portDefault {
        param($a) ($a -match '^\d+$') -and [int]$a -ge 1024 -and [int]$a -le 65535 -and -not $busy.ContainsKey([int]$a)
    } "Use un numero entre 1024 y 65535 que no este ocupado (vea la lista de arriba).")

$wantFirewall = AskYesNo "Abrir el puerto $Port en el firewall de Windows (para consultar la API desde otras maquinas)?" ($OpenFirewall.IsPresent -or -not $NonInteractive)

# --- 5. Configuracion (.env) -----------------------------------------------------------------------------------
Step "Configuracion del entorno (.env)"
$template = Join-Path $source ".env.example"
$current = Read-EnvFile $envFile
$currentEnv = $current["MIDAGRI_ENVIRONMENT"]
$fields = @(
    @{ Key = "MIDAGRI_MSSQL_HOST";     Label = "SQL Server - servidor (host o IP)" },
    @{ Key = "MIDAGRI_MSSQL_PORT";     Label = "SQL Server - puerto"; Default = "1433"; Number = $true },
    @{ Key = "MIDAGRI_MSSQL_DATABASE"; Label = "SQL Server - base"; Default = $envProfile.MssqlDatabase; PerEnv = $true },
    @{ Key = "MIDAGRI_MSSQL_USERNAME"; Label = "SQL Server - usuario" },
    @{ Key = "MIDAGRI_MSSQL_PASSWORD"; Label = "SQL Server - contrasena"; Secret = $true },
    @{ Key = "MIDAGRI_PG_HOST";        Label = "PostgreSQL - servidor (host o IP)" },
    @{ Key = "MIDAGRI_PG_PORT";        Label = "PostgreSQL - puerto"; Default = "5432"; Number = $true },
    @{ Key = "MIDAGRI_PG_DATABASE";    Label = "PostgreSQL - base (debe existir)"; Default = $envProfile.PgDatabase; PerEnv = $true },
    @{ Key = "MIDAGRI_PG_USERNAME";    Label = "PostgreSQL - usuario" },
    @{ Key = "MIDAGRI_PG_PASSWORD";    Label = "PostgreSQL - contrasena"; Secret = $true }
)
$required = @($fields | ForEach-Object { $_.Key }) + @("MIDAGRI_API_KEY")
$missing = @($required | Where-Object { Test-Blank $current[$_] })

$edit = $true
if (Test-Path $envFile) {
    if ($currentEnv -and $currentEnv -ne $Environment) {
        Warn "El .env existente es de '$currentEnv', no de '$Environment'. Revise todos los valores."
    } elseif ($missing.Count) {
        Warn "Al .env le faltan: $($missing -join ', ')."
    } else {
        Info "Se encontro $envFile :"
        foreach ($field in $fields) {
            $shown = if ($field.Secret) { "********" } else { $current[$field.Key] }
            Info ("   {0,-36} {1}" -f $field.Label, $shown)
        }
        Info ("   {0,-36} {1}" -f "Correo habilitado", $current["MIDAGRI_MAIL_ENABLED"])
        Info ("   {0,-36} {1}" -f "Alta automatica de faltantes", $current["MIDAGRI_CATALOG_AUTO_REGISTER"])
        $edit = AskYesNo "Editar la configuracion?" $false
    }
} else {
    Info "No hay .env en $ProjectDir : se arma ahora a partir de .env.example."
}
if ($edit -and $NonInteractive) { Fail "El .env de $envLabel falta o esta incompleto: complete $envFile o ejecute sin -NonInteractive." }

$updates = @{ MIDAGRI_ENVIRONMENT = $Environment }
$sameEnv = (-not $currentEnv) -or ($currentEnv -eq $Environment)
if ($edit) {
    Info "Enter acepta el valor entre corchetes."
    foreach ($field in $fields) {
        $existing = $current[$field.Key]
        $useExisting = -not (Test-Blank $existing) -and ($sameEnv -or -not $field.PerEnv)
        if ($field.Secret) {
            $updates[$field.Key] = AskSecret $field.Label $(if ($useExisting) { $existing } else { "" })
        } else {
            $default = if ($useExisting) { $existing } elseif ($field.Default) { $field.Default } else { "" }
            $validate = if ($field.Number) { { param($a) $a -match '^\d+$' } } else { $null }
            $updates[$field.Key] = Ask $field.Label $default $validate
        }
    }

    Info ""
    Info "Correo de inicio y fin de cada ETL (Gmail con contrasena de aplicacion)."
    $mailEnabled = AskYesNo "Habilitar el envio de correos?" ($current["MIDAGRI_MAIL_ENABLED"] -eq "true")
    $updates["MIDAGRI_MAIL_ENABLED"] = if ($mailEnabled) { "true" } else { "false" }
    if ($mailEnabled) {
        $mailUser = $current["MIDAGRI_MAIL_USERNAME"]
        $updates["MIDAGRI_MAIL_USERNAME"] = Ask "Correo - cuenta de Gmail remitente" $(if (Test-Blank $mailUser) { "" } else { $mailUser }) `
            { param($a) $a -match '^[^@\s]+@[^@\s]+$' } "Escriba una direccion de correo."
        $mailPassword = $current["MIDAGRI_MAIL_PASSWORD"]
        $updates["MIDAGRI_MAIL_PASSWORD"] = AskSecret "Correo - contrasena de aplicacion" $(if (Test-Blank $mailPassword) { "" } else { $mailPassword })
        Info "Los destinatarios se cargan en la API (tabla mail_recipient), no aqui."
    }

    Info ""
    Info "Alta automatica de faltantes en el catalogo al final de cada ETL (D36)."
    if ($Environment -eq "prd") { Warn "En PRD solo se activa con aprobacion expresa; primero se valida en QAS." }
    $autoDefault = ($current["MIDAGRI_CATALOG_AUTO_REGISTER"] -eq "true") -and $sameEnv
    $autoRegister = AskYesNo "Activar el alta automatica?" $autoDefault
    $updates["MIDAGRI_CATALOG_AUTO_REGISTER"] = if ($autoRegister) { "true" } else { "false" }
}

# URL publica (enlaces de los correos): mismo host, puerto nuevo.
$publicUrl = $current["MIDAGRI_API_PUBLIC_URL"]
if ((Test-Blank $publicUrl) -or $publicUrl -match '://(localhost|127\.0\.0\.1)[:/]' -or -not $sameEnv) {
    $publicUrl = "http://$($env:COMPUTERNAME.ToLower()):$Port"
} else {
    $publicUrl = $publicUrl -replace '(://[^/:]+)(:\d+)?', "`$1:$Port"
}
if ($edit) {
    $publicUrl = Ask "URL con la que se llega a la API desde otras maquinas (enlaces en los correos)" $publicUrl `
        { param($a) $a -match '^https?://' } "Debe empezar con http:// o https://."
}
$updates["MIDAGRI_API_PUBLIC_URL"] = $publicUrl

$apiKey = $current["MIDAGRI_API_KEY"]
$apiKeyGenerated = (Test-Blank $apiKey) -or $apiKey.Length -lt 32 -or -not $sameEnv
if ($apiKeyGenerated) {
    $apiKey = New-ApiKey
    $updates["MIDAGRI_API_KEY"] = $apiKey
    Info "Se generara una MIDAGRI_API_KEY nueva para $envLabel."
}

# --- 6. Migraciones --------------------------------------------------------------------------------------------
Step "Migraciones de PostgreSQL"
$pgDatabase = if ($updates["MIDAGRI_PG_DATABASE"]) { $updates["MIDAGRI_PG_DATABASE"] } else { $current["MIDAGRI_PG_DATABASE"] }
Info "Crean o actualizan las tablas propias de la API (etl_run, price_load, mail_*...) en '$pgDatabase'."
Info "No tocan SQL Server: los scripts de sql\ van por el runbook."
$runMigrations = (-not $SkipMigrations) -and (AskYesNo "Aplicar las migraciones (alembic upgrade head)?" $true)

# --- 7. Tarea programada del ETL -------------------------------------------------------------------------------
Step "Ejecucion diaria del ETL"
$taskMode = "none"   # none | enabled | disabled | cutover
$legacy = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
        $_.State -ne "Disabled" -and ($_.Actions | Where-Object { "$($_.Execute) $($_.Arguments)" -match "run_midagri" })
    })
if (-not $SkipEtlTask -and (AskYesNo "Programar la ejecucion diaria del ETL para ${envLabel}?" $true)) {
    $taskMode = "enabled"
    $existingTime = Get-TaskTime $taskName
    $otherTime = Get-TaskTime "MIDAGRI API $($otherEnv.ToUpper()) - ETL diario"
    Info "El ETL toma los ultimos dias del portal SISAP (MIDAGRI_ETL_DEFAULT_WINDOW_DAYS) y tarda unos minutos."
    Info "El portal publica los precios del dia por la tarde; el legado corre a las 18:00."
    if ($existingTime) { Info "La tarea de $envLabel ya corre a las $existingTime." }
    if ($otherTime) { Info "La tarea de $($otherEnv.ToUpper()) corre a las ${otherTime}: conviene no hacerlas coincidir." }
    $timeDefault = if ($EtlTime) { $EtlTime } elseif ($existingTime) { $existingTime } else { $envProfile.EtlTime }
    $answer = Ask "Hora de ejecucion diaria (HH:mm, 24 h)" $timeDefault { param($a) $a -match $timePattern } "Formato HH:mm de 24 horas, p. ej. 18:00."
    $parts = $answer -split ":"
    $EtlTime = "{0:D2}:{1}" -f [int]$parts[0], $parts[1]

    if ($Environment -eq "prd" -and $legacy.Count) {
        Warn "La tarea del script legado sigue activa: $($legacy.TaskName -join ', ')."
        Warn "El legado y la API de PRD escriben en BM_CatalogPrice: nunca deben correr los dos."
        $option = AskChoice "Que hacer con la tarea de la API?" @(
            "Registrarla DESHABILITADA; se habilita el dia del corte (recomendado)",
            "Hacer el corte ahora: deshabilitar el legado y habilitar la tarea de la API",
            "No registrar la tarea") 1
        $taskMode = @("disabled", "cutover", "none")[$option - 1]
        if ($taskMode -eq "cutover") {
            Warn "Siga el runbook del corte (specs\SPEC-price-ingestion.md). Volver atras: rehabilitar la tarea del legado."
            Ask "Escriba CORTE para confirmar" "" { param($a) $a -ceq "CORTE" } "Escriba CORTE en mayusculas, o cierre la ventana para cancelar." | Out-Null
        }
    }
}
# Si no se reprograma, una tarea ya registrada debe seguir llamando al puerto elegido.
$taskUrl = "http://localhost:$Port"
$staleTaskUrl = ""
if ($taskMode -eq "none") {
    $existingUrl = Get-TaskBaseUrl $taskName
    if ($existingUrl -and $existingUrl -ne $taskUrl) {
        $staleTaskUrl = $existingUrl
        Info "La tarea existente llama a $existingUrl; se apuntara a $taskUrl (hora y estado sin cambios)."
    }
}

# --- 8. Resumen y confirmacion ---------------------------------------------------------------------------------
Step "Resumen"
$taskText = switch ($taskMode) {
    "enabled" { "todos los dias a las $EtlTime" }
    "disabled" { "registrada a las $EtlTime, DESHABILITADA hasta el corte" }
    "cutover" { "todos los dias a las $EtlTime; se DESHABILITA el legado" }
    default { if ($staleTaskUrl) { "sin cambios de hora; la tarea existente pasa a $taskUrl" } else { "no se programa" } }
}
Info ("{0,-14} {1}" -f "Entorno", $envProfile.Label)
Info ("{0,-14} {1}" -f "Carpeta", $ProjectDir)
Info ("{0,-14} {1}" -f "Servicio", $serviceName)
Info ("{0,-14} {1}" -f "Puerto", "$Port  (URL: $publicUrl)")
Info ("{0,-14} {1}" -f "Firewall", $(if ($wantFirewall) { "abrir el puerto $Port" } else { "sin cambios" }))
Info ("{0,-14} {1}" -f "Version", $version)
Info ("{0,-14} {1}" -f "Migraciones", $(if ($runMigrations) { "si, en '$pgDatabase'" } else { "no" }))
Info ("{0,-14} {1}" -f "ETL diario", $taskText)
if ($Environment -eq "prd") {
    Ask "Se va a desplegar en PRODUCCION. Escriba PRD para continuar" $(if ($NonInteractive) { "PRD" } else { "" }) `
        { param($a) $a -ceq "PRD" } "Escriba PRD en mayusculas, o cierre la ventana para cancelar." | Out-Null
} elseif (-not (AskYesNo "Continuar?" $true)) {
    exit 1
}

# --- 9. Codigo -------------------------------------------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $ProjectDir | Out-Null
$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($service -and $service.Status -ne "Stopped") {
    Step "Deteniendo el servicio $serviceName"
    Stop-Service -Name $serviceName -Force
    $service.WaitForStatus("Stopped", (New-TimeSpan -Seconds 60))
}
if (-not $sameDir) {
    $present = @($codeItems | Where-Object { Test-Path (Join-Path $ProjectDir $_) })
    if ($present.Count) {
        $backup = Join-Path $backupsDir $stamp
        Step "Respaldando el codigo actual en $backup"
        New-Item -ItemType Directory -Force -Path $backup | Out-Null
        foreach ($item in $present) { Copy-Item (Join-Path $ProjectDir $item) (Join-Path $backup $item) -Recurse -Force }
        Get-ChildItem $backupsDir -Directory | Sort-Object Name -Descending | Select-Object -Skip $KeepBackups |
            Remove-Item -Recurse -Force
    }
    Step "Copiando el codigo nuevo en $ProjectDir"
    foreach ($item in $present) { Remove-Item (Join-Path $ProjectDir $item) -Recurse -Force }
    foreach ($item in $codeItems) {
        $from = Join-Path $source $item
        if (Test-Path $from) { Copy-Item $from (Join-Path $ProjectDir $item) -Recurse -Force }
    }
    # Archivos bajados de otra maquina: quitar la marca de Internet para que PowerShell los ejecute sin avisos.
    Get-ChildItem $ProjectDir -Recurse -File -Include *.ps1, *.cmd -ErrorAction SilentlyContinue | Unblock-File
}
if ($tempSource) { Remove-Item $tempSource -Recurse -Force -ErrorAction SilentlyContinue }

# --- 10. .env --------------------------------------------------------------------------------------------------
Step "Guardando $envFile"
Save-EnvFile $envFile (Join-Path $ProjectDir ".env.example") $updates
Protect-EnvFile $envFile
Info "Permisos: solo Administradores y SYSTEM."

# --- 11. Servicio (dependencias, migraciones, arranque) --------------------------------------------------------
$installArgs = @{ ProjectDir = $ProjectDir; Environment = $Environment; ServiceName = $serviceName; NssmPath = $nssm; Port = $Port }
if (-not $runMigrations) { $installArgs.SkipMigrations = $true }
if ($wantFirewall) { $installArgs.OpenFirewall = $true }
& (Join-Path $ProjectDir "deploy\windows\install_service.ps1") @installArgs
if ($LASTEXITCODE -ne 0) { Fail "La instalacion del servicio fallo (arriba, el detalle). La tarea del ETL no se toco." }

# --- 12. Tarea programada --------------------------------------------------------------------------------------
if ($taskMode -ne "none") {
    Step "Tarea programada '$taskName'"
    if ($taskMode -eq "cutover") {
        foreach ($task in $legacy) {
            Disable-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath | Out-Null
            Info "Tarea del legado deshabilitada: $($task.TaskName)"
        }
    }
    & (Join-Path $ProjectDir "deploy\windows\register_etl_task.ps1") -ProjectDir $ProjectDir -TaskName $taskName `
        -At $EtlTime -BaseUrl $taskUrl -AllowLegacyTask
    if ($LASTEXITCODE -ne 0) { Fail "No se pudo registrar la tarea programada." }
    if ($taskMode -eq "disabled") {
        Disable-ScheduledTask -TaskName $taskName | Out-Null
        Info "Tarea registrada DESHABILITADA. El dia del corte: Disable-ScheduledTask (legado) y Enable-ScheduledTask -TaskName '$taskName'."
    }
} elseif ($staleTaskUrl) {
    Step "Tarea programada '$taskName': nuevo puerto"
    $task = Get-ScheduledTask -TaskName $taskName
    $action = $task.Actions[0]
    $action.Arguments = ($action.Arguments -replace '\s+-BaseUrl\s+"?[^\s"]+"?', '') + " -BaseUrl $taskUrl"
    Set-ScheduledTask -TaskName $taskName -TaskPath $task.TaskPath -Action $action | Out-Null
    Info "La tarea ahora llama a $taskUrl (hora y estado sin cambios)."
}

# --- Final -----------------------------------------------------------------------------------------------------
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "   $envLabel desplegado" -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Info "API:            $publicUrl   (documentacion: $publicUrl/docs)"
Info "Salud:          Invoke-RestMethod http://localhost:$Port/health"
Info "Logs:           $ProjectDir\logs\api.log"
Info "ETL diario:     $taskText"
Info "Probar el ETL:  Start-ScheduledTask -TaskName '$taskName'  (resultado en logs\etl_trigger.log)"
if ($apiKeyGenerated) {
    Write-Host ""
    Write-Host "    MIDAGRI_API_KEY de $envLabel (cabecera X-API-Key; guardela en un lugar seguro):" -ForegroundColor Yellow
    Write-Host "    $apiKey" -ForegroundColor Yellow
} else {
    Info "API key:        MIDAGRI_API_KEY en $envFile"
}
