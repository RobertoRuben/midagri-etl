/* =====================================================================
   0003 — dbo.uspBM_GetMarketCatalogParameters: selectores Cultivo → Variedad del reporte de precios (D38)
   Los mercados salen de dbo.uspBM_GetMarkets (sql/0006).
   SP nuevo: no toca uspBM_GetParametersCatalogMonitor (D30). Salida: id, code, name, parentCode,
   typeCode (equivalen a auxValue/auxValue2 de ese SP) y mismos números de lista que usa el mobile
   (2 cultivos, 5 variedades), filtrados por mercado. En la lista 2 el cultivo va en `code` ('0203'): el mobile
   lo manda como @type en la lista 5 (`id` es INT y pierde los ceros: 203; @type acepta ambos).
   Requiere 0001 y 0002_create_bm_market_price. Idempotente (CREATE OR ALTER).
   Rollback: 0003_create_uspBM_GetMarketCatalogParameters.rollback.sql

   EXEC dbo.uspBM_GetMarketCatalogParameters @list = '2', @idMarket = 1;                   -- cultivos del mercado
   EXEC dbo.uspBM_GetMarketCatalogParameters @list = '5', @idMarket = 1, @type = '0203';   -- variedades del cultivo
   EXEC dbo.uspBM_GetMarketCatalogParameters @list = '5', @idMarket = 1, @type = '0203', @input = 'panca';
   EXEC dbo.uspBM_GetMarketCatalogParameters @list = '2', @idMarket = 0;                   -- cultivos de todos los mercados
   EXEC dbo.uspBM_GetMarketCatalogParameters @list = '5', @idMarket = 0, @type = '0203';   -- variedades de todos los mercados
   ===================================================================== */

/*======================================================================
  Descripción : Obtiene parámetros del monitor de precios por mercado (Cultivo → Variedad)
  Autor       : JRUIZ
  Creado      : 04/02/2025
  Modificado  : 01/10/2026 -> etl-sisap -> derivado de uspBM_GetParametersCatalogMonitor.
                Lista 1: mercados activos de BM_Market. Lista 2: productos con precios en
                BM_MarketPrice para @idMarket (@type de cultivo opcional), con la misma salida
                que la lista 5. El SP original no se modifica.
                01/10/2026 -> etl-sisap -> mismos números de lista que el mobile: lista 2 =
                cultivos (BM_TCATCAT) con precios en @idMarket, lista 5 = variedades del cultivo
                @type con precios en @idMarket (antes lista 2). @type acepta '0203' o '203'.
                01/10/2026 -> etl-sisap -> listas 2 y 5: @idMarket = 0 = todos los mercados
                (con precios en cualquier mercado). NULL sigue sin devolver filas.
                02/10/2026 -> etl-sisap -> columnas auxValue / auxValue2 renombradas a
                parentCode / typeCode. Lista 1: el tipo de mercado (MAYORISTA / CIUDADES)
                pasa a typeCode y parentCode queda vacío. Lista 5: parentCode = cultivo,
                typeCode = tipo de catálogo. Lista 2: ambos vacíos.
                02/10/2026 -> etl-sisap -> se quita la lista 1 (mercados): ahora la da
                uspBM_GetMarkets. @list = '1' devuelve vacío, como cualquier lista desconocida.
===========================================================================*/
CREATE OR ALTER PROCEDURE dbo.uspBM_GetMarketCatalogParameters
    @input        VARCHAR(200) = '',   -- búsqueda por nombre o código
    @organization INT          = 1,    -- idOrganization
    @user         VARCHAR(20)  = NULL, -- reservado (mismo contrato que uspBM_GetParametersCatalogMonitor)
    @list         VARCHAR(20)  = '',   -- '2' cultivos del mercado · '5' variedades
    @type         VARCHAR(20)  = '',   -- lista 2: SystemCodeCluster (como el SP original) · lista 5: cultivo, p. ej. '0203'
    @idMarket     INT          = NULL  -- BM_Market.id · 0 = todos los mercados (obligatorio en las listas 2 y 5)
