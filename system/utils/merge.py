# system/merge/merge.py
import pandas as pd
import unicodedata
from system.core.logging import LOGGER
import re
import unicodedata



ALIASES = {
    "limametropolitana": "lima",
    "sanmartin": "sanmartin",
    "lalibertad": "lalibertad",
    "madrededios": "madrededios",
}




def _norm(s) -> str:
    """Normaliza texto: elimina tildes, mayúsculas, símbolos y TODOS los espacios."""
    if pd.isna(s):
        return ""
    s = str(s)
    # 1️⃣ Quitar tildes
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    # 2️⃣ Pasar a minúsculas
    s = s.casefold()
    # 3️⃣ Reemplazar espacios invisibles, tabs, saltos, etc.
    s = re.sub(r"[\xa0\t\r\n]+", " ", s)
    # 4️⃣ Eliminar todo lo que no sea letra o número (espacios, paréntesis, guiones, comas, puntos, etc.)
    s = re.sub(r"[^a-z0-9]", "", s)
    # 5️⃣ Quitar espacios restantes si quedaran
    return s.strip()


def _apply_alias(x: str) -> str:
    return ALIASES.get(x, x)

def _ubigeo_long(ubg: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in ubg.columns}
    dept = cols.get("department", "department")
    prov = cols.get("province",   "province")   # si no existieran en tu tabla, quita esta línea
    dist = cols.get("district",   "district")   # idem

    parts = []
    if dist in ubg.columns:
        d1 = ubg[["id", dist]].rename(columns={dist: "name"})
        d1["priority"] = 1
        parts.append(d1)
    if prov in ubg.columns:
        d2 = ubg[["id", prov]].rename(columns={prov: "name"})
        d2["priority"] = 2
        parts.append(d2)
    if dept in ubg.columns:
        d3 = ubg[["id", dept]].rename(columns={dept: "name"})
        d3["priority"] = 3
        parts.append(d3)

    long = pd.concat(parts, ignore_index=True)
    long["key"] = long["name"].apply(_norm).apply(_apply_alias)
    long = long.dropna(subset=["key"]).drop_duplicates(subset=["key", "priority"])
    long = long.sort_values(["key", "priority"]).drop_duplicates("key", keep="first")
    return long[["key", "id"]]

def prepare_for_merge(prices: pd.DataFrame, cats: pd.DataFrame, ubis: pd.DataFrame,
                      default_type="Mayorista", default_registered_by="etl-sisap") -> pd.DataFrame:
    """
    prices: producto_name | date | department | unitOfMeasure | equivalence | min | mean | max
    cats:   id | code | name
    ubis:   id | department | (province) | (district)
    """
    if prices is None or prices.empty:
        return pd.DataFrame()

    df = prices.copy()

    # normalizaciones
    df["producto_key"] = df["producto_name"].apply(_norm)
    df["dep_key"] = df["department"].apply(_norm).apply(_apply_alias)
    df["date"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce").dt.date

    cats = cats.copy()
    cats["producto_key"] = cats["name"].apply(_norm)

    ub_long = _ubigeo_long(ubis)

    # joins en memoria
    df = df.merge(cats[["id", "producto_key"]], on="producto_key", how="left").rename(columns={"id": "idCatalog"})
    df = df.merge(ub_long, left_on="dep_key", right_on="key", how="left").rename(columns={"id": "idUbigeo"}).drop(columns=["key"], errors="ignore")

    miss_cat = int(df["idCatalog"].isna().sum())
    miss_ubi = int(df["idUbigeo"].isna().sum())
    
    if miss_cat:
        top = (
            df.loc[df["idCatalog"].isna(), "producto_name"]
            .dropna().astype(str).str.strip().str.upper()
            .value_counts().head(15)
        )
        LOGGER.warning(f"⚠️ Productos sin match en BM_Catalog: {miss_cat}. Ejemplos:\n{top.to_string()}")


    if miss_ubi:
        top = (
            df.loc[df["idUbigeo"].isna(), "department"]
              .dropna().astype(str).str.strip().str.upper()
              .value_counts().head(15)
        )
        LOGGER.warning(f"Ubigeos sin match: {miss_ubi}. Top:\n{top.to_string()}")

    if "type" not in df.columns: df["type"] = default_type
    if "registeredBy" not in df.columns: df["registeredBy"] = default_registered_by

    out_cols = ["idCatalog","idUbigeo","date","unitOfMeasure","equivalence","min","mean","max","type","registeredBy"]
    return df[out_cols]

