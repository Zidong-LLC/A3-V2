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


# ── Búsqueda y filtros del listado (2026-08-28) ───────────────────────────────

class _QueryFalsa:
    """Doble del constructor de consultas de Supabase: anota qué se le pidió."""

    def __init__(self, registro):
        self.registro = registro

    def select(self, *a, **k):
        return self

    def eq(self, campo, valor):
        self.registro.append(("eq", campo, valor)); return self

    def ilike(self, campo, valor):
        self.registro.append(("ilike", campo, valor)); return self

    def gte(self, campo, valor):
        self.registro.append(("gte", campo, valor)); return self

    def lte(self, campo, valor):
        self.registro.append(("lte", campo, valor)); return self

    def or_(self, expr):
        self.registro.append(("or", expr)); return self

    def order(self, *a, **k):
        return self

    def range(self, *a, **k):
        return self

    def execute(self):
        class R:
            data, count = [], 0
        return R()


def _consulta(filtros):
    from unittest.mock import MagicMock

    from app.services import db as dbs

    registro = []
    cliente = MagicMock()
    cliente.table.return_value = _QueryFalsa(registro)
    with patch.object(dbs, "_client", cliente):
        dbs.list_cached_invoices(filtros, page=1, per_page=10)
    return registro


def test_una_palabra_busca_en_numero_nombre_y_nit():
    registro = _consulta({"search": "zoopecas"})
    condicion = next(r[1] for r in registro if r[0] == "or")
    assert "number.ilike" in condicion and "client_name.ilike" in condicion and "client_nit.ilike" in condicion


def test_la_busqueda_encuentra_con_tilde_y_sin_tilde():
    """En la base conviven «Clinica» y «Clínica»: buscar una traía 89 y la otra 8."""
    registro = _consulta({"search": "clinica"})
    condicion = next(r[1] for r in registro if r[0] == "or")
    assert "cl_n_c_" in condicion          # cada vocal es un comodín de un carácter
    assert "clinica" not in condicion


def test_dos_palabras_se_buscan_todas_en_cualquier_orden():
    """«lopez isabel» tiene que encontrar a «Dra Isabel Cristina Lopez»."""
    registro = _consulta({"search": "lopez isabel"})
    nombres = [r for r in registro if r[0] == "ilike" and r[1] == "client_name"]
    assert len(nombres) == 2
    assert not [r for r in registro if r[0] == "or"]


def test_la_coma_separa_palabras_y_no_rompe_la_consulta():
    registro = _consulta({"search": "clinica, veterinaria"})
    assert len([r for r in registro if r[0] == "ilike" and r[1] == "client_name"]) == 2


def test_los_comodines_que_escriba_el_usuario_no_viajan_a_la_consulta():
    registro = _consulta({"search": "cli%nica_"})
    condicion = next(r[1] for r in registro if r[0] == "or")
    assert "%nica" not in condicion


def test_el_nit_se_busca_sin_puntos_ni_digito_de_verificacion():
    """En el cache el NIT viene pelado: escribirlo como en la factura no encontraba nada."""
    registro = _consulta({"client_nit": "32.180.929-1"})
    assert ("ilike", "client_nit", "%32180929%") in registro


def test_el_rango_de_totales_y_las_fechas_van_a_la_consulta():
    registro = _consulta({"total_min": 20000, "total_max": 50000,
                          "date_from": "2026-08-01", "date_to": "2026-08-20"})
    assert ("gte", "total", 20000) in registro
    assert ("lte", "total", 50000) in registro
    assert ("gte", "invoice_date", "2026-08-01") in registro
    assert ("lte", "invoice_date", "2026-08-20") in registro


def test_un_total_escrito_con_puntos_se_entiende():
    from app.dashboard import _parse_invoice_filters

    class Args(dict):
        def get(self, k, d=None):
            return dict.get(self, k, d)

    filtros = _parse_invoice_filters(Args({"total_min": "$ 1.000.000", "total_max": "50.000"}))
    assert filtros["total_min"] == 1000000
    assert filtros["total_max"] == 50000


def test_sin_coincidencias_no_dice_que_falta_sincronizar():
    """Con 1.200 facturas en cache, «no hay facturas en cache» era falso y mandaba a
    sincronizar de gusto: lo que no hay son coincidencias."""
    cuerpo, _, _ = _abrir("/facturacion?search=noexisteestecliente")
    assert "Ninguna factura coincide" in cuerpo or "invoices_rows" not in cuerpo


def test_sin_filtros_la_tabla_vacia_sigue_invitando_a_sincronizar():
    from unittest.mock import patch as _patch

    client = _get_test_client()
    _login(client)
    vacio = {**FACTURAS, "invoices_rows": [], "invoices_total": 0}
    with _patch("app.dashboard.build_dashboard_context", return_value=_contexto()), \
         _patch("app.dashboard._build_invoices_context", return_value=vacio):
        cuerpo = client.get("/facturacion").get_data(as_text=True)
    assert "No hay facturas en cache" in cuerpo
