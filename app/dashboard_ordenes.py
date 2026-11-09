"""Eliminar una orden o quitarle un análisis desde Pedidos (pedido de A3, 2026-11-09).

«Si el cliente tiene varios análisis y uno se cargó mal o se pidieron dos de más, que se
pueda borrar ese». Hasta ahora una orden solo se podía marcar Cancelada.

Para que no cause problemas:
- la foto de lo que había se guarda en el historial ANTES de tocar; sin respaldo no se borra;
- no se toca una orden con muestras o resultados en el laboratorio, ni un pedido ya pagado
  en línea, ni uno cuya factura ya fue emitida;
- la plataforma NO modifica Alegra: si el pedido ya tiene borrador, avisa que hay que
  corregirlo allá.
El permiso por perfil lo controla `app/access.py` antes de llegar acá.
"""
import logging

from flask import Blueprint, jsonify, request

from app import access, orden_edicion
from app.services import alegra, audit_db, db, ordenes_db

log = logging.getLogger(__name__)
dashboard_ordenes = Blueprint("dashboard_ordenes", __name__)
_login_required = access.login_requerido

_SIN_MOVER = "Si no va, márcala como Cancelada en la columna Estado."
_FACTURA_VIVA = ("open", "closed", "paid")


def _estado_factura(invoice_id: str) -> str | None:
    """Estado de la factura en Alegra (solo lectura), o None si no se pudo consultar."""
    try:
        return str((alegra.get_invoice(invoice_id) or {}).get("status") or "").lower() or None
    except Exception:  # noqa: BLE001 — sin Alegra no se adivina: se frena
        log.warning("ordenes: no se pudo leer la factura %s de Alegra", invoice_id)
        return None


def revisar(fila: dict, fila_pedido: dict | None) -> tuple[str | None, list[str]]:
    """(motivo por el que NO se puede tocar la orden, avisos de lo que hay que revisar)."""
    atada = ordenes_db.ataduras(fila["id"])
    if atada["muestras"] or atada["resultados"]:
        return ("La orden ya tiene muestras o resultados cargados en el laboratorio: "
                f"no se modifica desde acá. {_SIN_MOVER}"), []
    avisos = []
    if not fila_pedido:
        return None, avisos
    if fila_pedido.get("status") == "abierto":
        # El agente lleva las órdenes del pedido abierto en la sesión del chat y al cerrarlo
        # factura con eso: tocarlo desde acá dejaría el borrador con lo que se borró.
        return ("El pedido sigue abierto en el chat del cliente. Ciérralo (o espera a que "
                "se cierre) y después modifica la orden."), []
    pagos = ordenes_db.pagos(fila_pedido["id"])
    if any(p.get("status") == "approved" for p in pagos):
        return ("El pedido ya fue pagado en línea: no se modifica desde acá. "
                "La devolución o el ajuste lo gestiona Contabilidad."), []
    if any(p.get("status") == "pending" for p in pagos):
        avisos.append("El cliente tiene un link de pago pendiente por el monto anterior.")
    factura = fila_pedido.get("alegra_invoice_id")
    if factura:
        estado = _estado_factura(str(factura))
        if estado is None:
            return "No pude verificar en Alegra el estado de la factura del pedido. Intenta de nuevo en un momento.", []
        if estado in _FACTURA_VIVA:
            return (f"La factura {factura} del pedido ya fue emitida: no se modifica desde acá. "
                    "Se corrige con una nota crédito en Alegra."), []
        if estado == "draft":
            avisos.append(f"El borrador {factura} de Alegra ya tenía cargado esto: "
                          "corrígelo allá, la plataforma no modifica Alegra.")
    return None, avisos


def _orden_del_pedido():
    """(fila, pedido, respuesta de error) de la orden que viene en el pedido HTTP."""
    datos = request.get_json(silent=True) or request.args
    request_id = str(datos.get("request_id") or "").strip()
    if not request_id:
        return None, None, (jsonify({"error": "Falta la orden"}), 400)
    fila = ordenes_db.orden(request_id)
    if not fila:
        return None, None, (jsonify({"error": "Esa orden ya no existe"}), 404)
    return fila, ordenes_db.pedido(fila.get("pedido_id")), None


