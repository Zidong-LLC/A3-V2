---
name: blueprint-blast
description: Darle forma a una idea de proyecto, automatización o agente ANTES de construir nada — cinco preguntas de descubrimiento (Norte, integraciones, fuente de verdad, entrega, reglas), el esquema de datos primero y un Blueprint aprobado; recién después Link → Architect → Stylize → Trigger. Usala al arrancar la conversación de un proyecto, cuando el pedido está difuso o cuando el equipo está perdido y no sabe por dónde seguir.
---

# Blueprint (protocolo B.L.A.S.T.)

Cinco fases en orden — **B**lueprint · **L**ink · **A**rchitect · **S**tylize · **T**rigger — sobre una
arquitectura de tres capas (SOPs · navegación · herramientas). La idea de fondo: un modelo es
probabilístico y la lógica del negocio tiene que ser determinista; primero se acuerda QUÉ se
construye y con QUÉ datos, y recién después se escribe una línea. Reliability antes que velocidad.
Nunca se adivina la lógica del negocio: se pregunta.

## Cuándo cargarla

- Arranca la conversación de un proyecto nuevo (una web, una automatización, un agente, una
  integración) y el pedido todavía no tiene UN resultado único definido.
- El pedido es difuso («quiero algo para…», «estaba pensando en…», «¿cómo encararías…?»).
- El trabajo ya empezó pero el equipo está perdido: no se sabe qué falta, qué sigue o para qué era.
  Ahí el Blueprint se reconstruye desde lo que hay: es el mapa, no un trámite.

## Protocolo 0 — nada se construye antes del Blueprint aprobado

Hasta que las cinco preguntas estén contestadas, el esquema de datos definido y el Blueprint
aprobado por la persona, **está prohibido construir**:

- En Desarrollo: modo Plan — se escribe sólo en `docs/` (`SPEC.md`, `TASKS.md`), nada de código.
- Como agente: nada de tools de escritura ni de efecto; sólo lectura, preguntas y el documento.
- Como asistente del chat: no se encarga, no se planea el reparto ni se crea un agente. Primero
  el Blueprint, después el camino que corresponda (un agente, un plan, una automatización).

## Fase B — Blueprint (visión y lógica)

### 1. Descubrimiento: las cinco preguntas

| # | Pregunta | Qué resuelve |
|---|---|---|
| 1 | **Norte** — ¿cuál es el resultado único que tiene que pasar? | Un solo resultado verificable. Si hay dos, son dos proyectos. |
| 2 | **Integraciones** — ¿qué servicios externos entran (Stripe, WhatsApp, Sheets, un CRM…) y las claves están listas? | Qué hay que conectar y qué falta pedir. Las claves van como VARIABLE por nombre; el valor nunca se escribe en el chat ni en un documento. |
| 3 | **Fuente de verdad** — ¿dónde viven los datos primarios? | De dónde se lee y quién manda cuando dos fuentes difieren. |
| 4 | **Entrega (payload)** — ¿cómo y dónde tiene que llegar el resultado final? | Un mensaje, una planilla, una pantalla, un PDF, una base. El proyecto está TERMINADO sólo cuando el payload está ahí. |
| 5 | **Reglas de comportamiento** — ¿cómo tiene que «actuar»? tono, límites, lo que NUNCA hace | Las invariantes: lo que no se negocia aunque la conversación lo contradiga. |

Cómo se preguntan en este OS:

- **Primero leé lo que ya hay**: el pedido, el proyecto, el Cerebro, la conversación. Lo que ya
  está contestado no se vuelve a preguntar; se anota como respondido y de dónde salió.
- Lo que falta se pregunta **de a UNA por vez**, con `preguntarAlUsuario` en `tipo: "elegir_una"`
  (o `"confirmar"` si es sí/no) y 2-4 opciones cortas, excluyentes, con la recomendada primera y
  marcada. Una pregunta abierta le pasa al humano el trabajo de escribir la spec; una con opciones
  se contesta en tres segundos. En la misma pregunta, media línea con **qué cambia según la
  respuesta**.
- Tope: **tres preguntas**. Lo que tiene un default razonable (retención de datos, manejo de
  errores, auth, cuántos ítems) no se pregunta: se elige el default y se anota como supuesto.
- Nunca se pregunta por tecnología (la fija el proyecto) ni por el valor de una clave.

### 2. Regla «datos primero»

Antes de cualquier herramienta, el **esquema de datos**: cómo se ve la entrada cruda y cómo se ve
la salida procesada, como JSON de ejemplo (uno de entrada, uno de salida, con los campos que de
verdad se usan). Si otro sistema o agente consume la salida, el esquema es validable y tiene
límite de tamaño y criterio de error. **El código empieza cuando la forma del payload está
confirmada, no antes.**