AS
BEGIN
    SET NOCOUNT ON;

    -- Salida tipada: todas las ramas devuelven exactamente estos tipos, sin NULL
    -- (id INT, code VARCHAR(50), name VARCHAR(250), parentCode VARCHAR(50), typeCode VARCHAR(50)).
    IF @list = '2'
    BEGIN
        -- Cultivos con al menos una variedad con precios en el mercado. Mismos filtros que la
        -- lista 2 de uspBM_GetParametersCatalogMonitor. id = cultivo como INT (203), code = '0203'.
        SELECT TOP 5000
            CAST(TRY_CAST(MV.Valor AS INT) AS INT)          AS id,
            CAST(MV.Valor AS VARCHAR(50))                   AS code,
            ISNULL(CAST(MV.Nombre AS VARCHAR(250)), '')     AS name,
            CAST('' AS VARCHAR(50))                         AS parentCode,
            CAST('' AS VARCHAR(50))                         AS typeCode
        FROM dbo.IT_Multivalor AS MV
        WHERE MV.Tabla = 'BM_TCATCAT'
          AND MV.idOrganization = @organization
          AND MV.Activo = 1
          AND TRY_CAST(MV.Valor AS INT) IS NOT NULL
          AND (ISNULL(@type, '') IN ('', ' ') OR MV.SystemCodeCluster = @type)
          AND (ISNULL(LTRIM(RTRIM(@input)), '') = ''
               OR MV.Nombre LIKE '%' + @input + '%' OR MV.Valor LIKE '%' + @input + '%')
          AND EXISTS (SELECT 1
                      FROM dbo.BM_Catalog AS C
                      INNER JOIN dbo.IT_Multivalor AS TY
                          ON TY.Valor = C.type AND TY.Tabla = 'BM_TCATTY' AND TY.idOrganization = C.idOrganization
                      WHERE C.idOrganization = @organization
                        AND C.category = MV.Valor
                        AND C.active = 1
                        AND TY.systemCode = 'MMPP'
                        AND EXISTS (SELECT 1 FROM dbo.BM_MarketPrice AS P
                                    WHERE P.idCatalog = C.id
                                      AND (@idMarket = 0 OR P.idMarket = @idMarket)))
        ORDER BY MV.Nombre;
    END
    ELSE IF @list = '5'
    BEGIN
        -- Variedades con al menos un precio en el mercado. Mismos filtros y salida que la lista 5
        -- de uspBM_GetParametersCatalogMonitor: parentCode = cultivo, typeCode = tipo.
        -- @type acepta el code ('0203') o el id (203) de la lista 2.
        SELECT TOP 7000
            CAST(C.id AS INT)                               AS id,
            CAST(C.id AS VARCHAR(50))                       AS code,
            ISNULL(CAST(C.name AS VARCHAR(250)), '')        AS name,
            ISNULL(CAST(C.category AS VARCHAR(50)), '')     AS parentCode,
            ISNULL(CAST(C.type AS VARCHAR(50)), '')         AS typeCode
        FROM dbo.BM_Catalog AS C
        INNER JOIN dbo.IT_Multivalor AS MV
            ON MV.Valor = C.type AND MV.Tabla = 'BM_TCATTY' AND MV.idOrganization = C.idOrganization
        WHERE C.idOrganization = @organization
          AND C.active = 1
          AND MV.systemCode = 'MMPP'
          AND (ISNULL(@type, '') IN ('', ' ')
               OR C.category = @type
               OR TRY_CAST(C.category AS INT) = TRY_CAST(@type AS INT))
          AND (ISNULL(LTRIM(RTRIM(@input)), '') = ''
               OR C.name LIKE '%' + @input + '%' OR C.code LIKE '%' + @input + '%')
          AND EXISTS (SELECT 1 FROM dbo.BM_MarketPrice AS P
                      WHERE P.idCatalog = C.id
                        AND (@idMarket = 0 OR P.idMarket = @idMarket))
        ORDER BY C.name;
    END
    ELSE
    BEGIN
        -- Lista desconocida: resultado vacío con los mismos tipos (nunca sin result set).
        SELECT TOP 0
            CAST(0 AS INT)          AS id,
            CAST('' AS VARCHAR(50)) AS code,
            CAST('' AS VARCHAR(250)) AS name,
            CAST('' AS VARCHAR(50)) AS parentCode,
            CAST('' AS VARCHAR(50)) AS typeCode;
    END
END;
