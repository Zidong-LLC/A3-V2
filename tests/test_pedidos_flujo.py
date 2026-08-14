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
from app.detectors import _is_bare_confirmation, _is_order_confirmation
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


def test_fijado_el_analisis_el_sistema_toma_el_turno():
    """El hueco que dejaba mandar al modelo. Entre "se fijó el análisis" y "la orden está
    completa" queda la observación (desde el 28/07 va después del análisis). Ahí este enforcer
    cedía y el modelo improvisaba su propia pregunta — el flujo daba vueltas sin llegar al
    resumen, y peor, decía haber agregado análisis que no agregaba. Ahora el sistema toma el
    turno y ofrece agregar otro análisis, que es el paso que corresponde."""
    base = {k: v for k, v in ORDEN_COMPLETA.items()
            if k not in ("observations", "exam_type", "_selected_profile_code",
                         "_selected_profile_name", "_selected_profile_price")}
    fields = dict(base, selected_tests=["1101"])
    ai = {"intent": "route_scheduling", "captured_fields": fields,
          "reply": "¿Quieres agregar otro análisis o ya lo cerramos así?"}
    with patch.object(eorden.db, "get_tests_by_codes", return_value=[]):
        out = eorden._enforce_extra_analysis_offer(SESSION, ai, base)
    assert extra_analysis_offer() in out["reply"], "la respuesta la controla el sistema"
    assert fields.get("_offering_extra_analysis") is True


def test_las_dos_preguntas_van_separadas():
    """Decisión del usuario (2026-08-14): la oferta de agregar análisis y la observación son
    preguntas DISTINTAS, una por turno. Juntas, un "no" seco no dice a cuál responde — que es
    donde el modelo se confundía. Separadas, el contexto lo vuelve inequívoco."""
    oferta = extra_analysis_offer()
    assert "observaci" not in oferta.lower(), "la observación se pregunta en su propio turno"
    # Y es CERRADA: las dos alternativas están explícitas en la frase.
    assert "?" in oferta and " o " in oferta


def test_declinar_la_oferta_lleva_a_la_observacion():
    """El "no" a la oferta pasa al paso siguiente, que es la observación — no al resumen ni al
    pago. Es el orden que pidió A3 (análisis, después observación)."""
    fields = {k: v for k, v in ORDEN_COMPLETA.items() if k != "observations"}
    fields["_offering_extra_analysis"] = True
    out = eorden._handle_extra_analysis_answer(SESSION, fields, "no")
    assert out is not None
    assert "observaci" in out["reply"].lower()
    assert fields.get("_offering_extra_analysis") is None


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


def test_agregar_en_la_confirmacion_no_deja_encendida_la_oferta():
    """LA CAUSA del bug del 2026-08-14. `_enforce_extra_analysis_offer` corre ANTES que el
    enforcer de confirmación, así que al agregar un análisis desde el resumen encendía
    `_offering_extra_analysis`; el resumen se mostraba igual, pero la marca quedaba viva
    detrás. En el turno siguiente el "Si" del cliente lo agarraba
    `_handle_extra_analysis_answer` como "sí, quiero agregar otro" y la orden no se
    registraba nunca."""
    GLUCOSA = {"code": "0201", "name": "Glucosa", "price": 18000, "category": "Química"}
    fields = dict(ORDEN_COMPLETA, _offering_extra_analysis=True)
    with patch.object(econf.db, "get_tests_by_codes_or_names", return_value=[GLUCOSA]), \
         patch.object(econf.db, "get_tests_by_codes", return_value=[GLUCOSA]):
        econf._confirmation_analysis_adjustment(
            SESSION, fields, "quiero agregar sodio y potasio", "correction")
    assert fields.get("_offering_extra_analysis") is None
    assert fields.get("_awaiting_additional_test") is None


def test_la_oferta_no_se_enciende_estando_en_la_confirmacion():
    """La raíz de la raíz: en la confirmación el resumen YA ofrece agregar análisis, así que
    el carril paralelo no debe activarse y dejar estado colgado."""
    en_confirmacion = dict(SESSION, phase_current=agent.CONFIRMATION_PHASE)
    base = dict(ORDEN_COMPLETA)
    fields = dict(base, selected_tests=["1101"])
    ai = {"intent": "route_scheduling", "captured_fields": fields, "reply": "(del modelo)"}
    out = eorden._enforce_extra_analysis_offer(en_confirmacion, ai, base)
    assert fields.get("_offering_extra_analysis") is None
    assert out["reply"] == "(del modelo)"


