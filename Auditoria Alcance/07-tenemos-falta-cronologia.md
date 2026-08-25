# A3 — Lo que tenemos, lo que falta y la cronología

**Fecha:** 2 de agosto de 2026
**Fuentes:** las 8 llamadas (`reuniones/`), `00-decisiones-triage.md` y verificación contra el código

Tres listas: qué está entregado, qué falta, y qué se pidió en cada llamada.

---

# 1 · LO QUE YA TENEMOS

Verificado en código. **15.282 líneas** en `app/`, **58 archivos de prueba** con **450 funciones
de test**.

## 1.1 Agente conversacional

| Componente | Detalle |
|---|---|
| Identificación de clínica | Por NIT (con y sin dígito de verificación) o por nombre, tolerando tipeos |
| Búsqueda por palabra clave | Lista de coincidencias numeradas; no elige la primera por su cuenta |
| Sedes múltiples | Selección y confirmación explícita de la sede |
| Flujo dinámico | Ramifica según lo que devuelve la base, no un camino único |
| Orden de servicio en el chat | Los 11 campos, paso a paso, sin formulario externo |
| Catálogo real | 133 perfiles, 159 análisis, 323 razas, con precios |
| Especies | Canino, felino, bovino, equino, porcino, caprino, aves, roedores, silvestres |
| Especie vs. raza | "Toro" → Bovino/Macho; "persa" y "San Bernardo" no pasan como especie |
| Descuentos por volumen | Tramos por cantidad de pruebas, con exclusión de convenio |
| Etiquetas diagnósticas | Sugiere pruebas de un perfil clínico sin dar recomendación médica |
| Perfil personalizado | Se arma en el chat, con resumen y precio ⚠️ *no se guarda — ver 2.3* |
| Multi-orden | Varias órdenes para el mismo cliente ⚠️ *sin el pago agrupado — ver 2.1* |
| Corte 17:30 | Siguiente día hábil |
| Derivaciones | Cliente nuevo → recepción · Pagos → contabilidad · Particulares → veterinario |
| Bloqueo sin cliente validado | No avanza la orden sin clínica identificada |
| Canales | Telegram y Chatwoot |

## 1.2 Plataforma interna (dashboard)

| Componente | Detalle |
|---|---|
| Solicitudes | Listado, detalle, filtros, asignadas y sin asignar |
| Operaciones | Qué hay que hacer, a quién está asignado, detalle capturado por el bot |
| Clientes | 992 cargados, alta de cliente nuevo, asignación de motorizado |
| Motorizados y mapa | Zonas, cobertura, colores, cambio manual de motorizado por solicitud |
| Zonificación de Bogotá | 8 zonas, 1.649 barrios, con barrios repetidos por localidad resueltos |
| Muestras | Estados: pendiente, recogida, en camino, recibida, en laboratorio |
| Catálogo | Perfiles, análisis y perfiles personalizados por clínica |
| Facturación | Listado con cache local, enlace a Alegra, exportación a CSV/Excel |
| Métricas | Indicadores operativos y de negocio, con preferencias de columnas |
| Consecutivo de orden | `A3-2026-001`, reinicia por año |
| PDF de la orden | Plantilla imprimible ⚠️ *con el bug del campo Valor — ver 2.4* |

## 1.3 Portal del cliente

| Componente | Detalle |
|---|---|
| Solicitud en línea | Con catálogo completo y precio, igual que por chat |
| Detalle e historial | Avance paso a paso de cada solicitud |
| Resultados 24/7 | Búsqueda, descarga individual y descarga masiva |
| Notificaciones | Bandeja del portal y aviso de resultado publicado |
| Filtros | En resultados y en el listado de solicitudes |

## 1.4 Facturación

| Componente | Detalle |
|---|---|
| Alegra | Borrador generado desde la orden, operando en cuenta demo |
| Líneas de factura | Perfil base, análisis agregados y descuento por volumen como porcentaje |
| Registro de fallos | Una orden no puede quedar sin facturar en silencio (ERR-100) |
| Contactos | Manejo de NIT con dígito de verificación, sin duplicados |

