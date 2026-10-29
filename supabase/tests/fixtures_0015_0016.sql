-- ============================================================================
-- Fixtures de prueba para las migraciones 0015 y 0016
-- ============================================================================
-- SOLO BASE LOCAL DESECHABLE (127.0.0.1:54322). No ejecutar en staging/prod.
--
-- Crea una empresa aislada (codigo 'TST15') con flota, choferes y documentos
-- suficientes para probar ocupación y licencia A5. Es IDEMPOTENTE: se puede
-- re-ejecutar; los ids son fijos para que los tests los referencien como
-- literales sin variables de psql.
--
-- Uso:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
--        -f supabase/tests/fixtures_0015_0016.sql
--
-- Los datos quedan COMMITEADOS a propósito: la prueba de concurrencia
-- (0015_02) necesita que la segunda conexión vea los maestros.
--
-- Mapa de ids (prefijo 00000015-0000-4000-8000-0000000000NN):
--   0001 empresa        0002 cliente
--   0003 tracto A       0004 tracto B
--   0005 rampla 1 (compartida en la prueba de concurrencia)
--   0006 rampla 2
--   0007 chofer A5 #1   documentos +3650 días
--   0008 chofer A5 #2   licencia_conducir +10 días   (por vencer: NO bloquea)
--   0009 chofer clase A3                             (bloquea)
--   000a chofer clase NULL                           (bloquea)
--   000b tarifa
--   000c chofer A5 #3   licencia_conducir -1 día      (vencida: bloquea)
--   000d chofer A5 sin documentos                     (faltante: bloquea)
--   000e chofer A5 #4   documentos +3650 días (2º chofer de la concurrencia)
-- ============================================================================

begin;

-- ----------------------------------------------------------------------------
-- Empresa de pruebas. dias_margen_documentos = 0 es DELIBERADO: el test
-- 0016_02 ("licencia que vence en 10 días no bloquea") solo es determinista
-- con margen 0 (ver 0004:1276-1279).
-- ----------------------------------------------------------------------------
insert into nucleo.empresas (
  id, codigo, razon_social, rut, giro, ciudad, region,
  zona_horaria, moneda, buffer_operacional_min,
  dias_margen_documentos, dias_alerta_documentos,
  exigir_soap, exigir_seguro_carga, exigir_curso_carga_peligrosa, exigir_oc,
  estado
) values (
  '00000015-0000-4000-8000-000000000001', 'TST15',
  'Empresa de pruebas 0015/0016', '99.999.999-9',
  'Pruebas de base de datos', 'Santiago', 'Metropolitana',
  'America/Santiago', 'CLP', 90,
  0, 14,
  true, true, true, false,
  'activa'
)
on conflict (id) do update set
  razon_social = excluded.razon_social,
  zona_horaria = excluded.zona_horaria,
  buffer_operacional_min = excluded.buffer_operacional_min,
  dias_margen_documentos = excluded.dias_margen_documentos,
  dias_alerta_documentos = excluded.dias_alerta_documentos,
  exigir_soap = excluded.exigir_soap,
  exigir_seguro_carga = excluded.exigir_seguro_carga,
  exigir_curso_carga_peligrosa = excluded.exigir_curso_carga_peligrosa,
  estado = 'activa';

insert into nucleo.clientes (id, empresa_id, razon_social, rut, dias_pago, activo)
values (
  '00000015-0000-4000-8000-000000000002',
  '00000015-0000-4000-8000-000000000001',
  'Cliente de pruebas 0015/0016', '88.888.888-8', 30, true
)
on conflict (id) do update set activo = true;

-- ----------------------------------------------------------------------------
-- Flota
-- ----------------------------------------------------------------------------
insert into nucleo.tractos (
  id, empresa_id, patente, marca, modelo, ano,
  peso_bruto_kg, tara_kg, capacidad_carga_kg, estado, activo
) values
  ('00000015-0000-4000-8000-000000000003',
   '00000015-0000-4000-8000-000000000001', 'TSTT01', 'Volvo', 'FH', 2022,
   39000, 9000, 30000, 'disponible', true),
  ('00000015-0000-4000-8000-000000000004',
   '00000015-0000-4000-8000-000000000001', 'TSTT02', 'Scania', 'R', 2021,
   39000, 9000, 30000, 'disponible', true)
on conflict (id) do update set activo = true, estado = 'disponible';

insert into nucleo.ramplas (
  id, empresa_id, patente, tipo, capacidad_carga_kg, estado, activo
) values
  ('00000015-0000-4000-8000-000000000005',
   '00000015-0000-4000-8000-000000000001', 'TSTR01', 'plana', 30000,
   'disponible', true),
  ('00000015-0000-4000-8000-000000000006',
   '00000015-0000-4000-8000-000000000001', 'TSTR02', 'plana', 30000,
   'disponible', true)
on conflict (id) do update set activo = true, estado = 'disponible';

