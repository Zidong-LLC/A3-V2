# Modificaciones Solicitadas - A3 Laboratorio Veterinario

## Fuente: Primera Charla Cliente + Catálogo 2025

---

## 1. AGENTE CONVERSACIONAL (Chatbot)

Lo que debe hacer el chatbot directamente en la conversación.

### 1.1 Flujo de Cliente Nuevo vs Existente
- Validar si es cliente nuevo o existente
- **Búsqueda progresiva**:
  1. Preguntar: "¿Cuál es el NIT de tu veterinaria?" (o nombre fiscal)
  2. Buscar en BD por NIT
  3. Si no encuentra: "¿Cuál es el nombre de tu veterinaria?"
  4. Buscar en BD por nombre
  5. Si sigue sin encontrar: "Aún no logro ubicar tu registro. ¿Eres cliente nuevo?"
     - Si dice SÍ: Derivar a Atención al Cliente (ver sección 1.8)
     - Si dice NO: Pedir más datos
- **IMPORTANTE**: No repetir preguntas (si ya preguntó NIT, no volver a preguntar NIT)
- Si es existente: proceder directamente a programación de ruta
- **Válidos**: Búsqueda CON y SIN dígito de verificación (ej: "90100-83-45-9" o "9010083459")

### 1.2 Asignación Automática de Motorizado
- **Basada en ZONAS**: El bot debe identificar la zona del cliente según dirección
- **Automáticamente**: Asignar el motorizado correspondiente a esa zona
- **Sugerencia por GPS (futuro)**: Si se implementa, sugerir motorista **más cercano** en tiempo real
- El bot **NO** debe permitir selección manual (eso es en la plataforma/recepción)
- **El chat continúa abierto**: Cambiar de fase/estado internamente, pero el cliente sigue teniendo disponible el bot
- Mostrar confirmación: "Tu dirección de recogida es: [DIRECCIÓN]. ¿Es correcta? (Sí/No)"
- Si dice No: "¿Cuál es la dirección correcta?"
- Notificar automáticamente:
  - Al motorista asignado
  - A recepción (para que tengan visibilidad)

### 1.3 Orden de Servicio (Campo por Campo)
- **NO es un formulario visual**, el bot pregunta **conversacionalmente**:
  - "¿Cuál es el nombre del paciente?"
  - "¿Qué especie es? (canino/felino/otra)"
  - "¿Cuántos años tiene?"
  - "¿Nombre del propietario?"
  - "¿Qué análisis/perfiles deseas? Puedes elegir perfiles predefinidos o crear el tuyo"
- Mostrar **perfiles sugeridos** del catálogo
- Permitir seleccionar perfil **predefinido**
- **NUEVO**: Permitir "Crear tu perfil" (combos personalizados)
- Al final: Mostrar resumen con **total a pagar**

### 1.4 Crear Tu Perfil (Combos Personalizados)
- Flujo conversacional que permita al cliente:
  - Ver categorías de pruebas (Hematología, Química Sanguínea, etc.)
  - Seleccionar servicios individuales
  - El bot calcula automáticamente: **precio base + descuento según cantidad**
  - Mostrar el precio final del perfil personalizado
- El bot debe sugerir: "Perfil similar al que usaste antes: ¿Quieres ese?"

### 1.4 Forma de Pago (NUEVA)
- Pregunta: "¿Deseas pagar ahora o contra entrega?"
- **Opción 1 - Contado (Ahora)**:
  - "¿Cómo prefieres pagar? (PSE, Transferencia Bancaria, Tarjeta de Crédito, etc.)"
  - Enviar **link de pago** (generado en la plataforma, NO por el bot)
  - Mostrar: "Te estamos validando tu pago con nuestro equipo administrativo"
  - **IMPORTANTE**: No esperar a que se valide para programar ruta. El motorista va aunque pago esté pendiente
- **Opción 2 - Contraentrega (Efectivo con motorista)**:
  - Mensaje: "El motorista cobrará en efectivo al momento de recoger la muestra"
  - El motorista confirma recepción de pago en la plataforma

### 1.5 Flujo de Dirección
- Pregunta: "¿Cuál es la dirección exacta donde recogeremos la muestra?"
- Mostrar dirección encontrada, pedir confirmación: "¿Es correcta? (Sí/No)"
- Si No: "¿Cuál es la dirección correcta?"

### 1.6 Cierre y Notificaciones
- Una vez confirmada dirección y forma de pago:
  - Mostrar resumen completo (paciente, análisis, total, dirección)
  - Mensaje de confirmación: "Hemos recibido tu orden. Tu motorizado será notificado"
  - Asignar motorizado automáticamente (por zona)
  - Enviar notificación al motorista asignado
  - Enviar notificación a recepción
  - **El chat NO se cierra**: Permanece disponible para dudas adicionales

### 1.8 Escaladas Automáticas
- **Contabilidad/Pagos**: Escalar a número específico (pendiente definir)
- **PQRs (Peticiones, Quejas, Reclamos)**: Escalar a número específico (pendiente definir)
- **Cliente nuevo sin datos completos**: Escalar a recepción

### 1.9 Consulta de Estado
- Si cliente pregunta "¿Cómo va mi orden?", el bot debe:
- Consultar estado en ANARVET (ver sección 3)
  - Responder conversacionalmente: "Tu muestra está en análisis, estará lista en 2 días"

