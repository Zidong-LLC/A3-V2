# Lecciones aprendidas — A3 Laboratorio Veterinario

> Actualizar después de cada corrección del usuario.
> El objetivo es no repetir el mismo error.

---

## Del agente V1 (razón del reinicio)

### L1 — Schema excesivo rompe el modelo
**Problema:** El JSON schema tenía 14 campos obligatorios. El modelo OpenAI prestaba más
atención al formato que a la respuesta conversacional.
**Regla:** Schema máximo 7 campos. Solo lo que realmente se usa.

### L2 — Fases rígidas como puertas rompen el flujo
**Problema:** 8 fases internas que el modelo debía mantener en sync con la BD.
Cualquier desincronía rompía el flujo.
**Regla:** Las fases son tracking interno (`collecting | confirming | done | escalated`).
No son puertas rígidas. Si el usuario da múltiples datos, capturarlos todos y avanzar.

### L3 — Lógica fragmentada es imposible de depurar
**Problema:** `main.py` de 307 KB con lógica mezclada entre archivos.
**Regla:** Un archivo = una responsabilidad. Todos < 200 líneas.
`main.py` solo I/O. `rules.py` solo lógica pura. `services/` solo llamadas externas.

### L4 — El bot sonaba como formulario, no como persona
**Problema:** Preguntas estructuradas A→B→C predecibles. El cliente sentía que
llenaba un formulario.
**Regla:** Una sola pregunta por turno. Tono cercano, colombiano.
Verificar `captured_fields` antes de cada pregunta. No repetir.

### L5 — System prompt y schema mezclados confunden al modelo
**Problema:** El system prompt incluía instrucciones de tono Y de schema en el mismo texto.
**Regla:** `prompt.py` = tono e intenciones. `schema.py` = estructura JSON. Separados.

---

## De sesiones de trabajo futuras

_agregar aquí después de cada corrección_

### L6 — Revisar rutas externas indicadas por el usuario
**Problema:** Se asumió que el dashboard debía estar dentro de `A3 ULTIMO`, pero el usuario lo tenía en otra carpeta/ZIP.
**Regla:** Cuando el usuario mencione una ruta externa, verificar esa ubicación antes de concluir que una pieza no existe.

### L7 — Evitar `Start-Process` en OpenCode (Windows)
**Problema:** Al levantar procesos en segundo plano con `Start-Process` (Flask/ngrok), el runner puede fallar con `ChildProcess.kill`, dejar estados inconsistentes o parecer "trabado".
**Regla:** En OpenCode, priorizar ejecución controlada en un solo comando/script (inicio + verificación + cierre limpio). Evitar procesos detached persistentes durante la sesión.

### L8 — Limpiar identificación fallida antes de reintentar cliente
**Problema:** Una sesión con `_client_not_found` podía conservar un `clinic_name` o `tax_id` viejo y bloquear búsquedas posteriores de veterinarias existentes.
**Regla:** Si el usuario responde con un nuevo identificador después de una identificación fallida, limpiar los campos de identificación contaminados antes de volver a consultar la BD.

### Formato de entrada

```
### L[N] — [Título del patrón]
**Problema:** [qué pasó]
**Regla:** [cómo evitarlo en el futuro]
```
