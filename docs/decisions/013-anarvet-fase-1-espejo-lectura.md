# 013 — Anarvet Fase 1: espejo de solo lectura

**Fecha:** 2026-08-25
**Estado:** Aceptada (Fase 1 implementada)

## Contexto

Anarvet es el sistema donde viven los resultados de exámenes del laboratorio. El
28/07 se acordó el camino técnico (acceso SQL de solo consulta, sin API REST — ver
Auditoría Alcance §D) y el 2026-08-25 entregaron las credenciales: un usuario
PostgreSQL restringido que ÚNICAMENTE puede ejecutar
`SELECT * FROM fn_reporte_examenes('AAAA-MM-DD','AAAA-MM-DD')` — un registro por
analito con resultado, filtrable solo por rango de fechas. Sin PDF: si se necesita,
lo generamos nosotros (fase posterior).

Smoke real (2026-08-25): ~3.900 analitos/día; todas las fechas llegan como `date`
(incluida `fec_val`); textos con espacios/saltos colgando; conexión **sin TLS**.

## Decisión

**Fase 1 = espejo de lectura, sin tocar el flujo conversacional.** El chat sigue
respondiendo el mensaje fijo de "resultados no disponibles"; habilitarlo será otra
fase con su propio plan y OK explícito.

1. **Servicio `app/services/anarvet.py`** (patrón alegra.py): conexión por llamada
   con `psycopg[binary]` (pin exacto), `connect_timeout=10`,
   `default_transaction_read_only=on` + `statement_timeout=60s` (doble cinturón
   sobre el usuario ya restringido), `sslmode=prefer`. Excepción deliberada a la
   regla "solo SDK" de services/CLAUDE.md: esa regla es para nuestro Supabase;
   Anarvet es otro Postgres sin API.
2. **Espejo en Supabase** (`anarvet_results`, migración 023) con sync **solo
   manual** desde el dashboard (`POST /api/dashboard/anarvet/sync`) — el proyecto
   no tiene scheduler y el disparo oportunista tocaría el camino del chat.
   Dedupe: `dedup_key = sha1(codigo|fechasolicitud|examenes|analito_cod)`; excluye
   `resultado`/`fec_val` para que una re-validación actualice en vez de duplicar.
3. **Mapeo de clientes en tabla dedicada `anarvet_client_map`** (estados
   pending/auto/manual/none). NO se reutiliza `clients.external_code`: ese campo ya
   significa "código cliente interno" del legacy y es editable en el dashboard —
   una edición manual rompería el vínculo Anarvet en silencio. Matching por nombre
   con la regla fuzzy existente (`db.client_name_matches`) vía
   `tools/scripts/anarvet_map_clients.py` (dry-run por defecto); ambiguos y sin
   match se asignan a mano por endpoint.
4. **Flag `ANARVET_ENABLED`** (default off) + health check no crítico: Anarvet
   caído = `degraded`, nunca 503.

## Consecuencias

- Primera corrida real: 84/103 códigos mapeados en automático (82%), 15 ambiguos y
  4 sin match quedaron `pending`.
- **Riesgo IP (el mayor):** conectividad verificada solo desde la máquina local; si
  Anarvet filtra por IP, habrá que pedir whitelisting de las IPs de egreso de Render.
  Se prueba encendiendo el flag en Render y corriendo un sync corto.
- **Sin TLS:** el tráfico va en claro por internet. Aceptado en Fase 1 (datos de
  resultados, credenciales de solo lectura); pedir TLS a Anarvet queda anotado.
- Colisión de dedupe aceptada: mismo paciente + examen + analito + fecha colapsa en
  una fila (2 casos en 7.694 filas reales).
- El PDF de resultados y el flujo de chat quedan para fases siguientes.
