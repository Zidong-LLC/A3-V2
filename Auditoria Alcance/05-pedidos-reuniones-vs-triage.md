# Consolidado de reuniones vs. triage de alcance

**Fecha:** 2 de agosto de 2026 · **Cobertura: las 10 reuniones (07/04 – 28/07/2026)**
**Fuentes:** `reuniones/` + `00-decisiones-triage.md` + verificación directa contra el código

> **Actualizado con las reuniones de levantamiento del 7 y 8 de abril** (`00a` y `00b`), que son
> transcripción literal. Varias fechas de origen retroceden a abril — ver §1.4 y §1.7.

Para cada pedido del cliente: qué pidió, en qué llamada, si se hizo, y si choca con el triage.
Todo estado ✅ / ❌ fue verificado en archivo y línea, no en documentación interna.

Leyenda: ✅ hecho · ⚠️ parcial · ❌ no hecho · ⛔ bloqueado · ❓ no determinable

---

## 0. El hallazgo principal

**El pago al final del pedido no es un pedido nuevo de la llamada 8. Se pidió el 20 de mayo.**

Llamada 5, punto 6, textual:

> *"Después de completar una orden, el bot debe preguntar si quiere anexar otra orden o
> continuar. **Si el usuario elige continuar, pasa a forma de pago.**"*

Y en el mismo punto A3 aclara que *"una veterinaria puede enviar 10 órdenes en una sola
recogida"*. La secuencia pedida era: orden → ¿otra orden? → pago.

