# A3 Laboratorio Veterinario — Reglas de trabajo

> Leer este archivo PRIMERO antes de cualquier tarea.

---

## ⛔ Entorno de pruebas y datos (NO NEGOCIABLE)

> Leer `docs/guardrails-entorno-y-datos.md` antes de tocar facturación o datos.
> - **TODO es prueba: NUNCA emitir facturas reales a la DIAN ni facturar a un cliente real
>   con datos de prueba.** En Alegra solo se crean BORRADORES en la cuenta de pruebas; no
>   crear facturas (ni borrador) sin avisar antes. Verificar en solo lectura.
> - **La base ya existe y está completa** (Supabase, ~800 clientes con NIT, catálogo con
>   precios reales). Verificar antes de asumir que falta un dato. Credenciales solo en `.env`.

---

## Sesión local de desarrollo

> Al iniciar cualquier sesión de trabajo leer `docs/runbooks/sesion-local.md`.
> ngrok genera una URL nueva cada vez — hay que actualizar Telegram y Chatwoot
> antes de probar cualquier cosa. El runbook tiene todos los pasos y datos.

---

## Workflow de trabajo

### ⛔ No tocar el flujo conversacional sin avisar (NO NEGOCIABLE)
> El flujo conversacional ya funciona en su gran mayoría. Cada paso/proceso aprobado está
> documentado en `docs/contrato-flujo-conversacional.md` (fuente única de verdad).
> - **ANTES de modificar cualquier paso del flujo**, avisar al usuario: "voy a tocar X, por
>   esto", y esperar su OK explícito. No editar y después contar.
> - **Un paso marcado ✅ APROBADO no se toca** salvo pedido directo del usuario.
> - **No rediseñar un paso aprobado como efecto colateral de arreglar otro.** Si arreglar un
>   bug obliga a tocar un paso aprobado, PARAR y avisar primero.
> - **Cambios mínimos y localizados:** un fix toca el paso reportado, no encadena ediciones
>   en pasos vecinos que ya estaban bien.
> - Si no sabés si un paso está bien o mal, **preguntar** ("¿este paso está bien?") y marcar
>   el estado en el contrato antes de avanzar.

### Modo Plan por defecto
- Entrar en modo plan para cualquier tarea no trivial (3+ pasos o decisiones arquitectónicas)
- Si algo se descarrila, PARAR y re-planificar — no seguir empujando
- Escribir specs detallados antes de implementar para reducir ambigüedad

### Gestión de tareas
1. Escribir el plan en `tasks/todo.md` con ítems marcables
2. Verificar el plan antes de empezar la implementación
3. Marcar ítems completos a medida que avanza
4. Resumen de alto nivel en cada paso
5. Agregar sección de resultados al `tasks/todo.md`
6. Actualizar `tasks/lessons.md` después de cada corrección del usuario
7. Registrar TODO bug conversacional en `tasks/errores-soluciones.md` (bitácora central de errores): síntoma, causa raíz, solución, tests y estado. Es la fuente única; sin actualizarla el bug no se considera cerrado (ver `docs/decisions/007-error-solution-log.md`).

### Subagentes
- Usar subagentes para investigación, exploración y análisis paralelo
- Un subagente = una tarea enfocada
- Mantener limpia la ventana de contexto principal

### Verificación antes de marcar completo
- Nunca marcar una tarea como completa sin demostrar que funciona
- Preguntarse: "¿Un desarrollador senior aprobaría esto?"
- Correr tests, revisar logs, demostrar correctitud

### Auto-mejora
- Al INICIO de cada sesión: revisar `tasks/errores-soluciones.md` (bitácora central de errores) y `tasks/lessons.md` para no repetir errores ya resueltos ni reabrir los que están en monitoreo.
- Después de CUALQUIER corrección del usuario: actualizar `tasks/lessons.md` con el patrón
- Escribir reglas para prevenir el mismo error en el futuro
- Revisar lessons al inicio de cada sesión

### Corrección de bugs autónoma
- Cuando se reporta un bug: simplemente arreglarlo. No pedir orientación paso a paso.
- Señalar logs, errores, tests fallidos — luego resolverlos

### Elegancia balanceada
- Para cambios no triviales: pausar y preguntar "¿hay una forma más elegante?"
- Omitir esto para fixes simples y obvios — no sobre-ingeniería

---

## Reglas de colaboración

### Siempre responder en español
Todas las explicaciones, respuestas y mensajes al usuario deben ser en español claro.

### Pensar antes de codificar
Escribir 2–3 párrafos de razonamiento antes de empezar a implementar cualquier cosa.

### Código simple y pequeño
- Archivos < 200 líneas, una responsabilidad por archivo
- Empezar minimal, agregar complejidad solo si es estrictamente necesario
- Si el plan tiene más de 5 archivos, replantear

### Implementar en pasos pequeños
Construir y probar incrementalmente. Cada feature o fix debe funcionar antes de continuar.

### Cambios mínimos al corregir errores
Modificar la menor cantidad de líneas posible. Explicar el problema en español antes de tocar el código.

---

## Contexto del proyecto

**A3 Laboratorio Veterinario** — laboratorio de análisis clínico veterinario en Bogotá. Atiende clínicas y veterinarias por Telegram directo y por Telegram vía Chatwoot.

El agente hace exactamente 4 cosas:
1. Programar recogida de muestras
2. Consultar resultados
3. Pagos/facturación → **siempre escala a contabilidad**
4. Cliente nuevo → **siempre escala a recepción**

### Stack (no cambiar)
- Python 3.12+ + Flask
- Supabase (PostgreSQL) — modelo de datos existente, no modificar
- OpenAI API (gpt-5.5)
- Telegram Bot API + Chatwoot Agent Bot
- Render

### Arquitectura objetivo
```
app/main.py          — Flask + webhooks Telegram/Chatwoot
app/agent.py         — process_turn() como función central con guardrails determinísticos
app/prompt.py        — System prompt
app/schema.py        — JSON schema OpenAI amplio (estado actual)
app/rules.py         — Reglas de negocio
app/config.py        — Variables de entorno
app/services/        — ai.py, db.py, telegram.py, chatwoot.py
```

### Reglas de negocio invariantes
1. Corte a las 17:30 → siguiente día hábil + 1
2. Motorizado asignado determinista (tabla `client_courier_assignment`)
3. Alta de cliente: siempre escala, el bot nunca registra
4. Contabilidad: siempre escala
5. Identificar al cliente antes de registrar cualquier solicitud

### Fuera de alcance V1
Integración Anarvet, envío PDFs, workflow contabilidad, dashboard, WhatsApp, audio/voz.

---

## Por qué se reinició el proyecto

El agente anterior falló por:
- Las fases rígidas rompían el flujo; el estado actual usa `fase_0_bienvenida` a `fase_7_escalado` con guardrails determinísticos.
- El JSON schema volvió a crecer por la orden de servicio; no ampliarlo sin pruebas de regresión.
- Lógica fragmentada en archivos de 307 KB → objetivo vigente: refactor por comportamiento probado, no por tamaño ideal.
- Sonaba como formulario/robot → debe sonar humano, colombiano, cercano

**La lección central: simplicidad técnica sobre completitud de schema.**
