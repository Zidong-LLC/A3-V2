# Cambios de criterio de A3 y su impacto en el plazo

**Fecha:** 2 de agosto de 2026 · **Uso interno — Laberit**
**Fuentes:** las 10 reuniones (`reuniones/`), el código y el historial del repositorio

Qué pidió A3, cuándo, cómo lo formuló, y en qué reunión posterior cambió de criterio obligando a
rehacer lo construido.

---

## 1. Cómo leer esto

La calidad de la fuente **no es la misma en todas las reuniones**:

| Reuniones | Fuente | Qué permite |
|---|---|---|
| **00a (07/04) y 00b (08/04)** | **Transcripción literal** (Fathom) | Cita palabra por palabra, con nombre y apellido de quien habló |
| 1 a 4 (16/04 – 13/05) | Resumen en checklist | Los hablantes son *Speaker A/B/C/D/E*; solo consta que Speaker B parece ser Luciano. **Atribución individual no certera** |
| 5 a 8 (20/05 – 28/07) | Resumen en checklist | Nombres reales (Luciano, Jorge, Sergio, Adriana, Guzmery) mezclados con "A3" genérico |

En las reuniones 1 a 8, las frases entre comillas son **la formulación del resumen**, no cita
textual del audio. Solo 00a y 00b sostienen una cita literal.

La marca **`[T]`** señala los puntos donde la cita textual cambiaría el peso del argumento. Están
listados en §6.

Las fechas de construcción salen del historial de git y son verificables.

---

## 2. Los diez cambios de criterio

### Caso 1 · Perfiles restringidos por especie 🔴

