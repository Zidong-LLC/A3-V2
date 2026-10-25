"""Administración de datos maestros: ficha editable del cliente, baja y traslado de
motorizados (también el reemplazo de un día o una zona) e historial de cambios.
El permiso por perfil lo controla `app/access.py` antes de llegar acá."""
from datetime import date

from flask import Blueprint, jsonify, request

from app import access, municipios
from app import permissions as P
from app.courier_notify import notify_assignment
from app.services import audit_db, db, maestros_db

dashboard_maestros = Blueprint("dashboard_maestros", __name__)

_TEXTO = {"clinic_name": 180, "tax_id": 30, "phone": 40, "address": 300, "zone": 20, "city": 80,
          "email": 160}
# Cada historial lo ve quien puede ver su módulo: el de usuarios, solo el Administrador.
_ENTIDADES = {"client": "clientes", "courier": "motorizados", "catalog": "precios", "user": "usuarios"}


_login_required = access.login_requerido


def _cambios_cliente(crudos: dict) -> dict:
    cambios = {}
    for campo, largo in _TEXTO.items():
        if campo in crudos:
            cambios[campo] = str(crudos.get(campo) or "").strip()[:largo] or None
    for campo in ("is_active", "electronic_invoice"):
        if campo in crudos:
            cambios[campo] = crudos.get(campo) is True or str(crudos.get(campo)).lower() in ("true", "on", "si")
    if crudos.get("billing_type") in ("credit", "cash"):
        cambios["billing_type"] = crudos["billing_type"]
    return cambios


@dashboard_maestros.post("/api/dashboard/client-ficha")
@_login_required
def client_ficha():
    payload = request.get_json(silent=True) or {}
    client_id = str(payload.get("client_id") or "").strip()
    cliente = maestros_db.get_client_any(client_id) if client_id else None
    if not cliente:
        return jsonify({"error": "Cliente no encontrado"}), 404
    cambios = _cambios_cliente(payload.get("cambios") or {})
    if cambios.get("clinic_name") is None and "clinic_name" in cambios:
        return jsonify({"error": "El nombre de la veterinaria no puede quedar vacío"}), 400
    reales = {k: v for k, v in cambios.items() if cliente.get(k) != v}
    if reales and not maestros_db.actualizar_cliente(client_id, reales):
        return jsonify({"error": "No se pudo guardar"}), 503
    if "courier_id" in (payload.get("cambios") or {}):
        courier = str(payload["cambios"].get("courier_id") or "").strip() or None
        db.upsert_client_assignment(client_id=client_id, courier_id=courier,
                                    assigned_by=f"dashboard:{audit_db.usuario_actual()}")
        reales["motorizado"] = courier
    if reales:
        accion = ("activate" if reales.get("is_active") else "deactivate") if list(reales) == ["is_active"] else "update"
        audit_db.registrar("client", client_id, accion,
                           {k: {"antes": cliente.get(k), "despues": v} for k, v in reales.items()})
    return jsonify({"ok": True, "cambios": reales})


@dashboard_maestros.post("/api/dashboard/courier-delete")
@_login_required
def courier_delete():
    courier_id = str((request.get_json(silent=True) or {}).get("courier_id") or "").strip()
    courier = db.get_courier(courier_id) if courier_id else None
    if not courier:
        return jsonify({"error": "Motorizado no encontrado"}), 404
    historia = maestros_db.historia_motorizado(courier_id)
    if historia["clientes"] or historia["localidades"] or historia["zonas"]:
        return jsonify({"error": "Primero traslada sus clientes, localidades y zonas a otro motorizado.",
                        "historia": historia}), 409
    if historia["recogidas"]:
        return jsonify({"error": "Tiene recogidas registradas: no se elimina para conservar la historia. "
                                 "Desactívalo con la casilla «Activo».", "historia": historia}), 409
    if not maestros_db.eliminar_motorizado(courier_id):
        return jsonify({"error": "No se pudo eliminar"}), 503
    audit_db.registrar("courier", courier_id, "delete", {"name": courier.get("name")})
    return jsonify({"ok": True})


