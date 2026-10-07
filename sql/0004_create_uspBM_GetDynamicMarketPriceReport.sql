/* =====================================================================
   0004 — dbo.uspBM_GetDynamicMarketPriceReport: reporte de precios de UN mercado (D38)
   Copia de uspBM_GetDynamicCatalogPriceReport de producción (sql/uspBM_GetDynamicCatalogPriceReport.rollback.sql)
   con dos cambios: lee dbo.BM_MarketPrice en lugar de BM_CatalogPrice y filtra por @idMarket (obligatorio).
   Misma salida (summary, graphics), tipada: summary y graphics NVARCHAR(MAX) NOT NULL (JSON).
   El JSON de graphics se arma con FOR JSON y STRING_ESCAPE (no concatenando texto), así que
   siempre es JSON válido aunque un producto o unidad traiga comillas, \ o saltos de línea.
   Su contenido es el mismo que el del SP de producción; el texto puede variar en el escape
   (FOR JSON escribe "Soles\/KG", que al leerlo es "Soles/KG").
   Dos objetos: uspBM_GetDynamicMarketPriceReportData (cálculo; usa tablas #temp, por eso SQL Server
   no puede describir su salida) y uspBM_GetDynamicMarketPriceReport (público: lo llama con
   WITH RESULT SETS y fija el contrato). El SP de producción no se toca (D30).
   Con CIUDADES y @ubigeo NULL se agregan todas las regiones, igual que el SP original sin @ubigeo.
   Requiere 0001 y 0002_create_bm_market_price. Idempotente (CREATE OR ALTER).
   Rollback: 0004_create_uspBM_GetDynamicMarketPriceReport.rollback.sql

   EXEC dbo.uspBM_GetDynamicMarketPriceReport @from = '20260901', @to = '20260930', @catalogIds = '5030', @idMarket = 1;
   ===================================================================== */

/*======================================================================
  Descripción : Cálculo del reporte dinámico de precios por mercado (summary y graphics).
                Uso interno: el front llama a uspBM_GetDynamicMarketPriceReport.
  Autor       : JRUIZ
  Creado      : 29/09/2025
  Modificado  : 01/10/2026 -> etl-sisap -> copia de uspBM_GetDynamicCatalogPriceReport que lee
                BM_MarketPrice en lugar de BM_CatalogPrice y filtra por el parámetro obligatorio
                @idMarket (BM_Market). La salida es la misma. El SP original no se modifica.
                01/10/2026 -> etl-sisap -> graphics se arma con FOR JSON, STRING_AGG y
                STRING_ESCAPE en lugar de concatenar texto con FOR XML PATH: el JSON siempre
                es válido y tiene la misma estructura.
===========================================================================*/
CREATE OR ALTER PROCEDURE [dbo].[uspBM_GetDynamicMarketPriceReportData]
--declare
    @from        date          = '20250905',
    @to        date          = '20251001',
    @catalogIds   nvarchar(max) = '5129'   ,   -- de hasta 4 ids de BM_Catalog, ej: '101,205'
    @ubigeo   nvarchar(max) = NULL,     --  id de BM_Ubigeo; NULL o 0 = todos
    @idMarket   int                     --  id de BM_Market (obligatorio)


