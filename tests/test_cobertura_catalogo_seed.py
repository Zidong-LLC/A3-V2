"""Invariante de COBERTURA TOTAL del catálogo (auditoría 2026-08-25, pedido del usuario).

Regla de negocio (2026-08-12): *"si te piden algo que está en esa base de datos, ya sea
por número, por nombre o lo que sea, que lo ofrezca — que no diga que no existe"*.

Este test la vuelve un invariante OFFLINE: parsea los seeds reales (misma data que
Supabase, verificado 2026-08-25) y exige que CADA fila resuelva por código y por nombre
con la lógica real del agente. Si un análisis nuevo entra con un nombre que el resolvedor
no puede nombrar, esto se pone rojo antes de que un cliente lo descubra en el chat.

Sin red y sin modelo: `catalog.resolve_tests` es pura; `_catalog_profile_matches` también.
"""
import re
from pathlib import Path

import pytest

from app import catalog
from app.services.db import _catalog_profile_matches

_RAIZ = Path(__file__).resolve().parents[1]
_ROW_RE = re.compile(r"^\('(\d+)',\s*'((?:[^']|'')*)',\s*'((?:[^']|'')*)'")


def _parse_seed(name: str) -> list[dict]:
    rows = []
    for line in (_RAIZ / "db" / "seeds" / name).read_text(encoding="utf-8").splitlines():
        m = _ROW_RE.match(line.strip())
        if m:
            code, nombre, cat = m.groups()
            rows.append({"code": code, "name": nombre.replace("''", "'"),
                         "category": cat, "price": 1000, "sample": "", "species": "ambos"})
    return rows


TESTS_SEED = _parse_seed("002_catalog_tests.sql")
PROFILES_SEED = _parse_seed("001_catalog_profiles.sql")


def test_seed_sizes_match_catalog_2025():
    # 183 análisis + 133 perfiles = PDF completo sin Mascolab (pendiente de A3).
    assert len(TESTS_SEED) == 183
    assert len(PROFILES_SEED) == 133


@pytest.mark.parametrize("row", TESTS_SEED, ids=lambda r: r["code"])
def test_cada_analisis_resuelve_por_codigo_y_nombre(row):
    por_codigo = catalog.resolve_tests(row["code"], TESTS_SEED)
    assert row["code"] in {t["code"] for t in por_codigo.tests}, "no resuelve por código"

    por_nombre = catalog.resolve_tests(row["name"], TESTS_SEED)
    assert row["code"] in {t["code"] for t in por_nombre.tests}, (
        f"'{row['name']}' no encuentra su propio análisis ({por_nombre.status})")


@pytest.mark.parametrize("row", PROFILES_SEED, ids=lambda r: r["code"])
def test_cada_perfil_matchea_por_codigo_y_nombre(row):
    assert _catalog_profile_matches(row["code"], row)
    assert _catalog_profile_matches(row["name"], row)
    # Como lo dice un cliente: sin la palabra 'Perfil' y con arábigos en vez de romanos.
    sin_perfil = re.sub(r"(?i)^perfil\s+", "", row["name"])
    assert _catalog_profile_matches(sin_perfil, row), sin_perfil
