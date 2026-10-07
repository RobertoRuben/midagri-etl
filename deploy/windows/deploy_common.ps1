<#
.SYNOPSIS
    Funciones compartidas del asistente de despliegue (deploy_package.ps1): preguntas por consola y lectura y
    escritura del .env. Se carga con dot-sourcing; no hace nada por si solo.

.NOTES
    Formato del .env: el de python-dotenv (lo lee pydantic-settings). Los valores con espacios, comillas, #, $ o
    barras invertidas se escriben entre comillas simples, escapando \ y ' con \. El archivo se guarda en UTF-8
    sin BOM.
#>

# Las preguntas leen $NonInteractive del script que carga este archivo (su parametro -NonInteractive).

function Step([string]$Message) { Write-Host ""; Write-Host "==> $Message" -ForegroundColor Cyan }
function Info([string]$Message) { Write-Host "    $Message" -ForegroundColor Gray }
function Warn([string]$Message) { Write-Host "    [AVISO] $Message" -ForegroundColor Yellow }
function Fail([string]$Message) { Write-Host "[ERROR] $Message" -ForegroundColor Red; exit 1 }

# --- Preguntas -------------------------------------------------------------------------------------------------

function Ask {
    <# Pide un valor. Enter acepta el valor por defecto. -Optional permite dejarlo vacio escribiendo "-". #>
    param(
        [string]$Question,
        [string]$Default = "",
        [scriptblock]$Validate = $null,
        [string]$Hint = "Valor obligatorio.",
        [switch]$Optional
    )
    while ($true) {
        if ($script:NonInteractive) {
            $answer = $Default
        } else {
            $suffix = if ($Default) { " [$Default]" } else { "" }
            $answer = Read-Host "  $Question$suffix"
            if (-not $answer) { $answer = $Default }
        }
        $answer = "$answer".Trim()
        if ($Optional -and ($answer -eq "-" -or -not $answer)) { return "" }
        if ($answer -and (-not $Validate -or (& $Validate $answer))) { return $answer }
        if ($script:NonInteractive) { Fail "Valor faltante o invalido para: $Question" }
        Warn $Hint
    }
}

function AskYesNo([string]$Question, [bool]$Default) {
    if ($script:NonInteractive) { return $Default }
    $suffix = if ($Default) { "[S/n]" } else { "[s/N]" }
    while ($true) {
        $answer = "$(Read-Host "  $Question $suffix")".Trim().ToLower()
        if (-not $answer) { return $Default }
        if ($answer -in @("s", "si", "y", "yes")) { return $true }
        if ($answer -in @("n", "no")) { return $false }
        Warn "Responda s o n."
    }
}

function AskSecret([string]$Question, [string]$Current) {
    <# Pide un secreto sin mostrarlo. Enter mantiene el actual, si lo hay. #>
    if ($script:NonInteractive) {
        if ($Current) { return $Current }
        Fail "Falta el valor de: $Question"
    }
    $suffix = if ($Current) { " [Enter = mantener el actual]" } else { "" }
    while ($true) {
        $secure = Read-Host "  $Question$suffix" -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
        if ($plain) { return $plain }
        if ($Current) { return $Current }
        Warn "Valor obligatorio."
    }
}

function AskChoice([string]$Question, [string[]]$Options, [int]$Default = 1) {
    <# Muestra opciones numeradas y devuelve el numero elegido (1..N). #>
    for ($i = 0; $i -lt $Options.Count; $i++) { Write-Host ("    {0}) {1}" -f ($i + 1), $Options[$i]) }
    $valid = 1..$Options.Count | ForEach-Object { "$_" }
    $defaultText = if ($Default -gt 0) { "$Default" } else { "" }   # 0 = sin valor por defecto: hay que elegir
    $answer = Ask $Question $defaultText { param($a) $a -in $valid } "Escriba un numero entre 1 y $($Options.Count)."
    return [int]$answer
}

# --- .env ------------------------------------------------------------------------------------------------------

function Test-Blank([string]$Value) {
    <# Vacio o marcador de .env.example (<host>, <usuario>...). #>
    return (-not $Value) -or ($Value.Trim() -match '^<.*>$')
}

