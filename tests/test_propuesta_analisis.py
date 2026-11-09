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


HIST_PROPUESTA = HIST + [{"role": "user", "content": "análisis de materia fecal"}, {"role": "bot", "content": PROPUESTA}]
CON_PROPUESTA = dict(SIN_ANALISIS, _test_menu_options=[dict(CATALOGO["1701"])])
RESPUESTA_LIBRE = "Perfecto, queda Coprológico. ¿Algo más?"


def _registrado(reply, f):
    return (f.get("selected_tests") == ["1701"] and f.get("exam_type") == "1701 Coprológico"
            and reply.startswith("Listo, registro:\n- 1701 Coprológico $12.000")
            and reply.endswith(f"{EXTRA_ANALYSIS_OFFER}\n\n1. Agregar otro análisis\n2. Dejarla así"))


@pytest.mark.parametrize("mensaje", ["Va, ese me sirve", "hágale pues con ese", "de una", "sí señor, vamos con eso que dijiste",
                                     "uy sí, justo eso era lo que necesitaba", "Ese está bien"])
def test_aceptar_con_cualquier_fraseo_registra_la_propuesta(mensaje):
    """Regla del usuario (09/11): nada de palabras mágicas. Decide la señal del modelo."""
    reply, f, _ = turno(mensaje, "affirm", CON_PROPUESTA, "fase_2_recogida_datos", HIST_PROPUESTA,
                        ai_fields={}, reply=RESPUESTA_LIBRE)
    assert _registrado(reply, f), reply
    assert f.get(opciones_cerradas.CLAVE), "la pregunta sale del código, con sus opciones"


@pytest.mark.parametrize("mensaje", ["dale", "ok ese", "listo"])
def test_sin_senal_clara_la_lista_de_palabras_queda_de_red(mensaje):
    reply, f, _ = turno(mensaje, "unclear", CON_PROPUESTA, "fase_2_recogida_datos", HIST_PROPUESTA,
                        ai_fields={}, reply=RESPUESTA_LIBRE)
    assert _registrado(reply, f), reply


@pytest.mark.parametrize("mensaje", ["nah, mejor otra cosa", "ese no me sirve", "no, eso no era"])
def test_rechazar_con_cualquier_fraseo_descarta_la_propuesta(mensaje):
    _, f, _ = turno(mensaje, "negate", CON_PROPUESTA, "fase_2_recogida_datos", HIST_PROPUESTA,
                    ai_fields={}, reply="Claro. ¿Qué análisis necesitan entonces?")
    assert not f.get("selected_tests") and not f.get("_test_menu_options"), "un «sí» posterior no debe elegirla"


@pytest.mark.parametrize("mensaje", ["Va, ese me sirve", "Hágale pues con ese", "listo sumercé, dejémoslo con ese"])
def test_el_modelo_tambien_lo_lee_como_dato_entregado_y_cuenta_como_aceptar(mensaje):
    """Con el modelo real, estas frases llegan como `provides_requested_data`, no `affirm`."""
    reply, f, _ = turno(mensaje, "provides_requested_data", CON_PROPUESTA, "fase_2_recogida_datos", HIST_PROPUESTA,
                        ai_fields={}, reply=RESPUESTA_LIBRE)
    assert _registrado(reply, f), reply


def test_pedir_otra_cosa_no_registra_la_propuesta():
    _, f, _ = turno("mejor un perfil renal", "provides_requested_data", CON_PROPUESTA, "fase_2_recogida_datos",
                    HIST_PROPUESTA, ai_fields={}, reply="Claro, te muestro los perfiles renales.")
    assert f.get("selected_tests") != ["1701"]


def test_una_correccion_tambien_descarta_la_propuesta():
    _, f, _ = turno("nah, mejor otra cosa", "correction", CON_PROPUESTA, "fase_2_recogida_datos", HIST_PROPUESTA,
                    ai_fields={}, reply="Claro. ¿Qué análisis o perfil desean en su lugar?")
    assert not f.get("selected_tests") and not f.get("_test_menu_options")


def test_aceptar_y_sumar_otro_en_la_misma_frase_registra_los_dos():
    reply, f, _ = turno("sí, y súmale también el coproscópico", "affirm", CON_PROPUESTA, "fase_2_recogida_datos",
                        HIST_PROPUESTA, ai_fields={}, reply=RESPUESTA_LIBRE)
    assert sorted(f.get("selected_tests") or []) == ["1701", "1702"], reply


def test_aceptar_con_varias_propuestas_pregunta_cual_con_numeros():
    estado = dict(SIN_ANALISIS, _test_menu_options=[dict(CATALOGO["1701"]), dict(CATALOGO["1702"])])
    reply, f, _ = turno("sí, me sirve", "affirm", estado, "fase_2_recogida_datos", HIST_PROPUESTA,
                        ai_fields={}, reply="Perfecto, registro los dos.")
    assert not f.get("selected_tests"), "no se adivina cuál"
    assert reply.startswith("¿Cuál prefieres?\n1. 1701 Coprológico ($12.000)\n2. 1702 Coproscópico ($15.000)")
    assert [o["code"] for o in f["_test_menu_options"]] == ["1701", "1702"]


def test_una_pregunta_no_es_aceptar():
    _, f, _ = turno("¿y eso cuánto demora?", "side_question", CON_PROPUESTA, "fase_2_recogida_datos", HIST_PROPUESTA,
                    ai_fields={}, reply="El resultado sale el mismo día.")
    assert not f.get("selected_tests")


def test_si_el_bot_dice_que_registro_y_no_habia_propuesta_se_registra_de_verdad():
    reply, f, _ = turno("ese está bien", "affirm", SIN_ANALISIS, "fase_2_recogida_datos", HIST, ai_fields={},
                        reply="Perfecto, registro Coprológico $12.000. ¿Quieres agregar otro análisis o lo dejamos así?")
    assert f.get("selected_tests") == ["1701"], "antes quedaba vacío y el bot volvía a preguntar"
    assert reply.startswith("Listo, registro:\n- 1701 Coprológico $12.000") and "1. Agregar otro análisis" in reply


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
