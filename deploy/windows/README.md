# Despliegue de la API en Windows Server

La API corre como **servicio de Windows** (NSSM) con `python -m fastapi run`. Una **tarea programada** la llama
todos los días (`POST /etl/runs`). Ver `specs/SPEC-api.md` (Despliegue).

Cada entorno es independiente y pueden convivir en el mismo servidor. Estos son los valores por defecto; el asistente los pregunta:

| Entorno | Carpeta | Servicio | Puerto | ETL | SQL Server / PostgreSQL |
|---|---|---|---|---|---|
| QAS | `C:\ServerServices\MidagriApi\qas` | `MidagriApi-QAS` | 8001 | 19:00 | `BDFarmex_Agri` / `midagri_qas` |
| PRD | `C:\ServerServices\MidagriApi\prd` | `MidagriApi-PRD` | 8000 | 18:00 | `BDFARMEX` / `midagri_prd` |

El legado (`C:\ServerServices\Midagri`, `run_midagri.bat`) no se toca: el asistente se niega a instalar en su carpeta.

## Requisitos del servidor (una sola vez)

| Qué | Cómo |
|---|---|
| uv | `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"`. Python 3.14 lo instala el script. |
| NSSM | Descargar de <https://nssm.cc> y dejar `nssm.exe` en el `PATH` (si no, el asistente pide la ruta). |
| ODBC Driver 17 for SQL Server | Instalador de Microsoft (el legado ya lo usa). |
| Bases | La base de PostgreSQL del entorno debe **existir** (las migraciones crean las tablas, no la base). |
| Red de salida | SQL Server, PostgreSQL, `sistemas.midagri.gob.pe:80` (SISAP) y `smtp.gmail.com:587` (correo). |

## 1. En la máquina de desarrollo: armar el paquete

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\build_package.ps1
```

Verifica `uv.lock`, `ruff` y `pytest` (se omiten con `-SkipChecks`) y genera `dist\midagri-api_<versión>_<fecha>.zip`:
el código, `.env.example`, `deploy\windows\`, `VERSION.txt` y `desplegar.cmd` en la raíz. **No** lleva `.env`,
tests ni el script legado.

## 2. En el servidor: ejecutar el asistente

1. Copiar el zip y descomprimirlo (p. ej. en `C:\Temp\midagri-api_0.1.0_20260930_1631`).
2. Doble clic en **`desplegar.cmd`** (pide permisos de administrador).

El asistente pregunta, en orden:

| Paso | Qué pregunta | Ayuda que muestra |
|---|---|---|
| Entorno | QAS o PRD | Bases de cada uno |
| Carpeta | Dónde instalar | Valor por defecto del entorno |
| Puerto | Puerto HTTP | Puertos ocupados (8000–8099), el que ya usa el servicio y el del otro entorno. Recomienda uno libre y no acepta uno ocupado. |
| Firewall | Abrir el puerto | Regla `MIDAGRI API <ENTORNO>` |
| `.env` | SQL Server, PostgreSQL, correo y alta automática | Si ya existe, lo muestra (contraseñas ocultas) y pregunta si editarlo. Si es de otro entorno, obliga a revisarlo y propone las bases del entorno elegido. Genera `MIDAGRI_API_KEY` si falta. |
| Migraciones | `alembic upgrade head` | Sobre qué base se aplican |
| ETL | Si programarlo y a qué hora (HH:mm) | Hora actual de la tarea y la del otro entorno, para que no coincidan |
| Resumen | Confirmación | En PRD hay que escribir `PRD` |

Después hace, sin más preguntas:
1. Detiene el servicio y respalda el código actual en `backups\<fecha>` (quedan los últimos 5).
2. Copia el código nuevo. **Conserva** `.env`, `logs\` y `.venv\`.
3. Guarda el `.env` en UTF-8, con permisos solo para Administradores y SYSTEM.
4. `install_service.ps1`:
   - instala Python y las dependencias (`uv sync --frozen --no-dev`);
   - valida el `.env` (si falta algo, dice qué campo);
   - migra PostgreSQL y muestra la revisión antes y después;
   - registra el servicio (arranque automático, reinicio si se cae, logs rotados en `logs\api.log`);
   - lo inicia y muestra el `/health` de SQL Server, PostgreSQL y SISAP.
5. Registra la tarea `MIDAGRI API <ENTORNO> - ETL diario` a la hora elegida.
6. Muestra la URL, la API key (si se generó una nueva; guárdela) y cómo probar el ETL.

**Legado en PRD:** si la tarea de `run_midagri.bat` sigue activa, el asistente ofrece tres opciones:
1. Registrar la tarea de la API **deshabilitada**, para habilitarla el día del corte (recomendado).
2. Hacer el corte: deshabilitar el legado y habilitar la API. Hay que escribir `CORTE` para confirmar.
3. No registrar la tarea.

Nunca corren los dos. En QAS no se pregunta, porque la API de QAS escribe en `BDFarmex_Agri`.

**Reconfigurar** (cambiar puerto, hora o `.env`): ejecutar `desplegar.cmd` desde la carpeta instalada. No copia código.
Si se cambia el puerto y no se reprograma el ETL, la tarea existente se apunta al puerto nuevo (conserva hora y estado).

**Sin preguntas** (el `.env` del entorno ya completo):

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\deploy_package.ps1 -Environment qas -Port 8001 -EtlTime 19:00 -OpenFirewall -NonInteractive
```

