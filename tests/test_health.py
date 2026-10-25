

# ── El health check de Render tiene que ser LIVIANO (ERR-182) ────────────────

def test_el_health_de_render_solo_mira_supabase():
    """Render corta a los 5s. El chequeo completo tarda ~3s porque llama a Alegra
    y abre conexión con Anarvet: un pico hacía que Render reiniciara la instancia
    y cortara las conversaciones en curso."""
    from unittest.mock import patch

    from app.health import check_liveness

    with patch("app.health.db.ping") as ping, \
         patch("app.health.alegra.ping") as alegra_ping, \
         patch("app.health.anarvet.ping") as anarvet_ping, \
         patch("app.health.pdf.available") as pdf_disp:
        payload, codigo = check_liveness()

    assert codigo == 200 and payload["status"] == "ok"
    ping.assert_called_once()
    # las lentas NO se tocan: son justamente las que causaban el timeout
    alegra_ping.assert_not_called()
    anarvet_ping.assert_not_called()
    pdf_disp.assert_not_called()


def test_si_supabase_cae_el_health_da_503():
    """503 es el único caso en que reiniciar la instancia sirve de algo."""
    from unittest.mock import patch

    from app.health import check_liveness

    with patch("app.health.db.ping", side_effect=RuntimeError("caida")):
        payload, codigo = check_liveness()
    assert codigo == 503 and payload["status"] == "error"


def test_la_ruta_health_usa_el_liviano_y_detalle_el_completo():
    from unittest.mock import patch

    from app.main import app

    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as sesion:  # /health/detalle exige sesión o token
        sesion["dashboard_authenticated"] = True
    with patch("app.main.check_liveness", return_value=({"status": "ok"}, 200)) as liviano, \
         patch("app.main.check_all", return_value=({"status": "ok"}, 200)) as completo:
        c.get("/health")
        liviano.assert_called_once()
        completo.assert_not_called()
        c.get("/health/detalle")
        completo.assert_called_once()
