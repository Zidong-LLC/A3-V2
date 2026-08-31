"""Cargas masivas por CSV: lectura del archivo, plan y aplicación con confirmación."""
import io
from unittest.mock import patch

from app import imports

TESTS = [{"code": "952", "name": "Hemograma", "price": 30000},
         {"code": "653", "name": "Química renal", "price": 45000}]
PROFILES = [{"code": "2401", "name": "Perfil PCR", "price": 157000}]
CLIENTES = [
    {"id": "c-1", "clinic_name": "Veterinaria Piscis", "tax_id": "80871972", "phone": "3001", "address": "", "city": None, "email": None},
    {"id": "c-2", "clinic_name": "Animal House", "tax_id": None, "phone": None, "address": "CL 1", "city": "Bogotá", "email": None},
]


def _csv(texto: str) -> bytes:
    return texto.encode("utf-8")


def _nombre_coincide(a, b):
    return imports.norm(a) == imports.norm(b)


# ── Lectura del archivo ──────────────────────────────────────────────────────

def test_lee_encabezados_en_cualquier_orden_y_con_alias():
    filas, ignorados = imports.leer_csv(_csv("Precio;Codigo\n30.000;952\n"))
    assert filas == [{"price": "30.000", "code": "952"}]
    assert ignorados == []


def test_reporta_las_columnas_que_no_entiende():
    filas, ignorados = imports.leer_csv(_csv("codigo,precio,color favorito\n952,30000,azul\n"))
    assert ignorados == ["color favorito"]
    assert filas[0]["code"] == "952"


def test_el_bom_del_excel_no_rompe_el_primer_encabezado():
    filas, _ = imports.leer_csv("﻿codigo,precio\n952,30000\n".encode("utf-8"))
    assert filas[0]["code"] == "952"


def test_precio_con_simbolos_y_decimales():
    assert imports.precio("$ 85.000") == 85000
    assert imports.precio("85000,00") == 85000
    assert imports.precio("1.234.567") == 1234567
    assert imports.precio("sin precio") is None


# ── Plan de precios ──────────────────────────────────────────────────────────

def test_plan_precios_solo_lista_lo_que_cambia():
    filas, _ = imports.leer_csv(_csv("codigo,precio\n952,35000\n653,45000\n"))
    plan = imports.plan_precios(filas, TESTS, PROFILES)
    assert plan["iguales"] == 1
    assert plan["actualizar"] == [{"tabla": "catalog_tests", "code": "952", "name": "Hemograma",
                                   "antes": 30000, "despues": 35000}]


def test_plan_precios_no_crea_codigos_que_no_existen():
    filas, _ = imports.leer_csv(_csv("codigo,precio\n9999,10000\n"))
    plan = imports.plan_precios(filas, TESTS, PROFILES)
    assert plan["actualizar"] == []
    assert "no existe en el catálogo" in plan["errores"][0]


def test_plan_precios_reporta_un_precio_ilegible_en_vez_de_adivinar():
    filas, _ = imports.leer_csv(_csv("codigo,precio\n952,consultar\n"))
    plan = imports.plan_precios(filas, TESTS, PROFILES)
    assert plan["actualizar"] == []
    assert "ilegible" in plan["errores"][0]


# ── Plan de portafolio ───────────────────────────────────────────────────────

def test_plan_portafolio_crea_solo_lo_que_falta():
    filas, _ = imports.leer_csv(_csv("codigo,nombre,precio,tipo\n952,Hemograma,30000,analisis\n"
                                     "3001,Prueba nueva,50000,analisis\n"
                                     "3002,Perfil nuevo,90000,perfil\n"))
    plan = imports.plan_portafolio(filas, TESTS, PROFILES)
    assert plan["iguales"] == 1
    assert [c["code"] for c in plan["crear"]] == ["3001", "3002"]
    assert plan["crear"][1]["tabla"] == "catalog_profiles"


def test_plan_portafolio_no_deja_pasar_un_codigo_repetido_en_el_archivo():
    filas, _ = imports.leer_csv(_csv("codigo,nombre,precio\n3001,Uno,1000\n3001,Otro,2000\n"))
    plan = imports.plan_portafolio(filas, TESTS, PROFILES)
    assert len(plan["crear"]) == 1
    assert "repetido" in plan["errores"][0]


# ── Plan de clientes ─────────────────────────────────────────────────────────

