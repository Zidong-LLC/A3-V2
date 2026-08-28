# Decisiones de alcance — 28 de agosto de 2026

Recorte y confirmación del alcance sobre el balance del 25/08, tomadas por el usuario en la
revisión de pendientes. Este documento manda sobre lo que digan los inventarios anteriores.

## Lo que SALE del alcance

| Frente | Decisión | Motivo |
|---|---|---|
| Adjuntos y fotos en el chat | Fuera | El agente es de texto. No se contrató recibir documentos ni imágenes |
| Inventario en Alegra | Fuera | Alegra descuenta la unidad sola al facturar: si hay 100 prequirúrgicos y se factura uno, quedan 99. No hay nada que construir |
| Pasarela de pago (Wompi / Bancolombia) | Cancelada | El pago se deriva a una persona, como hoy |
| Unidades y valores de referencia por analito (Anarvet) | Fuera | El documento lo carga el cliente. Nosotros mostramos la información como llega hoy |
| Historial de resultados anterior a la conexión | Fuera | El espejo arranca donde nos conectamos y va acumulando |
| Tabla de usuarios y rol de mensajero | Fuera | Ver abajo |
| Validación bloqueante del médico veterinario | Fuera | El agente sigue anotando el nombre que le den, sin comprobar que esté registrado |

## Roles: solo dos

- **Personal interno de A3**: entra con el usuario administrador de la plataforma. No hay
  usuarios individuales por persona.
- **Cliente final**: entra al portal con nombre de la clínica y NIT, ve solo lo suyo.
- **El motorizado no se loguea a nada.**

Esto cierra el pendiente de "cuentas con rol para el equipo y los motorizados".

## Lo que ENTRA

**Consulta de resultados por chat.** El cliente pide un resultado por Telegram, el agente
busca en los resultados ya cargados en la plataforma los de ese paciente y le envía **el PDF
por el mismo chat** (decisión del usuario: el archivo, no un enlace al portal). La carga de documentos por paciente ya existe. Falta el envío de archivos por
el canal y reemplazar el mensaje fijo de "resultados no disponibles", que es un paso aprobado
del contrato conversacional y requiere OK antes de tocarse.

**Calendario de mensajeros, completo.** Vista de recogidas por mensajero con reasignación y
reprogramación desde la plataforma. La asignación automática por zona ya existe y se mantiene.

## Lo que queda en observación

- **Bloquear el cambio de cliente maestro dentro de un pedido**: se prueba antes de decidir.
- **Los 17 mapeos de Anarvet**: no se toca la base. Esperan la respuesta de A3 al documento
  `docs/anarvet-consulta-clientes.html`. Son 88 informes que hoy no se le muestran a nadie.

## Verificado el mismo día

**La migración 030 de Mascolab ya estaba aplicada en Supabase.** Comprobado contra la base
viva: 30 perfiles y 92 análisis en las categorías Mascolab, los 122 códigos presentes, cero
faltantes. El catálogo queda en 163 perfiles y 275 análisis. **El frente de catálogo y precios
se cierra al 100%.**