function ConvertFrom-EnvValue([string]$Raw) {
    $value = $Raw.Trim()
    if ($value -match "^'(.*)'$") { return ($Matches[1] -replace "\\'", "'") -replace '\\\\', '\' }
    if ($value -match '^"(.*)"$') { return ($Matches[1] -replace '\\"', '"') -replace '\\\\', '\' }
    return ($value -replace '\s+#.*$', '')
}

function ConvertTo-EnvValue([string]$Value) {
    if ($Value -match '^[A-Za-z0-9_.,:/@+=\-]+$') { return $Value }
    return "'" + (($Value -replace '\\', '\\') -replace "'", "\'") + "'"
}

function Read-EnvFile([string]$Path) {
    $values = @{}
    if (Test-Path $Path) {
        foreach ($line in [IO.File]::ReadAllLines($Path)) {
            if ($line -match '^\s*([A-Za-z0-9_]+)\s*=(.*)$') { $values[$Matches[1]] = ConvertFrom-EnvValue $Matches[2] }
        }
    }
    return $values
}

function Save-EnvFile([string]$Path, [string]$TemplatePath, [hashtable]$Updates) {
    <# Actualiza las claves en su linea (o en la comentada de la plantilla) y conserva el resto del archivo. #>
    $source = if (Test-Path $Path) { $Path } else { $TemplatePath }
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.AddRange([string[]][IO.File]::ReadAllLines($source))
    foreach ($key in @($Updates.Keys)) {
        $newLine = "$key=$(ConvertTo-EnvValue ([string]$Updates[$key]))"
        $index = -1
        foreach ($pattern in @("^\s*$key\s*=", "^\s*#\s*$key\s*=")) {
            for ($i = 0; $i -lt $lines.Count -and $index -lt 0; $i++) {
                if ($lines[$i] -match $pattern) { $index = $i }
            }
        }
        if ($index -ge 0) { $lines[$index] = $newLine } else { $lines.Add($newLine) }
    }
    [IO.File]::WriteAllLines($Path, [string[]]$lines, (New-Object Text.UTF8Encoding($false)))
}

function Protect-EnvFile([string]$Path) {
    <# Solo Administradores y SYSTEM (el servicio y la tarea corren como SYSTEM): el .env tiene contrasenas. #>
    icacls $Path /inheritance:r /grant:r "*S-1-5-32-544:(F)" "*S-1-5-18:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { Warn "No se pudieron restringir los permisos de $Path." }
}

function New-ApiKey {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

# --- Servidor --------------------------------------------------------------------------------------------------

function Get-ServicePort([string]$ServiceName) {
    <# Puerto configurado en NSSM (registro del servicio), o 0 si no existe. #>
    $key = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName\Parameters"
    $params = (Get-ItemProperty -Path $key -Name AppParameters -ErrorAction SilentlyContinue).AppParameters
    if ($params -match '--port\s+(\d+)') { return [int]$Matches[1] }
    return 0
}

function Get-ListeningPorts([int]$From, [int]$To) {
    <# Puertos TCP en escucha del rango, con el proceso dueno. #>
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -ge $From -and $_.LocalPort -le $To } |
        Sort-Object LocalPort -Unique |
        ForEach-Object {
            $process = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
            [pscustomobject]@{ Port = [int]$_.LocalPort; Owner = if ($process) { $process.ProcessName } else { "PID $($_.OwningProcess)" } }
        }
}

function Get-TaskTime([string]$TaskName) {
    <# Hora (HH:mm) del primer disparador de la tarea, o "" si no existe. #>
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task -or -not $task.Triggers -or -not $task.Triggers[0].StartBoundary) { return "" }
    return ([datetime]$task.Triggers[0].StartBoundary).ToString("HH:mm")
}

function Get-TaskBaseUrl([string]$TaskName) {
    <# URL (-BaseUrl) a la que llama la tarea del ETL, o "" si no existe. #>
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) { return "" }
    $match = [regex]::Match("$($task.Actions[0].Arguments)", '-BaseUrl\s+"?([^\s"]+)')
    if ($match.Success) { return $match.Groups[1].Value }
    return "http://localhost:8000"   # sin -BaseUrl, trigger_etl.ps1 usa su valor por defecto
}
