"""Emparejamiento cod_cliente de Anarvet ↔ clients (Anarvet Fase 2).

El matcher original dejó 100 de 184 códigos sin resolver, y con ellos el 41% de los
informes sin dueño — incluidos los 65 de Emergencias Veterinarias Integrales, un cliente
que SÍ está en nuestra base. Lo que separaba los nombres era la palabrería comercial.

La regla que no se negocia: con más de un destino posible no se elige. Un mapeo errado le
muestra los resultados de un paciente a la veterinaria equivocada.
"""
from pathlib import Path

from app import anarvet_map
from app.anarvet_map import candidatos_para, normalizar, planificar, sugerencias


def _cliente(nombre, id_="c1", activo=True):
    return {"id": id_, "clinic_name": nombre, "is_active": activo}


# ── Normalización ────────────────────────────────────────────────────────────────

def test_la_palabreria_comercial_no_distingue_a_nadie():
    """Casos reales de la base: los tres nombres son la misma veterinaria."""
    assert normalizar("Clínica Veterinaria El Panda") == normalizar("Veterinaria el Panda")
    assert normalizar("Clinica Veterinaria Zoopecas") == normalizar("Zoopecas SAS")
    assert normalizar("Hospital Veterinario Praga") == normalizar("Praga Veterinaria")


def test_normaliza_tildes_y_puntuacion():
    assert normalizar("Clínica  Veterinaria,  Aquiles.") == "aquiles"


def test_un_nombre_que_es_todo_ruido_no_matchea_con_nadie():
    """'Centro Medico Veterinario' (caso real) no distingue a ninguna clínica: si se
    dejara matchear, emparejaría con cualquier otra que también sea genérica."""
    assert normalizar("Centro Medico Veterinario") == ""
    assert candidatos_para("Centro Medico Veterinario",
                           [_cliente("Centro Medico Veterinario")]) == []


# ── Candidatos y la regla de privacidad ──────────────────────────────────────────

def test_encuentra_al_cliente_aunque_el_nombre_este_escrito_distinto():
    clientes = [_cliente("Emergencias Veterinarias Integrales", "evi")]
    assert [c["id"] for c in candidatos_para("Emergencias Veterinarias Integrales SAS", clientes)] == ["evi"]


def test_con_dos_destinos_posibles_devuelve_los_dos_y_no_elige():
    """En la base de A3 esto pasa por clientes duplicados ('Zoopecas' y 'Zoopecas SAS')."""
    clientes = [_cliente("Clinica Veterinaria Zoopecas", "a"), _cliente("Zoopecas SAS", "b")]
    assert len(candidatos_para("Clinica Veterinaria Zoopecas", clientes)) == 2


# ── Plan: qué se aplica solo y qué no ────────────────────────────────────────────

def test_el_plan_separa_lo_seguro_de_lo_que_decide_un_humano():
    pendientes = [
        {"cod_cliente": "75", "nombre_cliente": "Emergencias Veterinarias Integrales"},
        {"cod_cliente": "572", "nombre_cliente": "Clinica Veterinaria Zoopecas"},
        {"cod_cliente": "999", "nombre_cliente": "Veterinaria Que No Existe"},
    ]
    clientes = [
        _cliente("Emergencias Veterinarias Integrales", "evi"),
        _cliente("Clinica Veterinaria Zoopecas", "z1"),
        _cliente("Zoopecas SAS", "z2"),
    ]
    plan = planificar(pendientes, clientes)

    assert [a["pendiente"]["cod_cliente"] for a in plan["automaticos"]] == ["75"]
    assert plan["automaticos"][0]["cliente"]["id"] == "evi"
    assert [a["pendiente"]["cod_cliente"] for a in plan["ambiguos"]] == ["572"]
    assert len(plan["ambiguos"][0]["candidatos"]) == 2
    assert [s["pendiente"]["cod_cliente"] for s in plan["sin_candidato"]] == ["999"]


def test_un_cliente_inactivo_no_es_destino():
    pendientes = [{"cod_cliente": "1", "nombre_cliente": "Veterinaria Fantasma"}]
    plan = planificar(pendientes, [_cliente("Veterinaria Fantasma", "x", activo=False)])
    assert not plan["automaticos"] and len(plan["sin_candidato"]) == 1


def test_el_modulo_no_puede_escribir_en_la_base():
    """Es puro a propósito: recibe las filas ya cargadas y solo clasifica. Por eso el plan
    se puede simular contra la base real antes de aplicar un solo cambio."""
    fuente = Path(anarvet_map.__file__).read_text(encoding="utf-8")
    assert "from app.services import db" not in fuente
    assert "import db" not in fuente
    assert not hasattr(anarvet_map, "db")


# ── Sugerencias (solo proponen, nunca asignan) ───────────────────────────────────

def test_sugiere_el_parecido_cuando_no_hay_coincidencia_exacta():
    """Caso real: los nombres difieren en un 'de'."""
    clientes = [_cliente("Clinica De Diagnostico Veterinario", "dx"), _cliente("Animal Pets", "ap")]
    props = sugerencias("Clinica Diagnostico Veterinario", clientes)
    assert props and props[0]["cliente"]["id"] == "dx"
    assert props[0]["similitud"] >= 0.70


def test_no_sugiere_cualquier_cosa():
    assert sugerencias("Vetgo", [_cliente("Hospital Veterinario San Martín", "x")]) == []


# ── Duplicados de la base de A3: el NIT los delata ───────────────────────────────

