"""Preguntas cerradas con opciones numeradas (pedido de A3, 2026-10-29).

Un mecanismo único: al salir se anexan «1. … 2. …» a las preguntas cerradas conocidas y se
guarda qué significa cada número; al entrar, un «2» se traduce al texto que el flujo ya
entiende, antes de interpretar nada. La marca vive un solo turno."""
import pytest

from app import agent, opciones_cerradas
from app.messages import (
    EXTRA_ANALYSIS_OFFER,
    PAYMENT_METHOD_QUESTION,
    PEDIDO_CLOSING_PROMPT,
    PEDIDO_CLOSING_QUESTION,
    PEDIDO_OFFER_REASK,
)
from tests.test_prueba_real_whatsapp_20261029 import CHAT1_TRAS_REGISTRAR, HIST1, turno


def _resp(reply, **fields):
    return {"reply": reply, "captured_fields": dict(fields)}


# ── Salida: anexar las opciones ─────────────────────────────────────────────────────


@pytest.mark.parametrize("pregunta,etiquetas", [
    (EXTRA_ANALYSIS_OFFER, ["1. Agregar otro análisis", "2. Dejarla así"]),
    (opciones_cerradas.OBSERVACION_PREGUNTA, ["1. Dejar una observación", "2. Sin observaciones"]),
    (PEDIDO_CLOSING_PROMPT, ["1. Otra orden para otro paciente", "2. Continuar con el pago"]),
    (PEDIDO_OFFER_REASK, ["1. Otra orden para otro paciente", "2. Continuar con el pago"]),
    (PEDIDO_CLOSING_QUESTION, ["1. Contraentrega con el motorizado", "2. Pago en línea"]),
    (PAYMENT_METHOD_QUESTION, ["1. Contraentrega con el motorizado", "2. Pago en línea"]),
])
def test_cada_pregunta_cerrada_sale_con_sus_opciones(pregunta, etiquetas):
    out = opciones_cerradas.agregar(_resp(f"Listo, anoto eso. {pregunta}"))
    assert out["reply"].endswith("\n".join(etiquetas))
    assert set(out["captured_fields"][opciones_cerradas.CLAVE]) == {"1", "2"}


def test_reoferta_de_datos_heredados_lista_confirmar_y_cada_cambio():
    reply = ("Perfecto, creamos otra orden de servicio. Mantengo estos datos de la orden anterior:\n"
             "- Dirección de retiro: Calle 1\n¿Confirmas o quieres cambiar alguno (dirección, médico o análisis)?")
    out = opciones_cerradas.agregar(_resp(reply))
    assert out["reply"].endswith("1. Confirmar estos datos\n2. Cambiar la dirección\n3. Cambiar el médico\n4. Cambiar el análisis")
    assert out["captured_fields"][opciones_cerradas.CLAVE]["3"] == "quiero cambiar el médico"


def test_una_respuesta_sin_pregunta_cerrada_queda_igual():
    out = opciones_cerradas.agregar(_resp("¿Cuál es el nombre del paciente?"))
    assert out["reply"] == "¿Cuál es el nombre del paciente?"
    assert opciones_cerradas.CLAVE not in out["captured_fields"]


def test_con_menu_de_analisis_pendiente_los_numeros_son_del_menu():
    out = opciones_cerradas.agregar(_resp(f"Listo. {EXTRA_ANALYSIS_OFFER}\n1. 1701 Coprológico\n2. 1702 Coproscópico",
                                          _test_menu_options=[{"code": "1701"}, {"code": "1702"}]))
    assert opciones_cerradas.CLAVE not in out["captured_fields"]
    assert "Dejarla así" not in out["reply"]


# ── Entrada: traducir la elección ───────────────────────────────────────────────────


@pytest.mark.parametrize("msg", ["2", "2.", " 2 ", "opción 2", "opcion 2", "la 2", "2)"])
def test_el_numero_se_traduce_al_texto_de_la_opcion(msg):
    prev = {opciones_cerradas.CLAVE: {"1": "sí, quiero agregar otro análisis", "2": "no, la dejamos así"}}
    assert opciones_cerradas.traducir(prev, msg) == "no, la dejamos así"
    assert opciones_cerradas.CLAVE not in prev, "la marca vive un solo turno"


@pytest.mark.parametrize("msg", ["no", "2 y sin observaciones", "1701", "7", ""])
def test_lo_que_no_es_una_eleccion_queda_intacto_y_borra_la_marca(msg):
    prev = {opciones_cerradas.CLAVE: {"1": "a", "2": "b"}}
    assert opciones_cerradas.traducir(prev, msg) == msg
    assert opciones_cerradas.CLAVE not in prev


def test_sin_marca_un_numero_no_se_toca():
    prev = {"_test_menu_options": [{"code": "1701"}]}
    assert opciones_cerradas.traducir(prev, "2") == "2"


# ── De punta a punta con el estado real del chat 1 ──────────────────────────────────


