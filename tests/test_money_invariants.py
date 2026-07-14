"""
INVARIANTES DE DINERO — probadas sobre la LÓGICA DETERMINISTA, con inputs reales.

Antes esto corría un turno completo FINGIENDO la respuesta del modelo (generate_turn
mockeado con "Coprológico $23k", "9999" en selected_tests, etc.). Fingir el modelo no
detecta el bug real: el modelo en vivo escribe el precio o inventa el código de formas
que el mock no anticipa. Los escenarios end-to-end reales viven en los QA con MODELO
REAL (test_qa_realista_guardrails con OpenAI, tools/scripts/validate_flows.py).

Acá quedan los invariantes probados DIRECTO sobre las funciones deterministas que los
hacen cumplir, con el dato tal como se cuela (un código inventado, un precio en el texto):

  I1  el validador descarta cualquier código que no exista en el catálogo.
  I2  el precio escrito en el texto se quita del nombre del análisis.
  I4  el total se calcula desde los códigos del catálogo, nunca del texto del modelo.
"""
import re
from unittest.mock import patch

from app import agent
from app.services import db
from app.text import strip_price_text

from tests.test_catalog_resolution import CATALOG

CATALOG_BY_CODE = {r["code"]: r for r in CATALOG}


def test_i1_invalid_code_is_dropped_before_registering():
    """I1: un código inventado ('9999') que se cuela en selected_tests se descarta antes
    de registrar; el código real ('1101') se conserva. Nunca una orden con análisis fantasma."""
    ai = {"captured_fields": {"selected_tests": ["1101", "9999"]}}
    with patch.object(db, "list_catalog_tests", return_value=CATALOG):
        out = agent._enforce_selected_tests_are_catalog_codes(ai)
    assert agent._as_text_items(out["captured_fields"]["selected_tests"]) == ["1101"]


def test_i2_invented_price_is_stripped_from_exam_text():
    """I2: '$23k' escrito por el modelo se quita del nombre del análisis (no viaja a la orden)."""
    cleaned = strip_price_text("Coprológico $23k")
    assert not re.search(r"\$\s*\d", cleaned)
    assert not re.search(r"\d\s*k\b", cleaned.lower())
    assert "Coprológico" in cleaned


def test_i4_total_comes_from_catalog_codes_not_model_text():
    """I4: el dinero sale de los precios del catálogo (por código), no de una cifra del texto:
    el subtotal = suma de precios del catálogo y el total = subtotal - descuento por tramos."""
    rows = [CATALOG_BY_CODE["1101"], CATALOG_BY_CODE["1309"]]   # 14.000 + 12.000
    result = agent.calculate_custom_profile_total(rows)
    assert result["subtotal"] == sum(r["price"] for r in rows)          # base = catálogo (26.000)
    assert result["total"] == result["subtotal"] - result["discount"]   # total coherente
