# Runbook — Cuando A3 pasa una lista actualizada de clientes

> Para usar cada vez que el laboratorio entrega un Excel o CSV de clientes: saber cuáles son
> nuevos, cuáles completan datos que nos faltan y cuáles ya no aparecen.

## Por qué existe esto

El padrón de la plataforma y las listas que maneja A3 se desincronizan: entran clientes
nuevos, algunos dejan de trabajar con el laboratorio, y a otros les falta el **NIT** —sin él
no pueden entrar al portal ni recibir factura electrónica—. Comparar a ojo 900 filas contra
900 registros no es viable, y equivocarse desactiva clientes que sí operan.

## Los tres pasos

### 1. Guardar una foto del padrón, antes de tocar nada

```bash
python tools/scripts/snapshot_clientes.py
```

Deja `data/snapshots/clientes-<fecha>.csv`. Sirve para volver atrás y para ver cómo cambió
el padrón entre entregas.

### 2. Conciliar la lista nueva contra la base

```bash
python tools/scripts/conciliar_clientes.py "Documentos de actualizacion/lista-nueva.xlsx"
python tools/scripts/conciliar_clientes.py lista.csv --hoja "Hoja1"     # si el Excel tiene varias
```

Acepta `.xlsx` y `.csv`, y reconoce las columnas por su nombre aunque cambie el encabezado
(«Nombre», «Cliente», «Veterinaria»… / «NIT», «Identificación», «Cédula»…). Cruza primero por
NIT —que es unívoco— y si no hay, por nombre, con el **mismo criterio** que usan la
identificación del agente y el login del portal (`client_name_matches`).

**No escribe nada en la base.** Deja tres archivos en `data/conciliacion-<fecha>/`:

| Archivo | Qué contiene | Qué hacer |
|---|---|---|
| `1-nuevos.csv` | Están en la lista y no en el sistema | Altas, con `/clientes/nuevo` o un import |
| `2-datos-nuevos.csv` | Ya existen y la lista completa un campo vacío | Aplicar, sobre todo los que traen **NIT** |
| `3-no-estan-en-la-lista.csv` | Activos que la lista no menciona | **Confirmar con A3 antes de desactivar** |

### 3. Leer el aviso de cobertura antes de dar de baja a nadie

El script informa qué porcentaje del padrón cubre la lista. **Si cubre menos del 60%, avisa
que la lista parece parcial** y que el grupo 3 no son bajas.

Ejemplo real (27/08): el Excel de terceros de Alegra cubría el **32%** —son solo los
contactos facturables— y dejaba 570 activos «fuera de la lista». Ninguno era una baja. La
lista de «Clientes y Doctores» cubría el **74%** y ahí sí tiene sentido revisar ausencias.

## Lo que ya sabemos del padrón (27/08/2026)

- **992 clientes**, 842 activos, **165 sin NIT** (161 de ellos activos).
- **154 de los que no tienen NIT entraron el 22/07** desde «Clientes y Doctores A3.xlsx», que
  solo traía nombre y médico: por eso les falta NIT, dirección y teléfono real. Los teléfonos
  con forma `5700000xxxxx` son de relleno, no sirven para llamar.
- La planilla para que A3 complete esos NIT se genera con
  `python tools/scripts/pdf_clientes_sin_nit.py` → `data/veterinarias-sin-nit.pdf`.
- **36 NIT están compartidos por 77 clientes**: son sedes de la misma empresa, no duplicados
  (ERR-157). El portal las maneja pidiendo elegir sede al entrar.

## Después de aplicar cambios

1. Volver a correr `snapshot_clientes.py` para dejar la foto nueva.
2. Si se completaron NIT, regenerar el PDF de faltantes.
3. Registrar en `tasks/todo.md` qué se aplicó y con qué lista.
