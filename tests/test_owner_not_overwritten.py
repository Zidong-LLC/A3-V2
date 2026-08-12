"""
ERR-092 — el propietario ya capturado no se puede pisar con "Sin propietario".

QA en vivo 2026-07-27 (chat 1): el cliente respondió "Luciano" al propietario y el bot
acusó "Perfecto, registro Luciano como propietario. ¿Quieres dejar alguna observación?".
Al turno siguiente el cliente dijo "No, no tengo ninguna observación" y el propietario
quedó guardado como "Sin propietario".

Causa: `_detect_which_field_is_being_asked` lee el mensaje del bot COMPLETO, así que el
ACUSE ("...como propietario") le hace creer que todavía se pide el propietario; y el token
"ninguna" de la respuesta sobre observaciones dispara `_says_no_owner`.
"""
from app import agent


def _history(bot_msg: str) -> list[dict]:
    return [{"role": "bot", "content": bot_msg}]


ACUSE_CON_PREGUNTA_DE_OBSERVACIONES = (
    "Perfecto, registro Luciano como propietario. "
    "¿Quieres dejar alguna observación para la orden o la registramos sin observaciones?"
)


def test_detector_still_sees_owner_in_the_acknowledgement():
    """El detector sigue confundido (no se tocó): por eso hace falta el blindaje."""
    assert agent._detect_which_field_is_being_asked(
        _history(ACUSE_CON_PREGUNTA_DE_OBSERVACIONES)) == "owner_name"
    assert agent._says_no_owner("No, no tengo ninguna observación") is True


def test_no_observations_answer_does_not_erase_the_owner():
    """El caso real: propietario ya capturado + 'ninguna observación' -> se conserva."""
    prev = {"owner_name": "Luciano"}
    fields = {"owner_name": "Luciano"}
    agent._apply_no_owner_shortcut(
        fields, prev, "No, no tengo ninguna observación",
        _history(ACUSE_CON_PREGUNTA_DE_OBSERVACIONES))
    assert fields["owner_name"] == "Luciano"


def test_owner_from_previous_turn_is_also_protected():
    """Aunque el nombre venga solo del estado previo, tampoco se pisa."""
    prev = {"owner_name": "Luciano"}
    fields = {}
    agent._apply_no_owner_shortcut(
        fields, prev, "ninguna", _history(ACUSE_CON_PREGUNTA_DE_OBSERVACIONES))
    assert fields.get("owner_name") in (None, "Luciano")


def test_stray_patient_still_registers_sin_propietario():
    """La regla de negocio original sigue viva: sin propietario previo, se registra."""
    fields = {}
    agent._apply_no_owner_shortcut(
        fields, {}, "es callejero, no tiene dueño",
        _history("¿Cuál es el nombre del propietario?"))
    assert fields["owner_name"] == "Sin propietario"