### 1.10 Entrega de Resultados
- Cuando resultados estén listos, el bot debe:
  - Notificar al cliente
  - Enviar enlace o archivo con resultados (si aplica)

---

## 2. INTEGRACIONES CON PLATAFORMAS EXTERNAS

Conexiones que el bot necesita hacer con sistemas terceros.

### 2.1 ANARVET (Sistema de Análisis del Laboratorio)
- **Qué necesita**: Estado actual del análisis de una muestra
- **Cuándo se consulta**: Cuando cliente pregunta "¿Cómo está mi análisis?"
- **Qué trae**: Fase actual (en cola, en proceso, completado, listo para entrega)
- **Acción bot**: Mostrar conversacionalmente el estado

### 2.2 Base de Datos de Zonas y Motoristas
- **Qué necesita**: Tabla con:
  - Número de zona
  - Descripción geográfica de zona
  - Motorista asignado a cada zona
  - Horarios de trabajo del motorista
  - Días de descanso/incapacidades (dinámico)
- **Cuándo se consulta**: Al registrar cliente nuevo para asignar motorista
- **Responsabilidad**: Laboratorio mantiene esta tabla actualizada (en la plataforma interna)

---

## 3. PLATAFORMA INTERNA (Gestión y Visualización)

Lo que el laboratorio maneja internamente, NO es responsabilidad del chatbot.

### 3.1 Gestión de Zonas y Rutas
- Crear/editar zonas geográficas
- Asignar motorista a cada zona
- Visualizar zonas en mapa (opcional)

### 3.2 Calendario de Repartidores
- **Nueva funcionalidad**: Sección para definir qué motorista trabaja cada día
- Por qué: Hay cambios diarios por incapacidades, descansos, permisos
- Qué permite:
  - A comienzo de semana: definir motorista por zona y día
  - Si hay cambio urgente: actualizar en el día (se sincroniza con bot)
  - Visualizar historia de cambios

### 3.3 Gestión de Portafolio y Precios
- Cargar/actualizar nuevo portafolio (27 páginas actualmente)
- Administrar precios de servicios individuales
- Definir **descuentos automáticos** por cantidad:
  - Ej: 3 parámetros = 5% descuento
  - Ej: 5+ parámetros = 10% descuento
- Crear/editar perfiles predefinidos

### 3.4 Órdenes de Servicio Visual
- Visualizar todas las órdenes creadas (vía chatbot)
- Información:
  - Cliente
  - Fecha/hora
  - Perfil solicitado
  - Motorista asignado
  - Estado actual (pendiente recogida, en análisis, completado)
  - Precio total y descuento aplicado

### 3.5 Asignación Manual de Motorista (Override)
- Si el motorista asignado automáticamente tiene un problema:
  - Poder cambiar manualmente a otro motorista para esa orden
  - Registrar el cambio con razón

### 3.6 Gestión de Clientes
- Crear cliente manualmente (si falla en chatbot)
- Editar datos de cliente
- Vincular cliente a zona automáticamente

### 3.7 Reportes y Dashboards
- Órdenes por día
- Órdenes por motorista
- Órdenes por zona
- Perfiles más solicitados
- Ingresos por cliente

### 3.8 Integración con Sistemas Internos (Visualización)
- Mostrar estado de análisis (traído de ANARVET)
- Mostrar historial de órdenes por cliente

---

## 4. INFORMACIÓN PENDIENTE DEL CLIENTE

Cosas que el cliente mencionó que debe enviar.

- [ ] Número de teléfono para escalar **contabilidad/pagos**
- [ ] Número de teléfono para escalar **PQRs**
- [ ] Definición de **zonas geográficas** con números y descripción
- [ ] **Nuevo portafolio** con precios actualizados (mencionaron cambios recientes)
- [ ] Tabla de **descuentos automáticos** por cantidad de parámetros
- [ ] **Estructura de perfiles predefinidos** (cuáles deben estar en el chatbot)
- [ ] Requisitos de **API de ANARVET** (qué datos expone, cómo consultarla)
- [ ] Horarios de recogida disponibles por zona/motorista

---

## 5. RESUMEN VISUAL

```
┌─────────────────────────────────────────┐
│         AGENTE CONVERSACIONAL           │
│  (Chatbot Telegram)                     │
├─────────────────────────────────────────┤
│ ✓ Cliente nuevo o existente             │
│ ✓ Asignar motorista por zona            │
│ ✓ Seleccionar análisis                  │
│ ✓ NUEVO: Crear tu perfil               │
│ ✓ Confirmar dirección                   │
│ ✓ Notificar motorista                   │
│ ✓ Consultar estado (ANARVET)            │
│ ✓ Escalar pagos/PQRs                    │
└──────────┬──────────────────────────────┘
           │
    ┌──────┴─────────┬──────────────────┐
    │                │                  │
    ▼                ▼                  ▼
┌─────────┐   ┌──────────┐    ┌──────────────┐
│ ANARVET │   │ PLATAFORMA   │
│(Estado) │   │(Gestión)     │
└─────────┘   └──────────────┘
```

---

## Próximos Pasos

1. ✋ **ESPERAR** segunda charla del cliente
2. Extraer modificaciones adicionales
3. Consolidar lista final
4. Priorizar por complejidad técnica
5. Definir fase de implementación
