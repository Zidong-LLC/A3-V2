# Runtime del servicio en Render.
#
# Se usa Docker y no el runtime nativo de Python por una razón concreta: publicar un
# informe al portal necesita Chromium, y en el runtime nativo no se es root, así que
# `apt-get` no existe. Ahí `playwright install chromium` deja el build en verde y el
# proceso revienta en el primer request real por una librería del sistema faltante
# (libnss3). Esta imagen ya trae Chromium y todas sus dependencias: convierte una familia
# entera de fallos de producción en un problema de build.
#
# El tag DEBE coincidir con la versión de playwright de requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# --timeout 60: el default de gunicorn son 30 s y mataría al worker a mitad de un render,
# dejando un Chromium huérfano comiéndose la memoria de la instancia.
# Workers sync/gthread, nunca gevent: Playwright no convive con un event loop parcheado.
# UN solo worker, a propósito: el buffer anti-ráfagas del bot (MessageDebouncer) vive en
# memoria del proceso — con 2 workers, dos mensajes seguidos del mismo chat caen en
# procesos distintos y se procesan por separado (ERR-176). Los turnos del agente corren
# en threads propios (no ocupan estos 8), así que 8 threads alcanzan para la web.
CMD gunicorn app.main:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 60
