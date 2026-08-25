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


def test_extract_clinic_name_from_reverse_marker_phrase():
    from app.agent import _extract_clinic_name_candidate

    assert _extract_clinic_name_candidate("animal Pet es la clinica con la que trabajo") == "animal Pet"


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


def test_catalog_profile_match_covers_roman_eleven_and_twelve():
    """Auditoría 2026-08-25: el mapa romano↔arábigo llegaba hasta X — 'prequirúrgico 11'
    no encontraba el 162 (Perfil Prequirúrgico XI) ni 'cachorros 12' el 212 (XII)."""
    from app.services.db import _catalog_profile_matches

    assert _catalog_profile_matches("prequirurgico 11", {"code": "162", "name": "Perfil Prequirúrgico XI"})
    assert _catalog_profile_matches("cachorros 11", {"code": "211", "name": "Perfil Cachorros XI"})
    assert _catalog_profile_matches("cachorros 12", {"code": "212", "name": "Perfil Cachorros XII"})
    assert _catalog_profile_matches("infecciosas felina 11", {"code": "361", "name": "Perfil Infecciosas Felina XI"})


def test_find_tests_by_area_matches_sample_name(monkeypatch):
    from app.services import db

    rows = [
        {"code": "U01", "name": "Parcial de Orina", "category": "Uroanálisis", "sample": "Orina Fresca", "price": 22000},
        {"code": "U02", "name": "Urocultivo", "category": "Uroanálisis", "sample": "Orina Fresca", "price": 45000},
        {"code": "H01", "name": "Hemograma", "category": "Hematología", "sample": "Sangre", "price": 30000},
    ]

    class FakeQuery:
        def select(self, *_args):
            return self

        def eq(self, *_args):
            return self

        def in_(self, *_args):
            return self

        def limit(self, *_args):
            return self

        def execute(self):
            return SimpleNamespace(data=rows)

    class FakeClient:
        def table(self, table_name: str):
            assert table_name == "catalog_tests"
            return FakeQuery()

    monkeypatch.setattr(db, "_client", FakeClient())

    area, tests = db.find_tests_by_area("orina", limit=10)

    assert area == "Uroanálisis"
    assert [test["code"] for test in tests] == ["U01", "U02"]


def test_find_tests_by_area_ignores_structural_words(monkeypatch):
    """ERR-063 (prueba real 2026-07-16): el 'con' de 'vamos CON el 152 y le quiero agregar
    potasio y sodio' matcheaba la muestra 'Tubo Tapa Azul CON 3/4 de sangre' y devolvía el
    área Coagulación. Las palabras estructurales no identifican un área."""
    from types import SimpleNamespace
    from app.services import db

    rows = [
        {"code": "1201", "name": "PT (Tiempo de Protrombina)", "category": "Coagulación",
         "sample": "Tubo Tapa Azul con 3/4 de sangre", "price": 18000},
        {"code": "1202", "name": "PTT", "category": "Coagulación",
         "sample": "Tubo Tapa Azul con 3/4 de sangre", "price": 18000},
    ]

    class FakeQuery:
        def select(self, *_args):
            return self

        def eq(self, *_args):
            return self

        def in_(self, *_args):
            return self

        def limit(self, *_args):
            return self

        def execute(self):
            return SimpleNamespace(data=rows)

    class FakeClient:
        def table(self, table_name: str):
            assert table_name == "catalog_tests"
            return FakeQuery()

    monkeypatch.setattr(db, "_client", FakeClient())

    area, tests = db.find_tests_by_area(
        "vamos con el 152 y le quiero agregar potasio y sodio si?", limit=10)
    assert area is None and tests == []
    # Control positivo: nombrar la muestra por su contenido sí matchea.
    area2, tests2 = db.find_tests_by_area("tubo tapa azul", limit=10)
    assert area2 == "Coagulación" and len(tests2) == 2


def test_create_request_persists_adjusted_profile_payload(monkeypatch):
    from app.services import db

    inserted_requests = []
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
                inserted_requests.append(self.payload)
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
        {"client_id": "client-1", "channel": "chatwoot"},
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
    # La columna entry_channel usa un valor admitido por el check constraint de la BD
    # (hoy solo "telegram"); el canal real del agente (Chatwoot) se conserva en el evento.
    assert inserted_requests[0]["entry_channel"] == "telegram"
    event_payload = inserted_events[0]["event_payload"]
    assert event_payload["source"] == "chatwoot"
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
