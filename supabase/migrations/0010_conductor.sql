-- ============================================================================
-- TRANSTEI — Migración 0010: vínculo usuario ↔ chofer para la PWA (P0-07)
-- ============================================================================
-- El conductor inicia sesión con Supabase Auth. El backend resuelve su ficha
-- de chofer por `auth_id`, nunca por un id enviado desde el navegador.
-- ============================================================================

alter table nucleo.choferes
  add column auth_id uuid;

create unique index uq_choferes_empresa_auth
  on nucleo.choferes (empresa_id, auth_id)
  where auth_id is not null;

comment on column nucleo.choferes.auth_id is
  'Usuario de Supabase Auth vinculado al chofer para la PWA del conductor';
