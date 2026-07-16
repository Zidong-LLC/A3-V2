"""ERR-065 — Buffer de ráfagas de mensajes (app/services/debounce.py).

Caso real (chat 4, 2026-07-16): "Si como no" / "La veterinaria es" / "Animal PET" en 6
segundos — el bot procesó cada fragmento por separado y buscó "Si como no" como nombre de
veterinaria. Con el buffer, la ráfaga completa se procesa como UN mensaje y una respuesta.
"""
import time

from app.services.debounce import MessageDebouncer


def test_window_zero_is_synchronous_passthrough():
    """Apagado (tests/producción sin buffer): flush inmediato, mensaje a mensaje."""
    got = []
    d = MessageDebouncer(window_seconds=0)
    d.submit("c1", "hola", got.append)
    d.submit("c1", "1", got.append)
    assert got == ["hola", "1"]


def test_burst_is_flushed_once_combined():
    """La ráfaga real: 3 fragmentos → UNA sola llamada con todo el texto unido."""
    got = []
    d = MessageDebouncer(window_seconds=0.15, max_wait_seconds=5)
    d.submit("c1", "Si como no", got.append)
    time.sleep(0.05)
    d.submit("c1", "La veterinaria es", got.append)
    time.sleep(0.05)
    d.submit("c1", "Animal PET", got.append)
    assert got == []                                   # todavía esperando la ráfaga
    time.sleep(0.4)
    assert got == ["Si como no\nLa veterinaria es\nAnimal PET"]


def test_chats_do_not_mix_and_buffer_resets_after_flush():
    got = []
    d = MessageDebouncer(window_seconds=0.1, max_wait_seconds=5)
    d.submit("c1", "a", lambda t: got.append(("c1", t)))
    d.submit("c2", "x", lambda t: got.append(("c2", t)))
    time.sleep(0.3)
    assert sorted(got) == [("c1", "a"), ("c2", "x")]
    # Nueva ráfaga tras el flush: estado limpio.
    d.submit("c1", "b", lambda t: got.append(("c1", t)))
    time.sleep(0.3)
    assert ("c1", "b") in got


def test_max_wait_forces_flush_on_endless_burst():
    """Una ráfaga interminable no pospone la respuesta para siempre: al tope duro se procesa."""
    got = []
    d = MessageDebouncer(window_seconds=0.2, max_wait_seconds=0.35)
    start = time.monotonic()
    while time.monotonic() - start < 0.6 and not got:
        d.submit("c1", "más", got.append)
        time.sleep(0.1)                                # siempre antes de que venza la ventana
    assert got, "el tope duro debió forzar el procesamiento"
    assert "más" in got[0]


def test_flush_error_does_not_break_the_buffer():
    """Un fallo procesando la ráfaga no tumba el buffer ni bloquea ráfagas siguientes."""
    got = []
    d = MessageDebouncer(window_seconds=0.05, max_wait_seconds=5)
    d.submit("c1", "boom", lambda t: 1 / 0)
    time.sleep(0.2)
    d.submit("c1", "hola", got.append)
    time.sleep(0.2)
    assert got == ["hola"]
