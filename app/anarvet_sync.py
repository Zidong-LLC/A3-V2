"""Sync del espejo de resultados Anarvet → Supabase (Fase 1, decisión 013).

Vuelca fn_reporte_examenes(desde, hasta) en la tabla anarvet_results y registra los
cod_cliente vistos en anarvet_client_map. Solo se dispara a mano desde el dashboard:
el proyecto no tiene scheduler y el disparo oportunista tocaría el camino del chat,
prohibido en esta fase. Patrón calcado de _sync_invoices_from_alegra (dashboard.py):
errores parciales se acumulan en `errors`, nunca revientan el sync entero.
"""

import hashlib
import logging
from datetime import datetime, timedelta

from app.config import APP_TIMEZONE
from app.services import anarvet, db

logger = logging.getLogger(__name__)

DEFAULT_SYNC_DAYS = 7
# Tope duro del rango: el smoke real midió ~3.900 analitos/día — 92 días ronda las
# 360k filas, ya bastante para un solo request; más que eso se corre en varios syncs.
MAX_RANGE_DAYS = 92
_BATCH_SIZE = 500

# Reporte → espejo. La columna "nombre" del reporte es la mascota y "examenes" es el
# código del examen; se renombran para que el espejo sea legible por sí solo.
_TEXT_FIELDS = {
    "codigo": "codigo",
    "cod_cliente": "cod_cliente",
    "nombre_cliente": "nombre_cliente",
    "nombre_propietario": "nombre_propietario",
    "nombre": "mascota",
    "especie": "especie",
    "raza": "raza",
    "genero": "genero",
    "usu_validador": "usu_validador",
    "examenes": "examen_cod",
    "analito_cod": "analito_cod",
    "analito": "analito",
    "resultado": "resultado",
}
_DATE_FIELDS = {"fechasolicitud": "fecha_solicitud", "nacio": "nacio", "fec_val": "fec_val"}


def _clean(value):
    """Normaliza un valor del reporte: los textos reales llegan con espacios y saltos
    de línea colgando ('KEIDYS REYES RIOS\\n'); las fechas van a ISO para el JSON."""
    if isinstance(value, str):
        return value.strip() or None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _row_to_mirror(row: dict) -> dict | None:
    """Mapea una fila del reporte al espejo y calcula la clave de dedupe.
    Devuelve None (y loguea) si faltan todos los componentes de la clave."""
    mapped: dict = {}
    for origen, destino in _TEXT_FIELDS.items():
        mapped[destino] = _clean(row.get(origen))
    for origen, destino in _DATE_FIELDS.items():
        mapped[destino] = _clean(row.get(origen))

    # sha1(codigo|fechasolicitud|examenes|analito_cod): excluye resultado/fec_val para
    # que una re-validación del mismo analito actualice la fila en vez de duplicarla.
    partes = (mapped["codigo"], mapped["fecha_solicitud"], mapped["examen_cod"], mapped["analito_cod"])
    if not any(partes):
        logger.warning("anarvet_sync: fila sin componentes de clave, descartada: %r", row)
        return None
    base = "|".join("" if p is None else str(p) for p in partes)
    mapped["dedup_key"] = hashlib.sha1(base.encode("utf-8")).hexdigest()
    mapped["raw"] = {k: _clean(v) for k, v in row.items()}
    return mapped


# Días que se re-piden hacia atrás además de lo nuevo. Un analito puede validarse días
# después de la solicitud, y el upsert por dedup_key hace que repetirlo sea gratis: lo
# reescribe, no lo duplica. Sin solapamiento, esas validaciones tardías nunca se verían.
_SOLAPAMIENTO_DIAS = 2