@dashboard_ordenes.get("/api/dashboard/order-lines")
@_login_required
def order_lines():
    try:
        fila, _pedido, error = _orden_del_pedido()
        if error:
            return error
        evento = ordenes_db.evento_creacion(fila["id"]) or {}
        lineas = orden_edicion.lineas((evento.get("event_payload") or {}).get("profile"))
    except Exception:  # noqa: BLE001
        log.exception("ordenes: no se pudieron leer las líneas")
        return jsonify({"error": "No se pudieron leer los análisis de la orden"}), 503
    return jsonify({"ok": True, "order_number": fila.get("order_number"), "lines": lineas,
                    "total": sum(linea["price"] for linea in lineas)})


@dashboard_ordenes.post("/api/dashboard/order-line-delete")
@_login_required
def order_line_delete():
    datos = request.get_json(silent=True) or {}
    try:
        fila, fila_pedido, error = _orden_del_pedido()
        if error:
            return error
        freno, avisos = revisar(fila, fila_pedido)
        if freno:
            return jsonify({"error": freno}), 409
        evento = ordenes_db.evento_creacion(fila["id"])
        perfil = ((evento or {}).get("event_payload") or {}).get("profile")
        antes = orden_edicion.lineas(perfil)
        indice = int(datos.get("index", -1))
        # El código confirma que la línea sigue siendo la que la persona vio en pantalla.
        if not 0 <= indice < len(antes) or antes[indice]["code"] != str(datos.get("code") or ""):
            return jsonify({"error": "La orden cambió: recarga la página y vuelve a intentarlo."}), 409
        nuevo, quitada = orden_edicion.quitar(perfil, indice)
        etiqueta = orden_edicion.etiqueta(fila.get("exam_type"), antes, indice, nuevo)
        usuario = audit_db.usuario_actual()
        ordenes_db.respaldar(fila["id"], "update", {
            "accion": "quitar análisis", "quitado": quitada, "perfil_antes": perfil,
            "exam_type_antes": fila.get("exam_type")}, usuario)
        ordenes_db.guardar_perfil(fila["id"], evento, nuevo, etiqueta)
        db.create_request_event(fila["id"], "dashboard_line_removed", {
            "quitado": quitada, "total": nuevo["total_estimated"], "updated_by": usuario})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:  # noqa: BLE001
        log.exception("ordenes: no se pudo quitar el análisis")
        return jsonify({"error": "No se pudo quitar el análisis"}), 503
    return jsonify({"ok": True, "quitado": quitada, "total": nuevo["total_estimated"], "avisos": avisos})


@dashboard_ordenes.post("/api/dashboard/order-delete")
@_login_required
def order_delete():
    try:
        fila, fila_pedido, error = _orden_del_pedido()
        if error:
            return error
        freno, avisos = revisar(fila, fila_pedido)
        if freno:
            return jsonify({"error": freno}), 409
        if fila.get("assigned_courier_id") and fila.get("status") in ("assigned", "on_route"):
            nombre = (fila.get("couriers") or {}).get("name") or "El motorizado"
            avisos.append(f"{nombre} ya tenía esta recogida asignada: avísale que no pase.")
        ordenes_db.respaldar(fila["id"], "delete", ordenes_db.foto(fila, fila_pedido),
                             audit_db.usuario_actual())
        sin_pedido = ordenes_db.borrar(fila["id"], fila_pedido)
    except Exception:  # noqa: BLE001
        log.exception("ordenes: no se pudo eliminar la orden")
        return jsonify({"error": "No se pudo eliminar la orden"}), 503
    return jsonify({"ok": True, "order_number": fila.get("order_number"),
                    "pedido_eliminado": sin_pedido, "avisos": avisos})
