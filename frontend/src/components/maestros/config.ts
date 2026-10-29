export type TipoMaestro = "clientes" | "tractos" | "ramplas" | "choferes";

export type CampoConfig = {
  key: string;
  label: string;
  type: "text" | "number" | "date" | "checkbox" | "select" | "percent" | "csv";
  required?: boolean;
  placeholder?: string;
  help?: string;
  options?: { valor: string; etiqueta: string }[];
  step?: string;
  min?: number;
  full?: boolean;
};

export const ETIQUETA_MAESTRO: Record<TipoMaestro, string> = {
  clientes: "Clientes",
  tractos: "Tractos",
  ramplas: "Ramplas",
  choferes: "Choferes",
};

const ESTADOS_RECURSO = [
  { valor: "disponible", etiqueta: "Disponible" },
  { valor: "asignado", etiqueta: "Asignado" },
  { valor: "en_ruta", etiqueta: "En ruta" },
  { valor: "en_taller", etiqueta: "En taller" },
  { valor: "en_descanso", etiqueta: "En descanso" },
  { valor: "bloqueado", etiqueta: "Bloqueado" },
  { valor: "vacaciones", etiqueta: "Vacaciones" },
  { valor: "baja", etiqueta: "Baja" },
];

const TIPOS_RAMPLA = [
  { valor: "plana", etiqueta: "Plana" },
  { valor: "sider", etiqueta: "Sider" },
  { valor: "refrigerada", etiqueta: "Refrigerada" },
  { valor: "portacontenedor", etiqueta: "Portacontenedor" },
  { valor: "cisterna", etiqueta: "Cisterna" },
  { valor: "cama_baja", etiqueta: "Cama baja" },
  { valor: "granelera", etiqueta: "Granelera" },
  { valor: "otra", etiqueta: "Otra" },
];

export const CAMPOS: Record<TipoMaestro, CampoConfig[]> = {
  clientes: [
    { key: "razon_social", label: "Razón social", type: "text", required: true },
    { key: "rut", label: "RUT", type: "text", required: true },
    { key: "giro", label: "Giro", type: "text" },
    { key: "direccion", label: "Dirección", type: "text" },
    { key: "comuna", label: "Comuna", type: "text" },
    { key: "ciudad", label: "Ciudad", type: "text" },
    { key: "contacto_nombre", label: "Contacto", type: "text" },
    { key: "contacto_email", label: "Email de contacto", type: "text" },
    { key: "contacto_telefono", label: "Teléfono de contacto", type: "text" },
    { key: "dias_pago", label: "Días de pago", type: "number", required: true, min: 0 },
    { key: "credito_autorizado", label: "Crédito autorizado (CLP)", type: "number", min: 0 },
    { key: "exige_oc", label: "Exige OC para facturar", type: "checkbox" },
    { key: "activo", label: "Activo", type: "checkbox" },
    { key: "observaciones", label: "Observaciones", type: "text", full: true },
  ],
  tractos: [
    { key: "patente", label: "Patente", type: "text", required: true },
    { key: "marca", label: "Marca", type: "text" },
    { key: "modelo", label: "Modelo", type: "text" },
    { key: "ano", label: "Año", type: "number" },
    { key: "vin", label: "VIN", type: "text" },
    { key: "color", label: "Color", type: "text" },
    { key: "configuracion_ejes", label: "Configuración de ejes", type: "text" },
    { key: "peso_bruto_kg", label: "Peso bruto (kg)", type: "number", required: true, min: 1 },
    { key: "tara_kg", label: "Tara (kg)", type: "number", required: true, min: 1 },
    { key: "capacidad_carga_kg", label: "Capacidad de carga (kg)", type: "number", required: true, min: 1 },
    { key: "volumen_m3", label: "Volumen (m³)", type: "number", min: 0, step: "0.001" },
    { key: "km_actual", label: "Km actual", type: "number", min: 0 },
    { key: "horas_motor", label: "Horas motor", type: "number", min: 0 },
    { key: "licencias_permitidas", label: "Licencias permitidas", type: "csv", help: "Separadas por coma. Ej: A4, A5" },
    { key: "estado", label: "Estado operativo", type: "select", options: ESTADOS_RECURSO },
    { key: "activo", label: "Activo", type: "checkbox" },
    { key: "ubicacion_ciudad", label: "Ciudad actual", type: "text" },
    { key: "ubicacion_lat", label: "Latitud", type: "number", step: "0.000001" },
    { key: "ubicacion_lon", label: "Longitud", type: "number", step: "0.000001" },
    { key: "observaciones", label: "Observaciones", type: "text", full: true },
  ],
  ramplas: [
    { key: "patente", label: "Patente", type: "text", required: true },
    { key: "tipo", label: "Tipo", type: "select", options: TIPOS_RAMPLA, required: true },
    { key: "marca", label: "Marca", type: "text" },
    { key: "modelo", label: "Modelo", type: "text" },
    { key: "ano", label: "Año", type: "number" },
    { key: "vin", label: "VIN", type: "text" },
    { key: "capacidad_carga_kg", label: "Capacidad de carga (kg)", type: "number", required: true, min: 1 },
    { key: "volumen_m3", label: "Volumen (m³)", type: "number", min: 0, step: "0.001" },
    { key: "largo_m", label: "Largo (m)", type: "number", min: 0, step: "0.001" },
    { key: "ancho_m", label: "Ancho (m)", type: "number", min: 0, step: "0.001" },
    { key: "alto_m", label: "Alto (m)", type: "number", min: 0, step: "0.001" },
    { key: "peso_tara_kg", label: "Tara (kg)", type: "number", min: 0 },
    { key: "ejes", label: "Ejes", type: "number", min: 1 },
    { key: "temperatura_min_c", label: "Temp. mínima (°C)", type: "number", step: "0.1" },
    { key: "temperatura_max_c", label: "Temp. máxima (°C)", type: "number", step: "0.1" },
    { key: "estado", label: "Estado operativo", type: "select", options: ESTADOS_RECURSO },
    { key: "activo", label: "Activo", type: "checkbox" },
    { key: "ubicacion_ciudad", label: "Ciudad actual", type: "text" },
    { key: "ubicacion_lat", label: "Latitud", type: "number", step: "0.000001" },
    { key: "ubicacion_lon", label: "Longitud", type: "number", step: "0.000001" },
    { key: "observaciones", label: "Observaciones", type: "text", full: true },
  ],
  choferes: [
    { key: "rut", label: "RUT", type: "text", required: true },
    { key: "nombre", label: "Nombre", type: "text", required: true },
    { key: "apellido_paterno", label: "Apellido paterno", type: "text" },
    { key: "apellido_materno", label: "Apellido materno", type: "text" },
    { key: "fecha_nacimiento", label: "Fecha de nacimiento", type: "date" },
    { key: "telefono", label: "Teléfono", type: "text" },
    { key: "email", label: "Email", type: "text" },
    { key: "direccion", label: "Dirección", type: "text" },
    { key: "comuna", label: "Comuna", type: "text" },
    { key: "ciudad", label: "Ciudad", type: "text" },
    { key: "numero_licencia", label: "Número de licencia", type: "text" },
    { key: "licencia_clase", label: "Clase de licencia", type: "text" },
    { key: "licencia_restricciones", label: "Restricciones", type: "text" },
    { key: "autorizado_carga_peligrosa", label: "Autorizado carga peligrosa", type: "checkbox" },
    { key: "sueldo_base", label: "Sueldo base (CLP)", type: "number", min: 0 },
    { key: "porcentaje_comision", label: "Comisión (%)", type: "percent", min: 0, step: "0.01", help: "Ej: 5 = 5%" },
    { key: "contacto_emergencia_nombre", label: "Contacto de emergencia", type: "text" },
    { key: "contacto_emergencia_telefono", label: "Teléfono de emergencia", type: "text" },
    { key: "estado", label: "Estado operativo", type: "select", options: ESTADOS_RECURSO },
    { key: "activo", label: "Activo", type: "checkbox" },
    { key: "observaciones", label: "Observaciones", type: "text", full: true },
  ],
};

