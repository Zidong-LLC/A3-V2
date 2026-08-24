"""Fix 2026-08-24 (tanda pre-lanzamiento, ítem 1): el "sí, confirmo" ambiguo tras la
oferta del pedido ("¿otra orden... o cerramos el pedido?") caía al vacío — B12 borraba
_pedido_offer_pending y nadie atendía la afirmación pelada (QA2/QA4 del checkpoint).
Ahora la marca sobrevive al reset mientras el pedido siga abierto y el enforcer del
pedido re-pregunta desambiguando, determinístico."""
from tests.test_etapa2_senal_confirmacion import ORDEN_COMPLETA, _run_turn

from app import agent


POST_CIERRE_CON_PEDIDO = dict(
    ORDEN_COMPLETA,
    _order_registered=True,
    _pedido_id="ped-1",
    _pedido_offer_pending=True,
    payment_method=None,
)


def test_affirm_pelado_con_oferta_de_pedido_repregunta():
    """'sí, confirmo' + affirm en fase terminal con la oferta pendiente → re-pregunta
    desambiguando (antes: '¿Cuál es el médico solicitante?' del first-missing)."""
    reply, _ = _run_turn("sí, confirmo", "affirm", POST_CIERRE_CON_PEDIDO,
                         phase="fase_6_cierre")
    assert reply == agent.PEDIDO_OFFER_REASK


def test_affirm_pelado_red_de_tokens_sin_senal():
    """'dale' con señal unclear entra por la red (_is_affirmative_text + bare)."""
    reply, _ = _run_turn("dale", "unclear", POST_CIERRE_CON_PEDIDO,
                         phase="fase_6_cierre")
    assert reply == agent.PEDIDO_OFFER_REASK


def test_otra_orden_sigue_ganando_a_la_oferta():
    """'sí, quiero otra orden para otro paciente' NO es ambiguo: la rama another_order
    gana y arranca la orden de seguimiento como siempre."""
    reply, persisted = _run_turn("sí, quiero otra orden para otro paciente",
                                 "another_order", POST_CIERRE_CON_PEDIDO,
                                 phase="fase_6_cierre")
    assert reply != agent.PEDIDO_OFFER_REASK
    fields = persisted.get("captured_fields", {}) if persisted else {}
    assert not fields.get("patient_name"), "la orden nueva arranca limpia"


def test_pago_en_el_mensaje_cierra_sin_repreguntar():
    """'contraentrega' con la oferta pendiente NO es ambiguo: cierra el pedido
    (el cierre determinístico pre-LLM o el enforcer lo toman)."""
    reply, _ = _run_turn("contraentrega", "unclear", POST_CIERRE_CON_PEDIDO,
                         phase="fase_6_cierre")
    assert reply != agent.PEDIDO_OFFER_REASK
