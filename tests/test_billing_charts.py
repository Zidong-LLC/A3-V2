"""Serie de facturación del Panel: agrupación por período, crecimiento y alturas."""
from datetime import date

from app import billing_charts as bc

HOY = date(2026, 8, 28)  # viernes


def _f(fecha, total, balance=0):
    return {"invoice_date": fecha, "total": total, "balance": balance}


# ── Agrupación ───────────────────────────────────────────────────────────────

def test_agrupa_por_mes_y_separa_cobrado_de_lo_que_falta():
    serie = bc.series([_f("2026-08-10", 100000, 40000), _f("2026-08-20", 50000, 0)],
                      "mes", HOY)
    agosto = serie[-1]
    assert agosto["facturado"] == 150000
    assert agosto["por_cobrar"] == 40000
    assert agosto["cobrado"] == 110000
    assert agosto["facturas"] == 2


def test_los_periodos_sin_facturas_van_en_cero_y_no_se_saltean():
    serie = bc.series([_f("2026-08-10", 100000)], "mes", HOY)
    assert len(serie) == 12
    assert [p["clave"] for p in serie][-3:] == ["2026-06", "2026-07", "2026-08"]
    assert serie[0]["facturado"] == 0


def test_la_semana_agrupa_de_lunes_a_domingo():
    # 24/8 es lunes: el 24 y el 30 caen en la misma semana.
    serie = bc.series([_f("2026-08-24", 10000), _f("2026-08-30", 5000)], "semana", HOY)
    assert serie[-1]["clave"] == "2026-08-24"
    assert serie[-1]["facturado"] == 15000


def test_una_factura_vieja_no_entra_en_la_ventana():
    serie = bc.series([_f("2024-01-05", 999999)], "mes", HOY)
    assert sum(p["facturado"] for p in serie) == 0


def test_una_fecha_ilegible_no_rompe_la_serie():
    serie = bc.series([{"invoice_date": None, "total": 1}, _f("no es fecha", 2),
                       _f("2026-08-10", 3000)], "mes", HOY)
    assert serie[-1]["facturado"] == 3000


def test_un_saldo_mayor_al_total_no_produce_cobrado_negativo():
    serie = bc.series([_f("2026-08-10", 100000, 150000)], "mes", HOY)
    assert serie[-1]["cobrado"] == 0
    assert serie[-1]["por_cobrar"] == 100000


# ── Elección automática de la ventana ────────────────────────────────────────

def test_con_meses_distintos_elige_meses():
    facturas = [_f("2026-07-10", 1000), _f("2026-08-10", 2000)]
    assert bc.elegir_periodo(facturas, HOY) == "mes"


def test_con_todo_en_un_mes_baja_a_semanas():
    facturas = [_f("2026-08-10", 1000), _f("2026-08-24", 2000)]
    assert bc.elegir_periodo(facturas, HOY) == "semana"


def test_con_todo_en_una_semana_baja_a_dias():
    facturas = [_f("2026-08-25", 1000), _f("2026-08-27", 2000)]
    assert bc.elegir_periodo(facturas, HOY) == "dia"


def test_sin_facturas_no_se_cuelga_y_devuelve_dias():
    assert bc.elegir_periodo([], HOY) == "dia"


# ── Crecimiento ──────────────────────────────────────────────────────────────

def test_crecimiento_compara_el_ultimo_periodo_con_el_anterior():
    serie = bc.series([_f("2026-07-10", 100000), _f("2026-08-10", 150000)], "mes", HOY)
    crec = bc.growth(serie)
    assert crec["diferencia"] == 50000
    assert crec["pct"] == 50.0


def test_sin_periodo_anterior_no_inventa_un_porcentaje():
    serie = bc.series([_f("2026-08-10", 150000)], "mes", HOY)
    assert bc.growth(serie)["pct"] is None


# ── Datos listos para dibujar ────────────────────────────────────────────────

def test_las_alturas_son_porcentaje_del_periodo_mas_alto():
    datos = bc.chart_data([_f("2026-07-10", 100000, 25000), _f("2026-08-10", 50000)],
                          periodo="mes", hoy=HOY)
    julio, agosto = datos["serie"][-2], datos["serie"][-1]
    assert julio["cobrado_pct"] + julio["por_cobrar_pct"] == 100.0
    assert agosto["cobrado_pct"] == 50.0


def test_sin_facturas_las_alturas_son_cero_y_no_dividen_por_cero():
    datos = bc.chart_data([], periodo="mes", hoy=HOY)
    assert datos["tope"] == 0
    assert all(p["cobrado_pct"] == 0 for p in datos["serie"])


def test_un_periodo_invalido_cae_en_la_eleccion_automatica():
    datos = bc.chart_data([_f("2026-08-25", 1000), _f("2026-08-27", 2000)],
                          periodo="trimestre", hoy=HOY)
    assert datos["periodo"] == "dia"


def test_los_totales_del_encabezado_cuadran_con_la_serie():
    datos = bc.chart_data([_f("2026-08-10", 100000, 40000)], periodo="mes", hoy=HOY)
    assert datos["total_facturado"] == 100000
    assert datos["total_cobrado"] == 60000
    assert datos["total_por_cobrar"] == 40000
    assert datos["total_cobrado"] + datos["total_por_cobrar"] == datos["total_facturado"]
