/* =====================================================================
   Verificación del SQL que genera el Excel de faltantes (catalog-gaps)
   Entorno: QAS = BDFarmex_Agri (equivalente de BDFARMEX). NO BDExtech_MultiGestion.
   Ejecutar por partes, en orden.
   Origen: docs/faltantes_sisap_20251001_20260923.xlsx (13 variedades)
   ===================================================================== */

/* ---------------------------------------------------------------------
   PARTE 1 — Sintaxis (no ejecuta nada, no escribe nada)
   Esperado: "Commands completed successfully." sin errores.
   --------------------------------------------------------------------- */
SET PARSEONLY ON;
GO

-- IT_Multivalor: en el periodo no hay cultivos nuevos; caso de prueba con ' " & en el nombre
IF NOT EXISTS (SELECT 1 FROM dbo.IT_Multivalor WHERE Tabla='BM_TCATCAT' AND Valor='0699' AND idOrganization=1) EXEC dbo.uspIT_GuardarActualizarMultivalores @xmlMultivalores=N'<root><item MultivalorId="0" Valor="0699" Nombre="Ají ''charapita'' &amp; &quot;prueba&quot;" Valor1="MIDAGRI" SystemCodeCluster="CROP"/></root>', @idMultitabla=49, @tablaMultitabla='BM_TCATCAT', @usuario='etl-sisap', @idOrganization=1;

-- BM_Catalog: las 13 filas del Excel
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='010601' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0106', @subCategory=NULL, @code='010601', @name='Maca', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='030301' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0303', @subCategory=NULL, @code='030301', @name='Haba verde criolla', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='040801' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0408', @subCategory=NULL, @code='040801', @name='Cañihua', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='040803' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0408', @subCategory=NULL, @code='040803', @name='Kiwicha', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='061506' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0615', @subCategory=NULL, @code='061506', @name='Mango chato', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='061522' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0615', @subCategory=NULL, @code='061522', @name='Mango pico de loro', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='061523' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0615', @subCategory=NULL, @code='061523', @name='Mango rosado', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='062616' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0626', @subCategory=NULL, @code='062616', @name='Palta queen', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='062617' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0626', @subCategory=NULL, @code='062617', @name='Palta villa campa', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='062619' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0626', @subCategory=NULL, @code='062619', @name='Palta ettinger', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='063825' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0638', @subCategory=NULL, @code='063825', @name='Zapote', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='090403' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0904', @subCategory=NULL, @code='090403', @name='Hoja de coca tingo maria', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='090416' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0904', @subCategory=NULL, @code='090416', @name='Hoja de coca ayacucho', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
GO
SET PARSEONLY OFF;
GO

/* ---------------------------------------------------------------------
   PARTE 2 — Nombres de parámetros de los SP
   PARSEONLY no valida que los @parámetros existan; esto sí.
   Esperado: 0 filas en la primera consulta; la segunda se revisa (ver nota).
   --------------------------------------------------------------------- */
-- Parámetros que usamos y el SP NO tiene
SELECT u.p AS parametro_inexistente, u.sp
FROM (VALUES
  ('dbo.uspBM_SaveUpdateCatalogo','@id'),('dbo.uspBM_SaveUpdateCatalogo','@process'),('dbo.uspBM_SaveUpdateCatalogo','@type'),
  ('dbo.uspBM_SaveUpdateCatalogo','@category'),('dbo.uspBM_SaveUpdateCatalogo','@subCategory'),('dbo.uspBM_SaveUpdateCatalogo','@code'),
  ('dbo.uspBM_SaveUpdateCatalogo','@name'),('dbo.uspBM_SaveUpdateCatalogo','@nickname'),('dbo.uspBM_SaveUpdateCatalogo','@description'),
  ('dbo.uspBM_SaveUpdateCatalogo','@unitOfMeasure'),('dbo.uspBM_SaveUpdateCatalogo','@netWeight'),('dbo.uspBM_SaveUpdateCatalogo','@maxPackaging'),
  ('dbo.uspBM_SaveUpdateCatalogo','@format'),('dbo.uspBM_SaveUpdateCatalogo','@gauge'),('dbo.uspBM_SaveUpdateCatalogo','@price'),
  ('dbo.uspBM_SaveUpdateCatalogo','@pieceCount'),('dbo.uspBM_SaveUpdateCatalogo','@dimension'),('dbo.uspBM_SaveUpdateCatalogo','@grossWeight'),
  ('dbo.uspBM_SaveUpdateCatalogo','@unitMeasureWeight'),('dbo.uspBM_SaveUpdateCatalogo','@idParent'),('dbo.uspBM_SaveUpdateCatalogo','@idOrganization'),
  ('dbo.uspBM_SaveUpdateCatalogo','@active'),('dbo.uspBM_SaveUpdateCatalogo','@User'),('dbo.uspBM_SaveUpdateCatalogo','@imagenUrl'),
  ('dbo.uspIT_GuardarActualizarMultivalores','@xmlMultivalores'),('dbo.uspIT_GuardarActualizarMultivalores','@idMultitabla'),
  ('dbo.uspIT_GuardarActualizarMultivalores','@tablaMultitabla'),('dbo.uspIT_GuardarActualizarMultivalores','@usuario'),
  ('dbo.uspIT_GuardarActualizarMultivalores','@idOrganization')
) AS u(sp, p)
WHERE NOT EXISTS (SELECT 1 FROM sys.parameters sp WHERE sp.object_id = OBJECT_ID(u.sp) AND sp.name = u.p);

