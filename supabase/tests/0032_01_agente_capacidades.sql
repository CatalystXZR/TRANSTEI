-- ============================================================================
-- Prueba 0032-1 — overrides de capacidades del chat in-app:
--                unicidad, formato, RLS por empresa, auditoría y versionado
-- ============================================================================
-- Invariantes (docs/datos/invariantes.md §16):
--   INV-AGCAP01 no hay dos filas para (empresa, agente, capacidad)
--   INV-AGCAP02 `agente` ∈ {gerente, secretaria} y `capacidad` cumple el formato
--   INV-AGCAP03 con el rol tei_app, dos empresas no se ven ni se cruzan
--   INV-AGCAP04 tei_app no puede borrar overrides
--   INV-AGCAP05 INSERT/UPDATE/DELETE dejan rastro en nucleo.auditoria
--   INV-AGCAP06 cada UPDATE refresca updated_at y sube version
--
-- Corre como `supabase_admin` (BYPASSRLS) para probar constraints, triggers y
-- auditoría; el bloque de aislamiento cambia a `tei_app` con `set local role`.
--
-- TODO termina en ROLLBACK: 0 filas residuales (se comparan los conteos
-- antes/después con \gset).
--
-- Uso:
--   docker exec -i supabase_db_TRANSTEI psql -U supabase_admin -d tei_test \
--     -v ON_ERROR_STOP=1 < supabase/tests/0032_01_agente_capacidades.sql
-- ============================================================================

\set ON_ERROR_STOP on

-- Conteo de partida (fuera de la transacción) para demostrar 0 residuo.
select count(*) as filas_antes from nucleo.agente_capacidades \gset

begin;

do $$
declare
  v_tei     constant uuid := '11111111-1111-1111-1111-111111111111';
  v_tes     constant uuid := '22222222-2222-2222-2222-222222222222';
  v_id      uuid;
  v_id3     uuid;
  v_n       integer;
  v_ver     integer;
  v_ts      timestamptz;
  v_creado  timestamptz;
  v_by      text;
  v_bypass  boolean;
  v_cap     text;
  v_trg     text;
  v_oper    text;
