"""
Edición del catálogo desde la plataforma: precio y etiqueta de especie.

El catálogo era de SOLO LECTURA — cambiar un precio exigía SQL a mano. A3 pidió poder
editarlo el 07/04 (es el pendiente más antiguo del proyecto) y marcar la especie exclusiva el
28/07. Sin esa etiqueta no pueden reclasificar sus 73 perfiles, que es lo que hace útil la
decisión 012.

Lo que estos tests protegen es sobre todo el DINERO: el precio entra por una request y
termina en el catálogo que factura, así que la validación no puede quedar floja, y cada
cambio tiene que quedar auditado con su valor anterior.
"""
import pytest

from app import dashboard as dash


@pytest.fixture
def cliente(monkeypatch):
    """App Flask con sesión autenticada y la capa de datos mockeada."""
    from app.main import app

    registro = {"updates": [], "auditoria": []}
    monkeypatch.setattr(dash.db, "get_catalog_item",
                        lambda t, c: {"code": c, "price": 14000, "species": "ambos"} if c == "1101" else None)
    monkeypatch.setattr(dash.db, "update_catalog_item",
                        lambda t, c, cambios: registro["updates"].append((t, c, cambios)) or {"code": c, **cambios})
    monkeypatch.setattr(dash.db, "log_catalog_change",
                        lambda t, c, antes, despues, por: registro["auditoria"].append((c, antes, despues, por)))

    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["dashboard_authenticated"] = True
            s["dashboard_username"] = "tester"
        c.registro = registro
        yield c


def _post(cliente, payload):
    return cliente.post("/api/dashboard/catalog-item", json=payload)


def test_cambia_el_precio_de_un_analisis(cliente):
    r = _post(cliente, {"kind": "analisis", "code": "1101", "price": 15500})
    assert r.status_code == 200
    assert cliente.registro["updates"] == [("catalog_tests", "1101", {"price": 15500})]


def test_el_cambio_de_precio_queda_auditado_con_el_valor_anterior(cliente):
    """Tocar un precio mueve plata: tiene que poder rastrearse quién y desde cuánto."""
    _post(cliente, {"kind": "analisis", "code": "1101", "price": 15500})
    code, antes, despues, por = cliente.registro["auditoria"][0]
    assert (code, antes, despues, por) == ("1101", {"price": 14000}, {"price": 15500}, "tester")


def test_marca_un_perfil_como_exclusivo_de_una_especie(cliente):
    r = _post(cliente, {"kind": "perfil", "code": "1101", "species": "Canino"})
    assert r.status_code == 200
    assert cliente.registro["updates"] == [("catalog_profiles", "1101", {"species": "canino"})]


def test_acepta_precio_con_separadores_de_miles(cliente):
    """El operador escribe '15.500', no '15500'."""
    r = _post(cliente, {"kind": "analisis", "code": "1101", "price": "15.500"})
    assert r.status_code == 200
    assert cliente.registro["updates"][0][2] == {"price": 15500}


@pytest.mark.parametrize("payload,motivo", [
    ({"kind": "otra_cosa", "code": "1101", "price": 1}, "tabla inventada"),
    ({"kind": "analisis", "price": 1}, "sin código"),
    ({"kind": "analisis", "code": "1101", "price": "gratis"}, "precio no numérico"),
    ({"kind": "analisis", "code": "1101", "price": -5}, "precio negativo"),
    ({"kind": "analisis", "code": "1101", "species": "marciano"}, "especie inexistente"),
    ({"kind": "analisis", "code": "1101"}, "nada para cambiar"),
])
def test_rechaza_entradas_invalidas(cliente, payload, motivo):
    assert _post(cliente, payload).status_code == 400, motivo
    assert not cliente.registro["updates"], f"no debió escribir nada ({motivo})"


def test_codigo_inexistente_da_404(cliente):
    assert _post(cliente, {"kind": "analisis", "code": "9999", "price": 1000}).status_code == 404
    assert not cliente.registro["updates"]


def test_exige_sesion(monkeypatch):
    """Sin login no se toca el catálogo."""
    from app.main import app

    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        r = c.post("/api/dashboard/catalog-item", json={"kind": "analisis", "code": "1101", "price": 1})
    assert r.status_code in (302, 401, 403)


def test_la_capa_de_datos_rechaza_una_tabla_arbitraria():
    """`tabla` viene de la request: nunca puede componerse libremente."""
    from app.services import db

    with pytest.raises(ValueError):
        db.update_catalog_item("clients", "x", {"price": 1})
