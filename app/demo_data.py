"""Datos de ejemplo para VER cómo se ve la plataforma con movimiento.

Nada de esto toca la base: se arma en memoria y se pinta solo cuando la URL trae
`?demo=1`, igual que la vista de Muestras. Sirve para revisar el diseño mientras
lo transaccional está vacío, y para mostrarlo sin ensuciar los datos reales.

Las filas imitan la forma EXACTA que devuelven `db.list_requests` y
`db.list_pedidos_for_dashboard`, así la plantilla no necesita saber si son de
verdad o de ejemplo. Los ids llevan el prefijo `demo-` para que un guardado
accidental falle en la base en vez de escribir algo raro.
"""
from datetime import datetime, timedelta, timezone

CLIENTES = [
    ("Veterinaria Piscis", "CL 78 Sur 9A 36", "Alexander"),
    ("Animal Pets", "CR 68B 98-38", "Cesar"),
    ("Clinica Veterinaria Zoopecas", "CR 88A 59C 45 Sur", "Javier"),
    ("Agromedica Huellas Timiza", "CL 40C Sur 72N Bis-30", "Jeeferson"),
    ("Centro Veterinario Pro Animals", "AV 1 de Mayo 45-12", "Alexander"),
    ("Animals Home Clinica Veterinaria", "CL 134 21-40", "Marlon"),
    ("Bioanimal Vet", "CR 15 93-60", "Cesar"),
    ("Veterinaria Animal Keeper", "CL 53 27-15", "Javier"),
]

ANALISIS = [
    ("Cuadro Hematico Completo", "Tubo Tapa Morada", 2),
    ("Perfil Renal", "Tubo Rojo", 1),
    ("Uroanalisis", "Orina Fresca", 1),
    ("Perfil Prequirurgico", "Tubo Rojo y Tapa Morada", 3),
    ("Coprologico Seriado", "Materia Fecal", 3),
    ("Perfil Hepatico", "Tubo Rojo", 1),
    ("Citologia PAF", "Lamina", 2),
]

PACIENTES = [("Firulais", "canino"), ("Michi", "felino"), ("Rocky", "canino"),
             ("Luna", "felino"), ("Toby", "canino"), ("Nala", "felino")]

ESTADOS = ("received", "assigned", "on_route", "in_lab", "processed",
           "sent", "assigned", "in_lab", "received", "error_pending_assignment")
PRIORIDADES = ("normal", "normal", "alta", "normal", "urgente", "normal")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def requests(cantidad: int = 10, couriers: list[dict] | None = None) -> list[dict]:
    """Solicitudes de ejemplo, de la más reciente a la más vieja.

    `couriers` son los motorizados REALES del dashboard: el desplegable de la tabla
    se arma con ellos, así que con ids inventados la columna mostraba siempre
    «Sin asignar»."""
    ahora = _ahora()
    reales = couriers or []
    filas = []
    for i in range(cantidad):
        clinica, direccion, motorizado = CLIENTES[i % len(CLIENTES)]
        examen, muestra, cantidad_muestras = ANALISIS[i % len(ANALISIS)]
        paciente, especie = PACIENTES[i % len(PACIENTES)]
        estado = ESTADOS[i % len(ESTADOS)]
        pedida = ahora - timedelta(hours=3 * i + 1)
        programada = (pedida + timedelta(days=1)).date()
        filas.append({
            "id": f"demo-req-{i + 1}",
            "order_number": f"A3-2026-{900 + i}",
            "requested_at": pedida.isoformat(),
            "clients": {"clinic_name": clinica},
            "pickup_address": direccion,
            "sample_count": cantidad_muestras,
            "exam_type": examen,
            "sample_types": muestra,
            "priority": PRIORIDADES[i % len(PRIORIDADES)],
            "assigned_courier_id": None if estado == "error_pending_assignment" or not reales
                                   else reales[i % len(reales)].get("id"),
            "couriers": None if estado == "error_pending_assignment" else {"name": motorizado},
            "status": estado,
            "scheduled_pickup_date": None if estado == "error_pending_assignment" else programada.isoformat(),
            "patient_name": paciente,
            "species": especie,
        })
    return filas


def pedidos(cantidad: int = 6) -> list[dict]:
    """Pedidos de ejemplo: uno abierto, uno cerrado sin facturar y el resto facturados."""
    ahora = _ahora()
    estados = ["abierto", "cerrado", "facturado", "facturado", "cerrado", "facturado"]
    pagos = ["contraentrega", "transferencia", "credito", "efectivo", "transferencia", "credito"]
    filas = []
    for i in range(cantidad):
        clinica, _, _ = CLIENTES[i % len(CLIENTES)]
        estado = estados[i % len(estados)]
        ordenes = []
        for j in range((i % 3) + 1):
            paciente, especie = PACIENTES[(i + j) % len(PACIENTES)]
            examen, _, _ = ANALISIS[(i + j) % len(ANALISIS)]
            ordenes.append({
                "order_number": f"A3-2026-{900 + i * 3 + j}",
                "patient_name": paciente,
                "species": especie,
                "exam_type": examen,
            })
        filas.append({
            "id": f"demo-pedido-{i + 1}",
            "pedido_number": f"PED-2026-{100 + i}",
            "client_name": clinica,
            "status": estado,
            "orders": ordenes,
            "orders_count": len(ordenes),
            "payment_method": pagos[i % len(pagos)],
            "created_at": (ahora - timedelta(hours=5 * i + 2)).isoformat(),
            "alegra_invoice_id": f"DEMO-{4000 + i}" if estado == "facturado" else None,
        })
    return filas


def request_status_counts(filas: list[dict]) -> dict:
    """Conteo por estado, para el pipeline del Panel."""
    conteo: dict[str, int] = {}
    for fila in filas:
        conteo[fila["status"]] = conteo.get(fila["status"], 0) + 1
    return conteo