insert into nucleo.choferes (
  id, empresa_id, rut, nombre, apellido_paterno, numero_licencia,
  licencia_clase, autorizado_carga_peligrosa, estado, activo
) values
  ('00000015-0000-4000-8000-000000000007',
   '00000015-0000-4000-8000-000000000001', '77.777.771-1', 'Ana', 'A5-Uno',
   'TSTLIC-0007', 'A5', false, 'disponible', true),
  ('00000015-0000-4000-8000-000000000008',
   '00000015-0000-4000-8000-000000000001', '77.777.772-2', 'Bruno', 'A5-Diez',
   'TSTLIC-0008', 'A5', false, 'disponible', true),
  ('00000015-0000-4000-8000-000000000009',
   '00000015-0000-4000-8000-000000000001', '77.777.773-3', 'Carla', 'A3',
   'TSTLIC-0009', 'A3', false, 'disponible', true),
  ('00000015-0000-4000-8000-00000000000a',
   '00000015-0000-4000-8000-000000000001', '77.777.774-4', 'Diego', 'SinClase',
   'TSTLIC-000A', null, false, 'disponible', true),
  ('00000015-0000-4000-8000-00000000000c',
   '00000015-0000-4000-8000-000000000001', '77.777.775-5', 'Elena', 'A5-Vencida',
   'TSTLIC-000C', 'A5', false, 'disponible', true),
  ('00000015-0000-4000-8000-00000000000d',
   '00000015-0000-4000-8000-000000000001', '77.777.776-6', 'Felipe', 'A5-SinDocs',
   'TSTLIC-000D', 'A5', false, 'disponible', true),
  ('00000015-0000-4000-8000-00000000000e',
   '00000015-0000-4000-8000-000000000001', '77.777.777-7', 'Gabriela', 'A5-Cuatro',
   'TSTLIC-000E', 'A5', false, 'disponible', true)
on conflict (id) do update set
  licencia_clase = excluded.licencia_clase,
  activo = true,
  estado = 'disponible';

