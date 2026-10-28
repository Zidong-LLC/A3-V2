"""Resultados por chat solo con nombre + NIT concordantes (ERR-187, decisión del usuario).

Antes alcanzaba con decir el nombre de una clínica para recibir sus PDF y sus avisos.
"""
from unittest.mock import MagicMock, patch

import pytest

from app import verificacion_cliente as V
from app.enforcers.resultados import DELIVER_KEY, PIDE_KEY, VERIFICADO_KEY, _enforce_results_message

CLIENTE = {"id": "c1", "clinic_name": "Veterinaria Maximascotas Lulu", "tax_id": "97448373-9"}
RESULTADO = {"id": "r1", "client_id": "c1", "published": True, "patient_name": "Luna",
             "exam_name": "Hemograma", "order_number": "A3-00042"}


@pytest.mark.parametrize("escrito,real,esperado", [
    ("Somos Maximascotas", "Veterinaria Maximascotas Lulu", True),
    ("maximascota", "Veterinaria Maximascotas Lulu", True),        # typo de una letra
    ("veterinaria", "Veterinaria Maximascotas Lulu", False),       # el ataque del portal
    ("clinica veterinaria", "Clínica Veterinaria San Roque", False),
    ("la de san roque", "Clínica Veterinaria San Roque", True),
    ("animal pet", "Animal Pets", True),                           # todo genérico: van todas
    ("animal", "Animal Pets", False),
    ("pets", "Animal Pets", False),
    ("Otra Clinica Felina", "Veterinaria Maximascotas Lulu", False),
])
def test_el_nombre_concuerda_solo_con_una_palabra_propia(escrito, real, esperado):
    assert V.nombre_concuerda(escrito, real) is esperado


@pytest.mark.parametrize("texto,nit_real,esperado", [
    ("mi NIT es 974483739", "97448373-9", True),     # pegado con el DV
    ("97448373", "97448373-9", True),                # sin el DV
    ("97.448.373-9", "97448373-9", True),            # con puntos y guion
    ("900123456-7", "900123456", True),              # la base no guarda el DV
    ("900123456", "9001234567", True),               # la base lo guarda pegado
    ("789838306", "789838306.0", True),              # artefacto de Excel (ERR-121)
    ("97448374", "97448373-9", False),
    ("1", "1-R", False),                             # NIT de relleno: no verifica
    ("hola", "97448373-9", False),
])
def test_el_nit_se_reconoce_en_los_formatos_reales_de_la_base(texto, nit_real, esperado):
    assert V.nit_en_texto(texto, nit_real) is esperado


def _turno(intent="results", **campos):
    return {"intent": intent, "captured_fields": dict(campos), "pending_intents": [], "reply": "",
            "phase": "fase_6_cierre"}


def _con(historial):
    """Parches: el cliente identificado, lo que escribió el usuario y su resultado."""
    return (patch("app.enforcers.resultados.db.get_client_by_id", return_value=CLIENTE),
            patch("app.enforcers.resultados.db.get_recent_messages",
                  return_value=[{"role": "user", "content": t} for t in historial]),
            patch("app.results_lookup.portal_db.list_lab_results", return_value=[RESULTADO]))


SESION = {"client_id": "c1", "external_chat_id": "chat-1"}


def test_identificado_solo_por_nombre_no_recibe_pdf_y_se_le_pide_el_nit():
    a, b, c = _con(["Hola", "1", "Somos Maximascotas"])
    with a, b, c:
        r = _enforce_results_message(SESION, _turno(patient_name="Luna"), "mándame el resultado de Luna")
    assert DELIVER_KEY not in r["captured_fields"]
    assert "NIT" in r["reply"]
    assert r["captured_fields"][PIDE_KEY] == "nit"


def test_con_el_nit_correcto_se_entrega_aunque_el_modelo_lo_lea_como_identificador():
    a, b, c = _con(["Somos Maximascotas", "mándame el resultado de Luna"])
    with a, b, c:
        r = _enforce_results_message(SESION, _turno("route_scheduling", patient_name="Luna", **{PIDE_KEY: "nit"}),
                                     "974483739")
    assert r["captured_fields"][DELIVER_KEY] == ["r1"]
    assert r["captured_fields"][VERIFICADO_KEY] == "c1"


def test_identificado_por_nit_tiene_que_dar_tambien_el_nombre():
    a, b, c = _con(["NIT 97448373-9"])
    with a, b, c:
        r = _enforce_results_message(SESION, _turno(patient_name="Luna"), "el resultado de Luna")
    assert DELIVER_KEY not in r["captured_fields"]
    assert r["captured_fields"][PIDE_KEY] == "nombre"


def test_tres_nits_equivocados_y_deja_de_pedir():
    a, b, c = _con(["Somos Maximascotas"])
    campos = {"patient_name": "Luna", PIDE_KEY: "nit"}
    with a, b, c:
        for intento in range(3):
            r = _enforce_results_message(SESION, _turno(**campos), f"mi nit es 11122233{intento}")
            campos = r["captured_fields"]
            assert DELIVER_KEY not in campos
    assert "no puedo enviarte resultados" in r["reply"]
    assert PIDE_KEY not in campos


def test_si_cambia_de_tema_la_verificacion_pendiente_se_suelta():
    a, b, c = _con(["Somos Maximascotas"])
    turno = _turno("route_scheduling", **{PIDE_KEY: "nit"})
    turno["reply"] = "¿Qué análisis desean?"
    with a, b, c:
        r = _enforce_results_message(SESION, turno, "mejor programemos una recogida")
    assert r["reply"] == "¿Qué análisis desean?"
    assert PIDE_KEY not in r["captured_fields"]


def test_el_aviso_de_resultado_va_al_chat_verificado_o_al_del_ultimo_pedido():
    from app.services import portal_db

    def cliente_con(sesiones, pedidos):
        cliente = MagicMock()

        def tabla(nombre):
            q = MagicMock()
            for m in ("select", "eq", "order", "limit", "not_", "is_"):
                getattr(q, m).return_value = q
            q.not_ = q
            q.execute.return_value.data = sesiones if nombre == "telegram_sessions" else pedidos
            return q
        cliente.table.side_effect = tabla
        return cliente

    with patch.object(portal_db, "_client", cliente_con([{"external_chat_id": "v1", "channel": "whatsapp"}], [])):
        assert portal_db.chat_for_client("c1") == ("v1", "whatsapp")
    with patch.object(portal_db, "_client", cliente_con([], [{"external_chat_id": "p1", "entry_channel": "chatwoot"}])):
        assert portal_db.chat_for_client("c1") == ("p1", "chatwoot")
    with patch.object(portal_db, "_client", cliente_con([], [])):
        assert portal_db.chat_for_client("c1") is None  # identificado solo por nombre: sin aviso


@pytest.mark.parametrize("nombre,entra", [("veterinaria", False), ("clinica veterinaria", False),
                                          ("Maximascotas", True), ("veterinaria maximascotas lulu", True)])
def test_portal_exige_una_palabra_propia_del_nombre_ademas_del_nit(monkeypatch, nombre, entra):
    from app.main import app
    from app.portal import auth

    app.config["TESTING"] = True
    auth._login_attempts.clear()
    monkeypatch.setattr(auth, "find_clients_by_tax_id", lambda nit: [CLIENTE])
    r = app.test_client().post("/portal/login", data={"clinic_name": nombre, "nit": "97448373-9"})
    assert (r.status_code == 302) is entra
