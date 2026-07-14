"""
Confirmación de dirección por SEÑAL semántica del LLM (Fase 3.3, piloto).

Estos tests ejercitan la LÓGICA DETERMINISTA con el texto REAL que escribe el cliente
("no hay drama, esa dirección está bien"), sin fingir la respuesta del modelo: la
lectura semántica (`user_intent_signal`) es la fuente primaria y los tokens el fallback.

El flujo end-to-end de ERR-046 (confirmación pendiente + respuesta esquiva que re-pregunta
la dirección) NO se prueba fingiendo el LLM —eso nunca detecta el bug real— sino con el
modelo real en `tools/scripts/validate_flows.py` (flujo H) y los QA adversariales.
"""
from app import agent


def test_confirms_address_signal_beats_misleading_tokens():
    """'no hay drama, esa dirección está bien' CONFIRMA, pero tiene un 'no' que hace que los
    tokens la RECHACEN. La lectura semántica de la IA (affirm) manda sobre los tokens."""
    msg = "no hay drama, esa dirección está bien"
    assert not agent._confirms_address(msg)                       # los tokens la tumban por el 'no'
    assert agent._confirms_address_now({"user_intent_signal": "affirm"}, msg)
    # y al revés: un 'sí' incidental NO confirma si la IA leyó que rechaza/corrige
    assert not agent._confirms_address_now({"user_intent_signal": "negate"}, "sí")


def test_rejects_address_by_signal():
    assert agent._rejects_address_now({"user_intent_signal": "negate"}, "esa no")
    assert agent._rejects_address_now({"user_intent_signal": "correction"}, "cambiala")
    assert not agent._rejects_address_now({"user_intent_signal": "affirm"}, "no")  # affirm gana


def test_address_signal_fallback_preserves_tokens():
    """Sin señal clara (unclear), se mantiene el comportamiento por tokens."""
    unclear = {"user_intent_signal": "unclear"}
    assert agent._confirms_address_now(unclear, "sí, correcta")
    assert not agent._confirms_address_now(unclear, "no, es otra")
    assert agent._rejects_address_now(unclear, "no, es otra")
