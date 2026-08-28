"""Tests de la facturación en Alegra (app/billing.py + hook en app/agent.py).

No tocan la red: la API de Alegra y Supabase se mockean. La validación real contra una
cuenta Alegra de Colombia se hace con scripts (ver tasks/todo.md), no aquí.
"""
import pytest

from app import billing, agent
from app.services import alegra


# ----------------------------- build_invoice_lines -----------------------------

def test_lineas_perfil_ajustado_cuadran_con_total():
    """base (100000) - removido (8000) + agregado (12000) = 104000."""
    profile = {
        "base_profile": {"code": "PERF-01", "name": "Perfil Prequirúrgico", "price": 100000},
        "added_tests": [{"code": "T-12", "name": "Creatinina", "price": 12000}],
        "removed_tests": [{"code": "T-08", "name": "TP", "price": 8000}],
    }
    lines = billing.build_invoice_lines(profile)
    assert sum(l["price"] for l in lines) == 104000
    assert lines[0]["price"] == 92000  # base ajustado por la prueba removida
    assert lines[0]["reference"] == "PERF-01"
    assert all(l["quantity"] == 1 for l in lines)


def test_sin_profile_no_genera_lineas():
    assert billing.build_invoice_lines(None) == []


def test_profile_sin_precio_no_genera_lineas():
    profile = {"base_profile": {"name": "Sin precio", "price": 0}, "added_tests": [], "removed_tests": []}
    assert billing.build_invoice_lines(profile) == []


def test_reference_se_deriva_del_nombre_cuando_falta_codigo():
    profile = {"base_profile": {"name": "Hemograma Completo", "price": 35000},
               "added_tests": [], "removed_tests": []}
    lines = billing.build_invoice_lines(profile)
    assert lines[0]["reference"].startswith("A3-")


def test_perfil_personalizado_lleva_descuento_por_volumen():
    """ERR-062 (prueba real 2026-07-16): 4 pruebas sueltas ($48.000) se facturaban a precio
    pleno cuando el chat cotizó $41.280 (descuento por volumen 14%). El borrador debe
    facturar EXACTAMENTE lo cotizado: sin línea de perfil $0 y con el % por línea."""
    profile = {
        "base_profile": {"code": None, "name": "Perfil personalizado (4 análisis)", "price": None},
        "added_tests": [
            {"code": "1106", "name": "Hemoglobina y Hematocrito", "price": 8000},
            {"code": "1404", "name": "Potasio", "price": 12000},
            {"code": "1405", "name": "Sodio", "price": 12000},
            {"code": "1601", "name": "Parcial de Orina (14 parámetros)", "price": 16000},
        ],
        "removed_tests": [],
    }
    lines = billing.build_invoice_lines(profile)
    assert len(lines) == 4                                   # sin la línea de perfil $0
    assert all(l["discount"] == 14.0 for l in lines)         # tramo de 4 pruebas
    total = sum(round(l["price"] * (1 - l["discount"] / 100)) for l in lines)
    assert total == 41280                                    # = lo cotizado en el chat


def test_perfil_base_no_lleva_descuento_por_volumen():
    """Los perfiles armados tienen precio fijo: sus líneas van sin descuento (como el chat)."""
    profile = {
        "base_profile": {"code": "152", "name": "Perfil Prequirúrgico I", "price": 24000},
        "added_tests": [{"code": "1601", "name": "Parcial de Orina", "price": 16000}],
        "removed_tests": [],
    }
    lines = billing.build_invoice_lines(profile)
    assert all("discount" not in l for l in lines)
    assert sum(l["price"] for l in lines) == 40000


