"""Avisos de error al Telegram del responsable (pedido del usuario para el lanzamiento).

Van por un bot PROPIO (@A3newsbot), no por el de los clientes: los mensajes del admin
nunca se mezclan con las conversaciones de las veterinarias en Chatwoot.

Lo que estos tests protegen: que el avisador NUNCA rompa lo que estaba pasando, que no
spamee cuando un error entra en bucle, y que no se active sin configurar.
"""
from unittest.mock import patch

import app.alerts as alerts

CONFIGURADO = {"ADMIN_TELEGRAM_CHAT_ID": "123", "ALERT_TELEGRAM_BOT_TOKEN": "tok"}


def _con(**overrides):
    """Contexto con la configuración de avisos puesta (o vacía)."""
    valores = {**CONFIGURADO, **overrides}
    return [patch(f"app.config.{k}", v) for k, v in valores.items()]


def _correr(fn, **overrides):
    """Ejecuta fn(enviar_mock) con la config indicada."""
    parches = _con(**overrides)
    for p in parches:
        p.start()
    alerts._estado.clear()
    try:
        with patch("app.alerts._enviar") as enviar:
            return fn(enviar)
    finally:
        for p in parches:
            p.stop()


def test_sin_chat_configurado_no_avisa():
    def caso(enviar):
        assert alerts.notify_error("prueba", RuntimeError("x")) is False
        enviar.assert_not_called()
    _correr(caso, ADMIN_TELEGRAM_CHAT_ID="")


def test_sin_token_del_bot_de_avisos_tampoco():
    def caso(enviar):
        assert alerts.notify_error("prueba", RuntimeError("x")) is False
        enviar.assert_not_called()
    _correr(caso, ALERT_TELEGRAM_BOT_TOKEN="")


def test_avisa_por_el_bot_de_avisos_con_el_contexto_y_el_error():
    def caso(enviar):
        assert alerts.notify_error("turno de Telegram", ValueError("se rompió"),
                                   "chat 999") is True
        chat, token, texto = enviar.call_args.args
        assert chat == "123"
        assert token == "tok"                      # el bot de avisos, no el de clientes
        assert "turno de Telegram" in texto
        assert "ValueError" in texto and "se rompió" in texto
        assert "chat 999" in texto
    _correr(caso)


def test_el_mismo_error_en_bucle_no_spamea():
    """Sin esto, una caída de la base mandaría cientos de mensajes y Telegram cortaría
    el bot — el aviso terminaría causando una falla peor que la que reporta."""
    def caso(enviar):
        salidas = [alerts.notify_error("turno", RuntimeError("misma falla"))
                   for _ in range(50)]
        assert salidas.count(True) == 1
        assert enviar.call_count == 1
    _correr(caso)


def test_errores_distintos_avisan_por_separado():
    def caso(enviar):
        alerts.notify_error("turno", RuntimeError("falla A"))
        alerts.notify_error("turno", RuntimeError("falla B"))
        alerts.notify_error("web", RuntimeError("falla A"))
        assert enviar.call_count == 3
    _correr(caso)


def test_pasada_la_ventana_vuelve_a_avisar_e_informa_las_repeticiones():
    def caso(enviar):
        alerts.notify_error("turno", RuntimeError("falla"))
        for _ in range(4):
            alerts.notify_error("turno", RuntimeError("falla"))      # silenciadas
        firma = next(iter(alerts._estado))
        alerts._estado[firma]["ultimo"] -= alerts.VENTANA_SEGUNDOS + 1
        alerts.notify_error("turno", RuntimeError("falla"))
        assert enviar.call_count == 2
        assert "se repitió 4" in enviar.call_args.args[2]
    _correr(caso)


def test_si_telegram_falla_el_avisador_no_explota():
    def caso(enviar):
        enviar.side_effect = RuntimeError("red caída")
        assert alerts.notify_error("turno", ValueError("x")) is False
    _correr(caso)


def test_el_dict_de_firmas_no_crece_para_siempre():
    def caso(enviar):
        for i in range(alerts._MAX_FIRMAS + 20):
            alerts.notify_error("turno", RuntimeError(f"falla {i}"))
        assert len(alerts._estado) <= alerts._MAX_FIRMAS + 1
    _correr(caso)
