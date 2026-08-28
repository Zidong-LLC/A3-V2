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

# Lo que pide una veterinaria de verdad: desde un análisis suelto hasta una orden con
# tres perfiles y varios sueltos para el mismo paciente. Sirve para ver si la tabla
# aguanta el peor caso, que es justo el que antes no se podía cargar.
COMBINACIONES = (
    ["Cuadro Hemático Completo"],
    ["Perfil Prequirúrgico I", "Cuadro Hemático Completo"],
    ["Perfil Renal I", "Perfil Hepático Canino I", "Uroanálisis"],
    ["Perfil Parasitológico I"],
    ["Perfil Prequirúrgico II", "Perfil Renal I", "Perfil Hepático Canino II",
     "Cuadro Hemático Completo", "Recuento de Plaquetas"],
    ["Citología PAF", "Cultivo y Antibiograma"],
    ["Perfil Hepático Canino I", "Perfil Renal I", "Perfil Tiroideo",
     "Hemoparásitos", "Uroanálisis", "Coprológico Seriado", "Ionograma"],
    ["Coprológico Seriado"],
    ["Perfil Geriátrico", "Perfil Cardíaco", "Cuadro Hemático Completo"],
    ["Hemoglobina y Hematocrito"],
)


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
        combinacion = COMBINACIONES[i % len(COMBINACIONES)]
        _, muestra, _ = ANALISIS[i % len(ANALISIS)]
        cantidad_muestras = min(len(combinacion), 6)
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
            "exam_type": ", ".join(combinacion),
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
            combinacion = COMBINACIONES[(i + j) % len(COMBINACIONES)]
            ordenes.append({
                "order_number": f"A3-2026-{900 + i * 3 + j}",
                "patient_name": paciente,
                "species": especie,
                "exam_type": ", ".join(combinacion),
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


# ── Muestras ──────────────────────────────────────────────────────────────────

ESTADOS_MUESTRA = ("pending_pickup", "picked_up", "received_lab", "in_lab", "processed", "sent")
TIPOS_MUESTRA = ("Tubo Tapa Morada", "Tubo Rojo", "Orina Fresca", "Materia Fecal",
                 "Tubo Rojo y Tapa Morada", "Lámina")


def samples(cantidad: int = 10) -> list[dict]:
    """Muestras de ejemplo para la tabla de Muestras.

    Cada una lleva la MISMA combinación de análisis que la solicitud que le
    corresponde: es el caso que hay que mirar, porque una sola muestra puede
    responder a tres perfiles del mismo paciente."""
    ahora = _ahora()
    filas = []
    for i in range(cantidad):
        clinica, _, motorizado = CLIENTES[i % len(CLIENTES)]
        combinacion = COMBINACIONES[i % len(COMBINACIONES)]
        estado = ESTADOS_MUESTRA[i % len(ESTADOS_MUESTRA)]
        filas.append({
            "id": f"demo-sample-{i + 1}",
            "created_at": (ahora - timedelta(hours=4 * i + 2)).isoformat(),
            "clients": {"clinic_name": clinica},
            "sample_type": TIPOS_MUESTRA[i % len(TIPOS_MUESTRA)],
            "test_name": ", ".join(combinacion),
            "test_code": None,
            "status": estado,
            "dropdown_status": estado if estado in ("pending_pickup", "picked_up", "received_lab", "in_lab") else "in_lab",
            "couriers": {"name": motorizado},
        })
    return filas
