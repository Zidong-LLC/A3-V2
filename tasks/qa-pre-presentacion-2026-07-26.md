# Informe de QA — pre-presentación al cliente (2026-07-26)

Testeo integral del estado del proyecto: conexiones, integraciones y flujo conversacional.
Alcance y decisiones acordadas con el usuario antes de empezar; hallazgos documentados sin
tocar código del agente (decisión explícita del usuario).

---

## 1. Veredicto

**GO con reservas.** El núcleo del negocio —identificar cliente, armar la orden, cobrar bien
y cerrarla con número— funciona y quedó validado contra el modelo real **en dos corridas
independientes**. Los tres bugs de dinero que estaban sin verificar en vivo (ERR-077/079/087)
**pasaron las dos veces**.

Las reservas, por orden de importancia para la demo:

1. **El bloque raza ↔ especie falla de forma consistente** (QA1 y QA4 en rojo en las 2
   corridas): corregir la raza en cadena, o dar una raza que no corresponde a la especie
   declarada, entra en bucle. Es el punto frágil real, no ruido estadístico.
2. **ERR-088** — si el cliente dice "no estamos registrados" y después se corrige, el bot
   queda mudo sin salida desde el chat.
3. **Variabilidad entre corridas** — 33/35 y 30/35 sin ningún cambio de código.

---

## 2. Capa técnica: conexiones e integraciones

| Verificación | Resultado |
|---|---|
| Supabase — 15 tablas × columnas | ✅ `supabase_state=ok` (992 clientes, 159 análisis, 133 perfiles, 1.649 barrios) |
| Integridad de datos | ✅ exit 0 — sin duplicados ni huérfanos reales |
| Carga de datos (`verify_update_documents`) | ⚠️ solo faltan los 3 de Club Animals (ERR-085, fuera de alcance por decisión) |
| OpenAI | ✅ responde en **2,3 s**, JSON válido contra el schema. Modelo: `gpt-5.4-mini` |
| Alegra — credenciales y lectura | ✅ `ping()` OK |
| Alegra — flags de seguridad | ✅ `ALEGRA_ENABLED=True`, `ALEGRA_PRODUCTION=False` (acciones DIAN bloqueadas en el dashboard) |
| Alegra — escritura autorizada | ✅ borrador creado y **releído**: `invoice_id=16`, `status=draft`, $58.000, contacto demo (no un cliente real) |
| Flask local `/health` | ✅ `{"status":"ok"}` |
| Cadena Telegram → Chatwoot → Agente | ✅ verificada punta a punta |
| Suite de tests | ✅ **498 passed**, 2 skipped, 1 xfailed |

**Hallazgo de infraestructura:** el Agent Bot de Chatwoot apuntaba a
`hortencia-spathaceous-carleen.ngrok-free.dev`, que devolvía **404 — el túnel estaba caído**,
o sea que el bot estaba desconectado de Telegram. Como es un dominio ngrok **fijo/reservado**,
se reconectó levantando ngrok con `--domain=...` sin tocar la configuración de Chatwoot.
Conviene saberlo: si el bot "no responde" antes de la demo, esta es la causa más probable y
el arreglo no requiere entrar a Chatwoot.

---

## 3. Flujo conversacional contra el modelo real

`validate_flows.py` — 35 flujos multi-turno, OpenAI real, catálogo real (159 análisis, 332 razas).

| Corrida | Resultado | Flujos en rojo |
|---|---|---|
| 1 | **33/35 OK** | QA1, QA4 |
| 2 | **30/35 OK** | QA1, QA4, **+** F, T, V |

Las dos corridas separan con claridad dos cosas distintas:

- **Fallos CONSISTENTES (rojos en ambas corridas) — son bugs reales, no ruido:**
  - **QA1** — correcciones encadenadas de raza ("no perdón, es criollo"): bucle en la edad.
    Ya estaba documentado como rojo en ERR-075.
  - **QA4** — especie declarada + raza de otra especie: bucle en la raza.
  - Los dos son de la **misma familia: raza ↔ especie**. Es el punto más frágil del flujo hoy.