begin
  -- ---- 0. El mecanismo existe en la base ----------------------------------
  select count(*) into v_n
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'nucleo'
     and c.relname = 'agente_capacidades'
     and c.relrowsecurity and c.relforcerowsecurity;
  if v_n <> 1 then
    raise exception 'FALLO 0032-1A: falta RLS+FORCE en agente_capacidades';
  end if;

  select count(*) into v_n
    from pg_policies
   where schemaname = 'nucleo'
     and tablename = 'agente_capacidades'
     and policyname = 'tenant_empresa'
     and coalesce(qual, '') like '%ctx_empresa%'
     and coalesce(with_check, '') like '%ctx_empresa%';
  if v_n <> 1 then
    raise exception 'FALLO 0032-1A: falta la política tenant_empresa con ctx_empresa';
  end if;

  select count(*) into v_n
    from pg_constraint
   where conrelid = 'nucleo.agente_capacidades'::regclass
     and contype = 'u'
     and conname = 'agente_capacidades_unica';
  if v_n <> 1 then
    raise exception 'FALLO 0032-1A: falta agente_capacidades_unica';
  end if;

  select count(*) into v_n
    from pg_trigger
   where tgrelid = 'nucleo.agente_capacidades'::regclass
     and not tgisinternal
     and tgname in ('trg_agente_capacidades_touch',
                    'trg_agente_capacidades_version',
                    'trg_agente_capacidades_audit');
  if v_n <> 3 then
    raise exception 'FALLO 0032-1A: % de 3 triggers de 0032', v_n;
  end if;

  if has_table_privilege('tei_app', 'nucleo.agente_capacidades', 'DELETE') then
    raise exception 'FALLO 0032-1A: tei_app tiene DELETE (INV-AGCAP04)';
  end if;
  if not has_table_privilege('tei_app', 'nucleo.agente_capacidades', 'INSERT')
     or not has_table_privilege('tei_app', 'nucleo.agente_capacidades', 'UPDATE')
     or not has_table_privilege('tei_app', 'nucleo.agente_capacidades', 'SELECT') then
    raise exception 'FALLO 0032-1A: tei_app sin SELECT/INSERT/UPDATE';
  end if;
  raise notice 'OK 0032-1A mecanismo: RLS+FORCE, política, UNIQUE, 3 triggers y privilegios';

  -- ---- 1. INSERT válido ---------------------------------------------------
  -- Sin `nucleo.auth_id` en el contexto: created_by cae a 'sistema'.
  perform set_config('nucleo.auth_id', '', true);
  insert into nucleo.agente_capacidades (empresa_id, agente, capacidad, habilitada)
  values (v_tei, 'gerente', 'facturacion.ver', true)
  returning id, version, created_at, updated_at, created_by
       into v_id, v_ver, v_creado, v_ts, v_by;

  if v_ver <> 1 then
    raise exception 'FALLO 0032-1B: version inicial % (esperado 1)', v_ver;
  end if;
  if v_by <> 'sistema' then
    raise exception 'FALLO 0032-1B: created_by=% (esperado sistema sin nucleo.auth_id)', v_by;
  end if;
  if v_creado <> v_ts then
    raise exception 'FALLO 0032-1B: created_at <> updated_at en el INSERT';
  end if;
  raise notice 'OK 0032-1B INSERT válido: version=1, created_by=sistema, created_at=updated_at';

  -- ---- 2. INV-AGCAP01: duplicado exacto -----------------------------------
  begin
    insert into nucleo.agente_capacidades (empresa_id, agente, capacidad, habilitada)
    values (v_tei, 'gerente', 'facturacion.ver', false);
    raise exception 'FALLO 0032-1C: se aceptó un duplicado (empresa, agente, capacidad)';
  exception when unique_violation then
    raise notice 'OK 0032-1C duplicado (empresa, agente, capacidad) => 23505';
  end;

  -- ---- 3. INV-AGCAP02: agente fuera del catálogo --------------------------
  begin
    insert into nucleo.agente_capacidades (empresa_id, agente, capacidad, habilitada)
    values (v_tei, 'admin', 'facturacion.ver', true);
    raise exception 'FALLO 0032-1D: se aceptó agente=admin';
  exception when check_violation then
    raise notice 'OK 0032-1D agente fuera de {gerente,secretaria} => 23514';
  end;

  -- ---- 4. INV-AGCAP02: formatos de capacidad inválidos --------------------
  foreach v_cap in array array[
    'a',                  -- demasiado corta
    'ab',                 -- 2 caracteres; exige 2–80 después de la inicial
    'AB',                 -- mayúsculas
    'Facturacion.ver',    -- mayúscula inicial
    '_x.y',               -- empieza con guion bajo
    'con espacio',        -- espacio
    'facturacion ver',    -- espacio
    'facturacion/ver',    -- barra
    'ñandu.ver'           -- fuera de [a-z0-9_.]
  ] loop
    begin
      insert into nucleo.agente_capacidades (empresa_id, agente, capacidad, habilitada)
      values (v_tei, 'gerente', v_cap, true);
      raise exception 'FALLO 0032-1D: se aceptó capacidad inválida %', v_cap;
    exception when check_violation then
      null;
    end;
  end loop;
  raise notice 'OK 0032-1D 9 formatos de capacidad inválidos => 23514';

  -- Borde permitido: 3 caracteres y punto.
  insert into nucleo.agente_capacidades (empresa_id, agente, capacidad, habilitada)
  values (v_tei, 'gerente', 'a.b', true);
  raise notice 'OK 0032-1D borde permitido: capacidad de 3 caracteres (a.b) aceptada';

  -- ---- 5. Bordes de unicidad: otro agente y otra empresa ------------------
  insert into nucleo.agente_capacidades (empresa_id, agente, capacidad, habilitada)
  values (v_tei, 'secretaria', 'facturacion.ver', false);
  insert into nucleo.agente_capacidades (empresa_id, agente, capacidad, habilitada)
  values (v_tes, 'gerente', 'facturacion.ver', true);
  raise notice 'OK 0032-1E misma capacidad en otro agente y en otra empresa convive';

  -- ---- 6. INV-AGCAP06: touch + version ------------------------------------
  -- fn_touch() usa now() (= transaction_timestamp), por lo que dentro de UNA
  -- transacción updated_at no avanza. La prueba demuestra que el trigger
  -- dispara: un valor explícito de updated_at se sobrescribe con now().
  update nucleo.agente_capacidades
     set habilitada = false,
         updated_at = timestamptz '2000-01-01 00:00:00+00'
   where id = v_id
  returning version, updated_at, updated_by into v_ver, v_ts, v_by;

  if v_ver <> 2 then
    raise exception 'FALLO 0032-1F: version=% tras UPDATE (esperado 2)', v_ver;
  end if;
  if v_ts <> now() then
    raise exception 'FALLO 0032-1F: fn_touch no refrescó updated_at (quedó %)', v_ts;
  end if;
  if v_by <> 'sistema' then
    raise exception 'FALLO 0032-1F: updated_by=% (esperado sistema)', v_by;
  end if;
  raise notice 'OK 0032-1F touch+version: version=2, updated_at=now() (sobrescribió 2000-01-01)';

  -- ---- 7. INV-AGCAP03/04: RLS con el rol real ----------------------------
  set local role tei_app;

  select rolbypassrls into v_bypass from pg_roles where rolname = current_user;
  if current_user <> 'tei_app' or coalesce(v_bypass, true) then
    raise exception 'FALLO 0032-1G rol: current_user=% bypass=%', current_user, v_bypass;
  end if;

  -- Sin contexto: fail-closed.
  perform set_config('app.empresa_id', '', true);
  select count(*) into v_n from nucleo.agente_capacidades;
  if v_n <> 0 then
    raise exception 'FALLO 0032-1G: % filas visibles sin app.empresa_id', v_n;
  end if;
  begin
    insert into nucleo.agente_capacidades (empresa_id, agente, capacidad, habilitada)
    values (v_tei, 'secretaria', 'viajes.crear', true);
    raise exception 'FALLO 0032-1G: INSERT sin contexto aceptado';
  exception when insufficient_privilege then
    raise notice 'OK 0032-1G sin contexto: 0 filas y INSERT => 42501';
  end;

  -- Contexto TEI: ve lo propio, no lo ajeno.
  perform set_config('app.empresa_id', v_tei::text, true);
  perform set_config('nucleo.auth_id', 'prueba-0032', true);

  select count(*) into v_n from nucleo.agente_capacidades;
  if v_n <> 3 then
    raise exception 'FALLO 0032-1G: TEI ve % filas (esperado 3: gerente, secretaria y a.b)', v_n;
  end if;
  select count(*) into v_n from nucleo.agente_capacidades where empresa_id = v_tes;
  if v_n <> 0 then
    raise exception 'FALLO 0032-1G: TEI ve % filas de TES', v_n;
  end if;

  insert into nucleo.agente_capacidades (empresa_id, agente, capacidad, habilitada)
  values (v_tei, 'gerente', 'viajes.crear', true)
  returning id into v_id3;

  select created_by into v_by from nucleo.agente_capacidades where id = v_id3;
  if v_by <> 'prueba-0032' then
    raise exception 'FALLO 0032-1G: created_by=% (esperado prueba-0032)', v_by;
  end if;

  update nucleo.agente_capacidades set habilitada = false where id = v_id3;
  get diagnostics v_n = row_count;
  if v_n <> 1 then
    raise exception 'FALLO 0032-1G: UPDATE propia afectó % filas (esperado 1)', v_n;
  end if;

  update nucleo.agente_capacidades set habilitada = true where empresa_id = v_tes;
  get diagnostics v_n = row_count;
  if v_n <> 0 then
    raise exception 'FALLO 0032-1G: UPDATE tocó % filas de TES', v_n;
  end if;

  begin
    insert into nucleo.agente_capacidades (empresa_id, agente, capacidad, habilitada)
    values (v_tes, 'secretaria', 'viajes.crear', true);
    raise exception 'FALLO 0032-1G: INSERT con empresa ajena aceptado';
  exception when insufficient_privilege then
    raise notice 'OK 0032-1G INSERT con empresa ajena => 42501';
  end;

  begin
    delete from nucleo.agente_capacidades where id = v_id3;
    raise exception 'FALLO 0032-1H: tei_app pudo borrar un override';
  exception when insufficient_privilege then
    raise notice 'OK 0032-1H DELETE con tei_app => 42501';
  end;

  -- Contexto TES: no ve TEI.
  perform set_config('app.empresa_id', v_tes::text, true);
  select count(*) into v_n from nucleo.agente_capacidades where empresa_id = v_tei;
  if v_n <> 0 then
    raise exception 'FALLO 0032-1G: TES ve % filas de TEI', v_n;
  end if;
  select count(*) into v_n from nucleo.agente_capacidades;
  if v_n <> 1 then
    raise exception 'FALLO 0032-1G: TES ve % filas propias (esperado 1)', v_n;
  end if;

  reset role;
  raise notice 'OK 0032-1G aislamiento: TEI y TES solo ven lo propio; INSERT cruzado rechazado';

  -- ---- 8. INV-AGCAP05: auditoría ------------------------------------------
  foreach v_oper in array array['INSERT', 'UPDATE'] loop
    select count(*) into v_n
      from nucleo.auditoria
     where tabla = 'nucleo.agente_capacidades'
       and registro_id = v_id
       and operacion = v_oper;
    if v_n <> 1 then
      raise exception 'FALLO 0032-1I: % fila(s) de auditoría % para el registro (esperado 1)', v_n, v_oper;
    end if;
  end loop;

  select count(*) into v_n
    from nucleo.auditoria
   where tabla = 'nucleo.agente_capacidades'
     and registro_id = v_id
     and operacion = 'UPDATE'
     and empresa_id = v_tei
     and datos_antes is not null
     and datos_despues is not null;
  if v_n <> 1 then
    raise exception 'FALLO 0032-1I: el UPDATE no dejó datos_antes/datos_despues';
  end if;

  select auth_id into v_by
    from nucleo.auditoria
   where tabla = 'nucleo.agente_capacidades'
     and registro_id = v_id3
     and operacion = 'INSERT';
  if v_by is distinct from 'prueba-0032' then
    raise exception 'FALLO 0032-1I: auth_id de auditoría=% (esperado prueba-0032)', v_by;
  end if;
  raise notice 'OK 0032-1I auditoría: INSERT y UPDATE con empresa, registro y auth_id';

  -- DELETE auditado (como rol de plataforma; tei_app no puede borrar).
  delete from nucleo.agente_capacidades where id = v_id3;
  select count(*) into v_n
    from nucleo.auditoria
   where tabla = 'nucleo.agente_capacidades'
     and registro_id = v_id3
     and operacion = 'DELETE';
  if v_n <> 1 then
    raise exception 'FALLO 0032-1I: el DELETE no dejó auditoría';
  end if;
  raise notice 'OK 0032-1I auditoría: DELETE registrado';

  -- ---- 9. Mutación: sin el UNIQUE el duplicado pasa -----------------------
  -- Se retira el mecanismo DENTRO de la transacción (se revierte con el
  -- ROLLBACK final). Si el duplicado no pasara, la prueba no probaría nada.
  alter table nucleo.agente_capacidades drop constraint agente_capacidades_unica;

  insert into nucleo.agente_capacidades (empresa_id, agente, capacidad, habilitada)
  values (v_tei, 'gerente', 'facturacion.ver', true);
  raise notice 'OK 0032-1J mutación: sin agente_capacidades_unica el duplicado pasa (la prueba depende del mecanismo)';

  raise notice 'OK 0032-1: unicidad, formato, RLS, no-delete, auditoría y versionado';
end
$$;

rollback;

-- 0 residuo: el conteo debe ser el mismo que antes de la transacción.
select count(*) as filas_despues from nucleo.agente_capacidades \gset
select (:filas_antes::bigint = :filas_despues::bigint) as sin_residuo \gset

\if :sin_residuo
\echo 'OK 0032-1: rollback sin residuo (conteo igual antes/después)'
\else
\warn 'FALLO 0032-1: residuo detectado'
do $$ begin raise exception 'FALLO 0032-1: el ROLLBACK dejó filas en nucleo.agente_capacidades'; end $$;
\endif