-- ----------------------------------------------------------------------------
-- Documentos. 'vence_en' relativo a CURRENT_DATE para que las pruebas de
-- vencimiento no dependan de la fecha en que se ejecuten.
-- ----------------------------------------------------------------------------
insert into nucleo.documentos (
  id, empresa_id, recurso_tipo, tracto_id, rampla_id, chofer_id,
  tipo, numero, vence_en, es_vigente
) values
  -- tracto A
  ('00000015-0000-4000-8000-000000000101', '00000015-0000-4000-8000-000000000001',
   'tracto', '00000015-0000-4000-8000-000000000003', null, null,
   'revision_tecnica', 'RT-0101', current_date + 3650, true),
  ('00000015-0000-4000-8000-000000000102', '00000015-0000-4000-8000-000000000001',
   'tracto', '00000015-0000-4000-8000-000000000003', null, null,
   'permiso_circulacion', 'PC-0102', current_date + 3650, true),
  ('00000015-0000-4000-8000-000000000103', '00000015-0000-4000-8000-000000000001',
   'tracto', '00000015-0000-4000-8000-000000000003', null, null,
   'seguro_obligatorio', 'SO-0103', current_date + 3650, true),
  ('00000015-0000-4000-8000-000000000104', '00000015-0000-4000-8000-000000000001',
   'tracto', '00000015-0000-4000-8000-000000000003', null, null,
   'soap', 'SOAP-0104', current_date + 3650, true),
  -- tracto B
  ('00000015-0000-4000-8000-000000000111', '00000015-0000-4000-8000-000000000001',
   'tracto', '00000015-0000-4000-8000-000000000004', null, null,
   'revision_tecnica', 'RT-0111', current_date + 3650, true),
  ('00000015-0000-4000-8000-000000000112', '00000015-0000-4000-8000-000000000001',
   'tracto', '00000015-0000-4000-8000-000000000004', null, null,
   'permiso_circulacion', 'PC-0112', current_date + 3650, true),
  ('00000015-0000-4000-8000-000000000113', '00000015-0000-4000-8000-000000000001',
   'tracto', '00000015-0000-4000-8000-000000000004', null, null,
   'seguro_obligatorio', 'SO-0113', current_date + 3650, true),
  ('00000015-0000-4000-8000-000000000114', '00000015-0000-4000-8000-000000000001',
   'tracto', '00000015-0000-4000-8000-000000000004', null, null,
   'soap', 'SOAP-0114', current_date + 3650, true),
  -- rampla 1
  ('00000015-0000-4000-8000-000000000121', '00000015-0000-4000-8000-000000000001',
   'rampla', null, '00000015-0000-4000-8000-000000000005', null,
   'revision_tecnica', 'RT-0121', current_date + 3650, true),
  ('00000015-0000-4000-8000-000000000122', '00000015-0000-4000-8000-000000000001',
   'rampla', null, '00000015-0000-4000-8000-000000000005', null,
   'permiso_circulacion', 'PC-0122', current_date + 3650, true),
  ('00000015-0000-4000-8000-000000000123', '00000015-0000-4000-8000-000000000001',
   'rampla', null, '00000015-0000-4000-8000-000000000005', null,
   'seguro_carga', 'SC-0123', current_date + 3650, true),
  -- rampla 2
  ('00000015-0000-4000-8000-000000000131', '00000015-0000-4000-8000-000000000001',
   'rampla', null, '00000015-0000-4000-8000-000000000006', null,
   'revision_tecnica', 'RT-0131', current_date + 3650, true),
  ('00000015-0000-4000-8000-000000000132', '00000015-0000-4000-8000-000000000001',
   'rampla', null, '00000015-0000-4000-8000-000000000006', null,
   'permiso_circulacion', 'PC-0132', current_date + 3650, true),
  ('00000015-0000-4000-8000-000000000133', '00000015-0000-4000-8000-000000000001',
   'rampla', null, '00000015-0000-4000-8000-000000000006', null,
   'seguro_carga', 'SC-0133', current_date + 3650, true),
  -- chofer A5 #1 (docs largos)
  ('00000015-0000-4000-8000-000000000141', '00000015-0000-4000-8000-000000000001',
   'chofer', null, null, '00000015-0000-4000-8000-000000000007',
   'licencia_conducir', 'LIC-0141', current_date + 3650, true),
  ('00000015-0000-4000-8000-000000000142', '00000015-0000-4000-8000-000000000001',
   'chofer', null, null, '00000015-0000-4000-8000-000000000007',
   'examen_medico', 'EM-0142', current_date + 3650, true),
  -- chofer A5 #2 (licencia por vencer en 10 días)
  ('00000015-0000-4000-8000-000000000151', '00000015-0000-4000-8000-000000000001',
   'chofer', null, null, '00000015-0000-4000-8000-000000000008',
   'licencia_conducir', 'LIC-0151', current_date + 10, true),
  ('00000015-0000-4000-8000-000000000152', '00000015-0000-4000-8000-000000000001',
   'chofer', null, null, '00000015-0000-4000-8000-000000000008',
   'examen_medico', 'EM-0152', current_date + 3650, true),
  -- chofer clase A3
  ('00000015-0000-4000-8000-000000000161', '00000015-0000-4000-8000-000000000001',
   'chofer', null, null, '00000015-0000-4000-8000-000000000009',
   'licencia_conducir', 'LIC-0161', current_date + 3650, true),
  ('00000015-0000-4000-8000-000000000162', '00000015-0000-4000-8000-000000000001',
   'chofer', null, null, '00000015-0000-4000-8000-000000000009',
   'examen_medico', 'EM-0162', current_date + 3650, true),
  -- chofer sin clase
  ('00000015-0000-4000-8000-000000000171', '00000015-0000-4000-8000-000000000001',
   'chofer', null, null, '00000015-0000-4000-8000-00000000000a',
   'licencia_conducir', 'LIC-0171', current_date + 3650, true),
  ('00000015-0000-4000-8000-000000000172', '00000015-0000-4000-8000-000000000001',
   'chofer', null, null, '00000015-0000-4000-8000-00000000000a',
   'examen_medico', 'EM-0172', current_date + 3650, true),
  -- chofer A5 #3 (licencia VENCIDA ayer)
  ('00000015-0000-4000-8000-000000000181', '00000015-0000-4000-8000-000000000001',
   'chofer', null, null, '00000015-0000-4000-8000-00000000000c',
   'licencia_conducir', 'LIC-0181', current_date - 1, true),
  ('00000015-0000-4000-8000-000000000182', '00000015-0000-4000-8000-000000000001',
   'chofer', null, null, '00000015-0000-4000-8000-00000000000c',
   'examen_medico', 'EM-0182', current_date + 3650, true),
  -- chofer A5 #4 (docs largos, 2º chofer de la prueba de concurrencia)
  ('00000015-0000-4000-8000-000000000191', '00000015-0000-4000-8000-000000000001',
   'chofer', null, null, '00000015-0000-4000-8000-00000000000e',
   'licencia_conducir', 'LIC-0191', current_date + 3650, true),
  ('00000015-0000-4000-8000-000000000192', '00000015-0000-4000-8000-000000000001',
   'chofer', null, null, '00000015-0000-4000-8000-00000000000e',
   'examen_medico', 'EM-0192', current_date + 3650, true)
on conflict (id) do update set
  vence_en = excluded.vence_en,
  es_vigente = excluded.es_vigente;

-- chofer '00000015-...-000d' (A5 sin documentos) queda SIN filas en documentos
-- a propósito: es el caso "documento faltante" del test 0015_03.

insert into nucleo.tarifas (
  id, empresa_id, cliente_id, codigo, nombre, modalidad,
  vigencia_desde, vigencia_hasta, moneda, precio_unitario, activo
) values (
  '00000015-0000-4000-8000-00000000000b',
  '00000015-0000-4000-8000-000000000001',
  '00000015-0000-4000-8000-000000000002',
  'T15', 'Tarifa de pruebas 0015/0016', 'viaje',
  current_date - 30, current_date + 3650, 'CLP', 100000, true
)
on conflict (id) do update set activo = true, vigencia_hasta = excluded.vigencia_hasta;

commit;

\echo 'fixtures_0015_0016: OK (empresa TST15 y maestros listos)'
