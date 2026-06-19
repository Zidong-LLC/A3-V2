# Hallazgos — Conversaciones reales de Chatwoot

> Fuente: 10 conversaciones extraídas vía API de Chatwoot (`tasks/analisis-chatwoot/raw/`).
> Transcripciones legibles: `transcripciones.md`. Generado el 2026-06-16.
> **Nota de alcance:** Chatwoot pagina y solo devuelve ~20 mensajes recientes por
> conversación, así que algunos chats están truncados al inicio.

## Ubicación temporal (¿bug vivo o histórico?)

| Conv | Cliente | Fecha | Relevancia |
|---|---|---|---|
| 1 | Luciano | **2026-06-16 (HOY)** | Agente actual — multi-orden |
| 4 | Chuuck | **2026-06-16 (HOY)** | Agente actual — post-cierre |
| 10 | Gusmery | **2026-06-15 (ayer)** | Casi actual — confirmación trabada |
| 7 | Adriana | 2026-06-01 | Reciente |
| 8 | SG-SST | 2026-06-01 | Reciente |
| 11 | Jorge | 2026-06-01 | Reciente — identificación |
| 9 | Clara | 2026-05-27 | Intermedio |
| 6 | MUJI | 2026-05-09 | Solo `/start` |
| 5 | Sérgio | 2026-05-06 | Intermedio |
| 2 | Chuuck | 2026-05-04 | Antiguo |

---

## Hallazgos por severidad

### 🔴 CRÍTICO — H1. Confirmación trabada en bucle, la orden nunca cierra (Conv 10, ayer)
- **Qué pasó:** el cliente intentó confirmar **8+ veces** ("Confirmo los datos", "Si",
  "Cierra la orden", "Ninguno", "1", "Sí") y el bot **re-mostró el resumen en bucle**
  alternando con "¿Qué dato quieres corregir?". La orden **nunca se registró**. El cliente
  se fue: *"Esto no avanza" → "Se quedó pegado" → "Chao no funciona"*.
- **Por qué importa:** es la peor experiencia posible (cliente listo para cerrar, frustrado y perdido).
- **Relación bitácora:** es el patrón de **ERR-008 / ERR-015 / ERR-018** (todos marcados
  *corregido*). Esto es una **regresión o un caso no cubierto** por esos fixes — posiblemente
  el "Sí" llega con la sesión fuera de `CONFIRMATION_PHASE` por los turnos intermedios
  ("Buenas", "Esto no avanza"), igual que la causa raíz de ERR-018.
- **Acción:** reproducir el guion exacto de Conv 10 con `validate_flows.py` / modelo real y BD.

### 🔴 CRÍTICO — H2. Bucle de identificación: "soy veterinario" se busca como nombre (Conv 11)
- **Qué pasó:** tras no hallar por teléfono, el cliente dijo "Soy veterinario" y el bot lo
  tomó como **nombre de cliente** → "Encontré demasiadas coincidencias con 'veterinario'".
  Peor: ante "Ver", "Vet", "Soy la veterinaria Josefa", "Nombre… tienda mis mascotas",
  el bot **siguió respondiendo con el mismo término 'veterinario'** (no actualizó la búsqueda)
  → bucle sin salida, jamás ofreció derivar.
- **Relación bitácora:** pariente directo de **ERR-010** (bucle con veterinario independiente,
  *corregido*) y **L6/L18**. Dos defectos: (a) frases tipo "soy veterinario" no son
  identificadores; (b) el término de búsqueda quedó **cacheado/arrastrado** entre turnos.
- **Acción:** verificar por qué "Ver"/"Vet" no reemplazan el término previo y por qué no se
  dispara la red anti-bucle (ERR-013 `_offtrack_count`).

### 🟠 ALTO — H3. Segunda orden (multi-orden) no pide paciente ni análisis nuevos (Conv 1, HOY)
- **Qué pasó:** cliente cierra orden A3-2026-040 y pide *"otro análisis para **otro paciente**"*.
  El bot abre la orden 2, pregunta solo el médico y la **cierra (A3-2026-041) sin pedir el
  paciente nuevo ni el análisis nuevo** → arrastró los datos de la orden 1. La segunda orden
  quedó efectivamente duplicada/incompleta respecto a lo que el cliente pidió.
