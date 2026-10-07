/* =====================================================================
   ROLLBACK DE EMERGENCIA — despliegue en producción del 2026-10-07 (0001, 0002, 0006, 0003, 0004, 0005)
   Deja BDFarmex como estaba antes: borra los 6 SP nuevos (8 objetos), dbo.BM_MarketPrice y dbo.BM_Market.
   NO toca BM_CatalogPrice ni ningún SP o tabla que existía antes (D30): el app y el SP de reportes
   de producción siguen funcionando igual, y el legado (run_midagri.bat) se puede volver a habilitar.

   Antes de borrar, copia BM_MarketPrice y BM_Market a tablas de respaldo (sin constraints), porque
   BM_MarketPrice tiene precios de mercados distintos de 15011501 que no están en ningún otro lado.
   Para no respaldar, poner @respaldar = 0.

   Una sola transacción: o se deshace todo o nada. Se puede ejecutar dos veces.
   Después de ejecutarlo: deshabilitar la tarea de la API nueva (POST /etl/runs) y volver a habilitar la del legado.
   ===================================================================== */
SET XACT_ABORT ON;
SET NOCOUNT ON;

DECLARE @respaldar BIT = 1;

IF DB_NAME() NOT IN (N'BDFarmex', N'BDFarmex_Agri')
    THROW 50000, 'Base inesperada: ejecutar en BDFarmex (producción) o BDFarmex_Agri (QAS).', 1;

BEGIN TRANSACTION;

-- 1) Respaldo (solo si hay algo que respaldar y no se hizo antes)
IF @respaldar = 1 AND OBJECT_ID(N'dbo.BM_MarketPrice', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.BM_MarketPrice_bak_rollback', N'U') IS NULL
    EXEC(N'SELECT * INTO dbo.BM_MarketPrice_bak_rollback FROM dbo.BM_MarketPrice;');
IF @respaldar = 1 AND OBJECT_ID(N'dbo.BM_Market', N'U') IS NOT NULL
   AND OBJECT_ID(N'dbo.BM_Market_bak_rollback', N'U') IS NULL
    EXEC(N'SELECT * INTO dbo.BM_Market_bak_rollback FROM dbo.BM_Market;');

-- 2) SP nuevos (rollbacks 0005, 0004, 0003, 0006)
DROP PROCEDURE IF EXISTS dbo.uspBM_GetDynamicMarketPriceReport_v2;
DROP PROCEDURE IF EXISTS dbo.uspBM_GetDynamicMarketPriceReportData_v2;
DROP PROCEDURE IF EXISTS dbo.uspBM_GetDynamicMarketPriceReport;
DROP PROCEDURE IF EXISTS dbo.uspBM_GetDynamicMarketPriceReportData;
DROP PROCEDURE IF EXISTS dbo.uspBM_GetMarketCatalogParameters;
DROP PROCEDURE IF EXISTS dbo.uspBM_GetMarkets;

-- 3) Tablas nuevas (rollbacks 0002 y 0001; primero la que tiene la FK)
DROP TABLE IF EXISTS dbo.BM_MarketPrice;
DROP TABLE IF EXISTS dbo.BM_Market;

COMMIT TRANSACTION;

-- Comprobación: no debe quedar ningún objeto nuevo; BM_CatalogPrice sigue igual.
SELECT name, type_desc FROM sys.objects
WHERE name IN (N'BM_Market', N'BM_MarketPrice', N'uspBM_GetMarkets', N'uspBM_GetMarketCatalogParameters',
               N'uspBM_GetDynamicMarketPriceReport', N'uspBM_GetDynamicMarketPriceReportData',
               N'uspBM_GetDynamicMarketPriceReport_v2', N'uspBM_GetDynamicMarketPriceReportData_v2');
SELECT name AS respaldo, create_date FROM sys.tables WHERE name LIKE N'BM_Market%_bak_rollback';
SELECT COUNT(*) AS filas_BM_CatalogPrice, SUM(mean) AS suma_mean, MAX([date]) AS hasta FROM dbo.BM_CatalogPrice;
