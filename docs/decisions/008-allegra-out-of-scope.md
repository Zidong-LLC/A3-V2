# 008 — Allegra fuera de alcance por ahora

Fecha: 2026-06-13

> **⚠️ SUPERADO por [009 — Alegra: integración por fases](009-alegra-integracion-por-fases.md).**
> Alegra sí entra en alcance mediante una integración por fases (solo borradores en
> cuenta de pruebas). Esta decisión se conserva como historial; no aplicar.

## Decisión

Allegra no está integrado todavía y no debe formar parte del camino activo de
tests, scripts ni tareas pendientes del agente por ahora.

## Consecuencia

- Se eliminan los scripts de importación/validación de clientes Allegra.
- Se eliminan los tests E2E que dependían de un Excel externo local.
- La suite `pytest` debe validar solo funcionalidades actuales del agente,
  dashboard, plataforma y Supabase.

## Reversión futura

Cuando exista una especificación real de integración, se debe reintroducir como
un módulo nuevo con datos de prueba versionados dentro del repo, no apuntando a
rutas locales externas.
