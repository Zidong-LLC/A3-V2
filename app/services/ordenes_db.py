"""Borrar una orden o sacarle un análisis desde la plataforma (pedido de A3, 2026-11-09).

Regla del módulo: antes de tocar nada se guarda la foto completa en `audit_log`. Ese
respaldo SÍ frena la operación —al revés que `audit_db.registrar`—: si no se pudo
escribir, no se borra.
"""
from app.services.db import _client


def orden(request_id: str) -> dict | None:
    filas = (_client.table("requests").select("*, clients(clinic_name), couriers(name)")
             .eq("id", request_id).limit(1).execute()).data
    return (filas or [None])[0]


def evento_creacion(request_id: str) -> dict | None:
    """El evento `created`: ahí vive el `profile` (lo que se factura) de la orden."""
    filas = (_client.table("request_events").select("id, event_payload")
             .eq("request_id", request_id).eq("event_type", "created")
             .order("created_at").limit(1).execute()).data
    return (filas or [None])[0]


def _contar(tabla: str, columna: str, valor: str) -> int:
    return (_client.table(tabla).select("id", count="exact").eq(columna, valor)
            .limit(1).execute()).count or 0


def ataduras(request_id: str) -> dict:
    """Lo que el laboratorio ya cargó sobre la orden: con esto no se borra."""
    return {"muestras": _contar("lab_samples", "request_id", request_id),
            "resultados": _contar("lab_results", "request_id", request_id)}


def pedido(pedido_id: str | None) -> dict | None:
    if not pedido_id:
        return None
    filas = _client.table("pedidos").select("*").eq("id", pedido_id).limit(1).execute().data
    return (filas or [None])[0]


def pagos(pedido_id: str) -> list[dict]:
    return (_client.table("pedido_payments").select("status, amount_in_cents")
            .eq("pedido_id", pedido_id).execute()).data or []


def respaldar(request_id: str, accion: str, foto: dict, usuario: str) -> None:
    _client.table("audit_log").insert({"entity": "request", "entity_id": str(request_id),
                                       "action": accion, "changes": foto, "username": usuario}).execute()


def foto(fila: dict, fila_pedido: dict | None) -> dict:
    eventos = (_client.table("request_events").select("event_type, event_payload, created_at")
               .eq("request_id", fila["id"]).order("created_at").limit(200).execute()).data or []
    return {"orden": fila, "eventos": eventos, "pedido": fila_pedido}


def borrar(request_id: str, fila_pedido: dict | None) -> bool:
    """Borra la orden; sus eventos caen en cascada. True si además se fue el pedido, que
    quedó vacío: un pedido sin órdenes, sin factura y sin pagos no le sirve a nadie."""
    _client.table("requests").delete().eq("id", request_id).execute()
    if not fila_pedido:
        return False
    pedido_id = fila_pedido["id"]
    if (_contar("requests", "pedido_id", pedido_id) or fila_pedido.get("alegra_invoice_id")
            or _contar("pedido_payments", "pedido_id", pedido_id)):
        return False
    _client.table("pedidos").delete().eq("id", pedido_id).execute()
    return True


def guardar_perfil(request_id: str, evento: dict, perfil: dict, exam_type: str) -> None:
    """Deja el `profile` nuevo en el evento de creación y el texto en la orden."""
    payload = dict(evento.get("event_payload") or {})
    payload["profile"] = perfil
    if isinstance(payload.get("service_order"), dict):
        payload["service_order"] = {**payload["service_order"], "exam_type": exam_type}
    _client.table("request_events").update({"event_payload": payload}).eq("id", evento["id"]).execute()
    _client.table("requests").update({"exam_type": exam_type}).eq("id", request_id).execute()
