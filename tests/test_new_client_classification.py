"""
Regresión (chat 4 real, 2026-06-22): "Si la uno" (selección de la opción 1 del menú de
bienvenida) escalaba a recepción como si fuera cliente nuevo.

Causa: `_confirms_new_client` da True para cualquier afirmación pelada de ≤4 palabras con
"sí" ("Si la uno"), y el flujo de identificación la tomaba como "soy cliente nuevo" sin
verificar si el bot lo había preguntado. Es el patrón que el usuario marcó en L46: clasificar
por longitud en vez de por contexto. El fix: una afirmación pelada solo significa "soy nuevo"
si el bot acaba de preguntarlo; la mención EXPLÍCITA de "cliente nuevo" cuenta siempre.
"""
from app import agent


def test_menu_option_selection_is_not_explicit_new_client():
    """Una selección del menú no es una declaración de cliente nuevo."""
    for text in ("Si la uno", "dale la uno", "la uno", "1", "sí", "ok la 1"):
        assert agent._explicitly_says_new_client(text) is False


def test_explicit_new_client_mention_counts():
    assert agent._explicitly_says_new_client("soy cliente nuevo") is True
    assert agent._explicitly_says_new_client("cliente nuevo") is True


def test_negated_new_client_does_not_count():
    assert agent._explicitly_says_new_client("no soy cliente nuevo") is False


def test_bare_affirmative_still_confirms_only_within_context():
    """`_confirms_new_client` sigue reconociendo la afirmación pelada (para usarse SOLO
    cuando el bot acaba de preguntar '¿eres cliente nuevo?'), pero por sí sola no es
    declaración explícita."""
    assert agent._confirms_new_client("Si la uno") is True
    assert agent._explicitly_says_new_client("Si la uno") is False
