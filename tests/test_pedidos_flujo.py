"""
El flujo conversacional del PEDIDO (decisión 011): varias órdenes, un pago, una factura.

Este archivo cubre el hueco que dejó el flag. `PEDIDOS_ENABLED` nació apagado, así que la
suite entera describía el flujo viejo: existían tests de la capa de datos, del dashboard y del
barrido, pero NINGUNO del carril conversacional. La ruta que decide cuándo se cobra y cuántas
facturas salen era la menos probada de las dos — y es la que toca dinero.

Lo que se protege acá es la secuencia que A3 acordó (reunión 28/07) y que el usuario reportó
rota en el testeo del 2026-08-14:

    orden 1 → (sin preguntar el pago) → "¿otra orden o cerramos?" → orden 2 → …
    → "eso es todo" → observación + forma de pago → UNA factura con el total

Los tres momentos donde el bot pedía la forma de pago por orden están cubiertos uno por uno.
"""
from unittest.mock import patch

import pytest

from app import agent
from app.config import PEDIDOS_ENABLED
from app.enforcers import confirmacion as econf, orden as eorden
from app.flow import extra_analysis_offer, order_required_fields
from app.messages import PEDIDO_CLOSING_QUESTION

pytestmark = pytest.mark.skipif(
    not PEDIDOS_ENABLED, reason="el flujo del pedido solo existe con PEDIDOS_ENABLED")


SESSION = {"client_id": "cli-1", "chat_id": "chat-1"}

ORDEN_COMPLETA = {
    "_client_found": True,
    "clinic_name": "Animal Pets",
    "pickup_address": "DG 51A SUR 61B-03",
    "requesting_doctor": "Dr. Araujo",
    "patient_name": "Greta",
    "species": "Canino",
    "breed": "Bulldog",
    "sex": "Hembra",
    "patient_age": "3 años",
    "owner_name": "Jose",
    "observations": "sin observaciones",
    "exam_type": "Perfil Prequirúrgico I",
    "_selected_profile_code": "152",
    "_selected_profile_name": "Perfil Prequirúrgico I",
    "_selected_profile_price": 24000,
}


def _resp(fields, **extra):
    ai = agent._base_route_response(extra.pop("reply", "(reply del modelo)"), fields)
    ai.update(extra)
    return ai


# ── 1. La orden no cobra ────────────────────────────────────────────────────────

def test_la_orden_completa_no_pregunta_la_forma_de_pago():
    """El síntoma que reportó el usuario: 'me estaba pidiendo antes de cerrar cómo prefiere
    la forma de pago'. Con pedidos el pago es del PEDIDO, no de la orden."""
    fields = dict(ORDEN_COMPLETA)
    out = agent._enforce_payment_step(SESSION, _resp(fields), fields)
    assert "pago" not in out["reply"].lower()


def test_payment_method_no_es_campo_requerido_de_la_orden():
    """La raíz de lo anterior: si `payment_method` sigue en los campos de la orden, TODO el
    flujo lo va a pedir (el paso de pago, el resumen, el empuje del dato faltante)."""
    assert "payment_method" not in order_required_fields()
    assert agent._missing_route_field(SESSION, dict(ORDEN_COMPLETA)) is None


def test_declinar_la_oferta_de_analisis_lleva_a_confirmar_no_a_pagar():
    """Tercer punto de fuga: `_handle_extra_analysis_answer` devolvía la pregunta de pago sin
    mirar el flag, así que el bot la pedía orden por orden aunque los pedidos estén activos."""
    fields = dict(ORDEN_COMPLETA, _offering_extra_analysis=True)
    out = agent._handle_extra_analysis_answer(SESSION, fields, "no, así está bien")
    assert "pago" not in out["reply"].lower()
    assert out["phase"] == agent.CONFIRMATION_PHASE
    assert "¿Confirmas estos datos?" in out["reply"]


def test_la_oferta_de_analisis_extra_no_promete_el_pago():
    """El texto tiene que anunciar el paso que de verdad sigue: cerrar la orden."""
    oferta = extra_analysis_offer()
    assert "pago" not in oferta.lower()
    assert "orden" in oferta.lower()


