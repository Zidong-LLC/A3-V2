"""
Tests de helpers de identificación de cliente (sin I/O de red).
"""

from types import SimpleNamespace


def test_nit_candidates_include_hyphen_and_base_variants():
    from app.services.db import _nit_candidates

    candidates = _nit_candidates("194207252")

    assert "194207252" in candidates
    assert "19420725" in candidates
    assert "19420725-2" in candidates


def test_nit_candidates_preserve_original_input_when_present():
    from app.services.db import _nit_candidates

    candidates = _nit_candidates("19420725-2")

    assert candidates[0] == "19420725-2"
    assert "194207252" in candidates


def test_nit_candidates_normalize_punctuation_and_check_digit():
    from app.services.db import _nit_candidates

    candidates = _nit_candidates("900.296.338-1")

    assert "900.296.338-1" in candidates
    assert "9002963381" in candidates
    assert "900296338" in candidates
    assert "900296338-1" in candidates


def test_nit_candidates_include_letter_verification_digit():
    from app.services.db import _nit_candidates

    candidates = _nit_candidates("80737694N")

    assert "80737694" in candidates
    assert "80737694-N" in candidates


def test_nit_candidates_include_excel_decimal_base():
    from app.services.db import _nit_candidates

    candidates = _nit_candidates("900296338.0")

    assert "900296338" in candidates


def test_name_matches_normalized_user_phrases():
    from app.services.db import _name_matches

    assert _name_matches("Somos Adryvete", "Adryvete")
    assert _name_matches("Agro mascotas", "Agromascotas")
    assert not _name_matches("No tengo ese dato", "Adryvete")


def test_identify_client_falls_back_to_name_when_tax_id_is_wrong(monkeypatch):
    from app.services import db

    client = {"id": "client-by-name", "clinic_name": "Agromascotas", "is_active": True}
    calls = []

    class FakeQuery:
        def __init__(self):
            self.filters = {}

        def select(self, *_args):
            return self

        def eq(self, field, value):
            self.filters[field] = value
            return self

        def ilike(self, field, value):
            self.filters[field] = value
            return self

        def execute(self):
            calls.append(dict(self.filters))
            if "clinic_name" in self.filters:
                return SimpleNamespace(data=[client])
            return SimpleNamespace(data=[])

    class FakeClient:
        def table(self, table_name: str):
            assert table_name == "clients"
            return FakeQuery()

    monkeypatch.setattr(db, "_client", FakeClient())

    result = db.identify_client(name="Agromascotas", tax_id="000000000")

    assert result == client
    assert any(call.get("tax_id") for call in calls)
    assert any(call.get("clinic_name") == "%Agromascotas%" for call in calls)


def test_catalog_profile_match_accepts_roman_and_arabic_aliases():
    from app.services.db import _catalog_profile_matches

    row = {"code": "501", "name": "Perfil Renal I"}

    assert _catalog_profile_matches("501", row)
    assert _catalog_profile_matches("Perfil Renal I", row)
    assert _catalog_profile_matches("renal I", row)
    assert _catalog_profile_matches("renal 1", row)
    assert _catalog_profile_matches("perfil renal 1", row)


def test_create_request_persists_adjusted_profile_payload(monkeypatch):
    from app.services import db

    inserted_events = []

    class FakeQuery:
        def __init__(self, table_name: str):
            self.table_name = table_name
            self.payload = None

        def insert(self, payload):
            self.payload = payload
            return self

        def execute(self):
            if self.table_name == "requests":
                return SimpleNamespace(data=[{"id": "req-profile-1"}])
            if self.table_name == "request_events":
                inserted_events.append(self.payload)
                return SimpleNamespace(data=[self.payload])
            return SimpleNamespace(data=[])

    class FakeClient:
        def table(self, table_name: str):
            return FakeQuery(table_name)

    monkeypatch.setattr(db, "_client", FakeClient())
    monkeypatch.setattr(db, "get_courier_for_client", lambda client_id: None)
    monkeypatch.setattr(
        db,
        "get_tests_by_codes_or_names",
        lambda items: [
            {"code": "1302", "name": "ALT", "price": 12000},
        ] if items == ["1302"] else [
            {"code": "1309", "name": "Creatinina", "price": 12000},
        ] if items == ["1309"] else [],
    )

    result = db.create_request(
        "chat-1",
        {"client_id": "client-1"},
        {
            "intent": "route_scheduling",
            "handoff_area": None,
            "captured_fields": {
                "exam_type": "Perfil Renal I",
                "patient_name": "Toby",
                "species": "canino",
                "requesting_doctor": "Dra. Ana Gomez",
                "clinic_phone": "3001234567",
                "breed": "criollo",
                "sex": "macho",
                "patient_age": "5 años",
                "owner_name": "Carlos Perez",
                "observations": "sin observaciones",
                "pickup_address": "Calle 1",
                "payment_method": "contraentrega",
                "selected_tests": ["1302"],
                "removed_tests": ["1309"],
                "_selected_profile_code": "501",
                "_selected_profile_name": "Perfil Renal I",
                "_selected_profile_price": 34000,
                "_selected_profile_description": "Cuadro Hemático, Parcial de Orina, BUN/UREA, Creatinina",
            },
        },
    )

    assert result["request_id"] == "req-profile-1"
    event_payload = inserted_events[0]["event_payload"]
    profile = event_payload["profile"]
    assert profile["base_profile"]["code"] == "501"
    assert profile["base_profile"]["name"] == "Perfil Renal I"
    assert profile["base_profile"]["price"] == 34000
    assert profile["added_tests"] == [{"code": "1302", "name": "ALT", "price": 12000}]
    assert profile["removed_tests"] == [{"code": "1309", "name": "Creatinina", "price": 12000}]
    assert profile["total_estimated"] == 34000
    service_order = event_payload["service_order"]
    assert service_order["requesting_doctor"] == "Dra. Ana Gomez"
    assert service_order["clinic_phone"] == "3001234567"
    assert service_order["patient"]["breed"] == "criollo"
    assert service_order["patient"]["sex"] == "macho"
    assert service_order["patient"]["age"] == "5 años"
    assert service_order["patient"]["owner_name"] == "Carlos Perez"
    assert service_order["observations"] == "sin observaciones"