- **Fallos NO DETERMINISTAS (solo en la corrida 2):** F (flaky conocido, ABIERTO-001), T, V.
  Confirman la lección de ERR-076: *un flujo que pasa una vez no está probado*.

Para la demo: el bloque raza/especie merece un guion ensayado; el resto puede variar entre
corridas sin que haya cambiado nada del código.

### Los 11 fixes que estaban sin validar en vivo

| Caso | Criterio | Veredicto |
|---|---|---|
| ERR-077 — menú "1, 3 y 6" | los tres perfiles, total sumado | ✅ (flujos P/Q/R OK) |
| ERR-079 — "5 del 1 y 6 del 3" | sin análisis intrusos | ✅ |
| ERR-087 — pedido mixto | los tres conceptos sobreviven | ✅ (QA8, QA9 OK) |
| ERR-076 — perfil + sueltos | el perfil no se pierde | ✅ (QA9 OK) |
| ERR-050 — perfil + agregar análisis | el área en afirmativo agrega bien | ✅ (flujo X OK) |
| ERR-083 — "Nose" a la raza | no repregunta, queda "Sin determinar" | ✅ (QA5 OK) |
| ERR-085 — nombres del Excel | "Agrocolombia", "VeroPets", "Citycan", "Maxivet" identifican bien | ✅ |
| ERR-080 — el "Sí" registra la orden | `request_id` real, no bucle | ✅ en los flujos de cierre |
| ERR-074 — raza desconocida | no traba la orden | ✅ |
| QA1 — correcciones de raza encadenadas | sin bucle | ❌ **rojo en las 2 corridas** (ver §3) |
| QA4 — especie declarada + raza de otra especie | sin bucle | ❌ **rojo en las 2 corridas** |
| ERR-084 — médico "José Toro" | no inventar especie/sexo | no se re-probó: abierto por decisión previa |

---

## 4. QA con conversaciones REALES de Chatwoot (aporte nuevo de esta sesión)

Idea del usuario: usar los chats que ya hicieron el equipo de A3 y el del cliente en vez de
guiones escritos por nosotros. Se construyeron dos herramientas nuevas:

- [tools/scripts/extract_chatwoot_history.py](tools/scripts/extract_chatwoot_history.py) — baja las conversaciones (solo lectura).
- [tools/scripts/replay_chatwoot_qa.py](tools/scripts/replay_chatwoot_qa.py) — las segmenta y las reproduce contra el agente real.

**Corpus obtenido:** 11 conversaciones, **2.361 turnos del cliente**, 80 sesiones utilizables.

> ⚠️ **La API de Chatwoot truncaba en 20 mensajes por conversación sin avisar.** La primera
> extracción devolvió 82 turnos; con paginación correcta, 2.361. El corpus estaba **96% oculto**.
> Es la lección L56 (`.limit()` que trunca en silencio) repitiéndose en otra API.

**Cómo leer estos resultados:** el replay envía los turnos del cliente en secuencia, pero esos
turnos respondían a preguntas de versiones anteriores del agente. Es **fuzzing con lenguaje
real**, no una reproducción fiel: sirve para encontrar bloqueos, crashes y bucles, pero no toda
divergencia es un bug. Por eso cada hallazgo se confirmó después **aislado y reproducible**.

### Lo que encontró (confirmado aparte, sin depender del corpus)

1. **ERR-088 — el escalado a "cliente nuevo" es irreversible.** El cliente dice "creo que no
   estamos registrados", el bot escala y setea `_blocked=True`; cuando se corrige ("sí estamos,
   somos Maxivet" — cliente real), **el bot no responde nunca más**. En el corpus real esto pasó:
   Gusmery Ruiz siguió escribiendo **12 turnos al vacío**, incluido su propio nombre.
   *Medido:* de 4 variantes, **3 sí se recuperan** (nombre mal escrito, duda, nombre inexistente).
   Solo falla cuando el cliente *declara* no estar registrado.
2. **ERR-089 — "Dale Pets"** no se reconoce en el reintento porque `"dale"` está en la lista de
   afirmativos. Familia "Toro" (ERR-075/078/084). *Medido:* **1 de 992 clientes**, con workaround
   (decir "veterinaria Dale Pets" o el NIT ya funciona).
