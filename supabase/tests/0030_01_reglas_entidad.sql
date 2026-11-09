-- ============================================================================
-- Prueba 0030-1 — reglas por entidad: coherencia, vigencia e inmutabilidad
-- ============================================================================
-- Invariantes (docs/datos/invariantes.md §14):
--   INV-TEN01 una regla tiene exactamente una entidad destino y coherente
--   INV-TEN02 la entidad destino es de la misma empresa (FK compuesta)
--   INV-TEN03 las vigencias de una regla no se solapan (EXCLUDE con centinela)
--   INV-TEN04 a lo sumo una regla abierta por (empresa, entidad, clave, destino)
--   INV-TEN05 la fila cerrada es historial inmutable; no se borra
--   INV-TEN09 con el rol tei_app, dos empresas no se ven
--
-- Corre como `supabase_admin` (BYPASSRLS) para probar constraints/triggers.
-- El aislamiento con el rol real está en 0030_03_rls_tei_app.sql; aquí se
-- incluye un bloque acotado con `set local role tei_app` para el punto
-- "dos empresas no se ven".
--
-- TODO termina en ROLLBACK: 0 filas residuales.
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0030_01_reglas_entidad.sql
-- ============================================================================

\set ON_ERROR_STOP on

begin;

do $$
declare
  v_tei     constant uuid := '11111111-1111-1111-1111-111111111111';
  v_tes     constant uuid := '22222222-2222-2222-2222-222222222222';
  v_cli     uuid;
  v_cho     uuid;
  v_tra     uuid;
  v_ram     uuid;
  v_con     uuid;
  v_cli_tes uuid;
  v_id      uuid;
  v_id2     uuid;
  v_ini     timestamptz;
  v_cierre  timestamptz;
  v_n       integer;
  v_ver     integer;
  v_rango   text;
