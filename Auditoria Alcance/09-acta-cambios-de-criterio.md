# A3 Laboratorio Clínico Veterinario
## Acta de definiciones y cambios de criterio durante el proyecto

**Fecha:** 2 de agosto de 2026 · **Preparado por:** Laberit
**Período cubierto:** 16 de abril – 28 de julio de 2026 · **Fuente:** las ocho reuniones de trabajo

---

## Para qué sirve este documento

A lo largo de ocho reuniones se tomaron definiciones sobre el funcionamiento del sistema. Varias
de ellas se precisaron o se reemplazaron en reuniones posteriores, a medida que el equipo de A3
fue viendo el comportamiento real del agente y contrastándolo con su operación diaria.

Este documento reúne esas definiciones con su fecha, para que ambas partes trabajen sobre el mismo
registro al momento de acordar el cierre del proyecto. **No busca asignar responsabilidades:**
busca que no queden definiciones abiertas ni supuestos distintos entre A3 y el equipo de
desarrollo.

Al final hay una lista de **cinco puntos que siguen sin decisión** y que conviene cerrar.

---

## 1. Alcance de los perfiles por especie

| Fecha | Definición |
|---|---|
| 29/04/2026 | Se carga el portafolio de A3. Los perfiles conservan la denominación del catálogo original, que distingue perfiles caninos, felinos y de aplicación general. Quedan 39 caninos, 34 felinos y 60 generales. |
| 06/05/2026 · Reunión 3 | Se confirma que al armar un perfil personalizado el usuario elige entre canino y felino. |
| 07/07/2026 · Reunión 7 | A3 informa que el laboratorio atiende también especies mayores: equinos, bovinos, porcinos y caprinos, además de aves, conejos, roedores y silvestres. |
| 28/07/2026 · Reunión 8 | Se define el criterio inverso: los perfiles aplican a **todas** las especies por defecto, y solo se restringen los que la denominación identifica explícitamente (por ejemplo, T4 canina). La etiqueta debe poder administrarse desde la plataforma. |

**Situación actual:** el sistema opera con el criterio de mayo. Aplicar el criterio de julio
requiere reclasificar los 73 perfiles hoy restringidos y habilitar la administración de etiquetas
en la plataforma.

---

## 2. Criterio de descuento

| Fecha | Definición |
|---|---|
| 16/04/2026 · Reunión 1 | El descuento se aplica según el perfil seleccionado. |
| 06/05 y 20/05 · Reuniones 3 y 5 | Queda pendiente que A3 envíe la tabla de descuentos. |
| 27/05/2026 · Reunión 6 | Se reemplaza el criterio: el descuento se calcula **por cantidad de pruebas**, con independencia del tipo de perfil. Escala definida: 2 pruebas 10 %, 3 pruebas 12 %, 4 pruebas 14 %, 5 pruebas 16 %. |
| 08/06/2026 | Se implementa el criterio por cantidad. |

**Situación actual:** operativo según la definición del 27 de mayo. **Pendiente:** que los
porcentajes sean editables desde la plataforma, como se pidió en esa misma reunión.

---

## 3. Estructura de perfiles

| Fecha | Definición |
|---|---|
| 06/05 y 20/05 · Reuniones 3 y 5 | Los perfiles personalizados se guardan asociados a cada clínica, con nombre automático, y se le ofrecen cuando vuelve a solicitar. |
| 27/05/2026 · Reunión 6 | A3 plantea dejar de manejar los perfiles como unidad cerrada de producto y migrar a pruebas individuales asociadas a etiquetas diagnósticas, para facilitar reportes, inventarios y reactivos. |
| 28/07/2026 · Reunión 8 | Se constata que, en la operación real, los clientes siguen solicitando perfiles cerrados con modificaciones puntuales ("perfil X, cámbieme esta prueba por esta otra"). |

**Situación actual:** conviven ambos modelos. Están construidos el perfil de catálogo, el perfil
personalizado y las etiquetas diagnósticas. **Pendiente:** guardar el perfil que arma el cliente
en la conversación y volver a ofrecérselo en la siguiente solicitud.

---

## 4. Datos de la orden de servicio

| Fecha | Definición |
|---|---|
| 22/04/2026 · Reunión 2 | Se enumeran los datos de la orden: paciente, especie, edad, propietario, exámenes y valor. |
| 20/05/2026 · Reunión 5 | Se amplía la lista: se incorporan **médico remitente, raza y sexo**, y se establece que ninguno es opcional. |

**Situación actual:** el agente solicita los once campos acordados. **Definición cerrada.**

---

## 5. Alta de cliente nuevo

| Fecha | Definición |
|---|---|
| 16/04/2026 · Reunión 1 | Se plantea un preregistro en la plataforma con datos de facturación y documentos, con aviso al área contable y validación humana antes de cargarlo en Alegra. |
| 22/04/2026 · Reunión 2 | Se define que, ante un cliente nuevo, el agente deriva a atención al cliente y **cierra su intervención**. En la misma reunión se plantea también que el formulario podría diligenciarse dentro del agente, con el RUT y demás documentos cargados a una carpeta compartida. |

**Situación actual:** operativo el criterio de derivación. **Pendiente de decisión:** si el agente
debe además capturar documentos, o si esa gestión queda íntegramente en el equipo de A3. Son dos
definiciones distintas tomadas en la misma reunión.

---

## 6. Momento de la forma de pago

