"""Pregunta del cliente (29/10): «si cargo la lista con el número del análisis y al lado el
precio, ¿lo detecta?». Listas sin encabezado, encabezados raros («Vlr») y códigos pegados
al nombre («1101 - Cuadro Hemático»)."""
import io

from openpyxl import Workbook

from app import imports_contenido
from app import imports_archivo as archivo
from app.main import app

TIPOS = ["precios", "clientes", "portafolio", "motorizados"]


def _xlsx(filas) -> bytes:
    libro = Workbook()
    for fila in filas:
        libro.active.append(fila)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _leer(filas):
    enc, datos = archivo.leer_tabla(_xlsx(filas), "lista.xlsx")
    return enc, datos, archivo.detectar_tipo(enc, TIPOS)


def test_codigo_y_precio_sin_encabezado_se_reconocen_como_precios():
    enc, datos, tipo = _leer([[1101, 14000], [1102, 28000], [1701, 12000]])
    assert enc == ["codigo", "precio"] and tipo == "precios"
    assert datos == [["1101", "14000"], ["1102", "28000"], ["1701", "12000"]], "la primera fila también son datos"


def test_codigo_nombre_y_precio_con_pesos_sin_encabezado():
    enc, datos, tipo = _leer([[1101, "Cuadro Hemático", "$ 14.000"], [1102, "Coombs", "$ 28.000"]])
    assert enc == ["codigo", "nombre", "precio"] and tipo == "precios" and len(datos) == 2


def test_clientes_sin_encabezado_por_nit_celular_y_correo():
    enc, datos, tipo = _leer([["Vet Norte", "900123456-1", 3001234567, "a@b.co", "Cl 1 # 2-3"],
                              ["Vet Sur", "800111222", 3109876543, "c@d.co", "Cra 5 # 6-7"]])
    assert enc == ["nombre", "nit", "telefono", "correo", "direccion"] and tipo == "clientes" and len(datos) == 2


def test_un_encabezado_real_sigue_ganando_al_contenido():
    enc, datos, tipo = _leer([["codigo", "precio"], [1101, 14000]])
    assert enc == ["codigo", "precio"] and datos == [["1101", "14000"]] and tipo == "precios"


def test_texto_suelto_sin_nada_reconocible_no_inventa_encabezados():
    enc, datos = archivo.leer_tabla(b"a;b\n1;2\n", "p.csv")
    assert enc == ["a", "b"] and datos == [["1", "2"]]


def test_vlr_y_precio_publico_son_precio():
    assert archivo.mapa_automatico(["Examen", "Vlr"], "precios") == {"name": 0, "price": 1}
    assert archivo.mapa_automatico(["Cod.", "Descripción", "Precio público"], "precios") == {"code": 0, "name": 1, "price": 2}


def test_el_codigo_pegado_al_nombre_se_separa_en_su_columna():
    enc, filas = ["Análisis", "Precio"], [["1101 - Cuadro Hemático", "14000"], ["1102 Coombs", "28000"], ["1701: Coprológico", "12000"]]
    enc2, filas2 = archivo.separar_codigo_del_nombre(enc, filas, "precios")
    assert enc2 == ["codigo", "Análisis", "Precio"]
    assert filas2 == [["1101", "Cuadro Hemático", "14000"], ["1102", "Coombs", "28000"], ["1701", "Coprológico", "12000"]]
    assert archivo.detectar_tipo(enc2, TIPOS) == "precios"


def test_nombres_sin_codigo_adelante_no_se_tocan():
    enc, filas = ["Análisis", "Precio"], [["Cuadro Hemático", "14000"], ["Coombs", "28000"]]
    assert archivo.separar_codigo_del_nombre(enc, filas, "precios") == (enc, filas)


def test_separar_codigo_casos():
    assert imports_contenido.separar_codigo("1101 - Cuadro Hemático") == ("1101", "Cuadro Hemático")
    assert imports_contenido.separar_codigo("2057") == ("2057", "")
    assert imports_contenido.separar_codigo("Coombs") == ("", "Coombs")
    assert imports_contenido.separar_codigo("12 meses") == ("", "12 meses"), "dos dígitos no son un código"


def test_en_la_pantalla_la_lista_codigo_precio_sin_encabezado_llega_al_plan():
    from unittest.mock import patch
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["dashboard_authenticated"] = True
        s["dashboard_username"] = "admin"
    tests = [{"code": "1101", "name": "Cuadro Hemático", "price": 14000}]
    with patch("app.dashboard_import.db.list_catalog_tests", return_value=tests), \
            patch("app.dashboard_import.db.list_catalog_profiles", return_value=[]):
        r = c.post("/cargas/previsualizar", data={"tipo": "auto", "csv": (io.BytesIO(_xlsx([[1101, 15000]])), "lista.xlsx")},
                   content_type="multipart/form-data")
    html = r.get_data(as_text=True)
    assert "Precios del catálogo" in html and "$15.000" in html and "1 a actualizar" in html
