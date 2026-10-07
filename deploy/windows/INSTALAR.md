# Instalar MIDAGRI API en Windows Server

## 1. Requisitos (una sola vez)

- **uv**: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` (Python lo instala el asistente).
- **NSSM**: bajar de <https://nssm.cc> y dejar `nssm.exe` en el `PATH`.
- **ODBC Driver 17 for SQL Server**.
- La base de PostgreSQL del entorno creada (`midagri_prd` o `midagri_qas`).
- Salida de red a SQL Server, PostgreSQL, `sistemas.midagri.gob.pe:80` y `smtp.gmail.com:587`.

## 2. Instalar

1. Copiar `midagri-api_<versión>_<fecha>.zip` al servidor y descomprimirlo (p. ej. en `C:\Temp\`).
2. Clic derecho en **`desplegar.cmd`** → *Ejecutar como administrador*.
3. Responder el asistente:

| Pregunta | PRD | QAS |
|---|---|---|
| Entorno | PRD | QAS |
| Carpeta | `C:\ServerServices\MidagriApi\prd` | `C:\ServerServices\MidagriApi\qas` |
| Puerto | 8000 | 8001 |
| Firewall | Sí, si se consulta desde otra máquina | |
| `.env` | SQL Server, PostgreSQL y correo | |
| Migraciones | Sí | |
| Hora del ETL | 18:00 | 19:00 |
| Confirmar | Escribir `PRD` | |

En PRD, si el script legado (`run_midagri.bat`) sigue activo, elegir **opción 1**: la tarea del ETL queda
registrada pero deshabilitada hasta el día del corte.

4. Al final se muestran la URL y la **API key**: guardarla.

## 3. Verificar

```powershell
Get-Service MidagriApi-*
Invoke-RestMethod http://localhost:8000/health
Start-ScheduledTask -TaskName "MIDAGRI API PRD - ETL diario"   # probar el ETL; ver logs\etl_trigger.log
```

## Día del corte (PRD)

```powershell
Disable-ScheduledTask -TaskName "<tarea de run_midagri.bat>"
Enable-ScheduledTask -TaskName "MIDAGRI API PRD - ETL diario"
```

## Otros

- **Reconfigurar** (puerto, hora, `.env`): ejecutar `desplegar.cmd` desde la carpeta instalada.
- **Rollback**: `powershell -ExecutionPolicy Bypass -File deploy\windows\deploy_package.ps1 -Environment prd -Rollback`.
- **Logs**: `logs\api.log` (API) y `logs\etl_trigger.log` (tarea).
- Detalle completo: `deploy\windows\README.md`.
