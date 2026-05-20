# 004 — Estrategia de ejecución de procesos en OpenCode (Windows)

## Contexto

En sesiones de troubleshooting local (Flask + ngrok), ejecutar procesos detached con `Start-Process` produjo fallos intermitentes del runner (`ChildProcess.kill`) y estados difíciles de verificar.

## Decisión

Para trabajo operativo en OpenCode sobre Windows:

- Evitar procesos en segundo plano persistentes cuando sea posible.
- Preferir comandos/scrips de ejecución controlada que hagan: inicio, verificación y cierre limpio.
- Si se requiere proceso prolongado, validar primero disponibilidad por endpoint y luego continuar con pasos dependientes.

## Consecuencias

- Menos bloqueos del runner y menos sesiones "trabadas".
- Logs más consistentes para diagnóstico.
- Flujo más predecible para validar integraciones (Telegram/Chatwoot/ngrok).
