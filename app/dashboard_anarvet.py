"""Vista del espejo Anarvet en el dashboard del personal (decisión 013).

Lista los informes sincronizados (un informe = un paciente en una fecha) y muestra
el detalle de cada uno con sus analitos agrupados por examen, como el documento
del resultado. Blueprint separado (misma razón que dashboard_results): usa la MISMA
sesión del dashboard y no toca app/dashboard.py. Solo LECTURA del espejo local:
nunca le pega a Anarvet — para traer datos nuevos está el botón de sync.
"""
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from app import anarvet_map
from app.config import ANARVET_ENABLED, APP_TIMEZONE
from app.services import db

dashboard_anarvet = Blueprint("dashboard_anarvet", __name__)

PER_PAGE = 50


def _login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("dashboard_authenticated"):
            return redirect(url_for("dashboard.login"))
        if not ANARVET_ENABLED:
            abort(404)  # con el flag apagado la sección no existe
        return view_func(*args, **kwargs)

    return wrapped


def _filters() -> dict:
    hoy = datetime.now(APP_TIMEZONE).date()
    return {
        "search": (request.args.get("search") or "").strip(),
        "cod_cliente": (request.args.get("cod_cliente") or "").strip(),
        "date_from": (request.args.get("date_from") or "").strip() or str(hoy - timedelta(days=7)),
        "date_to": (request.args.get("date_to") or "").strip(),
    }


