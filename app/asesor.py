"""¿Una persona de A3 está atendiendo esta conversación? Entonces el bot no habla.

Prueba de A3 del 12/11: el bot derivó a un cliente nuevo, la asesora lo tomó y, mientras ella
lo atendía, el bot volvió a contestar encima. A3 preguntó cada cuánto retoma el bot. Regla
(OK del usuario, 2026-11-16):

- El bot CALLA mientras la conversación de Chatwoot está abierta, asignada a un asesor, y
  alguien de A3 la miró en las últimas `ASESOR_ACTIVO_HORAS` (12 por defecto).
- El bot VUELVE cuando el asesor la marca como resuelta (el próximo mensaje del cliente abre
  una conversación nueva, sin asesor) o cuando pasan esas horas sin que nadie de A3 la mire.

Todo sale del mismo aviso de Chatwoot que trae el mensaje del cliente: no se consulta nada.
Lógica pura. Sin esos datos (o fuera de Chatwoot) responde False y el bot sigue como siempre.
"""
import time

from app.config import ASESOR_ACTIVO_HORAS


def _dict(valor) -> dict:
    return valor if isinstance(valor, dict) else {}


def _segundos(valor) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def atendiendo(conversacion: dict | None, ahora: float | None = None) -> bool:
    """`conversacion` es el bloque `conversation` del webhook de Chatwoot.

    Hacen falta las tres cosas: «open» (el bot atiende en «pending»), un asesor asignado
    (derivar a un EQUIPO no alcanza: todavía no la tomó nadie) y que alguien de A3 la haya
    abierto hace poco (`agent_last_seen_at`: Chatwoot lo actualiza mientras el asesor la tiene
    a la vista; las respuestas del bot por API no lo tocan)."""
    conversacion = _dict(conversacion)
    if str(conversacion.get("status") or "").lower() != "open":
        return False
    if not _dict(_dict(conversacion.get("meta")).get("assignee")).get("id"):
        return False
    visto = _segundos(conversacion.get("agent_last_seen_at"))
    if visto <= 0:
        return False
    ahora = time.time() if ahora is None else ahora
    return ahora - visto < ASESOR_ACTIVO_HORAS * 3600