## 1.5 Infraestructura

| Componente | Detalle |
|---|---|
| Health check real | Verifica dependencias, no responde "ok" fijo (ERR-101) |
| API interna | Cerrada por token, fail-closed (ERR-098) |
| Migraciones | 17 aplicadas |
| Suite de pruebas | 450 tests en verde |

---

# 2 · LO QUE FALTA

Unifica lo pendiente del triage y lo pedido en las llamadas. Ordenado por urgencia real.

## 2.1 🔴 Bloqueantes para cerrar el flujo con A3

| # | Qué | Origen | Por qué bloquea |
|---|---|---|---|
| 1 | **Forma de pago al final del pedido**, tras anexar todas las órdenes | Llamada 5 (20/05) y 8 | Pedido hace 2 meses y medio. Es lo que impide cerrar la prueba de inicio a fin |
| 2 | **Jerarquía pedido → órdenes → análisis** | Llamada 8 | Sin entidad "pedido" no hay dónde colgar el pago ni la factura agrupada |
| 3 | **Una factura por pedido**, no por orden | Llamada 8 | Hoy `invoices_cache` es una factura por `request` |
| 4 | **Campo consumidor final vs. nombre propio** por cliente | Llamada 4 (13/05) | **Sin esto no se puede pasar Alegra a la cuenta real**: las facturas saldrían mal emitidas |
| 5 | **Resumen de orden sin forma de pago** | Llamada 8 | Consecuencia de 1 y 2 |

## 2.2 🔴 Rediseños de flujo pedidos y no hechos

| # | Qué | Origen |
|---|---|---|
| 6 | **Observaciones después del análisis**, no antes | Llamada 8 |
| 7 | **Bloquear el cambio de cliente maestro** (cierra ERR-099 por la vía que A3 eligió) | Llamada 7 |
| 8 | **Perfiles válidos para todas las especies** salvo los etiquetados, con etiqueta administrable desde la plataforma | Llamada 8 |
| 9 | **Guardar perfiles favoritos por clínica y reofrecerlos en el chat** | Llamada 3 (06/05) y 5 |
| 10 | **Asignación automática de motorizado por zona** | Llamadas 1, 2, 4 y 5 |
| 11 | **Reiniciar / finalizar conversación** | Llamada 4 (13/05) y 7 |

## 2.3 🟠 Módulos nuevos pendientes

| # | Qué | Origen |
|---|---|---|
| 12 | **Calendario de mensajeros** — compensatorios, permisos, vacaciones | Llamada 1 |
| 13 | **Cargas masivas por CSV** de precios, clientes y portafolio | Llamada 4 |
| 14 | **Adjuntar soporte de pago en el chat** + "gestión de pagos" | Llamada 2 |
| 15 | **RUT y documentos a Google Drive** con validación humana | Llamada 2 |
| 16 | **Rol de mensajero** con vista limitada a sus rutas | Llamada 2 |
| 17 | **Alertas por recolección pendiente durante X tiempo** | Llamada 4 |
| 18 | **Nombre del paciente en la descripción de cada servicio facturado** | Llamada 4 |
| 19 | **Sincronización bidireccional plataforma ↔ Alegra** | Llamada 4 |
| 20 | **Edición de precios desde la plataforma** | Llamada 1 |
| 21 | **Descuentos editables desde la plataforma** | Llamada 6 |
| 22 | **Pago en línea con pasarela** (Wompi/Bancolombia) | Llamadas 2, 5, 6, 8 |
| 23 | **Control de inventarios sobre Alegra** (sustituto de DelSol) | Triage ítem 11 — *el más pesado del triage* |
| 24 | **Chatbot externo para dueños de mascotas** | Llamadas 1 y 3 — *segundo desarrollo completo* |

