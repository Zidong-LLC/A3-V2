"""Regresión ERR-125 (Ronda 3, bloque_partido): pedido cerrado SIN factura por NIT ausente.

Dos capas:
1. `find_client_matches("Animal Pets, registrada")` devolvía [] — la muletilla 'registrada'
   no estaba en los stopwords y el score exige todas las palabras. El cliente diciendo
   "estamos registrados" es de lo más natural.
2. Aunque la identificación copie el NIT, algún carril puede no hacerlo (se midió
   intermitente): `_try_invoice_pedido` ahora re-resuelve el NIT contra la base con el
   nombre YA identificado antes de renunciar a facturar — puerta del dinero.
"""
from unittest.mock import patch

from app import agent
from app.services import db

CLINICAS = [
    {"id": "c1", "clinic_name": "Animal Pets", "tax_id": "53115419-1"},
    {"id": "c2", "clinic_name": "Mascotas Express", "tax_id": "2"},
]


def test_la_muletilla_registrada_no_rompe_el_lookup():
    with patch.object(db, "_fetch_all_active_clients", return_value=CLINICAS):
        m = db.find_client_matches("Animal Pets, registrada")
        assert m and m[0]["clinic_name"] == "Animal Pets"
        m2 = db.find_client_matches("somos Animal Pets, ya registrados")
        assert m2 and m2[0]["clinic_name"] == "Animal Pets"


def test_pedido_sin_nit_en_estado_lo_re_resuelve_y_factura():
    """El caso literal: al cierre el estado no tiene tax_id pero sí el nombre identificado.
    La factura debe salir igual, con el NIT de la base."""
    fields = {
        "clinic_name": "Animal Pets",
        "_pedido_ordenes": [{"patient_name": "Duke"}],
        "_pedido_profiles": [{"base_profile": {"code": "152", "name": "Perfil Prequirúrgico I",
                                               "price": 24000}, "added_tests": [],
                              "total_estimated": 24000}],
    }
    facturas = []
    with patch.object(agent.billing, "build_invoice_lines",
                      return_value=[{"desc": "x", "price": 24000}]), \
         patch.object(agent.billing, "invoice_order",
                      side_effect=lambda nit, *a, **k: facturas.append(nit) or {"invoice_id": "i1"}), \
         patch.object(agent.db, "find_client_exact",
                      return_value={"id": "c1", "clinic_name": "Animal Pets", "tax_id": "53115419-1"}), \
         patch.object(agent.db, "mark_pedido_invoiced", lambda *a, **k: None):
        agent._try_invoice_pedido("ped-1", fields)
    assert facturas == ["53115419-1"]


def test_sin_nit_ni_nombre_sigue_sin_facturar_y_sin_romper():
    """La red no inventa: sin NIT y sin nombre identificado, el cierre no factura (queda
    'cerrado' visible para operaciones) y no explota."""
    with patch.object(agent.billing, "build_invoice_lines", return_value=[{"d": 1}]), \
         patch.object(agent.db, "find_client_exact", return_value=None):
        agent._try_invoice_pedido("ped-2", {"_pedido_profiles": [{"total_estimated": 1}],
                                            "_pedido_ordenes": [{}]})


def test_payload_sale_con_analisis_sueltos_sin_exam_type():
    """ERR-127 (Ronda 4, consulta_primero): la orden se registró con el 1101 en
    selected_tests pero exam_type vacío → payload None → pedido cerrado 'sin especificar'
    y SIN factura. El dinero sigue a lo GUARDADO, no a un campo de display."""
    with patch.object(db, "get_tests_by_codes_or_names",
                      return_value=[{"code": "1101", "name": "Cuadro Hemático Completo",
                                     "price": 14000}]):
        p = db._profile_event_payload({"selected_tests": ["1101"]})
    assert p is not None
    assert p["total_estimated"] == 14000
    assert p["base_profile"]["name"] == "Perfil personalizado (1 análisis)"
    # Sin NADA guardado sigue sin inventar payload.
    assert db._profile_event_payload({}) is None
