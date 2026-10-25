"""Plataforma A3 local en modo SOLO LECTURA, para grabar demostraciones.

Lee los datos reales de Supabase, pero anula toda escritura: insert/update/upsert/delete
del cliente de Supabase, subidas a storage, avisos por Telegram/Chatwoot y llamadas de
escritura a Alegra. Las recogidas de ejemplo de la Agenda (prefijo DEMO-) viven solo en
memoria, para mostrar la reasignación sin tocar la base.
"""
import sys
import threading
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PUERTO = 5055
_PREFIJOS_ESCRITURA = ("create", "update", "delete", "remove", "upload", "send", "void",
                       "stamp", "publish", "unpublish", "mark", "insert", "upsert", "post")


class _SinEscritura:
    """Reemplaza un builder de escritura: cualquier cadena termina en data=[]."""
    data: list = []
    count = 0

    def __getattr__(self, _name):
        return lambda *args, **kwargs: self

    def execute(self):
        return self


def _anular_modulo(modulo) -> None:
    for nombre, valor in list(vars(modulo).items()):
        es_lectura = "signed" in nombre or "url" in nombre
        if callable(valor) and nombre.lower().startswith(_PREFIJOS_ESCRITURA) and not es_lectura:
            setattr(modulo, nombre, lambda *args, **kwargs: None)


def _bloquear_escrituras() -> None:
    from postgrest import SyncRequestBuilder
    for metodo in ("insert", "update", "upsert", "delete"):
        setattr(SyncRequestBuilder, metodo, lambda self, *a, **k: _SinEscritura())
    from app.services import alegra, chatwoot, storage, telegram
    for modulo in (alegra, chatwoot, storage, telegram):
        _anular_modulo(modulo)
    import app.alerts as alertas
    import app.courier_notify as courier_notify
    import app.dashboard as dashboard_module
    # Un error de la demo no es un error de producción: no va al Telegram de reportes.
    alertas._enviar = lambda *args, **kwargs: None
    _anular_modulo(courier_notify)
    dashboard_module.notify_assignment = lambda *args, **kwargs: None


_PREFIJOS_LECTURA = ("list_", "get_", "fetch_", "find_", "count_", "cartera", "max_", "search_",
                     "clientes_del_cache")


def _cachear_lecturas() -> None:
    """Memoriza las lecturas: tras una pasada de precarga, las pantallas cargan al instante
    y el video no muestra esperas en blanco. Devuelve copias para que nadie mute la caché."""
    import copy
    import functools
    from app.services import db, portal_db
    for modulo in (db, portal_db):
        for nombre, funcion in list(vars(modulo).items()):
            if not (callable(funcion) and nombre.startswith(_PREFIJOS_LECTURA)) or nombre == "get_or_create_session":
                continue
            cache: dict = {}

            @functools.wraps(funcion)
            def leer(*args, _f=funcion, _c=cache, **kwargs):
                clave = repr((args, sorted(kwargs.items())))
                if clave not in _c:
                    _c[clave] = _f(*args, **kwargs)
                return copy.deepcopy(_c[clave])

            setattr(modulo, nombre, leer)


def _recogidas_demo(couriers: list[dict]) -> list[dict]:
    hoy = date.today()
    base = couriers[0] if couriers else None
    filas = []
    ejemplos = [("Veterinaria Ejemplo Norte", "Calle 140 # 15-20, Bogotá", "Max", "Perfil prequirúrgico"),
                ("Clínica Ejemplo Suba", "Av. Suba # 110-30, Bogotá", "Luna", "Hemograma"),
                ("Veterinaria Ejemplo Usaquén", "Calle 119 # 6-15, Bogotá", "Toby", "Perfil renal")]
    for i, (clinica, direccion, paciente, examen) in enumerate(ejemplos, start=1):
        filas.append({
            "id": f"dddddddd-dddd-dddd-dddd-00000000000{i}", "order_number": f"DEMO-00{i}",
            "status": "received", "priority": "normal", "pickup_address": direccion,
            "patient_name": paciente, "exam_type": examen,
            "scheduled_pickup_date": (hoy + timedelta(days=1 if hoy.weekday() < 4 else 0)).isoformat(),
            "assigned_courier_id": base["id"] if base else None,
            "client_id": f"cccccccc-cccc-cccc-cccc-00000000000{i}",
            "clients": {"clinic_name": clinica, "phone": "300 000 0000"},
            "couriers": base,
        })
    return filas


def _instalar_agenda_demo() -> None:
    from app.services import db
    couriers = db.list_active_couriers()
    demo = {fila["id"]: fila for fila in _recogidas_demo(couriers)}
    leer_real = db.list_pickups_between
    leer_pedido = db.get_request_with_client

    def list_pickups_between(start, end, limit=1000):
        extras = [f for f in demo.values() if start <= f["scheduled_pickup_date"] <= end]
        return list(leer_real(start, end, limit)) + extras

    def get_request_with_client(request_id):
        return demo.get(request_id) or leer_pedido(request_id)

    def update_request(request_id, payload):
        fila = demo.get(request_id)
        if not fila:
            return False
        fila.update(payload)
        fila["couriers"] = next((c for c in couriers if c["id"] == fila.get("assigned_courier_id")), None)
        return True

    db.list_pickups_between = list_pickups_between
    db.get_request_with_client = get_request_with_client
    db.update_request = update_request
    db.create_request_event = lambda *args, **kwargs: None


def preparar_app():
    from flask import request, session
    from app.main import app
    _bloquear_escrituras()
    _cachear_lecturas()
    _instalar_agenda_demo()

    @app.before_request
    def _sesion_demo():
        # El login del personal se muestra, pero no se escribe la contraseña en el video.
        if not request.path.startswith(("/portal", "/login", "/static")):
            session["dashboard_authenticated"] = True
            session["dashboard_username"] = "admin"

    return app


def levantar_servidor(app) -> threading.Thread:
    from werkzeug.serving import make_server
    servidor = make_server("127.0.0.1", PUERTO, app, threaded=True)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    return hilo
