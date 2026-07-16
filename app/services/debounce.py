"""Buffer de ráfagas de mensajes (debounce) — capa de transporte.

Las personas reales escriben en RÁFAGAS: "Si como no" / "La veterinaria es" / "Animal PET"
(3 mensajes en 6 segundos, chat real 2026-07-16). Procesar cada fragmento por separado
descarrila el flujo: el bot buscó "Si como no" como nombre de veterinaria.

Patrón: al llegar un mensaje se espera `window_seconds`; si llegan más, se acumulan y la
espera se reinicia. Cuando la ráfaga para, TODOS los fragmentos se procesan como UN solo
mensaje (unidos con salto de línea) y se responde una sola vez. `max_wait_seconds` es el
tope duro: una ráfaga interminable se procesa igual al alcanzarlo.

Con `window_seconds <= 0` el debounce queda APAGADO y el flush es síncrono e inmediato
(modo de los tests). Estado en memoria del proceso: válido para el despliegue actual
(un solo proceso Flask); si se escala a varios workers, mover el buffer a Supabase/Redis.
"""
import threading
import time


class MessageDebouncer:
    def __init__(self, window_seconds: float = 5.0, max_wait_seconds: float = 20.0):
        self.window = float(window_seconds)
        self.max_wait = float(max_wait_seconds)
        self._lock = threading.Lock()
        self._buffers: dict[str, dict] = {}  # key -> {texts, first_ts, generation, flush}

    def submit(self, key: str, text: str, flush) -> None:
        """Encola `text` para `key` (chat). `flush(combined_text)` se invoca UNA vez por
        ráfaga, con todos los fragmentos unidos. Con window<=0 se invoca ya mismo."""
        if self.window <= 0:
            flush(text)
            return

        with self._lock:
            buf = self._buffers.get(key)
            if buf is None:
                buf = {"texts": [], "first_ts": time.monotonic(), "generation": 0, "flush": flush}
                self._buffers[key] = buf
            buf["texts"].append(text)
            buf["flush"] = flush
            buf["generation"] += 1
            generation = buf["generation"]

            # Tope duro: la ráfaga lleva demasiado — se procesa ya, incluyendo este mensaje.
            if time.monotonic() - buf["first_ts"] >= self.max_wait:
                combined, flush_fn = self._drain(key)
            else:
                combined = None
                timer = threading.Timer(self.window, self._on_timer, args=(key, generation))
                timer.daemon = True
                timer.start()
        if combined is not None:
            self._safe_flush(flush_fn, combined)

    def _on_timer(self, key: str, generation: int) -> None:
        with self._lock:
            buf = self._buffers.get(key)
            # Llegó otro mensaje después de programar este timer: hay un timer más nuevo.
            if buf is None or buf["generation"] != generation:
                return
            combined, flush_fn = self._drain(key)
        self._safe_flush(flush_fn, combined)

    def _drain(self, key: str):
        buf = self._buffers.pop(key)
        return "\n".join(buf["texts"]), buf["flush"]

    @staticmethod
    def _safe_flush(flush, combined: str) -> None:
        try:
            flush(combined)
        except Exception:  # noqa: BLE001 — el buffer jamás debe tumbar el webhook
            import logging
            logging.getLogger(__name__).error("debounce: fallo procesando ráfaga", exc_info=True)
