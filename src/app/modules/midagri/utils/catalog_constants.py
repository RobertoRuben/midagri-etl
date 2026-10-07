"""Filtros fijos del catálogo de productos de mercado y de la multi gestión (D2, D6)."""

from typing import Final

CATALOG_TYPE_MARKET: Final[str] = "0001"
"""`BM_Catalog.type` de los productos de mercado."""

CROP_TABLE: Final[str] = "BM_TCATCAT"
"""`IT_Multivalor.Tabla` de los cultivos."""

CROP_CLUSTER: Final[str] = "CROP"
"""`IT_Multivalor.systemCodeCluster` de los cultivos."""

ORGANIZATION_ID: Final[int] = 1
"""`idOrganization` de MIDAGRI en la multi gestión y el catálogo."""