| Fecha | Definición |
|---|---|
| 22/04/2026 · Reunión 2 | Al finalizar la orden se muestra la opción de pago. |
| 20/05/2026 · Reunión 5 | Se precisa la secuencia: al completar una orden, el agente pregunta si desea anexar otra o continuar; **si el cliente continúa, recién ahí se solicita la forma de pago**. |
| 28/07/2026 · Reunión 8 | Se confirma y amplía: la forma de pago corresponde al pedido completo, no a cada orden, y no debe figurar en el resumen individual de cada orden. La facturación agrupa todas las órdenes del pedido. |

**Situación actual:** el sistema solicita la forma de pago dentro de cada orden. **Es el ajuste de
mayor impacto entre los pendientes** y está identificado como prioritario.

---

## 7. Asignación del motorizado

| Fecha | Definición |
|---|---|
| 16/04/2026 · Reunión 1 | La asignación del mensajero se realiza automáticamente según la zona. |
| 22/04/2026 · Reunión 2 | Se aclara que recepción mantiene el control de las rutas y que esa operación no cambiaría por completo; la asignación automática por zona quedaría sujeta a confirmación de recepción antes de notificar al mensajero. |
| 13/05 y 20/05 · Reuniones 4 y 5 | Se integra el archivo de zonas de A3 y se construye la zonificación territorial: 8 zonas, 1.649 barrios y cobertura por motorizado, validada por A3 en la reunión 5. |

**Situación actual:** la zonificación está construida y visible en la plataforma. La asignación de
cada solicitud toma el motorizado fijo de la clínica, con posibilidad de cambio manual desde el
panel. **Pendiente de decisión:** cuál de los dos criterios debe gobernar la asignación
automática.

---

## 8. Seguimiento por GPS

| Fecha | Definición |
|---|---|
| 22/04/2026 · Reunión 2 | Se consulta la posibilidad de asignar el mensajero más cercano por geolocalización. Se explica que el seguimiento en tiempo real requiere una aplicación móvil instalada en los equipos de los mensajeros. |
| 13/05/2026 · Reunión 4 | Se acuerda que, de no ser viable, la reasignación quede disponible de forma manual desde recepción. |
| 07/07/2026 · Reunión 7 | Se acuerda mantener el seguimiento por GPS como **mejora posterior**, fuera del cierre del proyecto base. |

**Situación actual:** resuelto mediante el avance de la orden por estados, visible en el portal del
cliente. **Definición cerrada.**

---

## 9. Transcripción de la orden por fotografía

| Fecha | Definición |
|---|---|
| 20/05/2026 · Reunión 5 | A3 consulta la posibilidad de que el cliente envíe una fotografía de la orden para su lectura automática. Se indica que es técnicamente posible, condicionado a la calidad de la imagen y la legibilidad de la escritura manuscrita. **Queda como decisión pendiente.** |
| 28/07/2026 · Reunión 8 | En la prueba con una orden real, la fotografía no resultó legible y los datos debieron dictarse. |

**Situación actual:** no incorporado. **Pendiente de decisión formal**, con el antecedente de la
prueba del 28 de julio.

---

## 10. Validación del médico solicitante

| Fecha | Definición |
|---|---|
| 27/05/2026 · Reunión 6 | El agente no debe avanzar si la clínica, el cliente o el médico no están verificados en la base. |
| 07/07/2026 · Reunión 7 | Se amplía: el médico debe registrarse con nombre completo, apellido, identificación y tarjeta profesional, y debe validarse que esté autorizado para solicitar órdenes por esa clínica. A3 enviaría la base de médicos y tarjetas. |

**Situación actual:** el agente identifica la clínica a partir del médico y no avanza sin clínica
validada. **Pendiente:** la validación de autorización médico–clínica, sujeta a la base de médicos
y tarjetas profesionales.

---

## 11. Información pendiente de A3

Estas entregas condicionan el avance de los puntos anteriores.

| Información | Comprometida | Situación |
|---|---|---|
| Base de médicos, tarjetas profesionales, especies, razas y clientes nuevos | Viernes 10/07/2026 · Reunión 7 | Razas incorporadas el 21/07. Al 28/07 persisten clientes sin dirección, sin NIT y sin motorizado asignado |
| Base de clientes completa | Reunión 4 en adelante | El 28/07 se retiró del sistema el listado con datos incompletos para evitar errores en las pruebas |
| Esquema de "Crea tu perfil" y tabla de descuentos editables | Reunión 6 · 27/05 | Sin recibir |
| Parámetros técnicos de Anarvet | Carta enviada el 20/05 | Camino técnico definido el 28/07: acceso SQL de consulta. Pendientes los parámetros de conexión |
| Cuenta de WhatsApp Business | — | Pendiente |
| Cuenta de facturación de producción, con IVA por análisis y régimen por cliente | — | Pendiente |
| Credenciales, ambientes y documentación técnica | Día 4 del plan · 30/01/2026 | Pendiente |
| Accesos de QA y producción | Día 25 del plan · 02/03/2026 | Pendiente |

---

## 12. Definiciones que siguen abiertas

Estos cinco puntos no tienen decisión tomada. Cerrarlos es condición para fijar la fecha de
entrega final.

1. **Perfiles por especie** — confirmar la reclasificación de los 73 perfiles hoy restringidos y
   el alcance de la administración de etiquetas desde la plataforma.
2. **Alta de cliente nuevo** — si el agente captura documentos o si la gestión queda íntegramente
   en A3.
3. **Asignación del motorizado** — si gobierna la zona o la clínica.
4. **Transcripción por fotografía** — confirmar si se incorpora o se descarta.
5. **Momento de la forma de pago y facturación agrupada por pedido** — alcance y prioridad del
   ajuste.

---

*Documento preparado por Laberit sobre la base de las ocho reuniones de trabajo del período.
Los resúmenes de cada reunión están disponibles a solicitud.*