def test_el_resumen_de_la_orden_no_muestra_forma_de_pago():
    """A3 lo pidió así: la forma de pago se ve en el resumen del PEDIDO, una sola vez."""
    resumen = agent._route_confirmation_summary(dict(ORDEN_COMPLETA))
    assert resumen and "Forma de pago" not in resumen


# ── 1b. Antes de confirmar, el cliente puede editar o agregar ───────────────────

def test_el_resumen_ofrece_cambiar_datos_y_agregar_analisis():
    """Pedido del usuario (2026-08-14): *"nunca le preguntaron si quería editar alguno de los
    datos o agregar otro análisis"*. El paso que lo ofrecía quedó huérfano el 28/07, cuando el
    análisis pasó a ir ANTES de las observaciones: desde entonces, al fijar el análisis siempre
    falta `observations`, así que la oferta no se disparaba nunca. Ahora se dice acá, que es el
    único momento en que el cliente ve la orden entera antes de que se registre."""
    resumen = agent._route_confirmation_summary(dict(ORDEN_COMPLETA))
    assert "cambiar algún dato" in resumen
    assert "agregar otro análisis" in resumen


def test_la_oferta_no_puede_quedar_solo_en_el_paso_huerfano():
    """Por qué el ofrecimiento NO puede depender de `order_data_complete`: al fijar el análisis
    la orden todavía no está completa (falta la observación), así que ese camino está muerto.
    Si alguien reordena los campos y este test empieza a fallar, revisar el resumen igual."""
    fields = {k: v for k, v in ORDEN_COMPLETA.items() if k != "observations"}
    assert agent._missing_route_field(SESSION, fields) == "observations"


def test_fijado_el_analisis_el_sistema_empuja_el_dato_que_falta():
    """El hueco que dejaba mandar al modelo. Entre "se fijó el análisis" y "la orden está
    completa" queda la observación (desde el 28/07 va después del análisis). Ahí este enforcer
    cedía, y el modelo improvisaba "¿quieres agregar otro análisis?": el flujo daba vueltas y
    no llegaba nunca al resumen. Verificado en vivo antes de arreglarlo."""
    base = {k: v for k, v in ORDEN_COMPLETA.items()
            if k not in ("observations", "exam_type", "_selected_profile_code",
                         "_selected_profile_name", "_selected_profile_price")}
    fields = dict(base, selected_tests=["1101"])
    ai = {"intent": "route_scheduling", "captured_fields": fields,
          "reply": "¿Quieres agregar otro análisis o ya lo cerramos así?"}
    with patch.object(eorden.db, "get_tests_by_codes", return_value=[]):
        out = eorden._enforce_extra_analysis_offer(SESSION, ai, base)
    assert "observación" in out["reply"].lower() or "observacion" in out["reply"].lower(), \
        "tiene que empujar el dato que falta, no dejar improvisar al modelo"


def test_agregar_un_analisis_en_la_confirmacion_no_registra_la_orden():
    """La respuesta a esa oferta tiene que AGREGAR, no cerrar. Se prueba con "agregame una
    glucosa", que el detector de tokens NO reconoce (medido: "agregale un coprológico" sí,
    "agregame una glucosa" no): entra por la señal del modelo."""
    GLUCOSA = {"code": "0201", "name": "Glucosa", "price": 18000, "category": "Química"}
    fields = dict(ORDEN_COMPLETA)
    with patch.object(econf.db, "get_tests_by_codes_or_names", return_value=[GLUCOSA]), \
         patch.object(econf.db, "get_tests_by_codes", return_value=[GLUCOSA]):
        out = econf._confirmation_analysis_adjustment(
            SESSION, fields, "agregame una glucosa", "correction")
    assert out is not None, "el ajuste tiene que tomar el turno, no dejarlo pasar al cierre"
    assert out["phase"] != "fase_6_cierre"


