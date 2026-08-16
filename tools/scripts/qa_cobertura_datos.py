"""QA de COBERTURA DE DATOS: cada fila real de la base contra su vía de resolución.

Pedido del usuario (2026-08-15): verificar que TODO lo cargado sea alcanzable — que ningún
cliente registrado quede sin detectar, ningún código de análisis/perfil sin resolver, ninguna
personalización sin piezas. Complementa el estrés de personas: esto es EXHAUSTIVO y
determinístico (solo lecturas, sin modelo) — recorre las ~992 clínicas, los 159 análisis y
todos los perfiles, uno por uno.

Solo LECTURAS. No escribe nada, no llama al modelo.

Uso:  python tools/scripts/qa_cobertura_datos.py [clientes|tests|perfiles]
"""
import sys
import unicodedata
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(RAIZ / ".env")

from app import catalog  # noqa: E402
from app.services import db  # noqa: E402


def _sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def qa_clientes() -> list[str]:
    """Cada cliente real debe encontrarse por su propio nombre (exacto, minúsculas, sin
    tildes) y por su NIT (crudo y sin puntos/guiones)."""
    # Caché de LECTURA solo para este barrido: las funciones reales de matching disparan
    # ~19.000 consultas de red (la tabla entera por cada búsqueda de nombre; ~8 queries por
    # NIT). Se baja la tabla UNA vez y se sirven las consultas desde memoria con la misma
    # semántica (eq = igualdad exacta, ilike 'x-%' = prefijo, case-insensitive). El código
    # de producción y sus funciones de matching quedan intactos — solo cambia el transporte.
    filas_cache = db._fetch_all_active_clients("id, clinic_name, tax_id, phone, address, zone, email")
    db._fetch_all_active_clients = lambda select_fields="*": filas_cache

    class _TablaEnMemoria:
        def __init__(self, rows):
            self._rows = rows
            self._filtros = []

        def select(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def range(self, lo, hi):
            self._filtros.append(("range", lo, hi))
            return self

        def eq(self, col, val):
            self._filtros.append(("eq", col, val))
            return self

        def ilike(self, col, pat):
            self._filtros.append(("ilike", col, pat))
            return self

        def execute(self):
            rows = self._rows
            for f in self._filtros:
                if f[0] == "eq":
                    _, col, val = f
                    # la caché ya es solo-activos y no trae is_active: ese filtro pasa
                    rows = [r for r in rows if col not in r or str(r.get(col)) == str(val)]
                elif f[0] == "ilike":
                    _, col, pat = f
                    pref = pat.rstrip("%").lower()
                    rows = [r for r in rows if str(r.get(col) or "").lower().startswith(pref)]
                elif f[0] == "range":
                    _, lo, hi = f
                    rows = rows[lo:hi + 1]
            return type("R", (), {"data": list(rows)})()

    class _ClienteEnMemoria:
        def __init__(self, real):
            self._real = real

        def table(self, nombre):
            if nombre == "clients":
                return _TablaEnMemoria(filas_cache)
            return self._real.table(nombre)

    db._client = _ClienteEnMemoria(db._client)
    fallos = []
    filas = db.list_rows("clients", limit=2000) if hasattr(db, "list_rows") else None
    if filas is None:
        filas = db._client.table("clients").select("id, clinic_name, tax_id").limit(2000).execute().data
    print(f"— clientes: {len(filas)} filas")
    for i, c in enumerate(filas):
        nombre = (c.get("clinic_name") or "").strip()
        nit = (c.get("tax_id") or "").strip()
        variantes = []
        if nombre:
            variantes += [("nombre exacto", nombre), ("nombre minúsculas", nombre.lower()),
                          ("nombre sin tildes", _sin_tildes(nombre.lower()))]
        if nit:
            variantes += [("nit", nit), ("nit sin guion", nit.split("-")[0])]
            if nit.endswith(".0"):
                # Mugre de importación (ERR-121): el cliente escribe su NIT REAL, sin el .0
                variantes += [("nit real sin .0", nit[:-2])]
        for etiqueta, consulta in variantes:
            try:
                # El camino REAL de cada dato: nombre → find_client_matches (difuso,
                # identificación); NIT → find_clients_by_tax_id (sedes por NIT).
                m = db.find_client_matches(consulta) if "nombre" in etiqueta \
                    else db.find_clients_by_tax_id(consulta)
            except Exception as exc:
                fallos.append(f"cliente '{nombre}' ({etiqueta}): EXCEPCIÓN {exc}")
                continue
            ids = {r.get("id") for r in (m or [])}
            if c["id"] not in ids:
                fallos.append(f"cliente '{nombre[:40]}' NO se encuentra por {etiqueta} ('{str(consulta)[:30]}')")
        if i and i % 200 == 0:
            print(f"    …{i} verificados, {len(fallos)} fallos")
    return fallos


def qa_tests() -> list[str]:
    """Cada análisis: alcanzable por su CÓDIGO y por su NOMBRE (resolución EXACT al código
    correcto, o AMBIGUOUS con él entre los candidatos)."""
    fallos = []
    filas = db.list_catalog_tests(limit=5000)
    print(f"— análisis: {len(filas)} filas")
    for t in filas:
        code, name = str(t.get("code")), (t.get("name") or "").strip()
        rows = db.get_tests_by_codes([code])
        if not rows:
            fallos.append(f"análisis {code} '{name[:40]}': el CÓDIGO no resuelve")
        res = catalog.resolve_tests(name, filas, None)
        codes_res = {str(r.get("code")) for r in (res.tests or [])}
        if code not in codes_res:
            fallos.append(f"análisis {code} '{name[:40]}': el NOMBRE no lo devuelve "
                          f"(status={res.status}, dio {sorted(codes_res)[:4]})")
    return fallos


def qa_perfiles() -> list[str]:
    """Cada perfil: alcanzable por CÓDIGO (sin veto de especie — ERR-104), por NOMBRE al
    perfil CORRECTO (la clase ERR-041: nombres parecidos no pueden devolver otro), y con
    descripción parseable para la personalización."""
    fallos = []
    filas = db._client.table("catalog_profiles").select(
        "code, name, species, description, price, is_active").eq("is_active", True).limit(2000).execute().data
    print(f"— perfiles: {len(filas)} filas")
    from app.menus import _profile_description_items
    for p in filas:
        code, name = str(p.get("code")), (p.get("name") or "").strip()
        m = db.get_catalog_profiles_by_codes([code], None)
        if not m or str(m[0].get("code")) != code:
            fallos.append(f"perfil {code} '{name[:40]}': el CÓDIGO no resuelve")
        try:
            pornombre = db.find_catalog_profile(name, p.get("species"))
        except Exception as exc:
            pornombre = None
            fallos.append(f"perfil {code} '{name[:40]}': búsqueda por nombre EXPLOTA: {exc}")
        if pornombre and str(pornombre.get("code")) != code:
            fallos.append(f"perfil {code} '{name[:40]}': por NOMBRE devuelve OTRO "
                          f"({pornombre.get('code')} {str(pornombre.get('name'))[:30]}) — clase ERR-041")
        if not _profile_description_items(p.get("description") or ""):
            fallos.append(f"perfil {code} '{name[:40]}': descripción NO parseable "
                          f"(la personalización no puede listar sus pruebas)")
        if not p.get("price"):
            fallos.append(f"perfil {code} '{name[:40]}': SIN PRECIO")
    return fallos


def main() -> int:
    args = sys.argv[1:]
    bloques = {"clientes": qa_clientes, "tests": qa_tests, "perfiles": qa_perfiles}
    correr = {k: v for k, v in bloques.items() if not args or k in args}
    total = 0
    for nombre, fn in correr.items():
        print("=" * 74)
        print(f"COBERTURA — {nombre.upper()}")
        fallos = fn()
        total += len(fallos)
        if fallos:
            print(f"  [XX] {len(fallos)} fallos:")
            for f in fallos[:40]:
                print(f"     - {f}")
            if len(fallos) > 40:
                print(f"     … y {len(fallos) - 40} más")
        else:
            print("  [OK] cobertura completa")
    print("=" * 74)
    print(f"TOTAL: {total} fallos de cobertura")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
