"""Auditoría de integridad de clientes, fichas y médicos (SOLO LECTURA).

Uso:
    python tools/scripts/audit_data_integrity.py

Verifica que las cargas no hayan duplicado ni pisado datos previos. Distingue lo legítimo
de lo que no:

  LEGÍTIMO   varias sedes de una clínica compartiendo NIT (nombres/direcciones distintos)
  LEGÍTIMO   una clínica con muchos médicos
  LEGÍTIMO   un médico que atiende en varias clínicas
  PROBLEMA   dos filas de cliente con el MISMO nombre normalizado
  PROBLEMA   dos sedes con mismo NIT Y mismo nombre (no se pueden distinguir)
  PROBLEMA   el mismo médico repetido dentro de la misma clínica
  PROBLEMA   fichas o médicos huérfanos, correos inválidos, clientes sin NIT

Sale con código 1 si encuentra algún problema.
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from app.services import db  # noqa: E402

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)
problems: list[str] = []


def fetch(table: str, columns: str) -> list[dict]:
    out, offset = [], 0
    while True:
        page = db._client.table(table).select(columns).range(offset, offset + 999).execute().data
        out += page
        if len(page) < 1000:
            break
        offset += 1000
    return out


def report(title: str) -> None:
    print(f"\n{'=' * 66}\n{title}\n{'=' * 66}")


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  [{'OK ' if ok else '!! '}] {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        problems.append(label)


def audit_clients(clients: list[dict]) -> None:
    report("CLIENTES")
    active = [c for c in clients if c.get("is_active")]
    print(f"  total {len(clients)} | activos {len(active)} | inactivos {len(clients) - len(active)}")

    by_name = defaultdict(list)
    for client in clients:
        by_name[db._normalize_lookup_key(client.get("clinic_name"))].append(client)
    dup_names = {k: v for k, v in by_name.items() if len(v) > 1 and k}
    check(not dup_names, "sin clientes con el mismo nombre", f"{len(dup_names)} nombres repetidos")
    for key, group in list(dup_names.items())[:8]:
        nits = {str(c.get("tax_id") or "-") for c in group}
        print(f"       '{group[0]['clinic_name'][:40]}' x{len(group)}  NITs={sorted(nits)}")

    by_nit = defaultdict(list)
    for client in clients:
        nit = db._normalize_nit(client.get("tax_id") or "")
        if nit:
            by_nit[nit].append(client)
    shared = {k: v for k, v in by_nit.items() if len(v) > 1}
    print(f"  NITs con varias sedes: {len(shared)} (legítimo: misma veterinaria)")
    # Lo que sí es un problema: mismo NIT Y mismo nombre -> filas indistinguibles.
    indistinguishable = [
        (nit, group) for nit, group in shared.items()
        if len({db._normalize_lookup_key(c.get("clinic_name")) for c in group}) < len(group)
    ]
    check(not indistinguishable, "las sedes de un mismo NIT se distinguen por nombre",
          f"{len(indistinguishable)} NITs con nombres repetidos")
    for nit, group in indistinguishable[:8]:
        print(f"       NIT {nit}: {[c['clinic_name'][:30] for c in group]}")

    phones = Counter(re.sub(r"\D", "", str(c.get("phone") or "")) for c in clients)
    dup_phones = {p: n for p, n in phones.items() if p and n > 1}
    check(not dup_phones, "sin teléfonos repetidos", f"{len(dup_phones)} teléfonos en más de un cliente")
    for phone, count in list(dup_phones.items())[:5]:
        names = [c["clinic_name"][:28] for c in clients if re.sub(r"\D", "", str(c.get("phone") or "")) == phone]
        print(f"       {phone} x{count}: {names}")

    sin_nit = [c for c in clients if not db._normalize_nit(c.get("tax_id") or "")]
    check(not sin_nit, "todos los clientes tienen NIT", f"{len(sin_nit)} sin NIT")

    con_mail = [c for c in clients if c.get("email")]
    malos = [c for c in con_mail if not EMAIL_RE.match(str(c["email"]).strip())]
    check(not malos, f"los {len(con_mail)} correos de clients son válidos", f"{len(malos)} inválidos")


def audit_knowledge(knowledge: list[dict], clients: list[dict]) -> None:
    report("FICHAS (clients_a3_knowledge)")
    print(f"  total {len(knowledge)}")
    keys = [k["clinic_key"] for k in knowledge]
    check(len(keys) == len(set(keys)), "clinic_key sin duplicados (es PK)")

    sin_nombre = [k for k in knowledge if not str(k.get("clinic_name") or "").strip()]
    check(not sin_nombre, "todas las fichas tienen nombre", f"{len(sin_nombre)} vacías")

    con_mail = [k for k in knowledge if k.get("email")]
    malos = [k for k in con_mail if not EMAIL_RE.match(str(k["email"]).strip())]
    check(not malos, f"los {len(con_mail)} correos de las fichas son válidos", f"{len(malos)} inválidos")

    client_keys = {db._normalize_lookup_key(c.get("clinic_name")) for c in clients}
    huerfanas = [k for k in knowledge if k["clinic_key"] not in client_keys]
    # No es un error: knowledge es un anexo histórico más amplio que la cartera activa.
    print(f"  fichas sin cliente en `clients`: {len(huerfanas)} (esperado: anexo histórico)")


def audit_professionals(professionals: list[dict], knowledge: list[dict]) -> None:
    report("MÉDICOS (clients_a3_professionals)")
    print(f"  total {len(professionals)}")

    by_clinic = defaultdict(list)
    for row in professionals:
        by_clinic[row["clinic_key"]].append(row)
    print(f"  clínicas con médicos: {len(by_clinic)} "
          f"| promedio {len(professionals) / max(len(by_clinic), 1):.1f} médicos por clínica")

    # El unique de la tabla es (clinic_key, professional_key, source_sheet): el MISMO médico
    # cargado desde dos Excel distintos genera dos filas. Eso sí es un duplicado real.
    pairs = Counter((r["clinic_key"], db._normalize_lookup_key(r.get("professional_name"))) for r in professionals)
    dupes = {p: n for p, n in pairs.items() if n > 1 and p[1]}
    check(not dupes, "ningún médico repetido dentro de la misma clínica",
          f"{len(dupes)} pares clínica-médico duplicados")
    for (clinic, doctor), count in list(dupes.items())[:8]:
        sheets = [r.get("source_sheet") for r in by_clinic[clinic]
                  if db._normalize_lookup_key(r.get("professional_name")) == doctor]
        print(f"       {clinic[:28]:28} / {doctor[:24]:24} x{count}  {sheets}")

    known = {k["clinic_key"] for k in knowledge}
    huerfanos = [r for r in professionals if r["clinic_key"] not in known]
    check(not huerfanos, "ningún médico huérfano (FK contra las fichas)", f"{len(huerfanos)} huérfanos")

    sin_nombre = [r for r in professionals if not str(r.get("professional_name") or "").strip()]
    check(not sin_nombre, "todos los médicos tienen nombre", f"{len(sin_nombre)} sin nombre")

    # Un médico en varias clínicas es normal (trabaja en más de una).
    por_medico = Counter(db._normalize_lookup_key(r.get("professional_name")) for r in professionals)
    multi = sum(1 for n in por_medico.values() if n > 1)
    print(f"  médicos distintos: {len(por_medico)} | en más de una clínica: {multi} (legítimo)")
    print(f"  origen de los datos: {dict(Counter(r.get('source_sheet') for r in professionals).most_common())}")


def audit_pending(clients: list[dict]) -> None:
    report("ALTAS PENDIENTES")
    pending = db.list_pending_client_reviews()
    print(f"  en la cola: {len(pending)}")
    by_id = {c["id"]: c for c in clients}
    activos = [p for p in pending if (by_id.get(p.get("client_id")) or {}).get("is_active")]
    check(not activos, "ninguna alta pendiente quedó ACTIVA (el bot no las atiende)",
          f"{len(activos)} activas por error")
    for p in pending:
        client = by_id.get(p.get("client_id")) or {}
        print(f"       {str(client.get('clinic_name'))[:38]:38} activo={client.get('is_active')} NIT={client.get('tax_id')}")
    sin_request = [c for c in clients if c.get("is_active") is False
                   and c["id"] not in {p.get("client_id") for p in pending}]
    print(f"  clientes inactivos sin solicitud en la cola: {len(sin_request)} "
          f"(históricos dados de baja, no de esta carga)")


def main() -> int:
    clients = fetch("clients", "id, clinic_name, tax_id, phone, address, email, is_active")
    knowledge = fetch("clients_a3_knowledge", "clinic_key, clinic_name, email, phone, source_excel")
    professionals = fetch("clients_a3_professionals", "clinic_key, professional_name, source_sheet")

    audit_clients(clients)
    audit_knowledge(knowledge, clients)
    audit_professionals(professionals, knowledge)
    audit_pending(clients)

    report("RESULTADO")
    if problems:
        print(f"  {len(problems)} problema(s):")
        for item in problems:
            print(f"     - {item}")
    else:
        print("  Sin problemas de integridad.")
    print("\nSOLO LECTURA: no se escribió nada.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
