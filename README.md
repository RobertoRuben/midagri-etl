# MIDAGRI ETL

API que descarga los precios del portal **SISAP** (MIDAGRI) y los carga por mercado en SQL Server (`BDFARMEX`).
Registra cada ejecución con su log, avisa por correo y reporta los productos del portal que faltan en el catálogo.

## Stack

Python 3.14 · FastAPI · Polars · SQLAlchemy async (SQL Server con `aioodbc`, PostgreSQL con `asyncpg`) · Alembic · uv.

| Base | Uso |
|---|---|
| SQL Server (`BDFARMEX`; QAS: `BDFarmex_Agri`) | Negocio: mercados, catálogo y precios (`BM_*`) |
| PostgreSQL (`midagri_*`) | Propio de la API: ejecuciones, logs, correos y faltantes |

## Estructura

```
src/app/                API (main.py, modules/common y modules/midagri)
alembic/                migraciones de PostgreSQL
sql/                    scripts de SQL Server con su rollback (se aplican por runbook)
deploy/windows/         asistente de despliegue en Windows Server (ver INSTALAR.md)
system/, run.py         script legado; se retira tras el corte
```

## Desarrollo

```powershell
uv sync                                   # dependencias
copy .env.example .env                    # y completar valores
uv run alembic upgrade head               # tablas de PostgreSQL
uv run fastapi dev                        # http://localhost:8000/docs
```

Requiere **ODBC Driver 17 for SQL Server**. La configuración usa variables `MIDAGRI_*` (ver `.env.example`).

## Endpoints

Todos piden la cabecera `X-API-Key`, salvo `/health`.

| Método | Ruta | Qué hace |
|---|---|---|
| `POST` | `/etl/runs` | Lanza el ETL en segundo plano. Cuerpo opcional: `date_from`, `date_to`, `market_codes`, `dry_run`. Sin cuerpo: mercados activos, últimos 5 días. |
| `GET` | `/etl/runs`, `/etl/runs/{id}` | Historial y detalle por mercado |
| `GET` | `/etl/runs/{id}/logs` | Log de la ejecución (visible mientras corre) |
| `GET` | `/catalog/gaps`, `/catalog/gaps/excel` | Productos del portal sin catálogo (JSON o Excel) |
| `POST` | `/catalog/gaps/refresh` | Recalcula los faltantes |
| `POST`/`GET` | `/catalog/registrations` | Alta de productos faltantes en el catálogo e historial |
| `GET` | `/markets` | Mercados configurados |
| `GET`/`POST`/`PATCH` | `/notifications/recipients` | Destinatarios de correo |
| `GET` | `/health` | Estado de SQL Server, PostgreSQL y SISAP |

Ejemplo:

```powershell
curl -X POST http://localhost:8000/etl/runs -H "X-API-Key: <clave>" -H "Content-Type: application/json" -d '{\"dry_run\": true}'
```

## Calidad

```powershell
uv run ruff check .
uv run ty check
uv run pytest                 # unitarias y de API
uv run pytest -m db           # integración contra las bases del .env
uv run pytest -m network      # contra el portal SISAP real
```

## Despliegue

Servicio de Windows (NSSM) más una tarea programada que llama a `POST /etl/runs` cada día.

```powershell
powershell -ExecutionPolicy Bypass -File deploy\windows\build_package.ps1   # genera dist\*.zip
```

En el servidor: descomprimir el zip y ejecutar `desplegar.cmd` como administrador. El asistente pregunta entorno,
puerto, `.env` y hora del ETL. Guía corta: [`deploy/windows/INSTALAR.md`](deploy/windows/INSTALAR.md);
detalle: [`deploy/windows/README.md`](deploy/windows/README.md).

## Legado

`system/` y `run.py` (lanzado por `run_midagri.bat`) son el script anterior, que sigue cargando producción hasta el
corte. El legado y la API **no deben correr los dos** contra `BM_CatalogPrice`.