## 2.4 🟡 Refinamientos

| # | Qué | Origen |
|---|---|---|
| 25 | **PDF de la orden**: la columna "Valor" imprime la forma de pago | Llamada 8 — bug confirmado |
| 26 | **Formato de precios**: `$18,000 COP` → `$18.000` | Llamada 7 |
| 27 | **Validación de médico** con nombre completo y tarjeta profesional que bloquee | Llamadas 6 y 7 |
| 28 | **PQR por link** | Llamada 2 |
| 29 | **Mensaje explícito de "te asignaremos un asesor"** | Llamada 3 — *verificar antes, puede estar* |
| 30 | **Estados operativos del chat** ("resuelto por llamada", "inactivo") | Llamada 2 |
| 31 | **Panel de métricas con bloques configurables** | Llamada 4 — hoy son preferencias de columnas |
| 32 | **Perfiles "prequirúrgico 1/2" y "parasitológico 3"** | Llamada 7 — *verificar contra el catálogo real* |
| 33 | **Tendencias y TAT en el dashboard** | Triage ítem 24 |
| 34 | **Consulta de resultados por chat** | Triage ítem 6 |
| 35 | **Aviso automático al motorizado** | Triage ítem 3 |
| 36 | **Escalado a operaciones** (hoy falla en silencio) | Triage ítem 2 |

## 2.5 ⛔ Bloqueado por A3

| # | Qué | Falta que entregue A3 |
|---|---|---|
| 37 | **Integración Anarvet** | Los parámetros de la conexión SQL. Ya no es "sin respuesta": el 28/07 ofrecieron acceso de solo consulta. **Cambia el diseño** — habría que generar nosotros el PDF de resultados |
| 38 | **Canal WhatsApp** | Cuenta Business. Además hay dos ajustes nuestros: el CHECK de `requests.entry_channel` solo admite Telegram, y el aviso de resultados llama a Telegram directo |
| 39 | **Cuenta real de Alegra** | Credenciales de producción, IVA por análisis y régimen por cliente |
| 40 | **Datos de clientes** | Dirección, NIT y motorizado faltan en parte de los 992 |
| 41 | **Deploy a producción** | Confirmación del ambiente. Arrastra el webhook de Chatwoot sin firma, `POST /setup-webhook` sin auth y `PORTAL_DEMO_MODE` |

## 2.6 Compromiso nuestro vencido

| # | Qué |
|---|---|
| 42 | **Acta/minuta de cierre prometida a A3** entre el 29 y 30 de julio (llamada 8, punto 25). Sin rastro |

---

# 3 · CRONOLOGÍA POR LLAMADA

## Llamada 1 — 16 de abril

*Alcance, fases y estructura del proyecto.*

| Pedido | Estado |
|---|---|
| Separar chatbot interno A3 del externo; priorizar el interno | ✅ |
| Chatbot externo para dueños de mascotas, como etapa posterior | ❌ Nunca entró al alcance |
| Flujo cliente nuevo vs. existente | ✅ |
| **Asignación automática de motorizado por zona** | ❌ Construida la zonificación, no se usa para asignar |
| Cambio manual de motorizado en casos excepcionales | ✅ |
| **Calendario de mensajeros** | ❌ No existe |
| Plataforma centralizada: clientes sin asignar, rutas, pedidos | ✅ |
| Orden de servicio en la plataforma, conectada a Alegra | ✅ |
| **Espacio para actualizar precios** | ❌ |
| "Crea tu perfil" con descuento | ⚠️ Se arma y cobra, no se guarda |
| Usuarios finales no ven precios de A3 | ✅ |
| Preregistro de cliente nuevo con consulta previa a Alegra y aviso al contador | ⚠️ Escala a recepción, sin documentos |
| Prefactura/factura desde la plataforma | ✅ Borrador en Alegra |

## Llamada 2 — 22 de abril

*Visibilidad de recepción, pagos y roles.*