def test_pedir_cambiar_otro_dato_no_entra_al_carril_de_analisis():
    """Contraprueba: "quiero cambiar el médico" también es `correction`, pero no es un ajuste
    de análisis — si este carril se lo tragara, el cliente no podría corregir nada más."""
    out = econf._confirmation_analysis_adjustment(
        SESSION, dict(ORDEN_COMPLETA), "quiero cambiar el médico", "correction")
    assert out is None or "análisis" not in (out.get("reply") or "").lower()


# ── 2. El pedido queda abierto y admite más órdenes ─────────────────────────────

def test_pedir_otra_orden_mantiene_el_pedido_abierto():
    """'otra orden' gana siempre sobre el cierre: se le cuelga una orden más al pedido."""
    prev = {"_pedido_id": "ped-1"}
    ai = _resp(dict(ORDEN_COMPLETA), user_intent_signal="another_order",
               reply="Perfecto, creamos otra orden.")
    out = agent._enforce_open_pedido_close(SESSION, ai, prev, "necesito otra orden")
    assert out["reply"] == "Perfecto, creamos otra orden."
    assert not out.get(agent._SKIP_REQUEST_CREATION)


def test_cargar_otro_paciente_no_cierra_el_pedido():
    """Contraprueba semántica: 'listo' abre la frase pero el cliente NO está terminando.
    Una lista de palabras leería 'listo' como despedida y cerraría el pedido de más."""
    prev = {"_pedido_id": "ped-1"}
    ai = _resp(dict(ORDEN_COMPLETA), user_intent_signal="another_order")
    out = agent._enforce_open_pedido_close(
        SESSION, ai, prev, "listo, ahora cargame el otro paciente")
    assert PEDIDO_CLOSING_QUESTION not in out["reply"]
    assert not out.get("captured_fields", {}).get("_pedido_awaiting_payment")


# ── 3. El pago se pregunta UNA vez, al final ────────────────────────────────────

@pytest.mark.parametrize("signal", ["farewell", "negate", "cancel"])
def test_terminar_de_cargar_dispara_la_pregunta_del_pago(signal):
    """El cliente da por terminada la carga de mil formas; la señal del modelo es la fuente."""
    prev = {"_pedido_id": "ped-1"}
    ai = _resp(dict(ORDEN_COMPLETA), user_intent_signal=signal)
    out = agent._enforce_open_pedido_close(SESSION, ai, prev, "eso sería todo")
    assert out["reply"] == PEDIDO_CLOSING_QUESTION
    assert out["captured_fields"]["_pedido_awaiting_payment"] is True


def test_un_pago_arrastrado_NO_cierra_ni_factura_el_pedido():
    """GUARD DE DINERO. En la prueba del 2026-08-14 el modelo rellenó `payment_method` solo,
    sin que el bot preguntara nunca: apareció "Forma de pago: contraentrega" en la segunda
    orden. Con ese valor suelto alcanzaba para cerrar el pedido entero y emitir la factura con
    un método que el cliente jamás eligió. Ahora el pago tiene que venir de lo que el cliente
    ACABA de escribir, o de que ya le hayamos preguntado."""
    prev = {"_pedido_id": "ped-1"}
    ai = _resp(dict(ORDEN_COMPLETA, payment_method="contraentrega"),
               user_intent_signal="provides_requested_data", reply="(del modelo)")
    out = agent._enforce_open_pedido_close(SESSION, ai, prev, "el propietario es Lola")
    assert out["reply"] == "(del modelo)", "no puede cerrar el pedido"
    assert not out.get("captured_fields", {}).get("_pedido_cerrado")


def test_el_pago_que_el_cliente_dice_si_cierra_el_pedido(monkeypatch):
    """La contraprueba del guard: dicho en el turno, cierra igual que siempre."""
    monkeypatch.setattr(agent.db, "close_pedido", lambda *a, **k: None)
    monkeypatch.setattr(agent.db, "list_pedido_requests", lambda pid: [{"id": "r-1"}])
    monkeypatch.setattr(agent, "ALEGRA_ENABLED", False)
    prev = {"_pedido_id": "ped-1"}
    ai = _resp(dict(ORDEN_COMPLETA, payment_method="contraentrega"))
    out = agent._enforce_open_pedido_close(SESSION, ai, prev, "pagamos contra entrega")
    assert out["captured_fields"]["_pedido_cerrado"] is True