def test_un_si_pelado_en_la_confirmacion_no_pide_analisis():
    """El síntoma exacto que vio el usuario: respondió "Si" al resumen y el bot le contestó
    "¿Qué análisis quieres agregar?". Red por si la marca vuelve a colarse."""
    en_confirmacion = dict(SESSION, phase_current=agent.CONFIRMATION_PHASE)
    fields = dict(ORDEN_COMPLETA, _offering_extra_analysis=True)
    out = eorden._handle_extra_analysis_answer(en_confirmacion, fields, "Si")
    assert out is None, "tiene que ceder para que el cierre determinístico registre la orden"
    assert fields.get("_offering_extra_analysis") is None


def test_un_si_que_ademas_pide_agregar_si_agrega():
    """Contraprueba (L49): el guard solo se lleva el "sí" PELADO. "sí, pero agrégale glucosa"
    trae una intención más y el carril tiene que actuar."""
    GLUCOSA = {"code": "0201", "name": "Glucosa", "price": 18000, "category": "Química"}
    fields = dict(ORDEN_COMPLETA)
    with patch.object(econf.db, "get_tests_by_codes_or_names", return_value=[GLUCOSA]), \
         patch.object(econf.db, "get_tests_by_codes", return_value=[GLUCOSA]):
        out = econf._confirmation_analysis_adjustment(
            SESSION, fields, "sí, pero agrégale glucosa", "correction")
    assert out is not None and out["phase"] == agent.CONFIRMATION_PHASE


def test_una_negacion_ambigua_repregunta_en_vez_de_adivinar():
    """Pedido del usuario (2026-08-14): *"si la respuesta es muy ambigua, repreguntá o pedile
    que especifique"*. Caso real: "No confirmo los datos no quiero agregar otro análisis" —
    niega las dos cosas, que llevan a lados opuestos. Antes quedaba en bucle preguntando qué
    análisis agregar."""
    fields = dict(ORDEN_COMPLETA, _awaiting_additional_test="add")
    out = econf._confirmation_analysis_adjustment(
        SESSION, fields, "No confirmo los datos no quiero agregar otro análisis", "negate")
    assert out is not None
    assert "no me quedó claro" in out["reply"].lower()
    assert fields.get("_awaiting_additional_test") is None, "tiene que soltar el carril"


SODIO = {"code": "1405", "name": "Sodio", "price": 12000, "category": "Química"}
POTASIO = {"code": "1404", "name": "Potasio", "price": 12000, "category": "Química"}


@pytest.mark.parametrize("mensaje", [
    "si quiero agreagar sodio y potasio",   # el typo EXACTO de la prueba en vivo
    "si quiero agregar sodio y potasio",
    "dale, sumale sodio y potasio",
    "ok, metele sodio y potasio",
    "confirmo pero añadime sodio y potasio",
])
def test_agregar_analisis_se_aplica_de_verdad_aunque_haya_typos(mensaje):
    """EL BUG DE DINERO del 2026-08-14. El cliente escribió "agreagar" con un typo:
    `_wants_partial_analysis_change` da True con "agregar" y False con el typo, así que el
    guard de ese día leyó el mensaje como confirmación pelada y CEDIÓ el turno al modelo. Sin
    el carril determinístico nadie resolvió nada contra el catálogo: el bot contestó "Perfecto,
    agrego Sodio y Potasio" con `selected_tests` VACÍO. La orden habría salido sin los análisis
    pedidos y facturada de menos, sin que el cliente pudiera notarlo.

    Se verifica el ESTADO, no el texto: este bug pasó desapercibido justamente porque la
    respuesta decía lo correcto."""
    fields = dict(ORDEN_COMPLETA)
    with patch.object(econf.db, "get_tests_by_codes_or_names", return_value=[SODIO, POTASIO]), \
         patch.object(econf.db, "get_tests_by_codes", return_value=[SODIO, POTASIO]):
        out = econf._confirmation_analysis_adjustment(SESSION, fields, mensaje, "correction")
    assert out is not None, "el sistema tiene que tomar el turno, no cederlo al modelo"
    guardados = set(agent._as_text_items(fields.get("selected_tests")))
    assert {"1405", "1404"} <= guardados, f"no se guardaron: {guardados}"


