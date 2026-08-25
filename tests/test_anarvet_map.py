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
