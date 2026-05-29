# Tareas — A3 Laboratorio Veterinario V2

---

## Agente Conversacional — Completado

### Core (Bloques 1–4)
- [x] `schema.py` → 10 campos, intents en inglés, 8 fases nombradas, message_mode, pending_intents, confidence
- [x] `prompt.py` → system prompt limpio, sin JSON embebido
- [x] `rules.py` → INTENT_TO_SERVICE_AREA + TERMINAL_PHASES
- [x] `db.py` → get_or_create_session, update_session, create_request alineados con modelo real
- [x] `agent.py` → pending_intents entre turnos, transición a fase terminal
- [x] `ai.py` → recibe pending_intents, filtra campos internos

### Tests obligatorios — 11/11 ✓
- [x] Test 1: cliente con motorizado asignado → solicitud `assigned`
- [x] Test 2: cliente sin motorizado → `error_pending_assignment` + evento en `request_events`
- [x] Test 3: cliente nuevo → `fase_7_escalado` inmediato, sin recolectar datos
- [x] Test 4: solicitud post-17:30 → `scheduled_pickup_date` = siguiente día hábil
- [x] Test 5: múltiples intenciones en un mensaje → ambas procesadas en orden correcto
- [x] Test 6: usuario repite sin dar dato → agente ofrece opciones en vez de preguntar de nuevo
- [x] Test 7: usuario cancela solicitud en curso → cancelación confirmada, flujo limpio
- [x] Test 8: conversación interrumpida y retomada → sin saludo, continúa donde estaba
- [x] Test 9: gestión de pagos → derivación inmediata a contabilidad
- [x] Test 10: alta de cliente nuevo → derivación inmediata a operaciones
- [x] Test 11: toda solicitud de ruta → priority siempre "normal" en BD

### Modificaciones V2.1 (llamadas con cliente)
- [x] Preguntas conversacionales, una por turno (no formulario)
- [x] Búsqueda progresiva de cliente: NIT → nombre → escalada
- [x] Forma de pago: contado vs contraentrega (PASO 4 del flujo)
- [x] Recolección conversacional: exam_type → patient_name → species (patient_age/owner_name opcionales)
- [x] "Crear tu perfil": selected_tests, catálogo individual, cálculo de subtotal/total
- [x] Chat permanece abierto: solo cierra con despedida explícita del usuario
- [x] Notificación del motorizado al cerrar orden (`agent.py` → append a reply)
- [x] Múltiples órdenes en misma sesión: reset de campos de orden al retomar desde fase terminal

---

## Agente Conversacional — Pendiente

### Tests nuevos (V2.1)
- [x] Múltiples órdenes en misma sesión: segunda orden con cliente ya identificado
- [x] "Crear tu perfil": seleccionar análisis individuales, ver subtotal calculado
- [x] Notificación de motorizado: mensaje incluido en cierre de orden

---

## Plataforma Interna — Pendiente (NO es el agente conversacional)

Estas funciones se implementarán en la plataforma de gestión, no en el chatbot.

- [ ] **Descuentos por cantidad**: `calculate_discount()` en `rules.py` es placeholder (retorna 0). Las reglas de descuento las define el cliente y se configuran desde la plataforma. La BD las persiste; el agente solo las lee.
- [ ] **Asignación por zonas geográficas**: hoy el agente asigna por `client_courier_assignment` (tabla por cliente). La asignación por zona requiere la tabla de zonas que define el cliente; se gestiona desde la plataforma.
- [ ] **Integración ANARVET**: consulta de estado de análisis. La plataforma expone el estado; el agente lo consumirá vía endpoint interno cuando esté disponible.
- [ ] **Integración ALEGRA**: generación de facturas al completar una orden. Se resuelve desde el backend de la plataforma, no desde el agente.
- [ ] **Gestión de zonas y motoristas**: calendario de repartidores, asignación manual de override, edición de zonas.
- [ ] **Dashboard y reportes**: órdenes por día, por motorista, por zona, perfiles más solicitados.
- [ ] **Gestión de clientes**: alta manual, edición de datos, vinculación a zona.
- [ ] **Gestión de portafolio**: cargar nuevo catálogo, editar precios, definir perfiles predefinidos.

