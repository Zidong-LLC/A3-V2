"""Utilidades de medición compartidas por los estrés (bot y web): percentiles, muestreo
de hilos y de /health en segundo plano, y la tabla del informe."""
import threading
import time
import urllib.request


def pct(valores, p: float) -> float:
    """Percentil por rango más cercano; 0 si no hay datos."""
    v = sorted(valores)
    if not v:
        return 0.0
    return v[min(len(v) - 1, max(0, int(round(p / 100 * len(v) + 0.5)) - 1))]


def resumen_ms(valores) -> str:
    if not valores:
        return "sin datos"
    return (f"p50 {pct(valores, 50) / 1000:.2f}s · p95 {pct(valores, 95) / 1000:.2f}s · "
            f"máx {max(valores) / 1000:.2f}s (n={len(valores)})")


class Muestreador:
    """Mientras corre la carga: cada `cada` s mide los hilos vivos del proceso y, si se
    le da una URL, cuánto tarda /health — el que mira Render para decidir un reinicio."""

    def __init__(self, url_salud: str | None = None, cada: float = 1.0, corte: float = 30.0):
        self.url, self.cada, self.corte = url_salud, cada, corte
        self.hilos: list[int] = []
        self.salud: list[tuple[float, int]] = []  # (ms, status) — status 0 = no respondió
        self._fin = threading.Event()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)

    def __enter__(self):
        self._hilo.start()
        return self

    def __exit__(self, *exc):
        self._fin.set()
        self._hilo.join(timeout=self.corte + 5)

    def _bucle(self):
        while not self._fin.is_set():
            self.hilos.append(threading.active_count())
            if self.url:
                inicio = time.monotonic()
                try:
                    with urllib.request.urlopen(self.url, timeout=self.corte) as r:
                        status = r.status
                except Exception as exc:  # noqa: BLE001 — se mide, no se interrumpe
                    status = getattr(exc, "code", 0)
                self.salud.append(((time.monotonic() - inicio) * 1000, status))
            self._fin.wait(self.cada)

    def informe(self, umbral_s: float = 5.0) -> list[str]:
        lineas = [f"hilos vivos: máx {max(self.hilos, default=0)}"]
        if self.url:
            ms = [m for m, _ in self.salud]
            lentos = sum(1 for m, s in self.salud if m > umbral_s * 1000 or s != 200)
            lineas.append(f"/health: {resumen_ms(ms)} · {lentos} sondeo(s) > {umbral_s:.0f}s o con error")
        return lineas
