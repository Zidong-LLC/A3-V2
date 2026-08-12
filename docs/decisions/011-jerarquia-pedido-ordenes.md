# 011 — Jerarquía pedido → órdenes → análisis

- **Estado:** PROPUESTO (2026-08-12) — pendiente de OK del usuario y de definición de A3
- **Reemplaza:** nada. Extiende la 005 (orden de servicio) y la 009 (Alegra por fases)
- **Origen:** reunión 8 (28/07) + llamada 5 (20/05, forma de pago al final del pedido)

## Problema

A3 pide tres cosas que son la misma: **la unidad que se cobra es el PEDIDO, no la orden.**

1. La forma de pago se pregunta al final del pedido, una vez, no dentro de cada orden.
2. Un pedido agrupa varias órdenes (una por paciente), y cada orden sus análisis.
3. Una factura por pedido, no una por orden.

### La jerarquía, según el cliente (aclarado 2026-08-12)

```
PEDIDO  ─── lo que se factura: una sola factura al final
  └── ORDEN  ─── UNA POR PACIENTE
        └── ANÁLISIS / PERFILES  ─── varios por orden
```

El caso real que describió A3: **uno o varios médicos de la misma clínica cargan varias
órdenes seguidas, para pacientes distintos, sin que se emita factura por cada una.** La
factura sale al final, con todo junto. Un paciente por orden; varios análisis por orden;
varias órdenes por pedido.

Esto confirma que el agrupador es la **sesión de carga**, no el paciente ni el médico: el
médico solicitante puede cambiar entre órdenes del mismo pedido, pero el CLIENTE (la
veterinaria que paga) es el mismo para todo el pedido.

Hoy no existe la entidad pedido. `create_request` (`app/services/db.py:1533`) inserta **una
fila por orden** con su propio `order_number`, y `_finalize_request` (`app/agent.py:2139`)
factura **cada una por separado**. El multi-orden vive solo en la memoria del chat:
`_begin_followup_order` (`app/agent.py:1065`) guarda un snapshot y resetea los campos.

Consecuencia para el cliente: si carga tres pacientes, le preguntan el pago tres veces y le
llegan tres facturas.

## Decisión

### Modelo de datos

Tabla **nueva** `pedidos` + columna nullable en `requests`. No se modifica ninguna tabla
existente: mismo patrón que las migraciones 009, 013 y 014 (alineado con la decisión 006).

```sql
CREATE TABLE IF NOT EXISTS pedidos (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id      uuid REFERENCES clients(id),
    pedido_number  text UNIQUE,            -- P-2026-001, contador anual
    payment_method text,                   -- se llena al CERRAR el pedido
    status         text NOT NULL DEFAULT 'abierto',   -- abierto | cerrado | facturado
    entry_channel  text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    closed_at      timestamptz
);

ALTER TABLE requests ADD COLUMN IF NOT EXISTS pedido_id uuid REFERENCES pedidos(id);
```

`pedido_id` **nullable** a propósito: las órdenes históricas y las que entren por el portal
siguen funcionando sin pedido. El contador anual replica `next_order_number()` de la
migración 011 (`P-` + año + secuencia), que ya está probado.

### Flujo conversacional

`payment_method` sale de `ROUTE_REQUIRED_FIELDS` (`app/flow.py:28`) y pasa a ser un dato del
pedido. La secuencia queda:

```
[datos de la orden] → análisis → observaciones
   → RESUMEN DE LA ORDEN (sin forma de pago)  → "¿confirmás?"
   → sí → se crea la orden con pedido_id, y se pregunta:
          "¿Agregás otra orden a este pedido o seguimos con el pago?"
   → otra orden → vuelve al inicio conservando cliente y estables (mecanismo actual)
   → seguimos   → forma de pago (UNA vez)
                → RESUMEN DEL PEDIDO (todas las órdenes + total)
                → cierre + UNA factura con las líneas de todas las órdenes
```

**Costo en turnos para el caso de una sola orden:** hoy el cliente ya recibe el
`CLOSING_PROMPT` ("si necesitas otra orden, escribime: otra orden"), así que el turno de
"¿otra orden?" no es nuevo — lo que se agrega es **un turno**: la forma de pago se pregunta
después de esa decisión en vez de antes del resumen. Es aceptable, pero es el punto a
vigilar: el pedido de una sola orden es el caso más común.

### Facturación

`_finalize_request` deja de facturar. La factura se emite en un `_finalize_pedido` nuevo, con
las líneas acumuladas de todas las órdenes del pedido. `billing.build_invoice_lines`
(`app/billing.py:94`) ya arma líneas desde el `profile` de una orden: se lo llama N veces y
se concatena. `invoices_cache` necesita una columna `pedido_id` junto a `request_id`.