def test_si_no_se_pudo_agregar_el_bot_no_dice_que_lo_agrego():
    """El acuse no puede adelantarse al estado. Si el catálogo devuelve algo que después no
    queda en la orden, hay que decirlo y preguntar — nunca un "listo, lo agregué" falso."""
    fields = dict(ORDEN_COMPLETA)
    FANTASMA = {"code": None, "name": None, "price": 0}
    with patch.object(econf.db, "get_tests_by_codes_or_names", return_value=[FANTASMA]), \
         patch.object(econf.db, "get_tests_by_codes", return_value=[]), \
         patch.object(econf, "_add_tests_to_order", lambda f, r, a: None):
        out = econf._confirmation_analysis_adjustment(
            SESSION, fields, "agregame un sodio", "correction")
    assert out is not None
    reply = out["reply"].lower()
    assert "no pude agregar" in reply, "tiene que admitir que no lo agregó"
    assert "listo, agrego" not in reply


def test_pedir_cambiar_otro_dato_no_entra_al_carril_de_analisis():
    """Contraprueba: "quiero cambiar el médico" también es `correction`, pero no es un ajuste
    de análisis — si este carril se lo tragara, el cliente no podría corregir nada más."""
    out = econf._confirmation_analysis_adjustment(
        SESSION, dict(ORDEN_COMPLETA), "quiero cambiar el médico", "correction")
    assert out is None or "análisis" not in (out.get("reply") or "").lower()


# ── 1c. La segunda orden: el atajo no puede tragarse la oración ────────────────

@pytest.mark.parametrize("mensaje", [
    "Si análisis quiero perfil 653",
    "dale pero cambiame el análisis al 653",
    "confirmo, aunque esta vez va el 653",
    "sí, todo igual salvo el análisis: el 653",
    "ok, igual que antes pero con el 653",
])
def test_un_si_con_algo_mas_no_es_una_confirmacion_pelada(mensaje):
    """El bloque del reofrecimiento de estables es determinístico y corre ANTES del modelo:
    solo ve palabras. Con "Si análisis quiero perfil 653" se quedaba con el "Si" inicial,
    contestaba su plantilla y tiraba el resto — el 653 se perdía y la orden seguía con el
    perfil HEREDADO que el cliente pedía cambiar (prueba en vivo 2026-08-14).

    El criterio no es "¿contiene un sí?" sino "¿queda algo si le sacamos el sí?", así que
    funciona con cualquier fraseo y no hay que ir agregando casos a una lista."""
    assert _is_order_confirmation(mensaje), "todas empiezan confirmando"
    assert not _is_bare_confirmation(mensaje), "…pero ninguna es SOLO una confirmación"


@pytest.mark.parametrize("mensaje", ["Si", "si", "dale", "correcto", "ok, listo",
                                     "sí, gracias", "Si, por favor"])
def test_un_si_pelado_sigue_siendo_pelado(mensaje):
    """Contraprueba: el atajo tiene que seguir resolviendo el caso simple sin llamar al modelo."""
    assert _is_bare_confirmation(mensaje)


def test_confirmar_pidiendo_otro_analisis_suelta_el_perfil_heredado():
    """La parte de DINERO. Aunque el turno se ceda al modelo, el análisis de la orden anterior
    tiene que soltarse acá: si sobrevive, el enforcer de integridad lo restaura y la orden
    queda con el perfil del paciente anterior (familia ERR-077/103/105/106)."""
    campos = dict(ORDEN_COMPLETA, _stable_confirm_pending=True)
    agent._clear_field_for_correction(campos, "exam_type")
    assert not campos.get("exam_type")
    assert not campos.get("_selected_profile_code"), "el código del perfil viejo también se va"


def test_dar_el_nombre_del_paciente_no_acusa_el_analisis():
    """El "clash" que reportó el usuario: respondió "Pedro" (nombre del paciente) y el bot le
    contestó "Listo, queda Perfil Prequirúrgico I". El análisis también cambia solo —al
    heredarse o al resolverse su precio—, así que el acuse le toca al dato que el cliente
    entregó de verdad."""
    base = {k: v for k, v in ORDEN_COMPLETA.items() if k != "patient_name"}
    fields = dict(base, patient_name="Pedro",
                  _selected_profile_code="152", _selected_profile_name="Perfil Prequirúrgico I")
    base.pop("_selected_profile_code", None)
    ai = {"intent": "route_scheduling", "captured_fields": fields, "reply": "(del modelo)"}
    out = eorden._enforce_extra_analysis_offer(SESSION, ai, base)
    assert out["reply"] == "(del modelo)", "el acuse del análisis no puede pisar este turno"


