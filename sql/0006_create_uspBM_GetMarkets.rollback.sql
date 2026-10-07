/* =====================================================================
   ROLLBACK 0006 — borra dbo.uspBM_GetMarkets. No toca tablas.
   Si se revierte, getListMarketsMobile debe volver a la lista 1 de uspBM_GetMarketCatalogParameters
   (revertir también el cambio de 0003 del 02/10/2026).
   ===================================================================== */
DROP PROCEDURE IF EXISTS dbo.uspBM_GetMarkets;
