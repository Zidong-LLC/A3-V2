"""Portal Web A3 — acceso EXCLUSIVO de clientes veterinarias.

El personal del laboratorio usa el dashboard administrativo existente
(la carga de resultados vive en app/dashboard_results.py). Las vistas se
reparten por responsabilidad: auth (login), client_requests (retiros/perfil)
y client_results (resultados/notificaciones).
"""
from flask import Blueprint, session

portal_bp = Blueprint("portal", __name__, url_prefix="/portal")


@portal_bp.context_processor
def _notification_badge():
    """Contador de notificaciones no leídas para el menú del cliente."""
    if not session.get("portal_client_id"):
        return {"notif_unread": 0}
    from app.services import portal_db
    try:
        return {"notif_unread": portal_db.count_unread_notifications(session["portal_client_id"])}
    except Exception:
        return {"notif_unread": 0}


from app.portal import auth, client_requests, client_results, client_cartera  # noqa: E402,F401