def test_si_lo_unico_que_cambia_es_el_analisis_el_enforcer_sigue_actuando():
    """No re-romper ERR-108: cuando el turno SÍ fue sobre el análisis, este enforcer tiene que
    seguir tomándolo en vez de dejar improvisar al modelo."""
    base = {k: v for k, v in ORDEN_COMPLETA.items()
            if k not in ("observations", "exam_type", "_selected_profile_code",
                         "_selected_profile_name", "_selected_profile_price")}
    fields = dict(base, selected_tests=["1101"])
    ai = {"intent": "route_scheduling", "captured_fields": fields, "reply": "(del modelo)"}
    with patch.object(eorden.db, "get_tests_by_codes", return_value=[]):
        out = eorden._enforce_extra_analysis_offer(SESSION, ai, base)
    assert out["reply"] != "(del modelo)"
    assert extra_analysis_offer() in out["reply"]


# ── 1d. El paquete heredado no sobrevive al cambio de análisis ─────────────────

@pytest.mark.parametrize("mensaje", [
    "analisis quiero el 653",       # la frase EXACTA de la prueba en vivo
    "quiero el 653",
    "mejor el 653",
    "cambialo al 653",
    "Si análisis quiero perfil 653",
    "todo igual menos el análisis",
])
def test_cambiar_el_analisis_reofrecido_suelta_tambien_los_agregados(mensaje):
    """DINERO (prueba en vivo 2026-08-14): la orden 1 llevaba el perfil 152 + Sodio y Potasio
    agregados. En la orden 2 el cliente pidió el 653; el enforcer reemplazó el perfil base
    pero los AGREGADOS heredados sobrevivieron — el resumen dio $82.000 en vez de $58.000,
    con análisis que el cliente nunca pidió en esa orden.

    `_replaces_offered_analysis` decide con el campo detectado o el código, no con verbos:
    "analisis quiero el 653" no lleva 'cambiar' ni 'otro' ni 'sí', y aun así reemplaza."""
    assert agent._replaces_offered_analysis(mensaje, "152") is True
    # Y la limpieza que dispara borra el paquete COMPLETO, agregados incluidos:
    campos = dict(ORDEN_COMPLETA, selected_tests=["1405", "1404"], removed_tests=[])
    agent._clear_field_for_correction(campos, "exam_type")
    assert not campos.get("selected_tests"), "los agregados heredados tienen que soltarse"
    assert not campos.get("_selected_profile_code")


@pytest.mark.parametrize("mensaje", [
    "si", "jose", "es un canino", "3 años",
    "quiero cambiar el médico",
    "el mismo pero sin la glucosa",   # parcial → personalización, no reemplazo
])
def test_lo_que_no_cambia_el_analisis_no_suelta_el_paquete(mensaje):
    assert agent._replaces_offered_analysis(mensaje, "152") is False


# ── 1e. "No quiero los agregados" quita los agregados ──────────────────────────

@pytest.mark.parametrize("mensaje", [
    "en esta orden no quiero los agregados",   # la frase EXACTA de la prueba en vivo
    "sin los agregados",
    "quitale los agregados",
    "sacame lo agregado",
])
def test_no_quiero_los_agregados_se_reconoce(mensaje):
    """'Agregados' es el rótulo que el bot imprime en el resumen: el cliente lo cita textual.
    Antes caía en la repregunta genérica '¿Qué dato quieres corregir?'."""
    assert agent._removes_the_additions(mensaje) is True


@pytest.mark.parametrize("mensaje", [
    "quiero agregar sodio",            # agregar ≠ quitar los agregados
    "no quiero cambiar nada",          # no menciona el rótulo
    "quitale el sodio",                # análisis puntual: lo maneja el ajuste existente
])
def test_referencias_que_no_son_quitar_los_agregados(mensaje):
    assert agent._removes_the_additions(mensaje) is False