### 3. Investigación antes de construir de cero

Buscar qué ya existe: el catálogo de recursos de `/recursos` (`buscarRecursos`), el Cerebro, las
skills del catálogo (`buscarSkills`) y los proyectos anteriores. Un motor que ya está resuelto se
adopta —con su licencia y su costo mirados— y no se reescribe.

### 4. El documento: el Blueprint

Ocho líneas, en este orden, y se guarda donde el trabajo vive:

```
BLUEPRINT — <nombre del proyecto>
Norte:          <el resultado único, verificable>
Integraciones:  <servicio → variable de la clave (NOMBRE_VARIABLE) · lista / falta pedir>
Fuente de verdad: <dónde viven los datos primarios · quién manda si difieren>
Entrega:        <dónde y cómo llega el payload final>
Reglas:         <tono · límites · «nunca …»>
Esquema:        entrada { … } → salida { … }
Supuestos:      <lo que se decidió por default, con su motivo>
Preguntas abiertas: <sólo las que cambian el plan; si no hay, «ninguna»>
```

- En **Desarrollo** va arriba de `docs/SPEC.md`, antes de las historias (MVP = H1 sigue siendo la
  primera línea del archivo).
- Como **agente**, el Blueprint aprobado se vuelve las secciones del prompt: Norte → objetivo y
  criterios de éxito; Integraciones → tools/MCPs y su ficha; Fuente de verdad → manifiesto de
  contexto; Entrega → formato de salida y destino; Reglas → invariantes.
- En una **conversación**, se entrega como documento (`crearDocumento`) o directamente en el
  chat, y se pide el OK con `preguntarAlUsuario` en `tipo: "confirmar"`. Aprobado el Blueprint,
  recién ahí se elige el camino: un agente, un plan de reparto o una automatización.

## Fase L — Link (conectividad)

Antes de la lógica, el **handshake** de cada integración: una llamada mínima que prueba que el
servicio responde con la clave dada (leer un registro, listar una cuenta). Si el Link está roto,
no se sigue: se avisa qué clave o permiso falta. En Desarrollo el handshake es la primera tarea de
la fase de Preparación en `docs/TASKS.md`. Las claves entran como variables de entorno por nombre
(`Secretos` del OS): el agente recibe el NOMBRE, nunca el valor, y la salida se redacta.

## Fase A — Architect (las tres capas)

1. **Arquitectura (SOPs en markdown)** — por cada proceso: objetivo, entradas, lógica de las
   herramientas, casos borde. **Regla de oro: si cambia la lógica, primero se actualiza el SOP,
   después el código.** En el OS viven en `docs/` del proyecto o en `/sops`.
2. **Navegación (la decisión)** — la capa de razonamiento: rutea datos entre SOPs y herramientas
   en el orden correcto. No hace cálculos complejos por su cuenta: llama a la herramienta
   determinista que corresponde.
3. **Herramientas (los motores)** — scripts o funciones deterministas, atómicas y testeables.
   Intermedios en `.tmp/`; secretos en variables de entorno; nada de lógica del negocio adentro
   de un prompt.

## Fase S — Stylize (refinamiento y entrega)

El payload se entrega con formato profesional (mensaje bien armado, documento, PDF, pantalla
limpia). Si hay pantalla, aplica el plan visual del proyecto. Antes del deploy, la persona ve el
resultado estilizado y da su devolución: no se despliega algo que nadie miró.

## Fase T — Trigger (puesta en marcha)

- Pasar de la prueba local al entorno real (en el OS: la micro-VM del proyecto, Vercel, o el
  destino que fijó la Entrega).
- Disparadores: **tarea programada** (por reloj), **automatización** (por evento) o webhook. La
  primera semana corre en **modo informe** («habría hecho»), y recién después con efecto.
- **Log de mantenimiento**: después de cada tarea con sentido, 1-3 líneas de handoff —qué cambió,
  por qué importa, cuál es el próximo paso— en `docs/` del proyecto o en la memoria del agente.
  Sin logs ni prosa: lo justo para retomar en una ventana nueva.

## Auto-reparación (el loop de arreglo)

Cuando una herramienta falla: **1) analizar** el error real (stack trace, mensaje; sin adivinar) →
**2) parchear** → **3) probar** que el arreglo anda → **4) actualizar el SOP** con lo aprendido
(«la API exige tal header», «el límite es 5 llamadas/segundo») para que no vuelva a pasar.

## Terminado

- Lo local (`.tmp/`, scraps, logs) es descartable.
- Lo global es el payload en su destino final. **Un proyecto está completo sólo cuando el
  payload está ahí** — no cuando el código compila.