def test_invoice_order_pasa_el_descuento_a_alegra(monkeypatch):
    """El % de descuento de la línea viaja al item de la factura en Alegra."""
    monkeypatch.setattr(alegra, "get_or_create_contact", lambda *a, **k: {"id": "7"})
    monkeypatch.setattr(alegra, "get_or_create_item", lambda ref, name, price: {"id": f"i-{ref}"})
    captured = {}

    def fake_create_invoice(contact_id, items, date, due_date=None, status=None, anotation=None):
        captured["items"] = items
        return {"id": "55", "total": 41280}

    monkeypatch.setattr(alegra, "create_invoice", fake_create_invoice)
    lines = [
        {"reference": "1404", "name": "Potasio", "price": 12000, "quantity": 1, "discount": 14.0},
        {"reference": "1405", "name": "Sodio", "price": 12000, "quantity": 1},
    ]
    result = billing.invoice_order("900123456", "Vet Demo", lines, "2026-07-16")
    assert result["invoice_id"] == "55"
    assert captured["items"][0]["discount"] == 14.0
    assert "discount" not in captured["items"][1]


# ----------------------------- hook _try_invoice_in_alegra -----------------------------

def _order_and_response():
    order_info = {
        "request_id": "req-1",
        "event_payload": {"profile": {
            "base_profile": {"code": "PERF-01", "name": "Perfil", "price": 50000},
            "added_tests": [], "removed_tests": [],
        }},
    }
    ai_response = {"intent": "route_scheduling",
                   "captured_fields": {"tax_id": "900123456", "clinic_name": "Vet Demo"}}
    return order_info, ai_response


def test_hook_factura_y_guarda_evento(monkeypatch):
    captured = {}
    monkeypatch.setattr(billing, "invoice_order",
                        lambda *a, **k: {"invoice_id": "9", "contact_id": "2", "number": "1", "total": 50000})
    monkeypatch.setattr(agent.db, "create_request_event",
                        lambda rid, etype, payload: captured.update({"rid": rid, "etype": etype, "payload": payload}))
    order_info, ai_response = _order_and_response()
    agent._try_invoice_in_alegra(order_info, ai_response)
    assert captured["rid"] == "req-1"
    assert captured["etype"] == "alegra_invoiced"
    assert captured["payload"]["invoice_id"] == "9"


def test_hook_no_rompe_si_alegra_falla(monkeypatch):
    """Un fallo de Alegra no tumba el cierre, pero SÍ deja rastro.

    Antes acá se afirmaba `eventos == []`: el fallo se perdía y nadie podía
    saber qué órdenes habían quedado sin facturar. Lo que no debe romperse es
    el cierre de la orden; el registro del fallo es justamente lo que faltaba.
    """
    eventos = []
    def boom(*a, **k):
        raise alegra.AlegraError("Alegra POST /invoices -> HTTP 400")
    monkeypatch.setattr(billing, "invoice_order", boom)
    monkeypatch.setattr(agent.db, "create_request_event", lambda *a, **k: eventos.append(a))
    order_info, ai_response = _order_and_response()
    agent._try_invoice_in_alegra(order_info, ai_response)  # no debe lanzar

    assert len(eventos) == 1
    rid, etype, payload = eventos[0]
    assert (rid, etype) == ("req-1", "alegra_failed")
    assert payload["reason"] == "error_alegra"


def test_hook_no_factura_orden_sin_perfil(monkeypatch):
    llamadas = []
    monkeypatch.setattr(billing, "invoice_order", lambda *a, **k: llamadas.append(a))
    monkeypatch.setattr(agent.db, "create_request_event", lambda *a, **k: None)
    order_info = {"request_id": "req-2", "event_payload": {}}  # sin profile
    ai_response = {"intent": "route_scheduling", "captured_fields": {"tax_id": "900"}}
    agent._try_invoice_in_alegra(order_info, ai_response)
    assert llamadas == []  # sin líneas no se intenta facturar


# ----------------------------- invoice_to_row (mapeo dashboard) -----------------------------

def _alegra_invoice_sample():
    return {
        "id": 42,
        "date": "2026-06-20T00:00:00-05:00",
        "dueDate": "2026-07-20",
        "status": "open",
        "numberTemplate": {"fullNumber": "FE-1001", "prefix": "FE", "documentType": "Factura de venta"},
        "client": {"id": 7, "name": "Veterinaria Demo A3",
                   "identificationObject": {"number": "900123456", "dv": "7", "type": "NIT"}},
        "subtotal": 100000,
        "tax": 19000,
        "total": 119000,
    }


