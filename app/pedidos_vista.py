"""Una sola página de Pedidos: cada pedido con sus órdenes adentro (ERR-194).

Había dos pantallas con la misma tabla `requests` y tres nombres («Solicitudes», «Orden» y
«Orden de servicio») sin un número en común para cruzarlas; el usuario no entendía qué era
cada cosa. Ahora: un PEDIDO junta las órdenes que se cobran en una factura y cada ORDEN es
una recogida (un paciente) con su motorizado, estado y fecha editables, como en Solicitudes.

Solo recogidas: las altas de cliente nuevo y los escalados a contabilidad también viven en
`requests`, pero no son órdenes. Las órdenes anteriores a que el portal y «Nueva Orden»
abrieran pedido (29/10) quedan en un grupo «Órdenes sin pedido».
"""
CANALES = {"portal": "Portal del cliente", "manual": "Cargado en el laboratorio",
           "telegram": "Chat", "chatwoot": "Chat", "whatsapp": "WhatsApp"}
ESTADOS = {"abierto": "Abierto", "cerrado": "Cerrado sin facturar", "facturado": "Facturado"}
MAX_SUELTAS = 150
# Estado del pago en línea (tabla pedido_payments) → cómo se lee en el encabezado del pedido.
PAGOS = {"approved": "Pagado en línea", "pending": "Link enviado, sin pagar", "declined": "Pago rechazado",
         "error": "Pago con error", "voided": "Pago anulado", "mismatch": "Pagó un monto distinto"}
FACTURA_EMITIDA = ("open", "closed", "paid")


def es_en_linea(forma) -> bool:
    return "linea" in str(forma or "").lower() or "línea" in str(forma or "").lower()


def _pago(pedido: dict, pago: dict | None) -> dict | None:
    """Lo que se muestra del cobro en línea, o None si el pedido no es de pago en línea."""
    if pago:
        estado = pago.get("status") or "pending"
        return {"estado": estado, "texto": PAGOS.get(estado, estado),
                "monto": int(pago.get("amount_in_cents") or 0) // 100,
                "url": pago.get("url") if estado != "approved" else None}
    if es_en_linea(pedido.get("payment_method")) and pedido.get("status") != "abierto":
        return {"estado": "sin_link", "texto": "Pago en línea sin link", "monto": 0, "url": None}
    return None


def es_recogida(fila: dict) -> bool:
    return (fila.get("service_area") or "route_scheduling") == "route_scheduling"


def agrupar(pedidos: list[dict], filas: list[dict], pagos: dict | None = None,
            facturas: dict | None = None) -> dict:
    """{pedidos: [... con `filas`, `canal`, `estado`], sueltas: [...], abiertos, sin_facturar}.
    `filas` son las órdenes completas (las mismas de la tabla de Solicitudes); si una orden de
    un pedido viejo no está entre ellas, la plantilla muestra el resumen de `orders`."""
    recogidas = [f for f in filas if es_recogida(f)]
    por_pedido: dict[str, list[dict]] = {}
    sueltas = []
    for fila in recogidas:
        if fila.get("pedido_id"):
            por_pedido.setdefault(str(fila["pedido_id"]), []).append(fila)
        else:
            sueltas.append(fila)
    for pedido in pedidos:
        pedido["filas"] = sorted(por_pedido.get(str(pedido.get("id")), []),
                                 key=lambda f: f.get("requested_at") or "")
        pedido["canal"] = CANALES.get(pedido.get("entry_channel") or "", "Chat")
        pedido["estado"] = ESTADOS.get(pedido.get("status"), pedido.get("status") or "-")
        pedido["pago"] = _pago(pedido, (pagos or {}).get(pedido.get("id")))
        factura = (facturas or {}).get(str(pedido.get("alegra_invoice_id") or "")) or {}
        pedido["emitida"] = bool(factura.get("is_stamped") or factura.get("status") in FACTURA_EMITIDA)
        pedido["factura_numero"] = factura.get("number") if pedido["emitida"] else None
    # Los abiertos primero (alguien tiene que mirarlos) y después del más nuevo al más viejo.
    ordenados = sorted(pedidos, key=lambda p: p.get("created_at") or "", reverse=True)
    ordenados.sort(key=lambda p: p.get("status") != "abierto")
    return {
        "pedidos": ordenados,
        "sueltas": sueltas[:MAX_SUELTAS],
        "sueltas_total": len(sueltas),
        "abiertos": sum(1 for p in pedidos if p.get("status") == "abierto"),
        "sin_facturar": sum(1 for p in pedidos if p.get("status") == "cerrado"),
    }
