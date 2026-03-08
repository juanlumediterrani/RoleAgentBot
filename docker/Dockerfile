# ─────────────────────────────────────────────────────────────────────────────
# Imagen del bot.  Hereda la capa de dependencias ya instaladas en la base.
#
# Construir:
#   docker build --build-arg PERSONALITY=kronk \
# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile principal - Imagen completa del bot
#
# Incluye todas las dependencias necesarias para todos los roles:
# - PyNaCl para voz de Discord
# - yt-dlp y ffmpeg para música
# - Todas las librerías de requirements.txt
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# Cambiar a root para instalar paquetes
USER root

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        ffmpeg \
        libffi-dev \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python (como root para evitar permisos)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar dependencias adicionales para voz
RUN pip install PyNaCl

# Volver a usuario normal (usará root para manejar volúmenes)
USER root

# ── Argumentos de construcción (inyectables) ──────────────────────────────────
# PERSONALITY : nombre del fichero sin extensión dentro de personalities/
#               p.ej. "kronk" → personalities/kronk.json
# ACTIVE_ROLES: lista separada por comas de roles a habilitar
#               p.ej. "news_watcher,treasure_hunter,trickster,banker,mc"
#               Si está vacío se respetan los valores de agent_config.json.
ARG PERSONALITY=""
ARG ACTIVE_ROLES=""

# ── Código fuente principal ───────────────────────────────────────────────────
COPY agent_config.json .
COPY agent_db.py .
COPY agent_engine.py .
COPY agent_logging.py .
COPY run.py .

# Crear directorios necesarios con permisos correctos (como root)
RUN mkdir -p /app/logs /app/databases /app/fatiga

# Copiar resto del código
COPY discord_bot/ discord_bot/
COPY postprocessor.py .
COPY personalities/ personalities/
COPY roles/ roles/
COPY docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Variables de entorno que el entrypoint puede leer
ENV PERSONALITY=${PERSONALITY}
ENV ACTIVE_ROLES=${ACTIVE_ROLES}

# Run as root to handle volume permissions properly
# The entrypoint will switch to the correct user
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "run.py"]
