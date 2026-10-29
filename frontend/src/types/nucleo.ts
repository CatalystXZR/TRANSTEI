export type TipoRecurso = "tracto" | "rampla" | "chofer";
export type EstadoViajeNucleo =
  | "borrador"
  | "cotizado"
  | "confirmado"
  | "asignado"
  | "en_carga"
  | "cargado"
  | "en_ruta"
  | "en_descarga"
  | "descargado"
  | "pod_pendiente"
  | "cerrado"
  | "facturado"
  | "cobrado"
  | "anulado";

export interface EmpresaNucleo {
  id: string;
  codigo: string;
  razon_social: string;
  rut: string;
  zona_horaria: string;
  moneda: string;
  buffer_operacional_min: number;
  rol: string;
}

export interface ClienteOpcionNucleo {
  id: string;
  razon_social: string;
  rut: string;
  exige_oc: boolean;
  dias_pago: number;
}

export interface TarifaOpcionNucleo {
  id: string;
  cliente_id: string;
  codigo: string;
  nombre: string;
  modalidad: string;
  origen: string | null;
  destino: string | null;
  moneda: string;
  precio_unitario: string;
  minimo_cobro: string;
  vigencia_desde: string;
  vigencia_hasta: string | null;
  activo: boolean;
}

export interface OrdenCompraOpcionNucleo {
  id: string;
  cliente_id: string;
  numero_oc: string;
  monto_autorizado: string;
  monto_consumido: string;
  sobregiro_autorizado: string;
  moneda: string;
  vigencia_desde: string;
  vigencia_hasta: string;
  estado: string;
}

export interface ClienteNucleo {
  id: string;
  razon_social: string;
  rut: string;
  giro: string | null;
  direccion: string | null;
  comuna: string | null;
  ciudad: string | null;
  contacto_nombre: string | null;
  contacto_email: string | null;
  contacto_telefono: string | null;
  dias_pago: number;
  credito_autorizado: string;
  exige_oc: boolean;
  activo: boolean;
  observaciones: string | null;
  version: number;
}

export interface TractoNucleo {
  id: string;
  patente: string;
  marca: string | null;
  modelo: string | null;
  ano: number | null;
  vin: string | null;
  color: string | null;
  configuracion_ejes: string | null;
  peso_bruto_kg: string;
  tara_kg: string;
  capacidad_carga_kg: string;
  volumen_m3: string | null;
  km_actual: string;
  horas_motor: string;
  licencias_permitidas: string[];
  estado: string;
  activo: boolean;
  ubicacion_ciudad: string | null;
  ubicacion_lat: string | null;
  ubicacion_lon: string | null;
  observaciones: string | null;
  version: number;
}

export interface RamplaNucleo {
  id: string;
  patente: string;
  tipo: string;
  marca: string | null;
  modelo: string | null;
  ano: number | null;
  vin: string | null;
  capacidad_carga_kg: string;
  volumen_m3: string | null;
  largo_m: string | null;
  ancho_m: string | null;
  alto_m: string | null;
  peso_tara_kg: string | null;
  ejes: number | null;
  temperatura_min_c: string | null;
  temperatura_max_c: string | null;
  estado: string;
  activo: boolean;
  ubicacion_ciudad: string | null;
  ubicacion_lat: string | null;
  ubicacion_lon: string | null;
  observaciones: string | null;
  version: number;
}

export interface ChoferNucleo {
  id: string;
  rut: string;
  nombre: string;
  apellido_paterno: string | null;
  apellido_materno: string | null;
  fecha_nacimiento: string | null;
  telefono: string | null;
  email: string | null;
  direccion: string | null;
  comuna: string | null;
  ciudad: string | null;
  numero_licencia: string | null;
  licencia_clase: string | null;
  licencia_restricciones: string | null;
  autorizado_carga_peligrosa: boolean;
  sueldo_base: string;
  porcentaje_comision: string;
  contacto_emergencia_nombre: string | null;
  contacto_emergencia_telefono: string | null;
  estado: string;
  activo: boolean;
  observaciones: string | null;
  version: number;
}