| Pedido | Estado |
|---|---|
| Cliente nuevo derivado directo a atención al cliente | ✅ |
| **NIT con y sin dígito de verificación** | ✅ |
| No repetir preguntas ya respondidas | ✅ |
| La ruta se programa aunque el pago no esté validado | ✅ |
| **"Gestión de pagos" + adjuntar soporte en el chat** | ❌ El bot no recibe archivos |
| **RUT a carpeta de Google Drive** | ❌ |
| **PQR por link** | ❌ |
| **Rol de mensajero con vista limitada** | ❌ |
| Check de muestra recogida y estados | ✅ |
| Visibilidad admin sobre conversaciones derivadas | ⚠️ |
| **Estados operativos del chat** ("resuelto por llamada") | ⚠️ |
| Autoasignación por zona con confirmación de recepción | ❌ |
| GPS requiere app móvil — se descarta | ✅ Acta |
| El bot no genera el link de pago; redirige a plataforma segura | ❌ Sin pasarela |

## Llamada 3 — 6 de mayo

*Flujo dinámico y perfiles favoritos.*

| Pedido | Estado |
|---|---|
| Mensaje explícito de "te asignaremos un asesor" | ❓ No lo encontré |
| No volver a pedir NIT si ya se identificó por nombre | ✅ |
| Sedes múltiples con lista y confirmación | ✅ |
| Nombres similares con lista de coincidencias | ✅ |
| **Flujo dinámico ramificado, no lineal** | ✅ |
| Orden de servicio dentro del chat, no formulario | ✅ |
| Búsqueda de exámenes por palabra clave | ✅ |
| Mostrar qué pruebas contiene un perfil | ✅ |
| **Guardar perfiles favoritos por clínica y reofrecerlos** | ❌ Solo en el dashboard |
| Perfiles más usados por veterinaria | ❌ |
| Descuentos | ✅ |
| **Consecutivo de orden de servicio** | ✅ |

## Llamada 4 — 13 de mayo

*Plataforma, cargas masivas e integraciones.*

| Pedido | Estado |
|---|---|
| Corregir URL vieja de base de datos | ✅ |
| Integrar archivo de rutas/zonas | ✅ |
| **Barrios repetidos por localidad** | ✅ |
| **Cargas masivas CSV** de precios, clientes y portafolio | ❌ Solo exportación |
| Sincronizar catálogo con el agente en tiempo real | ✅ |
| **Sincronización bidireccional con Alegra** | ❌ |
| **Alertas por recolección pendiente X tiempo** | ❌ |
| Reasignar mensajero desde recepción + notificar al nuevo | ⚠️ Reasigna; falta el aviso |
| **Colores por etapa** | ✅ |
| Panel de métricas personalizable | ⚠️ Columnas, no bloques |
| **Campo consumidor final vs. nombre propio** | ❌ **Bloqueante para Alegra real** |
| **Nombre del paciente en la descripción de cada servicio** | ❌ |
| **Reiniciar / finalizar conversación** | ❌ |
| API de Alegra con token | ✅ |
| ANAR: acceso solo de lectura, documento formal | ⛔ |

## Llamada 5 — 20 de mayo · *la del cierre de etapa 1*

| Pedido | Estado |
|---|---|
| **Búsqueda por palabra clave** ("Venecia" → Consultorio Veterinario Venecia) | ✅ |
| Tono más amable y colombiano | ✅ |
| **Datos completos de la orden**: médico, paciente, especie, raza, sexo, edad, propietario, exámenes | ✅ |
| **Foto de la orden con OCR** | ➖ **Quedó como decisión abierta, nunca fue compromiso** |
| **Varias órdenes por recogida** | ✅ |
| **Al terminar una orden, preguntar si anexa otra o continúa → y ahí pasar a forma de pago** | ❌ **El pago sigue dentro de cada orden** |
| Formas de pago: contraentrega o pago en línea | ⚠️ La opción existe, sin pasarela |
| Consulta de resultados → fase posterior | ⛔ |
| Mapa de motorizados, validado por A3 | ✅ |
| Cambiar motorizado de zona y que se refleje en el agente | ❌ |
| **Guardar perfil personalizado por clínica y reofrecerlo** | ❌ |
| Carta técnica para Anarbet | ✅ Enviada |

