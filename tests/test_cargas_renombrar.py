"""Pedido de A3 (2026-11-09): «cuando se actualice información, que también se actualicen
los nombres: es más fácil cargar una base de todos que hacer el cambio a mano».

La carga cruza por NIT, así que con el NIT se puede renombrar. Para que no cause problemas:
es una casilla aparte, solo actúa cuando el NIT identifica a UN cliente y viene UNA vez en
el archivo, y la ficha de datos del cliente (que se cruza por nombre) lo sigue.
"""
from unittest.mock import patch

from app import imports, imports_aplicar
from app import imports_archivo as archivo
from app.main import app

CLIENTES = [
    {"id": "c1", "clinic_name": "Vet Los Andes", "tax_id": "900100200-1", "phone": "300", "email": None},
    {"id": "s1", "clinic_name": "Club Animals Norte", "tax_id": "900111", "phone": None, "email": None},
    {"id": "s2", "clinic_name": "Club Animals Sur", "tax_id": "900111", "phone": None, "email": None},
    {"id": "c3", "clinic_name": "Dra. Paula Ruiz", "tax_id": None, "phone": "311", "email": None},
]


def _coincide(a, b):
    return imports.norm(a) == imports.norm(b)


def _plan(csv_texto, **opciones):
    enc, filas = archivo.leer_tabla(csv_texto.encode("utf-8"), "x.csv")
    filas = archivo.filas_con_mapa(filas, archivo.mapa_automatico(enc, "clientes"))
    return imports.plan_clientes(filas, CLIENTES, _coincide, **opciones)


def test_con_la_casilla_el_nombre_del_archivo_reemplaza_al_de_la_base():
    plan = _plan("nombre,nit\nClínica Veterinaria Los Andes SAS,900100200\n", renombrar=True)
    assert plan["crear"] == [] and plan["errores"] == []
    cambio = plan["actualizar"][0]
    assert cambio["id"] == "c1" and cambio["clinic_name"] == "Vet Los Andes", "la vista previa muestra el nombre actual"
    assert cambio["cambios"] == {"clinic_name": "Clínica Veterinaria Los Andes SAS"}
    assert cambio["antes"] == {"clinic_name": "Vet Los Andes"}


def test_sin_la_casilla_el_nombre_no_se_toca_aunque_se_marque_actualizar():
    plan = _plan("nombre,nit,telefono\nClínica Los Andes SAS,900100200-1,301\n", actualizar=True)
    assert plan["actualizar"][0]["cambios"] == {"phone": "301"}


def test_renombrar_y_actualizar_van_juntos_en_el_mismo_cambio():
    plan = _plan("nombre,nit,telefono\nClínica Los Andes SAS,900100200-1,301\n", actualizar=True, renombrar=True)
    assert plan["actualizar"][0]["cambios"] == {"phone": "301", "clinic_name": "Clínica Los Andes SAS"}
    assert plan["actualizar"][0]["antes"] == {"phone": "300", "clinic_name": "Vet Los Andes"}


def test_solo_cambia_mayusculas_o_tildes_tambien_es_un_ajuste_de_nombre():
    plan = _plan("nombre,nit\nVET LOS ANDES,900100200\n", renombrar=True)
    assert plan["actualizar"][0]["cambios"] == {"clinic_name": "VET LOS ANDES"}


def test_el_mismo_nombre_no_genera_cambio():
    plan = _plan("nombre,nit\nVet Los Andes,900100200\n", renombrar=True)
    assert plan["actualizar"] == [] and plan["iguales"] == 1


def test_las_sedes_que_comparten_nit_no_se_renombran():
    """Entre sedes el nombre es lo único que las distingue: el archivo no puede decir cuál es."""
    plan = _plan("nombre,nit\nClub Animals Norte,900111\nClub Animals Chapinero,900111\n", renombrar=True)
    assert not any("clinic_name" in c["cambios"] for c in plan["actualizar"])
    assert plan["crear"] == []


