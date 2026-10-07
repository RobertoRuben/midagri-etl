from __future__ import annotations
import pyodbc
import pandas as pd
from typing import Dict
from system.core.env import SETTINGS
from system.core.logging import LOGGER
from system.utils.decimal import parse_number


# ============================================================
# Conexión
# ============================================================

def _conn_str() -> str:
    return (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={SETTINGS.sql_server};"
        f"DATABASE={SETTINGS.sql_database};"
        f"UID={SETTINGS.sql_user};"
        f"PWD={SETTINGS.sql_pwd};"
        "TrustServerCertificate=yes;"
    )

def get_connection():
    return pyodbc.connect(_conn_str())


# ============================================================
# Lecturas auxiliares (usadas por tu módulo system/merge/merge.py)
# ============================================================

def fetch_catalog_products(conn) -> pd.DataFrame:
    """
    Devuelve id, code, name de BM_Catalog donde type='0001'.
    Útil para preparar el merge en Python (join por name/code).
    """
    sql = """
    SELECT id, code, name
    FROM dbo.BM_Catalog
    WHERE type='0001' and active=1
    """
    return pd.read_sql(sql, conn)

def fetch_ubigeo(conn) -> pd.DataFrame:
    """
    Devuelve id, inei, department de BM_Ubigeo (nivel departamento).
    Útil para preparar el merge en Python (join por department).
    """
    sql = "SELECT id, inei, department, province,district FROM dbo.BM_Ubigeo"
    return pd.read_sql(sql, conn)

# ============================================================
# Upsert masivo (sin tablas permanentes): ##TmpPrices (global)
# ============================================================

