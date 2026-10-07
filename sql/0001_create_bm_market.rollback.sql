/* =====================================================================
   ROLLBACK 0001 — borra dbo.BM_Market.
   Ejecutar DESPUÉS de 0002_create_bm_market_price.rollback.sql: con la FK de idMarket
   todavía en BM_MarketPrice, el DROP falla (a propósito).
   ===================================================================== */
IF OBJECT_ID(N'dbo.BM_Market', N'U') IS NOT NULL
    DROP TABLE dbo.BM_Market;