| | |
|---|---|
| **Origen** | **29/04** — se carga el catálogo de A3. `catalog_profiles.species` admite `canino / felino / ambos` porque **así viene nombrado el portafolio del cliente**: "Perfil Hepático Canino III", "Perfil Felino II", "Perfil Cachorros VIII". De los 133 perfiles, **39 quedan canino, 34 felino y 60 ambos**. |
| **Ratificación** | **06/05, llamada 3, punto 11** — Speaker/desarrollo muestra la lógica de perfil personalizado y A3 confirma el requisito: *"El usuario debe poder elegir canino/felino"*. A3 valida que va en la dirección correcta. **`[T]`** |
| **Qué se construyó** | Filtro por especie en la resolución de catálogo ([catalog.py:204](app/catalog.py#L204)) y el paso **B7 del contrato de flujo** — *"lista perfiles de la especie con código y precio"* — aprobado el 22/06. |
| **Primer choque** | **07/07, llamada 7, punto 20** — A3 informa que **también trabajan con especies grandes**: equinos, bovinos, porcinos, caprinos, además de aves, conejos, roedores y silvestres. El modelo canino/felino queda corto. |
| **Reversión** | **28/07, llamada 8, puntos 6 y 7** — con el perfil 653, que en la base figura como *"perfil senior canino 3"*, A3 intenta usarlo en un felino. Ante el bloqueo, plantea la regla inversa: *"las pruebas/perfiles aplican para todas las especies por defecto"*, y solo se restringe lo que diga explícitamente canina, felina, equina. Pide además que la etiqueta se administre desde la plataforma. |
| **Qué hay que rehacer** | El campo `species` de `catalog_profiles`, el filtro de `catalog.py`, la reclasificación de los 73 perfiles hoy restringidos, el paso B7 aprobado, y una pantalla nueva de etiquetado en la plataforma. |
| **Impacto** | **Tres meses** entre la carga del catálogo y la reversión. El agravante: **la restricción reproduce el nombre que A3 le puso a sus propios perfiles**. Nadie inventó que el 653 fuera canino. |

### Caso 2 · Criterio de descuento: por perfil → por cantidad 🔴

| | |
|---|---|
| **Pedido inicial** | **16/04, llamada 1, punto 12** — Speaker C plantea "Crea tu perfil" y A3 pide que *"una vez armado el perfil, se aplique un tipo de descuento para facturarlo"*. El descuento se asocia **al perfil**. |
| **Bloqueo** | **06/05, llamada 3, punto 8** — *"Los descuentos todavía no están cargados. A3 debe enviar la información."* **20/05, llamada 5, punto 14** — siguen faltando; A3 se compromete a enviarlos *"durante la semana o comienzos de la siguiente"*. |
| **Cambio de criterio** | **27/05, llamada 6, punto 12** — A3 cambia el modelo: los descuentos van **por cantidad de pruebas, no por tipo de perfil**. Tabla nueva: 2 pruebas → 10 %, 3 → 12 %, 4 → 14 %, 5 → 16 %. Explícitamente: *"sin separar por hematología, minerales, químicas, hormonas, pruebas especiales"*. **`[T]`** |
| **Qué se construyó** | `DISCOUNT_TIERS` por tramos de cantidad ([config.py:25](app/config.py#L25)) y `calculate_discount` ([rules.py:46](app/rules.py#L46)), **el 08/06** — después del cambio. |
| **Impacto** | **Seis semanas** de indefinición (16/04 → 27/05). La información que A3 debía enviar para el modelo original nunca llegó en ese formato: llegó recién cuando el criterio ya había cambiado. |

### Caso 3 · Perfiles como producto → pruebas sueltas con etiquetas 🔴

| | |
|---|---|
| **Origen** | **08/04, reunión 00b — transcripción literal.** Adriana enuncia la funcionalidad por primera vez: *"cuando tengamos todo esto que queremos crear —ya se ha creado acá internamente en el papel— es una nueva opción que se va a llamar **Crea tu propio perfil**, pero creo que lo podemos definir cuando ya se vea la generalidad de los otros, para poderte explicar los puntos claves de cómo formar ese nuevo perfil"*. Queda enunciada y sin definir. |
| **Pedido inicial** | **06/05, llamada 3, puntos 11 y 12** — perfiles personalizados guardados por clínica, con nombre automático ("Perfil Clínica Animal Planet 1"), reutilizables y modificables. Speaker C valida la idea y pide *"que se alimente como una base/caché"*. Ratificado el **20/05, llamada 5, punto 14**. |
| **Qué se construyó** | `client_custom_profiles` y `diagnostic_label_tests`, **el 08/06**. |
| **Cambio de criterio** | **27/05, llamada 6, punto 17** — A3 quiere *"dejar de manejar perfiles como unidad rígida de producto"* y pasar a pruebas individuales con etiquetas y descuento por cantidad. Motivo declarado: reportes, inventarios y reactivos. |
| **Advertencia registrada** | **27/05, punto 15** — Luciano advierte que *"esta lógica puede alargar el desarrollo"* porque exige una estructura nueva de pruebas, perfiles, etiquetas y sugerencias. A3 responde que *"no es un desarrollo nuevo, sino una evolución"* y que la información *"ya está en la lista de precios"*. **El punto quedó abierto.** **`[T]`** |
| **Vuelta atrás parcial** | **28/07, llamada 8, punto 5** — A3 reconoce que los clientes **siguen pidiendo perfiles cerrados**: *"perfil X y cámbiame esto por esto"*. La migración a pruebas sueltas no ocurrió en la operación real. |
| **Impacto** | Dos modelos conviviendo: perfiles de catálogo y perfil personalizado, cada uno con su cálculo de total. La advertencia sobre el plazo está documentada y A3 la desestimó. **La funcionalidad se enunció el 8 de abril y su definición se pospuso hasta el 27 de mayo — siete semanas de indefinición pedidas por A3.** |

### Caso 4 · Los campos de la orden crecieron sobre la marcha 🟠

| | |
|---|---|
| **Pedido inicial** | **22/04, llamada 2, punto 15** — Speaker C ejemplifica la orden con el paciente Coco: nombre del paciente, especie, edad, propietario, exámenes enviados y valor. **Seis campos.** |
| **Cambio** | **20/05, llamada 5, punto 4** — *"El bot está pidiendo muy poca información. Actualmente solo pide nombre y exámenes, pero eso no alcanza."* Se agregan **médico remitente, raza y sexo**, y A3 aclara que *"no son opcionales"*. Queda en enviar el listado por correo. |
| **Impacto** | **Cuatro semanas.** Rehace el paso de recolección: cada campo nuevo es una pregunta, una validación y un lugar en el resumen. Hoy son once campos. |

### Caso 5 · Cliente nuevo: contradicción dentro de la misma llamada 🟠

| | |
|---|---|
| **Instrucción A** | **22/04, llamada 2, punto 8** — *"Una vez derivado, el proceso del bot se cierra para ese caso."* Speaker A resume que **el bot solo deriva y no hace ninguna otra gestión**. |
| **Instrucción B** | **22/04, llamada 2, punto 10** — mismo día: *"El formulario para cliente nuevo puede hacerse dentro del agente conversacional"*, con el RUT y los documentos subidos a una carpeta de Google Drive y validación humana posterior. |
| **Antecedente** | **16/04, llamada 1, punto 14** — flujo aún más amplio: consultar primero en Alegra, preregistro con datos de facturación, aviso al contador. |
| **Impacto** | Las dos instrucciones son incompatibles y llegaron en la misma reunión. Se implementó la A (escalar y cerrar). La B nunca se construyó y sigue figurando como pendiente. **Conviene resolverla antes del cierre, no después.** |

### Caso 6 · Dónde se pregunta la forma de pago 🔴

| | |
|---|---|
| **Formulación inicial** | **22/04, llamada 2, punto 15** — *"Al finalizar la orden, debe aparecer opción de pago."* Leído literalmente: el pago pertenece a la orden. |
| **Formulación posterior** | **20/05, llamada 5, punto 6** — la secuencia cambia: *"Después de completar una orden, el bot debe preguntar si quiere anexar otra orden o continuar. **Si el usuario elige continuar, pasa a forma de pago.**"* A3 aclara que una veterinaria puede enviar **diez órdenes en una sola recogida**. |
| **Reclamo final** | **28/07, llamada 8, puntos 11 y 12** — explícito: la forma de pago **no va dentro de cada orden** ni en el resumen de la orden; va al cierre del pedido completo. |
| **Estado** | ❌ Hoy `payment_method` es campo obligatorio de cada orden ([flow.py:28](app/flow.py#L28)). |
| **Nota — leer antes de usar este caso** | **La formulación del 20/05 es correcta y sigue sin cumplirse.** Sirve para mostrar que la instrucción del 22/04 era ambigua y que el criterio se precisó recién un mes después, pero **no sirve como argumento de sobrecosto**: A3 tiene el pedido del 20/05 a su favor. En la llamada 8, punto 15, A3 sostuvo que *"no es un cambio de negocio, sino una lógica que recién se ve al llegar a la prueba completa"* — y en este punto la documentación lo respalda. |

### Caso 7 · Asignación de mensajero: automática o de recepción 🟠

| | |
|---|---|
| **Pedido inicial** | **16/04, llamada 1, punto 6** — Speaker B confirma que *"la IA asigne mensajero automáticamente según clasificación de zonas"*. |
| **Señal contraria** | **22/04, llamada 2, punto 11** — *"Recepción debe mantener control de rutas… actualmente la asignación se hace en recepción y eso no cambiaría completamente."* |
| **Señal mixta** | **22/04, mismo día, punto 13** — *"Debe existir autoasignación por zona"*, pero recepción confirma o cambia **antes** de notificar al mensajero. |
| **Ratificación** | **13/05, llamada 4, punto 6** y **20/05, llamada 5, punto 12** — las zonas se asignarán automáticamente y el cambio de zona *"se reflejará en el agente conversacional"*. |
| **Qué se construyó** | `territorial_zones` **el 20/05**: 8 zonas, 1.649 barrios, cobertura por motorizado. A3 lo validó en la llamada 5 (*"les gusta mucho el mapa"*). |
| **Estado** | La zonificación existe y **no decide la orden**: el motorizado sale de `client_courier_assignment`, fijo por clínica ([db.py:1226](app/services/db.py#L1226)). |
| **Impacto** | Se construyó la zonificación completa y la operación sigue asignando por clínica. **Cuál de los dos criterios gana nunca se cerró.** |

### Caso 8 · GPS: dos meses y medio de tema abierto 🟡

- **22/04, llamada 2, punto 11** — Speaker D pregunta si se puede asignar el mensajero más cercano por GPS. Luciano explica que la geolocalización en tiempo real **requiere una aplicación móvil**.
- **13/05, llamada 4, punto 8** — vuelve: *"si GPS no es viable por ahora, debe quedar opción manual desde recepción"*.
- **07/07, llamada 7, punto 8** — A3 lo replantea con ubicación de Google. Speaker G pregunta si estaba en el alcance inicial y señala que hay que cerrar el proyecto base *"para no seguir agregando indefinidamente nuevas cosas"*. **Se retira de común acuerdo.**
- **Impacto:** dos meses y medio de tema recurrente que terminó descartado. **Ventaja nuestra:** la llamada 7 es el acta que el documento 01 pedía para sacarlo del alcance sin riesgo.

### Caso 9 · Foto de la orden con OCR: consultado y nunca decidido 🟡

- **20/05, llamada 5, punto 5** — A3 pregunta si el cliente podría enviar una foto de la orden para que la IA la lea. Desarrollo confirma que técnicamente se puede, con la advertencia de que depende de que la foto sea clara y la letra legible. El punto cierra: *"Pendiente: decidir si esta opción se agrega como alternativa o si se mantiene solo carga manual por chat."*
- **Nunca se decidió.**
- **28/07, llamada 8, punto 3** — en la prueba real, la orden fotografiada **no se entendía** y A3 tuvo que dictarla: *"lo dictarán porque así llega normalmente del cliente"*.
- **Ventaja nuestra:** nunca fue un compromiso, y la propia prueba de A3 demostró el problema. Retirarlo del alcance está respaldado por acta.

### Caso 10 · La validación exigida creció 🟠

- **27/05, llamada 6, puntos 3 y 4** — A3 pide que el bot no avance si el doctor, la veterinaria o el cliente no están verificados en base.
- **07/07, llamada 7, punto 22** — el requisito sube: el médico debe quedar con **nombre completo, apellido, identificación y tarjeta profesional**, y hay que confirmar que *"ese médico está autorizado para solicitar órdenes por esa clínica"*.
- **Dependencia:** A3 debía enviar la base de médicos y tarjetas el **10/07**.
- **Impacto:** el requisito pasó de "no avanzar sin cliente" a un modelo de autorización médico↔clínica que necesita datos que llegaron incompletos.

---

## 3. Entregas de A3 comprometidas y no cumplidas

| Comprometido | Cuándo se pidió | Qué pasó |
|---|---|---|
| Definición formal de zonas y portafolio actualizado | 16/04, llamada 1 | El archivo de rutas aparece recién en la **llamada 4 (13/05)** — casi un mes |
| Información de descuentos | 06/05, llamada 3 | Seguía faltando el **20/05** y el **27/05**; llegó junto con el cambio de criterio |
| Esquema ordenado de "Crea tu perfil" | 27/05, llamada 6 | **Sin constancia de entrega** |
| Médicos, clínicas, tarjetas profesionales, especies, razas y clientes nuevos | 07/07, llamada 7 — comprometido para el **viernes 10/07** | Las razas se cargaron el **21/07**. El **28/07** los clientes seguían sin dirección, sin NIT y sin motorizado (llamada 8, punto 19) |
| Base de clientes utilizable | 13/05, llamada 4 | El **28/07** hubo que **retirar el listado con datos incompletos para evitar errores** (llamada 8, punto 2) |
| Respuesta de Anarvet | Carta enviada el **20/05** | Sin respuesta el 27/05 y el 07/07. Camino técnico recién el **28/07**: SQL de solo consulta. **Más de dos meses** |
| Credenciales, sandboxes y documentación de API | Plan de trabajo firmado — **día 4, viernes 30/01** | Nunca llegaron |
| Accesos de QA y producción | Plan de trabajo firmado — **día 25, lunes 02/03** | Nunca llegaron |

El cronograma acordado en la llamada 7 era explícito: A3 enviaba el **10/07**, el equipo trabajaba
la semana siguiente y la prueba quedaba para el **21-22/07**. La entrega incompleta corrió esa
fecha, y la prueba de inicio a fin del **28/07** tampoco pudo cerrarse.

---

## 4. Impacto en el plazo

| Caso | Semanas entre pedido y cambio | Qué quedó afectado |
|---|---|---|
| 1 · Perfiles por especie | **13 semanas** (29/04 → 28/07) | `catalog_profiles`, filtro de catálogo, paso B7 aprobado, 73 perfiles a reclasificar, pantalla de etiquetado nueva |
| 2 · Criterio de descuento | **6 semanas** (16/04 → 27/05) | Modelo de descuento completo |
| 3 · Perfiles como producto | **3 semanas** (06/05 → 27/05) | Dos modelos conviviendo; migración a pruebas sueltas nunca ocurrió en la operación |
| 4 · Campos de la orden | **4 semanas** (22/04 → 20/05) | Paso de recolección, de 6 a 11 campos |
| 5 · Cliente nuevo | Mismo día | Instrucción B nunca construida |
| 6 · Ubicación del pago | 4 semanas (22/04 → 20/05) | *Ver la nota del caso 6 antes de usarlo* |
| 7 · Asignación por zona | **Sin cerrar desde el 16/04** | Zonificación construida y sin uso en la orden |
| 8 · GPS | **11 semanas** hasta descartarlo | Tiempo de reunión; sin código perdido |
| 9 · OCR | **10 semanas** sin decisión | Sin código perdido |
| 10 · Validación de médicos | 6 semanas (27/05 → 07/07) | Modelo de autorización médico↔clínica, con datos incompletos |

**Lectura:** los casos 1, 2, 3 y 4 son los que efectivamente hicieron rehacer trabajo. Los casos 8
y 9 no costaron código: costaron reuniones. El caso 7 nunca se resolvió y explica por qué hay una
zonificación completa que no se usa.

---

## 5. Qué puede responder A3

Anticipar esto vale más que ignorarlo. Tres puntos donde el reclamo tiene base:

1. **El pago al final del pedido** se pidió el **20/05** y sigue sin hacerse. Es el caso 6 y
   está señalado ahí mismo. Si se presenta como cambio de alcance, A3 saca la llamada 5.
2. **Los perfiles favoritos guardados por clínica** se pidieron el **06/05**, se ratificaron el
   **20/05**, y el chat todavía no los guarda ni los reofrece.
3. **El reinicio de conversación** se pidió el **13/05** y se repitió el 07/07.

Ninguno de los tres entra en la lista de §2 porque no son cambios de criterio de A3: son pedidos
suyos que siguen pendientes. Conviene tenerlos resueltos —o al menos reconocidos— antes de abrir
la discusión de los diez casos.

---

## 6. Puntos a confirmar con transcripción

Estos son los `[T]`. En todos, la cita textual cambiaría el peso del argumento. **Con las
transcripciones de abril quedaron cinco pendientes, no siete.**

| # | Qué confirmar | Reunión |
|---|---|---|
| 1 | Quién dijo exactamente *"elegir canino/felino"* y en qué términos — si fue requisito o descripción de lo que veían en pantalla | 3 (06/05) |
| 2 | La formulación completa del cambio a descuento por cantidad y si se mencionó que reemplazaba el criterio anterior | 6 (27/05) |
| 3 | El intercambio completo sobre "evolución vs. desarrollo nuevo", incluida la advertencia de Luciano sobre el plazo | 6 (27/05), punto 15 |
| 4 | La frase exacta del 22/04 sobre la opción de pago al finalizar la orden | 2 (22/04), punto 15 |
| 5 | Quién es Speaker G, que planteó cerrar el proyecto base — su rol da peso al acta del GPS | 7 (07/07), punto 8 |

### Resueltos con las transcripciones de abril

- **El alta de cliente nuevo** (antes punto 5 de esta lista): la reunión 00b del 08/04 resuelve la
  contradicción aparente de la llamada 2. Adriana define el circuito completo —documento según
  tipo de cliente, aprobación humana, primera venta asistida— y su formulación es literal:
  *"Estamos en Colombia, se pueden falsificar documentos"*. No hay ambigüedad que confirmar.
- **El retrabajo y alcance de la llamada 8** (antes punto 7): sigue siendo útil tenerlo, pero el
  antecedente que lo enmarca —el pedido del 20/05— ya está documentado en §5.

---

**Documento interno.** La versión presentable a A3 es `09-acta-cambios-de-criterio.md`: mismos
hechos y fechas, sin atribución ni estimación de impacto.
