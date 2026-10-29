-- ============================================================================
-- TRANSTEI — Migración 0006: Bloqueos de recursos (P0-04)
-- ============================================================================
-- El libro `nucleo.reservas_recurso` ya soporta mantención, descanso,
-- vacaciones, siniestro y bloqueo manual. Esta migración agrega la
-- trazabilidad de cancelación para que un bloqueo se desactive sin borrarse.
-- ============================================================================

alter table nucleo.reservas_recurso
  add column cancelado_motivo text,
  add column cancelado_por text,
  add column cancelado_en timestamptz;

create index idx_reservas_bloqueos_empresa
  on nucleo.reservas_recurso (empresa_id, tipo_reserva, ventana)
  where activa and tipo_reserva <> 'viaje';

comment on column nucleo.reservas_recurso.cancelado_motivo is
  'Motivo de desactivación de un bloqueo; la fila se conserva para auditoría';
