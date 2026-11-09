"""Sacar UN análisis de una orden ya registrada (pedido de A3, 2026-11-09: «se pidieron dos
de más»).

Trabaja sobre el `profile` que guardó `db.create_request` —el mismo que después factura
`billing.build_invoice_lines`— y conserva los precios con los que se cotizó: no vuelve a
leer el catálogo. Las líneas salen en el orden en que se facturan. Lógica pura, sin I/O.
"""
from app.rules import calculate_custom_profile_total, calculate_profile_adjusted_total

PERFIL, ADICIONAL, ANALISIS = "Perfil", "Perfil adicional", "Análisis"


def _precio(item: dict) -> int:
    return int((item or {}).get("price") or 0)


def _linea(tipo: str, item: dict, precio: int | None = None) -> dict:
    return {"tipo": tipo, "code": str(item.get("code") or ""), "name": item.get("name") or "",
            "price": _precio(item) if precio is None else precio}


def lineas(profile: dict | None) -> list[dict]:
    """[{tipo, code, name, price}]. El «Perfil personalizado (N análisis)» sin código ni
    precio no es una línea: es solo el rótulo de un grupo de análisis sueltos."""
    profile = profile or {}
    base = profile.get("base_profile") or {}
    salida = []
    if base.get("code") or _precio(base) > 0:
        neto = max(_precio(base) - sum(_precio(t) for t in profile.get("removed_tests") or []), 0)
        salida.append(_linea(PERFIL, base, neto))
    salida += [_linea(ADICIONAL, p) for p in profile.get("extra_profiles") or []]
    salida += [_linea(ANALISIS, t) for t in profile.get("added_tests") or []]
    return salida


def quitar(profile: dict, indice: int) -> tuple[dict, dict]:
    """(perfil sin esa línea y con el total recalculado, línea quitada). ValueError con el
    motivo si la línea no existe o es la única que le queda a la orden."""
    actuales = lineas(profile)
    if not 0 <= indice < len(actuales):
        raise ValueError("Ese análisis ya no está en la orden.")
    if len(actuales) == 1:
        raise ValueError("Es el único análisis de la orden: para sacarlo, elimina la orden.")
    quitada = actuales[indice]
    base = dict(profile.get("base_profile") or {})
    extras = list(profile.get("extra_profiles") or [])
    sueltos = list(profile.get("added_tests") or [])
    removidos = list(profile.get("removed_tests") or [])
    incluidos = list(profile.get("included_tests") or [])
    corrimiento = 1 if actuales[0]["tipo"] == PERFIL else 0

    if quitada["tipo"] == PERFIL:
        # Se va el perfil base: el primer adicional ocupa su lugar; sin adicionales la
        # orden queda como análisis sueltos. Lo «removido» era de ese perfil: se va con él.
        base = dict(extras.pop(0)) if extras else {"code": None, "name": None, "price": 0}
        removidos, incluidos = [], []
    elif quitada["tipo"] == ADICIONAL:
        extras.pop(indice - corrimiento)
    else:
        sueltos.pop(indice - corrimiento - len(extras))

    if not base.get("code") and not _precio(base) and sueltos:
        # Mismo criterio que `db._profile_event_payload`: análisis sueltos llevan el
        # descuento por volumen, que cambia al cambiar la cantidad.
        base["name"] = f"Perfil personalizado ({len(sueltos)} análisis)"
        suelto = calculate_custom_profile_total(sueltos)
        totales = {"base": 0, "added": suelto["subtotal"], "removed": 0, "subtotal": suelto["subtotal"],
                   "volume_discount": suelto["discount"], "total": suelto["total"]}
    else:
        totales = calculate_profile_adjusted_total(
            _precio(base), [_precio(t) for t in sueltos] + [_precio(p) for p in extras],
            [_precio(t) for t in removidos])
    nuevo = {**profile, "base_profile": base, "extra_profiles": extras, "added_tests": sueltos,
             "removed_tests": removidos, "included_tests": incluidos,
             "total_estimated": totales["total"], "price_adjustment": totales}
    return nuevo, quitada


def etiqueta(anterior: str | None, antes: list[dict], indice: int, nuevo: dict) -> str:
    """El texto de la columna Análisis después de quitar la línea `indice`."""
    partes = [p for p in (anterior or "").split(", ") if p]
    if len(partes) == len(antes):  # formulario: un nombre por línea y en el mismo orden
        return ", ".join(p for i, p in enumerate(partes) if i != indice)
    base = nuevo.get("base_profile") or {}
    if not base.get("code") or antes[indice]["tipo"] == PERFIL:
        return base.get("name") or anterior or ""  # chat: el rótulo del perfil
    return anterior or ""
