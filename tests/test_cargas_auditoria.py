"""Cargas masivas: arreglos de la auditoría del 2026-10-19 (validación, detección y aplicación)."""
from unittest.mock import patch

from app import imports, imports_aplicar
from app import imports_archivo as archivo

TODOS = ["precios", "clientes", "portafolio", "motorizados"]
TESTS = [{"code": "952", "name": "Hemograma", "price": 30000}]


def _filas(texto: str) -> list[dict]:
    return imports.leer_csv(texto.encode("utf-8"))[0]


def test_portafolio_sin_categoria_avisa_en_la_vista_previa():
    plan = imports.plan_portafolio(_filas("codigo,nombre,precio\n3001,Nueva,50000\n"), TESTS, [])
    assert plan["crear"] == [] and "categoría" in plan["errores"][0]


def test_portafolio_normaliza_la_especie():
    plan = imports.plan_portafolio(_filas("codigo,nombre,precio,categoria,especie\n"
                                          "3001,A,1000,Otros,Perro\n3002,B,1000,Otros,\n3003,C,1000,Otros,Pez\n"),
                                   TESTS, [])
    assert [(c["code"], c["species"]) for c in plan["crear"]] == [("3001", "canino"), ("3002", "ambos")]
    assert "Pez" in plan["errores"][0]


def test_precio_fuera_de_rango_no_llega_al_catalogo():
    plan = imports.plan_precios(_filas("codigo,precio\n952,300000000\n952,0\n"), TESTS, [])
    assert plan["actualizar"] == [] and len(plan["errores"]) == 2


def test_deteccion_del_tipo_por_columnas_propias():
    assert archivo.detectar_tipo(["nombre", "telefono"], TODOS) == "motorizados"
    assert archivo.detectar_tipo(["codigo", "nombre", "precio", "tipo", "especie"], TODOS) == "precios"
    assert archivo.detectar_tipo(["codigo", "nombre", "precio", "categoria"], TODOS) == "portafolio"
    assert archivo.detectar_tipo(["nombre", "nit", "telefono", "motorizado"], TODOS) == "clientes"


def test_cliente_repetido_en_la_lista_no_se_crea_dos_veces():
    plan = imports.plan_clientes(_filas("nombre,nit\nVet Uno,900-1\nVet Uno,900-1\n"), [], lambda a, b: False)
    assert len(plan["crear"]) == 1 and "repetido" in plan["errores"][0]


def test_iguales_nunca_es_negativo_con_sedes_que_comparten_nit():
    sedes = [{"id": f"s{i}", "clinic_name": f"Sede {i}", "tax_id": "900111", "email": None} for i in range(3)]
    plan = imports.plan_clientes(_filas("nombre,nit,correo\nClub,900111,f@club.co\n"), sedes, lambda a, b: False)
    assert len(plan["actualizar"]) == 3 and plan["iguales"] == 0


def test_aplicar_clientes_solo_toca_las_columnas_de_la_carga():
    plan = {"crear": [{"clinic_name": "Nueva", "phone": "1", "electronic_invoice": False}],
            "actualizar": [{"id": "c1", "clinic_name": "Vieja", "antes": {"phone": "0"},
                            "cambios": {"phone": "300", "is_active": False, "billing_type": "credit"}}]}
    with patch("app.services.db.create_client", return_value={"id": "n1"}) as crear, \
         patch("app.services.db.update_client_profile", return_value=True) as actualizar, \
         patch("app.services.audit_db.registrar_lote") as historial:
        assert imports_aplicar.aplicar_clientes(plan) == (1, 1, [])
    crear.assert_called_once_with({"clinic_name": "Nueva", "phone": "1"})
    actualizar.assert_called_once_with("c1", {"phone": "300"})
    entidad, lineas = historial.call_args.args
    assert entidad == "client" and [l[:2] for l in lineas] == [("n1", "create"), ("c1", "update")]
    assert lineas[1][2]["phone"] == {"antes": "0", "despues": "300"}


def test_un_precio_que_revienta_no_corta_la_carga():
    cambios = [{"tabla": "catalog_tests", "code": "1", "despues": 1000},
               {"tabla": "catalog_tests", "code": "2", "despues": 2000},
               {"tabla": "catalog_tests", "code": "3", "despues": -5}]
    leer = [RuntimeError("timeout"), {"price": 1}]
    with patch("app.services.db.get_catalog_item", side_effect=leer), \
         patch("app.services.db.update_catalog_item", return_value={"price": 2000}), \
         patch("app.services.db.log_catalog_change"):
        hechos, fallidos = imports_aplicar.aplicar_precios(cambios, "ana")
    assert hechos == 1 and len(fallidos) == 2


def test_portafolio_revalida_lo_que_vuelve_del_navegador():
    with patch("app.services.db.create_catalog_item") as crear:
        hechos, fallidos = imports_aplicar.aplicar_portafolio(
            [{"tabla": "catalog_tests", "code": "9", "name": "X", "price": 1000, "category": ""}], "ana")
    assert hechos == 0 and fallidos and not crear.called


def test_motorizados_solo_cambia_el_telefono_y_exige_telefono_al_crear():
    plan = imports_aplicar.plan_motorizados([{"name": "Nuevo", "phone": ""}], [])
    assert plan["crear"] == [] and "teléfono" in plan["errores"][0]
    with patch("app.services.db.update_courier", return_value=True) as actualizar, \
         patch("app.services.audit_db.registrar"):
        imports_aplicar.aplicar_motorizados({"actualizar": [
            {"id": "m1", "cambios": {"phone": "300", "is_active": False}}]})
    actualizar.assert_called_once_with("m1", {"phone": "300"})
