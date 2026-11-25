"""Cobro de un pedido desde la pantalla de Pedidos: link de pago en línea y emisión.

- Link de pago: los pedidos del chat reciben su link al cerrar; los del portal y los cargados
  a mano lo reciben al crearse. Este botón cubre el resto (un pedido que quedó sin link, o el
  cliente que perdió el mensaje): devuelve el link vigente o crea uno.
- Emitir: ver `app/emision.py`. Es de quien gestiona Facturación; recepción arma borradores
  pero no emite.
- Modo de emisión (decisión 017): manual, automática solo para clientes elegidos o para todos.
  Lo elige A3 en Facturación; lo guarda `emision_ajustes_db`.
El permiso por perfil de las rutas lo controla `app/access.py` antes de llegar acá.
"""
import logging
import uuid

from flask import Blueprint, flash, jsonify, redirect, request, url_for

from app import access, emision, pagos
from app import permissions as P
from app.services import audit_db, db, emision_ajustes_db, pagos_db

log = logging.getLogger(__name__)
dashboard_cobro = Blueprint("dashboard_cobro", __name__)
_login_required = access.login_requerido


def _pedido():
    pedido_id = str((request.get_json(silent=True) or {}).get("pedido_id") or "").strip()
    return db.get_pedido(pedido_id) if pedido_id else None


@dashboard_cobro.post("/api/dashboard/pedido-pago-link")
@_login_required
def pedido_pago_link():
    pedido = _pedido()
    if not pedido:
        return jsonify({"error": "El pedido no existe"}), 404
    if pedido.get("status") == "abierto":
        return jsonify({"error": "El pedido sigue abierto: el link se arma al cerrarlo."}), 409
    try:
        pago = pagos_db.por_pedidos([pedido["id"]]).get(pedido["id"])
        if pago and pago.get("status") == "approved":
            return jsonify({"error": "Ese pedido ya está pagado."}), 409
        if pago and pago.get("status") == "pending":
            return jsonify({"ok": True, "url": pago["url"], "nuevo": False})
        total = sum(int(p.get("total_estimated") or 0) for p in db.get_pedido_profiles(pedido["id"]))
        cliente = (db.get_client_by_id(pedido.get("client_id")) or {}).get("clinic_name") or ""
        url = pagos.link_para_pedido(pedido["id"], total, cliente)
    except Exception:  # noqa: BLE001
        log.exception("cobro: no se pudo armar el link del pedido %s", pedido.get("id"))
        return jsonify({"error": "No se pudo crear el link de pago"}), 503
    if not url:
        return jsonify({"error": "No se pudo crear el link: el pago en línea está apagado, el pedido "
                                 "no tiene valor o el cliente no está habilitado todavía."}), 409
    return jsonify({"ok": True, "url": url, "nuevo": True})


@dashboard_cobro.post("/api/dashboard/pedido-emitir")
@_login_required
def pedido_emitir():
    if not P.puede(access.perfil_actual(), "facturacion", P.GESTION):
        return jsonify({"error": "Emitir es de quien gestiona Facturación."}), 403
    resultado = emision.emitir(_pedido())
    if not resultado["ok"]:
        return jsonify({"error": resultado["error"]}), resultado["codigo"]
    return jsonify(resultado)


def _ids_validos(valores: list[str]) -> list[str]:
    salida = []
    for valor in valores:
        try:
            limpio = str(uuid.UUID(str(valor).strip()))
        except ValueError:
            continue
        if limpio not in salida:
            salida.append(limpio)
    return salida


@dashboard_cobro.post("/facturacion/emision")
@_login_required
def emision_ajustes():
    """Guarda a quién se le emite la factura automáticamente. Exige gestionar Facturación
    (lo controla `app/access.py`: es un POST)."""
    modo = (request.form.get("modo") or "").strip()
    ids = _ids_validos(request.form.getlist("client_ids"))
    if modo not in emision_ajustes_db.MODOS:
        flash("Elegí una de las tres opciones.", "emision_error")
    elif modo == "clientes" and not ids:
        flash("Para la emisión automática por cliente, agregá al menos un cliente.", "emision_error")
    else:
        try:
            emision_ajustes_db.guardar(modo, ids if modo == "clientes" else [], audit_db.usuario_actual())
            audit_db.registrar("emision_ajustes", 1, "update",
                               {"modo": modo, "clientes": ids if modo == "clientes" else []})
            flash("Modo de emisión guardado.", "emision_ok")
        except Exception:  # noqa: BLE001
            log.exception("emision_ajustes: no se pudo guardar")
            flash("No se pudo guardar. Intenta de nuevo en un momento.", "emision_error")
    return redirect(url_for("dashboard.billing_page") + "#emision")
