"""Lo que «Nueva Orden» le suma a recepción (pedido de A3, 2026-11-09).

- CONTRAMUESTRA: una segunda muestra para confirmar el resultado de un examen. Se recoge
  como cualquier orden pero NO se factura: no abre pedido, no guarda precios y queda
  rotulada en el análisis y en las observaciones (sin tocar el modelo de datos).
- RECOLECCIÓN EFECTIVA: hay clientes que no programan ruta porque el motorizado siempre
  pasa en su recorrido y recoge lo que haya. Recepción la registra después, ya recogida,
  para llevar el control; se factura como cualquier orden.

Lógica pura, sin I/O: el formulario decide con esto qué guarda `db.create_request`.
"""
from datetime import date, datetime

from app.config import APP_TIMEZONE

ROTULO = "Contramuestra"
NOTA = "CONTRAMUESTRA: no se factura."
NOTA_RECOLECCION = "Recolección efectiva sin ruta programada, registrada en recepción"
# Todo lo que haría que la orden lleve un precio: una contramuestra no se cobra.
_CON_PRECIO = frozenset({"_selected_profile_code", "_selected_profile_name", "_selected_profile_price",
                         "_selected_profile_description", "_extra_profiles", "selected_tests"})


def es_contramuestra(exam_type) -> bool:
    return str(exam_type or "").startswith(ROTULO)


def como_contramuestra(fields: dict) -> dict:
    """Los mismos datos sin nada que lleve precio: lo elegido queda solo como texto."""
    limpio = {k: v for k, v in fields.items() if k not in _CON_PRECIO}
    elegido = (fields.get("exam_type") or "").strip()
    limpio["exam_type"] = f"{ROTULO}: {elegido}" if elegido else ROTULO
    obs = (fields.get("observations") or "").strip()
    limpio["observations"] = NOTA if obs in ("", "sin observaciones") else f"{NOTA} {obs}"
    return limpio


def recoleccion(fecha_txt: str | None, courier_id: str | None, asignado_id: str | None,
                hoy: date | None = None) -> tuple[dict | None, str | None]:
    """(columnas de una orden que nace YA recogida, None) o (None, error para el formulario)."""
    hoy = hoy or datetime.now(APP_TIMEZONE).date()
    texto = (fecha_txt or "").strip()
    try:
        fecha = date.fromisoformat(texto) if texto else hoy
    except ValueError:
        return None, "La fecha de recolección no es válida."
    if fecha > hoy:
        return None, "La fecha de recolección no puede ser futura: para eso se programa la recogida."
    quien = (courier_id or "").strip() or (asignado_id or "")
    if not quien:
        return None, "Elige el motorizado que hizo la recolección."
    return {"status": "picked_up", "assigned_courier_id": quien,
            "scheduled_pickup_date": fecha.isoformat(), "fallback_reason": None}, None