**Rollback** al respaldo anterior (no revierte migraciones de PostgreSQL):

```powershell
powershell -ExecutionPolicy Bypass -File C:\ServerServices\MidagriApi\qas\deploy\windows\deploy_package.ps1 -Environment qas -Rollback
```

Los scripts de SQL Server (`sql/`) **no** se aplican aquí: van por el runbook, con respaldo previo.

## Scripts

| Script | Dónde | Para qué |
|---|---|---|
| `build_package.ps1` | Desarrollo | Verifica y arma el zip |
| `desplegar.cmd` | Servidor | Pide administrador y abre el asistente |
| `deploy_package.ps1` | Servidor | Asistente: preguntas, respaldo, copia, `.env`, servicio y tarea |
| `deploy_common.ps1` | — | Funciones del asistente (preguntas y `.env`) |
| `install_service.ps1` | Servidor | Dependencias, validación del `.env`, migraciones, servicio NSSM y `/health` |
| `register_etl_task.ps1` | Servidor | Tarea programada diaria |
| `trigger_etl.ps1` | Servidor | Lo ejecuta la tarea: `POST /etl/runs {"trigger":"cron"}` con la key del `.env`; un 409 no se reintenta |
| `uninstall_service.ps1` | Servidor | Quita servicio, tarea y regla de firewall de un entorno |

## Operación

| Acción | Comando |
|---|---|
| Estado | `Get-Service MidagriApi-*` · `Invoke-RestMethod http://localhost:8001/health` |
| Detener / iniciar | `Stop-Service MidagriApi-QAS` · `Start-Service MidagriApi-QAS` |
| Logs de la API | `Get-Content C:\ServerServices\MidagriApi\qas\logs\api.log -Tail 100 -Wait` |
| Probar el ETL ahora | `Start-ScheduledTask -TaskName "MIDAGRI API QAS - ETL diario"` (resultado en `logs\etl_trigger.log`) |
| Log de una ejecución | `GET /etl/runs/{id}/logs` (con `X-API-Key`) |
| Versión instalada | `Get-Content C:\ServerServices\MidagriApi\qas\VERSION.txt` |
| Quitar un entorno | `deploy\windows\uninstall_service.ps1 -Environment qas -RemoveTask -RemoveFirewallRule` (no borra carpeta, `.env` ni logs) |
| Volver al legado (PRD) | `Disable-ScheduledTask "MIDAGRI API PRD - ETL diario"` y rehabilitar la tarea de `run_midagri.bat` |

Si se detiene el servicio con una ejecución en curso, esa ejecución queda `failed` al volver a arrancar.
