"""
ERR-088 — el escalado por "no encuentro tu registro" tiene que poder deshacerse.

`_escalate_unfound_client` marcaba `_blocked`, el mismo flag que usa el cliente
particular/final al que A3 no le presta servicio. Ese flag corta el turno al principio de
`process_turn`, así que el cliente que se corregía un turno después ("sí estamos, somos
Maxivet") no volvía a recibir NUNCA una respuesta. En el corpus real (conv 10) hay tres
rachas de silencio de 9, 6 y 10 turnos, con el cliente escribiendo "El bot no esta activo".

Ahora el escalado usa su propio flag y se reabre SOLO si el identificador existe en la base;
cualquier otro mensaje mantiene el silencio, para no pisar al humano que tomó el caso.

Autorizado por el usuario el 2026-08-12 (toca B3, marcado APROBADO en el contrato).
"""
import pytest

from app import agent


@pytest.fixture(autouse=True)
def base_con_maxivet(monkeypatch):
    """Mock de infraestructura: Maxivet existe, "Clinica Fantasma" no."""
    def _matches(query, limit=6):
        return [{"id": "cli-1", "clinic_name": "Maxivet"}] if "maxivet" in (query or "").lower() else []

    monkeypatch.setattr(agent.db, "find_client_matches", _matches)
    monkeypatch.setattr(agent.db, "find_clients_by_tax_id", lambda t: [])


def test_el_escalado_no_usa_el_flag_del_cliente_particular():
    """`_blocked` es el silencio definitivo; este escalado no debe reusarlo."""
    fields = {}
    agent._escalate_unfound_client(fields)
    assert fields.get("_escalated_unfound_client") is True
    assert "_blocked" not in fields


def test_un_nombre_que_existe_en_la_base_reabre_la_conversacion():
    """El caso real: el cliente se corrige y nombra una veterinaria que sí está."""
    assert agent._reidentifies_after_escalation("sí estamos, somos Maxivet") is True


def test_un_nombre_que_no_existe_no_reabre():
    assert agent._reidentifies_after_escalation("somos Clinica Fantasma") is False


def test_un_mensaje_sin_identificador_no_reabre():
    """Insistir sin dar datos mantiene el silencio: el humano ya tomó el caso."""
    assert agent._reidentifies_after_escalation("hola? alguien ahí?") is False
    assert agent._reidentifies_after_escalation("Buen dia") is False


def test_una_falla_de_la_base_no_reabre(monkeypatch):
    """Ante un error de red se mantiene el silencio (falla del lado seguro)."""
    def _explota(*_a, **_k):
        raise RuntimeError("supabase caído")

    monkeypatch.setattr(agent.db, "find_client_matches", _explota)
    assert agent._reidentifies_after_escalation("somos Maxivet") is False
