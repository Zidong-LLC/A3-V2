from unittest.mock import patch


def _client():
    from app.main import app

    app.config["TESTING"] = True
    return app.test_client()


def test_chatwoot_webhook_ignores_empty_non_text_payloads():
    with patch("app.main.process_turn") as mock_process:
        response = _client().post(
            "/chatwoot/webhook",
            json={
                "event": "message_created",
                "message_type": "incoming",
                "content": None,
                "conversation": {"id": 123},
            },
        )

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
    mock_process.assert_not_called()


def test_chatwoot_webhook_replies_and_assigns_handoff_team():
    session = {"requires_handoff": True, "handoff_area": "contabilidad"}

    with patch("app.main.process_turn", return_value="Te comunico con contabilidad") as mock_process, \
         patch("app.main.chatwoot.send_message") as mock_send, \
         patch("app.main.chatwoot.assign_team") as mock_assign, \
         patch("app.main.get_or_create_session", return_value=session):
        response = _client().post(
            "/chatwoot/webhook",
            json={
                "event": "message_created",
                "message_type": "incoming",
                "content": "Necesito pagar una factura",
                "conversation": {"id": 456},
            },
        )

    assert response.status_code == 200
    mock_process.assert_called_once()
    args, kwargs = mock_process.call_args
    assert args == ("456", "Necesito pagar una factura")
    assert "on_progress" in kwargs
    mock_send.assert_called_once_with("456", "Te comunico con contabilidad")
    mock_assign.assert_called_once_with("456", "contabilidad")


def test_chatwoot_webhook_ignores_private_notes():
    with patch("app.main.process_turn") as mock_process:
        response = _client().post(
            "/chatwoot/webhook",
            json={
                "event": "message_created",
                "message_type": "incoming",
                "private": True,
                "content": "Nota interna",
                "conversation": {"id": 789},
            },
        )

    assert response.status_code == 200
    mock_process.assert_not_called()