export function formInicial(tipo: TipoMaestro): Record<string, string | boolean> {
  const form: Record<string, string | boolean> = {};
  for (const campo of CAMPOS[tipo]) {
    if (campo.type === "checkbox") form[campo.key] = campo.key === "activo";
    else if (campo.type === "select") form[campo.key] = campo.options?.[0]?.valor ?? "";
    else if (campo.type === "csv") form[campo.key] = "A5";
    else if (campo.type === "percent") form[campo.key] = "5";
    else if (campo.key === "dias_pago") form[campo.key] = "30";
    else if (campo.key === "credito_autorizado" || campo.key === "sueldo_base") form[campo.key] = "0";
    else if (campo.key === "km_actual" || campo.key === "horas_motor") form[campo.key] = "0";
    else form[campo.key] = "";
  }
  return form;
}

export function formDesdeRegistro(
  tipo: TipoMaestro,
  registro: Record<string, unknown>,
): Record<string, string | boolean> {
  const form: Record<string, string | boolean> = {};
  for (const campo of CAMPOS[tipo]) {
    const valor = registro[campo.key];
    if (campo.type === "checkbox") {
      form[campo.key] = Boolean(valor);
    } else if (campo.type === "percent") {
      form[campo.key] = String(Number(valor ?? 0) * 100);
    } else if (campo.type === "csv") {
      form[campo.key] = Array.isArray(valor) ? valor.join(", ") : "";
    } else if (campo.type === "select") {
      form[campo.key] = String(valor ?? campo.options?.[0]?.valor ?? "");
    } else {
      form[campo.key] = valor === null || valor === undefined ? "" : String(valor);
    }
  }
  return form;
}

export function bodyDesdeForm(
  tipo: TipoMaestro,
  form: Record<string, string | boolean>,
): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const campo of CAMPOS[tipo]) {
    const valor = form[campo.key];
    if (campo.type === "checkbox") {
      body[campo.key] = Boolean(valor);
    } else if (campo.type === "csv") {
      body[campo.key] = String(valor ?? "")
        .split(",")
        .map((v) => v.trim())
        .filter(Boolean);
    } else if (campo.type === "percent") {
      body[campo.key] = (Number(valor) || 0) / 100;
    } else if (campo.type === "number") {
      body[campo.key] = String(valor).trim() === "" ? null : Number(valor);
    } else {
      const texto = String(valor ?? "").trim();
      body[campo.key] = texto === "" ? null : texto;
    }
  }
  return body;
}
