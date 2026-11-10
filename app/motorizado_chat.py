"""El motorizado por WhatsApp (pedido del usuario, 10/11).

El motorizado le escribe primero al WhatsApp de A3 y el bot lo reconoce por el celular de su
tarjeta. No lo atiende como cliente ni le pide la autorización de datos (decisión del usuario):
le manda sus recogidas pendientes y le deja marcar una como recogida. Su conversación queda
vinculada sola en la tarjeta («Chat de avisos»), así los avisos de asignación le llegan por ahí.
WhatsApp solo deja escribirle dentro de las 24 h desde su último mensaje: por eso se le pide
que escriba cada mañana.

Marcar «recogida» va en dos toques, para que una orden nombrada al pasar («¿dónde queda la
13?») nunca cambie de estado sola: nombra la orden → el bot pregunta con el botón «Recogí
A3-2026-013» → ese botón (o ese texto exacto) la pasa a `picked_up`, el mismo estado de la
recolección efectiva (decisión 015). No le avisa nada al cliente.
"""
import logging
import re
from datetime import date, datetime, timedelta, timezone

from app.alerts import notify_error
from app.config import APP_TIMEZONE
from app.services import chatwoot, db, maestros_db

logger = logging.getLogger(__name__)

MAX_LISTADAS = 30
MAX_PREGUNTAS = 3
_DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
_CONFIRMA = re.compile(r"^\W*recog[ií]\s+(A3-\d{4}-\d{1,6})\W*$", re.IGNORECASE)
_ORDEN_COMPLETA = re.compile(r"A3[-\s]?(\d{4})[-\s](\d{1,6})", re.IGNORECASE)
# Número suelto («la 13»): pegado a una letra no cuenta, así el «3» de «A3» no es una orden.
_NUMERO_SUELTO = re.compile(r"(?<![\w-])(\d{1,6})(?![\w-])")
RECORDATORIO = "Escríbeme cada mañana: así te llegan por acá las recogidas que te asignen en el día."
PROBLEMA = "Tuve un problema para traer tus recogidas. Intenta de nuevo en un rato, por favor."


def _ultimos10(telefono) -> str:
    digitos = re.sub(r"\D", "", str(telefono or ""))
    return digitos[-10:] if len(digitos) >= 10 else ""


def motorizado_por_telefono(telefono: str, motorizados: list[dict]) -> dict | None:
    """El motorizado activo con ese celular. Van los 10 últimos dígitos: WhatsApp manda
    +57… y la tarjeta guarda el número sin indicativo."""
    buscado = _ultimos10(telefono)
    if not buscado:
        return None
    return next((m for m in motorizados if _ultimos10(m.get("phone")) == buscado), None)


def _sufijo(numero: str | None) -> int | None:
    match = re.search(r"-(\d+)$", numero or "")
    return int(match.group(1)) if match else None


def ordenes_mencionadas(texto: str, pendientes: list[dict]) -> list[dict]:
    """Las recogidas pendientes que el mensaje nombra, completas (A3-2026-013) o por el número
    del final («la 13»). Un número que no es de una sola pendiente no cuenta."""
    elegidas: list[dict] = []
    for anio, num in _ORDEN_COMPLETA.findall(texto or ""):
        elegidas += [p for p in pendientes if str(p.get("order_number") or "").startswith(f"A3-{anio}-")
                     and _sufijo(p.get("order_number")) == int(num)]
    for num in _NUMERO_SUELTO.findall(_ORDEN_COMPLETA.sub(" ", texto or "")):
        candidatas = [p for p in pendientes if _sufijo(p.get("order_number")) == int(num)]
        if len(candidatas) == 1:
            elegidas.append(candidatas[0])
    unicas: dict[str, dict] = {}
    for orden in elegidas:
        unicas.setdefault(orden["id"], orden)
    return list(unicas.values())


def orden_confirmada(linea: str) -> str | None:
    """El número de orden si la línea es el botón «Recogí A3-2026-013» (o ese texto)."""
    match = _CONFIRMA.match((linea or "").strip())
    return match.group(1).upper() if match else None


def _corta(fecha: date) -> str:
    return f"{fecha.day:02d}/{fecha.month:02d}"


def _titulo(fecha_iso: str, hoy: date) -> str:
    if not fecha_iso:
        return "Sin fecha"
    fecha = date.fromisoformat(fecha_iso)
    if fecha < hoy:
        return "⚠️ Atrasadas"
    if fecha == hoy:
        return f"Hoy {_corta(fecha)}"
    if fecha == hoy + timedelta(days=1):
        return f"Mañana {_corta(fecha)}"
    return f"{_DIAS[fecha.weekday()]} {_corta(fecha)}"


def _clinica(orden: dict) -> str:
    return (orden.get("clients") or {}).get("clinic_name") or "Veterinaria"


