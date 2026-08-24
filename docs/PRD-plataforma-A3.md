# PRD — Plataforma web A3 Laboratorio Veterinario

## Propósito

Plataforma web interna de A3, un laboratorio de análisis clínico veterinario en Bogotá.
Tiene dos superficies: un **dashboard de staff** (operaciones del laboratorio) y un
**portal de clientes** (veterinarias que consultan resultados y solicitan recogidas).
Todo el entorno es de PRUEBA: los datos son de prueba y las acciones de facturación
externa (Alegra/DIAN) están bloqueadas por la aplicación.

## Acceso

- **Dashboard staff**: `/login` — formulario de usuario y contraseña. Tras login
  exitoso redirige a `/dashboard` (Panel Ejecutivo).
- **Portal clientes**: `/portal/login` — login por nombre de veterinaria + NIT.
- Sin sesión, cualquier ruta del dashboard redirige a `/login`.

## Módulos del dashboard staff (navegación por sidebar)

1. **Panel** (`/`): Panel Ejecutivo con KPIs de operación (solicitudes activas,
   sin recoger, procesadas, sin motorizado) y de negocio (clientes activos,
   facturación del mes, ticket promedio, tasa de cancelación), pipeline de
   solicitudes por estado, solicitudes recientes, muestras por etapa, carga por
   motorizado, facturación mini, top clientes, charts de TAT y tendencias
   (ApexCharts), feed de actividad y botón "Personalizar" que abre un panel
   lateral para ocultar/mostrar widgets (persiste la preferencia).
2. **Operación** (`/operacion`): centro operativo diario — KPIs del día, alertas y
   excepciones, buscador de órdenes, tabla de órdenes; al hacer clic en una fila se
   abre un panel lateral de detalle con secciones y acciones.
3. **Clientes** (`/clientes`): tabla editable inline de ~990 clientes con filtros
   (búsqueda, tipo, estado, motorizado, facturación electrónica), selector de
   columnas configurable (persiste en localStorage y backend), botón "Sugerir
   motorizados" y acceso a "Nuevo Cliente" (`/clientes/nuevo`, wizard de registro
   documental de 4 pasos).
4. **Pedidos** (`/pedidos`): órdenes de servicio expandibles (tarjeta estilo papel)
   con link a impresión.
5. **Facturación** (`/facturacion`): KPIs de facturación, filtros por estado/fecha/
   NIT/montos, tabla ordenable por columnas con export CSV/Excel, modal de detalle
   de factura. Acciones de reenvío por correo y descarga XML están bloqueadas en
   entorno de pruebas (aviso visible).
6. **Motorizados** (`/motorizados`): KPIs de cobertura, equipo de motorizados
   (teléfono, disponibilidad, color), cobertura por localidad con asignación por
   dropdown, zonas territoriales y mapa Leaflet de cobertura.
7. **Muestras** (`/muestras`): 3 pestañas — kanban de proceso de muestras (etapas:
   a retirar → recogida → recibida laboratorio → en análisis → resultados listos →
   enviada, con dropdown para mover de etapa), catálogo de pruebas con constructor
   de perfiles (agregar pruebas, total en dinero), y perfiles guardados.
8. **Resultados** (`/resultados` del blueprint dashboard_results): subir informe
   PDF (máx 10 MB) identificando destino por número de orden o NIT.

## Portal de clientes

- **Solicitudes**: lista de solicitudes de la veterinaria con detalle por solicitud
  (avance de la orden por etapas, historial). Crear nueva solicitud de recogida
  seleccionando pruebas del catálogo.
- **Resultados**: informes PDF compartidos por el laboratorio, con visor embebido.
- **Notificaciones**: lista con badge de no leídas en el menú.
- **Mi perfil**: datos de la veterinaria.

## Reglas de negocio clave

- Corte a las 17:30: recogidas después del corte pasan al siguiente día hábil + 1.
- Motorizado asignado de forma determinista por zona/localidad del cliente.
- El alta de cliente nuevo requiere revisión (queda "en revisión", no activo).
- Los colores de estado son semánticos: azul=asignada, naranja=en ruta,
  violeta=en laboratorio, verde=procesada, rojo=cancelada.

## Criterios de calidad a verificar

- Login staff correcto e incorrecto (mensaje de error visible).
- Navegación entre los 8 módulos sin errores; cada módulo carga sus datos.
- Filtros y buscadores reducen las filas visibles.
- Selector de columnas oculta/muestra columnas y persiste.
- Kanban de muestras permite mover una muestra de etapa.
- Modal de factura abre y cierra; export CSV descarga.
- Panel lateral de detalle de orden abre desde la tabla de Operación.
- Portal: login por veterinaria+NIT, listas cargan, notificaciones marcan leído.
- Responsive básico y tema oscuro consistente (accesibilidad: focos visibles).

## Fuera de alcance

- El agente conversacional de Telegram/Chatwoot (no es parte de la web).
- Emisión real de facturas (bloqueada; solo lectura de cache local).
- La hoja de impresión de orden de servicio (documento estático para imprimir).