3. **ERR-090 — dos preguntas laterales se ignoran textualmente.** *Medido:* de 5 preguntas reales,
   **3 se atienden bien** (precio, horario, desconcierto); fallan las de metainformación del
   proceso ("¿a dónde me vas a confirmar?", "pero ya estaba registrado"). Es UX, no correctitud.

Los tres quedaron registrados en [tasks/errores-soluciones.md](tasks/errores-soluciones.md).
**No se tocó código**: por decisión del usuario, ERR-088 y ERR-089 solo se documentan (el fix de
ERR-088 caería sobre B3, que está ✅ APROBADO en el contrato).

### Evidencia histórica del corpus (lo que ya pasó en producción)
- **9 casos** de frustración explícita del cliente ("Ya te lo dije", "es una perra ya te dije"),
  todos con el mismo patrón: el bot re-pregunta un dato ya entregado.
- ERR-087 se ve ocurriendo en vivo: *"Necesito análisis de sangre u orina, sodio y potasio"* →
  *"Listo, queda análisis de sangre"*. Ese caso hoy está corregido y validado.

---

## 5. Riesgos para la presentación

| # | Riesgo | Mitigación sugerida |
|---|---|---|
| 1 | **ERR-088**: si alguien dice "no estamos registrados" y se corrige, el bot queda mudo | No incluir ese camino en el guion; si pasa, reiniciar la conversación |
| 2 | **Túnel ngrok caído** = bot desconectado, sin error visible | Verificar `/health` por la URL pública **antes** de empezar |
| 3 | **Raza ↔ especie (QA1/QA4)**: corregir la raza en cadena o dar raza que no corresponde a la especie → bucle. Falla consistente | Dar raza y especie coherentes y a la primera; no corregir la raza dos veces seguidas |
| 3b | **No-determinismo**: el mismo flujo puede fallar en una corrida y no en otra (F, T, V) | No improvisar caminos raros; ensayar el guion exacto 2 veces |
| 4 | **ERR-084 abierto**: médico "José Toro" inventa especie y sexo | Evitar apellidos de animal en el nombre del médico |
| 5 | **ERR-082**: latencia (fuera de alcance por decisión) | Referencia medida: OpenAI responde en 2,3 s; el resto del turno es overhead a diagnosticar |
| 6 | `/health` no detecta caídas de dependencias (devuelve 200 con Supabase caído) | Verificar además con `check_supabase_state.py` |

---

## 6. Pendiente de esta sesión

- **Prueba por Telegram real**: entorno listo y verificado (Flask + ngrok + Chatwoot, con un
  POST real ya recibido en `/chatwoot/webhook`), faltan las 3 conversaciones —camino feliz,
  ráfaga "1/1/2" y escalado a Contabilidad—. Requiere que el usuario escriba desde Telegram.
- **QA1 / QA4** quedan como los dos fallos consistentes a resolver. No se tocaron en esta
  sesión por la decisión de solo documentar; son la familia raza ↔ especie, que ya acumula
  ERR-074/075/078/083/084.

---

## 7. Cómo reproducir todo esto

```bash
python -m pytest -q                                    # 498 passed
python tools/scripts/check_supabase_state.py           # exit 0
python tools/scripts/alegra_smoke.py                   # ping OK
python tools/scripts/validate_flows.py                 # 35 flujos, modelo real

# QA con conversaciones reales (nuevo)
python tools/scripts/extract_chatwoot_history.py       # baja el corpus (solo lectura)
python tools/scripts/replay_chatwoot_qa.py --list      # lista segmentos, sin gastar tokens
python tools/scripts/replay_chatwoot_qa.py --limit 6   # reproduce los más sospechosos

# Entorno local (el dominio ngrok es fijo: no hay que tocar Chatwoot)
python -m flask --app app.main run --port 5000 --host 0.0.0.0
ngrok http 5000 --domain=hortencia-spathaceous-carleen.ngrok-free.dev
python tools/scripts/verify_chatwoot_telegram_agent.py
```