def test_tras_preguntar_el_pago_vale_la_lectura_del_modelo(monkeypatch):
    """Si ya preguntamos, la respuesta puede venir en cualquier fraseo y la interpreta el
    modelo — el guard no puede exigir que el token esté en el texto."""
    monkeypatch.setattr(agent.db, "close_pedido", lambda *a, **k: None)
    monkeypatch.setattr(agent.db, "list_pedido_requests", lambda pid: [{"id": "r-1"}])
    monkeypatch.setattr(agent, "ALEGRA_ENABLED", False)
    prev = {"_pedido_id": "ped-1", "_pedido_awaiting_payment": True}
    ai = _resp(dict(ORDEN_COMPLETA, payment_method="contraentrega"))
    out = agent._enforce_open_pedido_close(SESSION, ai, prev, "cuando lleguen les doy la plata")
    assert out["captured_fields"]["_pedido_cerrado"] is True


def test_la_orden_siguiente_no_hereda_una_forma_de_pago():
    """El snapshot de datos reusados mostraba "Forma de pago: contraentrega" — contradice que
    el pago sea del pedido, y le da credibilidad a un valor que el cliente nunca eligió."""
    fields = dict(ORDEN_COMPLETA, payment_method="contraentrega",
                  _prev_order_snapshot=dict(ORDEN_COMPLETA))
    out = agent._start_followup_service_order_response(fields, "otra orden")
    assert "Forma de pago" not in out["reply"]
    assert "forma de pago" not in out["reply"].lower()


def test_la_pregunta_del_pago_no_se_repite():
    """Con `_pedido_awaiting_payment` ya puesto, otro mensaje no vuelve a preguntar."""
    prev = {"_pedido_id": "ped-1", "_pedido_awaiting_payment": True}
    ai = _resp(dict(ORDEN_COMPLETA), user_intent_signal="farewell", reply="(del modelo)")
    out = agent._enforce_open_pedido_close(SESSION, ai, prev, "dale")
    assert out["reply"] == "(del modelo)"


def test_el_cierre_del_pedido_no_registra_otra_orden():
    """Guard del turno de cierre: llega a fase terminal pero sus órdenes YA se registraron una
    por una. Sin esta marca `_finalize_request` leía 'entró a cierre' y creaba una orden más
    — en la prueba con sinónimos llegó a duplicar la misma orden cuatro veces."""
    prev = {"_pedido_id": "ped-1"}
    ai = _resp(dict(ORDEN_COMPLETA), user_intent_signal="farewell")
    out = agent._enforce_open_pedido_close(SESSION, ai, prev, "eso es todo")
    assert out[agent._SKIP_REQUEST_CREATION] is True
    assert out["phase"] != "fase_6_cierre", "fase terminal acá volvía a registrar la orden"


# ── 4. El cierre: un resumen con todas las órdenes y UNA factura ────────────────

@pytest.fixture
def pedido_cerrado(monkeypatch):
    """Cierra un pedido de DOS órdenes y captura lo que se le mandó a Alegra."""
    reg = {"cerrados": [], "facturas": []}
    monkeypatch.setattr(agent.db, "close_pedido",
                        lambda pid, pago: reg["cerrados"].append((pid, pago)))
    monkeypatch.setattr(agent.db, "list_pedido_requests",
                        lambda pid: [{"id": "r-1"}, {"id": "r-2"}])
    monkeypatch.setattr(agent, "_try_invoice_pedido",
                        lambda pid, fields: reg["facturas"].append(pid))
    monkeypatch.setattr(agent, "ALEGRA_ENABLED", True)

    fields = dict(
        ORDEN_COMPLETA,
        _pedido_id="ped-1",
        _pedido_awaiting_payment=True,
        _pedido_ordenes=[
            {"order_number": "A3-001", "patient_name": "Greta", "species": "Canino",
             "requesting_doctor": "Dr. Araujo", "exam_type": "Perfil Prequirúrgico I",
             "total": 24000},
            {"order_number": "A3-002", "patient_name": "Rocco", "species": "Felino",
             "requesting_doctor": "Dr. Araujo", "exam_type": "Cuadro Hemático",
             "total": 14000},
        ],
    )
    reg["out"] = agent._close_pedido_turn(SESSION, fields, "contraentrega")
    return reg


