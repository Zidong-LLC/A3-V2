"""Aplicar un plan de carga masiva ya confirmado por una persona.

Cada fila va por separado: que una reviente (NIT o teléfono duplicado, restricción de
la tabla) no cancela las demás. Con la lista real de terceros v3, un teléfono repetido a
mitad de la carga dejó 17 altas hechas y todo lo demás sin aplicar.

El plan vuelve del navegador en un campo oculto: acá solo pasan las columnas que cada
carga puede tocar y se revalidan precio, categoría y especie (auditoría 2026-10-19).
"""
from app.imports import CAMPOS_CLIENTE, especie, norm, precio_valido
from app.services import audit_db, db

_CAMPOS_ALTA = ("clinic_name",) + CAMPOS_CLIENTE
_TABLAS = ("catalog_tests", "catalog_profiles")


def _solo(datos: dict | None, campos) -> dict:
    return {k: v for k, v in (datos or {}).items() if k in campos}


def plan_motorizados(filas: list[dict], couriers: list[dict]) -> dict:
    """Motorizados nuevos (por nombre) y teléfonos que cambian en los que ya existen."""
    existentes = {norm(c.get("name")): c for c in couriers}
    nuevos, cambios, errores, vistos, iguales = [], [], [], set(), 0
    for numero, fila in enumerate(filas, start=2):
        nombre, telefono = (fila.get("name") or "").strip(), (fila.get("phone") or "").strip()
        clave = norm(nombre)
        if not nombre:
            errores.append(f"Fila {numero}: sin nombre")
            continue
        if clave in vistos:
            errores.append(f"Fila {numero}: «{nombre}» viene repetido en el archivo")
            continue
        vistos.add(clave)
        actual = existentes.get(clave)
        if not actual and not telefono:  # la tabla exige teléfono: el alta fallaba al aplicar
            errores.append(f"Fila {numero}: «{nombre}» es nuevo y le falta el teléfono")
        elif not actual:
            nuevos.append({"name": nombre, "phone": telefono})
        elif telefono and telefono != (actual.get("phone") or ""):
            cambios.append({"id": actual["id"], "clinic_name": actual.get("name"),
                            "cambios": {"phone": telefono}, "antes": {"phone": actual.get("phone")}})
        else:
            iguales += 1
    return {"tipo": "motorizados", "crear": nuevos, "actualizar": cambios, "iguales": iguales,
            "errores": errores}


def motivo(exc: Exception) -> str:
    """El mensaje útil del error de la base, sin el JSON completo."""
    texto = str(getattr(exc, "message", "") or exc)
    if "clients_phone_key" in texto:
        return "el teléfono ya pertenece a otro cliente"
    if "duplicate key" in texto:
        return "ya existía un registro con esa clave"
    return texto[:120]


def aplicar_precios(cambios: list[dict], quien: str) -> tuple[int, list[str]]:
    hechos, fallidos = 0, []
    for cambio in cambios:
        tabla, code = cambio.get("tabla"), str(cambio.get("code") or "")
        nuevo = precio_valido(cambio.get("despues"))
        if tabla not in _TABLAS or nuevo is None:
            fallidos.append(f"{code}: tabla o precio inválido")
            continue
        try:
            antes = db.get_catalog_item(tabla, code)
            if not antes:
                fallidos.append(f"{code}: ya no existe en el catálogo")
                continue
            despues = db.update_catalog_item(tabla, code, {"price": nuevo})
            if not despues:
                fallidos.append(f"{code}: no se pudo actualizar")
                continue
            db.log_catalog_change(tabla, code, antes, despues, quien)
        except Exception as exc:  # noqa: BLE001 — se informa por fila
            fallidos.append(f"{code}: {motivo(exc)}")
            continue
        hechos += 1
    return hechos, fallidos