# ── 1f. El snapshot no revive códigos que el cliente no nombró ─────────────────

def test_el_snapshot_no_revive_los_agregados_limpiados():
    """ERR-114 (prueba en vivo 2026-08-14 21:19): la limpieza de ERR-112 corrió bien, pero el
    MODELO re-emitió [1405, 1404] porque los vio en el historial, y el anclaje tenía una
    excepción que dejaba pasar sin verificar cualquier código presente en el snapshot de la
    orden anterior. Los agregados revivían y la orden 2 salía $24.000 más cara.

    Regla: un código que el cliente no nombró no entra, venga de donde venga."""
    from app.enforcers import catalogo as ecat
    prev = {
        "_client_found": True, "species": "Canino",
        "selected_tests": None,                      # limpiado por el cambio de análisis
        "_prev_order_snapshot": {"selected_tests": ["1405", "1404"]},
    }
    fields = dict(prev, selected_tests=["1405", "1404"],   # el modelo los re-emite
                  _selected_profile_code="653", exam_type="Perfil Senior Canino III")
    ai = {"intent": "route_scheduling", "requires_handoff": False,
          "captured_fields": fields, "reply": "(del modelo)"}
    SODIO = {"code": "1405", "name": "Sodio", "price": 12000, "category": "Química"}
    POTASIO = {"code": "1404", "name": "Potasio", "price": 12000, "category": "Química"}
    with patch.object(ecat.db, "list_catalog_tests", return_value=[SODIO, POTASIO]):
        out = ecat._enforce_selected_tests_grounding(
            {"client_id": "c1"}, ai, prev, "laura", [])
    guardados = set(agent._as_text_items(out["captured_fields"].get("selected_tests")))
    assert not ({"1405", "1404"} & guardados), \
        f"el anclaje tiene que descartar los códigos no nombrados: {guardados}"


def test_los_heredados_activos_no_pasan_por_el_anclaje():
    """Contraprueba: si los heredados siguen ACTIVOS están en prev.selected_tests, no son
    'nuevos' y el anclaje ni interviene — la reoferta confirmada sigue funcionando."""
    from app.enforcers import catalogo as ecat
    prev = {"_client_found": True, "selected_tests": ["1405", "1404"],
            "_prev_order_snapshot": {"selected_tests": ["1405", "1404"]}}
    fields = dict(prev)
    ai = {"intent": "route_scheduling", "requires_handoff": False,
          "captured_fields": fields, "reply": "(del modelo)"}
    out = ecat._enforce_selected_tests_grounding({"client_id": "c1"}, ai, prev, "si", [])
    assert out["reply"] == "(del modelo)"
    assert agent._as_text_items(out["captured_fields"].get("selected_tests")) == ["1405", "1404"]


# ── 1g. El carril del pedido mixto no cruza la frontera entre órdenes ──────────

def test_el_texto_del_pedido_mixto_no_sobrevive_a_la_frontera():
    """LA vía real de ERR-114 (diagnóstico instrumentado 2026-08-15). `_mixed_request_text`
    guarda el TEXTO del pedido original para re-escanearlo al fijar el perfil (ERR-076,
    correcto DENTRO de una orden). Fuera de `_ORDER_RESET_FIELDS`, sobrevivía a la frontera y
    en la orden 2 ese texto viejo resucitaba los análisis de la orden 1: $24.000 de más."""
    for marca in ("_mixed_request_text", "_pending_ambiguous_items", "_pending_offer_count"):
        assert marca in agent._ORDER_RESET_FIELDS, marca


def test_cambiar_el_analisis_tambien_suelta_el_texto_mixto():
    campos = dict(ORDEN_COMPLETA, _mixed_request_text="un prequirúrgico, sodio y potasio",
                  _pending_ambiguous_items=["orina"], _pending_offer_count=1)
    agent._clear_field_for_correction(campos, "exam_type")
    assert "_mixed_request_text" not in campos
    assert "_pending_ambiguous_items" not in campos
    assert "_pending_offer_count" not in campos