## Llamada 6 — 27 de mayo

*Validaciones y "Crea tu perfil".*

| Pedido | Estado |
|---|---|
| Un teléfono cualquiera no debe permitir avanzar | ✅ |
| Detener el flujo sin cliente/clínica validada | ✅ |
| Caso Puppy Export: el teléfono no debe cambiar el cliente | ✅ ERR-081 |
| Búsqueda por palabra clave con lista; no elegir la primera | ✅ |
| Reconocimiento del cliente por teléfono | ❌ Planteado como futuro |
| **Descuentos por cantidad de pruebas** | ✅ |
| **Porcentajes editables desde la plataforma** | ❌ Viven en código |
| **Etiquetas diagnósticas + sugerencia de pruebas** | ✅ |
| Sin recomendación médica | ✅ |
| Alegra: factura, pago en línea, cartera | ⚠️ Factura sí; pago y cartera no |

## Llamada 7 — 7 de julio

*Demo completa y primera prueba guiada.*

| Pedido | Estado |
|---|---|
| **No permitir cambiar el cliente maestro** | ❌ ERR-099 abierto |
| Cambiar dirección y análisis | ✅ |
| Varias órdenes para el mismo cliente | ✅ |
| **Especie vs. raza; especies grandes** | ✅ |
| Razas por especie | ✅ 323 |
| **Validar médico con nombre completo y tarjeta profesional** | ⚠️ Sin validación que bloquee |
| **Formato "18K" → "18.000"** | ⚠️ Quedó `$18,000 COP` |
| Perfiles prequirúrgico 1/2, parasitológico 3 | ❓ Sin verificar |
| Reiniciar conversación para pruebas limpias | ❌ |
| **GPS como mejora futura, no bloqueo** | ✅ **Acta** |
| Plan B de Anarvet: PDFs desde OneDrive | ❌ |
| Prueba de inicio a fin | ⚠️ Sin cerrar |

## Llamada 8 — 28 de julio · *la última*

| Pedido | Estado |
|---|---|
| **Jerarquía pedido → órdenes → análisis** | ❌ |
| **Forma de pago al cierre del pedido** | ❌ *(ya pedido el 20/05)* |
| **Una factura por pedido** | ❌ |
| **Resumen de orden sin forma de pago** | ❌ |
| "Otra orden" vs. "otro análisis" | ⚠️ |
| **Observaciones después del análisis** | ❌ |
| **Perfiles para todas las especies salvo etiquetados** | ❌ |
| Etiqueta de especie administrable | ❌ |
| **PDF: donde imprime la forma de pago debe ir el valor** | ❌ Bug confirmado |
| Ordenar base de clientes (dirección, NIT, motorizado) | ⛔ Pendiente de A3 |
| Alegra con credenciales reales | ⛔ |
| **Anarbet daría acceso SQL de solo consulta** | ⛔ Cambia el diseño |
| Generar el PDF de resultados desde la plataforma | ❌ Trabajo nuevo |
| Wompi/Bancolombia para pago en línea | ❌ |
| **Acta/minuta de cierre** | ❌ **Compromiso nuestro vencido** |

---

# Resumen numérico

| | Cantidad |
|---|---|
| Entregado y verificado | 40 componentes |
| Parcial | 8 |
| Falta — nuestro | 30 |
| Falta — bloqueado por A3 | 5 |
| Fuera del alcance con acta | 8 |

**De los 30 pendientes nuestros, 5 son bloqueantes para cerrar el flujo** (§2.1) y de esos, dos
—el pago al final del pedido y el campo consumidor final— se pidieron en mayo.