def test_un_nit_repetido_en_el_archivo_no_renombra_y_avisa():
    plan = _plan("nombre,nit\nAndes Sede A,900100200\nAndes Sede B,900100200\n", renombrar=True)
    assert not any("clinic_name" in c["cambios"] for c in plan["actualizar"])
    assert any("900100200" in e and "no se cambia el nombre" in e for e in plan["errores"])


def test_quien_cruza_por_nombre_no_tiene_otro_nombre_que_poner():
    plan = _plan("nombre,telefono\nDra. Paula Ruiz,312\n", actualizar=True, renombrar=True)
    assert plan["actualizar"][0]["cambios"] == {"phone": "312"}


def test_aplicar_renombra_al_cliente_y_a_su_ficha_y_deja_el_antes_en_el_historial():
    plan = {"crear": [], "actualizar": [{"id": "c1", "clinic_name": "Vet Los Andes",
                                         "antes": {"clinic_name": "Vet Los Andes"},
                                         "cambios": {"clinic_name": "  Clínica Los Andes SAS  ", "is_active": False}}]}
    with patch("app.services.db.update_client_profile", return_value=True) as actualizar, \
         patch("app.services.maestros_db.renombrar_ficha") as ficha, \
         patch("app.services.audit_db.registrar_lote") as historial:
        assert imports_aplicar.aplicar_clientes(plan) == (0, 1, [])
    actualizar.assert_called_once_with("c1", {"clinic_name": "Clínica Los Andes SAS"})
    ficha.assert_called_once_with("Vet Los Andes", "Clínica Los Andes SAS")
    assert historial.call_args.args[1][0][2]["clinic_name"] == {"antes": "Vet Los Andes",
                                                               "despues": "Clínica Los Andes SAS"}


def test_un_nombre_vacio_nunca_pisa_al_que_hay():
    plan = {"crear": [], "actualizar": [{"id": "c1", "clinic_name": "Vet", "cambios": {"clinic_name": "  ", "phone": "1"}}]}
    with patch("app.services.db.update_client_profile", return_value=True) as actualizar, \
         patch("app.services.maestros_db.renombrar_ficha") as ficha, \
         patch("app.services.audit_db.registrar_lote"):
        imports_aplicar.aplicar_clientes(plan)
    actualizar.assert_called_once_with("c1", {"phone": "1"})
    assert not ficha.called


def test_si_la_ficha_no_se_pudo_renombrar_el_cliente_cuenta_y_se_avisa():
    plan = {"crear": [], "actualizar": [{"id": "c1", "clinic_name": "Vet", "cambios": {"clinic_name": "Vet Nueva"}}]}
    with patch("app.services.db.update_client_profile", return_value=True), \
         patch("app.services.maestros_db.renombrar_ficha", side_effect=RuntimeError("x")), \
         patch("app.services.audit_db.registrar_lote"):
        creados, actualizados, fallidos = imports_aplicar.aplicar_clientes(plan)
    assert actualizados == 1 and "ficha" in fallidos[0]


def test_la_ficha_conserva_su_clave_y_cambia_el_nombre_visible(monkeypatch):
    from app.services import maestros_db
    hechos = []

    class _Tabla:
        def update(self, cambios):
            self.cambios = cambios
            return self

        def eq(self, campo, valor):
            hechos.append((self.cambios, campo, valor))
            return self

        def execute(self):
            return None

    monkeypatch.setattr(maestros_db._client, "table", lambda nombre: _Tabla())
    maestros_db.renombrar_ficha("Vet Los Andes", "Clínica Los Andes SAS")
    assert hechos == [({"clinic_name": "Clínica Los Andes SAS"}, "clinic_key", "vet_los_andes"),
                      ({"clinic_name": "Clínica Los Andes SAS"}, "clinic_name", "Vet Los Andes")]
    hechos.clear()
    maestros_db.renombrar_ficha("", "X")
    assert hechos == []


def test_la_pantalla_ofrece_la_casilla_de_nombres():
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["dashboard_authenticated"] = True
        s["dashboard_username"] = "admin"
    html = c.get("/cargas").get_data(as_text=True)
    assert 'name="renombrar"' in html and 'name="actualizar"' in html
