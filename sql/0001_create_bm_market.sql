/* =====================================================================
   0001 — dbo.BM_Market: mercados SISAP que carga la API (D1', D21, D22)
   Idempotente: se puede ejecutar dos veces. Rollback: 0001_create_bm_market.rollback.sql
   Probado en QAS (BDFarmex_Agri) el 2026-09-24.
   ===================================================================== */
SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.BM_Market', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.BM_Market (
        id               INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_BM_Market PRIMARY KEY,
        code             VARCHAR(20)  NOT NULL CONSTRAINT UQ_BM_Market_code UNIQUE,
        name             VARCHAR(120) NOT NULL,
        source           VARCHAR(20)  NOT NULL CONSTRAINT CK_BM_Market_source CHECK (source IN ('MAYORISTA', 'CIUDADES')),
        active           BIT          NOT NULL CONSTRAINT DF_BM_Market_active DEFAULT (1),
        registrationDate DATETIME     NULL     CONSTRAINT DF_BM_Market_registrationDate DEFAULT (GETDATE()),
        registeredBy     VARCHAR(20)  NULL     CONSTRAINT DF_BM_Market_registeredBy DEFAULT ('etl-sisap'),
        editDate         DATETIME     NULL,
        editedBy         VARCHAR(20)  NULL
    );
END;

/* Mercados del selector del portal (2026-09-24) + el portal Ciudades.
   Inactivos: 15010106 (aves vivas, fuera de alcance, D4/D5), 15011503 (un solo día de datos en 12 meses) y
   CIUDADES (hasta definir las unidades con el área funcional, Open Question 5). Se activan con un UPDATE. */
MERGE dbo.BM_Market AS T
USING (VALUES
    ('15011501', 'Gran mercado mayorista de lima',        'MAYORISTA', 1),
    ('15011502', 'Mercado mayorista nro 2-frutas',        'MAYORISTA', 1),
    ('15011503', 'Mcdo mod. de frutas',                   'MAYORISTA', 0),
    ('15011506', 'Mcdo. may. cereales, legum. y oleag.',  'MAYORISTA', 1),
    ('15013405', 'Mcdo. coop. platanos',                  'MAYORISTA', 1),
    ('15013704', 'Mcdo prod. santa anita',                'MAYORISTA', 1),
    ('15010106', 'Mercado mayorista de aves vivas',       'MAYORISTA', 0),
    ('CIUDADES', 'Portal Ciudades',                       'CIUDADES',  0)
) AS S (code, name, source, active)
ON T.code = S.code
WHEN NOT MATCHED BY TARGET THEN
    INSERT (code, name, source, active) VALUES (S.code, S.name, S.source, S.active);
-- Un mercado que ya existe no se toca: su `active` pudo cambiarse a propósito.

COMMIT TRANSACTION;

SELECT id, code, name, source, active FROM dbo.BM_Market ORDER BY id;
