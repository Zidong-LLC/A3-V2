"""Genera la migración del convenio Mascolab cruzando el Excel de A3 con los precios.

Fuentes:
  - «Documentos de actualizacion/Mascolab.xlsx»: 122 filas (61 códigos, cada uno en
    Punto Final y en Tiempo Real con sufijo «-1»). Trae referencia, nombre y categoría.
  - «docs/catalogo-mascolab-pendiente.md»: los precios de ambas técnicas, extraídos del
    catálogo 2025. Tarifa general $157.000 / $224.000 salvo los marcados.

Decisión de A3 (2026-08-27): se cargan LAS DOS técnicas — el médico elige, y cada una
lleva su precio. El nombre lleva la técnica entre paréntesis para poder distinguirlas
al cotizar. El código 2461 entra con la tarifa general.

    python tools/scripts/build_mascolab_migration.py

Escribe db/migrations/030_catalog_mascolab.sql (no lo aplica).
"""

import io
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]
EXCEL = ROOT / "Documentos de actualizacion" / "Mascolab.xlsx"
DOC = ROOT / "docs" / "catalogo-mascolab-pendiente.md"
SALIDA = ROOT / "db" / "migrations" / "030_catalog_mascolab.sql"

TARIFA_GENERAL = (157000, 224000)
MUESTRA = "PCR — consultar tipo de muestra con el laboratorio (entrega 3 dias habiles)"


def _precio(texto: str) -> tuple[int, int] | None:
    """'$168.000 / $238.000' -> (168000, 238000)."""
    montos = [int(m.replace(".", "")) for m in re.findall(r"\$([\d.]+)", texto or "")]
    return (montos[0], montos[1]) if len(montos) >= 2 else None


def _leer_doc() -> tuple[dict, dict, set]:
    """Devuelve (precios por código, especie por código, códigos que son perfil)."""
    texto = io.open(DOC, encoding="utf-8").read()
    precios: dict[str, tuple[int, int]] = {}
    especies: dict[str, str] = {}
    perfiles: set[str] = set()
    seccion_perfiles = False
    for linea in texto.splitlines():
        if linea.startswith("## Perfiles Mascolab"):
            seccion_perfiles = True
            continue
        if linea.startswith("## Individuales"):
            seccion_perfiles = False
            continue
        fila = re.match(r"^\|\s*(\d{4})\s*\|([^|]*)\|([^|]*)\|(.*)$", linea)
        if not fila:
            continue
        codigo, _nombre, especie, resto = fila.groups()
        especies[codigo] = especie.strip().lower() or "ambos"
        precios[codigo] = _precio(resto) or TARIFA_GENERAL
        if seccion_perfiles:
            perfiles.add(codigo)
    return precios, especies, perfiles


def _sql_str(valor: str) -> str:
    return "'" + str(valor).replace("'", "''") + "'"


def main() -> int:
    precios, especies, perfiles = _leer_doc()
    filas = list(openpyxl.load_workbook(EXCEL, data_only=True).active.iter_rows(values_only=True))[1:]

    tests, profiles, sin_precio = [], [], []
    for referencia, nombre, categoria in filas:
        if not referencia:
            continue
        ref = str(referencia).strip()
        base = ref.split("-")[0]
        tiempo_real = ref.endswith("-1")
        tecnica = "Tiempo Real" if tiempo_real else "Punto Final"
        par = precios.get(base)
        if par is None:
            par = TARIFA_GENERAL
            sin_precio.append(base)
        precio = par[1] if tiempo_real else par[0]
        # El nombre lleva la técnica: en el Excel las dos filas se llaman igual y el bot
        # no podría distinguir cuál está cotizando.
        nombre_final = f"{str(nombre).strip()} ({tecnica})"
        registro = (ref, nombre_final, str(categoria).strip(), especies.get(base, "ambos"), precio)
        (profiles if base in perfiles else tests).append(registro)

    lineas = [
        "-- 030: Convenio Mascolab (pruebas moleculares PCR).",
        "-- Ejecutar con tools/scripts/apply_supabase_migration.py o el SQL Editor de Supabase.",
        "-- GENERADO por tools/scripts/build_mascolab_migration.py — no editar a mano.",
        "--",
        "-- Fuente: Mascolab.xlsx (A3, 2026-08-27) + precios de docs/catalogo-mascolab-pendiente.md.",
        "-- Cada prueba se carga DOS veces: codigo base = Punto Final, sufijo -1 = Tiempo Real,",
        "-- con su propio precio. El medico elige la tecnica al pedir (decision de A3).",
        "--",
        f"-- {len(tests)} analisis individuales + {len(profiles)} perfiles = {len(tests) + len(profiles)} entradas.",
        "-- ON CONFLICT DO NOTHING: el catalogo se edita desde el dashboard; re-ejecutar no pisa precios.",
        "",
    ]
    if profiles:
        lineas.append("INSERT INTO catalog_profiles (code, name, category, species, description, price) VALUES")
        lineas += [
            "    (%s, %s, %s, %s, %s, %d)%s" % (
                _sql_str(c), _sql_str(n), _sql_str(cat), _sql_str(esp), _sql_str(MUESTRA), p,
                "," if i < len(profiles) - 1 else "\nON CONFLICT (code) DO NOTHING;")
            for i, (c, n, cat, esp, p) in enumerate(profiles)
        ]
        lineas.append("")
    if tests:
        lineas.append("INSERT INTO catalog_tests (code, name, category, species, sample, price) VALUES")
        lineas += [
            "    (%s, %s, %s, %s, %s, %d)%s" % (
                _sql_str(c), _sql_str(n), _sql_str(cat), _sql_str(esp), _sql_str(MUESTRA), p,
                "," if i < len(tests) - 1 else "\nON CONFLICT (code) DO NOTHING;")
            for i, (c, n, cat, esp, p) in enumerate(tests)
        ]
    SALIDA.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    print(f"{SALIDA.relative_to(ROOT)}")
    print(f"  perfiles      : {len(profiles)}")
    print(f"  analisis      : {len(tests)}")
    if sin_precio:
        print(f"  sin precio en el doc (tarifa general): {sorted(set(sin_precio))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