- **Fricción extra:** "el médico ahora de Gastón, el resto igual" → bot repregunta "¿Cuál es
  el médico solicitante?" → cliente: *"Gastón, te dije"*.
- **Relación bitácora:** es justo lo que **ERR-023** debía cubrir (reset de orden de
  seguimiento: paciente desde cero, análisis reofrecido). Aparece **en el agente de HOY** →
  revisar si la rama `fix/agente-robustez-multiorden` cerró este caso.

### 🟠 ALTO — H4. Estado arrastrado tras el cierre: pregunta médico cuando piden info (Conv 4, HOY)
- **Qué pasó:** orden cerrada (A3-2026-046). El cliente pregunta *"¿hacen análisis a
  reptiles?"* y el bot responde **"¿Cuál es el médico solicitante?"** (totalmente fuera de
  contexto). Antes, "¿qué especies analizan?" recibió el mensaje fijo de *resultados no
  disponibles* (intención mal clasificada). Solo al repetir, derivó a una persona.
- **Relación bitácora:** arrastre de fase post-cierre + clasificación de intención
  (pariente de ERR-023 y del refactor `user_intent_signal`, **ABIERTO-003**).

### 🟡 MEDIO — H5. Se expone el ID interno del motorizado al cliente (Conv 7 y 8)
- **Qué pasó:** el cierre muestra *"Motorizado asignado: Javier (0007f3d0970ec)"* y
  *"Luis (00054ba429228)"* — el **UUID/ID interno** queda visible para el cliente.
- **Relación bitácora:** no registrado. Bug de presentación, fix acotado (no imprimir el ID).

### 🟡 MEDIO — H6. No recuerda "soy cliente nuevo" + respuestas vacías (Conv 5)
- **Qué pasó:** el cliente dijo de entrada *"Soy cliente nuevo y quiero tomar servicios"* y el
  bot respondió **"Claro, con gusto."** / **"Perfecto."** (sin contenido), luego lo hizo dar
  toda la vuelta de identificación y recién al final preguntó "¿Sos cliente nuevo?". No usó la
  señal que el cliente ya había dado.
- **Relación bitácora:** memoria de intención / `user_intent_signal` (ABIERTO-003); respuestas
  enlatadas vacías ("Perfecto.") empobrecen el tono (L4).

### 🟡 MEDIO — H7. Orden de campos inconsistente: raza después de observaciones (Conv 7)
- **Qué pasó:** el bot preguntó observaciones, el cliente dijo "No", y **después** preguntó
  "¿Cuál es la raza del paciente?". El orden de recolección se desordenó.
- **Relación bitácora:** **L11** (el orden de la orden vive en dos lugares sincronizados).

### 🟢 BAJO — H8. Detalle de qué incluye cada perfil no disponible (Conv 2)
- **Qué pasó:** "Dime qué abarcan el 1 y el 2" → el bot **deriva al equipo de catálogo** en
  lugar de listar las pruebas del perfil. Es limitación conocida, pero el cliente quería
  comparar perfiles para decidir y no pudo en el chat.

### 🟢 BAJO — H9. `/start` sin respuesta y typo `/star` (Conv 6 y 5)
- **Conv 6 (MUJI):** solo `/start`, **sin respuesta del bot** registrada (posible no-respuesta
  o conversación abandonada — datos insuficientes).
- **Conv 5:** `/star` (typo) sí se manejó como bienvenida — OK.

---

## Resumen ejecutivo

| # | Hallazgo | Sev | ¿En agente actual? | Bitácora relacionada |
|---|---|---|---|---|
| H1 | Confirmación trabada, nunca cierra | 🔴 | Sí (ayer) | ERR-008/015/018 (regresión) |
| H2 | Bucle identificación "soy veterinario" | 🔴 | Reciente | ERR-010, L18 |
| H3 | 2ª orden no pide paciente/análisis | 🟠 | **Sí (hoy)** | ERR-023 |
| H4 | Estado arrastrado post-cierre | 🟠 | **Sí (hoy)** | ERR-023, ABIERTO-003 |
| H5 | ID interno del motorizado visible | 🟡 | Reciente | — (nuevo) |
| H6 | No recuerda "cliente nuevo" + respuestas vacías | 🟡 | Intermedio | ABIERTO-003, L4 |
| H7 | Orden de campos desordenado | 🟡 | Reciente | L11 |
| H8 | Detalle de perfiles no disponible | 🟢 | — | limitación conocida |
| H9 | `/start` sin respuesta | 🟢 | Antiguo | datos insuficientes |

