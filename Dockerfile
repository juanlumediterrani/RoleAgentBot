# ─────────────────────────────────────────────────────────────────────────────
# Imagen del bot.  Hereda la capa de dependencias ya instaladas en la base.
#
# Construir:
#   docker build --build-arg PERSONALITY=kronk \
#                --build-arg ACTIVE_ROLES="vigia_noticias,buscar_anillo" \
#                -t roleagentbot:latest .
#
# Si no se pasan argumentos se usa la personalidad y los roles definidos en
# agent_config.json tal cual está en el repositorio.
# ─────────────────────────────────────────────────────────────────────────────
FROM roleagentbot-base:latest

WORKDIR /app

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
COPY postprocessor.py .
COPY fatiga.json .
COPY run.py .

# ── Personalidades y roles (todos se copian; el script de entrypoint filtra) ──
COPY personalities/ personalities/
COPY roles/ roles/

# ── Script que aplica los ARG al agent_config.json en tiempo de arranque ──────
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# ── Directorios con estado persistente (montados como volúmenes) ──────────────
RUN mkdir -p databases logs

# Variables de entorno que el entrypoint puede leer
ENV PERSONALITY=${PERSONALITY}
ENV ACTIVE_ROLES=${ACTIVE_ROLES}

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "run.py"]