begin
  -- ---- 0. Mecanismo -------------------------------------------------------
  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo' and c.relname = 'tenant_reglas_entidad'
     and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 1 then
    raise exception 'FALLO 0030-1A: tenant_reglas_entidad sin RLS+FORCE';
  end if;

  select count(*) into v_n
    from pg_constraint
   where conrelid = 'nucleo.tenant_reglas_entidad'::regclass and contype = 'x';
  if v_n <> 1 then
    raise exception 'FALLO 0030-1A: falta el EXCLUDE de vigencia (hay %)', v_n;
  end if;

  select count(*) into v_n
    from pg_indexes
   where schemaname = 'nucleo' and tablename = 'tenant_reglas_entidad'
     and indexname = 'uq_regla_vigente';
  if v_n <> 1 then
    raise exception 'FALLO 0030-1A: falta el UNIQUE parcial uq_regla_vigente';
  end if;

  select count(*) into v_n
    from pg_trigger
   where tgrelid = 'nucleo.tenant_reglas_entidad'::regclass and not tgisinternal
     and tgname in ('trg_tenant_reglas_inmutable', 'trg_tenant_reglas_touch',
                    'trg_tenant_reglas_version', 'trg_tenant_reglas_audit');
  if v_n <> 4 then
    raise exception 'FALLO 0030-1A: % de 4 triggers en tenant_reglas_entidad', v_n;
  end if;

  select array_agg(e.enumlabel::text order by e.enumsortorder)::text into v_rango
    from pg_enum e join pg_type t on t.oid = e.enumtypid
    join pg_namespace n on n.oid = t.typnamespace
   where n.nspname = 'nucleo' and t.typname = 'tipo_entidad_regla';
  if v_rango <> '{cliente,chofer,tracto,rampla,contacto}' then
    raise exception 'FALLO 0030-1A: enum inesperado: %', v_rango;
  end if;
  raise notice 'OK 0030-1A mecanismo: RLS+FORCE, EXCLUDE, UNIQUE parcial, 4 triggers, enum';

  -- ---- 1. Fixtures: entidades de TEI y un cliente de TES -------------------
  select id into v_cli from nucleo.clientes  where empresa_id = v_tei order by id limit 1;
  select id into v_cho from nucleo.choferes  where empresa_id = v_tei order by id limit 1;
  select id into v_tra from nucleo.tractos   where empresa_id = v_tei order by id limit 1;
  select id into v_ram from nucleo.ramplas   where empresa_id = v_tei order by id limit 1;
  select id into v_con from nucleo.contactos_whatsapp where empresa_id = v_tei order by id limit 1;
  select id into v_cli_tes from nucleo.clientes where empresa_id = v_tes order by id limit 1;
  if v_cli is null or v_cho is null or v_tra is null or v_ram is null
     or v_con is null or v_cli_tes is null then
    raise exception 'ENTORNO 0030-1: faltan entidades de TEI/TES en el seed';
  end if;

  -- ---- 2. Una regla válida por cada tipo de entidad ------------------------
  insert into nucleo.tenant_reglas_entidad
    (empresa_id, entidad, cliente_id, clave, valor)
  values (v_tei, 'cliente', v_cli, 'comision_cliente', to_jsonb(5))
  returning id, vigente_desde into v_id, v_ini;

  insert into nucleo.tenant_reglas_entidad
    (empresa_id, entidad, chofer_id, clave, valor)
  values (v_tei, 'chofer', v_cho, 'comision_chofer', to_jsonb(8));
  insert into nucleo.tenant_reglas_entidad
    (empresa_id, entidad, tracto_id, clave, valor)
  values (v_tei, 'tracto', v_tra, 'rendimiento_minimo', to_jsonb(2.5));
  insert into nucleo.tenant_reglas_entidad
    (empresa_id, entidad, rampla_id, clave, valor)
  values (v_tei, 'rampla', v_ram, 'tarifa_rampla', to_jsonb(1000));
  insert into nucleo.tenant_reglas_entidad
    (empresa_id, entidad, contacto_id, clave, valor)
  values (v_tei, 'contacto', v_con, 'idioma_preferido', to_jsonb('es'::text));

  select count(*) into v_n from nucleo.tenant_reglas_entidad where empresa_id = v_tei;
  if v_n <> 5 then
    raise exception 'FALLO 0030-1B: se esperaban 5 reglas de TEI, hay %', v_n;
  end if;
  raise notice 'OK 0030-1B una regla por entidad (5 tipos)';

  -- ---- 3. INV-TEN01: exactamente una FK y coherente con `entidad` ---------
  begin
    insert into nucleo.tenant_reglas_entidad
      (empresa_id, entidad, cliente_id, chofer_id, clave, valor)
    values (v_tei, 'cliente', v_cli, v_cho, 'dos_fks', to_jsonb(1));
    raise exception 'FALLO 0030-1C: se aceptaron dos FKs';
  exception when check_violation then
    raise notice 'OK 0030-1C dos FKs => 23514';
  end;

  begin
    insert into nucleo.tenant_reglas_entidad
      (empresa_id, entidad, clave, valor)
    values (v_tei, 'cliente', 'ninguna_fk', to_jsonb(1));
    raise exception 'FALLO 0030-1C: se aceptó una regla sin entidad';
  exception when check_violation then
    raise notice 'OK 0030-1C sin FK => 23514';
  end;

  begin
    insert into nucleo.tenant_reglas_entidad
      (empresa_id, entidad, chofer_id, clave, valor)
    values (v_tei, 'cliente', v_cho, 'fk_incoherente_a', to_jsonb(1));
    raise exception 'FALLO 0030-1C: entidad cliente con chofer_id fue aceptada';
  exception when check_violation then
    raise notice 'OK 0030-1C entidad cliente con chofer_id => 23514';
  end;

  begin
    insert into nucleo.tenant_reglas_entidad
      (empresa_id, entidad, cliente_id, clave, valor)
    values (v_tei, 'tracto', v_cli, 'fk_incoherente_b', to_jsonb(1));
    raise exception 'FALLO 0030-1C: entidad tracto con cliente_id fue aceptada';
  exception when check_violation then
    raise notice 'OK 0030-1C entidad tracto con cliente_id => 23514';
  end;

  -- ---- 4. Formato de clave ------------------------------------------------
  begin
    insert into nucleo.tenant_reglas_entidad
      (empresa_id, entidad, cliente_id, clave, valor)
    values (v_tei, 'cliente', v_cli, 'ClaveMayuscula', to_jsonb(1));
    raise exception 'FALLO 0030-1D: clave con mayúsculas aceptada';
  exception when check_violation then
    raise notice 'OK 0030-1D clave con mayúsculas => 23514';
  end;

  begin
    insert into nucleo.tenant_reglas_entidad
      (empresa_id, entidad, cliente_id, clave, valor)
    values (v_tei, 'cliente', v_cli, 'ab', to_jsonb(1));
    raise exception 'FALLO 0030-1D: clave demasiado corta aceptada';
  exception when check_violation then
    raise notice 'OK 0030-1D clave de 2 caracteres => 23514';
  end;

  begin
    insert into nucleo.tenant_reglas_entidad
      (empresa_id, entidad, cliente_id, clave, valor)
    values (v_tei, 'cliente', v_cli, '1empieza_numero', to_jsonb(1));
    raise exception 'FALLO 0030-1D: clave que empieza con número aceptada';
  exception when check_violation then
    raise notice 'OK 0030-1D clave que empieza con número => 23514';
  end;

  -- ---- 5. Vigencia que retrocede -----------------------------------------
  begin
    insert into nucleo.tenant_reglas_entidad
      (empresa_id, entidad, cliente_id, clave, valor, vigente_desde, vigente_hasta)
    values (v_tei, 'cliente', v_cli, 'vigencia_mala', to_jsonb(1),
            now(), now() - interval '1 hour');
    raise exception 'FALLO 0030-1E: se aceptó vigente_hasta <= vigente_desde';
  exception when check_violation then
    raise notice 'OK 0030-1E vigencia que retrocede => 23514';
  end;

  -- ---- 6. INV-TEN04: dos filas abiertas ----------------------------------
  begin
    insert into nucleo.tenant_reglas_entidad
      (empresa_id, entidad, cliente_id, clave, valor)
    values (v_tei, 'cliente', v_cli, 'comision_cliente', to_jsonb(6));
    raise exception 'FALLO 0030-1F: dos reglas abiertas para la misma clave/destino';
  exception when unique_violation or exclusion_violation then
    raise notice 'OK 0030-1F segunda fila abierta => 23505/23P01';
  end;

  -- ---- 7. INV-TEN03: solape histórico (aislado del UNIQUE parcial) --------
  v_cierre := v_ini + interval '1 day';
  update nucleo.tenant_reglas_entidad set vigente_hasta = v_cierre where id = v_id;

  begin
    insert into nucleo.tenant_reglas_entidad
      (empresa_id, entidad, cliente_id, clave, valor, vigente_desde, vigente_hasta)
    values (v_tei, 'cliente', v_cli, 'comision_cliente', to_jsonb(7),
            v_ini + interval '1 hour', v_cierre - interval '1 hour');
    raise exception 'FALLO 0030-1G: se aceptó un solape con la fila cerrada';
  exception when exclusion_violation then
    raise notice 'OK 0030-1G solape histórico => 23P01';
  end;

  -- Borde: [desde, hasta) semiabierto permite empezar justo en el cierre.
  insert into nucleo.tenant_reglas_entidad
    (empresa_id, entidad, cliente_id, clave, valor, vigente_desde)
  values (v_tei, 'cliente', v_cli, 'comision_cliente', to_jsonb(9), v_cierre)
  returning id into v_id2;
  raise notice 'OK 0030-1G borde: nueva vigencia en el cierre exacto aceptada';

  -- ---- 8. INV-TEN05: la fila cerrada es inmutable -------------------------
  begin
    update nucleo.tenant_reglas_entidad set valor = to_jsonb(99) where id = v_id;
    raise exception 'FALLO 0030-1H: se editó el valor de una fila cerrada';
  exception when check_violation then
    raise notice 'OK 0030-1H UPDATE valor de fila cerrada => 23514';
  end;

  begin
    update nucleo.tenant_reglas_entidad set clave = 'otra_clave' where id = v_id;
    raise exception 'FALLO 0030-1H: se editó la clave de una fila cerrada';
  exception when check_violation then
    raise notice 'OK 0030-1H UPDATE clave de fila cerrada => 23514';
  end;

  begin
    update nucleo.tenant_reglas_entidad
       set vigente_desde = vigente_desde - interval '1 hour'
     where id = v_id;
    raise exception 'FALLO 0030-1H: se editó vigente_desde de una fila cerrada';
  exception when check_violation then
    raise notice 'OK 0030-1H UPDATE vigente_desde cerrada => 23514';
  end;

  begin
    update nucleo.tenant_reglas_entidad set vigente_hasta = null where id = v_id;
    raise exception 'FALLO 0030-1H: se reabrió una vigencia cerrada';
  exception when check_violation then
    raise notice 'OK 0030-1H reabrir vigencia cerrada => 23514';
  end;

  begin
    delete from nucleo.tenant_reglas_entidad where id = v_id;
    raise exception 'FALLO 0030-1H: se borró una regla';
  exception when check_violation then
    raise notice 'OK 0030-1H DELETE de regla => 23514';
  end;

  -- La fila abierta sí se puede actualizar (no es historial todavía) y
  -- fn_version incrementa `version`.
  update nucleo.tenant_reglas_entidad
     set valor = to_jsonb(10)
   where id = v_id2
  returning version into v_ver;
  if v_ver <> 2 then
    raise exception 'FALLO 0030-1H: version esperada 2, quedó %', v_ver;
  end if;
  raise notice 'OK 0030-1H fila abierta editable; version = 2';

  -- ---- 9. INV-TEN02: FK compuesta impide cruzar empresas -----------------
  begin
    insert into nucleo.tenant_reglas_entidad
      (empresa_id, entidad, cliente_id, clave, valor)
    values (v_tei, 'cliente', v_cli_tes, 'cliente_cruzado', to_jsonb(1));
    raise exception 'FALLO 0030-1I: se aceptó un cliente de TES con empresa TEI';
  exception when foreign_key_violation then
    raise notice 'OK 0030-1I cliente de otra empresa => 23503';
  end;

  -- ---- 10. Otra empresa con la misma clave/destino lógico es independiente
  insert into nucleo.tenant_reglas_entidad
    (empresa_id, entidad, cliente_id, clave, valor)
  values (v_tes, 'cliente', v_cli_tes, 'comision_cliente', to_jsonb(3));
  raise notice 'OK 0030-1J misma clave en TES convive con la de TEI';

  -- ---- 11. INV-TEN09 acotado: con tei_app, dos empresas no se ven ---------
  set local role tei_app;

  perform set_config('app.empresa_id', v_tei::text, true);
  select count(*) into v_n from nucleo.tenant_reglas_entidad;
  if v_n <> 6 then  -- 5 tipos + la nueva abierta de comision_cliente
    raise exception 'FALLO 0030-1K: TEI ve % reglas (esperado 6)', v_n;
  end if;
  select count(*) into v_n from nucleo.tenant_reglas_entidad where empresa_id = v_tes;
  if v_n <> 0 then
    raise exception 'FALLO 0030-1K: TEI ve % reglas de TES', v_n;
  end if;

  perform set_config('app.empresa_id', v_tes::text, true);
  select count(*) into v_n from nucleo.tenant_reglas_entidad where empresa_id = v_tei;
  if v_n <> 0 then
    raise exception 'FALLO 0030-1K: TES ve % reglas de TEI', v_n;
  end if;

  reset role;

  raise notice 'OK 0030-1K dos empresas no se ven (set local role tei_app)';
  raise notice 'OK 0030-1: coherencia, formato, vigencia, solape, inmutabilidad y tenant';
end
$$;

rollback;

\echo '0030-1: OK (rollback; 0 filas residuales)'