-- Parámetros que el SP tiene y NO enviamos
SELECT OBJECT_NAME(p.object_id) AS sp, p.name AS parametro_faltante
FROM sys.parameters p
WHERE p.object_id IN (OBJECT_ID('dbo.uspBM_SaveUpdateCatalogo'), OBJECT_ID('dbo.uspIT_GuardarActualizarMultivalores'))
  AND p.has_default_value = 0 AND p.is_output = 0
  AND p.name NOT IN ('@id','@process','@type','@category','@subCategory','@code','@name','@nickname','@description',
                     '@unitOfMeasure','@netWeight','@maxPackaging','@format','@gauge','@price','@pieceCount','@dimension',
                     '@grossWeight','@unitMeasureWeight','@idParent','@idOrganization','@active','@User','@imagenUrl',
                     '@xmlMultivalores','@idMultitabla','@tablaMultitabla','@usuario');
-- Nota: en SP T-SQL has_default_value siempre es 0, así que aquí sale todo parámetro no enviado.
-- Si sale alguno, revisar en la firma del SP si tiene default (= NULL, etc.); si no lo tiene, el EXEC fallará.
GO

/* ---------------------------------------------------------------------
   PARTE 3 (opcional) — Ejecución real con ROLLBACK
   Corre los EXEC de verdad y deshace todo al final.
   Esperado: cada EXEC devuelve STATUS/MSG de éxito y total_esperado_13 = 13
   (existentes + nuevas).
   Si un SP hace ROLLBACK interno, la transacción externa se pierde: el
   ROLLBACK final daría error 3903 y lo insertado hasta ahí quedaría.
   Por eso: solo en QAS.
   --------------------------------------------------------------------- */
-- Cuántas ya existen en QAS (esas se saltan por el IF NOT EXISTS)
SELECT COUNT(*) AS ya_existian FROM dbo.BM_Catalog WHERE type='0001' AND deleted=0 AND code IN ('010601','030301','040801','040803','061506','061522','061523','062616','062617','062619','063825','090403','090416');

BEGIN TRAN;

IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='010601' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0106', @subCategory=NULL, @code='010601', @name='Maca', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='030301' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0303', @subCategory=NULL, @code='030301', @name='Haba verde criolla', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='040801' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0408', @subCategory=NULL, @code='040801', @name='Cañihua', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='040803' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0408', @subCategory=NULL, @code='040803', @name='Kiwicha', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='061506' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0615', @subCategory=NULL, @code='061506', @name='Mango chato', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='061522' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0615', @subCategory=NULL, @code='061522', @name='Mango pico de loro', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='061523' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0615', @subCategory=NULL, @code='061523', @name='Mango rosado', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='062616' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0626', @subCategory=NULL, @code='062616', @name='Palta queen', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='062617' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0626', @subCategory=NULL, @code='062617', @name='Palta villa campa', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='062619' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0626', @subCategory=NULL, @code='062619', @name='Palta ettinger', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='063825' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0638', @subCategory=NULL, @code='063825', @name='Zapote', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='090403' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0904', @subCategory=NULL, @code='090403', @name='Hoja de coca tingo maria', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='090416' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0904', @subCategory=NULL, @code='090416', @name='Hoja de coca ayacucho', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;

SELECT COUNT(*) AS total_esperado_13 FROM dbo.BM_Catalog WHERE type='0001' AND deleted=0 AND code IN ('010601','030301','040801','040803','061506','061522','061523','062616','062617','062619','063825','090403','090416');

-- Idempotencia: repetir un EXEC no debe crear duplicados (debe seguir en 1)
IF NOT EXISTS (SELECT 1 FROM dbo.BM_Catalog WHERE type='0001' AND code='010601' AND deleted=0) EXEC dbo.uspBM_SaveUpdateCatalogo @id=0, @process='-', @type='0001', @category='0106', @subCategory=NULL, @code='010601', @name='Maca', @nickname=NULL, @description=NULL, @unitOfMeasure='KG', @netWeight=NULL, @maxPackaging=NULL, @format=NULL, @gauge=NULL, @price=NULL, @pieceCount=NULL, @dimension=NULL, @grossWeight=NULL, @unitMeasureWeight=NULL, @idParent=NULL, @idOrganization=1, @active=1, @User='etl-sisap', @imagenUrl=NULL;
SELECT COUNT(*) AS maca_esperado_1 FROM dbo.BM_Catalog WHERE type='0001' AND code='010601' AND deleted=0;

IF @@TRANCOUNT > 0 ROLLBACK;
GO
