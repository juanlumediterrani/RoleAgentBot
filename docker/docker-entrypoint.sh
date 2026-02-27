#!/bin/sh
# ─────────────────────────────────────────────────────────────────────────────
# docker-entrypoint.sh
#
# Aplica los inyectables de construcción/entorno sobre agent_config.json
# antes de arrancar el bot.
#
# Variables de entorno leídas:
#   PERSONALITY   - nombre del JSON de personalidad (sin extensión ni ruta)
#                   p.ej. "kronk"  →  personalities/kronk.json
#   ACTIVE_ROLES  - lista separada por comas de roles a habilitar
#                   p.ej. "vigia_noticias,buscar_anillo"
#                   Los roles NO incluidos se deshabilitan automáticamente.
#                   Si la variable está vacía se deja el config tal cual.
# ─────────────────────────────────────────────────────────────────────────────
set -e

CONFIG="agent_config.json"

# ── 1. Aplicar personalidad ───────────────────────────────────────────────────
if [ -n "${PERSONALITY}" ]; then
    PERSONALITY_PATH="personalities/${PERSONALITY}.json"
    if [ ! -f "${PERSONALITY_PATH}" ]; then
        echo "ERROR: No se encontró la personalidad '${PERSONALITY_PATH}'" >&2
        exit 1
    fi
    python3 - <<PYEOF
import json, sys
with open("${CONFIG}", encoding="utf-8") as f:
    cfg = json.load(f)
cfg["personality"] = "${PERSONALITY_PATH}"
with open("${CONFIG}", "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print(f"[entrypoint] Personalidad → ${PERSONALITY_PATH}")
PYEOF
fi

# ── 2. Aplicar roles activos ──────────────────────────────────────────────────
if [ -n "${ACTIVE_ROLES}" ]; then
    python3 - <<PYEOF
import json, os, sys

active = [r.strip() for r in "${ACTIVE_ROLES}".split(",") if r.strip()]

with open("${CONFIG}", encoding="utf-8") as f:
    cfg = json.load(f)

for role_name, role_cfg in cfg.get("roles", {}).items():
    enabled = role_name in active
    role_cfg["enabled"] = enabled
    state = "✅ activo" if enabled else "💤 desactivado"
    print(f"[entrypoint] Rol '{role_name}' → {state}")

with open("${CONFIG}", "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
PYEOF
fi

exec "$@"