def test_plan_clientes_completa_datos_vacios_y_no_pisa_los_que_estan():
    filas, _ = imports.leer_csv(_csv("nombre,nit,telefono,direccion\n"
                                     "Veterinaria Piscis,80871972,3999,CR 88\n"))
    plan = imports.plan_clientes(filas, CLIENTES, _nombre_coincide)
    assert plan["crear"] == []
    assert plan["actualizar"][0]["cambios"] == {"address": "CR 88"}  # el teléfono ya estaba


def test_plan_clientes_cruza_por_nombre_cuando_no_hay_nit():
    filas, _ = imports.leer_csv(_csv("nombre,nit\nAnimal House,900123456\n"))
    plan = imports.plan_clientes(filas, CLIENTES, _nombre_coincide)
    assert plan["crear"] == []
    assert plan["actualizar"][0]["cambios"] == {"tax_id": "900123456"}


def test_plan_clientes_crea_los_que_no_estan():
    filas, _ = imports.leer_csv(_csv("nombre,nit\nVeterinaria Nueva,901000000\n"))
    plan = imports.plan_clientes(filas, CLIENTES, _nombre_coincide)
    assert plan["crear"] == [{"clinic_name": "Veterinaria Nueva", "tax_id": "901000000"}]


def test_plan_clientes_no_reparte_la_direccion_entre_sedes_del_mismo_nit():
    """La dirección es de cada sede: con NIT compartido no se aplica a ninguna
    (solo el correo se comparte, que es del NIT). Antes esto era revisión manual."""
    dos_sedes = CLIENTES + [{"id": "c-3", "clinic_name": "Veterinaria Piscis", "tax_id": "80871972"}]
    filas, _ = imports.leer_csv(_csv("nombre,nit,direccion\nVeterinaria Piscis,80871972,CR 88\n"))
    plan = imports.plan_clientes(filas, dos_sedes, _nombre_coincide)
    assert plan["crear"] == [] and plan["actualizar"] == []
    assert plan["errores"] == []


# ── La pantalla ──────────────────────────────────────────────────────────────

def _get_test_client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def _login(client):
    with client.session_transaction() as sess:
        sess["dashboard_authenticated"] = True
        sess["dashboard_username"] = "admin"


def test_la_pantalla_de_cargas_exige_sesion():
    response = _get_test_client().get("/cargas")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_la_vista_previa_no_escribe_nada():
    client = _get_test_client()
    _login(client)
    with patch("app.dashboard_import.db.list_catalog_tests", return_value=TESTS), \
         patch("app.dashboard_import.db.list_catalog_profiles", return_value=PROFILES), \
         patch("app.dashboard_import.db.update_catalog_item") as escribe:
        response = client.post("/cargas/previsualizar", data={
            "tipo": "precios",
            "csv": (io.BytesIO(_csv("codigo,precio\n952,35000\n")), "precios.csv"),
        }, content_type="multipart/form-data")
    cuerpo = response.get_data(as_text=True)
    escribe.assert_not_called()
    assert "Aplicar estos cambios" in cuerpo
    assert "Hemograma" in cuerpo


def test_aplicar_escribe_el_precio_y_deja_auditoria():
    client = _get_test_client()
    _login(client)
    plan = {"tipo": "precios", "actualizar": [
        {"tabla": "catalog_tests", "code": "952", "antes": 30000, "despues": 35000}]}
    with patch("app.dashboard_import.db.get_catalog_item", return_value={"code": "952", "price": 30000}), \
         patch("app.dashboard_import.db.update_catalog_item", return_value={"code": "952", "price": 35000}) as escribe, \
         patch("app.dashboard_import.db.log_catalog_change") as auditoria:
        response = client.post("/cargas/aplicar", data={"plan": __import__("json").dumps(plan)},
                               follow_redirects=True)
    assert response.status_code == 200
    escribe.assert_called_once_with("catalog_tests", "952", {"price": 35000})
    auditoria.assert_called_once()


def test_aplicar_ignora_un_plan_con_tabla_inventada():
    client = _get_test_client()
    _login(client)
    plan = {"tipo": "precios", "actualizar": [{"tabla": "clients", "code": "952", "despues": 1}]}
    with patch("app.dashboard_import.db.update_catalog_item") as escribe:
        client.post("/cargas/aplicar", data={"plan": __import__("json").dumps(plan)},
                    follow_redirects=True)
    escribe.assert_not_called()


