/* =====================================================================
   ROLLBACK 0005 — borra dbo.uspBM_GetDynamicMarketPriceReport_v2 y su SP interno
   dbo.uspBM_GetDynamicMarketPriceReportData_v2. No toca tablas, ni los SP de 0004, ni los de producción.
   ===================================================================== */
DROP PROCEDURE IF EXISTS dbo.uspBM_GetDynamicMarketPriceReport_v2;
DROP PROCEDURE IF EXISTS dbo.uspBM_GetDynamicMarketPriceReportData_v2;
