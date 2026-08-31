"""Consultas Supabase propias del Portal Web: lab_results, portal_notifications
y solicitudes por cliente. Solo I/O — el aislamiento por client_id lo hace
cumplir la capa de vistas (app/portal/), que nunca acepta client_id del usuario.
"""
import functools
from datetime import datetime, timezone

from app.services.db import _client


def _safe(factory):
    """Degrada a un valor por defecto si la tabla del portal aún no existe en
    Supabase (migración 015 no aplicada → error PGRST205). Cualquier otro error
    se propaga. Permite mostrar el portal aunque falten lab_results/portal_notifications."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 — se re-lanza salvo tabla ausente
                msg = str(exc)
                if "PGRST205" in msg or "Could not find the table" in msg:
                    return factory()
                raise
        return wrapper
    return deco


# ── lab_results ───────────────────────────────────────────────────────────────

def insert_lab_result(fields: dict) -> dict | None:
    result = _client.table("lab_results").insert(fields).execute()
    return result.data[0] if result.data else None


@_safe(lambda: None)
def get_lab_result(result_id: str) -> dict | None:
    result = (
        _client.table("lab_results")
        .select("*, clients(clinic_name)")
        .eq("id", result_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


@_safe(list)
def list_lab_results(
    filters: dict,
    client_id: str | None = None,
    only_published: bool = False,
    limit: int = 100,
) -> list[dict]:
    """Lista resultados con filtros opcionales. `client_id` restringe a un
    cliente (vistas de veterinaria); `only_published` oculta borradores."""
    select = "*, clients(clinic_name)"
    if filters.get("clinic"):
        # !inner para que el filtro sobre la tabla embebida excluya filas padre.
        select = "*, clients!inner(clinic_name)"
    query = _client.table("lab_results").select(select)
    if client_id:
        query = query.eq("client_id", client_id)
    if only_published:
        query = query.eq("published", True)
    if filters.get("clinic"):
        query = query.ilike("clients.clinic_name", f"%{filters['clinic']}%")
    if filters.get("patient"):
        query = query.ilike("patient_name", f"%{filters['patient']}%")
    if filters.get("owner"):
        query = query.ilike("owner_name", f"%{filters['owner']}%")
    if filters.get("order_number"):
        query = query.ilike("order_number", f"%{filters['order_number']}%")
    # Exacto, no ilike: se usa para responder "¿ESTA orden ya tiene su resultado?". Sin el
    # filtro, la consulta devolvía todos los del cliente y el portal marcaba una solicitud
    # como resuelta por el resultado de otra.
    if filters.get("request_id"):
        query = query.eq("request_id", filters["request_id"])
    if filters.get("date_from"):
        query = query.gte("created_at", filters["date_from"])
    if filters.get("date_to"):
        query = query.lte("created_at", f"{filters['date_to']}T23:59:59")
    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data or []


def publish_lab_result(result_id: str) -> dict | None:
    result = (
        _client.table("lab_results")
        .update({"published": True, "published_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", result_id)
        .execute()
    )
    return result.data[0] if result.data else None


# ── portal_notifications ──────────────────────────────────────────────────────

@_safe(lambda: None)
def insert_notification(
    client_id: str,
    type: str,
    title: str,
    body: str | None = None,
    request_id: str | None = None,
    result_id: str | None = None,
) -> None:
    _client.table("portal_notifications").insert({
        "client_id": client_id,
        "type": type,
        "title": title,
        "body": body,
        "request_id": request_id,
        "result_id": result_id,
    }).execute()


@_safe(list)
def list_notifications(client_id: str, limit: int = 50) -> list[dict]:
    result = (
        _client.table("portal_notifications")
        .select("*")
        .eq("client_id", client_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


@_safe(lambda: 0)
def count_unread_notifications(client_id: str) -> int:
    result = (
        _client.table("portal_notifications")
        .select("id", count="exact")
        .eq("client_id", client_id)
        .is_("read_at", "null")
        .execute()
    )
    return result.count or 0


@_safe(lambda: None)
def mark_notification_read(notification_id: str, client_id: str) -> None:
    """El filtro por client_id garantiza que un cliente no marque ajenas."""
    (
        _client.table("portal_notifications")
        .update({"read_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", notification_id)
        .eq("client_id", client_id)
        .execute()
    )


# ── Solicitudes del cliente ───────────────────────────────────────────────────

def list_client_requests(
    client_id: str, filters: dict | None = None, limit: int = 100
) -> list[dict]:
    """Solicitudes de retiro del cliente, con filtros opcionales.

    Mismos filtros que list_lab_results (paciente, n° de orden, rango de
    fechas) más el estado, para que las dos pantallas del portal se usen
    igual. Sin filtros se comporta como antes.
    """
    filters = filters or {}
    query = (
        _client.table("requests")
        .select("*, couriers(name)")
        .eq("client_id", client_id)
        .eq("service_area", "route_scheduling")
    )
    if filters.get("patient"):
        query = query.ilike("patient_name", f"%{filters['patient']}%")
    if filters.get("order_number"):
        query = query.ilike("order_number", f"%{filters['order_number']}%")
    if filters.get("status"):
        query = query.eq("status", filters["status"])
    if filters.get("date_from"):
        query = query.gte("requested_at", filters["date_from"])
    if filters.get("date_to"):
        query = query.lte("requested_at", f"{filters['date_to']}T23:59:59")
    result = query.order("requested_at", desc=True).limit(limit).execute()
    return result.data or []


def get_client_request(request_id: str, client_id: str) -> dict | None:
    """Una solicitud del cliente. Filtra por client_id en la query, no después:
    una orden de otra veterinaria no debe llegar nunca a la capa de vistas."""
    result = (
        _client.table("requests")
        .select("*, couriers(name, phone)")
        .eq("id", request_id)
        .eq("client_id", client_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def get_request_by_order_number(order_number: str) -> dict | None:
    result = (
        _client.table("requests")
        .select("*")
        .eq("order_number", order_number)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def chat_for_client(client_id: str) -> tuple[str, str] | None:
    """(chat_id, canal) de la sesión más reciente del cliente, para avisos de resultados.

    Antes filtraba `channel = "telegram"`: un cliente que escribe por Chatwoot (web o
    WhatsApp) no recibía NINGÚN aviso — era el tapón #2 de WhatsApp. El canal devuelto
    decide el transporte del aviso; whatsapp viaja por Chatwoot."""
    result = (
        _client.table("telegram_sessions")
        .select("external_chat_id, channel")
        .eq("client_id", client_id)
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    row = result.data[0]
    return row["external_chat_id"], (row.get("channel") or "telegram")

@_safe(lambda: None)
def unpublish_lab_result(result_id: str) -> dict | None:
    """Saca el informe del portal sin borrarlo: vuelve a borrador.

    Borra también el aviso: si quedara, el cliente vería en sus notificaciones un
    «resultado disponible» que ya no puede abrir.
    """
    _client.table("portal_notifications").delete().eq("result_id", result_id).execute()
    result = (
        _client.table("lab_results")
        .update({"published": False, "published_at": None})
        .eq("id", result_id)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


@_safe(lambda: None)
def delete_lab_result(result_id: str) -> None:
    """Borra el informe y el aviso que se le mandó al cliente.

    Primero la notificación: si quedara colgando, el cliente vería un aviso que lleva a un
    informe que ya no existe.
    """
    _client.table("portal_notifications").delete().eq("result_id", result_id).execute()
    _client.table("lab_results").delete().eq("id", result_id).execute()
