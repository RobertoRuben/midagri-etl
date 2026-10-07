-- ROLLBACK: definición original en producción (capturada el 2026-09-23). Ejecutar si hay que revertir el SP.


-- =============================================
-- Author:		JRUIZ
-- Create date: 29-09-2025
-- Description:	Listar Ubigeos
-- =============================================

CREATE OR ALTER PROCEDURE [dbo].[uspBM_GetDynamicCatalogPriceReport]
--declare
    @from        date          = '20250905',
    @to        date          = '20251001',
    @catalogIds   nvarchar(max) = '5129'   ,   -- de hasta 4 ids de BM_Catalog, ej: '101,205'
    @ubigeo   nvarchar(max) = NULL      --  de hasta 4 ids de BM_Catalog, ej: '101,205'


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
	FROM BM_CatalogPrice
	WHERE (@from IS NULL OR [date] >= @from)
	  AND (@to IS NULL OR [date] <  @to)
	  AND ( @ubigeo IS NULL OR @ubigeo = 0 OR idUbigeo = @ubigeo )
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
		FROM BM_CatalogPrice
		WHERE (@from IS NULL OR [date] >= @from)
		  AND (@to IS NULL OR [date] <  @to)
		  AND ( @ubigeo IS NULL OR @ubigeo = 0 OR idUbigeo = @ubigeo )
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
	FROM BM_CatalogPrice cp
	JOIN BM_Catalog     c ON c.id = cp.idCatalog
	JOIN BM_Ubigeo      u ON u.ID = cp.idUbigeo
	JOIN IT_Multivalor  t ON t.Valor = c.category AND t.idOrganization = c.idOrganization
	LEFT JOIN #lastValues   lv ON lv.idCatalog = cp.idCatalog AND lv.idUbigeo = cp.idUbigeo
	LEFT JOIN #countRegistros cr ON cr.idCatalog = cp.idCatalog AND cr.idUbigeo = cp.idUbigeo
	WHERE (@from IS NULL OR cp.[date] >= @from)
	  AND (@to IS NULL OR cp.[date] <  @to)
	  AND (NOT EXISTS (SELECT 1 FROM @Cat) OR c.id IN (SELECT id FROM @Cat))
	  AND ( @ubigeo IS NULL OR @ubigeo = 0 OR cp.idUbigeo = @ubigeo );



    IF NOT EXISTS (SELECT 1 FROM #base)
    BEGIN
        SELECT JSON_QUERY('[]') AS summary, JSON_QUERY('[]') AS graphics;
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

    -- labels JSON por dimensión
    DROP TABLE IF EXISTS #labelsJson;
    CREATE TABLE #labelsJson (idCategoria int PRIMARY KEY, labelsJson nvarchar(max));

    INSERT INTO #labelsJson(idCategoria, labelsJson)
    SELECT idCategoria,
           N'[' + STUFF((
                SELECT ',' + '"' + REPLACE(label,'"','\"') + '"'
                FROM #labels L2
                WHERE L2.idCategoria = L.idCategoria
                ORDER BY L2.ord
                FOR XML PATH(''), TYPE
           ).value('.', 'nvarchar(max)'), 1, 1, '') + N']'
    FROM (SELECT DISTINCT idCategoria FROM #labels) L;

    -- datasets por métrica y unidad
    DROP TABLE IF EXISTS #datasetsJson;
    CREATE TABLE #datasetsJson (idCategoria int, metrica nvarchar(20), datasets nvarchar(max));

    INSERT INTO #datasetsJson(idCategoria, metrica, datasets)
    SELECT A.idCategoria, M.metrica,
           STUFF((
                SELECT N',' + N'{"label":"' +
                       CASE WHEN U.unidad IS NULL OR U.unidad = N'' THEN N'Soles' ELSE N'Soles/' + REPLACE(U.unidad,'"','\"') END
                       + N'","data":' +
                       (SELECT N'[' + STUFF((
                                SELECT N',' + CAST(ISNULL(
                                       CASE M.metrica
									     WHEN N'Último'   THEN X.Ultimo
                                         WHEN N'Máximo'   THEN X.Maximo
                                         WHEN N'Mínimo'   THEN X.Minimo
                                         WHEN N'Promedio' THEN X.Promedio
                                         --WHEN N'Entradas' THEN X.Conteo

                                       END, 0) AS nvarchar(50))
                                FROM #aggCat X
                                WHERE X.idCategoria = A.idCategoria
                                  AND ((X.unidad IS NULL AND U.unidad IS NULL) OR X.unidad = U.unidad)
                                ORDER BY X.ordLabel
                                FOR XML PATH(''), TYPE
                        ).value('.', 'nvarchar(max)'), 1, 1, '') + N']')
                       + N'}'
                FROM #units U
                FOR XML PATH(''), TYPE
           ).value('.', 'nvarchar(max)'), 1, 1, '') AS datasets
    FROM (SELECT DISTINCT idCategoria FROM #labels) A
    CROSS APPLY (VALUES (N'Último'),(N'Máximo'),(N'Mínimo'),(N'Promedio')) M(metrica);

    DROP TABLE IF EXISTS #metricasCat;
    CREATE TABLE #metricasCat (idCategoria int, metricas nvarchar(max));

    INSERT INTO #metricasCat(idCategoria, metricas)
    SELECT L.idCategoria,
           N'[' +
           STUFF((
             SELECT N',' + N'{"metrica":"' + D.metrica + N'","labels":' + LJ.labelsJson + N',"datasets":[' + ISNULL(D.datasets,N'') + N']}'
             FROM #datasetsJson D
             JOIN #labelsJson  LJ ON LJ.idCategoria = D.idCategoria
             WHERE D.idCategoria = L.idCategoria
             ORDER BY CASE D.metrica 
					WHEN N'Último' THEN 1
					WHEN N'Promedio' THEN 2 
					WHEN N'Mínimo' THEN 3
					ELSE 4 END
             FOR XML PATH(''), TYPE
           ).value('.', 'nvarchar(max)'), 1, 1, '')
           + N']'
    FROM (SELECT DISTINCT idCategoria FROM #labels) L;

    DECLARE @graphicsCat nvarchar(max);
    SELECT @graphicsCat =
        N'[' + STUFF((
           SELECT N',' + N'{"idCategoria":' + CAST(D.idCategoria AS nvarchar(10))
                        + N',"title":"' + D.title + N'","metricas":' + MC.metricas + N'}'
           FROM (VALUES (1, N'DEPARTAMENTO'),(3, N'PRODUCTO'),(5, N'FAMILIA DE PRODUCTO')) D(idCategoria, title)
           JOIN #metricasCat MC ON MC.idCategoria = D.idCategoria
           
           FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 1, '') + N']';

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



        DECLARE @labelsTime nvarchar(max) =
            N'[' + STUFF((
                SELECT ',' + '"' + b.label + '"'
                FROM #buckets b ORDER BY b.ord
                FOR XML PATH(''), TYPE
            ).value('.', 'nvarchar(max)'), 1, 1, '') + N']';

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

        DROP TABLE IF EXISTS #timeDatasets;
        CREATE TABLE #timeDatasets(metrica nvarchar(20), datasets nvarchar(max));

        INSERT INTO #timeDatasets(metrica, datasets)
        SELECT M.metrica,
               STUFF((
                   SELECT N',' + N'{"label":"' + REPLACE(S.serie,'"','\"') + N'","data":' +
                          (SELECT N'[' + STUFF((
                               SELECT N',' + CAST(ISNULL(
                                       CASE M.metrica
									   	 WHEN N'Último'   THEN TA.Ultimo
                                         WHEN N'Máximo'   THEN TA.Maximo
                                         WHEN N'Mínimo'   THEN TA.Minimo
                                         WHEN N'Promedio' THEN TA.Promedio
                                       END, 0) AS nvarchar(50))
                               FROM #timeAgg TA
                               WHERE TA.idCatalog=S.idCatalog
                                 AND ((TA.unidad IS NULL AND S.unidad IS NULL) OR TA.unidad = S.unidad)
                               ORDER BY TA.ord
                               FOR XML PATH(''), TYPE
                          ).value('.', 'nvarchar(max)'), 1, 1, '') + N']')
                          + N'}'
                   FROM #seriesNames S
                   FOR XML PATH(''), TYPE
               ).value('.', 'nvarchar(max)'), 1, 1, '') AS datasets
        FROM (VALUES (N'Último'),(N'Máximo'),(N'Mínimo'),(N'Promedio')) M(metrica);

        DECLARE @metricasTime nvarchar(max) =
            N'[' +
            STUFF((
                SELECT N',' + N'{"metrica":"' + T.metrica + N'","labels":' + @labelsTime + N',"datasets":[' + ISNULL(T.datasets,N'') + N']}'
                FROM #timeDatasets T
                ORDER BY CASE T.metrica 
					WHEN N'Último' THEN 1
					WHEN N'Promedio' THEN 2 
					WHEN N'Máximo' THEN 3
					ELSE 4 END
                FOR XML PATH(''), TYPE
            ).value('.', 'nvarchar(max)'), 1, 1, '')
            + N']';

        DECLARE @titleTime nvarchar(60) =
            CASE @granularity
                WHEN 'Y' THEN N'PRECIO POR AÑO'
                WHEN 'S' THEN N'PRECIO POR SEMESTRE'
                WHEN 'M' THEN N'PRECIO POR MES'
                WHEN 'W' THEN N'PRECIO POR SEMANA'
                ELSE           N'PRECIO POR DÍA'
            END;

        DECLARE @graphicTime nvarchar(max) =
            N'{"idCategoria":99,"title":"' + @titleTime + N'","metricas":' + @metricasTime + N'}';

			-- Primero aseguramos no null
			SET @graphicsCat = ISNULL(@graphicsCat, N'[]');

			-- Insertamos el gráfico de tiempo como primer elemento
			SET @graphicsCat =
				STUFF(@graphicsCat, 2, 0, @graphicTime + N',');


    END

    ------------------------------------------------------------
    -- 5) OUTPUT final
    ------------------------------------------------------------
    SELECT
        JSON_QUERY(@summary) AS [summary],
        JSON_QUERY(@graphicsCat)      AS [graphics];

		--ACA TODO JUNTO SI GUSTAS HULKISTO
 --   SELECT (
	--	SELECT
	--		JSON_QUERY(@summary) AS summary,
	--		JSON_QUERY(@graphicsCat)      AS graphics
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
    DROP TABLE IF EXISTS #labelsJson;
    DROP TABLE IF EXISTS #datasetsJson;
    DROP TABLE IF EXISTS #metricasCat;
    DROP TABLE IF EXISTS #buckets;
    DROP TABLE IF EXISTS #timeAgg;
    DROP TABLE IF EXISTS #seriesNames;
    DROP TABLE IF EXISTS #timeDatasets;
	DROP TABLE IF EXISTS #lastValues
END
