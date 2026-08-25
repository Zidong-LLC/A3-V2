# Triage de alcance — decisiones tomadas

**Fecha:** 2 de agosto de 2026 · **Decidido por:** Artel (Zidong)

Clasificación ítem por ítem de todo lo que estaba parcial o sin hacer en el proyecto A3,
contrastado contra los cuatro documentos contractuales (Propuesta V2, Kickoff, Plan de Trabajo
firmado 28/01–02/06/2026 y Respuesta a Cambios Solicitados del 20/05).

Este archivo es la **fuente de verdad del alcance vigente**. Si una reunión con el cliente
contradice alguna de estas decisiones, gana lo que se haya acordado después — pero debe quedar
registrado acá.

## Estado global

| Fase | Avance | Descontando lo bloqueado por A3 |
|---|---|---|
| Fase 1 — Agente conversacional | 76 % | **80 %** |
| Fase 2 — Integraciones | 52 % | **80 %** |
| Fase 3 — Portal y dashboard | 82 % | 82 % |
| **Global** | **67 %** | **81 %** |

Sobre el alcance *originalmente vendido* (antes de las sustituciones acordadas) el avance
equivalente es del 43 %. La diferencia no es trabajo nuevo: es que Siigo, DelSol, LiveConnect,
el tracking GPS y el OCR salieron del alcance por sustitución o acuerdo.

---

## Los 34 ítems

Leyenda: ✅ hecho · ⏳ pendiente nuestro · ⛔ bloqueado por A3 · ➖ fuera del conteo

### Fase 1 — Agente conversacional

| # | Ítem | Decisión | Estado |
|---|---|---|---|
| 1 | Área de PQR en el escalamiento | Lo cubre operaciones, no se crea área nueva | ➖ |
| 2 | Escalado a soporte técnico sin equipo | Se redirige a operaciones (hoy falla en silencio) | ⏳ |
| 3 | Aviso automático al motorizado | Sí se hace | ⏳ |
| 4 | Fecha de recogida al cliente | No se comunica, es a propósito | ➖ |
| 5 | Canal WhatsApp | Sí va a WhatsApp | ⏳ mixto |
| 6 | Consulta de resultados por chat | Sí se hace | ⏳ |
| 7 | Notificaciones por etapa | Alcanza el aviso de resultado publicado, que ya funciona | ➖ |
| 8 | Integración Anarvet / LAB3 | A3 no entregó accesos ni documentación | ⛔ |

### Fase 2 — Integraciones e infraestructura

| # | Ítem | Decisión | Estado |
|---|---|---|---|
| 9 | Facturación electrónica DIAN | El borrador es el entregable; contabilidad emite | ➖ |
| 10 | Fallo de Alegra sin registro | Sí se corrige | ✅ ERR-100 |
| 11 | Inventarios (sustituto de DelSol) | Sí se hace sobre Alegra | ⏳ |
| 12 | Orquestación cross-systems | Diferido hasta que llegue Anarvet | ⛔ |
| 13 | Colas, reintentos y DLQ | Diferido hasta que llegue Anarvet | ⛔ |
| 14 | Observabilidad | Reclasificado a "mínimo útil": health real + alerta | ✅ ERR-101 |
| 15 | API Gateway | Reclasificado a "mínimo útil". Falta rate limit | ✅ parcial |
| 16 | `PORTAL_DEMO_MODE=true` | Se deja mientras sea entorno de pruebas; se apaga al desplegar | ⏳ atado a 25 |

### Fase 3 — Portal y dashboard

| # | Ítem | Decisión | Estado |
|---|---|---|---|
| 17 | Catálogo de análisis en el portal | Sí se corrige (la orden quedaba en $0) | ✅ ERR-097 |
| 18 | Filtros en la lista de solicitudes | Sí se hace | ✅ |
| 19 | Detalle e historial de la orden | Sí se hace | ✅ |
| 20 | Descarga masiva de resultados | Sí se hace | ✅ |
| 21 | Notificaciones por email | Alcanza con WhatsApp y la bandeja del portal | ➖ |
| 22 | Roles y multi-usuario por clínica | No aplica — el roadmap lo condiciona con "(si aplica)" | ➖ |
| 23 | Tracking GPS | **Reemplazado por avance de la orden por estados** | ✅ |
| 24 | Tendencias y TAT en el dashboard | Sí se hace | ⏳ |
| 25 | Deploy a producción | Se hace al cerrar las funcionalidades | ⏳ pausado |
| 26 | Manuales de usuario y capacitación | No se hacen. Ya avisado a A3 en llamada | ➖ |