Lo que hay hoy en [flow.py:23-28](app/flow.py#L23): `payment_method` es un campo obligatorio
**de cada orden**, y la oferta de "otra orden" llega **después** de registrar y cobrar la
primera ([messages.py:95](app/messages.py#L95)).

Esto cambia la naturaleza de la discusión de la llamada 8, donde el equipo planteó que mover el
pago *"puede implicar retrabajo"* y A3 respondió que *"no es un cambio de negocio, sino una
lógica que recién se ve al llegar a la prueba completa"*. **A3 tiene razón sobre el fondo, y
además tiene el antecedente del 20 de mayo a favor.** Lo que la llamada 8 sí agrega es la
nomenclatura "pedido", la factura agrupada y el resumen sin forma de pago.

Conviene saberlo antes de sentarse a discutir si se cobra como alcance adicional.

---

## 1. Contradicciones con el triage

### 1.1 Asignación de motorizado por zona — pedida en TRES llamadas

| | |
|---|---|
| **Pedido** | **Llamada 1, punto 6:** A3 explica la base por zonas; Luciano confirma que *"la IA asigne mensajero automáticamente según clasificación de zonas"*. **Llamada 2, punto 13:** *"debe existir autoasignación por zona"*, con recepción confirmando antes de notificar. **Llamada 4, punto 6:** *"las zonas se asignarán automáticamente cuando se integre el archivo enviado por A3"*. **Llamada 5, punto 12:** cambiar un motorizado de zona en la plataforma *"se reflejará en el agente conversacional"*. |
| **Triage** | *"Asignación de domiciliario por zona — ASÍ A PROPÓSITO — Motorizado fijo por clínica es lo que requiere la operación"*. Fuera del conteo. |
| **Código** | Ambas cosas conviven. La zonificación está construida ([territory.py](app/territory.py), `territorial_zones`, 8 zonas, 1.649 barrios) y A3 la validó en la llamada 5 (*"les gusta mucho el mapa"*). Pero el motorizado de la orden sale de `client_courier_assignment` — fijo por clínica ([db.py:1226](app/services/db.py#L1226)). |
| **Veredicto** | **La contradicción más documentada del proyecto.** Cuatro llamadas lo piden, el triage lo declara decisión de diseño. Lo pedido está construido y no se usa para decidir la orden. |

### 1.2 No permitir cambiar el cliente maestro

| | |
|---|---|
| **Pedido** | Llamada 7, punto 16: **no debe permitirse** cambiar el cliente una vez seleccionado; si está mal, se anula y se empieza de nuevo. Sí cambia dirección y análisis. Reafirmado en el punto 17. |
| **Triage** | No figura. |
| **Código** | [ERR-099](tasks/errores-soluciones.md) abierto y crítico, tratado como bug a corregir **permitiendo** el cambio. |
| **Veredicto** | Si se aplica lo que A3 decidió, ERR-099 se cierra bloqueando el cambio, no arreglándolo. Menos trabajo y es su decisión. |

### 1.3 Pago en línea — pedido en cuatro llamadas, con proveedor definido

| | |
|---|---|
| **Pedido** | **Llamada 2, puntos 16 y 17:** el bot no debe generar el link por seguridad; debe redirigir a plataforma segura; medios: PSE, transferencia, contraentrega; *"no usar la palabra crédito"*. **Llamada 5, punto 6:** las formas de pago son contraentrega o pago en línea. **Llamada 6, punto 11.** **Llamada 8, punto 14: Wompi/Bancolombia.** |
| **Triage** | Ítem 29: *"Alcanza con derivar a contabilidad. Avisado en llamada"*. Fuera del conteo. |
| **Código** | `payment_method == "pago_linea"` existe como opción ([confirmacion.py:158](app/enforcers/confirmacion.py#L158)); no hay pasarela. |
| **Veredicto** | **Es el ítem con más recorrido y menos resolución.** Cuatro llamadas, proveedor elegido, y el triage lo da por cubierto derivando a contabilidad. |

### 1.4 Alta de cliente nuevo con validación humana

| | |
|---|---|
| **Pedido** | **Origen real: reunión 00b (08/04), transcripción literal.** Adriana define los dos tipos de cliente —clínica o médico independiente— y el documento de cada uno: tarjeta profesional para el médico, RUT o cámara de comercio para la clínica. Justifica la tarjeta: *"aquí incluso muchos veterinarios no sacan RUT… la tarjeta profesional es un documento indispensable para que el veterinario ejerza su labor"*. Y exige aprobación humana: *"que recaiga esa aprobación directamente por un profesional… Estamos en Colombia, se pueden falsificar documentos"*. Luciano propone el mecanismo y ella confirma: *"Exactamente"*. Agrega que **la primera venta la acompaña una persona** y después pasa a automática. · **Llamada 2, puntos 8 y 10:** derivar a atención al cliente; notificación en plataforma; **documentos a una carpeta de Google Drive**. **Llamada 1, punto 14:** consultar antes si existe en Alegra; preregistro; aviso al contador. **Llamada 3, punto 3:** el bot debe decir explícitamente *"te asignaremos un asesor"*. |
| **Triage** | *"Alta de cliente nuevo por chat — ASÍ A PROPÓSITO — Escala a recepción"*. |
| **Código** | Existe el escalado y el alta desde el dashboard. **No hay recepción de archivos adjuntos** en el bot ni integración con Drive. |
| **Veredicto** | Coincide el principio, no el alcance. Falta toda la parte documental. **Y el pedido no es de abril 22: es del 8 de abril, con transcripción literal que lo respalda.** |

### 1.7 Afiliación médico ↔ clínica — nació el 8 de abril, no en julio

| | |
|---|---|
| **Pedido** | **Reunión 00b (08/04), transcripción literal.** Adriana: *"las clínicas veterinarias grandes tienen sucursales por un lado. Por otro lado, tienen rotación de médicos"*. Pide *"que la clínica afilie sus médicos veterinarios que están vinculados con ella. Paso solo para las clínicas, los médicos independientes no"*. Y explica el porqué: *"una clínica puede tener cinco médicos, pero también puede decir: este médico ya no trabaja con nosotros… eso es importante para nosotros para el tema de facturación, porque si un médico que ya no está en la clínica pide un examen…"*. Luciano acuerda que la gestión sea control humano en la plataforma; Adriana confirma. |
| **Reaparece** | **Llamada 6 (27/05)**: no avanzar sin médico verificado. **Llamada 7 (07/07), punto 22**: nombre completo, apellido, identificación y tarjeta profesional, y *"confirmar que ese médico está autorizado para solicitar órdenes por esa clínica"*. |
| **Código** | Existe `clients_a3_professionals` y la búsqueda inversa `find_clients_by_professional` ([agent.py:3295](app/agent.py#L3295)), que sirve para identificar la clínica a partir del médico. **No encontré la validación que bloquee a un médico no autorizado**, ni la gestión de alta/baja de la afiliación desde la plataforma. |
| **Veredicto** | El pedido tiene **casi cuatro meses**, no dos. Cuando A3 lo repita, el antecedente del 8 de abril está en transcripción literal. Conviene resolverlo antes de la reunión de cierre. |

### 1.5 Anarvet — el supuesto cambió dos veces

| | |
|---|---|
| **Pedido** | **Llamada 4, punto 4:** Anarbet pide documento formal firmado; **el acceso solicitado es solo de lectura**; objetivo: leer estados y obtener documentos/resultados en PDF. **Llamada 8, punto 22: darían acceso por base de datos SQL, solo consulta, no doble vía.** **Punto 23:** si solo hay SQL, el PDF del resultado habría que generarlo desde la plataforma. |
| **Triage** | Ítem 8: *"A3 no entregó accesos ni documentación"* ⛔. Doc 01 asume *"endpoint, credenciales y documentación de la API"*. |
| **Veredicto** | Desde el 13/05 se sabía que era **solo lectura**; el 28/07 se supo que el mecanismo sería **SQL directo, no API REST**. El triage quedó desactualizado en ambos frentes, y aparece trabajo nuevo no contemplado: **generar nosotros el PDF de resultados**. Arrastra los ítems 12 y 13, diferidos *"hasta que llegue Anarvet"*. |

### 1.6 PQR con link

| | |
|---|---|
| **Pedido** | Llamada 2, punto 7: *"PQR se maneja con un link"*; pendiente integrar el link correcto en el bot. |
| **Triage** | Ítem 1: *"Lo cubre operaciones, no se crea área nueva"* ➖. |
| **Veredicto** | Contradicción menor pero real: A3 no pidió un área, pidió **un enlace**. Es más barato que lo decidido y sigue sin estar. |

---

## 2. El caso del OCR — buena noticia

El doc 01 advierte que la foto de la orden con OCR *"fue un pedido explícito del cliente el 20 de
mayo"* y que retirarla sin acta *"reaparece en la reunión de cierre"*.

**La llamada 5, punto 5, dice otra cosa.** A3 *preguntó* si se podía; desarrollo respondió que
técnicamente sí, con el riesgo de que la foto salga desenfocada o con letra ilegible; y el punto
cierra: *"Pendiente: decidir si esta opción se agrega como alternativa o si se mantiene solo carga
manual por chat."*

**Nunca fue un compromiso: quedó como decisión abierta.** Retirarlo del alcance es defendible con
el propio acta. Además, la llamada 8, punto 3, refuerza el argumento práctico: en la prueba real
la orden fotografiada **no se entendía** y tuvieron que dictarla.

---

## 3. Pedidos sin registro en ningún lado

Ninguno figura en los 34 ítems del triage ni en los documentos 01 y 04.

| # | Pedido | Llamada | Estado |
|---|---|---|---|
| 3.1 | **Calendario de mensajeros** — compensatorios, permisos, vacaciones; sección para registrar quién trabaja cada día | 1 | ❌ Cero coincidencias en el repo |
| 3.2 | **Jerarquía pedido → órdenes → análisis** | 8 | ❌ Cada orden es un `request` independiente |
| 3.3 | **Forma de pago al cierre del pedido** | **5**, 8 | ❌ Ver §0 |
| 3.4 | **Una factura por pedido**, con varias órdenes | 8 | ❌ `invoices_cache.request_id` |
| 3.5 | **Nombre del paciente en la descripción de cada servicio facturado** | 4 | ❌ No está en `billing.py` |
| 3.6 | **Campo "factura a nombre propio / consumidor final"** por cliente, guardado en base, sin preguntarlo cada vez; con datos de la veterinaria en observaciones cuando sea consumidor final | 4 | ❌ Cero coincidencias. **Bloqueante para facturar en la cuenta real** |
| 3.7 | **Perfiles válidos para todas las especies salvo los etiquetados**, con etiqueta administrable | 8 | ❌ `catalog_profiles.species` solo admite `canino/felino/ambos` ([catalog.py:204](app/catalog.py#L204)) |
| 3.8 | **Observaciones después del análisis** | 8 | ❌ [flow.py:23](app/flow.py#L23): `observations` va antes de `exam_type` |
| 3.9 | **Guardar perfiles favoritos por clínica y reofrecerlos en el chat**, con nombre automático, modificables | **3**, 5 | ❌ Ver §5 — el chat no los guarda ni los ofrece |
| 3.10 | **Cargas masivas por CSV** de precios, clientes y portafolio | 4 | ❌ El dashboard solo **exporta** CSV |
| 3.11 | **Adjuntar soporte de pago en el chat** y verlo en la plataforma; renombrar "aclara tus pagos" a "gestión de pagos" | 2 | ❌ El bot no recibe archivos |
| 3.12 | **RUT y documentos a carpeta de Google Drive** | 2 | ❌ No existe |
| 3.13 | **Rol de mensajero** con vista limitada a sus rutas + pendientes generales | 2 | ❌ No hay roles; los estados de muestra sí existen |
| 3.14 | **Alertas por recolección pendiente durante X tiempo** | 4 | ❌ Hay alertas de cobertura y ruta sin asignar, no por tiempo |
| 3.15 | **Sincronización bidireccional plataforma ↔ Alegra** | 4 | ❌ |
| 3.16 | **Chatbot externo para dueños de mascotas** | 1, 3 | ❌ Segundo desarrollo, nunca entró al alcance |
| 3.17 | **Plan B de Anarvet: PDFs desde OneDrive** | 7 | ❌ |
| 3.18 | **Reinicio / finalizar conversación** | **4**, 7 | ❌ Pedido el 13/05, sin comando de reset |
| 3.19 | **Edición de precios desde la plataforma** | 1 | ❌ Catálogo por seed SQL |
| 3.20 | **Descuentos editables desde la plataforma** | 6 | ❌ `DISCOUNT_TIERS` en [config.py:25](app/config.py#L25) |
| 3.21 | **Reconocimiento del cliente por su teléfono** | 6, 7 | ❌ Planteado como objetivo futuro |
| 3.22 | **Estados operativos del chat** ("resuelto por llamada", "inactivo", "disponible") | 2 | ⚠️ Hay fases del agente, no estos estados |
| 3.23 | **Acta/minuta de cierre prometida a A3** entre el 29 y 30 de julio | 8 | ❓ Sin rastro. Compromiso nuestro vencido |

### 3.24 Bug confirmado en el PDF de la orden

Reportado en la llamada 8, punto 18. Está en
[service_order_print.html:102](app/templates/service_order_print.html#L102): la columna rotulada
**Valor** se rellena con `order.payment_method`. Imprime "contraentrega" donde va el precio.
Confirmado, sin corregir, y no está en la bitácora de errores.

---

## 4. Pedidos cumplidos

| Pedido | Llamada | Verificación |
|---|---|---|
| Búsqueda por NIT con y sin dígito de verificación | 2 | ✅ `_nit_candidates` ([db.py:171](app/services/db.py#L171)) |
| No repetir NIT si ya se identificó por nombre | 3 | ✅ RESUELTO-025 |
| Búsqueda por palabra clave con lista de coincidencias | **5**, 6 | ✅ Validado en vivo en la llamada 7 (caso "Planet") |
| Sedes múltiples con selección y confirmación | 3 | ✅ |
| Flujo dinámico ramificado según la base | 3 | ✅ FSM por fases |
| Orden de servicio dentro del chat, no formulario externo | 2, 3 | ✅ |
| Datos completos de la orden: médico, paciente, especie, raza, sexo, edad, propietario, exámenes | **5** | ✅ Los 11 campos en `ROUTE_REQUIRED_FIELDS` |
| Consecutivo de orden de servicio | 3 | ✅ `011_order_number_yearly` (A3-2026-001) |
| Varias órdenes por recogida | **5**, 7, 8 | ⚠️ Existe, pero sin la parte del pago (§0) |
| Barrios repetidos en varias localidades | 4 | ✅ `territorial_neighborhoods` con clave compuesta |
| Estados de muestra (pendiente, recogida, en camino, en laboratorio) | 2, 4 | ✅ `SAMPLE_STATUS_LABELS` |
| Cambio manual de motorizado en una solicitud | 1, 2, 4 | ✅ [dashboard.py:1909](app/dashboard.py#L1909) |
| Colores por etapa | 4 | ✅ `008_courier_color` |
| Panel de métricas personalizable | 4 | ⚠️ `013_dashboard_column_prefs` — columnas, no "cubos" arrastrables |
| "Crea tu perfil" — construcción en el chat con resumen y precio | 1, 3, 6 | ✅ Ver la salvedad en §5 |
| Descuento por cantidad de pruebas | 3, 6 | ✅ [rules.py:46](app/rules.py#L46) |
| Etiquetas diagnósticas y sugerencia sin recomendación médica | 6 | ✅ `012_diagnostic_labels` |
| Detalle de un perfil (qué pruebas contiene) | 3 | ✅ |
| Usuarios finales no ven precios de A3 | 1 | ✅ |
| Especie vs. raza; especies grandes | 7 | ✅ [species.py](app/species.py) — ver ❌ en catálogo de perfiles (3.7) |
| Detener el flujo si no hay cliente validado | 6 | ✅ [flujo.py:46](app/enforcers/flujo.py#L46) |
| Teléfono no arrastra a otro cliente (Puppy Export) | 6 | ✅ ERR-081 |
| La ruta se programa aunque el pago no esté validado | 2 | ✅ El registro no depende del pago |
| API de Alegra con token | 4 | ✅ Operando en cuenta demo |

### GPS

La llamada 7, punto 8, es el acta que el doc 01 pedía: fue A3 quien lo movió a mejora futura, y
Speaker G señaló que había que cerrar el proyecto base *"para no seguir agregando
indefinidamente"*. Ya en la llamada 2, punto 11, se había explicado que el GPS en tiempo real
requiere una app móvil. **Está bien cubierto.**

---

## 5. Perfiles personalizados: entregado a medias, presentado como completo

Es el caso que más conviene revisar antes de mostrarle nada a A3.

- **Llamada 3, punto 11:** Luciano aclara que *"lo pendiente es guardar el perfil y aplicar
  descuentos"*.
- **Llamada 3, punto 12:** guardarlos con nombre automático ("Perfil Clínica Animal Planet 1"),
  **mostrárselos a la clínica cuando vuelva a pedir**, permitir modificarlos, y opcionalmente
  ordenar por frecuencia de uso.
- **Llamada 5, punto 14:** *"el agente debe ofrecer perfiles personalizados existentes cuando esa
  clínica vuelva a pedir una muestra"*.

Qué hay hoy: el chat **arma** un perfil personalizado, calcula el total y aplica el descuento
(`calculate_custom_profile_total`). Pero `list_custom_profiles` y `save_custom_profile` solo se
invocan desde [dashboard.py:2056](app/dashboard.py#L2056) y `2069`. **`agent.py` no los llama
nunca.** El perfil que arma el cliente en la conversación no se guarda, y en la siguiente orden
no se le ofrece.

De las dos cosas que Luciano marcó como pendientes en la llamada 3, se hizo una: el descuento.

El documento 04 lista *"perfiles personalizados creados por clientes"* entre lo entregado.

---

## 6. No determinables

- **El mensaje de cliente nuevo con asesor** (llamada 3, punto 3): no encontré el texto en
  `messages.py`. Habría que ver el escalado en vivo antes de afirmar nada.
- **Los "diez cambios del 20 de mayo"**: la llamada 5 tiene diecisiete pedidos concretos, y no
  incluye el texto institucional ICA ni la corrección ortográfica (triage 27 y 28). Esos dos
  probablemente vinieron del correo que A3 dijo que enviaría después, que no tengo.
- **Si A3 respondió el acta prometida** en la llamada 8, punto 25.
- **Perfiles "prequirúrgico 1 / 2" y "parasitológico 3"** (llamada 7): hay fixes de matching
  (ERR-043, ERR-045, ERR-056); no verifiqué esos tres códigos contra el catálogo real.

---

## 7. Riesgo en el documento que se le muestra al cliente

[04-avance-visual-a3](Auditoria Alcance/04-avance-visual-a3.html) dice, sobre los cambios del 20
de mayo: *"Hoy están resueltos o cubiertos todos salvo la transcripción de la orden por foto"*.

Dos problemas:

1. El **pago en línea** tampoco se hizo, y A3 lo pidió en cuatro llamadas con proveedor elegido.
2. Los **perfiles personalizados** figuran como entregados, pero el chat no los guarda ni los
   reofrece (§5) — y eso se pidió en las llamadas 3 y 5.

---

## 8. Lectura de conjunto

Las ocho llamadas muestran un patrón consistente: **A3 valida la plataforma interna y concentra
sus objeciones en el chatbot.** Lo dice en la llamada 7, punto 25, y lo repite en la 8, punto 26:
*"el bloqueo principal sigue en la etapa 1"*.

Eso choca con la foto del triage, donde la Fase 1 está al 80 % y lo pendiente se concentra en
inventarios, deploy y Anarvet.

Sobre la discusión de fondo — si los cambios de la llamada 8 son retrabajo o alcance nuevo — el
material de las ocho llamadas deja una conclusión incómoda pero clara:

- El **pago después de anexar todas las órdenes** se pidió el **20 de mayo** (§0).
- El **reset de conversación** se pidió el **13 de mayo**.
- Los **perfiles favoritos guardados y reofrecidos** se pidieron el **6 de mayo** y se
  reafirmaron el 20.
- La **asignación por zona** se pidió en cuatro llamadas distintas.

Ninguno de los cuatro está hecho, y ninguno es un pedido de última hora. Esto no significa que
no haya alcance agregado — lo hay, y está en `06-agregados-al-alcance.md`. Significa que la
línea entre "lo pedido y no entregado" y "lo agregado sobre la marcha" **no cae donde el triage
la puso**, y conviene tenerlo claro antes de sentarse a negociar el cierre.
