# 006 — Identificación de cliente por nombre o NIT

## Estado

Aprobada (2026-05-29)

## Contexto

Los clientes en A3 son veterinarias, clínicas veterinarias o médicos veterinarios
independientes registrados en la tabla `clients`.

Durante pruebas, el agente podía pedir teléfono para validar identidad o avanzar con
un cliente ambiguo. Esto generaba riesgo de asociar una orden a una sede o cliente
equivocado.

## Decisión

La identificación conversacional del cliente se hace solo con:

- NIT
- Nombre de la veterinaria, clínica o médico veterinario registrado

El teléfono no se usa para identificar ni verificar clientes durante el paso de
identificación. Si se solicita teléfono más adelante, es solo como contacto de la
orden de servicio.

Cuando una búsqueda por nombre devuelve varias coincidencias, el agente muestra
hasta 5 opciones numeradas y espera selección del usuario. Si hay demasiadas
coincidencias, pide una palabra más específica, el nombre exacto o el NIT.

## Consecuencias

- El agente no debe escoger automáticamente la primera coincidencia por nombre.
- El agente no debe avanzar a datos del paciente sin cliente real identificado.
- No se modifica el esquema de Supabase.