def test_aplicar_no_pisa_un_codigo_de_portafolio_que_ya_existe():
    client = _get_test_client()
    _login(client)
    plan = {"tipo": "portafolio", "crear": [
        {"tabla": "catalog_tests", "code": "952", "name": "Hemograma", "price": 1}]}
    with patch("app.dashboard_import.db.get_catalog_item", return_value={"code": "952"}), \
         patch("app.dashboard_import.db.create_catalog_item") as crea:
        client.post("/cargas/aplicar", data={"plan": __import__("json").dumps(plan)},
                    follow_redirects=True)
    crea.assert_not_called()


def test_create_client_pone_billing_type_porque_la_tabla_lo_exige():
    """La columna es NOT NULL sin default: sin esto toda alta por CSV revienta con 23502.
    Se descubrió aplicando la lista real de terceros v3 (ninguna alta funcionaba)."""
    from unittest.mock import MagicMock, patch
    from app.services import db as dbs

    cliente = MagicMock()
    with patch.object(dbs, "_client", cliente):
        dbs.create_client({"clinic_name": "Vet Nueva", "tax_id": "900123456"})
    enviado = cliente.table.return_value.insert.call_args.args[0]
    assert enviado["billing_type"] == "cash"
    assert enviado["is_active"] is True


def test_una_alta_que_revienta_no_cancela_las_demas():
    """Con la lista real de terceros, un teléfono duplicado a mitad de carga dejó
    17 altas hechas y las actualizaciones sin aplicar. Cada fila va por separado."""
    from unittest.mock import patch
    from app.dashboard_import import _aplicar_clientes

    plan = {"crear": [{"clinic_name": "Vet A"}, {"clinic_name": "Vet B"}, {"clinic_name": "Vet C"}],
            "actualizar": [{"id": "c-1", "clinic_name": "Vet D", "cambios": {"email": "d@d.co"}}]}
    def crear(payload):
        if payload["clinic_name"] == "Vet B":
            raise RuntimeError('duplicate key value violates unique constraint "clients_phone_key"')
        return {"id": "nuevo"}
    with patch("app.dashboard_import.db.create_client", side_effect=crear), \
         patch("app.dashboard_import.db.get_client_by_id", return_value={"id": "c-1"}), \
         patch("app.dashboard_import.db.update_client_profile", return_value=True):
        creados, actualizados, fallidos = _aplicar_clientes(plan)
    assert (creados, actualizados) == (2, 1)
    assert fallidos == ["Vet B: el teléfono ya pertenece a otro cliente"]


def test_el_correo_de_un_nit_compartido_completa_todas_las_sedes_vacias():
    """El correo es del NIT (ahí llega la factura); el teléfono es de cada sede y no
    se comparte. Con la lista real de terceros, 106 filas quedaban en revisión manual
    solo porque el NIT apuntaba a dos sedes."""
    from app.imports import plan_clientes

    sedes = [{"id": "s-1", "clinic_name": "Club Marruecos", "tax_id": "1055126168", "email": ""},
             {"id": "s-2", "clinic_name": "Club Venecia", "tax_id": "1055126168", "email": "ya@tiene.co"}]
    fila = {"name": "Club Animals", "tax_id": "1055126168", "email": "nit@club.co", "phone": "3000000000"}
    plan = plan_clientes([fila], sedes, lambda a, b: False)
    assert plan["errores"] == []
    assert plan["crear"] == []
    assert plan["actualizar"] == [{"id": "s-1", "clinic_name": "Club Marruecos",
                                   "cambios": {"email": "nit@club.co"}}]


def test_dos_coincidencias_solo_por_nombre_siguen_siendo_revision_manual():
    """Sin NIT no hay certeza de que sean sedes: la ambigüedad queda para una persona."""
    from app.imports import plan_clientes

    parecidos = [{"id": "c-1", "clinic_name": "Vet Andes Norte", "tax_id": "", "email": ""},
                 {"id": "c-2", "clinic_name": "Vet Andes Sur", "tax_id": "", "email": ""}]
    plan = plan_clientes([{"name": "Vet Andes", "email": "x@x.co"}], parecidos, lambda a, b: True)
    assert plan["actualizar"] == []
    assert len(plan["errores"]) == 1
