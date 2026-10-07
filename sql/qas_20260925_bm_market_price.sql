/* =====================================================================
   SOLO QAS (BDFarmex_Agri), una vez — deja BM_CatalogPrice como en producción y pasa los precios a BM_MarketPrice.
   Estado de partida: 0001 aplicado, el 0002 anterior (idMarket en BM_CatalogPrice) aplicado, y precios de
   CIUDADES dentro de BM_CatalogPrice. El SP de reportes ya se devolvió a la versión de producción.

   Pasos, en una transacción:
     1) Respaldo BM_CatalogPrice_bak_20260925 (con idMarket).
     2) Borra de BM_CatalogPrice lo que no es 15011501.
     3) Quita idMarket, su FK y UQ_BM_CatalogPrice_Key (lo mismo que hacía el rollback del 0002 anterior).
     4) Crea BM_MarketPrice y la siembra con BM_CatalogPrice como 15011501 (= sql/0002_create_bm_market_price.sql).
     5) Copia del respaldo a BM_MarketPrice los precios de los demás mercados.
     6) Verifica que cada mercado tenga en BM_MarketPrice las mismas filas y la misma suma de `mean` que antes.
   Si algo no cuadra, THROW y no queda nada aplicado.
   ===================================================================== */
SET XACT_ABORT ON;
SET NOCOUNT ON;

IF DB_NAME() <> N'BDFarmex_Agri'
    THROW 50000, 'Este script es solo para QAS (BDFarmex_Agri).', 1;
IF OBJECT_ID(N'dbo.BM_MarketPrice', N'U') IS NOT NULL
    THROW 50000, 'BM_MarketPrice ya existe: este script ya se ejecutó.', 1;
IF COL_LENGTH(N'dbo.BM_CatalogPrice', N'idMarket') IS NULL
    THROW 50000, 'BM_CatalogPrice no tiene idMarket: el estado de partida no es el esperado.', 1;

BEGIN TRANSACTION;

DECLARE @lima INT = (SELECT id FROM dbo.BM_Market WHERE code = '15011501');

-- 1) Respaldo y foto de control
EXEC(N'SELECT * INTO dbo.BM_CatalogPrice_bak_20260925 FROM dbo.BM_CatalogPrice;');
CREATE TABLE #before (idMarket INT PRIMARY KEY, n INT, total DECIMAL(38,4));
EXEC(N'INSERT INTO #before SELECT idMarket, COUNT(*), SUM(mean) FROM dbo.BM_CatalogPrice_bak_20260925 GROUP BY idMarket;');

-- 2) Solo 15011501 se queda en BM_CatalogPrice
EXEC sys.sp_executesql N'DELETE FROM dbo.BM_CatalogPrice WHERE idMarket <> @lima;', N'@lima INT', @lima = @lima;

-- 3) BM_CatalogPrice vuelve al esquema de producción
IF OBJECT_ID(N'dbo.UQ_BM_CatalogPrice_Key', N'UQ') IS NOT NULL
    ALTER TABLE dbo.BM_CatalogPrice DROP CONSTRAINT UQ_BM_CatalogPrice_Key;
IF OBJECT_ID(N'dbo.FK_BM_CatalogPrice_idMarket', N'F') IS NOT NULL
    ALTER TABLE dbo.BM_CatalogPrice DROP CONSTRAINT FK_BM_CatalogPrice_idMarket;
ALTER TABLE dbo.BM_CatalogPrice DROP COLUMN idMarket;

-- 4) BM_MarketPrice (misma definición que sql/0002_create_bm_market_price.sql)
CREATE TABLE dbo.BM_MarketPrice (
    id               INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_BM_MarketPrice PRIMARY KEY,
    uuid             UNIQUEIDENTIFIER NULL     CONSTRAINT DF_BM_MarketPrice_uuid DEFAULT (NEWID()),
    [type]           NVARCHAR(50)     NOT NULL,
    idCatalog        INT              NOT NULL,
    idMarket         INT              NOT NULL CONSTRAINT FK_BM_MarketPrice_idMarket REFERENCES dbo.BM_Market (id),
    idUbigeo         INT              NOT NULL,
    [date]           DATE             NOT NULL,
    unitOfMeasure    NVARCHAR(50)     NOT NULL,
    equivalence      NVARCHAR(50)     NULL,
    [min]            DECIMAL(18,4)    NULL,
    mean             DECIMAL(18,4)    NULL,
    [max]            DECIMAL(18,4)    NULL,
    registrationDate DATETIME         NULL     CONSTRAINT DF_BM_MarketPrice_registrationDate DEFAULT (GETDATE()),
    registeredBy     VARCHAR(20)      NULL     CONSTRAINT DF_BM_MarketPrice_registeredBy DEFAULT ('etl-sisap'),
    CONSTRAINT UQ_BM_MarketPrice_Key UNIQUE (idCatalog, idMarket, idUbigeo, [date], unitOfMeasure, [type])
);

-- 5) Todos los mercados, desde el respaldo (conserva registrationDate y registeredBy)
EXEC(N'INSERT INTO dbo.BM_MarketPrice
          ([type], idCatalog, idMarket, idUbigeo, [date], unitOfMeasure, equivalence, [min], mean, [max],
           registrationDate, registeredBy)
      SELECT [type], idCatalog, idMarket, idUbigeo, [date], unitOfMeasure, equivalence, [min], mean, [max],
             registrationDate, registeredBy
      FROM dbo.BM_CatalogPrice_bak_20260925;');

-- 6) Verificación
IF EXISTS (
    SELECT idMarket, n, total FROM #before
    EXCEPT
    SELECT idMarket, COUNT(*), SUM(mean) FROM dbo.BM_MarketPrice GROUP BY idMarket)
    THROW 50003, 'BM_MarketPrice no coincide con el respaldo por mercado; no se aplica nada.', 1;
IF EXISTS (
    SELECT n, total FROM #before WHERE idMarket = @lima
    EXCEPT
    SELECT COUNT(*), SUM(mean) FROM dbo.BM_CatalogPrice)
    THROW 50004, 'BM_CatalogPrice no coincide con 15011501 del respaldo; no se aplica nada.', 1;

COMMIT TRANSACTION;

SELECT m.code, COUNT(*) AS filas, SUM(p.mean) AS suma_mean, MIN(p.[date]) AS desde, MAX(p.[date]) AS hasta
FROM dbo.BM_MarketPrice AS p JOIN dbo.BM_Market AS m ON m.id = p.idMarket
GROUP BY m.code ORDER BY m.code;
SELECT COUNT(*) AS filas_BM_CatalogPrice, SUM(mean) AS suma_mean FROM dbo.BM_CatalogPrice;
