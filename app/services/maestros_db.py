"""Clientes y motorizados: borrado seguro, desactivación y traslados.

Regla de borrado (cierre de la versión 1): un registro creado por error y sin movimientos
se puede eliminar; si ya tiene solicitudes, pedidos, muestras, resultados o facturas, se
desactiva y conserva su historia. Un motorizado con clientes, localidades o recogidas a
su cargo se traslada primero a otro.
"""
from app.imports import norm
from app.services.db import _client

PENDIENTES = ("received", "assigned", "error_pending_assignment")


def _contar(tabla: str, columna: str, valor) -> int:
    r = _client.table(tabla).select("*", count="exact").eq(columna, valor).limit(1).execute()
    return r.count or 0


def get_client_any(client_id: str) -> dict | None:
    """Cliente activo o inactivo (la ficha tiene que poder reactivarlo)."""
    filas = _client.table("clients").select("*").eq("id", client_id).limit(1).execute().data
    return filas[0] if filas else None


def courier_de_cliente(client_id: str) -> str | None:
    """Motorizado fijo del cliente, solo lectura (get_courier_for_client puede auto-asignar)."""
    filas = (_client.table("client_courier_assignment").select("courier_id")
             .eq("client_id", client_id).limit(1).execute().data)
    return (filas[0].get("courier_id") if filas else None) or None


def historia_cliente(cliente: dict) -> dict:
    cid = cliente["id"]
    historia = {"solicitudes": _contar("requests", "client_id", cid),
                "pedidos": _contar("pedidos", "client_id", cid),
                "muestras": _contar("lab_samples", "client_id", cid),
                "resultados": _contar("lab_results", "client_id", cid), "facturas": 0}
    nit = "".join(c for c in (cliente.get("tax_id") or "").split("-")[0] if c.isdigit())
    if len(nit) >= 5:
        r = (_client.table("invoices_cache").select("*", count="exact")
             .ilike("client_nit", f"{nit}%").limit(1).execute())
        historia["facturas"] = r.count or 0
    return historia


def actualizar_cliente(client_id: str, cambios: dict) -> bool:
    return bool(_client.table("clients").update(cambios).eq("id", client_id).execute().data)


def historia_motorizado(courier_id: str) -> dict:
    return {"recogidas": _contar("requests", "assigned_courier_id", courier_id),
            "clientes": _contar("client_courier_assignment", "courier_id", courier_id),
            "localidades": _contar("courier_locality_coverage", "courier_id", courier_id),
            "zonas": _contar("territorial_zones", "courier_id", courier_id)}


def eliminar_motorizado(courier_id: str) -> bool:
    return bool(_client.table("couriers").delete().eq("id", courier_id).execute().data)


def recogidas_pendientes(courier_id: str, fecha: str | None = None, zona: str | None = None) -> list[dict]:
    """Recogidas sin recoger de un motorizado; con fecha, solo las de ese día; con zona,
    solo las de clientes de esa zona o municipio."""
    q = (_client.table("requests")
         .select("id, order_number, scheduled_pickup_date, pickup_address, clients(clinic_name, zone, city)")
         .eq("assigned_courier_id", courier_id).in_("status", list(PENDIENTES)))
    if fecha:
        q = q.eq("scheduled_pickup_date", fecha)
    filas = q.limit(1000).execute().data or []
    if zona:  # sin tildes ni mayúsculas: «Bogota» del formulario es la «Bogotá» del cliente
        clave = norm(zona)
        filas = [f for f in filas if clave in {norm(str((f.get("clients") or {}).get("zone") or "").split(".")[0]),
                                                norm((f.get("clients") or {}).get("city"))}]
    return filas


def trasladar(origen: str, destino: str, clientes: bool, localidades: bool, recogidas: list[str]) -> dict:
    hecho = {"clientes": 0, "localidades": 0, "zonas": 0, "recogidas": 0}
    if clientes:
        hecho["clientes"] = len(_client.table("client_courier_assignment").update({"courier_id": destino})
                                .eq("courier_id", origen).execute().data or [])
    if localidades:
        hecho["localidades"] = len(_client.table("courier_locality_coverage").update({"courier_id": destino})
                                   .eq("courier_id", origen).execute().data or [])
        nuevo = (_client.table("couriers").select("name, phone").eq("id", destino).limit(1).execute().data or [{}])[0]
        hecho["zonas"] = len(_client.table("territorial_zones").update(
            {"courier_id": destino, "courier_name": nuevo.get("name"), "courier_phone": nuevo.get("phone")})
            .eq("courier_id", origen).execute().data or [])
    if recogidas:
        hecho["recogidas"] = len(_client.table("requests").update({"assigned_courier_id": destino})
                                 .in_("id", recogidas).execute().data or [])
    return hecho


def asignaciones() -> dict:
    """Motorizado fijo de cada cliente ({client_id: courier_id}), paginando de a 1000."""
    mapa, desde = {}, 0
    while True:
        filas = (_client.table("client_courier_assignment").select("client_id, courier_id")
                 .range(desde, desde + 999).execute().data or [])
        mapa.update({f["client_id"]: f["courier_id"] for f in filas if f.get("client_id")})
        if len(filas) < 1000:
            return mapa
        desde += 1000


def list_municipios(solo_activos: bool = False) -> list[dict]:
    q = _client.table("coverage_municipalities").select("code, name, lat, lng, is_active").order("name")
    if solo_activos:
        q = q.eq("is_active", True)
    return q.execute().data or []


def guardar_municipio(code: str, nombre: str, lat, lng, activo: bool = True) -> dict | None:
    fila = {"code": code, "name": nombre, "lat": lat, "lng": lng, "is_active": activo}
    datos = _client.table("coverage_municipalities").upsert(fila, on_conflict="code").execute().data
    return datos[0] if datos else None
