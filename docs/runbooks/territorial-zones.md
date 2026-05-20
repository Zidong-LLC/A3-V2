# Carga territorial de zonas y motorizados A3

## Estado actual

La base Supabase ya tiene registrados los 8 motorizados en `couriers` y se cargaron asignaciones cliente -> motorizado en `client_courier_assignment` desde `Relacion Clientes.xlsx`.

Asignacion territorial base:

| Zona | Motorizado |
|---|---|
| 1 | Javier |
| 2 | Jeeferson |
| 3 | Diego |
| 4 | Luis |
| 5 | Gerardo |
| 6 | Alexander |
| 7 | Marlon |
| 8 | Cesar |

## Archivos fuente versionados

- `data/barrios_zonas_a3.csv`: 1649 barrios normalizados desde `Barrios y zonas A3.xlsx`.
- `app/territory.py`: respaldo interno para que el dashboard funcione aunque Supabase aun no tenga tablas territoriales.
- `db/migrations/006_territorial_zones.sql`: migracion para crear tablas territoriales.
- `tools/scripts/apply_supabase_migration.py`: aplica la migracion con `SUPABASE_ACCESS_TOKEN`.
- `tools/scripts/seed_territory_supabase.py`: carga idempotente de zonas y barrios.
- `tools/scripts/seed_client_courier_assignments.py`: carga idempotente de asignaciones cliente -> motorizado.
- `.env`: credenciales locales del proyecto. Esta protegido por `.gitignore` y no debe subirse.

## Bloqueo actual

La `SUPABASE_SERVICE_ROLE_KEY` permite insertar/actualizar datos en tablas existentes, pero no permite crear tablas por DDL desde el entorno local.

Para aplicar `db/migrations/006_territorial_zones.sql` hace falta una de estas credenciales:

- `SUPABASE_ACCESS_TOKEN` personal de Supabase.
- `DATABASE_URL` directo de Postgres.
- Acceso manual al SQL Editor de Supabase.

## Aplicar migracion manualmente

1. Abrir Supabase Dashboard.
2. Ir a SQL Editor.
3. Pegar el contenido de `db/migrations/006_territorial_zones.sql`.
4. Ejecutar.

## Aplicar migracion automaticamente

Si se cuenta con `SUPABASE_ACCESS_TOKEN`, definirlo en `.env` y ejecutar:

```bash
python tools/scripts/apply_supabase_migration.py
```

La `SUPABASE_SERVICE_ROLE_KEY` no alcanza para este paso porque no tiene permiso de administracion SQL/DDL.

## Cargar datos despues de la migracion

Ejecutar:

```bash
python tools/scripts/seed_territory_supabase.py
```

Resultado esperado:

```text
couriers_ok=8
territorial_zones_ok=8
territorial_neighborhoods_ok=1649
```

## Recargar asignaciones cliente -> motorizado

Si se actualiza `Relacion Clientes.xlsx`, ejecutar:

```bash
python tools/scripts/seed_client_courier_assignments.py
```

## Modo operativo sin tablas territoriales

Si `territorial_zones` y `territorial_neighborhoods` aun no existen, el dashboard sigue funcionando con `data/barrios_zonas_a3.csv` y `app/territory.py` como fuente interna:

- Autocompletado de barrios.
- Localidad y zona autocompletadas.
- Motorizado sugerido por zona.
- Override manual del operador.

Esto permite operar sin pedir nuevas credenciales. La migracion a Supabase queda como mejora de persistencia centralizada, no como bloqueo funcional.

## Verificacion

Ejecutar suite completa:

```bash
python -m pytest
```

Estado esperado actual:

```text
84 passed
```

## Seguridad

Si una `SUPABASE_SERVICE_ROLE_KEY` fue compartida en chat o por un canal no seguro, rotarla desde Supabase cuando termine la carga.
