"""Matching one-shot: cod_cliente de Anarvet → clients de Supabase (Fase 1, decisión 013).

Compara el nombre_cliente que reporta Anarvet contra clinic_name de los clientes activos
usando la MISMA regla fuzzy que la identificación del agente (db.client_name_matches).
Exactamente 1 coincidencia → candidato 'auto'; 2+ → ambiguo; 0 → sin match. Los ambiguos
y sin match quedan 'pending' para asignarlos a mano vía el endpoint del dashboard.

DRY-RUN por defecto: solo imprime el reporte. Con --apply persiste los 'auto'.

Uso (desde la raíz del repo):
    python -m tools.scripts.anarvet_map_clients            # reporte, sin escribir
    python -m tools.scripts.anarvet_map_clients --apply    # persiste los match únicos
"""

import argparse

from app.services import db


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Persistir los matches únicos (auto)")
    args = parser.parse_args()

    pendientes = db.list_anarvet_client_map(status="pending")
    if not pendientes:
        print("Sin cod_cliente pendientes: nada que mapear (¿ya corriste un sync?).")
        return 0

    clientes = [
        c for c in db.list_clients_with_assignment()
        if c.get("is_active") and (c.get("clinic_name") or "").strip()
    ]
    print(f"-> {len(pendientes)} códigos pendientes contra {len(clientes)} clientes activos\n")

    autos, ambiguos, sin_match = [], [], []
    for fila in pendientes:
        nombre = (fila.get("nombre_cliente") or "").strip()
        candidatos = [c for c in clientes if db.client_name_matches(nombre, c["clinic_name"])]
        if len(candidatos) == 1:
            autos.append((fila, candidatos[0]))
        elif candidatos:
            ambiguos.append((fila, candidatos))
        else:
            sin_match.append(fila)

    print(f"[AUTO] {len(autos)} con coincidencia única:")
    for fila, c in autos:
        print(f"  {fila['cod_cliente']:>6}  {fila.get('nombre_cliente')!r:<40} -> {c['clinic_name']!r} ({c['id']})")

    print(f"\n[AMBIGUO] {len(ambiguos)} con varias coincidencias (asignar a mano):")
    for fila, cands in ambiguos:
        opciones = ", ".join(repr(c["clinic_name"]) for c in cands[:4])
        print(f"  {fila['cod_cliente']:>6}  {fila.get('nombre_cliente')!r:<40} -> {opciones}")

    print(f"\n[SIN MATCH] {len(sin_match)} sin coincidencia (asignar a mano o marcar 'none'):")
    for fila in sin_match:
        print(f"  {fila['cod_cliente']:>6}  {fila.get('nombre_cliente')!r}")

    if not args.apply:
        print("\nDRY-RUN: no se escribió nada. Repetir con --apply para persistir los AUTO.")
        return 0

    for fila, c in autos:
        db.assign_anarvet_client(fila["cod_cliente"], c["id"], "auto")
    print(f"\n[OK] {len(autos)} mapeos 'auto' persistidos. Ambiguos y sin match siguen 'pending'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
