# Plantilla de WhatsApp para el aviso al motorizado

Informe de A3 del 25/11 (punto 6, brecha B1): el aviso al mensajero tiene que ser automático.
WhatsApp solo deja escribirle a alguien que escribió en las últimas 24 h; fuera de esa ventana
hace falta una **plantilla aprobada por Meta**. La plataforma ya está lista: apenas Chatwoot
tenga la plantilla APROBADA, los avisos empiezan a salir solos (no hay que tocar nada más).

## Lo que tiene que hacer A3 (dueña de la cuenta de WhatsApp Business)

1. Entrar al **WhatsApp Manager** de Meta (business.facebook.com → WhatsApp Manager →
   Administrar plantillas) → **Crear plantilla**.
2. Datos exactos (el nombre tiene que ser este, en minúsculas y con guion bajo):
   - **Categoría:** Utilidad
   - **Nombre:** `recogida_asignada`
   - **Idioma:** Español
   - **Cuerpo:**

     ```
     🛵 Nueva recogida asignada
     Orden: {{1}}
     Veterinaria: {{2}}
     Dirección: {{3}}
     Fecha de recogida: {{4}}
     Escríbenos por acá para ver todas tus recogidas del día.
     ```
   - Ejemplos que pide Meta: `A3-2026-040`, `Laboratorio Clínico Veterinario Lacliv`,
     `CR 2 8-56`, `27/11/2026`.
3. Enviar a revisión. Meta suele aprobar las de Utilidad en minutos u horas.
4. En Chatwoot: Configuración → Bandejas → A3 WhatsApp → sincronizar plantillas (si no
   aparece sola).

## Cómo funciona

- Motorizado que escribió en las últimas 24 h → mensaje normal (no usa la plantilla).
- Ventana cerrada → la plantilla, en su conversación.
- Motorizado sin conversación → se abre una con el celular de su tarjeta y queda vinculada.
- Sin plantilla aprobada → como antes (solo a quien tiene la ventana abierta).

Código: `app/courier_notify.py`, `app/services/chatwoot_plantillas.py`.

## Costo

Meta cobra los mensajes con plantilla (los de Utilidad, de bajo valor por mensaje). La tarifa
vigente la ve A3 en su WhatsApp Manager → Información de pago. Dentro de la ventana de 24 h el
aviso sale como mensaje normal.
