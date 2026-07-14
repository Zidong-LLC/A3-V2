"""Login del Portal Web (solo clientes veterinarias) contra Supabase Auth.

Solo I/O: valida credenciales con el password grant y devuelve la identidad
del usuario. El client_id vive en app_metadata, que solo puede editarse con
la service role (nunca por el propio usuario). El access_token no se guarda:
el backend opera con service role vía app/services/db.py.
"""
import json
import urllib.error
import urllib.request

from app.config import SUPABASE_URL, SUPABASE_ANON_KEY


class PortalAuthError(Exception):
    """Login rechazado: credenciales inválidas o cuenta sin acceso al portal."""


def sign_in(email: str, password: str) -> dict:
    """Valida email/contraseña en GoTrue y devuelve
    {"user_id", "email", "client_id"}.

    Solo cuentas con app_metadata.portal_role == "client" y client_id entran
    al portal (el personal del laboratorio usa el dashboard, no el portal).
    Lanza PortalAuthError con mensaje mostrable si el login no procede.
    """
    if not SUPABASE_ANON_KEY:
        raise PortalAuthError("Portal no configurado: falta SUPABASE_ANON_KEY")

    payload = json.dumps({"email": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        data=payload,
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise PortalAuthError("Correo o contraseña incorrectos") from exc
    except urllib.error.URLError as exc:
        raise PortalAuthError("No se pudo contactar el servicio de acceso") from exc

    user = data.get("user") or {}
    meta = user.get("app_metadata") or {}
    if meta.get("portal_role") != "client" or not meta.get("client_id"):
        raise PortalAuthError("La cuenta no tiene acceso al portal de clientes")

    return {
        "user_id": user.get("id"),
        "email": user.get("email"),
        "client_id": meta.get("client_id"),
    }