**Prioridad sugerida para fase 3 (re-simular contra el agente actual):** H1, H3 y H4
primero — son los de impacto alto y los dos últimos son de HOY, así que confirman si la rama
actual ya los resolvió o siguen vivos.

---

## Resultados de simulación (fase 3) — 2026-06-16

Reproducción contra el **agente + modelo reales** (BD mockeada) con
`tools/scripts/diag_chatwoot.py`. Cada flujo replica el guion del chat real.

| # | Resultado | Evidencia |
|---|---|---|
| **H4** | 🔴 **VIVO — reproducido idéntico** | Tras cerrar la orden, "¿hacen análisis a reptiles?" → el bot responde **"¿Cuál es el médico solicitante?"** (exactamente como el chat real). El estado de orden se arrastra tras el cierre. |
| **H3** | ✅ **RESUELTO** | La 2ª orden ya **reofrece datos y pregunta "¿Cuál es el nombre del paciente?"** en vez de cerrar arrastrando. Corregido en la rama `fix/agente-robustez-multiorden`. |
| **H2** | ✅ **RESUELTO** | "soy veterinario" ya **muestra opciones** y los turnos siguientes **no arrastran** el término; termina derivando. Desapareció el bucle infinito de "demasiadas coincidencias". |
| **H1** | ⚠️ **No reproducido en esta corrida** | Con la orden **completa**, el agente **sí cerró** (A3-2026-002). El chat real de Gusmery no cerraba porque tenía la **dirección sin confirmar** (el bot pedía "responde 1) sí, esa dirección está bien"); ese dato faltante bloqueaba el cierre determinista y generaba el bucle resumen↔corregir (patrón ERR-018). Falta reproducirlo con ese estado exacto. |

### Estado final (tras corrección y verificación)

| # | Estado | Detalle |
|---|---|---|
| **H4** | ✅ **CORREGIDO HOY** | Fix en `app/agent.py`: tras cerrar, una consulta `off_topic`/`unclear` que no pide otra orden **deriva de una** en vez de pedir el médico. Verificado con `diag_chatwoot.py H4`, suite 77/77 y `validate_flows.py A`. Registrado como **ERR-025**. |
| **H3** | ✅ ya resuelto | La 2ª orden reofrece datos y pide el paciente nuevo (rama de robustez multi-orden). |
| **H2** | ✅ ya resuelto | "soy veterinario" muestra opciones, no arrastra el término, deriva. Sin bucle. |
| **H1** | ✅ no reproducible | El agente actual **cierra la orden** incluso con la dirección sin confirmar (la auto-confirma al progresar, `agent.py` ~3093). El chat real era previo a los fixes del 16-jun. **ABIERTO-005** → monitoreo. |
| **H5** | ✅ ya resuelto | El ID interno del motorizado ya no se muestra: el commit `694e518` dejó solo el nombre. Chats 7/8 eran anteriores. |
| **H6** | ✅ **CORREGIDO HOY** | Las respuestas vacías ("Perfecto.") ya no ocurren. Al reproducirlo apareció un bug real: un escalado de cliente nuevo marcaba `_order_registered`, y "sí, soy nuevo" arrancaba una orden en vez de escalar. Corregido en `_finalize_request`. Registrado como **ERR-026**. |
| **H7** | ✅ no reproducible | El agente actual pide los campos en orden (médico→paciente→especie→raza→sexo→edad→propietario→observaciones). El desorden del chat real (raza tras observaciones) no ocurre. |

**Conclusión:** de los 4 hallazgos graves, **3 ya estaban resueltos** y **H4 se corrigió hoy**.
De los menores, **H5 y H7 ya estaban resueltos** y **H6 se corrigió hoy** (destapó ERR-026).
**No queda ningún bug vivo de estas conversaciones.**

> Script de reproducción: `tools/scripts/diag_chatwoot.py` (uso: `python … [H1 H2 H3 H4]`).
</content>
</invoke>
