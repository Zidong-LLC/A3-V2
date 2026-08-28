"""Búsqueda y filtros de la tabla de Clientes: se filtra sobre TODOS y después se pagina.

El bug que originó esto: buscar «animal pet» devolvía cero porque el filtro miraba las 15
filas de la página visible, con el cliente cargado en otra página.
"""
from unittest.mock import patch

from app import client_filters


def _cliente(nombre, **extra):
    fila = {
        "client_id": nombre.lower().replace(" ", "-"),
        "clinic_name": nombre, "display_name": nombre, "secondary_name": "",
        "commercial_name": "", "client_code": "-", "tax_id": "-", "phone": "-",
        "email": "-", "billing_email": "-", "address": "-", "zone": "-",
        "courier_name": "Sin mensajero", "doctors_label": "-",
        "client_type": "", "client_status": "Activo", "assigned_courier_id": "",
        "electronic_invoicing_option": "sin_dato",
    }
    fila.update(extra)
    return fila


PADRON = [
    _cliente("Animal Pets", tax_id="53115419-1"),
    _cliente("Animal Pet", client_status="Inactivo"),
    _cliente("Pet Shop Animal Home"),
    _cliente("Veterinaria Piscis", tax_id="80871972", assigned_courier_id="c-1",
             client_type="empresa", electronic_invoicing_option="si"),
    _cliente("Clínica Muñoz", address="CR 88 sur", client_status="Inactivo"),
]


# ── Búsqueda ─────────────────────────────────────────────────────────────────

def test_encuentra_por_dos_palabras_aunque_esten_pegadas_a_otras():
    encontrados = client_filters.filtrar(PADRON, q="animal pet")
    assert [c["clinic_name"] for c in encontrados] == ["Animal Pets", "Animal Pet", "Pet Shop Animal Home"]


def test_el_orden_de_las_palabras_no_importa():
    assert client_filters.filtrar(PADRON, q="pet animal") == client_filters.filtrar(PADRON, q="animal pet")


def test_los_espacios_de_mas_no_cambian_el_resultado():
    assert len(client_filters.filtrar(PADRON, q="  animal   pet  ")) == 3


def test_encuentra_sin_tildes_y_sin_mayusculas():
    assert [c["clinic_name"] for c in client_filters.filtrar(PADRON, q="clinica munoz")] == ["Clínica Muñoz"]


def test_busca_tambien_por_nit_y_por_direccion():
    assert [c["clinic_name"] for c in client_filters.filtrar(PADRON, q="53115419")] == ["Animal Pets"]
    assert [c["clinic_name"] for c in client_filters.filtrar(PADRON, q="cr 88")] == ["Clínica Muñoz"]


def test_un_cliente_inactivo_aparece_igual_en_la_busqueda():
    """Que no aparezca hace pensar que no está cargado, y casi siempre está pero inactivo."""
    nombres = [c["clinic_name"] for c in client_filters.filtrar(PADRON, q="animal pet")]
    assert "Animal Pet" in nombres


def test_sin_criterios_devuelve_todo_intacto():
    assert client_filters.filtrar(PADRON) == PADRON


def test_algo_que_no_existe_devuelve_vacio():
    assert client_filters.filtrar(PADRON, q="dinosaurios") == []


# ── Filtros ──────────────────────────────────────────────────────────────────

def test_filtro_de_estado():
    assert len(client_filters.filtrar(PADRON, estado="inactivo")) == 2
    assert len(client_filters.filtrar(PADRON, estado="activo")) == 3


def test_filtro_de_motorizado():
    assert [c["clinic_name"] for c in client_filters.filtrar(PADRON, motorizado="yes")] == ["Veterinaria Piscis"]
    assert len(client_filters.filtrar(PADRON, motorizado="no")) == 4


def test_filtro_de_facturacion_electronica_y_de_tipo():
    assert [c["clinic_name"] for c in client_filters.filtrar(PADRON, fe="si")] == ["Veterinaria Piscis"]
    assert [c["clinic_name"] for c in client_filters.filtrar(PADRON, tipo="empresa")] == ["Veterinaria Piscis"]


def test_los_criterios_se_combinan():
    encontrados = client_filters.filtrar(PADRON, q="animal", estado="inactivo")
    assert [c["clinic_name"] for c in encontrados] == ["Animal Pet"]


# ── Lectura de la URL ────────────────────────────────────────────────────────

class _Args(dict):
    def get(self, clave, default=None):
        return dict.get(self, clave, default)


def test_desde_args_deja_afuera_lo_que_no_filtra():
    criterios = client_filters.desde_args(_Args(q=" animal ", tipo="all", estado="inactivo"))
    assert criterios == {"q": "animal", "estado": "inactivo"}


def test_desde_args_sin_nada_devuelve_vacio():
    assert client_filters.desde_args(_Args()) == {}


# ── La pantalla ──────────────────────────────────────────────────────────────

def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def _login(client):
    with client.session_transaction() as sess:
        sess["dashboard_authenticated"] = True
        sess["dashboard_username"] = "admin"


def _contexto_con(padron):
    """Contexto de dashboard mínimo, con el padrón como filas de clientes."""
    from tests.test_dashboard import _base_context

    return _base_context(clients_rows=padron, client_type_options={"empresa": "Empresa"},
                         vat_regime_options={})


def test_la_busqueda_encuentra_un_cliente_de_otra_pagina():
    """20 clientes de relleno empujan a «Animal Pet» fuera de la primera página."""
    client = _get_test_client()
    _login(client)
    relleno = [_cliente(f"Aaa Veterinaria {i:02d}") for i in range(20)]
    with patch("app.dashboard.build_dashboard_context", return_value=_contexto_con(relleno + PADRON)):
        sin_buscar = client.get("/clientes").get_data(as_text=True)
        buscando = client.get("/clientes?q=animal+pet").get_data(as_text=True)
    assert "Animal Pet" not in sin_buscar          # está en la página 2
    assert "Animal Pets" in buscando               # aparece aunque no esté en la página 1
    assert "3 de 25 clientes" in buscando          # el contador habla del total encontrado


def test_la_paginacion_conserva_lo_buscado():
    client = _get_test_client()
    _login(client)
    padron = [_cliente(f"Animal Pet {i:02d}") for i in range(30)]
    with patch("app.dashboard.build_dashboard_context", return_value=_contexto_con(padron)):
        cuerpo = client.get("/clientes?q=animal+pet").get_data(as_text=True)
    assert "q=animal+pet" in cuerpo or "q=animal%20pet" in cuerpo


def test_una_pagina_fuera_de_rango_no_rompe_la_pantalla():
    client = _get_test_client()
    _login(client)
    with patch("app.dashboard.build_dashboard_context", return_value=_contexto_con(PADRON)):
        respuesta = client.get("/clientes?q=animal&page=99")
    assert respuesta.status_code == 200
    assert "Animal Pets" in respuesta.get_data(as_text=True)