def _desde_incremental(hoy) -> str:
    """Desde dónde sincronizar: lo que sigue a lo que ya está en el espejo.

    Antes pedía siempre "los últimos 7 días" a ciegas, sin importar si el espejo estaba al
    día o vacío: traía de más cuando ya estaba cubierto, y dejaba huecos si nadie apretaba
    el botón por más de una semana. Ahora arranca en la última fecha sincronizada menos el
    solapamiento; sin espejo, mantiene el comportamiento de siempre.
    """
    ultima = None
    try:
        ultima = db.max_anarvet_fecha_solicitud()
    except Exception:  # noqa: BLE001 — sin dato, se cae al rango por defecto
        ultima = None
    if not ultima:
        return str(hoy - timedelta(days=DEFAULT_SYNC_DAYS))
    try:
        base = datetime.strptime(str(ultima)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return str(hoy - timedelta(days=DEFAULT_SYNC_DAYS))
    return str(min(base - timedelta(days=_SOLAPAMIENTO_DIAS), hoy))


def sync_results(desde: str | None = None, hasta: str | None = None) -> dict:
    """Trae el reporte del rango (default: últimos DEFAULT_SYNC_DAYS días) y hace
    upsert en el espejo. Lanza ValueError si el rango es inválido (el endpoint lo
    traduce a 400); los fallos de red/lotes van acumulados en `errors`."""
    hoy = datetime.now(APP_TIMEZONE).date()
    hasta = hasta or str(hoy)
    desde = desde or _desde_incremental(hoy)
    try:
        d_desde = datetime.strptime(desde, "%Y-%m-%d").date()
        d_hasta = datetime.strptime(hasta, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Fechas inválidas: {desde!r}..{hasta!r} (se espera AAAA-MM-DD)") from exc
    if d_desde > d_hasta:
        raise ValueError(f"Rango invertido: {desde} es posterior a {hasta}")
    if (d_hasta - d_desde).days > MAX_RANGE_DAYS:
        raise ValueError(f"Rango mayor a {MAX_RANGE_DAYS} días: correr varios syncs más cortos")

    resultado = {
        "synced": 0,
        "skipped": 0,
        "collapsed": 0,
        "client_codes_seen": 0,
        "new_client_codes": 0,
        "range": {"desde": desde, "hasta": hasta},
        "errors": [],
    }
    try:
        report = anarvet.fetch_report(desde, hasta)
    except anarvet.AnarvetError as exc:
        logger.error("anarvet_sync: fetch_report falló: %s", exc)
        resultado["errors"].append(str(exc))
        return resultado

    # Dedupe en memoria por clave (última gana): dos filas con la misma clave en un
    # mismo upsert hacen fallar a Postgres ("cannot affect row a second time").
    unicos: dict[str, dict] = {}
    client_codes: dict[str, str | None] = {}
    for raw in report:
        mapped = _row_to_mirror(raw)
        if mapped is None:
            resultado["skipped"] += 1
            continue
        if mapped["dedup_key"] in unicos:
            resultado["collapsed"] += 1
        unicos[mapped["dedup_key"]] = mapped
        cod = mapped.get("cod_cliente")
        if cod:
            client_codes.setdefault(cod, mapped.get("nombre_cliente"))

    filas = list(unicos.values())
    for i in range(0, len(filas), _BATCH_SIZE):
        lote = filas[i : i + _BATCH_SIZE]
        try:
            resultado["synced"] += db.upsert_anarvet_results(lote)
        except Exception as exc:
            logger.error("anarvet_sync: upsert del lote %s falló: %s", i // _BATCH_SIZE, exc)
            resultado["errors"].append(f"lote {i // _BATCH_SIZE}: {exc}")

    resultado["client_codes_seen"] = len(client_codes)
    try:
        existentes = {r["cod_cliente"] for r in db.list_anarvet_client_map()}
        resultado["new_client_codes"] = len(set(client_codes) - existentes)
        db.register_anarvet_client_codes(client_codes)
    except Exception as exc:
        logger.error("anarvet_sync: registro de cod_cliente falló: %s", exc)
        resultado["errors"].append(f"registro de clientes: {exc}")

    logger.info(
        "anarvet_sync %s..%s: %s filas, %s colapsadas, %s códigos de cliente (%s nuevos), %s errores",
        desde, hasta, resultado["synced"], resultado["collapsed"],
        resultado["client_codes_seen"], resultado["new_client_codes"], len(resultado["errors"]),
    )
    return resultado
