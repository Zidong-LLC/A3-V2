"""El motorizado por WhatsApp (pedido del usuario, 10/11): se lo reconoce por el celular de su
tarjeta, ve sus recogidas pendientes y marca una como recogida en dos toques."""
from datetime import date
from unittest.mock import patch

from app import motorizado_chat as mc

CESAR = {"id": "c-1", "name": "Cesar Rojas", "phone": "3503297922", "chatwoot_conversation_id": None}
HOY = date(2026, 11, 10)


def _orden(numero, fecha="2026-11-11", clinica="Varvet", direccion="Cr 1 38 128", id_=None):
    return {"id": id_ or f"r-{numero}", "order_number": numero, "scheduled_pickup_date": fecha,
            "pickup_address": direccion, "clients": {"clinic_name": clinica}}


# ── Reconocimiento por celular ───────────────────────────────────────────────

def test_reconoce_al_motorizado_aunque_whatsapp_mande_el_indicativo():
    assert mc.motorizado_por_telefono("+573503297922", [CESAR]) is CESAR


def test_un_numero_que_no_es_de_ningun_motorizado_no_cuenta():
    assert mc.motorizado_por_telefono("+573001112233", [CESAR]) is None
    assert mc.motorizado_por_telefono("", [CESAR]) is None


def test_los_telefonos_de_relleno_no_coinciden_con_nadie():
    relleno = {**CESAR, "phone": "0006ab874ea22"}
    assert mc.motorizado_por_telefono("+570006874220", [relleno]) is None


# ── Qué orden nombra el mensaje ─────────────────────────────────────────────

PENDIENTES = [_orden("A3-2026-013"), _orden("A3-2026-014", clinica="Hocicos")]


def test_nombra_la_orden_completa_o_solo_su_numero():
    assert [o["order_number"] for o in mc.ordenes_mencionadas("recogí la 13", PENDIENTES)] == ["A3-2026-013"]
    assert [o["order_number"] for o in mc.ordenes_mencionadas("ya tengo A3-2026-014", PENDIENTES)] == ["A3-2026-014"]


def test_el_3_de_a3_y_los_numeros_ajenos_no_son_ordenes():
    assert mc.ordenes_mencionadas("Hola A3, buenos días", [_orden("A3-2026-003")]) == []
    assert mc.ordenes_mencionadas("voy en 25 minutos", PENDIENTES) == []


def test_solo_el_boton_exacto_confirma():
    assert mc.orden_confirmada("Recogí A3-2026-013") == "A3-2026-013"
    assert mc.orden_confirmada("recogi a3-2026-013") == "A3-2026-013"
    assert mc.orden_confirmada("recogí la 13") is None
    assert mc.orden_confirmada("¿dónde queda la A3-2026-013?") is None


# ── La lista ─────────────────────────────────────────────────────────────────

def test_la_lista_agrupa_atrasadas_hoy_y_manana():
    texto = mc.mensaje_lista("Cesar Rojas", [
        _orden("A3-2026-020", fecha="2026-11-12"), _orden("A3-2026-011", fecha="2026-11-08"),
        _orden("A3-2026-015", fecha="2026-11-10"), _orden("A3-2026-016", fecha="2026-11-11"),
    ], HOY)
    assert texto.startswith("Hola Cesar 👋")
    assert texto.index("Atrasadas") < texto.index("Hoy 10/11") < texto.index("Mañana 11/11") < texto.index("Jueves 12/11")
    assert "era para el 08/11" in texto
    assert "Cr 1 38 128" in texto and "Varvet" in texto


def test_sin_recogidas_lo_dice_y_pide_que_escriba_cada_manana():
    texto = mc.mensaje_lista("Cesar", [], HOY)
    assert "No tienes recogidas pendientes" in texto
    assert "cada mañana" in texto


# ── atender(): la entrada desde WhatsApp ─────────────────────────────────────

def _atender(texto, pendientes=None, couriers=(CESAR,), canal="whatsapp", telefono="+573503297922"):
    with patch("app.motorizado_chat.db.list_active_couriers", return_value=list(couriers)), \
         patch("app.motorizado_chat.db.update_courier") as vincular, \
         patch("app.motorizado_chat.db.update_request") as estado, \
         patch("app.motorizado_chat.db.create_request_event") as evento, \
         patch("app.motorizado_chat.maestros_db.recogidas_pendientes",
               return_value=list(pendientes if pendientes is not None else PENDIENTES)), \
         patch("app.motorizado_chat.chatwoot.send_message") as mensaje, \
         patch("app.motorizado_chat.chatwoot.send_options") as botones:
        atendido = mc.atender("77", texto, canal, telefono)
    return atendido, {"vincular": vincular, "estado": estado, "evento": evento,
                      "mensaje": mensaje, "botones": botones}


