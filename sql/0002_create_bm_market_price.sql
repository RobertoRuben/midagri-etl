/* =====================================================================
   0002 — dbo.BM_MarketPrice: precios de todos los mercados SISAP, con su mercado (D1', D15', D22)
   Requiere 0001. No toca BM_CatalogPrice ni ningún SP: el SP de reportes sigue leyendo solo BM_CatalogPrice,
   donde la API escribe únicamente el mercado 15011501 (igual que el legado).
   Siembra: copia BM_CatalogPrice como mercado 15011501 (el único que cargaba el legado).
   Un solo lote y una sola transacción. Idempotente. Rollback: 0002_create_bm_market_price.rollback.sql
   ===================================================================== */
SET XACT_ABORT ON;
SET NOCOUNT ON;
BEGIN TRANSACTION;

DECLARE @lima INT = (SELECT id FROM dbo.BM_Market WHERE code = '15011501');
IF @lima IS NULL
    THROW 50001, 'Falta el mercado 15011501 en dbo.BM_Market: ejecutar primero 0001_create_bm_market.sql.', 1;

IF OBJECT_ID(N'dbo.BM_MarketPrice', N'U') IS NULL
BEGIN
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
    -- Sin FK a BM_Catalog ni a BM_Ubigeo: una tabla nueva no debe impedir nada sobre las tablas del app.
END;

-- Siembra: el histórico de BM_CatalogPrice es del mercado 15011501. Lo que ya está no se vuelve a copiar.
INSERT INTO dbo.BM_MarketPrice
    ([type], idCatalog, idMarket, idUbigeo, [date], unitOfMeasure, equivalence, [min], mean, [max],
     registrationDate, registeredBy)
SELECT p.[type], p.idCatalog, @lima, p.idUbigeo, p.[date], p.unitOfMeasure, p.equivalence, p.[min], p.mean, p.[max],
       p.registrationDate, p.registeredBy
FROM dbo.BM_CatalogPrice AS p
WHERE p.[type] IS NOT NULL AND p.idUbigeo IS NOT NULL AND p.unitOfMeasure IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM dbo.BM_MarketPrice AS m
      WHERE m.idCatalog = p.idCatalog AND m.idMarket = @lima AND m.idUbigeo = p.idUbigeo
        AND m.[date] = p.[date] AND m.unitOfMeasure = p.unitOfMeasure AND m.[type] = p.[type]);

-- Toda fila de BM_CatalogPrice debe quedar en BM_MarketPrice (si alguna tiene la llave nula, no se sigue).
DECLARE @missing INT = (
    SELECT COUNT(*) FROM dbo.BM_CatalogPrice AS p
    WHERE NOT EXISTS (
        SELECT 1 FROM dbo.BM_MarketPrice AS m
        WHERE m.idCatalog = p.idCatalog AND m.idMarket = @lima AND m.idUbigeo = p.idUbigeo
          AND m.[date] = p.[date] AND m.unitOfMeasure = p.unitOfMeasure AND m.[type] = p.[type]));
IF @missing > 0
    THROW 50002, 'Quedaron filas de BM_CatalogPrice sin copiar a BM_MarketPrice (llave nula); no se continúa.', 1;

COMMIT TRANSACTION;

SELECT m.code, COUNT(*) AS filas, MIN(p.[date]) AS desde, MAX(p.[date]) AS hasta
FROM dbo.BM_MarketPrice AS p
JOIN dbo.BM_Market AS m ON m.id = p.idMarket
GROUP BY m.code
ORDER BY m.code;
