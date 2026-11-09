"""ERR-198 (prueba real por WhatsApp, 2026-11-09): el modelo propuso un análisis, el cliente
dijo «ese está bien», el bot contestó «registro…» sin guardar nada y entró en bucle. Lo que
el bot propone o dice haber registrado tiene que quedar en el estado."""
import pytest

from app import opciones_cerradas, propuesta_analisis
from app.messages import EXTRA_ANALYSIS_OFFER
from tests.test_prueba_real_whatsapp_20261029 import CATALOGO, CHAT3_ANTES_DE_CODIGOS, turno

SIN_ANALISIS = {k: v for k, v in CHAT3_ANTES_DE_CODIGOS.items() if k != "_correction_pending"}
SIN_ANALISIS = dict(SIN_ANALISIS, observations=None)
HIST = [{"role": "user", "content": "Hoy"}, {"role": "bot", "content": "Perfecto, lo anoto. ¿Qué análisis o perfil desean?"}]
PROPUESTA = "Para parasitología, lo más habitual es Coprológico $12.000. Si quieres, te ayudo a elegir un perfil."


def test_lo_que_el_bot_propone_queda_guardado_como_opcion():
    from unittest.mock import patch

    from app import agent
    sesion = {"client_id": "cli-A", "channel": "whatsapp", "phase_current": "fase_2_recogida_datos"}
    respuesta = {"intent": "route_scheduling", "requires_handoff": False, "reply": PROPUESTA,
                 "captured_fields": dict(SIN_ANALISIS)}
    with patch.object(agent, "db") as db:
        db.list_catalog_tests.return_value = list(CATALOGO.values())
        out = agent._anclar_analisis_nombrado(sesion, respuesta)
    assert out["reply"] == PROPUESTA, "la propuesta del modelo no se toca"
    assert [o["code"] for o in out["captured_fields"]["_test_menu_options"]] == ["1701"]
    assert not out["captured_fields"].get("selected_tests")


@pytest.mark.parametrize("mensaje", ["Ese está bien", "si ese", "dale", "ese", "Perfecto, ese"])
def test_aceptar_la_unica_propuesta_la_registra_con_la_oferta_numerada(mensaje):
    estado = dict(SIN_ANALISIS, _test_menu_options=[dict(CATALOGO["1701"])])
    hist = HIST + [{"role": "user", "content": "análisis de materia fecal"}, {"role": "bot", "content": PROPUESTA}]
    reply, f, _ = turno(mensaje, "affirm", estado, "fase_2_recogida_datos", hist, ai_fields={},
                        reply="Perfecto, registro Coprológico $12.000. ¿Quieres agregar otro análisis?")
    assert f.get("selected_tests") == ["1701"] and f.get("exam_type") == "1701 Coprológico"
    assert reply.startswith("Listo, registro:\n- 1701 Coprológico $12.000")
    assert reply.endswith(f"{EXTRA_ANALYSIS_OFFER}\n\n1. Agregar otro análisis\n2. Dejarla así")
    assert f.get(opciones_cerradas.CLAVE), "la pregunta sale del código, con sus opciones"


def test_si_el_bot_dice_que_registro_y_no_habia_propuesta_se_registra_de_verdad():
    reply, f, _ = turno("ese está bien", "affirm", SIN_ANALISIS, "fase_2_recogida_datos", HIST, ai_fields={},
                        reply="Perfecto, registro Coprológico $12.000. ¿Quieres agregar otro análisis o lo dejamos así?")
    assert f.get("selected_tests") == ["1701"], "antes quedaba vacío y el bot volvía a preguntar"
    assert reply.startswith("Listo, registro:\n- 1701 Coprológico $12.000") and "1. Agregar otro análisis" in reply


def test_con_varias_propuestas_un_si_no_elige_ninguna():
    estado = dict(SIN_ANALISIS, _test_menu_options=[dict(CATALOGO["1701"]), dict(CATALOGO["1702"])])
    _, f, _ = turno("si", "affirm", estado, "fase_2_recogida_datos", HIST, ai_fields={}, reply="¿Cuál de los dos prefieres?")
    assert not f.get("selected_tests")


def test_con_el_analisis_ya_fijado_no_se_ancla_nada():
    estado = dict(SIN_ANALISIS, exam_type="1702 Coproscópico", selected_tests=["1702"], removed_tests=[])
    _, f, _ = turno("¿y el coprológico cuánto vale?", "side_question", estado, "fase_2_recogida_datos", HIST,
                    ai_fields={}, reply="El Coprológico vale $12.000.")
    assert f.get("selected_tests") == ["1702"] and not f.get("_test_menu_options")


@pytest.mark.parametrize("texto,acepta", [
    ("Ese está bien", True), ("si ese", True), ("dale", True), ("con ese", True), ("ese mismo", True), ("ok", True),
    ("ese y un coproscópico", False), ("no, ese no", False), ("5 años", False), ("cuánto vale ese", False), ("", False),
])
def test_aceptar_la_propuesta(texto, acepta):
    assert propuesta_analisis.acepta_la_propuesta(texto) is acepta


def test_nombrados_exige_el_nombre_completo_y_prefiere_el_mas_largo():
    filas = list(CATALOGO.values()) + [{"code": "1705", "name": "Coproscópico con flotación", "price": 20000}]
    assert [f["code"] for f in propuesta_analisis.nombrados("registro Coproscópico con flotación $20.000", filas)] == ["1705"]
    assert [f["code"] for f in propuesta_analisis.nombrados("te sirve un Coprológico o un Coproscópico", filas)] == ["1701", "1702"]
    assert propuesta_analisis.nombrados("un análisis de sangre general", filas) == []


def test_dos_codigos_con_el_mismo_nombre_no_se_registran_solos():
    iguales = [{"code": "2457", "name": "Chlamydophila psittaci (Punto Final)"}, {"code": "2461", "name": "Chlamydophila psittaci (Punto Final)"}]
    assert propuesta_analisis.sin_nombres_repetidos(iguales) is False
    assert propuesta_analisis.sin_nombres_repetidos(list(CATALOGO.values())) is True