export interface DocumentoUrlNucleo {
  url: string;
  expires_in: number;
}

export interface IncidenciaNucleo {
  codigo: string;
  mensaje: string;
  bloqueante: boolean;
  recurso_tipo?: TipoRecurso | null;
  recurso_id?: string | null;
}

export interface DocumentoNucleo {
  id?: string;
  recurso_tipo: TipoRecurso;
  recurso_id: string;
  tipo: string;
  estado: string;
  requerido: boolean;
  bloqueante: boolean;
  vence_en?: string | null;
  dias_restantes?: number | null;
  motivo?: string | null;
  numero?: string | null;
  entidad_emisora?: string | null;
  archivo_url?: string | null;
  hash_sha256?: string | null;
  observaciones?: string | null;
  created_at?: string;
  version?: number;
  es_vigente?: boolean;
}

export type DocumentoArchivoNucleo = DocumentoNucleo & {
  id: string;
  es_vigente: boolean;
};

export interface ReservaNucleo {
  id: string;
  tipo_reserva: string;
  inicio: string;
  fin: string;
  motivo?: string | null;
  viaje_id?: string | null;
}

export interface ConflictoNucleo {
  recurso_tipo: TipoRecurso;
  recurso_id: string;
  tipo_reserva: string;
  inicio: string;
  fin: string;
  motivo?: string | null;
  viaje_id?: string | null;
}

export interface RecursoNucleo {
  id: string;
  tipo: TipoRecurso;
  etiqueta: string;
  estado: string;
  activo: boolean;
  disponible: boolean;
  libre_desde: string | null;
  inicio_operativo_posible: string | null;
  documentos_ok: boolean;
  capacidad_carga_kg?: string | null;
  volumen_m3?: string | null;
  tipo_rampla?: string | null;
  licencia_clase?: string | null;
  incidencias: IncidenciaNucleo[];
  advertencias: IncidenciaNucleo[];
  documentos: DocumentoNucleo[];
  proximas_reservas: ReservaNucleo[];
}

export interface ListaRecursosNucleo {
  items: RecursoNucleo[];
  paginacion: { total: number; limit: number; offset: number; hay_mas: boolean };
  desde: string;
  hasta: string;
  zona_horaria: string;
}

export interface ViajeNucleo {
  id: string;
  numero_viaje: string;
  estado: EstadoViajeNucleo;
  cliente_id: string;
  cliente_nombre: string;
  orden_compra_id?: string | null;
  oc_numero?: string | null;
  tarifa_id?: string | null;
  tarifa_codigo?: string | null;
  origen: string;
  destino: string;
  inicio_planificado: string;
  fin_planificado: string;
  buffer_minutos: number;
  peso_bruto_kg?: string | null;
  flete_total: string;
  tracto_id?: string | null;
  tracto_patente?: string | null;
  rampla_id?: string | null;
  rampla_patente?: string | null;
  chofer_id?: string | null;
  chofer_nombre?: string | null;
  carga_peligrosa: boolean;
  refrigerada: boolean;
}

export interface ListaViajesNucleo {
  items: ViajeNucleo[];
  total: number;
  limit: number;
  offset: number;
  hay_mas: boolean;
}

export interface ResultadoNucleo {
  apto: boolean;
  viaje_id: string;
  numero_viaje: string;
  estado: EstadoViajeNucleo;
  empresa_id: string;
  zona_horaria: string;
  ventana: { inicio: string; fin: string; incluye_buffer: boolean };
  recursos: RecursoNucleo[];
  documentos: DocumentoNucleo[];
  conflictos: ConflictoNucleo[];
  incidencias: IncidenciaNucleo[];
  advertencias: IncidenciaNucleo[];
  libre_desde: string | null;
  inicio_operativo_posible: string | null;
  flete_total: string;
  oc_numero?: string | null;
  tarifa_codigo?: string | null;
  mensaje: string;
}