def aplicar_portafolio(nuevos: list[dict], quien: str) -> tuple[int, list[str]]:
    hechos, fallidos = 0, []
    for item in nuevos:
        tabla, code = item.get("tabla"), str(item.get("code") or "")
        payload = {"code": code, "name": str(item.get("name") or "").strip(),
                   "price": precio_valido(item.get("price")),
                   "category": str(item.get("category") or "").strip(), "species": especie(item.get("species"))}
        if tabla not in _TABLAS or not all(payload.values()):
            fallidos.append(f"{code}: faltan nombre, precio, categoría o especie válidos")
            continue
        if tabla == "catalog_tests":
            payload["sample"] = item.get("sample")
        try:
            if db.get_catalog_item(tabla, code):
                fallidos.append(f"{code}: ya existía, no se pisa")
                continue
            creado = db.create_catalog_item(tabla, payload)
            if not creado:
                fallidos.append(f"{code}: no se pudo crear")
                continue
            db.log_catalog_change(tabla, code, {}, creado, quien)
        except Exception as exc:  # noqa: BLE001
            fallidos.append(f"{code}: {motivo(exc)}")
            continue
        hechos += 1
    return hechos, fallidos


def aplicar_clientes(plan: dict) -> tuple[int, int, list[str]]:
    creados, actualizados, fallidos, historial = 0, 0, [], []
    for nuevo in plan.get("crear") or []:
        datos = _solo(nuevo, _CAMPOS_ALTA)
        try:
            hecho = db.create_client(datos)
        except Exception as exc:  # noqa: BLE001 — se informa por fila
            hecho = None
            fallidos.append(f"{nuevo.get('clinic_name')}: {motivo(exc)}")
        else:
            if not hecho:
                fallidos.append(f"{nuevo.get('clinic_name')}: no se pudo crear")
        if hecho and isinstance(hecho, dict) and hecho.get("id"):
            if nuevo.get("courier_id"):
                db.upsert_client_assignment(hecho["id"], nuevo["courier_id"], "carga_masiva")
            historial.append((hecho["id"], "create", {"origen": "carga masiva", **datos}))
        creados += 1 if hecho else 0
    for cambio in plan.get("actualizar") or []:
        client_id = cambio.get("id")
        bruto = dict(cambio.get("cambios") or {})
        courier_id = bruto.pop("courier_id", None)
        datos = _solo(bruto, CAMPOS_CLIENTE)
        if not client_id:
            continue
        try:
            ok = db.update_client_profile(client_id, datos) if datos else True
            if courier_id:
                db.upsert_client_assignment(client_id, courier_id, "carga_masiva")
            if ok:
                actualizados += 1
                antes = cambio.get("antes") or {}
                historial.append((client_id, "update", {
                    "origen": "carga masiva", **({"courier_id": courier_id} if courier_id else {}),
                    **{c: {"antes": antes.get(c), "despues": v} for c, v in datos.items()}}))
            else:
                fallidos.append(f"{cambio.get('clinic_name')}: el cliente ya no existe")
        except Exception as exc:  # noqa: BLE001
            fallidos.append(f"{cambio.get('clinic_name')}: {motivo(exc)}")
    audit_db.registrar_lote("client", historial)
    return creados, actualizados, fallidos


def aplicar_motorizados(plan: dict) -> tuple[int, int, list[str]]:
    creados, actualizados, fallidos = 0, 0, []
    for nuevo in plan.get("crear") or []:
        datos = {"name": str(nuevo.get("name") or "").strip(), "phone": nuevo.get("phone"),
                 "availability": "available"}
        try:
            hecho = db.create_courier(datos)
        except Exception as exc:  # noqa: BLE001
            hecho = None
            fallidos.append(f"{nuevo.get('name')}: {motivo(exc)}")
        if hecho:
            creados += 1
            audit_db.registrar("courier", hecho.get("id") if isinstance(hecho, dict) else "", "create", datos)
    for cambio in plan.get("actualizar") or []:
        datos = _solo(cambio.get("cambios"), ("phone",))
        if not cambio.get("id") or not datos:
            continue
        try:
            ok = db.update_courier(cambio["id"], datos)
        except Exception as exc:  # noqa: BLE001
            fallidos.append(f"{cambio.get('clinic_name')}: {motivo(exc)}")
            continue
        if ok:
            actualizados += 1
            audit_db.registrar("courier", cambio["id"], "update", datos)
        else:
            fallidos.append(f"{cambio.get('clinic_name')}: no se pudo actualizar")
    return creados, actualizados, fallidos
