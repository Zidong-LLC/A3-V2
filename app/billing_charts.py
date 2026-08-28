"""Serie de facturación para el gráfico del Panel.

Lógica pura sobre el cache de facturas: agrupa por período lo facturado, lo cobrado
y lo que queda por cobrar, y calcula el crecimiento contra el período anterior. Sin
I/O, para poder probarlo sin base.

Se apila cobrado + por cobrar porque juntos SON lo facturado: la altura de la barra
es el período y el color dice cuánto de eso ya entró. Dos medidas en un solo eje,
sin segunda escala.

Por qué hay tres períodos y no solo meses: el cache trae lo que se haya sincronizado
de Alegra, y hoy son doce días. Un gráfico de doce meses con once vacíos no dice
nada. `auto` elige la ventana más grande que tenga al menos dos puntos con datos, así
el mismo widget sirve hoy y cuando haya historial de verdad.
"""
from datetime import date, timedelta

MESES = ("ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic")

PERIODOS = {
    "mes": {"puntos": 12, "titulo": "los ultimos 12 meses"},
    "semana": {"puntos": 12, "titulo": "las ultimas 12 semanas"},
    "dia": {"puntos": 14, "titulo": "los ultimos 14 dias"},
}


def _entero(valor) -> int:
    try:
        return int(round(float(valor or 0)))
    except (TypeError, ValueError):
        return 0


def _fecha(factura: dict) -> date | None:
    texto = str(factura.get("invoice_date") or "")[:10]
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def _clave(dia: date, periodo: str) -> str:
    if periodo == "mes":
        return f"{dia.year:04d}-{dia.month:02d}"
    if periodo == "semana":
        lunes = dia - timedelta(days=dia.weekday())
        return lunes.isoformat()
    return dia.isoformat()


def _etiqueta(clave: str, periodo: str) -> tuple[str, str]:
    """Texto corto del eje y el detalle que va en el tooltip y la tabla."""
    if periodo == "mes":
        anio, mes = clave.split("-")
        return MESES[int(mes) - 1], anio
    dia = date.fromisoformat(clave)
    if periodo == "semana":
        return f"{dia.day}/{dia.month}", f"semana del {dia.day}/{dia.month}/{dia.year}"
    return f"{dia.day}/{dia.month}", f"{dia.day}/{dia.month}/{dia.year}"


def _claves_hacia_atras(hasta: date, cantidad: int, periodo: str) -> list[str]:
    """Claves del período más viejo al más nuevo, incluyendo el de `hasta`."""
    if periodo == "mes":
        claves, anio, mes = [], hasta.year, hasta.month
        for _ in range(cantidad):
            claves.append(f"{anio:04d}-{mes:02d}")
            mes -= 1
            if mes == 0:
                anio, mes = anio - 1, 12
        return list(reversed(claves))
    paso = timedelta(days=7 if periodo == "semana" else 1)
    inicio = hasta - timedelta(days=hasta.weekday()) if periodo == "semana" else hasta
    return [(inicio - paso * i).isoformat() for i in range(cantidad)][::-1]


def series(invoices: list[dict], periodo: str = "mes", hoy: date | None = None) -> list[dict]:
    """Un punto por período, del más viejo al más nuevo. Los períodos sin facturas
    van en cero: un hueco en la serie mentiría sobre el ritmo del negocio."""
    hoy = hoy or date.today()
    cantidad = PERIODOS.get(periodo, PERIODOS["mes"])["puntos"]
    claves = _claves_hacia_atras(hoy, cantidad, periodo)
    puntos = {c: {"clave": c, "facturado": 0, "cobrado": 0, "por_cobrar": 0, "facturas": 0}
              for c in claves}

    for factura in invoices:
        dia = _fecha(factura)
        punto = puntos.get(_clave(dia, periodo)) if dia else None
        if punto is None:
            continue
        total = _entero(factura.get("total"))
        saldo = min(_entero(factura.get("balance")), total)
        punto["facturado"] += total
        punto["por_cobrar"] += saldo
        punto["cobrado"] += total - saldo
        punto["facturas"] += 1

    salida = []
    for clave in claves:
        punto = puntos[clave]
        punto["etiqueta"], punto["detalle"] = _etiqueta(clave, periodo)
        salida.append(punto)
    return salida


def monthly_series(invoices: list[dict], months: int = 12, hoy: date | None = None) -> list[dict]:
    """Compatibilidad: la serie mensual de siempre."""
    return series(invoices, periodo="mes", hoy=hoy)


def elegir_periodo(invoices: list[dict], hoy: date | None = None) -> str:
    """La ventana más grande que tenga al menos dos puntos con facturas."""
    for periodo in ("mes", "semana", "dia"):
        con_datos = [p for p in series(invoices, periodo, hoy) if p["facturas"]]
        if len(con_datos) >= 2:
            return periodo
    return "dia"


def growth(serie: list[dict]) -> dict:
    """Cuánto cambió el último período contra el anterior. `pct` es None cuando el
    anterior fue cero: ahí no hay porcentaje que calcular, solo un arranque."""
    if len(serie) < 2:
        return {"actual": 0, "anterior": 0, "diferencia": 0, "pct": None}
    actual, anterior = serie[-1]["facturado"], serie[-2]["facturado"]
    diferencia = actual - anterior
    return {"actual": actual, "anterior": anterior, "diferencia": diferencia,
            "pct": round(diferencia / anterior * 100, 1) if anterior else None}


def chart_data(invoices: list[dict], periodo: str = "auto", hoy: date | None = None) -> dict:
    """Todo lo que la plantilla necesita para dibujar, ya calculado acá: alturas en
    porcentaje del máximo, para que el HTML no haga cuentas."""
    if periodo not in PERIODOS:
        periodo = elegir_periodo(invoices, hoy)
    serie = series(invoices, periodo, hoy)
    tope = max((p["facturado"] for p in serie), default=0)
    for punto in serie:
        punto["cobrado_pct"] = round(punto["cobrado"] / tope * 100, 2) if tope else 0
        punto["por_cobrar_pct"] = round(punto["por_cobrar"] / tope * 100, 2) if tope else 0
    return {
        "serie": serie,
        "tope": tope,
        "periodo": periodo,
        "titulo": PERIODOS[periodo]["titulo"],
        "unidad": {"mes": "mes", "semana": "semana", "dia": "dia"}[periodo],
        "crecimiento": growth(serie),
        # El último punto es el período EN CURSO: comparar un mes a medias contra uno
        # completo hace ver una caída que no existe, así que la vista lo dice.
        "ultimo_en_curso": True,
        "total_facturado": sum(p["facturado"] for p in serie),
        "total_cobrado": sum(p["cobrado"] for p in serie),
        "total_por_cobrar": sum(p["por_cobrar"] for p in serie),
    }
