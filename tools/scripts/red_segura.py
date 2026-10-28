"""Red de seguridad de RED para las pruebas que corren contra la base real.

Los arneses de QA simulan las escrituras parcheando funciones de `app.services.db`, pero
cada función nueva que no esté en la lista se escapa a producción sin que nadie lo note:
pasó con el barrido de pedidos abandonados (cierra pedidos reales y avisa a clientes
reales) y con la factura de `validate_flows` (con ALEGRA_ENABLED=true iba a la cuenta
REAL de Alegra). Esta red corta el problema un nivel más abajo, en el transporte:

- Supabase: solo lecturas (GET/HEAD) y la firma de URLs de Storage. Toda escritura falla.
- OpenAI: solo si se pide (`permitir_openai=True`), y solo chat/completions.
- Todo lo demás (Telegram, Chatwoot, WhatsApp, Alegra, Anarvet, alertas): bloqueado.

Lo bloqueado lanza un error de red del mismo tipo que la librería original (el código lo
trata como una caída) y queda anotado en `bloqueos`. Como la app atrapa muchos errores
de red a propósito, el arnés DEBE mirar `bloqueos` al final: si no está vacío, algo
intentó salir. `activar()` va ANTES de importar la app.
"""
import atexit
import os
import threading
import traceback
import urllib.error
import urllib.request
from urllib.parse import urlsplit

bloqueos: list[dict] = []
RPC_DE_LECTURA = {"anarvet_informes_por_cliente"}  # migración 037: solo cuenta
_lock = threading.Lock()
_estado = {"activa": False, "openai": False, "silenciosa": False}


def _host_supabase() -> str:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    return urlsplit(os.environ.get("SUPABASE_URL", "")).hostname or ""


def _permitido(metodo: str, url: str) -> bool:
    partes = urlsplit(url)
    host, ruta = partes.hostname or "", partes.path or ""
    if host in ("127.0.0.1", "localhost"):
        return True  # el servidor local que levanta el propio arnés
    if host and host == _estado["supabase"]:
        if metodo in ("GET", "HEAD"):
            return True
        # Firmar una URL de descarga no modifica nada en el bucket; las funciones de la
        # lista solo leen (se llaman por POST porque así es /rpc en PostgREST).
        return metodo == "POST" and (ruta.startswith("/storage/v1/object/sign/")
                                     or ruta.removeprefix("/rest/v1/rpc/") in RPC_DE_LECTURA)
    if host == "api.openai.com" and _estado["openai"]:
        return metodo == "POST" and ruta.endswith("/chat/completions")
    return False


def _anotar(metodo: str, url: str, via: str) -> None:
    partes = urlsplit(url)
    # El origen es la primera línea de la app en la pila: dice QUIÉN intentó salir.
    origen = next((f"{f.filename.split('A3 V2')[-1]}:{f.lineno} {f.name}"
                   for f in reversed(traceback.extract_stack())
                   if os.sep + "app" + os.sep in f.filename), "?")
    with _lock:
        bloqueos.append({"metodo": metodo, "host": partes.hostname, "ruta": partes.path[:80],
                         "via": via, "origen": origen})


def _guardia_httpx():
    import httpx

    original = httpx.Client.send

    def send(self, request, *args, **kwargs):
        metodo, url = request.method.upper(), str(request.url)
        if not _permitido(metodo, url):
            _anotar(metodo, url, "httpx")
            raise httpx.ConnectError(f"red_segura: bloqueado {metodo} {urlsplit(url).hostname}",
                                     request=request)
        return original(self, request, *args, **kwargs)

    httpx.Client.send = send


def _guardia_urllib():
    original = urllib.request.OpenerDirector.open

    def open_(self, fullurl, data=None, *args, **kwargs):
        if isinstance(fullurl, urllib.request.Request):
            url, metodo = fullurl.full_url, fullurl.get_method()
        else:
            url, metodo = str(fullurl), "POST" if data is not None else "GET"
        if not _permitido(metodo.upper(), url):
            _anotar(metodo.upper(), url, "urllib")
            raise urllib.error.URLError(f"red_segura: bloqueado {metodo} {urlsplit(url).hostname}")
        return original(self, fullurl, data, *args, **kwargs)

    urllib.request.OpenerDirector.open = open_


def _guardia_requests():
    try:
        import requests
    except ImportError:
        return
    original = requests.Session.send

    def send(self, request, **kwargs):
        if not _permitido(request.method.upper(), request.url):
            _anotar(request.method.upper(), request.url, "requests")
            raise requests.ConnectionError(f"red_segura: bloqueado {request.method} {urlsplit(request.url).hostname}")
        return original(self, request, **kwargs)

    requests.Session.send = send


def _guardia_psycopg():
    try:
        import psycopg
    except ImportError:
        return

    def connect(*args, **kwargs):
        _anotar("CONNECT", f"postgresql://{kwargs.get('host', 'anarvet')}/", "psycopg")
        raise psycopg.OperationalError("red_segura: conexión a Anarvet bloqueada")

    psycopg.connect = connect


def activar(permitir_openai: bool = False, silenciosa: bool = False) -> None:
    """Enciende la red. Idempotente. `silenciosa` no imprime el resumen al salir."""
    if _estado["activa"]:
        return
    _estado.update(activa=True, openai=permitir_openai, silenciosa=silenciosa, supabase=_host_supabase())
    if not _estado["supabase"]:
        raise SystemExit("red_segura: falta SUPABASE_URL; no se puede saber qué lecturas permitir")
    # Los avisos de error irían al Telegram de reportes: se apagan además de bloquearse.
    os.environ["ADMIN_TELEGRAM_CHAT_ID"] = ""
    os.environ["ALERT_TELEGRAM_BOT_TOKEN"] = ""
    _guardia_httpx()
    _guardia_urllib()
    _guardia_requests()
    _guardia_psycopg()
    atexit.register(resumen)


def resumen() -> str:
    """Texto con lo bloqueado, agrupado por origen. Vacío = nada intentó salir."""
    if not bloqueos:
        texto = "red_segura: 0 intentos bloqueados — nada salió de la máquina."
    else:
        grupos: dict[str, int] = {}
        for b in bloqueos:
            clave = f"{b['metodo']} {b['host']}{b['ruta']} <- {b['origen']}"
            grupos[clave] = grupos.get(clave, 0) + 1
        texto = f"red_segura: {len(bloqueos)} intento(s) BLOQUEADO(S):\n" + "\n".join(
            f"  {n:>4} × {k}" for k, n in sorted(grupos.items(), key=lambda x: -x[1]))
    if not _estado["silenciosa"]:
        print("\n" + texto)
    return texto
