/* =====================================================================
   ROLLBACK 0004 — borra dbo.uspBM_GetDynamicMarketPriceReport y su SP interno
   dbo.uspBM_GetDynamicMarketPriceReportData. No toca tablas ni el SP de producción.
   ===================================================================== */
DROP PROCEDURE IF EXISTS dbo.uspBM_GetDynamicMarketPriceReport;
DROP PROCEDURE IF EXISTS dbo.uspBM_GetDynamicMarketPriceReportData;
