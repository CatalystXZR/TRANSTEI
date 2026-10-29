> **ARCHIVADO 2026-10-29 — NO CITAR COMO ESTADO.**
> Documento histórico. Reemplazos y contexto: `docs/_archivo/README.md` · Estado real: `docs/estado.md`.
> Sus cifras y afirmaciones de "terminado" NO fueron re-verificadas en esta fecha.

# PLAN DE DESARROLLO — ERP "Transportes TEI SpA"

> Documento maestro del plan. Aprobado por el cliente.
> Fuente de verdad ante discrepancias: `prompts.md` (estados y paleta de colores).

## 1. Decisiones fijadas

| Tema | Decisión |
|---|---|
| Fuente de verdad | `prompts.md` manda: estado `Finalizado`, azul `#2A237A`, amarillo `#FCD116` |
| Moneda/formato | CLP sin decimales `$ 1.500.000`, fechas DD/MM/AAAA, interfaz es-CL |
| Roles | Admin (dueño), Operación (secretaria), Contabilidad (contador) |
| Entorno actual | 100% local (pruebas exhaustivas) + Supabase cloud gratis (DB/Auth/Storage), preparado para migrar a Vercel/Render a corto plazo |
| IVA | Facturas afectas y exentas; gastos con flag IVA recuperable sí/no; cuadratura día 20 |
| Sueldos | Base + % comisión + anticipos descontables + ajustes manuales (bonos/descuentos) |
| Mantenimiento | Pauta por flota con ítems e intervalos en km; alerta a 5.000 km antes + alerta permanente al vencer |
| Alertas calendario | 30 días antes (rev. técnica, seguro, licencias), configurable en Ajustes |
| Respaldos | Foto boleta de gasto (cámara celular) + PDFs de facturas |
| Reportes | Exportar Excel/CSV + liquidación PDF desde plantilla parametrizada (pendiente archivo del cliente) |
| Git | Monorepo: `frontend/`, `backend/`, `supabase/`, `docs/` |

## 2. Arquitectura

```
TRANSTEI/
├── frontend/          # Next.js App Router + TS + Tailwind + Shadcn UI
├── backend/           # FastAPI + SQLModel + Pydantic
├── supabase/          # Migraciones SQL + seed
└── docs/              # Decisiones, API spec, manual de usuario
```

- Auth: Supabase Auth (JWT) → backend valida token; rol en tabla `usuarios`
- Variables de entorno desde día 1 (`SUPABASE_URL`, `DATABASE_URL`, etc.)
- Docker Compose opcional para replicar entorno

## 3. Modelo de datos

```
usuarios(auth_id, nombre, rol)                      ← roles: admin/operacion/contabilidad
clientes(razon_social, rut, dias_pago, telefono, email, activo)
choferes(nombre, rut, sueldo_base, porcentaje_produccion, vencimiento_licencia, activo)
tractos(patente, marca, modelo, ano, km_actual, venc_rev_tecnica, venc_seguro, activo)
ramplas(patente, tipo, venc_rev_tecnica, activo)
viajes(fecha_inicio, fecha_fin, origen, destino, estado, valor_flete_neto,
       FK cliente, chofer, tracto, rampla)          ← Programado→En Ruta→Finalizado→Facturado
gastos_viaje(viaje_id, categoria, monto, iva_recuperable, respaldo_url, fecha, notas)
facturas(numero_sii, cliente_id, tipo(afecta/exenta), monto_neto, iva, total,
         fecha_emision, fecha_vencimiento, fecha_pago, estado)  ← Pendiente/Pagada/Anulada
factura_viaje(factura_id, viaje_id)                 ← N:M
anticipos_chofer(chofer_id, fecha, monto, mes_liquidacion, notas)
ajustes_liquidacion(chofer_id, mes, tipo(bono/descuento), concepto, monto)
liquidaciones(chofer_id, mes, base, comision, anticipos, ajustes, total, estado, pdf_url)
pautas_mantenimiento(item, intervalo_km)            ← aceite, filtro aceite, engrase, filtro aire,
                                                       pastillas freno, discos freno, etc.
mantenimientos(tracto_id, pauta_id, fecha, km, costo, notas, respaldo_url)
configuracion(clave, valor)                         ← iva=19, alerta_km=5000, dias_alerta=30
```

## 4. Fases de ejecución

### FASE 0 — Fundaciones (setup)
- Monorepo, Supabase project, migraciones SQL + seed
- Backend base: auth JWT, middleware de roles, estructura de routers
- Frontend base: tema TEI, layout sidebar, login, guard de rutas por rol, utilidades CLP
- **Hito**: login con 3 roles funcionando

### FASE 1 — Mantenedores (CRUD)
- Clientes, Choferes, Tractos, Ramplas: tablas grandes, botones visibles, validación RUT, formateo CLP
- **Hito**: datos maestros cargados y editables

### FASE 2 — Operaciones (Viajes + Dashboard)
- Crear viaje, máquina de estados con validaciones, gastos con foto boleta
- Dashboard: viajes activos, KPIs, centro de alertas v1
- **Hito**: "qué camión fue a dónde y con qué gastos"

### FASE 3 — El dinero (Facturación + IVA)
- Fletes por facturar → asociar factura N° SII; semáforo cobranzas; cuadratura IVA mensual
- **Hito**: "quién me debe plata y cuánto IVA debo pagar"

### FASE 4 — Sueldos, Mantenimiento y Alertas
- Pauta de mantenimiento por flota con alertas por km
- Calculadora de liquidaciones (base + comisión − anticipos ± ajustes)
- Generador PDF con plantilla parametrizada (pendiente archivo)
- Alertas calendario 30 días configurables
- **Hito**: liquidaciones legales imprimibles + cero mantenimientos olvidados

### FASE 5 — Reportes, Datos históricos y Preparación cloud
- Exportación Excel/CSV
- Importación/limpieza de planillas Excel históricas
- Preparación migración: CORS, env vars, health checks, CI básico
- Documentación de despliegue Vercel + Render

## 5. Reglas de cálculo (backend, no frontend)

1. **Comisión**: Σ `valor_flete_neto` de viajes `Finalizado`/`Facturado` del mes × `porcentaje_produccion`
2. **Rentabilidad viaje**: flete − Σ gastos − pago chofer estimado
3. **IVA**: facturas afectas 19% (configurable); cuadratura = débito − crédito
4. **Próximo mantenimiento**: km última mantención + intervalo; estados: OK / Por vencer (≤5.000 km) / Pendiente permanente

## 6. UX (obligatorio, usuario de 55 años)
- Mínimo 16px, ideal 18px en datos críticos; semáforo Rojo/Amarillo/Verde estricto
- Formato CLP instantáneo; tablas con acciones visibles; cero menús ocultos
- Responsive: PC oficina + celular terreno

## 7. Pendientes del cliente
1. Plantilla parametrizada de liquidación (Word/PDF) → Fase 4
2. Planillas Excel para migración → Fase 5
3. Confirmar ítems e intervalos reales de la pauta de mantenimiento (arrancar con valores por defecto configurables)

## 8. Riesgos
- Formato desordenado de Excel → fase de limpieza con reglas de validación
- Migración cloud → mitigado usando Supabase cloud desde el inicio
- Plantilla PDF legal → iniciar Fase 4 solo con archivo en mano
