"""Avisos de error al Telegram del responsable (pedido del usuario para el lanzamiento).

Lo que estos tests protegen: que el avisador NUNCA rompa lo que estaba pasando, que no
spamee cuando un error entra en bucle, y que no se active sin configurar.
"""
from unittest.mock import patch

import app.alerts as alerts


def _limpiar():
    alerts._estado.clear()


def test_sin_chat_configurado_no_avisa():
    _limpiar()
    with patch("app.config.ADMIN_TELEGRAM_CHAT_ID", ""), \
         patch("app.services.telegram.send_message") as enviar:
        assert alerts.notify_error("prueba", RuntimeError("x")) is False
    enviar.assert_not_called()


def test_avisa_con_el_contexto_y_el_error():
    _limpiar()
    with patch("app.config.ADMIN_TELEGRAM_CHAT_ID", "123"), \
         patch("app.services.telegram.send_message") as enviar:
        assert alerts.notify_error("turno de Telegram", ValueError("se rompió"),
                                   "chat 999") is True
    chat, texto = enviar.call_args.args
    assert chat == "123"
    assert "turno de Telegram" in texto
    assert "ValueError" in texto and "se rompió" in texto
    assert "chat 999" in texto


def test_el_mismo_error_en_bucle_no_spamea():
    """Sin esto, una caída de la base mandaría cientos de mensajes y Telegram cortaría
    el bot — el aviso terminaría causando una falla peor que la que reporta."""
    _limpiar()
    with patch("app.config.ADMIN_TELEGRAM_CHAT_ID", "123"), \
         patch("app.services.telegram.send_message") as enviar:
        salidas = [alerts.notify_error("turno", RuntimeError("misma falla")) for _ in range(50)]
    assert salidas.count(True) == 1
    assert enviar.call_count == 1


def test_errores_distintos_avisan_por_separado():
    _limpiar()
    with patch("app.config.ADMIN_TELEGRAM_CHAT_ID", "123"), \
         patch("app.services.telegram.send_message") as enviar:
        alerts.notify_error("turno", RuntimeError("falla A"))
        alerts.notify_error("turno", RuntimeError("falla B"))
        alerts.notify_error("web", RuntimeError("falla A"))
    assert enviar.call_count == 3


def test_pasada_la_ventana_vuelve_a_avisar_e_informa_las_repeticiones():
    _limpiar()
    with patch("app.config.ADMIN_TELEGRAM_CHAT_ID", "123"), \
         patch("app.services.telegram.send_message") as enviar:
        alerts.notify_error("turno", RuntimeError("falla"))
        for _ in range(4):
            alerts.notify_error("turno", RuntimeError("falla"))      # silenciadas
        # el reloj avanza más que la ventana
        alerts._estado[next(iter(alerts._estado))]["ultimo"] -= alerts.VENTANA_SEGUNDOS + 1
        alerts.notify_error("turno", RuntimeError("falla"))
    assert enviar.call_count == 2
    assert "se repitió 4" in enviar.call_args.args[1]


def test_si_telegram_falla_el_avisador_no_explota():
    _limpiar()
    with patch("app.config.ADMIN_TELEGRAM_CHAT_ID", "123"), \
         patch("app.services.telegram.send_message", side_effect=RuntimeError("red caída")):
        assert alerts.notify_error("turno", ValueError("x")) is False


def test_el_dict_de_firmas_no_crece_para_siempre():
    _limpiar()
    with patch("app.config.ADMIN_TELEGRAM_CHAT_ID", "123"), \
         patch("app.services.telegram.send_message"):
        for i in range(alerts._MAX_FIRMAS + 20):
            alerts.notify_error("turno", RuntimeError(f"falla {i}"))
    assert len(alerts._estado) <= alerts._MAX_FIRMAS + 1
