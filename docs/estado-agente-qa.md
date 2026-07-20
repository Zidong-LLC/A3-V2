# Estado del agente conversacional — QA y hallazgos

> Última actualización: 2026-07-20. Documento de estado para revisión.
> Detalle técnico completo de cada error en `tasks/errores-soluciones.md`.

---

## Resumen

El agente cubre las 4 funciones del negocio (programar recogida, consultar resultados,
pagos → contabilidad, cliente nuevo → recepción). El **flujo feliz y la mayoría de las
etapas están sólidos**, validados con QA adversarial usando el **modelo real y la base
real** (cliente Animal Pets, catálogo con precios reales). Lo que todavía falla son
**combos y correcciones a mitad de conversación**, que quedan documentados abajo.

---

## Qué funciona bien (QA de estrés, 8 baterías, 2026-07-20)

| Etapa | Estado |
|-------|--------|
| Identificación de cliente (NIT, nombre parcial, multi-coincidencia, particular) | ✅ OK |
| Captura de datos del paciente (especie exótica, datos en bloque, ráfagas) | ✅ OK |
| Selección de análisis (perfil, por área, código inexistente, pedido mixto) | ✅ OK |
| Pedido mixto "sodio potasio y orina" (registra únicos + ofrece el ambiguo) | ✅ OK |
| Perfil por nombre / categoría ("un prequirúrgico" → variantes) | ✅ OK |
| Pago (contraentrega / pago en línea → contabilidad) | ✅ OK |
| Confirmación y cierre con número de orden y motorizado | ✅ OK |
| Multi-orden ("otra orden", "lo mismo para otro paciente") | ✅ OK |
| Corrección de un dato con acuse ("me confundí, la raza es X") | ✅ OK |
| Cambio de cliente a mitad de orden (fraseos comunes + flexivos) | ✅ OK (reforzado) |
| Red de seguridad de estado (FSM en modo bloqueo) | ✅ Activo |

---

## Errores / limitaciones conocidos (pendientes)

Todos son de la **misma clase**: cuando el cliente combina dos intenciones en una frase, o
corrige un dato dando el valor nuevo en el mismo mensaje, un atajo interno responde antes de
que el modelo lea el turno. El modelo clasifica bien; el pipeline lo intercepta.

| # | Caso | Qué hace hoy | Debería |
|---|------|--------------|---------|
| 1 | "cambia la edad a 5 años **y confirmo**" | Vuelve a preguntar la edad | Corregir a 5 años y confirmar |
| 2 | "ponme un hemograma **pero cambiá el paciente** a Rocky" | Recomienda perfiles | Registrar el hemograma y corregir el paciente |
| 3 | Corrección de especie + nombre en un turno | Avanza sin acusar el cambio | Acusar "corrijo a X" |
| 4 | "cambiala a la veterinaria **de siempre**" | Variable (a veces no cambia) | Cambiar de cliente |

**Ninguno pierde datos de forma silenciosa ni factura mal** — son de experiencia
conversacional (el bot responde algo distinto a lo pedido, o pide un dato que ya se dio).

### Por qué no se parchean ahora

Estos casos exigen que los atajos internos de corrección/confirmación **cedan el turno al
modelo**, lo cual requiere reorganizar el pipeline central (la tarea "Tanda D": partir
`process_turn`). Un parche puntual arriesga romper algo que hoy funciona — ya pasó una vez
(ver ERR-072 en la bitácora). Se resuelven de raíz junto con esa reorganización.

---

## Trabajo de fondo completado (refactor Fase 3)

- **3.4a** — 21/21 guardrails movidos a módulos por responsabilidad; `agent.py` bajó a ~3.180 líneas.
- **3.2** — Red de seguridad de estado (FSM) en modo bloqueo: repara estados inconsistentes antes de guardar.
- **3.3** — La intención la interpreta el modelo (las señales) y el código la hace cumplir; los detectores de palabras quedan como respaldo.

## Próximos pasos

1. **Tanda D** — partir `process_turn` en módulos; resuelve de raíz los 4 pendientes de arriba.
2. Ronda final de QA de estrés tras la Tanda D.
3. Deploy a Render (hoy corre local con ngrok).