def test_un_cliente_sigue_al_flujo_de_siempre():
    atendido, m = _atender("Hola", telefono="+573001112233")
    assert atendido is False
    m["mensaje"].assert_not_called()


def test_fuera_de_whatsapp_no_se_mira():
    assert _atender("Hola", canal="chatwoot")[0] is False


def test_el_motorizado_recibe_su_lista_y_queda_vinculado():
    atendido, m = _atender("Hola")
    assert atendido is True
    m["vincular"].assert_called_once_with("c-1", {"chatwoot_conversation_id": "77"})
    assert "A3-2026-013" in m["mensaje"].call_args.args[1]
    m["estado"].assert_not_called()


def test_ya_vinculado_no_se_vuelve_a_guardar():
    atendido, m = _atender("Hola", couriers=({**CESAR, "chatwoot_conversation_id": "77"},))
    m["vincular"].assert_not_called()


def test_nombrar_una_orden_pregunta_con_boton_y_no_la_marca():
    _, m = _atender("recogí la 13")
    m["estado"].assert_not_called()
    m["botones"].assert_called_once()
    assert m["botones"].call_args.args[2][0]["title"] == "Recogí A3-2026-013"
    assert len(m["botones"].call_args.args[2][0]["title"]) <= 20


def test_el_boton_marca_la_orden_como_recogida():
    _, m = _atender("Recogí A3-2026-013")
    m["estado"].assert_called_once_with("r-A3-2026-013", {"status": "picked_up"})
    evento = m["evento"].call_args.args
    assert evento[2]["source"] == "whatsapp_motorizado" and evento[2]["updated_by"] == "Cesar Rojas"
    assert "quedó como recogida" in m["mensaje"].call_args.args[1]
    assert "Te quedan 1 pendientes" in m["mensaje"].call_args.args[1]


def test_no_se_marca_una_orden_que_no_es_suya():
    _, m = _atender("Recogí A3-2026-099")
    m["estado"].assert_not_called()
    assert "no está entre tus recogidas" in m["mensaje"].call_args.args[1]


def test_si_no_se_puede_mirar_la_base_sigue_el_flujo_de_siempre():
    with patch("app.motorizado_chat.db.list_active_couriers", side_effect=RuntimeError("caída")), \
         patch("app.motorizado_chat.notify_error") as alerta:
        assert mc.atender("77", "Hola", "whatsapp", "+573503297922") is False
    alerta.assert_called_once()


def test_si_falla_despues_de_reconocerlo_se_disculpa_y_no_cae_al_flujo_de_clientes():
    with patch("app.motorizado_chat.db.list_active_couriers", return_value=[CESAR]), \
         patch("app.motorizado_chat.db.update_courier"), \
         patch("app.motorizado_chat.maestros_db.recogidas_pendientes", side_effect=RuntimeError("x")), \
         patch("app.motorizado_chat.notify_error") as alerta, \
         patch("app.motorizado_chat.chatwoot.send_message") as mensaje:
        assert mc.atender("77", "Hola", "whatsapp", "+573503297922") is True
    alerta.assert_called_once()
    assert mensaje.call_args.args[1] == mc.PROBLEMA


# ── main: el motorizado va antes de la autorización de datos y del agente ────

def test_el_motorizado_no_pasa_por_privacidad_ni_por_el_agente():
    from app import main

    with patch("app.main.motorizado_chat.atender", return_value=True), \
         patch("app.main.privacidad.atender") as privacidad, \
         patch("app.main.process_turn") as agente:
        main._process_chatwoot("77", "Hola", "whatsapp", "+573503297922")
    privacidad.assert_not_called()
    agente.assert_not_called()


def test_un_cliente_sigue_pasando_por_privacidad():
    from app import main

    with patch("app.main.motorizado_chat.atender", return_value=False), \
         patch("app.main.privacidad.atender", return_value=True) as privacidad, \
         patch("app.main.process_turn") as agente:
        main._process_chatwoot("78", "Hola", "whatsapp", "+573001112233")
    privacidad.assert_called_once()
    agente.assert_not_called()