AS
BEGIN
    SET NOCOUNT ON;
    IF @to IS NOT NULL SET @to = DATEADD(DAY, 1, @to);  -- inclusivo

    ------------------------------------------------------------
    -- 0) Catálogos solicitados (CSV -> tabla)
    ------------------------------------------------------------
    DECLARE @Cat TABLE (id int PRIMARY KEY);
    IF @catalogIds IS NOT NULL AND LTRIM(RTRIM(@catalogIds)) <> ''
    BEGIN
        INSERT INTO @Cat(id)
        SELECT  TRY_CONVERT(int, value)
        FROM STRING_SPLIT(@catalogIds, ',')
        WHERE TRY_CONVERT(int, value) IS NOT NULL;
    END;

    ------------------------------------------------------------
    -- 1) BASE materializada (usa unitOfMeasure tal cual llega)
    ------------------------------------------------------------
	DROP TABLE IF EXISTS #countRegistros;
	SELECT
		idCatalog,
		idUbigeo,
		countRegistros = COUNT(1)
	INTO #countRegistros
	FROM BM_MarketPrice
	WHERE (@from IS NULL OR [date] >= @from)
	  AND (@to IS NULL OR [date] <  @to)
	  AND ( @ubigeo IS NULL OR @ubigeo = 0 OR idUbigeo = @ubigeo )
	  AND idMarket = @idMarket
	GROUP BY idCatalog, idUbigeo;

	DROP TABLE IF EXISTS #lastValues;
	SELECT
		cp.idCatalog,
		cp.idUbigeo,
		lastValue = TRY_CONVERT(decimal(18,6), cp.[mean])
	INTO #lastValues
	FROM (
		SELECT *,
			   ROW_NUMBER() OVER (PARTITION BY idCatalog, idUbigeo ORDER BY [date] DESC) AS rn
		FROM BM_MarketPrice
		WHERE (@from IS NULL OR [date] >= @from)
		  AND (@to IS NULL OR [date] <  @to)
		  AND ( @ubigeo IS NULL OR @ubigeo = 0 OR idUbigeo = @ubigeo )
		  AND idMarket = @idMarket
	) cp
	WHERE cp.rn = 1;


    DROP TABLE IF EXISTS #base;
	SELECT
		[date]        = CONVERT(date, cp.[date]),
		lastValue     = lv.lastValue,
		countRegistros = cr.countRegistros,
		pmax          = TRY_CONVERT(decimal(18,6), cp.[max]),
		pmin          = TRY_CONVERT(decimal(18,6), cp.[min]),
		pavg          = TRY_CONVERT(decimal(18,6), cp.[mean]),
		idCatalog     = c.id,
		producto      = c.[name],
		familia       = t.[Nombre],
		departamento  = u.[department],
		unidad        = cp.unitOfMeasure
	INTO #base
	FROM BM_MarketPrice cp
	JOIN BM_Catalog     c ON c.id = cp.idCatalog
	JOIN BM_Ubigeo      u ON u.ID = cp.idUbigeo
	JOIN IT_Multivalor  t ON t.Valor = c.category AND t.idOrganization = c.idOrganization
	LEFT JOIN #lastValues   lv ON lv.idCatalog = cp.idCatalog AND lv.idUbigeo = cp.idUbigeo
	LEFT JOIN #countRegistros cr ON cr.idCatalog = cp.idCatalog AND cr.idUbigeo = cp.idUbigeo
	WHERE (@from IS NULL OR cp.[date] >= @from)
	  AND (@to IS NULL OR cp.[date] <  @to)
	  AND (NOT EXISTS (SELECT 1 FROM @Cat) OR c.id IN (SELECT id FROM @Cat))
	  AND ( @ubigeo IS NULL OR @ubigeo = 0 OR cp.idUbigeo = @ubigeo )
	  AND cp.idMarket = @idMarket;



    IF NOT EXISTS (SELECT 1 FROM #base)
    BEGIN
        SELECT CAST(N'[]' AS nvarchar(max)) AS summary, CAST(N'[]' AS nvarchar(max)) AS graphics;
        RETURN;
    END;

    ------------------------------------------------------------
    -- 1.1) Universo de unidades tal cual llegan
    ------------------------------------------------------------
    DROP TABLE IF EXISTS #units;
    CREATE TABLE #units (ord int IDENTITY(1,1), unidad nvarchar(100) NULL);
    INSERT INTO #units(unidad)
    SELECT DISTINCT unidad FROM #base ORDER BY unidad;

    ------------------------------------------------------------
    -- 2) SUMMARY por (producto, unidad)
    ------------------------------------------------------------
    DROP TABLE IF EXISTS #prodAgg;
    SELECT
        idCatalog,
        producto,
        unidad,
		lastValue = MAX(lastValue),
        Promedio = AVG(pavg),
        Maximo   = MAX(pmax),
        Minimo   = MIN(pmin),
		Conteo = MAX(countRegistros)
    INTO #prodAgg
    FROM #base
    GROUP BY idCatalog, producto, unidad;

    DECLARE @summary nvarchar(max);
    SELECT @summary = (
        SELECT
            p.idCatalog,
            p.producto,
            nombreVariable = N'' + Producto,
            unidadMedida   = CASE WHEN p.unidad IS NULL OR p.unidad = N'' THEN N'Soles' ELSE N'Soles/' + p.unidad END,
            tipo           = N'Numérico',
            kpis = JSON_QUERY((
                SELECT v.metrica, v.valorNumerico
                FROM (VALUES
						 (N'Ultimo', p.lastValue),
                         (N'Promedio', p.Promedio),
                         (N'Maximo',   p.Maximo),
                         (N'Minimo',   p.Minimo),
                         (N'Entradas',   p.Conteo)
                ) AS v(metrica, valorNumerico)
                FOR JSON PATH
            ))
        FROM #prodAgg p
        ORDER BY p.producto, p.unidad
        FOR JSON PATH
    );

    ------------------------------------------------------------
    -- 3) GRAPHICS categóricos (Producto, Departamento, Familia) – datasets por unidad tal cual
    ------------------------------------------------------------
    DROP TABLE IF EXISTS #labels;
    CREATE TABLE #labels(idCategoria int, ord int IDENTITY(1,1), label nvarchar(400));

    INSERT INTO #labels(idCategoria, label)
    --SELECT 1, departamento FROM (SELECT DISTINCT departamento FROM #base WHERE departamento IS NOT NULL) d
    --UNION ALL
    SELECT 3, producto     FROM (SELECT DISTINCT producto     FROM #base WHERE producto     IS NOT NULL) p;
    --UNION ALL
    --SELECT 5, familia      FROM (SELECT DISTINCT familia      FROM #base WHERE familia      IS NOT NULL) f;

    DROP TABLE IF EXISTS #aggCat;
    CREATE TABLE #aggCat
    (
        idCategoria int,
        ordLabel    int,
        unidad      nvarchar(100) NULL,
		Ultimo   decimal(38,10),
        Maximo      decimal(38,10),
        Minimo      decimal(38,10),
        Promedio    decimal(38,10),
		Conteo      decimal(38,10)
    );

    INSERT INTO #aggCat(idCategoria, ordLabel, unidad,Ultimo, Maximo, Minimo, Promedio)
    SELECT L.idCategoria, L.ord, U.unidad, MAX(b.lastValue),
           MAX(b.pmax), MIN(b.pmin), AVG(b.pavg)
    FROM #labels L
    CROSS JOIN #units U
    LEFT JOIN #base b
      ON (
            (L.idCategoria=1 AND b.departamento = L.label)
         OR (L.idCategoria=3 AND b.producto     = L.label)
         OR (L.idCategoria=5 AND b.familia      = L.label)
         )
     AND ((b.unidad IS NULL AND U.unidad IS NULL) OR b.unidad = U.unidad)
    GROUP BY L.idCategoria, L.ord, U.unidad;

    -- Una fila por (dimensión, label, unidad, métrica)
    DROP TABLE IF EXISTS #aggCatMetric;
    SELECT A.idCategoria, A.ordLabel, A.unidad, M.metrica, M.valor
    INTO #aggCatMetric
    FROM #aggCat A
    CROSS APPLY (VALUES (N'Último', A.Ultimo), (N'Máximo', A.Maximo),
                        (N'Mínimo', A.Minimo), (N'Promedio', A.Promedio)) M(metrica, valor);

    -- Gráficos de la salida: el temporal (ord 0) se agrega en la sección 4
    DROP TABLE IF EXISTS #graphics;
    CREATE TABLE #graphics (ord int, idCategoria int, title nvarchar(60), metricas nvarchar(max));

    -- JSON con FOR JSON y STRING_ESCAPE: los textos van escapados y la salida siempre es JSON válido
    INSERT INTO #graphics(ord, idCategoria, title, metricas)
    SELECT D.idCategoria, D.idCategoria, D.title,
           (
             SELECT
                 M.metrica,
                 labels = JSON_QUERY((
                     SELECT N'[' + STRING_AGG(CAST(N'"' + STRING_ESCAPE(L.label, 'json') + N'"' AS nvarchar(max)), N',')
                                   WITHIN GROUP (ORDER BY L.ord) + N']'
                     FROM #labels L
                     WHERE L.idCategoria = D.idCategoria
                 )),
                 datasets = JSON_QUERY(ISNULL((
                     SELECT
                         label = CASE WHEN U.unidad IS NULL OR U.unidad = N'' THEN N'Soles' ELSE N'Soles/' + U.unidad END,
                         data  = JSON_QUERY((
                             SELECT N'[' + STRING_AGG(CAST(CAST(ISNULL(X.valor, 0) AS nvarchar(50)) AS nvarchar(max)), N',')
                                           WITHIN GROUP (ORDER BY X.ordLabel) + N']'
                             FROM #aggCatMetric X
                             WHERE X.idCategoria = D.idCategoria
                               AND X.metrica = M.metrica
                               AND ((X.unidad IS NULL AND U.unidad IS NULL) OR X.unidad = U.unidad)
                         ))
                     FROM #units U
                     ORDER BY U.ord
                     FOR JSON PATH
                 ), N'[]'))
             FROM (VALUES (N'Último', 1), (N'Promedio', 2), (N'Mínimo', 3), (N'Máximo', 4)) M(metrica, ord)
             ORDER BY M.ord
             FOR JSON PATH
           )
    FROM (VALUES (1, N'DEPARTAMENTO'), (3, N'PRODUCTO'), (5, N'FAMILIA DE PRODUCTO')) D(idCategoria, title)
    WHERE EXISTS (SELECT 1 FROM #labels L WHERE L.idCategoria = D.idCategoria);

    ------------------------------------------------------------
    -- 4) GRÁFICO TEMPORAL por (producto, unidad tal cual) con buckets
    ------------------------------------------------------------
    IF EXISTS (SELECT 1 FROM @Cat)
    BEGIN
        SET DATEFIRST 1; -- lunes
        DECLARE @minDate date = (SELECT MIN([date]) FROM #base WHERE idCatalog IN (SELECT id FROM @Cat));
        DECLARE @maxDate date = (SELECT MAX([date]) FROM #base WHERE idCatalog IN (SELECT id FROM @Cat));
        DECLARE @rangeDays int = CASE WHEN @minDate IS NULL OR @maxDate IS NULL THEN 0 ELSE DATEDIFF(DAY,@minDate,@maxDate) END;

        DECLARE @granularity char(1) =
            CASE
                WHEN @rangeDays > 720 THEN 'Y'
                WHEN @rangeDays > 365 THEN 'S'
                WHEN @rangeDays >  90 THEN 'M'
                WHEN @rangeDays >  20 THEN 'W'
                ELSE 'D'
            END;

        DROP TABLE IF EXISTS #buckets;
        CREATE TABLE #buckets
        (
            ord   int IDENTITY(1,1) PRIMARY KEY,
            label nvarchar(20),
            y     int NULL,
            m     int NULL,
            w     int NULL,
            sem   int NULL,
            d     date NULL
        );

    IF @granularity = 'Y'
BEGIN
    INSERT INTO #buckets(label, y)
    SELECT DISTINCT CONVERT(char(4), YEAR([date])), YEAR([date])
    FROM #base WHERE idCatalog IN (SELECT id FROM @Cat)
    ORDER BY 2;
END
ELSE IF @granularity = 'S'
BEGIN
    INSERT INTO #buckets(label, y, sem)
    SELECT DISTINCT RIGHT(CONVERT(char(4), YEAR([date])), 2) + N'-S' + CAST(CASE WHEN MONTH([date])<=6 THEN 1 ELSE 2 END AS nvarchar(1)),
                    YEAR([date]), CASE WHEN MONTH([date])<=6 THEN 1 ELSE 2 END
    FROM #base WHERE idCatalog IN (SELECT id FROM @Cat)
    ORDER BY 2,3;
END
ELSE IF @granularity = 'M'
BEGIN
    INSERT INTO #buckets(label, y, m)
    SELECT DISTINCT RIGHT(CONVERT(char(4), YEAR([date])), 2) + '-' + RIGHT('00' + CAST(MONTH([date]) AS varchar(2)), 2),  YEAR([date]),  MONTH([date])
    FROM #base WHERE idCatalog IN (SELECT id FROM @Cat)
    ORDER BY 2,3;
END
ELSE IF @granularity = 'W'
BEGIN
    INSERT INTO #buckets(label, y, w)
    SELECT DISTINCT N'S-' + RIGHT('00' + CAST(DATEPART(ISO_WEEK,[date]) AS varchar(2)),2),
                    YEAR([date]), DATEPART(ISO_WEEK,[date])
    FROM #base WHERE idCatalog IN (SELECT id FROM @Cat)
    ORDER BY 2,3;
END
ELSE
BEGIN
    INSERT INTO #buckets(label, d)
    SELECT DISTINCT FORMAT([date], 'dd/MM') AS label,   [date]
    FROM #base WHERE idCatalog IN (SELECT id FROM @Cat)
    ORDER BY 2;
END


-- ============================================================
-- LIMITAR A MÁXIMO 10 PUNTOS (toma equidistantes)
-- SIEMPRE incluye primer y último punto
-- ============================================================
DECLARE @totalBuckets INT = (SELECT COUNT(*) FROM #buckets);
DECLARE @maxPoints INT = 8;

IF @totalBuckets > @maxPoints
BEGIN
    DROP TABLE IF EXISTS #bucketsLimited;
    CREATE TABLE #bucketsLimited
    (
        label nvarchar(20),
        y     int NULL,
        m     int NULL,
        w     int NULL,
        sem   int NULL,
        d     date NULL,
        originalOrd int
    );
    
    DECLARE @minOrd INT = (SELECT MIN(ord) FROM #buckets);
    DECLARE @maxOrd INT = (SELECT MAX(ord) FROM #buckets);
    
    -- Insertar primer punto
    INSERT INTO #bucketsLimited(label, y, m, w, sem, d, originalOrd)
    SELECT label, y, m, w, sem, d, ord
    FROM #buckets
    WHERE ord = @minOrd;
    
    -- Insertar puntos intermedios equidistantes (8 puntos)
    DECLARE @step FLOAT = CAST(@maxOrd - @minOrd AS FLOAT) / (@maxPoints - 1);
    DECLARE @i INT = 1;
    
    WHILE @i < (@maxPoints - 1)
    BEGIN
        DECLARE @targetOrd FLOAT = @minOrd + (@i * @step);
        
        INSERT INTO #bucketsLimited(label, y, m, w, sem, d, originalOrd)
        SELECT TOP 1 label, y, m, w, sem, d, ord
        FROM #buckets
        WHERE ord > @minOrd 
          AND ord < @maxOrd
          AND ord NOT IN (SELECT originalOrd FROM #bucketsLimited)
        ORDER BY ABS(ord - @targetOrd);
        
        SET @i = @i + 1;
    END
    
    -- Insertar último punto
    INSERT INTO #bucketsLimited(label, y, m, w, sem, d, originalOrd)
    SELECT label, y, m, w, sem, d, ord
    FROM #buckets
    WHERE ord = @maxOrd;
    
    -- Limpiar y recrear #buckets con los datos limitados
    TRUNCATE TABLE #buckets;
    
    INSERT INTO #buckets(label, y, m, w, sem, d)
    SELECT label, y, m, w, sem, d
    FROM #bucketsLimited
    ORDER BY originalOrd;
    
    DROP TABLE IF EXISTS #bucketsLimited;
END
-- ============================================================



        DECLARE @labelsTime nvarchar(max) = (
            SELECT N'[' + STRING_AGG(CAST(N'"' + STRING_ESCAPE(b.label, 'json') + N'"' AS nvarchar(max)), N',')
                          WITHIN GROUP (ORDER BY b.ord) + N']'
            FROM #buckets b
        );

        -- Agregado temporal por (catalogo, unidad tal cual, bucket)
		DROP TABLE IF EXISTS #timeAgg;
		CREATE TABLE #timeAgg
		(
			idCatalog int,
			producto  nvarchar(400),
			unidad    nvarchar(100) NULL,
			ord       int,
			Ultimo    decimal(38,10),
			Maximo    decimal(38,10),
			Minimo    decimal(38,10),
			Promedio  decimal(38,10)
		);

		--  Calcula primero la fecha más reciente (maxDate) de cada bucket y catálogo
		;WITH CTE_MaxDate AS (
			SELECT 
				b.idCatalog,
				b.unidad,
				k.ord,
				MAX(b.[date]) AS maxDate
			FROM #buckets k
			JOIN #base b
				ON b.idCatalog IN (SELECT id FROM @Cat)
			   AND (
					(@granularity='Y' AND YEAR(b.[date]) = k.y)
				 OR (@granularity='S' AND YEAR(b.[date]) = k.y AND (CASE WHEN MONTH(b.[date])<=6 THEN 1 ELSE 2 END) = k.sem)
				 OR (@granularity='M' AND YEAR(b.[date]) = k.y AND MONTH(b.[date]) = k.m)
				 OR (@granularity='W' AND YEAR(b.[date]) = k.y AND DATEPART(ISO_WEEK,b.[date]) = k.w)
				 OR (@granularity='D' AND b.[date] = k.d)
				)
			GROUP BY b.idCatalog, b.unidad, k.ord
		)

		INSERT INTO #timeAgg(idCatalog, producto, unidad, ord, Ultimo, Maximo, Minimo, Promedio)
		SELECT 
			b.idCatalog,
			MAX(prod.producto) AS producto,
			b.unidad,
			k.ord,
			MAX(CASE WHEN b.[date] = md.maxDate THEN b.pavg END) AS Ultimo,
			MAX(b.pmax) AS Maximo,
			MIN(b.pmin) AS Minimo,
			AVG(b.pavg) AS Promedio
		FROM #buckets k
		JOIN #base b
			ON b.idCatalog IN (SELECT id FROM @Cat)
		   AND (
				(@granularity='Y' AND YEAR(b.[date]) = k.y)
			 OR (@granularity='S' AND YEAR(b.[date]) = k.y AND (CASE WHEN MONTH(b.[date])<=6 THEN 1 ELSE 2 END) = k.sem)
			 OR (@granularity='M' AND YEAR(b.[date]) = k.y AND MONTH(b.[date]) = k.m)
			 OR (@granularity='W' AND YEAR(b.[date]) = k.y AND DATEPART(ISO_WEEK, b.[date]) = k.w)
			 OR (@granularity='D' AND b.[date] = k.d)
		   )
		JOIN CTE_MaxDate md
		   ON md.idCatalog = b.idCatalog AND md.unidad = b.unidad AND md.ord = k.ord
		JOIN (SELECT DISTINCT idCatalog, producto FROM #base) prod
		   ON prod.idCatalog = b.idCatalog
		GROUP BY b.idCatalog, b.unidad, k.ord;




        -- Series (producto [Soles/UNIDAD]) con UNIDAD tal cual llega (o 'Soles' si null/'')
        DROP TABLE IF EXISTS #seriesNames;
        CREATE TABLE #seriesNames(idCatalog int, unidad nvarchar(100) NULL, serie nvarchar(260));

        INSERT INTO #seriesNames(idCatalog, unidad, serie)
        SELECT DISTINCT idCatalog, unidad,
               (SELECT TOP 1 producto FROM #base WHERE idCatalog = TA.idCatalog) + N' [' +
               CASE WHEN TA.unidad IS NULL OR TA.unidad = N'' THEN N'Soles' ELSE N'Soles/' + TA.unidad END + N']'
        FROM #timeAgg TA;

        -- Una fila por (catálogo, unidad, bucket, métrica)
        DROP TABLE IF EXISTS #timeAggMetric;
        SELECT TA.idCatalog, TA.unidad, TA.ord, M.metrica, M.valor
        INTO #timeAggMetric
        FROM #timeAgg TA
        CROSS APPLY (VALUES (N'Último', TA.Ultimo), (N'Máximo', TA.Maximo),
                            (N'Mínimo', TA.Minimo), (N'Promedio', TA.Promedio)) M(metrica, valor);

        DECLARE @titleTime nvarchar(60) =
            CASE @granularity
                WHEN 'Y' THEN N'PRECIO POR AÑO'
                WHEN 'S' THEN N'PRECIO POR SEMESTRE'
                WHEN 'M' THEN N'PRECIO POR MES'
                WHEN 'W' THEN N'PRECIO POR SEMANA'
                ELSE           N'PRECIO POR DÍA'
            END;

        -- El gráfico temporal va primero en graphics (ord 0)
        INSERT INTO #graphics(ord, idCategoria, title, metricas)
        SELECT 0, 99, @titleTime,
               (
                 SELECT
                     M.metrica,
                     labels   = JSON_QUERY(@labelsTime),
                     datasets = JSON_QUERY(ISNULL((
                         SELECT
                             label = S.serie,
                             data  = JSON_QUERY((
                                 SELECT N'[' + STRING_AGG(CAST(CAST(ISNULL(X.valor, 0) AS nvarchar(50)) AS nvarchar(max)), N',')
                                               WITHIN GROUP (ORDER BY X.ord) + N']'
                                 FROM #timeAggMetric X
                                 WHERE X.idCatalog = S.idCatalog
                                   AND X.metrica = M.metrica
                                   AND ((X.unidad IS NULL AND S.unidad IS NULL) OR X.unidad = S.unidad)
                             ))
                         FROM #seriesNames S
                         ORDER BY S.idCatalog, S.unidad
                         FOR JSON PATH
                     ), N'[]'))
                 FROM (VALUES (N'Último', 1), (N'Promedio', 2), (N'Máximo', 3), (N'Mínimo', 4)) M(metrica, ord)
                 ORDER BY M.ord
                 FOR JSON PATH
               );
    END

    ------------------------------------------------------------
    -- 5) OUTPUT final
    ------------------------------------------------------------
    DECLARE @graphics nvarchar(max) = (
        SELECT g.idCategoria, g.title, metricas = JSON_QUERY(g.metricas)
        FROM #graphics g
        ORDER BY g.ord
        FOR JSON PATH
    );

    SELECT
        CAST(ISNULL(@summary, N'[]') AS nvarchar(max))  AS [summary],
        CAST(ISNULL(@graphics, N'[]') AS nvarchar(max)) AS [graphics];

		--ACA TODO JUNTO SI GUSTAS HULKISTO
 --   SELECT (
	--	SELECT
	--		JSON_QUERY(@summary) AS summary,
	--		JSON_QUERY(@graphics)      AS graphics
	--	FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
	--) AS ReporteJSON;


    ------------------------------------------------------------
    -- Limpieza
    ------------------------------------------------------------
    DROP TABLE IF EXISTS #base;
    DROP TABLE IF EXISTS #units;
    DROP TABLE IF EXISTS #prodAgg;
    DROP TABLE IF EXISTS #labels;
    DROP TABLE IF EXISTS #aggCat;
    DROP TABLE IF EXISTS #aggCatMetric;
    DROP TABLE IF EXISTS #graphics;
    DROP TABLE IF EXISTS #buckets;
    DROP TABLE IF EXISTS #timeAgg;
    DROP TABLE IF EXISTS #seriesNames;
    DROP TABLE IF EXISTS #timeAggMetric;
	DROP TABLE IF EXISTS #lastValues
END

GO

/*======================================================================
  Descripción : Reporte dinámico de precios por mercado (summary y graphics), con salida tipada
  Autor       : JRUIZ
  Creado      : 29/09/2025
  Modificado  : 01/10/2026 -> etl-sisap -> punto de entrada del front. Llama a
                uspBM_GetDynamicMarketPriceReportData con WITH RESULT SETS: devuelve siempre
                summary NVARCHAR(MAX) NOT NULL y graphics NVARCHAR(MAX) NOT NULL (JSON).
                Mismos parámetros que uspBM_GetDynamicCatalogPriceReport más @idMarket.
===========================================================================*/
CREATE OR ALTER PROCEDURE [dbo].[uspBM_GetDynamicMarketPriceReport]
    @from        date          = '20250905',
    @to          date          = '20251001',
    @catalogIds  nvarchar(max) = '5129',     -- ids de BM_Catalog separados por coma, ej: '101,205'
    @ubigeo      nvarchar(max) = NULL,       -- id de BM_Ubigeo; NULL o 0 = todos
    @idMarket    int                         -- id de BM_Market (obligatorio)
AS
BEGIN
    SET NOCOUNT ON;

    EXEC dbo.uspBM_GetDynamicMarketPriceReportData
        @from       = @from,
        @to         = @to,
        @catalogIds = @catalogIds,
        @ubigeo     = @ubigeo,
        @idMarket   = @idMarket
    WITH RESULT SETS
    ((
        summary  nvarchar(max) NOT NULL,
        graphics nvarchar(max) NOT NULL
    ));
END
