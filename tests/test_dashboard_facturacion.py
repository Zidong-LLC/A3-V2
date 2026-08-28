"""Facturación en dos pestañas: cada una arma SOLO lo suyo.

Antes la pantalla calculaba las dos mitades en cada visita, y cada una lee el cache de
facturas entero: era leerlo dos veces para mostrar la mitad.
"""
from unittest.mock import patch

CARTERA = {
    "cartera_totales": {"facturado": 100, "cobrado": 60, "por_cobrar": 40, "vencido": 10,
                        "facturas": 3, "facturas_pendientes": 1, "facturas_vencidas": 1},
    "cartera_clientes": [{"client_name": "Veterinaria Piscis", "client_nit": "80871972",
                          "facturado": 100, "cobrado": 60, "por_cobrar": 40, "vencido": 10,
                          "pendientes": 1, "dias_mora": 5}],
    "cartera_clientes_total": 1,
    "cartera_deudores": 1,
}
FACTURAS = {
    "invoices_rows": [{"alegra_invoice_id": "1", "number": "FE-1", "client_name": "Veterinaria Piscis",
                       "total": 100, "status": "open", "invoice_date": "2026-08-20"}],
    "invoices_total": 1, "invoices_page": 1, "invoices_pages": 1,
    "invoices_metrics": {"today_count": 0, "month_total": 100, "year_total": 100,
                         "avg_ticket": 100, "invoices_count": 1},
    "invoice_status_options": [],
}


def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def _login(client):
    with client.session_transaction() as sess:
        sess["dashboard_authenticated"] = True
        sess["dashboard_username"] = "admin"


def _contexto():
    from tests.test_dashboard import _base_context

    return _base_context(client_type_options={}, vat_regime_options={})


def _abrir(ruta):
    client = _get_test_client()
    _login(client)
    with patch("app.dashboard.build_dashboard_context", return_value=_contexto()), \
         patch("app.dashboard._build_cartera_context", return_value=CARTERA) as cartera, \
         patch("app.dashboard._build_invoices_context", return_value=FACTURAS) as facturas:
        respuesta = client.get(ruta)
    return respuesta.get_data(as_text=True), cartera, facturas


def test_entra_en_facturas_y_no_calcula_la_cartera():
    cuerpo, cartera, facturas = _abrir("/facturacion")
    cartera.assert_not_called()
    facturas.assert_called_once()
    assert "Ticket promedio" in cuerpo
    assert "Cartera por cliente" not in cuerpo


def test_la_pestana_cartera_no_calcula_el_listado_de_facturas():
    cuerpo, cartera, facturas = _abrir("/facturacion?vista=cartera")
    cartera.assert_called_once()
    facturas.assert_not_called()
    assert "Cartera por cliente" in cuerpo
    assert "Veterinaria Piscis" in cuerpo
    assert "Ticket promedio" not in cuerpo


def test_una_pestana_inventada_cae_en_facturas():
    cuerpo, cartera, facturas = _abrir("/facturacion?vista=loquesea")
    cartera.assert_not_called()
    facturas.assert_called_once()


def test_las_dos_pestanas_se_ofrecen_siempre():
    cuerpo, _, _ = _abrir("/facturacion")
    assert 'href="/facturacion?vista=cartera"' in cuerpo
    assert cuerpo.count('class="tab-btn') == 2


def test_los_filtros_de_facturas_siguen_llegando():
    cuerpo, _, facturas = _abrir("/facturacion?status=open&date_from=2026-08-01&page=2")
    argumentos = facturas.call_args.args
    assert argumentos[0] == 2                      # la página
    assert argumentos[1]["status"] == "open"       # los filtros
    assert argumentos[1]["date_from"] == "2026-08-01"


def test_el_boton_de_sincronizar_esta_en_las_dos_pestanas():
    for ruta in ("/facturacion", "/facturacion?vista=cartera"):
        cuerpo, _, _ = _abrir(ruta)
        assert "data-invoices-sync" in cuerpo, ruta
