# Modificaciones del Agente Conversacional - Filtradas

**Documento enfocado**: Solo los cambios que aplican DIRECTAMENTE al chatbot de Telegram.

---

## 1. FLUJO DE IDENTIFICACIÓN DE CLIENTE

### 1.1 Búsqueda Progresiva (Nueva)
El bot debe validar si el cliente es nuevo o existente con este flujo:

1. **Pregunta inicial**: "¿Cuál es el NIT de tu veterinaria?" (o nombre fiscal)
2. **Busca en BD por NIT** (soporta formato con/sin dígito verificador: "9010083459" o "90100-83-45-9")
3. **Si no encuentra**: "¿Cuál es el nombre de tu veterinaria?"
4. **Busca en BD por nombre**
5. **Si sigue sin encontrar**: "Aún no logro ubicar tu registro. ¿Eres cliente nuevo?"
   - Si dice SÍ → **ESCALAR a Atención al Cliente** (sin crear cliente en BD)
   - Si dice NO → Pedir más datos

**Importante**: No repetir preguntas ya respondidas.

---

## 2. FLUJO DE ORDEN DE SERVICIO

### 2.1 Recopilación de Datos (Conversacional, no formulario)
El bot pregunta campo por campo, **conversacionalmente**:

1. "¿Cuál es el nombre del paciente?"
2. "¿Qué especie es? (canino/felino/otra)"
3. "¿Cuántos años tiene?"
4. "¿Nombre del propietario?"
5. "¿Qué análisis/perfiles deseas?"
   - Mostrar **perfiles predefinidos** (del catálogo)
   - Permitir seleccionar un perfil existente
   - **NUEVO**: Opción "Crear tu perfil" (combos personalizados)

### 2.2 Crear Tu Perfil (Nuevo)
Si cliente elige "Crear tu perfil":

1. Bot muestra **categorías de pruebas** (Hematología, Química Sanguínea, etc.)
2. Cliente selecciona servicios individuales conversacionalmente
3. Bot calcula automáticamente: **precio base + descuento según cantidad**
4. Bot sugiere: "¿Parece similar al perfil que usaste antes? ¿Quieres ese?"
5. Mostrar **precio final** del perfil personalizado

---

## 3. FORMA DE PAGO (Nueva funcionalidad)

### 3.1 Pregunta Inicial
"¿Deseas pagar ahora o contra entrega?"

### 3.2 Opción 1: Contado (Pagar ahora)
- "¿Cómo prefieres pagar? (PSE, Transferencia Bancaria, Tarjeta de Crédito, etc.)"
- Bot **genera/muestra link de pago** (enlace externo, no procesa bot directamente)
- Mensaje: "Te estamos validando tu pago con nuestro equipo administrativo"
- **CRÍTICO**: No esperar validación de pago para programar ruta
  - El motorista va **aunque pago esté pendiente**
  - Se valida después (contabilidad la resuelve)

### 3.3 Opción 2: Contraentrega (Efectivo con motorista)
- Mensaje: "El motorista cobrará en efectivo al momento de recoger la muestra"
- Motorista confirma recepción de pago en plataforma interna (no en bot)

---

## 4. DIRECCIÓN Y UBICACIÓN

### 4.1 Recopilación de Dirección
1. "¿Cuál es la dirección exacta donde recogeremos la muestra?"
2. Mostrar dirección detectada/sugerida
3. "¿Es correcta? (Sí/No)"
4. Si No: "¿Cuál es la dirección correcta?"

### 4.2 Asignación Automática de Motorizado
1. Bot identifica **zona geográfica** de la dirección
2. **Asigna automáticamente** el motorista correspondiente a esa zona
3. Bot **NO permite selección manual** (eso es para recepción)
4. **El chat NO se cierra** - cambia fase/estado internamente, pero cliente sigue teniendo acceso al bot

### 4.3 Notificaciones (Automáticas desde bot)
- Notificar al **motorista asignado** (con datos de orden)
- Notificar a **recepción** (para visibilidad)

---

## 5. CONFIRMACIÓN Y CIERRE

### 5.1 Resumen de Orden
Mostrar resumen completo:
- Paciente (nombre, especie, edad)
- Propietario
- Análisis solicitados
- Total a pagar
- Dirección de recogida
- Horario estimado (si aplica)

### 5.2 Mensaje de Confirmación
"Hemos recibido tu orden. Tu motorizado será notificado."

### 5.5 Chat Permanece Abierto
- **No se cierra** la conversación
- Cliente puede hacer preguntas adicionales
- Cliente puede consultar estado de su orden
- Bot permite nuevas solicitudes en la misma conversación

---

## 6. CONSULTA DE ESTADO

