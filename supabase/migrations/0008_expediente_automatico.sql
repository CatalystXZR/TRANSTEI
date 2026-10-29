-- ============================================================================
-- TRANSTEI — Migración 0008: inicialización automática del expediente
-- ============================================================================
-- Todo viaje nuevo nace con sus paradas de origen/descarga, checklist estándar
-- y un evento inicial. Así el expediente nunca queda vacío, venga el viaje de
-- la API, del seed o de una migración.
-- ============================================================================

create or replace function nucleo.fn_viaje_expediente_inicial()
returns trigger
language plpgsql
as $$
declare
  v_auth text := coalesce(nullif(current_setting('nucleo.auth_id', true), ''), 'sistema');
begin
  insert into nucleo.viaje_paradas
    (empresa_id, viaje_id, orden, tipo, nombre, direccion, comuna, ciudad,
     ventana_desde, ventana_hasta, estado)
  values
    (new.empresa_id, new.id, 1, 'origen', new.origen_nombre, new.origen_direccion,
     new.origen_comuna, new.origen_ciudad, new.inicio_planificado, null, 'pendiente'),
    (new.empresa_id, new.id, 2, 'descarga', new.destino_nombre, new.destino_direccion,
     new.destino_comuna, new.destino_ciudad, null, new.fin_planificado, 'pendiente')
  on conflict (viaje_id, orden) do nothing;

  insert into nucleo.viaje_checklist
    (empresa_id, viaje_id, orden, categoria, item, requerido)
  values
    (new.empresa_id, new.id, 1, 'documentos', 'Documentos del viaje revisados y vigentes', true),
    (new.empresa_id, new.id, 2, 'carga', 'Carga asegurada, sujeta y sellos verificados', true),
    (new.empresa_id, new.id, 3, 'ruta', 'Ruta, ventanas y contactos confirmados con el cliente', true),
    (new.empresa_id, new.id, 4, 'seguridad', 'Extintor, botiquín y EPP revisados', true),
    (new.empresa_id, new.id, 5, 'entrega', 'Recepción conforme y evidencia de entrega', true);

  insert into nucleo.viaje_eventos (empresa_id, viaje_id, tipo, descripcion, auth_id)
  values (new.empresa_id, new.id, 'creado', 'Viaje creado en el sistema', v_auth);

  return new;
end;
$$;

create trigger trg_viajes_75_expediente
  after insert on nucleo.viajes
  for each row execute function nucleo.fn_viaje_expediente_inicial();

comment on function nucleo.fn_viaje_expediente_inicial() is
  'Crea paradas, checklist y evento inicial para todo viaje nuevo';
