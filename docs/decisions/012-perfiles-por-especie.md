# 012 — Perfiles y análisis por especie: lista negra, no lista blanca

- **Estado:** PROPUESTO (2026-08-12) — pendiente de OK del usuario
- **Origen:** reunión 8 (28/07) y aclaración del usuario del 2026-08-12

## Problema

El sistema hoy asume lo contrario de lo que es cierto en el laboratorio.

**Cómo funciona hoy** (`app/services/db.py:892-911` y otros tres sitios): cada perfil tiene
una columna `species` (`'canino' | 'felino' | 'ambos'`, default `'ambos'`), y al listar se
filtra `species IN (especie_del_paciente, 'ambos')`. Es una **lista blanca**: un perfil solo
aparece si su especie coincide.

Eso tiene dos defectos:

1. **Excluye perfiles que sí sirven.** El usuario dio el caso real: paciente **gato**, y el
   cliente pidió un perfil catalogado como **de perro**; en el laboratorio se procesó sin
   problema. Con el filtro actual ese perfil ni siquiera se le habría ofrecido.
2. **Es inconsistente:** el filtro solo se aplica cuando la especie es canino o felino. Para
   bovino, equino, porcino y las demás **no filtra nada**, así que ya hoy se ofrecen todos.

La realidad del negocio, según A3: **son pocos los análisis realmente exclusivos de una
especie; la gran mayoría sirve para varias.**

## Decisión

Invertir el criterio: **todos los perfiles y análisis están disponibles para cualquier
especie, salvo los que estén explícitamente etiquetados como exclusivos.**

### Datos

La columna `species` de `catalog_profiles` / `catalog_tests` pasa a interpretarse como
**restricción opcional**, no como pertenencia:

- vacío / `'ambos'` → disponible para **todas** las especies (caso por defecto y mayoritario)
- `'canino'`, `'felino'`, … → **exclusivo** de esa especie

El cambio de significado no requiere migración de esquema: `'ambos'` ya es el default y
seguirá significando "todas". Sí hay que **revisar los 73 perfiles hoy marcados con una
especie concreta** y dejar la etiqueta solo en los que de verdad son exclusivos — esa
reclasificación la tiene que hacer A3, es una de las cinco definiciones abiertas del acta.

### Código

Los cuatro sitios que filtran por especie (`db.py:619`, `:630`, `:892`, `:946`) pasan de
"incluir solo lo que coincide" a "excluir solo lo etiquetado para otra especie":

```
-- hoy (lista blanca)
WHERE species IN (:especie, 'ambos')
-- propuesto (lista negra)
WHERE species IS NULL OR species = 'ambos' OR species = :especie
```

La diferencia práctica: un perfil marcado `'canino'` **deja de ofrecerse** para un felino
(sigue siendo exclusivo), pero un perfil sin etiqueta se ofrece siempre — hoy también, así
que el caso mayoritario no cambia. Lo que cambia es que la etiqueta pase a ser deliberada.

### Plataforma

Hace falta poder **administrar la etiqueta desde el dashboard**, que hoy no existe: el
catálogo es de solo lectura (no hay ningún endpoint que escriba en `catalog_profiles` /
`catalog_tests`). Es un CRUD chico: listar el catálogo y poder marcar/desmarcar la
exclusividad de especie de cada perfil o análisis.

## Consecuencia sobre el flujo conversacional

Se ofrecerán más perfiles por especie que hoy. El menú de recomendación
(`list_catalog_profiles_for_species`, limitado a 6) va a tener más candidatos, así que el
criterio de orden pasa a importar más que antes. Conviene revisarlo en la misma tanda.

**No cambia** el resolvedor por código ni por nombre: si el cliente pide un perfil concreto,
se le da (ya funciona así hoy — de hecho es lo que permitió el caso del gato).

## Riesgo

El único real es de **producto, no técnico**: si A3 no reclasifica los 73 perfiles, la
inversión del filtro los deja igual de restringidos que hoy. El cambio de código sin la
reclasificación no se nota. Por eso conviene entregar el CRUD junto con el cambio de lógica,
para que A3 pueda hacer la limpieza sin depender de nosotros.