def test_invoice_to_row_mapea_campos_clave():
    row = billing.invoice_to_row(_alegra_invoice_sample(), request_id="req-9", origin="Agente")
    assert row["invoice_id"] == "42"
    assert row["number"] == "FE-1001"
    assert row["date"] == "2026-06-20"
    assert row["client_name"] == "Veterinaria Demo A3"
    assert row["client_nit"] == "900123456-7"
    assert row["subtotal"] == 100000 and row["tax"] == 19000 and row["total"] == 119000
    assert row["status"] == "open" and row["status_label"] == "Abierta"
    assert row["request_id"] == "req-9"
    assert row["is_stamped"] is False


def test_invoice_to_row_borrador_sin_stamp_ni_dv():
    inv = {"id": 1, "status": "draft", "client": {"name": "X", "identification": "53115419"}}
    row = billing.invoice_to_row(inv)
    assert row["status_label"] == "Borrador"
    assert row["client_nit"] == "53115419"
    assert row["origin"] == "Agente"
    assert row["is_stamped"] is False


def test_invoice_to_row_tolera_objeto_vacio():
    row = billing.invoice_to_row({})
    assert row["invoice_id"] == "" and row["total"] == 0 and row["number"] == "-"


def test_contact_lookup_retries_without_dv_before_create(monkeypatch):
    llamadas = []

    def fake_request(method, path, body=None):
        llamadas.append((method, path, body))
        if method == "GET" and "53115419-1" in path:
            return []
        if method == "GET" and "53115419" in path:
            return [{"id": "3", "name": "Animal Pets", "identification": "53115419"}]
        raise AssertionError("no debe crear un contacto duplicado")

    monkeypatch.setattr(alegra, "_request", fake_request)

    contact = alegra.get_or_create_contact("53115419-1", "Animal Pets")

    assert contact["id"] == "3"
    assert [call[0] for call in llamadas] == ["GET", "GET"]


# ── El paciente en la descripción de cada línea (factura real de A3, 03/08/2026) ──
# Una factura de PEDIDO junta varios pacientes: en la factura real de A3 la columna
# "Descripción" lleva el nombre del paciente de cada línea (Chilindrina Garzon, Isis,
# Lulu Castillo). Sin eso la veterinaria recibe seis análisis sin saber cuál es de cuál.

def test_la_linea_lleva_el_paciente_en_la_descripcion():
    perfil = {"base_profile": {"code": "160", "name": "Perfil Prequirúrgico IX", "price": 54117},
              "added_tests": [], "removed_tests": []}
    lineas = billing.build_invoice_lines(perfil, "Chilindrina Garzon")
    assert lineas[0]["description"] == "Chilindrina Garzon"


def test_cada_analisis_agregado_tambien_lleva_el_paciente():
    perfil = {"base_profile": {"code": "160", "name": "Perfil", "price": 50000},
              "added_tests": [{"code": "1101", "name": "Cuadro Hemático", "price": 14000}],
              "removed_tests": []}
    lineas = billing.build_invoice_lines(perfil, "Isis")
    assert [l.get("description") for l in lineas] == ["Isis", "Isis"]


def test_sin_paciente_la_linea_no_trae_descripcion():
    """No-regresión: el camino viejo (sin paciente) no cambia."""
    perfil = {"base_profile": {"code": "160", "name": "Perfil", "price": 50000},
              "added_tests": [], "removed_tests": []}
    assert "description" not in billing.build_invoice_lines(perfil)[0]


# ── Factura electrónica vs. Consumidor Final (pedido de A3, 2026-08-27) ──────────
# En la cuenta real, las facturas de los clientes sin factura electrónica salen al
# contacto genérico «Consumidor Final» (NIT 222222222222) con el nombre de la
# veterinaria o del médico en las notas. Los demás se facturan a su propio NIT.