export interface AsignacionNucleo {
  viaje_id: string;
  numero_viaje: string;
  estado: EstadoViajeNucleo;
  version: number;
  empresa_id: string;
  recursos: RecursoNucleo[];
  ventana: { inicio: string; fin: string; incluye_buffer: boolean };
  reservas: ReservaNucleo[];
  libre_desde: string | null;
  inicio_operativo_posible: string | null;
  audit_ok: boolean;
}

/* ------------------------------------------------------------------ */
/* P0-03 Comercial                                                     */
/* ------------------------------------------------------------------ */
export type ModalidadTarifaNucleo =
  | "viaje"
  | "km"
  | "tonelada"
  | "tonelada_km"
  | "hora"
  | "contenedor"
  | "estadia"
  | "mixta";

export interface CentroCostoNucleo {
  id: string;
  codigo: string;
  nombre: string;
  descripcion: string | null;
  activo: boolean;
  version: number;
}

export interface TarifaNucleo {
  id: string;
  cliente_id: string;
  cliente_nombre: string;
  codigo: string;
  nombre: string;
  descripcion: string | null;
  modalidad: ModalidadTarifaNucleo;
  origen: string | null;
  destino: string | null;
  tipo_rampla: string | null;
  tipo_carga: string | null;
  vigencia_desde: string;
  vigencia_hasta: string | null;
  moneda: string;
  precio_unitario: string;
  minimo_cobro: string;
  incluye_peajes: boolean;
  incluye_combustible: boolean;
  precio_diesel_base: string | null;
  rendimiento_km_l: string | null;
  participacion_combustible: string | null;
  recargos: Record<string, unknown>;
  condiciones: Record<string, unknown>;
  activo: boolean;
  vencida: boolean;
  viajes_activos: number;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface LineaOCNucleo {
  id: string;
  numero_linea: number;
  descripcion: string;
  origen: string | null;
  destino: string | null;
  tarifa_id: string | null;
  centro_costo_id: string | null;
  cantidad_estimada: string;
  unidad: string;
  precio_unitario: string;
  monto_linea: string;
  activa: boolean;
  version: number;
}

export interface ConsumoViajeNucleo {
  id: string;
  numero_viaje: string;
  estado: EstadoViajeNucleo;
  inicio_planificado: string;
  monto: string;
  porcentaje_oc: string;
}

export type AlertaOCNucleo = "normal" | "80" | "90" | "100" | "sobregiro";
export type EstadoSobregiroNucleo =
  | "sin_solicitud"
  | "pendiente"
  | "aprobado"
  | "rechazado";

export interface OrdenCompraResumenNucleo {
  id: string;
  cliente_id: string;
  cliente_nombre: string;
  numero_oc: string;
  referencia_interna: string | null;
  fecha_emision: string;
  vigencia_desde: string;
  vigencia_hasta: string;
  monto_autorizado: string;
  sobregiro_autorizado: string;
  monto_consumido: string;
  saldo_disponible: string;
  porcentaje_consumo: string;
  alerta: AlertaOCNucleo;
  moneda: string;
  centro_costo_id: string | null;
  centro_costo_nombre: string | null;
  estado: string;
  vencida: boolean;
  sobregiro_estado: EstadoSobregiroNucleo;
  sobregiro_solicitado: string;
  lineas_count: number;
  viajes_count: number;
  version: number;
}

export interface OrdenCompraNucleo extends OrdenCompraResumenNucleo {
  proyecto: string | null;
  faena: string | null;
  condiciones_pago_dias: number | null;
  observaciones: string | null;
  sobregiro_motivo: string | null;
  sobregiro_solicitado_por: string | null;
  sobregiro_solicitado_en: string | null;
  sobregiro_aprobado_por: string | null;
  sobregiro_aprobado_en: string | null;
  sobregiro_resolucion: string | null;
  lineas: LineaOCNucleo[];
  viajes: ConsumoViajeNucleo[];
  created_at: string;
  updated_at: string;
}

export interface HistorialCambioNucleo {
  id: number;
  tabla: string;
  registro_id: string | null;
  operacion: string;
  ocurrido_en: string;
  auth_id: string | null;
  datos_antes: Record<string, unknown> | null;
  datos_despues: Record<string, unknown> | null;
}

/* ------------------------------------------------------------------ */
/* P0-04 Agenda y bloqueos                                             */
/* ------------------------------------------------------------------ */
export type TipoReservaNucleo =
  | "viaje"
  | "mantenimiento"
  | "descanso"
  | "vacaciones"
  | "bloqueo_manual"
  | "siniestro"
  | "otro";

export interface BloqueoNucleo {
  id: string;
  recurso_tipo: TipoRecurso;
  recurso_id: string;
  etiqueta: string;
  inicio: string;
  fin: string;
  tipo_reserva: TipoReservaNucleo;
  motivo: string | null;
  activa: boolean;
  cancelado_motivo: string | null;
  cancelado_por: string | null;
  cancelado_en: string | null;
  creado_por: string;
  created_at: string;
  version: number;
}

export interface AgendaItemNucleo {
  id: string;
  origen: "bloqueo" | "viaje";
  recurso_tipo: TipoRecurso;
  recurso_id: string;
  inicio: string;
  fin: string;
  tipo_reserva: TipoReservaNucleo;
  motivo: string | null;
  viaje_id: string | null;
  numero_viaje: string | null;
  estado_viaje: EstadoViajeNucleo | null;
  cancelable: boolean;
}

export interface AgendaRecursoNucleo {
  recurso_tipo: TipoRecurso;
  recurso_id: string;
  etiqueta: string;
  estado: string;
  activo: boolean;
  items: AgendaItemNucleo[];
}

export interface AgendaNucleo {
  desde: string;
  hasta: string;
  zona_horaria: string;
  recursos: AgendaRecursoNucleo[];
  total_bloqueos: number;
  total_viajes: number;
  mensaje: string;
}

/* ------------------------------------------------------------------ */
/* P0-05 Expediente                                                    */
/* ------------------------------------------------------------------ */
export interface ParadaNucleo {
  id: string;
  orden: number;
  tipo: string;
  nombre: string;
  direccion: string | null;
  comuna: string | null;
  ciudad: string | null;
  contacto_nombre: string | null;
  contacto_telefono: string | null;
  ventana_desde: string | null;
  ventana_hasta: string | null;
  estado: string;
  notas: string | null;
  activo: boolean;
  version: number;
}

export interface ChecklistItemNucleo {
  id: string;
  orden: number;
  categoria: string;
  item: string;
  requerido: boolean;
  completado: boolean;
  completado_por: string | null;
  completado_en: string | null;
  evidencia_url: string | null;
  notas: string | null;
  version: number;
}

export interface EventoNucleo {
  id: string;
  tipo: string;
  descripcion: string;
  ocurrido_en: string;
  payload: Record<string, unknown>;
  auth_id: string | null;
}

export interface IncidenteNucleo {
  id: string;
  tipo: string;
  severidad: string;
  descripcion: string;
  estado: string;
  ocurrido_en: string;
  reportado_por: string | null;
  resolucion: string | null;
  resuelto_por: string | null;
  resuelto_en: string | null;
  version: number;
}

export interface ViajeDocumentoNucleo {
  id: string;
  tipo: string;
  nombre: string;
  archivo_url: string;
  hash_sha256: string | null;
  content_type: string | null;
  tamano_bytes: number | null;
  observaciones: string | null;
  activo: boolean;
  created_at: string;
  url_firmada: string | null;
}

export interface ResumenExpedienteNucleo {
  checklist_total: number;
  checklist_completados: number;
  checklist_requeridos_pendientes: number;
  paradas_total: number;
  paradas_completadas: number;
  incidentes_abiertos: number;
  documentos_count: number;
  progreso_pct: string;
  puede_cerrar: boolean;
  motivos_cierre: string[];
}

export interface PODFotoNucleo {
  path: string;
  nombre: string | null;
  content_type: string | null;
  url_firmada: string | null;
}

export interface PODNucleo {
  id: string;
  viaje_id: string;
  receptor_nombre: string;
  receptor_rut: string | null;
  receptor_cargo: string | null;
  fecha_hora: string;
  lat: string | null;
  lon: string | null;
  firma_url: string;
  firma_url_firmada: string | null;
  firma_hash: string | null;
  fotos: PODFotoNucleo[];
  danios: string | null;
  observaciones: string | null;
  created_at: string;
  created_by: string;
  version: number;
  facturacion_habilitada: boolean;
  mensaje: string;
}

export interface GastoNucleo {
  id: string;
  viaje_id: string;
  tipo: string;
  proveedor: string | null;
  numero_documento: string | null;
  fecha: string;
  monto_total: string;
  iva: string;
  monto_neto: string;
  moneda: string;
  litros: string | null;
  precio_litro: string | null;
  km_odometro: string | null;
  estacion: string | null;
  tag: string | null;
  comprobante_url: string | null;
  comprobante_url_firmada: string | null;
  estado: string;
  motivo_rechazo: string | null;
  aprobado_por: string | null;
  aprobado_en: string | null;
  observaciones: string | null;
  activo: boolean;
  created_at: string;
  created_by: string;
  version: number;
}

export interface CostoPorTipoNucleo {
  tipo: string;
  cantidad: number;
  monto: string;
}

export interface CostosViajeNucleo {
  viaje_id: string;
  flete_neto: string;
  recargos: string;
  ingreso_total: string;
  gastos_aprobados: string;
  gastos_pendientes: string;
  comision_estimada: string;
  costo_variable: string;
  costo_total: string;
  margen: string;
  margen_pct: string;
  litros: string;
  km_recorridos: string | null;
  rendimiento_km_l: string | null;
  costo_por_km: string | null;
  por_tipo: CostoPorTipoNucleo[];
  actualizado_en: string | null;
  mensaje: string;
}

export interface PrecioDieselNucleo {
  id: string;
  fecha: string;
  precio_litro: string;
  fuente: string | null;
  created_at: string;
}

/* ------------------------------------------------------------------ */
/* P0-09 Rentabilidad y Freight Score                                  */
/* ------------------------------------------------------------------ */
export interface ConfiguracionCostosNucleo {
  id: string | null;
  configurado: boolean;
  costo_fijo_mensual: string;
  viajes_estimados_mes: number;
  margen_objetivo: string;
  benchmark_margen_km: string;
  contribucion_minima: string;
  costo_variable_km_estandar: string;
  rendimiento_km_l: string;
  precio_diesel: string;
  version: number;
  updated_at: string | null;
}

export interface ComponenteFreightScoreNucleo {
  codigo: string;
  nombre: string;
  score: string;
  peso: string;
  aporte: string;
  detalle: string;
}

export interface ResultadoRentabilidadNucleo {
  ingreso_total: string;
  costo_variable: string;
  costo_fijo_asignado: string;
  costo_total: string;
  margen: string;
  margen_pct: string;
  margen_km: string | null;
  km_totales: string;
  tarifa_piso_estrategica: string;
  tarifa_piso_tactica: string;
  score: string;
  semaforo: "verde" | "amarillo" | "rojo";
  componentes: ComponenteFreightScoreNucleo[];
  explicacion: string[];
  margen_objetivo: string;
  benchmark_margen_km: string;
  configurado: boolean;
}

export interface RentabilidadViajeNucleo extends ResultadoRentabilidadNucleo {
  viaje_id: string;
  numero_viaje: string;
  fuente_costos: "real" | "estandar";
  cliente_nombre: string;
  distancia_km: string | null;
  km_vacios: string | null;
}

export interface ViajeExpedienteNucleo {
  id: string;
  numero_viaje: string;
  estado: EstadoViajeNucleo;
  cliente_id: string;
  cliente_nombre: string;
  cliente_rut: string | null;
  orden_compra_id: string | null;
  oc_numero: string | null;
  tarifa_id: string | null;
  tarifa_codigo: string | null;
  tracto_id: string | null;
  tracto_patente: string | null;
  rampla_id: string | null;
  rampla_patente: string | null;
  chofer_id: string | null;
  chofer_nombre: string | null;
  inicio_planificado: string;
  fin_planificado: string;
  fin_estimado: string | null;
  inicio_real: string | null;
  fin_real: string | null;
  buffer_minutos: number;
  origen_nombre: string;
  origen_direccion: string | null;
  origen_comuna: string | null;
  origen_ciudad: string | null;
  origen_region: string | null;
  destino_nombre: string;
  destino_direccion: string | null;
  destino_comuna: string | null;
  destino_ciudad: string | null;
  destino_region: string | null;
  distancia_km: string | null;
  tiempo_estimado_h: string | null;
  tipo_carga: string;
  descripcion_carga: string | null;
  peso_bruto_kg: string | null;
  peso_neto_kg: string | null;
  volumen_m3: string | null;
  bultos: number | null;
  valor_declarado: string | null;
  moneda_valor: string | null;
  carga_peligrosa: boolean;
  numero_un: string | null;
  clase_peligro: string | null;
  refrigerada: boolean;
  temperatura_min_c: string | null;
  temperatura_max_c: string | null;
  sobredimensionada: boolean;
  instrucciones_especiales: string | null;
  valor_flete_neto: string;
  monto_recargos: string;
  monto_total_neto: string | null;
  moneda: string;
  condiciones_pago_dias: number | null;
  observaciones: string | null;
  motivo_anulacion: string | null;
  created_at: string;
  updated_at: string;
  version: number;
  paradas: ParadaNucleo[];
  checklist: ChecklistItemNucleo[];
  eventos: EventoNucleo[];
  incidentes: IncidenteNucleo[];
  documentos: ViajeDocumentoNucleo[];
  historial: HistorialCambioNucleo[];
  gastos: GastoNucleo[];
  factura: FacturaNucleo | null;
  pod: PODNucleo | null;
  costos: CostosViajeNucleo | null;
  resumen: ResumenExpedienteNucleo;
  qr_url: string;
}

export interface ViajeExpedienteResumenNucleo {
  id: string;
  numero_viaje: string;
  estado: EstadoViajeNucleo;
  cliente_id: string;
  cliente_nombre: string;
  origen: string;
  destino: string;
  inicio_planificado: string;
  fin_planificado: string;
  peso_bruto_kg: string | null;
  flete_total: string;
  oc_numero: string | null;
  tarifa_codigo: string | null;
  tracto_patente: string | null;
  rampla_patente: string | null;
  chofer_nombre: string | null;
  checklist_pct: string;
  checklist_pendientes: number;
  incidentes_abiertos: number;
  documentos_count: number;
  puede_cerrar: boolean;
}

export interface ListaExpedienteNucleo {
  items: ViajeExpedienteResumenNucleo[];
  total: number;
  limit: number;
  offset: number;
  hay_mas: boolean;
}

/* ------------------------------------------------------------------ */
/* P0-07 PWA del conductor                                             */
/* ------------------------------------------------------------------ */
export interface ConductorPerfilNucleo {
  id: string;
  nombre: string;
  rut: string;
  telefono: string | null;
  licencia_clase: string | null;
  numero_licencia: string | null;
  estado: string;
}

export interface MiViajeNucleo {
  chofer: ConductorPerfilNucleo;
  viaje: ViajeExpedienteNucleo | null;
  mensaje: string;
  siguiente_accion: string | null;
  acciones_disponibles: string[];
}

/* ------------------------------------------------------------------ */
/* P0-10 Facturación y cobranza                                        */
/* ------------------------------------------------------------------ */
export interface ViajeFacturableNucleo {
  viaje_id: string;
  numero_viaje: string;
  cliente_id: string;
  cliente_nombre: string;
  orden_compra_id: string | null;
  oc_numero: string | null;
  fecha_inicio: string;
  monto: string;
  tiene_pod: boolean;
}

export interface FacturaViajeNucleo {
  viaje_id: string;
  numero_viaje: string;
  estado: EstadoViajeNucleo;
  monto: string;
  fecha_inicio: string | null;
}

export interface PagoNucleo {
  id: string;
  factura_id: string;
  fecha: string;
  monto: string;
  metodo: string;
  referencia: string | null;
  observaciones: string | null;
  created_at: string;
  created_by: string;
}

export interface NotaCreditoNucleo {
  id: string;
  factura_id: string;
  numero: string;
  fecha: string;
  monto: string;
  motivo: string;
  estado: string;
  created_at: string;
}

export interface PromesaPagoNucleo {
  id: string;
  factura_id: string;
  fecha_prometida: string;
  monto: string;
  estado: string;
  notas: string | null;
  created_at: string;
}

export interface FacturaResumenNucleo {
  id: string;
  numero_factura: string;
  cliente_id: string;
  cliente_nombre: string;
  orden_compra_id: string | null;
  oc_numero: string | null;
  fecha_emision: string;
  fecha_vencimiento: string;
  moneda: string;
  neto: string;
  iva: string;
  total: string;
  pagado: string;
  notas_credito: string;
  saldo: string;
  estado: string;
  dias_atraso: number;
  aging: string;
  viajes_count: number;
  version: number;
}

export interface FacturaNucleo extends FacturaResumenNucleo {
  observaciones: string | null;
  viajes: FacturaViajeNucleo[];
  pagos: PagoNucleo[];
  notas: NotaCreditoNucleo[];
  promesas: PromesaPagoNucleo[];
  created_at: string;
  updated_at: string;
}

export interface AgingBucketNucleo {
  etiqueta: string;
  facturas: number;
  monto: string;
}

export interface AgingNucleo {
  total_cxc: string;
  total_vencido: string;
  facturas_abiertas: number;
  buckets: AgingBucketNucleo[];
  mensaje: string;
}

/* ------------------------------------------------------------------ */
/* P0-11 Alertas y tablero del dueño                                   */
/* ------------------------------------------------------------------ */
export interface AlertaNucleo {
  id: string;
  categoria: string;
  severidad: "critica" | "alta" | "media" | "baja";
  titulo: string;
  detalle: string;
  accion: string;
  link: string;
  entidad_tipo: string | null;
  entidad_id: string | null;
  fecha_referencia: string | null;
}

export interface TableroKpisNucleo {
  cxc_total: string;
  cxc_vencido: string;
  caja_operativa: string;
  viajes_activos: number;
  tractos_activos: number;
  tractos_disponibles: number;
  oc_con_alerta: number;
  documentos_por_vencer: number;
  mantenciones_proximas: number;
  viajes_sin_pod: number;
  viajes_sin_facturar: number;
  freight_score_promedio: string | null;
  alertas_criticas: number;
  alertas_altas: number;
  alertas_medias: number;
}

export interface AccionTableroNucleo {
  titulo: string;
  descripcion: string;
  link: string;
  prioridad: string;
}

export interface TableroNucleo {
  generado_en: string;
  zona_horaria: string;
  kpis: TableroKpisNucleo;
  salud: Record<string, number>;
  alertas: AlertaNucleo[];
  briefing: string[];
  acciones: AccionTableroNucleo[];
  aging: AgingNucleo;
}

/* ------------------------------------------------------------------ */
/* P0-12 Roles, permisos y auditoría                                   */
/* ------------------------------------------------------------------ */
export interface PermisoRolNucleo {
  rol: string;
  permisos: string[];
}

export interface MatrizPermisosNucleo {
  roles: PermisoRolNucleo[];
  permisos: string[];
}

export interface MisPermisosNucleo {
  rol: string;
  permisos: string[];
  empresa_id: string;
}

export interface PaginaAuditoriaNucleo {
  items: HistorialCambioNucleo[];
  total: number;
  limit: number;
  offset: number;
  hay_mas: boolean;
}

export interface TablaAuditoriaNucleo {
  tabla: string;
  total: number;
}

/* ------------------------------------------------------------------ */
/* P0-13 Cutover                                                       */
/* ------------------------------------------------------------------ */
export interface CutoverEstadoNucleo {
  legacy_escritura_congelada: boolean;
  congelada_en: string | null;
  congelada_por: string | null;
  motivo: string | null;
  updated_at: string | null;
  legacy_viajes_abiertos: number;
  nucleo_viajes: number;
  mensaje: string;
}