def _hist_con_opciones():
    bot = HIST1[-1]["content"] + "\n1. Otra orden para otro paciente\n2. Continuar con el pago"
    return HIST1[:-1] + [{"role": "bot", "content": bot}]


def test_2_a_la_oferta_del_pedido_cierra_y_pide_el_pago():
    estado = dict(CHAT1_TRAS_REGISTRAR, **{opciones_cerradas.CLAVE: {
        "1": "otra orden para otro paciente", "2": "no, eso es todo, cerramos el pedido"}})
    reply, f, _ = turno("2", "unclear", estado, "fase_6_cierre", _hist_con_opciones())
    assert reply.startswith(agent.PEDIDO_CLOSING_QUESTION)
    assert f.get("_pedido_awaiting_payment")
    assert reply.endswith("1. Contraentrega con el motorizado\n2. Pago en línea"), "la pregunta del pago sale numerada"
    assert f[opciones_cerradas.CLAVE]["1"] == "contraentrega"


def test_1_a_la_oferta_del_pedido_arranca_otra_orden():
    estado = dict(CHAT1_TRAS_REGISTRAR, **{opciones_cerradas.CLAVE: {
        "1": "otra orden para otro paciente", "2": "no, eso es todo, cerramos el pedido"}})
    reply, f, _ = turno("1", "unclear", estado, "fase_6_cierre", _hist_con_opciones())
    assert reply != agent.PEDIDO_CLOSING_QUESTION and reply != agent.PEDIDO_OFFER_REASK
    assert not f.get("_pedido_awaiting_payment")
    assert "orden" in reply.lower()


def test_la_oferta_del_pedido_sale_numerada_al_registrar():
    """El propio mensaje de registro («¿Necesitas cargar otra orden…?») lleva las opciones."""
    out = opciones_cerradas.agregar(_resp("Quedó registrado:\n- Paciente: Roku\n\nNúmero de orden: A3-2026-003\n\n" + PEDIDO_CLOSING_PROMPT))
    assert out["reply"].endswith("1. Otra orden para otro paciente\n2. Continuar con el pago")


def test_2_a_agregar_otro_analisis_sigue_con_la_observacion():
    """«¿Agregamos otro análisis…?» numerada → «2» = «no, la dejamos así» → pregunta la
    observación, también numerada."""
    from tests.test_prueba_real_whatsapp_20261029 import CHAT3_ANTES_DE_CODIGOS
    estado = dict(CHAT3_ANTES_DE_CODIGOS, selected_tests=["1701", "2057"], exam_type="Perfil personalizado (2 análisis)",
                  removed_tests=[], observations=None, _awaiting_additional_test="add",
                  **{opciones_cerradas.CLAVE: {"1": "sí, quiero agregar otro análisis", "2": "no, la dejamos así"}})
    estado.pop("_correction_pending")
    hist = [{"role": "user", "content": "1701 y 2057"},
            {"role": "bot", "content": f"Listo, agrego 1701-Coprológico, 2057-Panleucopenia. {EXTRA_ANALYSIS_OFFER}\n1. Agregar otro análisis\n2. Dejarla así"}]
    reply, f, _ = turno("2", "unclear", estado, "fase_2_recogida_datos", hist)
    assert sorted(f.get("selected_tests") or []) == ["1701", "2057"], "no se pierde la selección"
    assert opciones_cerradas.OBSERVACION_PREGUNTA in reply
    assert reply.endswith("1. Dejar una observación\n2. Sin observaciones")


def test_2_en_la_reoferta_de_datos_heredados_pide_la_direccion():
    from tests.test_prueba_real_whatsapp_20261029 import CHAT3_ANTES_DE_CODIGOS
    estado = dict(CHAT3_ANTES_DE_CODIGOS, patient_name=None, species=None, breed=None, sex=None, patient_age=None,
                  owner_name=None, sample_taken_date=None, pickup_address="Calle 10 # 20-30", _address_confirmed=True,
                  exam_type=None, selected_tests=None, _stable_confirm_pending=True,
                  **{opciones_cerradas.CLAVE: {"1": "confirmo", "2": "quiero cambiar la dirección", "3": "quiero cambiar el médico"}})
    estado.pop("_correction_pending")
    hist = [{"role": "user", "content": "otra orden"},
            {"role": "bot", "content": "Perfecto, creamos otra orden de servicio. Mantengo estos datos de la orden anterior:\n"
                                       "- Dirección de retiro: Calle 10 # 20-30\n¿Confirmas o quieres cambiar alguno (dirección, médico o análisis)?\n"
                                       "1. Confirmar estos datos\n2. Cambiar la dirección\n3. Cambiar el médico\n4. Cambiar el análisis"}]
    reply, f, _ = turno("2", "unclear", estado, agent.CONFIRMATION_PHASE, hist)
    assert "dirección" in reply.lower()
    assert not f.get("pickup_address")
