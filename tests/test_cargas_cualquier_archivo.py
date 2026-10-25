"""Cierre v1: cargas masivas con cualquier archivo, columnas elegibles, plantillas y exportación."""
import io
import json
from unittest.mock import patch

import pytest

from app import imports, imports_aplicar
from app import imports_archivo as archivo
from app.main import app


def _xlsx(filas) -> bytes:
    from openpyxl import Workbook
    libro = Workbook()
    for fila in filas:
        libro.active.append(fila)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


@pytest.mark.parametrize("separador", [";", "\t", "|", ","])
def test_lee_cualquier_separador(separador):
    datos = separador.join(["codigo", "precio"]) + "\n" + separador.join(["952", "35000"]) + "\n"
    encabezados, filas = archivo.leer_tabla(datos.encode("utf-8"), "x.csv")
    assert encabezados == ["codigo", "precio"] and filas == [["952", "35000"]]


def test_lee_el_csv_que_guarda_excel_en_windows():
    datos = "nombre;dirección\nClínica Peña;Cl 1\n".encode("cp1252")
    encabezados, filas = archivo.leer_tabla(datos, "x.csv")
    assert encabezados[1] == "dirección" and filas[0][0] == "Clínica Peña"


def test_lee_xlsx_y_no_agrega_punto_cero_a_los_numeros():
    encabezados, filas = archivo.leer_tabla(_xlsx([["Código", "Precio"], [952, 35000.0], [None, None]]), "p.xlsx")
    assert encabezados == ["Código", "Precio"] and filas == [["952", "35000"]]


def test_reconoce_municipio_y_motorizado_en_clientes():
    mapa = archivo.mapa_automatico(["Razón social", "NIT", "Municipio", "Motorizado"], "clientes")
    assert mapa == {"name": 0, "tax_id": 1, "city": 2, "courier": 3}


def test_avisa_lo_obligatorio_que_falta():
    assert archivo.faltantes({"code": 0}, "precios") == ["Precio"]
    assert archivo.faltantes({"phone": 0}, "clientes") == ["Nombre o NIT"]


def _coincide(a, b):
    return imports.norm(a) == imports.norm(b)


CLIENTES = [{"id": "c1", "clinic_name": "Vet Norte", "tax_id": "900111", "phone": "1", "city": "Bogotá", "email": ""}]


def test_por_defecto_solo_completa_vacios():
    filas = [{"tax_id": "900111", "phone": "2", "email": "a@a.co"}]
    plan = imports.plan_clientes(filas, CLIENTES, _coincide)
    assert plan["actualizar"][0]["cambios"] == {"email": "a@a.co"}


def test_con_actualizar_cambia_lo_que_difiere_y_guarda_el_antes():
    filas = [{"tax_id": "900111", "phone": "2", "city": "Soacha"}]
    plan = imports.plan_clientes(filas, CLIENTES, _coincide, actualizar=True)
    cambio = plan["actualizar"][0]
    assert cambio["cambios"] == {"phone": "2", "city": "Soacha"}
    assert cambio["antes"] == {"phone": "1", "city": "Bogotá"}


def test_asigna_motorizado_por_nombre_y_avisa_si_no_existe():
    filas = [{"tax_id": "900111", "courier": "javier"}, {"name": "Vet Nueva", "courier": "Fantasma"}]
    plan = imports.plan_clientes(filas, CLIENTES, _coincide, motorizados={"javier": "m1"}, asignaciones={})
    assert plan["actualizar"][0]["cambios"] == {"courier_id": "m1"}
    assert "Fantasma" in plan["errores"][0] and plan["crear"][0]["clinic_name"] == "Vet Nueva"


def test_plan_motorizados_crea_actualiza_y_detecta_repetidos():
    plan = imports_aplicar.plan_motorizados(
        [{"name": "Javier", "phone": "300"}, {"name": "Nuevo", "phone": ""}, {"name": "nuevo"}],
        [{"id": "m1", "name": "Javier", "phone": "111"}])
    assert plan["actualizar"][0]["cambios"] == {"phone": "300"}
    # Sin teléfono no se crea: la tabla lo exige y el alta fallaba recién al aplicar.
    assert plan["crear"] == []
    assert "teléfono" in plan["errores"][0] and "repetido" in plan["errores"][1]


