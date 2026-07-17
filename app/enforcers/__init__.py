"""Guardrails post-modelo (enforcers), por responsabilidad (Paso 3.4).

Cada enforcer recibe el ai_response y lo corrige/valida de forma determinística.
Migración incremental desde agent.py: acá van los que son cerrados (sin helpers que
queden en agent, para no crear imports circulares).
"""
from app.enforcers.dinero import (  # noqa: F401
    enforce_selected_tests_are_catalog_codes,
)