def test_cliente_con_factura_electronica_se_factura_a_su_nombre():
    nit, nombre, nota = billing.invoice_target(
        {"electronic_invoice": True, "clinic_name": "Animal Pets"}, "53115419", "Animal Pets"
    )
    assert (nit, nombre, nota) == ("53115419", "Animal Pets", None)


def test_cliente_sin_factura_electronica_va_a_consumidor_final_con_nota():
    nit, nombre, nota = billing.invoice_target(
        {"electronic_invoice": False, "invoice_note": "Dr Diego Figueroa", "clinic_name": "Vet Sais"},
        "80871972",
        "Vet Sais",
    )
    assert nit == billing.CONSUMIDOR_FINAL_NIT
    assert nombre == "Consumidor Final"
    assert nota == "Dr Diego Figueroa"


def test_sin_nota_propia_usa_el_nombre_de_la_veterinaria():
    _, _, nota = billing.invoice_target(
        {"electronic_invoice": False, "clinic_name": "Veterinaria Piscis"}, "80871972", "X"
    )
    assert nota == "Veterinaria Piscis"


def test_sin_fila_de_cliente_se_factura_a_nombre_propio():
    """Default seguro: si no se pudo leer el cliente, no se desvía a Consumidor Final."""
    assert billing.invoice_target(None, "53115419", "Animal Pets") == ("53115419", "Animal Pets", None)


def test_la_factura_a_consumidor_final_manda_la_nota_y_no_los_datos_del_cliente(monkeypatch):
    creado = {}

    def fake_get_or_create_contact(tax_id, name, extra=None, **kwargs):
        creado["contacto"] = (tax_id, name, extra)
        return {"id": "1"}

    def fake_get_or_create_item(reference, name, price):
        return {"id": "77"}

    def fake_create_invoice(client_id, items, date, due_date=None, status=None, anotation=None):
        creado["factura"] = {"client": client_id, "anotation": anotation}
        return {"id": "900", "total": 38000}

    monkeypatch.setattr(alegra, "get_or_create_contact", fake_get_or_create_contact)
    monkeypatch.setattr(alegra, "get_or_create_item", fake_get_or_create_item)
    monkeypatch.setattr(alegra, "create_invoice", fake_create_invoice)

    lines = [{"reference": "1101", "name": "Cuadro Hemático", "price": 38000, "quantity": 1}]
    billing.invoice_order(
        "80871972",
        "Veterinaria Piscis",
        lines,
        "2026-08-27",
        client_extra={"email": "piscis@correo.co"},
        client_row={"electronic_invoice": False, "invoice_note": "German Chacon"},
    )

    assert creado["contacto"][0] == billing.CONSUMIDOR_FINAL_NIT
    assert creado["contacto"][2] is None, "el email del cliente no se cuelga del contacto compartido"
    assert creado["factura"]["anotation"] == "German Chacon"


# ── Perfiles adicionales en la misma orden (ERR-162, 2026-08-28) ──────────────

def test_factura_una_linea_por_cada_perfil_adicional():
    """Una orden con tres perfiles se facturaba solo con el primero: la plata de los
    otros dos no llegaba a la factura."""
    payload = {
        "base_profile": {"code": "952", "name": "Perfil Prequirurgico", "price": 90000},
        "extra_profiles": [{"code": "653", "name": "Perfil Renal", "price": 45000},
                           {"code": "101", "name": "Perfil Parasitologico", "price": 30000}],
        "added_tests": [{"code": "1101", "name": "Cuadro Hematico", "price": 14000}],
        "removed_tests": [],
    }
    lineas = billing.build_invoice_lines(payload, patient="Firulais")
    assert [l["reference"] for l in lineas] == ["952", "653", "101", "1101"]
    assert sum(l["price"] for l in lineas) == 179000


def test_sin_perfiles_adicionales_la_factura_no_cambia():
    payload = {
        "base_profile": {"code": "952", "name": "Perfil Prequirurgico", "price": 90000},
        "added_tests": [], "removed_tests": [],
    }
    lineas = billing.build_invoice_lines(payload)
    assert len(lineas) == 1 and lineas[0]["price"] == 90000