def _con_nit(nombre, id_, nit, motorizado=False):
    fila = _cliente(nombre, id_)
    fila["tax_id"] = nit
    if motorizado:
        fila["client_courier_assignment"] = [{"courier_id": "m1"}]
    return fila


def test_el_mismo_nit_con_y_sin_digito_es_el_mismo_cliente():
    """Caso real: 'Barber Dog' (1031127036) y 'Veterinaria Barber Dog' (1031127036-5)."""
    candidatos = [
        _con_nit("Barber Dog", "a", "1031127036"),
        _con_nit("Veterinaria Barber Dog", "b", "1031127036-5", motorizado=True),
    ]
    elegido = anarvet_map.desempatar_duplicado(candidatos)
    assert elegido and elegido["id"] == "b", "gana el que la operación usa de verdad"


def test_no_desempata_cuando_los_nit_son_distintos():
    """'Hospital Veterinario Praga' (1013618770) y 'Praga Veterinaria' (40077667) son dos
    clientes distintos con nombre parecido: elegir uno sería adivinar."""
    candidatos = [
        _con_nit("Hospital Veterinario Praga", "a", "1013618770"),
        _con_nit("Praga Veterinaria", "b", "40077667", motorizado=True),
    ]
    assert anarvet_map.desempatar_duplicado(candidatos) is None


def test_no_desempata_si_ninguno_tiene_motorizado():
    candidatos = [_con_nit("Vet X", "a", "900123"), _con_nit("Clinica Vet X", "b", "900123-4")]
    assert anarvet_map.desempatar_duplicado(candidatos) is None


def test_no_desempata_sin_nit():
    candidatos = [_con_nit("Vet Y", "a", ""), _con_nit("Clinica Vet Y", "b", "", motorizado=True)]
    assert anarvet_map.desempatar_duplicado(candidatos) is None


def test_una_cedula_de_diez_digitos_no_se_recorta():
    """Recortarle el último dígito la convertía en otro documento y rompía el par."""
    assert anarvet_map._nit_base("1031127036") == "1031127036"
    assert anarvet_map._nit_base("1031127036-5") == "1031127036"
    assert anarvet_map._nit_base("901905889") == "901905889"


def test_el_duplicado_resuelto_queda_registrado_en_el_plan():
    """Se anota con qué otro registro chocaba: es la lista de duplicados para A3."""
    pendientes = [{"cod_cliente": "1", "nombre_cliente": "Veterinaria Barber Dog"}]
    clientes = [
        _con_nit("Barber Dog", "a", "1031127036"),
        _con_nit("Veterinaria Barber Dog", "b", "1031127036-5", motorizado=True),
    ]
    plan = planificar(pendientes, clientes)
    assert len(plan["automaticos"]) == 1 and not plan["ambiguos"]
    assert plan["automaticos"][0]["duplicado"] == ["Barber Dog", "Veterinaria Barber Dog"]


def _con_dir(nombre, id_, nit, direccion, motorizado=False):
    fila = _con_nit(nombre, id_, nit, motorizado)
    fila["address"] = direccion
    return fila


def test_mismo_nit_pero_locales_distintos_son_SUCURSALES():
    """Corrección del usuario (2026-08-25): un NIT compartido no significa duplicado. Una
    veterinaria puede tener varias sucursales, todas con el mismo NIT y a veces con el
    mismo nombre. Elegir una mandaría los resultados de una sede a la otra."""
    candidatos = [
        _con_dir("Veterinaria Aquiles", "a", "1031142246", "CR 81 72 24 SUR"),
        _con_dir("Clinica Veterinaria Aquiles", "b", "1031142246-8", "CR 81 72-25 SUR", True),
    ]
    assert anarvet_map.desempatar_duplicado(candidatos) is None


def test_la_misma_direccion_escrita_distinto_sigue_siendo_el_mismo_local():
    """'AV 30 1-136' y 'AV 30 1 136' son el mismo lugar: eso sí es un duplicado."""
    candidatos = [
        _con_dir("Clinivet Perritos CIA Perotes", "a", "901502986", "AV 30 1 136"),
        _con_dir("Clinivet Perritos CIA Perrotes", "b", "901502986-1", "AV 30 1-136", True),
    ]
    elegido = anarvet_map.desempatar_duplicado(candidatos)
    assert elegido and elegido["id"] == "b"


def test_el_digito_verificador_pegado_sin_guion_es_el_mismo_contribuyente():
    """'Policlinica 20 de Julio' figura con 19441545 y 194415453: mismo local, misma
    dirección, y el segundo es el primero más su verificador."""
    candidatos = [
        _con_dir("Policlinica 20 de Julio", "a", "19441545", "CL 24 SUR 6-56"),
        _con_dir("Policlinica Veterinaria 20 De Julio", "b", "194415453", "CL 24 SUR 6-56", True),
    ]
    elegido = anarvet_map.desempatar_duplicado(candidatos)
    assert elegido and elegido["id"] == "b"


def test_dos_nit_que_solo_se_parecen_no_son_el_mismo():
    """80871972 y 901684701 son negocios distintos, por más que compartan el nombre."""
    candidatos = [
        _con_dir("Veterinaria Piscis", "a", "80871972", "CL 1"),
        _con_dir("Veterinaria Piscis SAS", "b", "901684701", "CL 1", True),
    ]
    assert anarvet_map.desempatar_duplicado(candidatos) is None
