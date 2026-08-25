"""Servicio de PDF en el servidor (Anarvet Fase 2).

Solo hace falta para PUBLICAR un informe al portal. Ver e imprimir el informe desde el
navegador del personal nunca depende de esto — por eso el modo de fallo correcto es un
error claro y rápido, jamás un request colgado.
"""
from unittest.mock import patch

import pytest

from app.services import pdf
from app.services.pdf import PdfUnavailable


def test_apagado_por_defecto_falla_con_mensaje_claro(monkeypatch):
    """Se despliega apagado, igual que ANARVET_ENABLED: se enciende tras verificar /health."""
    monkeypatch.setattr(pdf, "PDF_ENABLED", False)
    with pytest.raises(PdfUnavailable, match="apagada"):
        pdf.html_to_pdf("<p>hola</p>")


def test_sin_playwright_no_rompe_el_arranque_ni_cuelga(monkeypatch):
    """El import es perezoso a propósito: que falte la librería no puede impedir que Flask
    levante, y al pedir un PDF tiene que fallar rápido y explicando qué pasa."""
    monkeypatch.setattr(pdf, "PDF_ENABLED", True)
    import builtins

    real_import = builtins.__import__

    def _sin_playwright(name, *args, **kwargs):
        if name.startswith("playwright"):
            raise ImportError("No module named 'playwright'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _sin_playwright)
    with pytest.raises(PdfUnavailable, match="playwright"):
        pdf.html_to_pdf("<p>hola</p>")


def test_el_semaforo_se_libera_aunque_el_render_falle(monkeypatch):
    """Si no se liberara, el primer error dejaría la generación trabada para siempre y el
    siguiente informe esperaría el timeout completo sin razón."""
    monkeypatch.setattr(pdf, "PDF_ENABLED", True)

    class _Boom:
        def __enter__(self):
            raise RuntimeError("chromium no arrancó")

        def __exit__(self, *a):
            return False

    with patch("playwright.sync_api.sync_playwright", return_value=_Boom()):
        with pytest.raises(RuntimeError):
            pdf.html_to_pdf("<p>hola</p>")

    assert pdf._UN_RENDER_A_LA_VEZ.acquire(timeout=0.1), "el semáforo quedó tomado"
    pdf._UN_RENDER_A_LA_VEZ.release()


def test_available_no_arranca_un_navegador_por_chequeo(monkeypatch):
    """/health se consulta seguido: arrancar Chromium cada vez sería absurdo."""
    monkeypatch.setattr(pdf, "PDF_ENABLED", True)
    monkeypatch.setattr(pdf, "_DISPONIBLE", None)
    llamadas = []

    class _P:
        def __enter__(self):
            llamadas.append(1)
            return self

        def __exit__(self, *a):
            return False

        @property
        def chromium(self):
            class _C:
                def launch(self, **kw):
                    return type("B", (), {"close": lambda s: None})()
            return _C()

    with patch("playwright.sync_api.sync_playwright", return_value=_P()):
        assert pdf.available() is True
        assert pdf.available() is True
    assert len(llamadas) == 1, "el resultado tiene que quedar cacheado"


def test_available_es_false_con_el_flag_apagado(monkeypatch):
    monkeypatch.setattr(pdf, "PDF_ENABLED", False)
    monkeypatch.setattr(pdf, "_DISPONIBLE", None)
    assert pdf.available() is False


def test_los_flags_de_chromium_son_los_que_evitan_tumbar_la_instancia():
    """Chromium usa 150-300 MB y el plan de Render tiene 512: sin estos flags, generar un
    informe puede llevarse puesta la instancia entera, con el bot adentro."""
    assert "--disable-dev-shm-usage" in pdf._ARGS   # /dev/shm son 64 MB: sin esto crashea
    assert "--no-sandbox" in pdf._ARGS
