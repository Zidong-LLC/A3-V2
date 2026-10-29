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


def es_recogida(fila: dict) -> bool:
    return (fila.get("service_area") or "route_scheduling") == "route_scheduling"


def agrupar(pedidos: list[dict], filas: list[dict]) -> dict:
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