### Cambios pedidos por A3 el 20 de mayo

De los diez, siete quedaron cerrados. Estos cuatro se decidieron así:

| # | Ítem | Decisión | Estado |
|---|---|---|---|
| 27 | Texto institucional (13 años, registro ICA) | El rechazo actual a particulares cumple la función | ➖ |
| 28 | Corrección ortográfica general | La capitalización actual alcanza | ➖ |
| 29 | Link de pago en línea | Alcanza con derivar a contabilidad. Avisado en llamada | ➖ |
| 30 | Foto de la orden con OCR | Retirado del alcance. Avisado en llamada | ➖ |

### Seguridad y operación

| # | Ítem | Decisión | Estado |
|---|---|---|---|
| 31 | API interna sin autenticación | Se cerró por código (fail-closed). **Falta definir `PLATFORM_API_TOKEN` en `.env`** | ✅ ERR-098 |
| 32 | Webhook de Chatwoot sin firma | Se corrige al desplegar | ⏳ atado a 25 |
| 33 | `POST /setup-webhook` sin auth | Se corrige al desplegar | ⏳ atado a 25 |
| 34 | Migraciones 014 y 015 | Ya estaban aplicadas; la bitácora estaba desactualizada | ➖ |

---

## Componentes sustituidos por acuerdo

No cuentan como deuda: la función contratada se cumplió de otra manera.

| Contratado | Resuelto con |
|---|---|
| Siigo (facturación) | Alegra |
| DelSol (sistema) | Consolidado en Alegra |
| LiveConnect (logística) | Chatwoot |
| Tracking GPS | Avance de la orden por estados (ítem 23) |
| Alta y actualización de clientes por chat | Escala a recepción, por diseño |

---

## Lo que falta, por responsable

**Bloqueado por A3 (~19 puntos del avance global):** Anarvet (8) y lo que arrastra —
orquestación (12) y colas (13). El plan de trabajo firmado fija dos entregas a cargo del cliente
que nunca llegaron: **Día 4 (viernes 30/01/2026)** — *"credenciales/sandboxes + contactos
técnicos + documentación API disponible"* — y **Día 25 (lunes 02/03/2026)** — *"accesos
QA/producción + whitelists/IPs si aplica"*.

**Nuestro (~17 puntos):** inventarios (11, +9,9 — el más pesado), deploy (25), tendencias y TAT
(24), resultados por chat (6), aviso al motorizado (3), escalado a operaciones (2).

**Mixto:** WhatsApp (5) — falta la cuenta Business de A3 **y** un ajuste nuestro (el CHECK de
`requests.entry_channel` solo admite Telegram, y el aviso de resultados llama a Telegram directo
en vez de rutear por Chatwoot). No es honesto presentarlo como bloqueo puro del cliente.

---

## Documentos de esta carpeta

| Archivo | Para quién |
|---|---|
| `01-estado-vs-contrato` | Línea base del 1/08 (58 % sobre el alcance anterior al triage) |
| `02-checklist-ejecucion` | Interno — con rutas de archivo, IDs de error y seguridad |
| `03-estado-para-cliente` | Presentable a A3 |
| `04-avance-visual-a3` | Presentable a A3 — con diagramas de flujo y arquitectura |
| `reuniones/` | Resúmenes de las llamadas con el cliente (pendiente de cargar) |

**Nota sobre los porcentajes:** el documento 01 dice 58 % y los posteriores 67 % / 81 %. No se
contradicen: en este triage el alcance *creció* (entraron observabilidad, gateway, inventarios,
tendencias, descarga masiva, detalle de orden, filtros, WhatsApp y consulta de resultados), así
que el denominador es más grande. El trabajo construido es el mismo.
