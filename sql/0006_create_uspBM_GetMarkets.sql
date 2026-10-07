/* =====================================================================
   0006 — dbo.uspBM_GetMarkets: mercados activos para el selector del reporte de precios (D38)
   Reemplaza la lista 1 de uspBM_GetMarketCatalogParameters (sql/0003), que queda solo para
   productos (listas 2 y 5). Columnas con los nombres del DTO de la API (idMarket, name, marketType).
   Para "todos los mercados" el front envía idMarket = 0 (no viene en esta lista).
   Requiere 0001. Idempotente (CREATE OR ALTER).
   Rollback: 0006_create_uspBM_GetMarkets.rollback.sql

   EXEC dbo.uspBM_GetMarkets;
   ===================================================================== */

/*======================================================================
  Descripción : Lista los mercados activos de BM_Market (selector Mercado del reporte de precios)
  Autor       : JRUIZ
  Creado      : 02/10/2026
  Modificado  : 02/10/2026 -> etl-sisap -> creación. Sale de la lista 1 de
                uspBM_GetMarketCatalogParameters. marketType = MAYORISTA / CIUDADES.
===========================================================================*/
CREATE OR ALTER PROCEDURE dbo.uspBM_GetMarkets
AS
BEGIN
    SET NOCOUNT ON;

    -- Salida tipada, sin NULL: idMarket INT, name VARCHAR(250), marketType VARCHAR(50).
    SELECT
        CAST(M.id AS INT)                               AS idMarket,
        ISNULL(CAST(M.name AS VARCHAR(250)), '')        AS name,
        ISNULL(CAST(M.source AS VARCHAR(50)), '')       AS marketType
    FROM dbo.BM_Market AS M
    WHERE M.active = 1
    ORDER BY M.name;
END;
GO