### Información pendiente del cliente (bloquea algunas de las anteriores)
- [ ] Números de teléfono para escalar contabilidad/pagos y PQRs
- [ ] Definición de zonas geográficas (número, descripción, motorista asignado)
- [ ] Tabla de descuentos por cantidad de parámetros
- [ ] Estructura de perfiles predefinidos en el catálogo
- [ ] API ANARVET: endpoint, autenticación, datos expuestos
- [ ] API ALEGRA: endpoint, autenticación, campos requeridos

---

## Resultados

**2026-04-27** — Bloques 1-4 completados.
**2026-04-30** — Tests obligatorios validados: 11/11 completados.
**2026-05-01** — Flujo de búsqueda progresiva + forma de pago cerrados para V2.1.
**2026-05-03** — Separación plataforma vs. agente documentada. Notificación de motorizado y múltiples órdenes en sesión implementadas en `agent.py`.
**2026-05-11** — Tests V2.1 pendientes cubiertos y suite validada: 64/64.
**2026-05-11** — Alta manual de clientes en dashboard afinada: validación de formulario, motorizado sugerido y contexto de motorizados cubiertos por tests. Suite validada: 68/68.
**2026-05-15** — Zonas territoriales A3 estructuradas: `data/barrios_zonas_a3.csv`, `app/territory.py`, migración `006_territorial_zones.sql` y scripts de carga. Supabase actual: 8 motorizados verificados y 282 asignaciones cliente→motorizado cargadas. Pendiente aplicar migración con credencial admin SQL para subir 1649 barrios.
**2026-05-15** — Alta manual de cliente ahora sugiere motorizado automaticamente por barrio/localidad/zona, con override manual del operador. Endpoint `GET /api/dashboard/courier-suggestion` y guardado de `courier_suggestion` en revisión. Suite validada: 83/83.
**2026-05-15** — Autocompletado de barrios agregado en alta manual: `GET /api/dashboard/neighborhood-search`, autollenado de localidad/zona y sugerencia de motorizado. Suite validada: 84/84.
**2026-05-15** — Flujo de migracion territorial cerrado: script `apply_supabase_migration.py` para aplicar DDL con `SUPABASE_ACCESS_TOKEN`, seed territorial idempotente y runbook actualizado. Service role key no permite crear tablas.
**2026-05-15** — Proyecto autosuficiente con `.env` local protegido por `.gitignore`; seeds corren sin rutas antiguas. Operacion territorial funcional con fallback interno hasta que existan tablas territoriales en Supabase.
**2026-05-15** — Centro Operativo Diario agregado en `/operacion`: KPIs de rutas, aprobaciones, muestras abiertas, alertas, rutas por gestionar y clientes nuevos. Suite validada: 85/85.
**2026-05-15** — Agenda por motorizado agregada dentro de `/operacion`, agrupando rutas activas por mensajero y columna `Sin asignar`. Suite validada: 86/86.
**2026-05-24** — Orden de servicio conversacional alineada al PDF oficial: datos completos antes de pago/cierre, persistencia en `request_events.event_payload.service_order`, vista Supabase `service_orders` preparada y PDF guardado en `docs/forms/orden-de-servicio-2025.pdf`. Suite validada: 131/131.
**2026-05-24** — Plataforma muestra ordenes de servicio del agente en `/operacion` y `/muestras`, con ficha visual tipo formulario y tarjetas derivadas en proceso de muestras. Suite validada: 133/133.
**2026-05-24** — Agregada vista imprimible de orden de servicio en `/ordenes-servicio/<request_id>/imprimir`, accesible desde las fichas como `Imprimir PDF` para imprimir o guardar desde el navegador. Suite validada: 134/134.
**2026-05-24** — Flujo multiorden ajustado: al cerrar una orden el agente pregunta si necesita otra para otro paciente/animal; respuesta afirmativa inicia nueva orden sin reidentificar cliente y respuesta negativa cierra la conversacion. Suite validada: 137/137.
