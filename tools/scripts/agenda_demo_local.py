"""Levanta la agenda local con un pedido ficticio, sin tocar Supabase."""
from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.dashboard as dashboard_module
from flask import session

from app.main import app
from app.services import db


COURIERS = [
    {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "name": "Javier", "color": "#0e7490"},
    {"id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "name": "Jeeferson", "color": "#c2410c"},
]
PICKUP = {
    "id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
    "order_number": "DEMO-AGENDA-001",
    "status": "received",
    "priority": "normal",
    "pickup_address": "Calle 93 # 15-40, Bogota",
    "patient_name": "Luna",
    "exam_type": "Perfil prequirurgico",
    "scheduled_pickup_date": date.today().isoformat(),
    "assigned_courier_id": None,
    "client_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
    "clients": {"clinic_name": "Veterinaria Demo A3", "phone": "300 000 0000"},
    "couriers": None,
}


def install_demo() -> None:
    # ponytail: estado en memoria; reiniciar devuelve la demo a "Sin asignar".
    @app.before_request
    def demo_login() -> None:
        session["dashboard_authenticated"] = True
        session["dashboard_username"] = "demo"

    db.list_active_couriers = lambda limit=500: COURIERS
    db.list_pickups_between = lambda start, end, limit=1000: (
        [PICKUP] if start <= PICKUP["scheduled_pickup_date"] <= end else []
    )
    db.get_request_with_client = lambda request_id: PICKUP if request_id == PICKUP["id"] else None
    db.create_request_event = lambda *args, **kwargs: None

    def update_request(request_id: str, payload: dict) -> bool:
        if request_id != PICKUP["id"]:
            return False
        PICKUP.update(payload)
        courier_id = PICKUP.get("assigned_courier_id")
        PICKUP["couriers"] = next((c for c in COURIERS if c["id"] == courier_id), None)
        return True

    db.update_request = update_request
    dashboard_module.notify_assignment = lambda *args, **kwargs: None


if __name__ == "__main__":
    install_demo()
    app.run(host="127.0.0.1", port=5000, debug=False)