def test_el_resumen_final_lista_TODAS_las_ordenes(pedido_cerrado):
    """El punto 4.6, que nunca se había demostrado: con dos pacientes en una sola factura, un
    renglón por pedido no alcanza — la veterinaria tiene que ver qué se le cobra por cada uno."""
    reply = pedido_cerrado["out"]["reply"]
    assert "A3-001" in reply and "Greta" in reply
    assert "A3-002" in reply and "Rocco" in reply
    assert "2 órdenes" in reply


def test_el_resumen_final_trae_el_total_consolidado(pedido_cerrado):
    reply = pedido_cerrado["out"]["reply"]
    assert "$38.000" in reply, "24.000 + 14.000 del pedido completo"
    assert "contraentrega" in reply.lower()


def test_se_emite_UNA_sola_factura_por_pedido(pedido_cerrado):
    """El corazón de la decisión 011: una factura con todas las órdenes, no una por orden."""
    assert pedido_cerrado["facturas"] == ["ped-1"]
    assert pedido_cerrado["cerrados"] == [("ped-1", "contraentrega")]


def test_el_cierre_limpia_el_estado_del_pedido(pedido_cerrado):
    """Sin esto el pedido siguiente heredaría las órdenes y los perfiles del anterior — y la
    factura del próximo cliente saldría con las líneas de este."""
    fields = pedido_cerrado["out"]["captured_fields"]
    for flag in ("_pedido_id", "_pedido_profiles", "_pedido_ordenes", "_pedido_awaiting_payment"):
        assert flag not in fields, flag
    assert fields["_pedido_cerrado"] is True


def test_un_fallo_de_alegra_no_tumba_el_cierre(monkeypatch):
    """La factura es complementaria: si Alegra falla, el pedido queda cerrado igual y la
    recogida sigue en pie. El pedido queda 'cerrado' y no 'facturado', que es lo único que
    después permite encontrar los que quedaron sin factura."""
    monkeypatch.setattr(agent.db, "close_pedido", lambda *a, **k: None)
    monkeypatch.setattr(agent.db, "list_pedido_requests", lambda pid: [{"id": "r-1"}])
    monkeypatch.setattr(agent, "ALEGRA_ENABLED", True)

    def _explota(*_a, **_k):
        raise RuntimeError("Alegra caído")

    monkeypatch.setattr(agent.billing, "invoice_order", _explota)
    fields = dict(ORDEN_COMPLETA, _pedido_id="ped-1", _pedido_profiles=[
        {"base_profile": {"code": "152", "name": "Prequirúrgico I", "price": 24000},
         "added_tests": [], "total_estimated": 24000}])
    out = agent._close_pedido_turn(SESSION, fields, "contraentrega")
    assert out["captured_fields"]["_pedido_cerrado"] is True
    assert "cerramos el pedido" in out["reply"]


def test_si_la_base_falla_el_cliente_igual_recibe_su_cierre(monkeypatch):
    """Un error de Supabase no puede dejar al cliente sin respuesta después de que dio el pago."""
    def _explota(*_a, **_k):
        raise RuntimeError("Supabase caído")

    monkeypatch.setattr(agent.db, "close_pedido", _explota)
    monkeypatch.setattr(agent, "ALEGRA_ENABLED", False)
    out = agent._close_pedido_turn(SESSION, dict(ORDEN_COMPLETA, _pedido_id="ped-1"),
                                   "contraentrega")
    assert out["reply"].strip()
    assert out[agent._SKIP_REQUEST_CREATION] is True