def mensaje_lista(nombre: str | None, pendientes: list[dict], hoy: date) -> str:
    saludo = f"Hola {nombre.split()[0]} 👋" if (nombre or "").strip() else "Hola 👋"
    if not pendientes:
        return f"{saludo} No tienes recogidas pendientes por ahora. Apenas te asignen una, te aviso por acá.\n\n{RECORDATORIO}"
    ordenadas = sorted(pendientes, key=lambda p: (str(p.get("scheduled_pickup_date") or "9999")[:10],
                                                  str(p.get("order_number") or "")))
    lineas = [f"{saludo} Estas son tus recogidas pendientes ({len(pendientes)}):"]
    grupo_actual = None
    for orden in ordenadas[:MAX_LISTADAS]:
        fecha = str(orden.get("scheduled_pickup_date") or "")[:10]
        grupo = _titulo(fecha, hoy)
        if grupo != grupo_actual:
            lineas += ["", f"*{grupo}*"]
            grupo_actual = grupo
        atraso = f" · era para el {_corta(date.fromisoformat(fecha))}" if grupo.startswith("⚠️") else ""
        lineas.append(f"• {orden.get('order_number') or 's/n'} · {_clinica(orden)}\n"
                      f"   {orden.get('pickup_address') or 'sin dirección'}{atraso}")
    if len(ordenadas) > MAX_LISTADAS:
        lineas.append(f"\n…y {len(ordenadas) - MAX_LISTADAS} más.")
    lineas += ["", "Cuando recojas una, escríbeme su número (por ejemplo «13») y te pido confirmar.",
               RECORDATORIO]
    return "\n".join(lineas)


def _marcar(orden: dict, motorizado: dict) -> None:
    db.update_request(orden["id"], {"status": "picked_up"})
    db.create_request_event(orden["id"], "dashboard_status_update", {
        "status": "picked_up", "status_label": "Retirada", "updated_by": motorizado.get("name"),
        "source": "whatsapp_motorizado", "updated_at": datetime.now(timezone.utc).isoformat()})


def _preguntar(conversation_id: str, orden: dict) -> None:
    numero = orden["order_number"]  # «Recogí A3-2026-013»: 18 caracteres, WhatsApp admite 20
    chatwoot.send_options(conversation_id,
                          f"¿Ya recogiste la {numero}?\n{_clinica(orden)} · {orden.get('pickup_address') or 'sin dirección'}",
                          [{"title": f"Recogí {numero}", "value": f"recogi {numero}"},
                           {"title": "No", "value": "no"}])


def _responder(conversation_id: str, texto: str, motorizado: dict) -> None:
    pendientes = maestros_db.recogidas_pendientes(motorizado["id"])
    lineas = (texto or "").splitlines() or [""]
    confirmadas = [orden_confirmada(linea) for linea in lineas]
    hechas, ajenas = [], []
    for numero in filter(None, confirmadas):
        orden = next((p for p in pendientes if p.get("order_number") == numero), None)
        if orden:
            _marcar(orden, motorizado)
            pendientes.remove(orden)
            hechas.append(orden)
        else:
            ajenas.append(numero)
    if hechas or ajenas:
        partes = [f"Listo ✅ La {o['order_number']} ({_clinica(o)}) quedó como recogida." for o in hechas]
        partes += [f"La {n} no está entre tus recogidas pendientes (puede que ya estuviera marcada)." for n in ajenas]
        partes.append(f"Te quedan {len(pendientes)} pendientes." if pendientes else "No te quedan recogidas pendientes 🙌")
        chatwoot.send_message(conversation_id, "\n".join(partes))
    resto = "\n".join(linea for linea, conf in zip(lineas, confirmadas) if not conf)
    mencionadas = ordenes_mencionadas(resto, pendientes)[:MAX_PREGUNTAS]
    for orden in mencionadas:
        _preguntar(conversation_id, orden)
    if not (hechas or ajenas or mencionadas):
        chatwoot.send_message(conversation_id, mensaje_lista(motorizado.get("name"), pendientes,
                                                             datetime.now(APP_TIMEZONE).date()))


def atender(conversation_id: str, texto: str, canal: str, telefono: str) -> bool:
    """True si el mensaje era de un motorizado y ya se le respondió (no sigue al agente)."""
    if canal != "whatsapp" or not _ultimos10(telefono):
        return False
    try:
        motorizado = motorizado_por_telefono(telefono, db.list_active_couriers())
    except Exception as exc:  # noqa: BLE001 — sin poder mirar, sigue el flujo de siempre
        logger.exception("No se pudo revisar si %s es motorizado", conversation_id)
        notify_error("reconocer motorizado por WhatsApp", exc, f"conversación {conversation_id}")
        return False
    if not motorizado:
        return False
    try:
        if str(motorizado.get("chatwoot_conversation_id") or "") != str(conversation_id):
            db.update_courier(motorizado["id"], {"chatwoot_conversation_id": str(conversation_id)})
        _responder(conversation_id, texto, motorizado)
    except Exception as exc:  # noqa: BLE001 — es motorizado: nunca cae al flujo de clientes
        logger.exception("Falló la atención del motorizado %s", motorizado.get("id"))
        notify_error("motorizado por WhatsApp", exc, f"conversación {conversation_id}")
        try:
            chatwoot.send_message(conversation_id, PROBLEMA)
        except Exception:  # noqa: BLE001
            pass
    return True