### 6.1 Si cliente pregunta "¿Cómo va mi orden?"
1. Bot consulta el estado en **ANARVET** (integración externa)
2. Responde conversacionalmente:
   - "Tu muestra está en análisis, estará lista en 2 días"
   - "Tu análisis está completado, resultados llegando a tu email"
   - Etc.

---

## 7. ENTREGA DE RESULTADOS

### 7.1 Notificación Automática
Cuando resultados estén listos:
- Bot notifica al cliente
- Envía enlace o archivo con resultados (si aplica)

---

## 8. ESCALADAS AUTOMÁTICAS

### 8.1 Casos de Escalada

**Contabilidad/Pagos:**
- Cliente pregunta sobre métodos de pago alternativos
- Cliente tiene problema con pago
- Cliente solicita cambio de forma de pago
- → Escalar a número de contabilidad (pendiente definir)

**PQRs (Peticiones, Quejas, Reclamos):**
- Cliente reclama sobre calidad de servicio
- Cliente reporta problema con motorista
- Cliente reporta error en análisis
- → Escalar a número de PQRs (pendiente definir)

**Cliente Nuevo Sin Datos Completos:**
- Bot no logra identificar cliente
- Bot no logra recolectar datos esenciales
- → Escalar a recepción para manual follow-up

---

## 9. MANEJO DE SOLICITUDES MÚLTIPLES

### 9.1 En la Misma Conversación
- Cliente puede hacer múltiples órdenes de servicio
- **No simultáneamente** - secuencialmente
- Entre orden 1 y orden 2:
  - Bot pregunta: "¿Necesitas algo más?"
  - Si SÍ → reiniciar flujo de orden de servicio
  - Si NO → cierre conversación o disponibilidad para consultas

---

## 10. TONO Y VOZ

### 10.1 Principios
- **Conversacional**: Preguntas como persona, no formulario
- **Colombiano**: Lenguaje natural, cercano
- **Eficiente**: No repetir información
- **Claro**: Explicar pasos siguientes

---

## Resumen Arquitectónico (Chatbot)

```
┌─────────────────────────────────────┐
│     AGENTE CONVERSACIONAL (BOT)     │
├─────────────────────────────────────┤
│ 1. Identificar cliente (NIT/nombre) │
│    └─ Escalar si es nuevo           │
│                                     │
│ 2. Recolectar orden de servicio     │
│    ├─ Paciente (nombre/especie/edad)│
│    ├─ Propietario                   │
│    ├─ Análisis (predefinido o custom)│
│    └─ Crear perfil personalizado    │
│                                     │
│ 3. Forma de pago (NEW)              │
│    ├─ Contado (PSE/Transferencia)   │
│    └─ Contraentrega (efectivo)      │
│                                     │
│ 4. Dirección y motorista            │
│    ├─ Confirmar dirección           │
│    ├─ Asignar motorista (automático)│
│    └─ Notificar motorista + recepción│
│                                     │
│ 5. Resumen y confirmación           │
│    └─ Chat permanece ABIERTO        │
│                                     │
│ 6. Disponible para:                 │
│    ├─ Consultar estado              │
│    ├─ Recibir resultados            │
│    ├─ Escalar a contabilidad/PQRs   │
│    └─ Nueva orden de servicio       │
└─────────────────────────────────────┘
```

---

## Cambios Clave vs Versión Anterior

| Aspecto | Antes | Ahora |
|---------|-------|-------|
| **Búsqueda de cliente** | Pregunta simple | Búsqueda progresiva (NIT→nombre) |
| **Orden de servicio** | Formulario con campos | Preguntas conversacionales |
| **Perfiles** | Solo predefinidos | Predefinidos + crear custom |
| **Forma de pago** | No contemplado | Contado vs Contraentrega |
| **Cierre** | Chat se cierra | Chat permanece abierto |
| **Motorista** | Manual selección | Asignación automática por zona |
| **Notificaciones** | Solo a cliente | Cliente + motorista + recepción |

---

## Integraciones Necesarias (No chatbot, pero el bot las llama)

1. **ANARVET**: Consultar estado de análisis (para responder "¿Cómo va?")
2. **ALEGRA**: Crear factura (tras completar orden) - backend
3. **BD de Zonas**: Mapear dirección → zona → motorista
4. **Sistema de notificaciones**: Telegram al cliente, interno a motorista/recepción

---

## Información Pendiente del Cliente

- [ ] Números de teléfono para escalar contabilidad/pagos
- [ ] Números de teléfono para escalar PQRs
- [ ] Definición de zonas geográficas con números
- [ ] Estructura de perfiles predefinidos (cuáles poner en bot)
- [ ] Tabla de descuentos por cantidad de parámetros
- [ ] API de ANARVET (endpoint, auth, qué datos expone)
- [ ] Horarios de recogida disponibles por zona