@dashboard_anarvet.get("/resultados/anarvet")
@_login_required
def informes_page():
    filters = _filters()
    try:
        page = max(int(request.args.get("page", "1")), 1)
    except ValueError:
        page = 1
    informes, total = db.list_anarvet_informes(filters, page=page, per_page=PER_PAGE)
    pages = max((total + PER_PAGE - 1) // PER_PAGE, 1)
    return render_template(
        "dashboard_anarvet.html",
        informes=informes, filters=filters, total=total, page=page, pages=pages,
        username=session.get("dashboard_username", ""),
    )


@dashboard_anarvet.get("/resultados/anarvet/clientes")
@_login_required
def clientes_page():
    """Emparejar los códigos de cliente de Anarvet con nuestras veterinarias.

    Sin este vínculo un informe no tiene dueño: no se puede publicar en el portal ni contar
    como de nadie. Los endpoints de asignación ya existían (`/api/dashboard/anarvet/clients*`)
    pero ningún template los usaba, así que la única vía era un script.
    """
    mapa = db.list_anarvet_client_map()
    clientes = [c for c in db.list_clients_with_assignment()
                if c.get("is_active") and (c.get("clinic_name") or "").strip()]
    informes_por_cod = db.count_anarvet_informes_por_cliente()

    pendientes = [m for m in mapa if not m.get("client_id")]
    plan = anarvet_map.planificar(pendientes, clientes)

    def _fila(entrada, candidatos):
        p = entrada["pendiente"]
        cod = str(p.get("cod_cliente") or "")
        return {
            "cod_cliente": cod,
            "nombre_cliente": p.get("nombre_cliente"),
            "informes": informes_por_cod.get(cod, 0),
            "candidatos": candidatos,
        }

    # Los que necesitan una decisión humana, con los más pesados primero: resolver el de
    # 65 informes cambia más que el de 1.
    por_resolver = [
        _fila(a, [{"cliente": c, "similitud": 1.0} for c in a["candidatos"]])
        for a in plan["ambiguos"]
    ] + [
        _fila(s, anarvet_map.sugerencias(s["pendiente"].get("nombre_cliente"), clientes))
        for s in plan["sin_candidato"]
    ]
    por_resolver.sort(key=lambda f: -f["informes"])

    asignados = sorted(
        ({**m, "informes": informes_por_cod.get(str(m.get("cod_cliente") or ""), 0)}
         for m in mapa if m.get("client_id")),
        key=lambda m: -m["informes"],
    )
    nombres_clientes = {str(c["id"]): c["clinic_name"] for c in clientes}

    return render_template(
        "dashboard_anarvet_clientes.html",
        por_resolver=por_resolver,
        asignados=asignados,
        clientes=clientes,
        nombres_clientes=nombres_clientes,
        automaticos_disponibles=len(plan["automaticos"]),
        total_informes=sum(informes_por_cod.values()),
        informes_con_dueno=sum(
            n for cod, n in informes_por_cod.items()
            if cod in {str(m.get("cod_cliente")) for m in mapa if m.get("client_id")}
        ),
        username=session.get("dashboard_username", ""),
    )


@dashboard_anarvet.get("/resultados/anarvet/<codigo>/<fecha>")
@_login_required
def informe_detalle(codigo: str, fecha: str):
    analitos = db.get_anarvet_informe(codigo, fecha)
    if not analitos:
        abort(404)
    # Agrupar por examen respetando el orden de la consulta (dict conserva inserción).
    examenes: dict[str, list[dict]] = {}
    for fila in analitos:
        examenes.setdefault(fila.get("examen_cod") or "—", []).append(fila)
    return render_template(
        "dashboard_anarvet_detalle.html",
        paciente=analitos[0], examenes=examenes, total_analitos=len(analitos),
        username=session.get("dashboard_username", ""),
    )


# ── Informe imprimible ───────────────────────────────────────────────────────────
# A3 lo pidió en la llamada del 21/08: que el personal pueda descargar el resultado y
# reenviárselo al cliente que llama y no tiene acceso al portal. Anarvet no entrega PDF
# (decisión 013), así que el documento lo componemos nosotros con los datos del espejo.

# Nombres legibles de los exámenes. Anarvet solo entrega el código corto ('H4', 'PROT');
# esto cubre los más frecuentes y cualquier otro se muestra con su código, sin inventar.
_EXAM_NAMES = {
    "H4": "Cuadro hemático", "H3": "Hemograma", "PROT": "Proteínas totales",
    "ALB": "Albúmina", "ALT": "ALT (GPT)", "AST": "AST (GOT)", "BUN": "Nitrógeno ureico (BUN)",
    "CRE": "Creatinina", "URE": "Urea", "FOSAL": "Fosfatasa alcalina", "GLU": "Glucosa",
    "COL": "Colesterol", "TRI": "Triglicéridos", "GGT": "GGT", "AMI": "Amilasa",
    "LIP": "Lipasa", "CA": "Calcio", "FOS": "Fósforo", "MG": "Magnesio", "NA": "Sodio",
    "K": "Potasio", "CL": "Cloro", "BT": "Bilirrubina total", "PU": "Parcial de orina",
    "COP": "Coprológico", "HEM": "Hemoparásitos", "T4": "T4", "TSH": "TSH",
}

# El reporte mezcla el comentario del profesional entre los analitos, como una fila más.
# En el documento va aparte: no es un valor medido.
_OBSERVATION_KEYS = ("observacion", "observaciones", "comentario", "comentarios", "nota")

_GENDERS = {"M": "Macho", "H": "Hembra", "F": "Hembra"}


def _es_observacion(fila: dict) -> bool:
    return (fila.get("analito") or "").strip().lower() in _OBSERVATION_KEYS


def _contexto(analito: str | None, examen: str) -> str:
    """Nombre del examen, solo cuando agrega algo al del analito.

    'BUN · Nitrógeno ureico (BUN)' y 'ALT · ALT (GPT)' repiten lo mismo dos veces: si uno
    de los dos nombres ya contiene al otro, con uno alcanza."""
    a = (analito or "").strip().lower()
    e = (examen or "").strip().lower()
    if not a or not e or a in e or e in a:
        return ""
    return examen


def _edad(nacio, referencia) -> str:
    """Edad al momento de la solicitud, en años y meses. Sin fecha de nacimiento, vacío."""
    if not nacio or not referencia:
        return ""
    try:
        n = date.fromisoformat(str(nacio)[:10])
        r = date.fromisoformat(str(referencia)[:10])
    except ValueError:
        return ""
    meses = (r.year - n.year) * 12 + (r.month - n.month) - (1 if r.day < n.day else 0)
    if meses < 0:
        return ""
    años, resto = divmod(meses, 12)
    if años and resto:
        return f"{años} {'año' if años == 1 else 'años'} y {resto} {'mes' if resto == 1 else 'meses'}"
    if años:
        return f"{años} {'año' if años == 1 else 'años'}"
    return f"{resto} {'mes' if resto == 1 else 'meses'}"


@dashboard_anarvet.get("/resultados/anarvet/<codigo>/<fecha>/imprimir")
@_login_required
def informe_imprimir(codigo: str, fecha: str):
    analitos = db.get_anarvet_informe(codigo, fecha)
    if not analitos:
        abort(404)

    examenes, observaciones = [], []
    por_codigo: dict[str, list[dict]] = {}
    for fila in analitos:
        if _es_observacion(fila):
            texto = (fila.get("resultado") or "").strip()
            if texto:
                observaciones.append(texto)
            continue
        por_codigo.setdefault(fila.get("examen_cod") or "—", []).append(fila)
    # Un examen de UN solo analito (creatinina, BUN, ALT…) no merece su propio bloque con
    # título y encabezados: gastaba 19,5 mm de hoja para mostrar un número, y cinco de esos
    # empujaban el informe a una segunda página casi vacía. Van juntos en un bloque final,
    # una línea cada uno — que es como se leen en un informe de laboratorio.
    sueltos = []
    for cod, filas in por_codigo.items():
        nombre = _EXAM_NAMES.get(cod.upper(), cod)
        if len(filas) == 1:
            sueltos.append({"codigo": cod, "fila": filas[0],
                            "medido": filas[0].get("analito") or nombre,
                            "contexto": _contexto(filas[0].get("analito"), nombre)})
        else:
            examenes.append({"codigo": cod, "nombre": nombre, "filas": filas})

    p = analitos[0]
    validaciones = [f.get("fec_val") for f in analitos if f.get("fec_val")]
    validadores = [f.get("usu_validador") for f in analitos if f.get("usu_validador")]
    paciente = {
        "codigo": codigo,
        "fecha_solicitud": fecha,
        "mascota": p.get("mascota"),
        "especie": p.get("especie"),
        "raza": p.get("raza"),
        "genero": _GENDERS.get((p.get("genero") or "").strip().upper(), p.get("genero") or ""),
        "edad": _edad(p.get("nacio"), fecha),
        "propietario": p.get("nombre_propietario"),
        "cliente": p.get("nombre_cliente"),
        "validado_el": max(validaciones) if validaciones else None,
        "validado_por": validadores[0] if validadores else None,
    }
    return render_template(
        "anarvet_informe_print.html",
        paciente=paciente, examenes=examenes, sueltos=sueltos,
        observaciones=observaciones,
        total_analitos=sum(len(e["filas"]) for e in examenes) + len(sueltos),
        total_examenes=len(examenes) + len(sueltos),
    )
