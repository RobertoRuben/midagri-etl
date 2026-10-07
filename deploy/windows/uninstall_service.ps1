<#
.SYNOPSIS
    Quita el servicio de la API MIDAGRI de un entorno y, opcionalmente, su tarea programada y su regla de firewall.

.DESCRIPTION
    No borra la carpeta del entorno, el .env, los logs ni las bases de datos. No toca la tarea del script legado:
    si se vuelve al legado, rehabilitela a mano (Enable-ScheduledTask).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File deploy\windows\uninstall_service.ps1 -Environment qas -RemoveTask -RemoveFirewallRule
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("qas", "prd")]
    [string]$Environment,
    [string]$NssmPath = "nssm.exe",
    [switch]$RemoveTask,
    [switch]$RemoveFirewallRule
)

$ErrorActionPreference = "Stop"
$envLabel = $Environment.ToUpper()
$serviceName = "MidagriApi-$envLabel"
$taskName = "MIDAGRI API $envLabel - ETL diario"
$firewallRule = "MIDAGRI API $envLabel"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "[ERROR] Ejecute PowerShell como administrador." -ForegroundColor Red
    exit 1
}

# Primero la tarea: que no dispare contra un servicio que ya no existe.
if ($RemoveTask -and (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue)) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "[OK] Tarea '$taskName' eliminada."
}

$service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($service) {
    if ($service.Status -ne "Stopped") {
        Stop-Service -Name $serviceName -Force
        $service.WaitForStatus("Stopped", (New-TimeSpan -Seconds 60))
    }
    $nssm = (Get-Command $NssmPath -ErrorAction SilentlyContinue).Source
    if ($nssm) { & $nssm remove $serviceName confirm } else { sc.exe delete $serviceName }
    if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] No se pudo quitar el servicio $serviceName." -ForegroundColor Red; exit 1 }
    Write-Host "[OK] Servicio $serviceName eliminado."
} else {
    Write-Host "[INFO] El servicio $serviceName no existe."
}

if ($RemoveFirewallRule -and (Get-NetFirewallRule -DisplayName $firewallRule -ErrorAction SilentlyContinue)) {
    Remove-NetFirewallRule -DisplayName $firewallRule
    Write-Host "[OK] Regla de firewall '$firewallRule' eliminada."
}
exit 0
