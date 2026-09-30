Documento de Arquitectura y Especificaciones Técnicas

Sistema ERP: Transportes TEI SpA

1. Visión y Propósito del Proyecto

1.1. ¿Qué es este software?

Es un sistema ERP (Enterprise Resource Planning) web, diseñado a la medida para la gestión operativa y financiera de la empresa de transporte de carga terrestre Transportes TEI SpA. Está enfocado exclusivamente en administrar la relación entre la flota (tractocamiones y ramplas), los choferes, los viajes (fletes) y la facturación.

1.2. El Propósito (El "Para Qué")

El objetivo principal es automatizar la carga mental, financiera y logística del dueño de la empresa (usuario de 55 años, acostumbrado a procesos manuales/Excel). El sistema busca:

Transformar la incertidumbre en datos claros (saber exactamente cuánto se debe cobrar, a quién, y qué gastos existen).

Automatizar cálculos tediosos (sueldos variables de choferes, cuadratura de IVA).

Prevenir pérdidas por negligencia (alertas de mantenimiento y vencimiento de documentos).

Entregar una vista centralizada, estructurada y simple del negocio.

2. Identidad Visual y UI/UX (Diseño)

Basado en el logo de Transportes TEI SpA, el sistema utilizará una paleta de colores estricta que transmite profesionalismo corporativo y permite crear alertas visuales claras.

2.1. Paleta de Colores (Tailwind CSS)

Color Primario (Índigo Profundo TEI): Extraído de las letras "TEI". Transmite estabilidad y confianza.

Uso: Barra de navegación lateral (Sidebar), encabezados principales, botones de acción primaria ("Guardar", "Nuevo Viaje").

Equivalente Tailwind: bg-indigo-900 o #31237A.

Color Secundario (Amarillo Alerta TEI): Extraído de la estela derecha del logo.

Uso: Notificaciones, estados de advertencia (Ej: "Factura por vencer", "Revisión técnica en 30 días"), botones de acción secundaria.

Equivalente Tailwind: text-yellow-500 o #F4C01E.

Color Neutro (Gris Asfalto): Extraído de los arcos del logo.

Uso: Bordes de tablas, textos secundarios, fondos de pantalla.

Equivalente Tailwind: bg-gray-100 (fondo), text-gray-500 (textos menores), #808285.

Color de Fondo: Blanco puro (bg-white) para las tarjetas (cards) y tablas, asegurando máximo contraste para la lectura.

2.2. Reglas de Usabilidad (Para usuario de 55 años)

Fuentes grandes: Tamaño mínimo de texto 16px (text-base), idealmente 18px (text-lg) para datos importantes.

Formato de Moneda Automático: Todo input numérico y visualización de dinero debe formatearse en pesos chilenos instantáneamente (Ej: $ 1.500.000).

Cero "Click-Derecho": Todas las acciones (Editar, Eliminar, Ver Factura) deben ser botones visibles y grandes en cada fila de las tablas.

3. Stack Tecnológico Definitivo

Este stack te permite desarrollo rápido, validación estricta de datos y escalabilidad futura para IA.

Frontend (La Interfaz):

Framework: Next.js (React) usando App Router.

Estilos: Tailwind CSS.

Componentes UI: Shadcn UI (tablas, modales, selectores preconstruidos y accesibles).

Hosting recomendado: Vercel.

Backend (El Motor / API):

Framework: FastAPI (Python). Excelente rendimiento, validación automática y fácil integración con scripts de IA futuros.

ORM: SQLModel (combina Pydantic y SQLAlchemy).

Hosting recomendado: Render o Railway.

Base de Datos y Autenticación:

Motor: PostgreSQL. Obligatorio por la integridad transaccional (dinero y relaciones complejas).

Proveedor: Supabase (ofrece PostgreSQL alojado y maneja el login/seguridad de manera transparente).

4. Arquitectura de Base de Datos (Esquema Relacional)

La base de datos se estructura separando los componentes físicos y lógicos.

clientes: id, razon_social, rut, dias_pago (entero, ej: 30), telefono, email.

choferes: id, nombre, rut, sueldo_base, porcentaje_produccion (decimal, ej: 0.15 para 15%), vencimiento_licencia.

tractos: id, patente, marca, modelo, ano, km_actual, vencimiento_revision_tecnica, vencimiento_seguro.

ramplas: id, patente, tipo (plana, sider), vencimiento_revision_tecnica.