def merge_prices(conn, df_prices: pd.DataFrame, price_type: str = "Mayorista", registered_by: str = "etl-sisap"):
    """
    Upsert en bloque a dbo.BM_CatalogPrice usando tabla temporal GLOBAL ##TmpPrices.
    Requisitos del df_prices (YA ENRIQUECIDO en Python):
      columnas: idCatalog, idUbigeo, date, unitOfMeasure, equivalence, min, mean, max, type, registeredBy

    - NO crea tablas permanentes.
    - Hace UPDATE de coincidencias y luego INSERT de faltantes.
    - 'equivalence' se maneja como NVARCHAR(50) (texto), tal como está en tu tabla.

    Sugerido: tener un índice en destino para la llave lógica:
      CREATE INDEX IX_BM_CatalogPrice_Key
      ON dbo.BM_CatalogPrice (idCatalog, [date], unitOfMeasure, [type])
      INCLUDE (min, mean, max, equivalence, registeredBy);
    """
    if df_prices is None or df_prices.empty:
        LOGGER.warning("No hay datos para insertar.")
        return

    # Normalización ligera (seguridad): solo numéricos
    df = df_prices.copy()
    for c in ("min", "mean", "max"):
        if c in df.columns:
            df[c] = df[c].apply(parse_number)

    # Claves mínimas necesarias
    if "type" not in df.columns:
        df["type"] = price_type or "Mayorista"
    if "registeredBy" not in df.columns:
        df["registeredBy"] = registered_by or "etl-sisap"

    req = ["idCatalog", "date", "type"]
    df = df.dropna(subset=[c for c in req if c in df.columns])
    if df.empty:
        LOGGER.warning("No hay filas con claves mínimas (idCatalog/date/type).")
        return

    # Armar filas para el insert a la temp global
    rows = []
    for _, r in df.iterrows():
        rows.append((
            str(r.get("type") or price_type or "Mayorista"),
            int(r["idCatalog"]),
            int(r["idUbigeo"]) if pd.notna(r.get("idUbigeo")) else None,
            r["date"],  # debe ser tipo date/datetime.date
            str(r.get("unitOfMeasure") or ""),
            str(r.get("equivalence") or ""),  # NVARCHAR(50) en destino
            r.get("min"),
            r.get("mean"),
            r.get("max"),
            str(r.get("registeredBy") or registered_by or "etl-sisap"),
        ))

    if not rows:
        LOGGER.warning("No hubo filas válidas para staging.")
        return

    PRICE_TABLE = getattr(SETTINGS, "catalog_prices_table", "dbo.BM_CatalogPrice")
    TMP = "##TmpPrices"  # global temp table

    cursor = conn.cursor()
    cursor.execute("SET LOCK_TIMEOUT 10000;")
    cursor.execute("SET NOCOUNT ON;")
    cursor.execute("SET XACT_ABORT ON;")

    # 1) Crear temp global (si ya existe por alguna corrida previa, la recreamos)
    cursor.execute(f"""
        IF OBJECT_ID('tempdb..{TMP}') IS NOT NULL DROP TABLE {TMP};
        CREATE TABLE {TMP}(
            [type]          NVARCHAR(50)  NOT NULL,
            [idCatalog]     INT           NOT NULL,
            [idUbigeo]      INT           NULL,
            [date]          DATE          NOT NULL,
            [unitOfMeasure] NVARCHAR(50)  NULL,
            [equivalence]   NVARCHAR(50)  NULL,
            [min]           DECIMAL(18,4) NULL,
            [mean]          DECIMAL(18,4) NULL,
            [max]           DECIMAL(18,4) NULL,
            [registeredBy]  NVARCHAR(20)  NULL
        );
        CREATE CLUSTERED INDEX IX_{TMP}_Key ON {TMP}(idCatalog, [date], unitOfMeasure, [type]);
    """)

    # 2) Bulk insert a la temp global
    #    Importante: con temp global + fast_executemany no tendrás el error 42S02
    cursor.fast_executemany = True
    cursor.executemany(f"""
        INSERT INTO {TMP}
        ([type],[idCatalog],[idUbigeo],[date],[unitOfMeasure],[equivalence],[min],[mean],[max],[registeredBy])
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, rows)
    conn.commit()

    # 3) UPDATE de coincidencias en destino (llave lógica)
    update_sql = f"""
    UPDATE T
       SET T.min          = S.min,
           T.mean         = S.mean,
           T.max          = S.max,
           T.equivalence  = S.equivalence,
           T.registeredBy = S.registeredBy
    FROM {PRICE_TABLE} AS T WITH (ROWLOCK)
    JOIN {TMP}         AS S
      ON T.idCatalog = S.idCatalog
     AND T.date      = S.date
     AND ISNULL(T.unitOfMeasure,'') = ISNULL(S.unitOfMeasure,'')
     AND ISNULL(T.type,'')          = ISNULL(S.type,'');
    """
    cursor.execute(update_sql)
    conn.commit()

    # 4) INSERT de faltantes
    insert_sql = f"""
    INSERT INTO {PRICE_TABLE}
        (type, idCatalog, idUbigeo, date, unitOfMeasure, equivalence, min, mean, max, registeredBy)
    SELECT S.type, S.idCatalog, S.idUbigeo, S.date, S.unitOfMeasure, S.equivalence, S.min, S.mean, S.max, S.registeredBy
    FROM {TMP} AS S
    WHERE NOT EXISTS (
        SELECT 1
        FROM {PRICE_TABLE} AS T WITH (NOLOCK)
        WHERE T.idCatalog = S.idCatalog
          AND T.date      = S.date
          AND ISNULL(T.unitOfMeasure,'') = ISNULL(S.unitOfMeasure,'')
          AND ISNULL(T.type,'')          = ISNULL(S.type,'')
    );
    """
    cursor.execute(insert_sql)
    conn.commit()

    # 5) Limpieza de la temp global (opcional)
    cursor.execute(f"DROP TABLE {TMP};")
    conn.commit()

    LOGGER.info(f"Upsert completado: {len(rows)} filas (##TmpPrices + UPDATE/INSERT).")