def test_fijar_un_perfil_con_texto_mixto_viejo_no_resucita_analisis():
    """El guion exacto del enforcer: orden nueva limpia + `_mixed_request_text` de la orden
    ANTERIOR presente (simula el estado contaminado pre-fix) → fijar el 653 NO debe re-agregar
    sodio y potasio. Con el reset de frontera la marca ya no llega acá; este test protege el
    invariante aunque llegue."""
    SODIO = {"code": "1405", "name": "Sodio", "price": 12000, "category": "Química"}
    POTASIO = {"code": "1404", "name": "Potasio", "price": 12000, "category": "Química"}
    P653 = {"code": "653", "name": "Perfil Senior Canino III", "species": "Canino",
            "description": "…", "price": 58000}
    fields = {"_client_found": True, "species": "Canino", "selected_tests": None}
    # SIN _mixed_request_text (el reset de frontera ya la limpió): el camino feliz.
    with patch.object(eorden.db, "get_catalog_profiles_by_codes", return_value=[P653]), \
         patch.object(agent.db, "get_catalog_profiles_by_codes", return_value=[P653]), \
         patch.object(agent.db, "list_catalog_tests", return_value=[SODIO, POTASIO]), \
         patch.object(agent.db, "get_tests_by_codes_or_names", return_value=[]), \
         patch.object(agent.db, "get_tests_by_codes", return_value=[]):
        out = eorden._enforce_catalog_profile_code_selection(
            {"client_id": "c1"},
            {"intent": "route_scheduling", "captured_fields": fields, "reply": "(m)"},
            "perfil 653")
    sel = agent._as_text_items(out["captured_fields"].get("selected_tests"))
    assert not ({"1405", "1404"} & set(sel)), f"resucitaron: {sel}"
    assert out["captured_fields"].get("_selected_profile_code") == "653"


# ── 1h. El turno del cierre no deja que los null del modelo borren la orden ────

def test_sigamos_con_el_pago_no_borra_la_orden_ni_pierde_la_pregunta():
    """Prueba en vivo 2026-08-15 22:48: el cliente citó al bot textual ("sigamos con la forma
    de pago") y recibió "¿Qué análisis o perfil desean?". El cierre SÍ entendió (dejó
    `_pedido_awaiting_payment=True`), pero la fusión naif `dict(prev, **fields)` dejó que el
    exam_type=None del modelo BORRARA la orden; con la orden "incompleta", un empuje posterior
    pisó la pregunta del pago."""
    prev = dict(ORDEN_COMPLETA, _pedido_id="ped-1", _order_registered=True)
    # El modelo emite el schema completo: los campos de la orden vienen en None.
    model_fields = {k: None for k in ("exam_type", "patient_name", "selected_tests",
                                      "_selected_profile_code")}
    ai = _resp(model_fields, user_intent_signal="farewell", reply="(del modelo)")
    out = agent._enforce_open_pedido_close(SESSION, ai, prev, "sigamos con la forma de pago")
    cf = out["captured_fields"]
    assert cf["_pedido_awaiting_payment"] is True
    assert cf.get("exam_type") == ORDEN_COMPLETA["exam_type"], "el None no puede borrar la orden"
    assert cf.get("_selected_profile_code") == ORDEN_COMPLETA["_selected_profile_code"]
    from app.messages import PEDIDO_CLOSING_QUESTION as PCQ
    assert out["reply"] == PCQ


def test_el_pago_final_tampoco_pierde_las_fichas_por_nulls(monkeypatch):
    monkeypatch.setattr(agent.db, "close_pedido", lambda *a, **k: None)
    monkeypatch.setattr(agent.db, "list_pedido_requests", lambda pid: [{"id": "r1"}, {"id": "r2"}])
    monkeypatch.setattr(agent, "ALEGRA_ENABLED", False)
    fichas = [{"order_number": "A3-186", "patient_name": "Lolo", "total": 48000},
              {"order_number": "A3-187", "patient_name": "Pipo", "total": 58000}]
    prev = dict(ORDEN_COMPLETA, _pedido_id="ped-1", _pedido_awaiting_payment=True,
                _pedido_ordenes=fichas)
    model_fields = {"payment_method": "contraentrega", "_pedido_ordenes": None}
    ai = _resp(model_fields)
    out = agent._enforce_open_pedido_close(SESSION, ai, prev, "contraentrega")
    assert out["captured_fields"]["_pedido_cerrado"] is True
    assert "A3-186" in out["reply"] and "A3-187" in out["reply"], \
        "el resumen del pedido lista TODAS las órdenes aunque el modelo mande nulls"


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
