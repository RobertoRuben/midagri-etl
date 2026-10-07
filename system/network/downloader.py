from __future__ import annotations
import io
import requests
import pandas as pd
import numpy as np
import warnings
from typing import List
from system.core.logging import LOGGER

# Suprimir warnings específicos de pandas sobre cambios futuros en ffill
warnings.filterwarnings('ignore', category=FutureWarning, message='.*Downcasting object dtype arrays.*')

SISAP_URL = "http://sistemas.midagri.gob.pe/sisap/portal2/ciudades/resumenes/filtrar"
# SISAP_URL = "http://200.115.22.230/sisap/portal2/ciudades/resumenes/filtrar"
HEADERS_ROWS = 4  # cabeceras apiladas


def _build_params(product_codes: List[str], fecha: str, desde: str, hasta: str,
                  periodicidad: str = "intervalo"):
    """Parámetros del endpoint; acepta un LOTE de códigos en 'productos[]'."""
    return {
        "region": "*",
        "variables[]": ["may_precio_min", "may_precio_prom", "may_precio_max"],
        "fecha": fecha,
        "desde": desde,
        "hasta": hasta,
        "anios[]": fecha[-4:],        # 'dd/mm/YYYY' -> YYYY
        "meses[]": fecha[3:5],        # 'dd/mm/YYYY' -> mm
        "productos[]": product_codes, # <-- lote completo
        "periodicidad": periodicidad,   # "intervalo" | "dia"
        "__ajax_carga_final": "consulta",
        "ajax": "true",
    }


def _read_first_table(content: bytes) -> pd.DataFrame:
    """Lee SOLO la primera tabla del HTML. Si no hay, DF vacío (no rompe)."""
    try:
        tables = pd.read_html(io.BytesIO(content), header=None)
        if not tables:
            return pd.DataFrame()
        return tables[0]
    except ValueError:
        return pd.DataFrame()
    except Exception as e:
        LOGGER.error(f"read_html fallo: {e}")
        return pd.DataFrame()


def _to_float_like(x: str):
    """Heurística por-valor para decimales."""
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    s = s.replace("\xa0", "").replace(" ", "")
    has_comma = "," in s
    has_dot = "." in s
    try:
        if has_comma and has_dot:
            s = s.replace(".", "").replace(",", ".")
        elif has_comma and not has_dot:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        s2 = str(x).replace("\xa0", "").replace(" ", "")
        s2 = pd.Series([s2]).str.replace(r"[^\d,.\-]", "", regex=True).iloc[0]
        s2 = s2.replace(".", "").replace(",", ".")
        try:
            return float(s2)
        except Exception:
            return None


def _clean_number_series(s: pd.Series) -> pd.Series:
    if s is None:
        return s
    return s.apply(_to_float_like)


def _clean_equivalence_series(s: pd.Series) -> pd.Series:
    return _clean_number_series(s)


