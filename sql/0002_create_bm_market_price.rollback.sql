/* =====================================================================
   ROLLBACK 0002 — borra dbo.BM_MarketPrice.
   ⚠️ Se pierden los precios de los mercados distintos de 15011501 (los de 15011501 siguen en BM_CatalogPrice).
   Ejecutar ANTES de 0001_create_bm_market.rollback.sql: con la FK de idMarket, el DROP de BM_Market falla.
   ===================================================================== */
IF OBJECT_ID(N'dbo.BM_MarketPrice', N'U') IS NOT NULL
    DROP TABLE dbo.BM_MarketPrice;
