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

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar dependencias adicionales para voz
RUN pip install PyNaCl

# ── Argumentos de construcción (inyectables) ──────────────────────────────────
# PERSONALITY : nombre del fichero sin extensión dentro de personalities/
#               p.ej. "kronk" → personalities/kronk.json
# ACTIVE_ROLES: lista separada por comas de roles a habilitar
#               p.ej. "vigia_noticias,buscar_anillo"
#               Si está vacío se respetan los valores de agent_config.json.
ARG PERSONALITY=""
ARG ACTIVE_ROLES=""

# ── Código fuente principal ───────────────────────────────────────────────────
COPY agent_config.json .
COPY agent_db.py .
COPY agent_discord.py .
COPY agent_engine.py .
COPY agent_logging.py .
COPY discord_http.py .
COPY postprocessor.py .
COPY run.py .

# ── Personalidades y roles (todos se copian; el script de entrypoint filtra) ──
COPY personalities/ personalities/
COPY roles/ roles/

# ── Script que aplica los ARG al agent_config.json en tiempo de arranque ──────
COPY docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# ── Directorios con estado persistente (montados como volúmenes) ──────────────
RUN mkdir -p databases logs

# Variables de entorno que el entrypoint puede leer
ENV PERSONALITY=${PERSONALITY}
ENV ACTIVE_ROLES=${ACTIVE_ROLES}

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "run.py"]