def _finalize_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Quita filas sin ningún precio y agrupa para dejar UNA fila por clave:
      producto_name + date + department (+ unitOfMeasure + equivalence)
    Agregación de precios: MAX (consolida valores repetidos por clave).
    """
    if df is None or df.empty:
        return pd.DataFrame()

    price_cols = [c for c in ("min", "mean", "max") if c in df.columns]
    if price_cols:
        df = df.dropna(subset=price_cols, how="all")
    if df.empty:
        return df

    key_cols = [c for c in ("producto_name", "date", "department", "unitOfMeasure", "equivalence") if c in df.columns]
    if not key_cols:
        return df.reset_index(drop=True)

    agg = {c: "max" for c in price_cols}
    grouped = (
        df.groupby(key_cols, dropna=False, as_index=False)
          .agg(agg)
          .sort_values(key_cols)
          .reset_index(drop=True)
    )
    return grouped


def _detect_mode_and_structure(df: pd.DataFrame) -> tuple[bool, str]:
    """
    Detecta si es modo intervalo o día único.
    Retorna: (es_intervalo, primera_columna_nombre)
    """
    if df is None or df.empty or len(df) < HEADERS_ROWS:
        return False, ""
    
    # Examinar la primera columna de datos para determinar el modo
    first_col_name = str(df.iloc[0, 0]).strip().lower()
    
    # Revisar algunas filas de datos de la primera columna
    sample_values = []
    for i in range(HEADERS_ROWS, min(HEADERS_ROWS + 5, len(df))):
        if i < len(df):
            val = str(df.iloc[i, 0]).strip()
            if val and val != "nan":
                sample_values.append(val)
    
    # Si encontramos fechas en formato dd/mm/yyyy, es modo intervalo
    is_interval = False
    for val in sample_values:
        if "/" in val and len(val.split("/")) == 3:
            try:
                pd.to_datetime(val, format="%d/%m/%Y", errors="raise")
                is_interval = True
                break
            except:
                continue
    
    return is_interval, first_col_name


def _extract_departments_from_headers(df: pd.DataFrame, is_interval: bool) -> dict:
    """
    Extrae departamentos y mapea qué columnas pertenecen a cada uno.
    Retorna un dict {col_index: department_name}
    """
    if df is None or df.empty:
        return {}

    import pandas as pd  # por si no está en el scope

    if is_interval:
        # Fila 0: 'Fecha' + departamentos con colspan -> ffill por columna
        header0 = df.iloc[0].astype(str).str.replace("\xa0", " ").str.strip()
        header0 = header0.mask((header0 == "") | (header0.str.lower() == "nan")).ffill()
        # Columna 0 es 'Fecha' en intervalo
        return {i: dept for i, dept in enumerate(header0) if i > 0}
    else:
        # Día único: fila 1 -> ffill por columna
        header1 = df.iloc[1].astype(str).str.replace("\xa0", " ").str.strip()
        header1 = header1.mask((header1 == "") | (header1.str.lower() == "nan")).ffill()
        # Columna 0 suele ser 'Productos' en día único (ignorar)
        return {i: dept for i, dept in enumerate(header1) if i > 0 and header1[i].lower() != "productos"}


def _parse_html_to_long(df: pd.DataFrame, fecha_consulta: str) -> pd.DataFrame:
    """
    Parser robusto para ambas modalidades.
    - En 'intervalo': primera col es Fecha, y hay 4 filas de header:
        row0=Departamento (con colspan), row1=Producto (por bloque),
        row2=Unidad/Equiv/Mayorista, row3=Precio min/prom/max.
      Se detecta producto **por columna** usando row1 del mismo índice,
      y se buscan las columnas de Unidad/Equiv que comparten (Departamento, Producto).
    - En 'dia': primera col es Producto y no hay columna de Fecha (se usa 'fecha_consulta').
    Devuelve columnas: ['producto_name','date','department','unitOfMeasure','equivalence','min','mean','max']
    """
    if df is None or df.empty:
        return pd.DataFrame()

    # Detectar modo y estructura
    is_interval, _ = _detect_mode_and_structure(df)

    # Cuerpo de datos sin headers
    body = df.iloc[HEADERS_ROWS:].copy().reset_index(drop=True)

    # Preparar encabezados normalizados (ffill por fila)
    # Row 0 -> Departamento (excepto col 0 que es 'Fecha' en intervalo)
    h0 = df.iloc[0].astype(str).str.replace("\xa0", " ").str.strip()
    h0 = h0.mask((h0 == "") | (h0.str.lower() == "nan")).ffill()

    # Row 1 -> Producto (por bloque); ffill para cubrir celdas vacías dentro del mismo bloque
    h1 = df.iloc[1].astype(str).str.replace("\xa0", " ").str.strip()
    h1 = h1.mask((h1 == "") | (h1.str.lower() == "nan")).ffill()

    # Row 2 -> "Unidad de medida"/"Equiv. (kg./lt)"/"Mayorista"
    h2 = df.iloc[2].astype(str).str.replace("\xa0", " ").str.strip().str.lower()

    # Row 3 -> "Precio min/prom/max"
    h3 = df.iloc[3].astype(str).str.replace("\xa0", " ").str.strip().str.lower()

    # Validaciones básicas
    if is_interval and (body.empty or df.shape[1] < 2):
        return pd.DataFrame()

    # Funciones auxiliares
    def _to_float(x):
        if pd.isna(x): return np.nan
        s = str(x).strip()
        if s == "": return np.nan
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return np.nan

    def _to_equiv(x):
        if pd.isna(x): return np.nan
        import re
        m = re.search(r"(\d+(?:[.,]\d+)?)", str(x))
        if not m: return np.nan
        val = m.group(1).replace(",", ".")
        try: return float(val)
        except Exception: return np.nan

    records = []

    if is_interval:
        # Fecha por fila
        dates = body.iloc[:, 0].astype(str).replace({"": pd.NA, "nan": pd.NA}).ffill()
        dates = pd.to_datetime(dates, dayfirst=True, errors="coerce").dt.strftime("%d/%m/%Y")

        ncols = df.shape[1]
        # Recorremos todas las columnas de precio mayorista
        for c in range(1, ncols):  # desde 1: salta la col 'Fecha'
            dept = h0.iloc[c]
            prod = h1.iloc[c]
            lvl2 = h2.iloc[c]
            lvl3 = h3.iloc[c]

            if not isinstance(dept, str) or dept.lower() == "fecha":
                continue
            if "mayorista" not in str(lvl2):
                continue
            ptype = None
            if "min" in str(lvl3): ptype = "min"
            elif "prom" in str(lvl3): ptype = "mean"
            elif "max" in str(lvl3): ptype = "max"
            if ptype is None:
                continue

            # Buscar columnas de Unidad y Equivalencia que compartan (Departamento, Producto)
            unit_col = None
            equiv_col = None
            for k in range(1, ncols):
                if h0.iloc[k] == dept and h1.iloc[k] == prod:
                    if "unidad" in h2.iloc[k] and "medida" in h2.iloc[k]:
                        unit_col = k
                    elif "equiv" in h2.iloc[k]:
                        equiv_col = k
                # Early exit si ya tenemos ambas
                if unit_col is not None and equiv_col is not None:
                    break

            price_series = body.iloc[:, c]
            unit_series  = body.iloc[:, unit_col]  if unit_col  is not None else pd.Series([np.nan]*len(body))
            equiv_series = body.iloc[:, equiv_col] if equiv_col is not None else pd.Series([np.nan]*len(body))

            # Construir registros
            for i in range(len(body)):
                price_val = _to_float(price_series.iat[i])
                if pd.isna(price_val):
                    continue
                rec = {
                    "producto_name": prod,
                    "date": dates.iat[i],
                    "department": dept,
                }
                rec[ptype] = price_val
                rec["unitOfMeasure"] = ("" if pd.isna(unit_series.iat[i]) else str(unit_series.iat[i]).strip())
                rec["equivalence"] = _to_equiv(equiv_series.iat[i])
                records.append(rec)

        if not records:
            return pd.DataFrame()

        out = pd.DataFrame(records)

        # Consolidar min/mean/max por clave
        agg = {}
        for p in ("min","mean","max"):
            if p in out.columns:
                agg[p] = "max"
        key_cols = ["producto_name","date","department","unitOfMeasure","equivalence"]
        out = (out.groupby(key_cols, dropna=False, as_index=False).agg(agg)
                 .sort_values(key_cols).reset_index(drop=True))

        return out

    # ---- Modo 'día' (por compatibilidad con tu flujo actual) ----
    # En día, la primera columna es el producto y no hay columna Fecha
    productos = (body.iloc[:, 0].astype(str).replace({"": pd.NA, "nan": pd.NA}).ffill()
        .str.replace("\xa0", " ", regex=False).str.replace(r"\s+", " ", regex=True).str.strip()
    )

    ncols = df.shape[1]
    if ncols <= 1:
        return pd.DataFrame()

    # Encabezados (ya calculados arriba):
    # h0 = df.iloc[0]  (tiene 'Productos' en col 0)
    # h1 = df.iloc[1]  -> Departamentos (colspan)
    # h2 = df.iloc[2]  -> "Unidad de medida" | "Equiv. (kg./lt)" | "Mayorista"
    # h3 = df.iloc[3]  -> "Precio Min/Prom/Max"
    dept_series = df.iloc[1, 1:ncols].astype(str).str.replace("\xa0", " ", regex=False).str.strip().ffill()
    lvl2_series = df.iloc[2, 1:ncols].astype(str).str.lower().str.replace("\xa0", " ", regex=False).str.strip()
    lvl3_series = df.iloc[3, 1:ncols].astype(str).str.lower().str.replace("\xa0", " ", regex=False).str.strip()

    # Identificar columnas de PRECIO (Mayorista + Min/Prom/Max)
    def _ptype_from_label(lbl: str):
        s = (str(lbl) if lbl is not None else "").lower()
        if "min" in s: return "min"
        if "prom" in s: return "mean"
        if "max" in s: return "max"
        return None

    price_cols = []
    for offset, (dept, l2, l3) in enumerate(zip(dept_series, lvl2_series, lvl3_series), start=1):
        if "mayorista" not in l2:
            continue
        ptype = _ptype_from_label(l3)
        if ptype is None:
            continue
        price_cols.append((offset, dept, ptype))  # offset es el índice real de columna en df/body

    if not price_cols:
        return pd.DataFrame()

    # Mapear por DEPARTAMENTO las columnas de Unidad y Equivalencia (una por departamento)
    dept_unit_col = {}
    dept_equiv_col = {}
    for offset, (dept, l2) in enumerate(zip(dept_series, lvl2_series), start=1):
        if "unidad" in l2 and "medida" in l2:
            dept_unit_col.setdefault(dept, offset)
        elif "equiv" in l2:
            dept_equiv_col.setdefault(dept, offset)

    # Funciones auxiliares ya definidas arriba:
    # - _to_float_like(x): convierte string a float manejando coma/punto
    # Normalizador de equivalencia vectorizado
    import re
    def _equiv_to_number(series: pd.Series) -> pd.Series:
        s = series.astype(str)
        # extrae el primer número (permite coma/punto)
        extracted = s.str.extract(r"(\d+(?:[.,]\d+)?)", expand=False)
        # convierte a float con coma europea si aplica
        return extracted.apply(lambda v: float(v.replace(",", ".")) if isinstance(v, str) else None)

    records_frames = []

    for col_idx, dept, ptype in price_cols:
        # Series de precio / unidad / equivalencia por filas (vectorizado)
        price_series = body.iloc[:, col_idx]
        unit_col  = dept_unit_col.get(dept, None)
        equiv_col = dept_equiv_col.get(dept, None)

        unit_series  = body.iloc[:, unit_col]  if unit_col  is not None else pd.Series([None]*len(body))
        equiv_series = body.iloc[:, equiv_col] if equiv_col is not None else pd.Series([None]*len(body))

        # Limpieza vectorizada
        price_clean = price_series.apply(_to_float_like)
        unit_clean  = unit_series.astype(str).replace({"None": None, "nan": None}).str.strip()
        equiv_num   = _equiv_to_number(equiv_series)

        # Armar bloque ya en formato long
        part = pd.DataFrame({
            "producto_name": productos,
            "date": fecha_consulta,
            "department": dept,
            "unitOfMeasure": unit_clean,
            "equivalence": equiv_num,
            ptype: price_clean
        })

        # Filtrar filas sin precio en este ptype (evita ruido)
        part = part[part[ptype].notna()]
        if not part.empty:
            records_frames.append(part)

    if not records_frames:
        return pd.DataFrame()

    out = pd.concat(records_frames, ignore_index=True)

    # Consolidar min/mean/max por clave (un producto tiene 3 columnas de precio por depto)
    agg = {p: "max" for p in ("min", "mean", "max") if p in out.columns}
    key_cols = ["producto_name", "date", "department", "unitOfMeasure", "equivalence"]
    out = (
        out.groupby(key_cols, dropna=False, as_index=False)
        .agg(agg)
        .sort_values(key_cols)
        .reset_index(drop=True)
    )

    return out 





def _download_batch(session: requests.Session, product_codes: List[str],
                    fecha: str, desde: str, hasta: str, periodicidad: str) -> pd.DataFrame:
    """UN request por lote (muchos productos en productos[]). Devuelve tabla NORMALIZADA y consolidada por clave."""
    params = _build_params(product_codes, fecha, desde, hasta, periodicidad)
    resp = session.get(SISAP_URL, params=params, timeout=90)
    resp.raise_for_status()
    df = _read_first_table(resp.content)
    if df is None or df.empty:
        return pd.DataFrame()
    return _parse_html_to_long(df, fecha_consulta=fecha)


from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

def fetch_prices(product_codes: List[str], fecha: str, desde: str, hasta: str,
                 batch_size: int = 40, periodicidad: str | None = None) -> pd.DataFrame:
    """Descarga en paralelo los lotes de productos del portal de ciudades."""
    if not product_codes:
        return pd.DataFrame()

    if periodicidad is None:
        use_dia = (fecha == desde == hasta)
        periodicidad = "dia" if use_dia else "intervalo"

    # Crear los lotes
    batches = [product_codes[i:i + batch_size] for i in range(0, len(product_codes), batch_size)]
    total = len(batches)
    LOGGER.info(f"Descargando {len(product_codes)} productos en {total} lotes (modo paralelo)...")

    results: List[pd.DataFrame] = []

    def process_batch(idx: int, batch: List[str]) -> pd.DataFrame:
        """Ejecuta un lote independiente usando su propia sesión."""
        with requests.Session() as s:
            try:
                df = _download_batch(s, batch, fecha, desde, hasta, periodicidad)
                LOGGER.info(f"Lote {idx+1}/{total} completado ({len(df)} filas).")
                return df
            except Exception as e:
                LOGGER.warning(f"Lote {idx+1}/{total} falló: {e}")
                return pd.DataFrame()

    # Ejecutar en paralelo
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(process_batch, i, batch) for i, batch in enumerate(batches)]
        for f in as_completed(futures):
            df = f.result()
            if df is not None and not df.empty:
                results.append(df)

    if not results:
        LOGGER.warning("No se descargaron datos válidos.")
        return pd.DataFrame()

    final_df = pd.concat(results, ignore_index=True)
    LOGGER.info(f"Descarga completada: {len(final_df)} filas totales.")
    return _finalize_table(final_df)





# ============================================================
# NUEVO MODO: MAYORISTA (portal2/mayorista/resumenes/filtrar)
# ============================================================

SISAP_URL_MAYORISTA = "http://sistemas.midagri.gob.pe/sisap/portal2/mayorista/resumenes/filtrar"
# SISAP_URL_MAYORISTA = "http://200.115.22.230/sisap/portal2/mayorista/resumenes/filtrar"

def _build_params_mayorista(
    product_codes: List[str],
    fecha: str,
    desde: str,
    hasta: str,
    mercado: str = "15011501",
    periodicidad: str = "intervalo",
):
    """Parámetros para el endpoint portal2/mayorista/resumenes/filtrar."""
    return {
        "mercado": mercado,
        "variables[]": ["precio_max", "precio_prom", "precio_min"],
        "fecha": fecha,
        "desde": desde,
        "hasta": hasta,
        "anios[]": fecha[-4:],     # 'dd/mm/YYYY' -> YYYY
        "meses[]": fecha[3:5],     # 'dd/mm/YYYY' -> mm
        "productos[]": product_codes,
        "periodicidad": periodicidad,
        "__ajax_carga_final": "consulta",
        "ajax": "true",
    }


def _parse_html_mayorista(content: bytes) -> pd.DataFrame:
    """Parser unificado para el HTML del portal mayorista (intervalo o día, con 3 precios)."""
    import re

    try:
        html = content.decode("utf-8", errors="ignore")
    except Exception:
        html = content.decode("ISO-8859-1", errors="ignore")

    if "<table" not in html.lower():
        LOGGER.warning("⚠️ No se detectó tabla en el HTML recibido.")
        return pd.DataFrame()

    try:
        df = pd.read_html(io.StringIO(html), header=None)[0]
    except Exception as e:
        LOGGER.warning(f"No se pudo leer tabla mayorista: {e}")
        return pd.DataFrame()

    # Detección automática
    first_cell = str(df.iloc[0, 0]).strip().lower()
    is_dia = "producto" in first_cell or "variedad" in first_cell

    # ============================================================
    # 🔹 CASO 1: periodicidad = "intervalo"
    # ============================================================
    if not is_dia:
        header1 = df.iloc[0].astype(str).str.strip()
        header2 = df.iloc[1].astype(str).str.strip().str.lower()

        df.columns = [
            "Fecha" if i == 0 else f"{header1[i]}_{header2[i]}"
            for i in range(len(header1))
        ]
        body = df.iloc[2:].copy().reset_index(drop=True)

        long_df = body.melt(id_vars=["Fecha"], var_name="col", value_name="value")
        long_df[["producto_name", "tipo_precio"]] = (
            long_df["col"].str.extract(r"^(.*?)_(precio [^<]+)$", expand=True).ffill()
        )

        def _map_tipo(t):
            t = str(t).lower()
            if "mín" in t or "min" in t:
                return "min"
            elif "máx" in t or "max" in t:
                return "max"
            elif "prom" in t:
                return "mean"
            return None

        long_df["tipo_precio"] = long_df["tipo_precio"].apply(_map_tipo)
        long_df = long_df[long_df["tipo_precio"].notna()]
        long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce")
        long_df["date"] = pd.to_datetime(
            long_df["Fecha"], dayfirst=True, errors="coerce"
        ).dt.strftime("%d/%m/%Y")

        wide = (
            long_df.pivot_table(
                index=["producto_name", "date"],
                columns="tipo_precio",
                values="value",
                aggfunc="max",
            )
            .reset_index()
        )

        wide["department"] = "Lima Metropolitana"
        wide["unitOfMeasure"] = "Kg"
        wide["equivalence"] = None

        for c in ("min", "mean", "max"):
            if c not in wide.columns:
                wide[c] = None

        return wide[
            [
                "producto_name",
                "date",
                "department",
                "unitOfMeasure",
                "equivalence",
                "min",
                "mean",
                "max",
            ]
        ]

    # ============================================================
    # 🔹 CASO 2: periodicidad = "dia"
    # ============================================================
    else:
        # Intentar extraer fecha del H1
        match = re.search(r"Fecha:\s*(\d{2}/\d{2}/\d{4})", html)
        fecha_consulta = match.group(1) if match else None

        # Reemplazar encabezados esperados
        df.columns = ["Producto", "Variedad", "Precio Máximo", "Precio Promedio", "Precio Mínimo"]

         # 💡 Eliminar fila basura (la cabecera "Variedad" que se cuela en los datos)
        df = df[df["Variedad"].notna() & (df["Variedad"].astype(str).str.lower() != "variedad")]


        # Rellenar producto en filas con rowspan
        df["Producto"] = df["Producto"].ffill()

        # Limpieza
        df["Variedad"] = df["Variedad"].astype(str).str.strip()
        df["Precio Máximo"] = pd.to_numeric(df["Precio Máximo"], errors="coerce")
        df["Precio Promedio"] = pd.to_numeric(df["Precio Promedio"], errors="coerce")
        df["Precio Mínimo"] = pd.to_numeric(df["Precio Mínimo"], errors="coerce")

        # Unificar nombres
        df["producto_name"] = df["Variedad"]
        df["date"] = fecha_consulta or pd.Timestamp.today().strftime("%d/%m/%Y")
        df["department"] = "Lima Metropolitana"
        df["unitOfMeasure"] = "Kg"
        df["equivalence"] = None
        df["max"] = df["Precio Máximo"]
        df["mean"] = df["Precio Promedio"]
        df["min"] = df["Precio Mínimo"]

        return df[
            [
                "producto_name",
                "date",
                "department",
                "unitOfMeasure",
                "equivalence",
                "min",
                "mean",
                "max",
            ]
        ]




from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

def fetch_prices_mayorista(
    product_codes: List[str],
    fecha: str,
    desde: str,
    hasta: str,
    mercado: str = "15011501",
    batch_size: int = 40,
    periodicidad: str = "intervalo",
) -> pd.DataFrame:
    """Descarga los precios del módulo MAYORISTA en paralelo (POST por lote)."""
    if not product_codes:
        return pd.DataFrame()

    # Crear lotes
    batches = [product_codes[i:i + batch_size] for i in range(0, len(product_codes), batch_size)]
    total = len(batches)
    LOGGER.info(f"Descargando {len(product_codes)} productos en {total} lotes (modo paralelo, mayorista)...")

    results: list[pd.DataFrame] = []

    def process_batch(idx: int, batch: list[str]) -> pd.DataFrame:
        """Ejecuta un lote de descarga independiente usando su propia sesión."""
        with requests.Session() as session:
            # Headers de navegador
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
                "Referer": "http://sistemas.midagri.gob.pe/sisap/portal2/mayorista/resumenes/consultar/",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "http://sistemas.midagri.gob.pe",
                "Content-Type": "application/x-www-form-urlencoded",
            })
            params = _build_params_mayorista(batch, fecha, desde, hasta, mercado, periodicidad)
            try:
                resp = session.post(SISAP_URL_MAYORISTA, data=params, timeout=90)
                resp.raise_for_status()
                content = resp.content.decode("ISO-8859-1", errors="ignore").encode("utf-8")
                parsed = _parse_html_mayorista(content)
                if not parsed.empty:
                    LOGGER.info(f"Lote {idx+1}/{total} completado ({len(parsed)} filas).")
                else:
                    LOGGER.info(f"Lote {idx+1}/{total} sin filas útiles.")
                return parsed
            except Exception as e:
                LOGGER.warning(f"Lote {idx+1}/{total} falló: {e}")
                return pd.DataFrame()

    # Ejecutar los lotes en paralelo
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(process_batch, i, batch) for i, batch in enumerate(batches)]
        for f in as_completed(futures):
            df = f.result()
            if df is not None and not df.empty:
                results.append(df)

    if not results:
        LOGGER.warning("No se descargaron datos válidos desde mayorista.")
        return pd.DataFrame()

    final = pd.concat(results, ignore_index=True)
    LOGGER.info(f"Descarga completada (mayorista): {len(final)} filas totales.")
    return final.sort_values(["producto_name", "date"])
