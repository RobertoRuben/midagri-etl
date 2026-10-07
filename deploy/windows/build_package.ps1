<#
.SYNOPSIS
    Arma el paquete .zip de la API para subirlo al servidor Windows. Se corre en la maquina de desarrollo.

.DESCRIPTION
    1. Verifica el codigo: uv.lock al dia, ruff y pytest (sin -m db ni -m network). Se omite con -SkipChecks.
    2. Copia solo lo que la API necesita: src\, alembic\, alembic.ini, pyproject.toml, uv.lock, .python-version,
       README.md, .env.example y deploy\windows\. Sin __pycache__, .venv, .env, tests ni el script legado.
    3. Escribe VERSION.txt (version de pyproject, fecha y equipo) y genera dist\midagri-api_<version>_<fecha>.zip.

    En el servidor, el paquete se instala con deploy_package.ps1 (ver deploy\windows\README.md).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File deploy\windows\build_package.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File deploy\windows\build_package.ps1 -SkipChecks -OutputDir C:\Temp
#>
[CmdletBinding()]
param(
    [string]$ProjectDir = "",   # por defecto, la carpeta del proyecto (dos niveles arriba de este script)
    [string]$OutputDir = "",    # por defecto, <proyecto>\dist
    [switch]$SkipChecks
)

$ErrorActionPreference = "Stop"
# En Windows PowerShell 5.1, $PSScriptRoot esta vacio en los valores por defecto de param().
if (-not $ProjectDir) { $ProjectDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path }
if (-not $OutputDir) { $OutputDir = Join-Path $ProjectDir "dist" }

function Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Fail([string]$Message) { Write-Host "[ERROR] $Message" -ForegroundColor Red; exit 1 }
function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { Fail "Fallo: $Exe $($Arguments -join ' ') (codigo $LASTEXITCODE)" }
}

# Lo que viaja al servidor. Carpetas se copian sin __pycache__.
$items = @("src", "alembic", "alembic.ini", "pyproject.toml", "uv.lock", ".python-version", "README.md",
    ".env.example", "deploy\windows")

Set-Location $ProjectDir
foreach ($item in $items) {
    if (-not (Test-Path $item)) { Fail "Falta $item en $ProjectDir" }
}

# --- 1. Verificaciones ------------------------------------------------------------------------------------------
if ($SkipChecks) {
    Write-Warning "Verificaciones omitidas (-SkipChecks)."
} else {
    $uv = (Get-Command uv.exe -ErrorAction SilentlyContinue).Source
    if (-not $uv) { Fail "No se encontro uv (o use -SkipChecks)." }
    Step "uv.lock al dia con pyproject.toml"
    Invoke-Checked $uv @("lock", "--check")
    Step "ruff check"
    Invoke-Checked $uv @("run", "ruff", "check", ".")
    Step "pytest (unitarias y de API)"
    Invoke-Checked $uv @("run", "pytest", "-q")
}

# --- 2. Copia a una carpeta temporal ----------------------------------------------------------------------------
$version = (Select-String -Path "pyproject.toml" -Pattern '^version\s*=\s*"([^"]+)"' | Select-Object -First 1).Matches[0].Groups[1].Value
$stamp = Get-Date -Format "yyyyMMdd_HHmm"
$name = "midagri-api_${version}_$stamp"
$staging = Join-Path ([IO.Path]::GetTempPath()) $name
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Force -Path $staging | Out-Null

Step "Copiando archivos del paquete"
foreach ($item in $items) {
    $target = Join-Path $staging $item
    if (Test-Path $item -PathType Container) {
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        # robocopy: /E subcarpetas, /XD excluye cache; codigos < 8 son exito.
        robocopy $item $target /E /XD __pycache__ .pytest_cache /XF *.pyc /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { Fail "robocopy fallo copiando $item (codigo $LASTEXITCODE)" }
    } else {
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item $item $target -Force
    }
}
if (Test-Path (Join-Path $staging ".env")) { Fail "El paquete no debe llevar .env" }
# Lanzador del asistente en la raiz: en el servidor basta con descomprimir y ejecutarlo.
Copy-Item "deploy\windows\desplegar.cmd" (Join-Path $staging "desplegar.cmd") -Force

@(
    "midagri-api $version",
    "Generado: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "Equipo: $env:COMPUTERNAME ($env:USERNAME)",
    "Verificaciones: $(if ($SkipChecks) { 'omitidas' } else { 'uv lock --check, ruff, pytest' })"
) | Set-Content -Path (Join-Path $staging "VERSION.txt") -Encoding UTF8

# --- 3. Zip -----------------------------------------------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$zip = Join-Path $OutputDir "$name.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Step "Comprimiendo"
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::CreateFromDirectory($staging, $zip, [IO.Compression.CompressionLevel]::Optimal, $false)
Remove-Item $staging -Recurse -Force

$sizeKb = [math]::Round((Get-Item $zip).Length / 1KB)
Write-Host ""
Write-Host "[OK] Paquete: $zip ($sizeKb KB)" -ForegroundColor Green
Write-Host "     En el servidor: copiar el zip, descomprimirlo (p. ej. en C:\Temp\$name) y ejecutar"
Write-Host "     desplegar.cmd como administrador. El asistente pregunta entorno (QAS/PRD), puerto, .env y hora del ETL."
