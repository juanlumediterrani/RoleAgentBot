#!/bin/sh
# ─────────────────────────────────────────────────────────────────────────────
# docker-entrypoint.sh
#
# Apply build/environment injectables to agent_config.json
# before starting the bot.
#
# Environment variables read:
#   PERSONALITY   - name of personality JSON (without extension or path)
#                   e.g. "kronk"  →  personalities/kronk.json
#   ACTIVE_ROLES  - comma-separated list of roles to enable
#                   e.g. "news_watcher,treasure_hunter,trickster,banker,mc"
#                   Roles NOT included are automatically disabled.
#                   If variable is empty, config is left as-is.
# ─────────────────────────────────────────────────────────────────────────────
set -e

# ── 0. No permission fixing needed ────────────────────────────────────────

# ── Now running as target user (or already running as correct user) ──────────────
CONFIG="agent_config.json"

# ── 1. Apply personality ───────────────────────────────────────────────────
if [ -n "${PERSONALITY}" ]; then
    # Try split structure first: personalities/putre/personality.json
    PERSONALITY_PATH_SPLIT="personalities/${PERSONALITY}/personality.json"
    # Fallback to legacy: personalities/putre.json
    PERSONALITY_PATH_LEGACY="personalities/${PERSONALITY}.json"
    
    # Special handling for personalities with parentheses (e.g., putre(english))
    case "${PERSONALITY}" in
        *"("*)
            # For names with parentheses, use them directly as directory names
            PERSONALITY_PATH_SPLIT="personalities/${PERSONALITY}/personality.json"
            # No legacy fallback for parenthesized names
            PERSONALITY_PATH_LEGACY=""
            ;;
    esac
    
    if [ -f "${PERSONALITY_PATH_SPLIT}" ]; then
        PERSONALITY_PATH="${PERSONALITY_PATH_SPLIT}"
    elif [ -n "${PERSONALITY_PATH_LEGACY}" ] && [ -f "${PERSONALITY_PATH_LEGACY}" ]; then
        PERSONALITY_PATH="${PERSONALITY_PATH_LEGACY}"
    else
        if [ -n "${PERSONALITY_PATH_LEGACY}" ]; then
            echo "ERROR: Personality not found '${PERSONALITY_PATH_SPLIT}' nor '${PERSONALITY_PATH_LEGACY}'" >&2
        else
            echo "ERROR: Personality not found '${PERSONALITY_PATH_SPLIT}'" >&2
        fi
        exit 1
    fi
    
    python3 - <<PYEOF
import json, sys
with open("${CONFIG}", encoding="utf-8") as f:
    cfg = json.load(f)
cfg["personality"] = "${PERSONALITY_PATH}"
with open("${CONFIG}", "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print(f"[entrypoint] Personality → ${PERSONALITY_PATH}")
PYEOF
fi

# ── 2. Apply active roles ──────────────────────────────────────────────────
if [ -n "${ACTIVE_ROLES}" ]; then
    python3 - <<PYEOF
import json, os, sys

active = [r.strip() for r in "${ACTIVE_ROLES}".split(",") if r.strip()]

with open("${CONFIG}", encoding="utf-8") as f:
    cfg = json.load(f)

for role_name, role_cfg in cfg.get("roles", {}).items():
    enabled = role_name in active
    role_cfg["enabled"] = enabled
    state = "✅ active" if enabled else "💤 disabled"
    print(f"[entrypoint] Rol '{role_name}' → {state}")

with open("${CONFIG}", "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
PYEOF
fi

exec "$@"
