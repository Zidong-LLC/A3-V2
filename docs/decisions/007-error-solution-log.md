# 007 — Bitacora viva de errores conversacionales

## Estado

Aprobada (2026-06-12)

## Contexto

El agente conversacional ha acumulado guardrails, correcciones de bucles y cambios de comportamiento que viven repartidos entre `tasks/todo.md`, `tasks/lessons.md`, tests y codigo. Eso dificulta saber que errores siguen abiertos, cuales ya se corrigieron y que decision falta tomar.

## Decision

La fuente operativa para bugs y soluciones conversacionales sera:

```text
tasks/errores-soluciones.md
```

Cada bug conversacional debe registrar:

- flujo afectado
- sintoma observado
- causa raiz
- solucion propuesta o aplicada
- archivos afectados
- tests agregados o justificacion de ausencia de test
- estado

El bloque `Indice automatico` se refresca con:

```bash
python tools/scripts/refresh_error_report.py
```

El script solo actualiza el bloque marcado como autogenerado. Las secciones manuales del documento se editan directamente cuando se analiza o corrige un bug.

## Consecuencias

- El equipo tiene una lista unica de errores abiertos y corregidos.
- Las lecciones historicas siguen en `tasks/lessons.md`, pero quedan enlazadas desde el reporte.
- No se considera cerrado un bug conversacional si no se actualizo esta bitacora.