@pytest.fixture
def client():
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["dashboard_authenticated"] = True
        s["dashboard_username"] = "admin"
    return c


def test_columnas_desconocidas_piden_elegir_y_luego_calculan_el_plan(client):
    tests = [{"code": "952", "name": "Hemograma", "price": 30000}]
    with patch("app.dashboard_import.db.list_catalog_tests", return_value=tests), \
            patch("app.dashboard_import.db.list_catalog_profiles", return_value=[]):
        r = client.post("/cargas/previsualizar", data={
            "tipo": "precios", "csv": (io.BytesIO(b"Referencia;Importe\n952;35000\n"), "raro.csv")},
            content_type="multipart/form-data")
        html = r.get_data(as_text=True)
        assert "Falta indicar" in html and "Aplicar estos cambios" not in html
        tabla = {"encabezados": ["Referencia", "Importe"], "filas": [["952", "35000"]], "archivo": "raro.csv"}
        r = client.post("/cargas/columnas", data={"tipo": "precios", "tabla": json.dumps(tabla),
                                                  "col_code": "0", "col_price": "1"})
    html = r.get_data(as_text=True)
    assert "Aplicar estos cambios" in html and "Hemograma" in html


def test_perfil_sin_permiso_de_precios_no_puede_cargar_precios(client):
    with client.session_transaction() as s:
        s["dashboard_role"] = "digitacion"  # Cargas sí, pero precios y clientes no
    r = client.post("/cargas/previsualizar", data={
        "tipo": "precios", "csv": (io.BytesIO(b"codigo,precio\n952,1\n"), "p.csv")},
        content_type="multipart/form-data")
    assert r.status_code == 302
    r = client.post("/cargas/aplicar", data={"plan": json.dumps({"tipo": "precios", "actualizar": []})})
    assert r.status_code == 302


def test_plantilla_y_exportacion_se_abren_en_excel(client):
    r = client.get("/cargas/plantilla/clientes")
    texto = r.get_data(as_text=True)
    assert texto.startswith("﻿nombre;nit;") and "attachment" in r.headers["Content-Disposition"]
    with patch("app.imports_exportar.db.list_couriers", return_value=[{"id": "m1", "name": "Javier", "is_active": True}]), \
            patch("app.imports_exportar.maestros_db.asignaciones", return_value={"c1": "m1"}), \
            patch("app.imports_exportar.db.list_clients_basic",
                  return_value=[{"id": "c1", "clinic_name": "Vet Norte", "tax_id": "900111", "is_active": True}]):
        texto = client.get("/cargas/exportar/clientes").get_data(as_text=True)
    assert "Vet Norte;900111;" in texto and ";Javier;si" in texto


def test_detecta_el_tipo_por_las_columnas():
    clientes = ["nombre", "nit", "telefono", "direccion", "municipio", "correo", "motorizado"]
    assert archivo.detectar_tipo(clientes, ["precios", "clientes", "portafolio", "motorizados"]) == "clientes"
    assert archivo.detectar_tipo(["codigo", "precio"], ["precios", "clientes", "portafolio", "motorizados"]) == "precios"
    assert archivo.detectar_tipo(["algo", "otra cosa"], ["precios", "clientes"]) is None
    # código + nombre + precio también calza con portafolio: en empate manda precios
    assert archivo.detectar_tipo(["codigo", "nombre", "precio"], ["precios", "clientes", "portafolio"]) == "precios"


def test_archivo_de_clientes_con_el_tipo_equivocado_se_lee_como_clientes(client):
    datos = "nombre;nit;municipio\nVet Demo;900999001-1;Soacha\n".encode("utf-8")
    with patch("app.dashboard_import.db.list_active_couriers", return_value=[]), \
            patch("app.dashboard_import.db.list_clients_basic", return_value=[]), \
            patch("app.dashboard_import.maestros_db.asignaciones", return_value={}):
        for tipo in ("precios", "auto"):
            r = client.post("/cargas/previsualizar", data={"tipo": tipo, "csv": (io.BytesIO(datos), "c.csv")},
                            content_type="multipart/form-data")
            html = r.get_data(as_text=True)
            assert "Aplicar estos cambios" in html and "Vet Demo" in html
    assert "se leyó como «Clientes»" in html