Esto **desbloquea** dos pedidos de Fase 2 que dependían de esto: una factura por pedido, y
—de paso— es el momento natural para meter el nombre del paciente en la descripción de cada
línea (hoy `_line()` no lo recibe).

## Qué dispara la factura del pedido — DECIDIDO (2026-08-12)

**Cierre explícito como camino principal + barrido por inactividad como red.**

- **Explícito:** el cliente dice "eso es todo" o responde la forma de pago → el pedido se
  cierra y se factura. Es el 100% de los pedidos sanos.
- **Red por inactividad:** un barrido cierra y factura los pedidos `abierto` que llevan X
  horas sin actividad. Cubre al cliente que abandona a mitad sin decir nada.
- **Cierre manual desde el dashboard** para los casos raros que ninguna de las dos atrape.

El barrido necesita un **job programado, que hoy el sistema no tiene** (las alertas del
dashboard se calculan al renderizar, no hay scheduler). Por eso la implementación se hace en
dos tiempos: primero el cierre explícito —que es el camino principal en cualquier variante—,
y el barrido después, sin rehacer nada. El pedido `abierto` viejo es visible en el dashboard
mientras tanto, así que ninguna orden se pierde.

El valor de X y quién corre el barrido quedan por definir con A3.

### Opciones evaluadas

| Disparador | A favor | En contra |
|---|---|---|
| **Cierre explícito** ("eso es todo" / responde el pago) | Es el que el cliente controla; sin ambigüedad | Si abandona, el pedido queda abierto y sin facturar para siempre |
| **Cierre por inactividad** (X horas sin actividad) | Recoge los abandonos; no requiere nada del cliente | Hace falta un job programado, que hoy el sistema no tiene |
| **Cierre por corte diario** (17:30, el corte que ya existe) | Se alinea con la operación real del laboratorio y con la regla de negocio ya vigente | Un pedido de las 18:00 espera al día siguiente |
| **Cierre manual desde la plataforma** | Control humano, sirve de red para los otros | Trabajo para el equipo de A3 |

Se adoptó la combinación de la primera y la segunda, con la cuarta como respaldo manual.

## Archivos que cambian

| Archivo | Cambio |
|---|---|
| `db/migrations/018_pedidos.sql` | tabla + columna + contador anual |
| `app/services/db.py` | `create_pedido`, `close_pedido`, `create_request` con `pedido_id` |
| `app/flow.py` | `payment_method` fuera de `ROUTE_REQUIRED_FIELDS`; pregunta de cierre de pedido |
| `app/orders.py` | `_order_summary_lines` sin la línea de pago; `_pedido_summary_lines` nuevo |
| `app/enforcers/flujo.py` | `_enforce_payment_step` se mueve del cierre de orden al de pedido |
| `app/agent.py` | `_finalize_request` sin facturar; `_finalize_pedido` nuevo |
| `app/billing.py` | acumular líneas de N órdenes |
| `app/dashboard.py`, `app/platform_api.py` | mostrar el pedido en los listados |

## Pasos del contrato que se tocan (requieren OK explícito)

- **B10 · Resumen** — pierde la línea de forma de pago
- **B13 · Cierre y forma de pago** — se parte en dos: cierre de orden y cierre de pedido
- **B14 · Multi-orden** — pasa de ser un extra a ser el mecanismo central
- **B18 · Alegra** — una factura por pedido

## Riesgos

1. **El caso de una sola orden no debe sentirse más largo.** Es el 90% del uso real. Si en
   pruebas agrega fricción, la salida es fusionar la confirmación de la orden con la pregunta
   de "¿otra orden o pago?" en un solo turno.
2. **Retrocompatibilidad:** `pedido_id` nullable y `payment_method` sigue existiendo en
   `requests` (se copia del pedido al cerrarlo), así que el dashboard, la orden imprimible y
   la vista `service_orders` siguen funcionando sin tocarse.
3. **Facturar al final:** si el cliente abandona el pedido a mitad, quedan órdenes creadas y
   sin facturar. Hay que decidir qué hace el dashboard con un pedido `abierto` viejo —
   propuesta: mostrarlo como pendiente, igual que hoy se muestran las órdenes sin motorizado.
4. **Contradicción con A3 a resolver antes:** en la llamada 7 pidieron *bloquear* el cambio
   de cliente maestro; ERR-099 lo dejó permisivo. Con pedidos, el cliente es del PEDIDO, así
   que cambiarlo a mitad afecta a todas sus órdenes. Conviene cerrar esa definición primero.

## Alternativa descartada

**Columna `group_id` en `requests` sin tabla padre.** Más barato, pero el pedido necesita
estado propio (`abierto`/`cerrado`/`facturado`), su propia forma de pago y su propio número
para la factura. Sin entidad, esos datos se duplicarían en cada fila y no habría dónde colgar
el `alegra_invoice_id` del pedido.