@dashboard_maestros.post("/api/dashboard/courier-transfer")
@_login_required
def courier_transfer():
    p = request.get_json(silent=True) or {}
    origen, destino = str(p.get("origen") or "").strip(), str(p.get("destino") or "").strip()
    if not origen or not destino or origen == destino:
        return jsonify({"error": "Elige dos motorizados distintos"}), 400
    destino_row = db.get_courier(destino)
    if not db.get_courier(origen) or not destino_row:
        return jsonify({"error": "Motorizado no encontrado"}), 404
    modo = p.get("recogidas") or "ninguna"
    fecha = str(p.get("fecha") or "").strip()[:10] or None
    if modo == "dia":
        try:
            date.fromisoformat(fecha or "")
        except ValueError:
            return jsonify({"error": "Elige la fecha del reemplazo"}), 400
    recogidas = [] if modo == "ninguna" else maestros_db.recogidas_pendientes(
        origen, fecha if modo == "dia" else None, str(p.get("zona") or "").strip() or None)
    historia = maestros_db.historia_motorizado(origen)
    plan = {"clientes": historia["clientes"] if p.get("clientes") else 0,
            "localidades": historia["localidades"] if p.get("localidades") else 0,
            "zonas": historia["zonas"] if p.get("localidades") else 0,
            "recogidas": len(recogidas)}
    if not p.get("confirmar"):
        return jsonify({"ok": True, "plan": plan, "destino": destino_row.get("name")})
    hecho = maestros_db.trasladar(origen, destino, bool(p.get("clientes")), bool(p.get("localidades")),
                                  [r["id"] for r in recogidas])
    avisos = sum(bool(notify_assignment(destino, order_number=r.get("order_number") or "",
                                        clinic=(r.get("clients") or {}).get("clinic_name") or "",
                                        address=r.get("pickup_address") or "",
                                        fecha=r.get("scheduled_pickup_date") or "", reasignada=True))
                 for r in recogidas)
    audit_db.registrar("courier", origen, "transfer", {"destino": destino, "modo": modo, "fecha": fecha,
                                                       "zona": p.get("zona") or None, **hecho})
    return jsonify({"ok": True, "hecho": hecho, "avisos": avisos})


@dashboard_maestros.get("/api/dashboard/historial")
@_login_required
def historial():
    entidad, entity_id = request.args.get("entidad", ""), request.args.get("id", "")
    if entidad not in _ENTIDADES or not entity_id:
        return jsonify({"error": "Pedido inválido"}), 400
    if not P.puede(access.perfil_actual(), _ENTIDADES[entidad]):
        return jsonify({"error": "Tu perfil no tiene permiso para esta acción."}), 403
    return jsonify({"ok": True, "cambios": audit_db.listar(entidad, entity_id)})


@dashboard_maestros.post("/api/dashboard/municipio")
@_login_required
def municipio():
    """Agrega (o reactiva) un municipio en la cobertura. Las coordenadas salen de la lista
    de la Sabana; uno que no esté ahí se lista igual, sin punto en el mapa."""
    p = request.get_json(silent=True) or {}
    nombre = " ".join(str(p.get("nombre") or "").split())[:60]
    if len(nombre) < 3:
        return jsonify({"error": "Escribe el nombre del municipio"}), 400
    lat, lng = municipios.coordenadas(nombre)
    activo = p.get("activo", True) is not False
    fila = maestros_db.guardar_municipio(municipios.codigo(nombre), nombre, lat, lng, activo)
    if not fila:
        return jsonify({"error": "No se pudo guardar"}), 503
    audit_db.registrar("courier", "", "update", {"municipio": nombre, "activo": activo})
    return jsonify({"ok": True, "municipio": fila, "en_mapa": lat is not None})
