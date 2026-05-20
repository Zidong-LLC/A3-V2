# A3 Laboratorio Veterinario — Reglas de trabajo

> Leer este archivo PRIMERO antes de cualquier tarea.

---

## Sesión local de desarrollo

> Al iniciar cualquier sesión de trabajo leer `docs/runbooks/sesion-local.md`.
> ngrok genera una URL nueva cada vez — hay que actualizar Telegram y Chatwoot
> antes de probar cualquier cosa. El runbook tiene todos los pasos y datos.

---

## Workflow de trabajo

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

### Subagentes
- Usar subagentes para investigación, exploración y análisis paralelo
- Un subagente = una tarea enfocada
- Mantener limpia la ventana de contexto principal

### Verificación antes de marcar completo
- Nunca marcar una tarea como completa sin demostrar que funciona
- Preguntarse: "¿Un desarrollador senior aprobaría esto?"
- Correr tests, revisar logs, demostrar correctitud

### Auto-mejora
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

**A3 Laboratorio Veterinario** — laboratorio de análisis clínico veterinario en Bogotá. Atiende clínicas y veterinarias por Telegram.

El agente hace exactamente 4 cosas:
1. Programar recogida de muestras
2. Consultar resultados
3. Pagos/facturación → **siempre escala a contabilidad**
4. Cliente nuevo → **siempre escala a recepción**

### Stack (no cambiar)
- Python 3.12+ + Flask
- Supabase (PostgreSQL) — modelo de datos existente, no modificar
- OpenAI API (gpt-5.5)
- Telegram Bot API
- Render

### Arquitectura objetivo
```
app/main.py          — Flask + webhook (< 100 líneas)
app/agent.py         — process_turn() como función central
app/prompt.py        — System prompt
app/schema.py        — JSON schema OpenAI
app/rules.py         — Reglas de negocio
app/config.py        — Variables de entorno
app/services/        — openai.py, supabase.py, telegram.py
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
- 8 fases internas → ahora 4: `collecting | confirming | done | escalated`
- JSON schema de 14 campos → ahora máximo 7 campos útiles
- Lógica fragmentada en archivos de 307 KB → archivos pequeños con responsabilidad única
- Sonaba como formulario/robot → debe sonar humano, colombiano, cercano

**La lección central: simplicidad técnica sobre completitud de schema.**
