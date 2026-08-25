"""Cliente PostgreSQL de Anarvet — resultados de exámenes (Fase 1: espejo de lectura).

Aislado: no importa `app/agent.py` ni `app/rules.py` (ver app/services/CLAUDE.md).
El usuario 'consulta' que entregó Anarvet SOLO puede ejecutar fn_reporte_examenes();
además cada sesión se abre read-only y con statement_timeout — doble cinturón sobre
la restricción del servidor (ver docs/decisions/013).

Excepción deliberada a la regla "solo SDK" del módulo: esa regla aplica a nuestro
Supabase; Anarvet es un PostgreSQL externo sin API REST, así que se usa psycopg con
SQL parametrizado. El feature flag ANARVET_ENABLED lo evalúa el llamador; este módulo
solo ejecuta I/O cuando se le invoca, igual que alegra.py.
"""

import re
from datetime import datetime

import psycopg
from psycopg.rows import dict_row

from app.config import (
    ANARVET_DB_HOST,
    ANARVET_DB_PORT,
    ANARVET_DB_NAME,
    ANARVET_DB_USER,
    ANARVET_DB_PASSWORD,
    ANARVET_SSLMODE,
    APP_TIMEZONE,
)

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# El servidor de Anarvet está en internet por IP cruda: timeouts obligatorios para que
# una caída suya nunca cuelgue un request nuestro (el repo histórico no usaba timeouts).
_CONNECT_TIMEOUT_S = 10
_STATEMENT_TIMEOUT_MS = 60_000


class AnarvetError(RuntimeError):
    """Falla al hablar con la base de Anarvet. Lleva contexto útil para el log."""


def _connect() -> psycopg.Connection:
    """Abre una conexión nueva, read-only y con timeouts. El tráfico es un sync manual
    esporádico + ping de health: una conexión por llamada alcanza, sin pool."""
    if not ANARVET_DB_HOST or not ANARVET_DB_PASSWORD:
        raise AnarvetError(
            "Anarvet sin configurar: faltan ANARVET_DB_HOST/ANARVET_DB_PASSWORD en el entorno"
        )
    return psycopg.connect(
        host=ANARVET_DB_HOST,
        port=ANARVET_DB_PORT,
        dbname=ANARVET_DB_NAME,
        user=ANARVET_DB_USER,
        password=ANARVET_DB_PASSWORD,
        connect_timeout=_CONNECT_TIMEOUT_S,
        sslmode=ANARVET_SSLMODE,
        options=(
            f"-c default_transaction_read_only=on "
            f"-c statement_timeout={_STATEMENT_TIMEOUT_MS}"
        ),
        row_factory=dict_row,
    )


def _query(sql: str, params: tuple = ()) -> list[dict]:
    """Ejecuta una consulta y devuelve las filas como dicts. Re-lanza con contexto
    (host/base y causa — nunca la contraseña) en cualquier error de red o SQL."""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    except psycopg.Error as e:
        raise AnarvetError(
            f"Anarvet {ANARVET_DB_HOST}:{ANARVET_DB_PORT}/{ANARVET_DB_NAME} "
            f"-> {type(e).__name__}: {e}"
        ) from e


def fetch_report(desde: str, hasta: str) -> list[dict]:
    """Trae el reporte de exámenes del rango [desde, hasta] (formato AAAA-MM-DD).
    Devuelve un dict por analito con resultado; Anarvet excluye los vacíos."""
    for etiqueta, valor in (("desde", desde), ("hasta", hasta)):
        if not isinstance(valor, str) or not _DATE_RE.match(valor):
            raise AnarvetError(f"Fecha '{etiqueta}' inválida: {valor!r} (se espera AAAA-MM-DD)")
    return _query("SELECT * FROM fn_reporte_examenes(%s, %s)", (desde, hasta))


def ping() -> bool:
    """Valida conectividad y credenciales con la consulta mínima que el usuario
    restringido puede ejecutar: la función con rango de 1 día y LIMIT 1.
    Lanza AnarvetError si la red, las credenciales o la función fallan."""
    hoy = datetime.now(APP_TIMEZONE).strftime("%Y-%m-%d")
    _query("SELECT * FROM fn_reporte_examenes(%s, %s) LIMIT 1", (hoy, hoy))
    return True