viajes (Core): id, fecha_inicio, fecha_fin, origen, destino, estado (Programado, En Ruta, Entregado, Facturado), valor_flete_neto, cliente_id, chofer_id, tracto_id, rampla_id.

gastos_viaje: id, viaje_id, categoria (Combustible, Peaje, Viático, Mantenimiento en ruta), monto, respaldo_url (foto boleta).

facturas: id, numero_sii, cliente_id, fecha_emision, fecha_vencimiento, monto_neto, iva, total, estado (Pendiente, Pagada, Anulada).

factura_viaje: Tabla intermedia (muchos a muchos) que asocia uno o más viajes a una factura específica.

5. Módulos y Funcionalidades del Sistema

Módulo 1: Dashboard Principal (El Panel de Control)

Tarjetas de Resumen (KPIs): "Ingresos del Mes", "Cuentas por Cobrar (Atrasadas)", "Gastos del Mes".

Centro de Alertas: Lista de acciones urgentes (Facturas vencidas que cobrar, revisiones técnicas a punto de vencer, licencias de choferes expirando).

Viajes Activos: Tabla rápida con los camiones que están en ruta hoy.

Módulo 2: Despacho y Operaciones (Viajes)

Creación de Viaje: Formulario donde se selecciona (mediante listas desplegables) el Cliente, Chofer, Tracto y Rampla. Se define Origen, Destino y Valor a cobrar.

Liquidación de Gastos: Dentro de cada viaje, poder ingresar cuánto se gastó en petróleo y peajes para calcular la rentabilidad real de ese flete.

Módulo 3: Facturación y Cobranzas (Caja)

Fletes por Facturar: Una vista que muestra todos los viajes con estado "Entregado". Permite seleccionar varios viajes de un mismo cliente y hacer clic en "Asociar Factura", ingresando el Nro emitido en el SII.

Control de Pagos: Panel tipo "Semáforo".

Verde: Facturas cobradas.

Amarillo: Facturas por vencer (ej. a 5 días).

Rojo: Facturas vencidas (dinero en la calle que hay que cobrar).

Cálculo IVA: Vista mensual que suma el IVA de las facturas emitidas menos el IVA de gastos registrados, dando el monto a pagar el día 20.

Módulo 4: Recursos Humanos (Choferes)

Perfil del Chofer: Datos personales y estado de su licencia de conducir.

Calculadora de Liquidaciones: Al cerrar el mes, el sistema toma el Sueldo Base del chofer y le suma el porcentaje correspondiente del valor_flete_neto de todos los viajes que él finalizó en ese mes.

Módulo 5: Flota y Mantenimiento

Ficha de Equipos: Historial de cada tracto y rampla.

Mantenimiento Preventivo: Al actualizar el km_actual de un tracto al finalizar un viaje, el sistema calcula si se acerca a la marca de cambio de aceite y dispara una alerta al Dashboard.

6. Plan de Desarrollo Paso a Paso

No programes todo al mismo tiempo. Sigue estas fases:

FASE 1: Estructura e Infraestructura (Semana 1)

Crear el proyecto Supabase y ejecutar los scripts SQL para crear las tablas principales (clientes, tractos, choferes, viajes).

Levantar el backend en FastAPI y conectar a Supabase mediante SQLModel. Crear los endpoints básicos (CRUD).

Levantar el frontend en Next.js, configurar Tailwind con la paleta de colores "TEI" y conectar el Login.

FASE 2: MVP Operacional (Semanas 2-3)

Desarrollar los mantenedores básicos: Agregar/Editar Clientes, Choferes, Tractos y Ramplas.

Desarrollar el Módulo de Viajes: Interfaz para crear un flete, asignarle recursos y cambiarle el estado.

Implementar la tabla del Dashboard solo con los viajes en curso.
Hito: Tu padre ya puede registrar qué camión fue a qué lugar.

FASE 3: El Flujo del Dinero (Semanas 4-5)

Crear el Módulo de Facturación.

Permitir asociar "Viajes finalizados" a "Facturas".

Crear el panel de "Cuentas por Cobrar" ordenado por fecha de vencimiento y con semaforización de colores.
Hito: Tu padre ya sabe quién le debe plata y cuándo pagan.

FASE 4: Costos, Sueldos y Alertas (Semanas 6+)

Agregar el registro de Gastos por viaje.

Desarrollar la calculadora automática de sueldos de choferes.

Implementar el sistema de alertas (fechas de vencimiento) en el Dashboard.