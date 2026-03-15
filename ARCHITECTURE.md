# RoleAgentBot — Architecture Reference
THE COMMANDS ARE REGISTERED DINAMICLY
## 1. System Overview

```
run.py (orchestrator)
├── agent_discord.py (main Discord bot — persistent subprocess)
│   ├── discord_core_commands.py  → core commands (help, greet, insult, test, role toggle)
│   ├── discord_role_loader.py   → dynamic command registration per role
│   └── discord_utils.py         → shared utilities (DB, permissions, send helpers)
│
├── roles/news_watcher/news_watcher.py      → scheduled task (subprocess, every 1h)
├── roles/treasure_hunter/treasure_hunter.py → scheduled task (subprocess, every 1h)
├── roles/trickster/trickster.py             → scheduled task (subprocess, every 12h)
│   └── subroles: beggar, dice_game, ring
├── roles/banker/banker.py                   → scheduled task (subprocess, every 24h)
└── roles/mc/                                → integrated mode (no subprocess)
```

## 2. Two Execution Modes Per Role

| Layer | Purpose | Runs as | File |
|-------|---------|---------|------|
| **Task** | Scheduled background work (scraping, begging, announcements) | Subprocess via `run.py` | `roles/<role>/<role>.py` |
| **Discord** | User-facing commands registered on the main bot | Integrated in `agent_discord.py` | `roles/<role>/<role>_discord.py` |

**Key principle:** Task scripts run in isolation as subprocesses. Discord command files are imported into the main bot process.

## 3. Command Registration Flow

```
agent_discord.py::on_ready()
  │
  ├─ 1. register_core_commands(bot, agent_config)
  │     → !agenthelp, !greet<name>, !nogreet<name>, !welcome<name>,
  │       !nowelcome<name>, !insult<name>, !role<name>, !test
  │
  └─ 2. register_all_role_commands(bot, agent_config, personality)
        │
        ├─ MC (always first, integrated mode)
        │  → !mc group: play, skip, stop, pause, resume, volume,
        │    nowplaying, np, history, leave, disconnect, queue, clear, add, help, commands
        │
        ├─ news_watcher (if enabled)
        │  → !watcher, !nowatcher, !watchernotify, !nowatchernotify,
        │    !watcherhelp, !watcherchannelhelp, !watcherchannel group
        │  → legacy: !vigia, !novigia, !vigiaayuda (deprecated redirects)
        │
        ├─ treasure_hunter (if enabled)
        │  → !hunter, !nohunter, !hunterpoe2, !hunteradd, !hunterdel,
        │    !hunterlist, !hunterhelp, !hunterfrequency
        │  → legacy: !buscartesoros, !poe2ayuda (deprecated redirects)
        │
        ├─ trickster (if enabled)
        │  → !trickster group: beggar (enable/disable/frequency/status/help),
        │    ring (enable/disable/frequency/help), help
        │  → !dice group: play, help, balance, stats, ranking, history, config
        │  → !accuse @user
        │  → legacy: !trilero, !bote, !acusaranillo (deprecated redirects)
        │
        └─ banker (if enabled)
           → !banker group: balance, tae, bonus, help
           → legacy: !banquero (deprecated redirect)
```

## 4. Canonical Role Names (English only)

| Config key | Task script | Discord commands | Legacy Spanish |
|------------|-------------|------------------|----------------|
| `news_watcher` | `roles/news_watcher/news_watcher.py` | `news_watcher_discord.py` | `vigia_noticias` |
| `treasure_hunter` | `roles/treasure_hunter/treasure_hunter.py` | `treasure_hunter_discord.py` | `buscador_tesoros` |
| `trickster` | `roles/trickster/trickster.py` | `trickster_discord.py` | `trilero` |
| `banker` | `roles/banker/banker.py` | `banker_discord.py` | `banquero` |
| `mc` | (integrated, no task script) | `mc_discord.py` | — |

Legacy Spanish names remain **only** as deprecated command aliases that redirect users.

## 5. Personality Injection Pattern

```
Code & developer help → English (universal)
User-facing messages  → Injected from personality JSON (any language)
Fallback messages     → English neutral defaults
```

### How it works:
```python
# In *_discord.py files — personality is passed as parameter
def register_banker_commands(bot, personality, agent_config):
    msgs = personality.get("discord", {}).get("banker_messages", {})
    title = msgs.get("help_title", "💰 Banker - Help")  # English fallback
```

### Personality JSON structure (split files):

**personality.json** - Core personality settings:
```json
{
  "name": "putre",
  "identity": "Eres PUTRE, un guerrero orko...",
  "format_rules": { "length": "2-3 frases..." },
  "orthography": ["que→ke | quien→kien..."],
  "style": ["Onomatopeyas guturales..."]
}
```

**prompts.json** - System prompts and role configurations:
```json
{
  "prompt_chat": { "context_prefix": "KONTEXTO" },
  "role_system_prompts": {
    "banker": "MISION ACTIVO - BANQUERO...",
    "news_watcher": "MISION ACTIVO - VIGÍA..."
  }
}
```

**answers.json / descriptions.json** - User-facing responses and descriptions:
```json
{
  "discord": {
    "banker_messages": { "help_title": "💰 El Banquero - Ayuda" },
    "mc_messages": { "presence_status": "🎵 ¡MC disponible!" },
    "role_messages": { "admin_permission": "❌ Solo jefes orcos..." }
  },
  "role_system_prompts": {
    "trickster": "MISION ACTIVA - TRILERO: ...",
    "banker": "MISION ACTIVA - BANQUERO: ..."
  }
}
```

## 6. File Responsibilities

| File | Responsibility |
|------|---------------|
| `run.py` | Orchestrator: launches bot + schedules role tasks |
| `agent_discord.py` | Discord bot: events, message handling, task loops |
| `agent_engine.py` | AI engine: LLM calls, personality loading, config |
| `agent_db.py` | Global database: interactions, server management |
| `agent_logging.py` | Logging setup per server/personality |
| `discord_utils.py` | Shared helpers: permissions, DB access, rate limiting |
| `discord_core_commands.py` | Core commands: help, greet, insult, test, role toggle |
| `discord_role_loader.py` | Dynamic role command registration |
| `discord_http.py` | Raw Discord HTTP API client (for task scripts) |
| `postprocessor.py` | AI response post-processing |

## 7. Directory Structure

```
RoleAgentBot/
├── __init__.py
├── run.py                      # Orchestrator
├── agent_discord.py            # Main Discord bot
├── agent_engine.py             # AI engine
├── agent_db.py                 # Global database
├── agent_config.json           # Role configuration
├── discord_core_commands.py    # Core commands
├── discord_role_loader.py      # Role command loader
├── discord_utils.py            # Shared utilities
├── discord_http.py             # HTTP API client
├── postprocessor.py            # Response post-processing
├── agent_logging.py            # Logging
│
├── personalities/
│   ├── putre/                  # Personality: Putre (Spanish)
│   │   ├── personality.json    # Core personality settings
│   │   ├── prompts.json        # System prompts & roles
│   │   ├── answers.json        # Discord answers and operational messages
│   │   └── descriptions.json   # Canvas and UI descriptions
│   └── kronk/                  # Personality: Kronk (Spanish)
│       ├── personality.json    # Core personality settings
│       ├── prompts.json        # System prompts & roles
│       ├── answers.json        # Discord answers and operational messages
│       └── descriptions.json   # Canvas and UI descriptions
│
└── roles/
    ├── __init__.py
    ├── news_watcher/
    │   ├── __init__.py
    │   ├── news_watcher.py          # Task script
    │   ├── news_watcher_discord.py  # Discord commands
    │   ├── watcher_commands.py      # Command logic
    │   ├── watcher_messages.py      # Message templates
    │   ├── premises_manager.py      # Premises management
    │   └── db_role_news_watcher.py  # Database layer
    │
    ├── treasure_hunter/
    │   ├── __init__.py
    │   ├── treasure_hunter.py            # Task script
    │   ├── treasure_hunter_discord.py    # Discord commands
    │   ├── buscador_tesoros.py           # Search logic
    │   ├── poe2/                         # POE2 subrole
    │   │   ├── __init__.py
    │   │   ├── db_role_poe.py
    │   │   └── poe2_subrole.py
    │   
    │
    ├── trickster/
    │   ├── __init__.py
    │   ├── trickster.py                 # Task script
    │   ├── trickster_discord.py         # Discord commands (652 lines)
    │   └── subroles/
    │       ├── __init__.py
    │       ├── beggar/
    │       │   ├── __init__.py
    │       │   ├── db_beggar.py
   │# Beggar task logic
    │       ├── dice_game/
    │       │   ├── __init__.py
    │       │   ├── db_dice_game.py
    │       │   ├── dice_game.py         # Dice game logic
   # Pot management task
    │       └── ring/
    │           ├── __init__.py
    │           ├── ring_discord.py      # Ring commands

    │
    ├── banker/
    │   ├── __init__.py
    │   ├── banker.py                    # Task script
    │   ├── banker_discord.py            # Discord commands
    │   └── db_role_banker.py            # Database layer
    │
    └── mc/
        ├── __init__.py
        ├── mc.py                        # Task script (maintenance only)
        ├── mc_discord.py                # Discord commands
        ├── mc_commands.py               # Command implementations
        └── db_role_mc.py                # Database layer
```

## 8. Architecture Status - ✅ **COMPLETE**

All major refactoring tasks have been completed:

### ✅ **Completed Items**
1. **English Localization**: All Spanish comments, variables, and fallback messages translated to English
2. **Clean Role Registry**: `ROLE_REGISTRY` uses only English canonical names
3. **Proper Imports**: `trickster.py` uses `importlib.util` instead of `sys.path` hacks
4. **Standalone Scripts**: `banker.py` and `mc.py` contain only task logic (no Discord client setup)
5. **Complete Structure**: All required `__init__.py` files present in subrole directories
6. **Configuration Verified**: Personality path matches active configuration

### 🏗️ **Current Architecture**
- **Integrated Bot**: Single Discord client in `agent_discord.py` with dynamic role loading
- **Task Scripts**: Standalone role scripts (`*_discord.py`) handle background tasks via scheduler
- **Clean Separation**: Discord commands vs task logic properly separated
- **Docker Ready**: Containerized deployment with `docker-compose.dev.yml`

### 🎯 **Key Features**
- **Dynamic Role Loading**: Roles can be enabled/disabled without restart
- **Multi-Personality Support**: Different bot personalities from JSON config
- **Per-Server Databases**: Isolated data per Discord server
- **Rate Limiting & Security**: Proper bot security measures implemented
- **Comprehensive Logging**: Structured logging with server-specific files
- **Robust UI Interaction Handling**: Canvas UI components gracefully handle Discord interaction errors

### 🔧 **Recent Fixes (2026-03-15)**
- **Discord UI Error Handling**: Fixed interaction failures in Canvas UI components
  - Added comprehensive exception handling for `interaction.response.edit_message()`
  - Handles `InteractionResponded`, `NotFound`, and other Discord exceptions
  - Provides fallback to `interaction.followup` when primary interaction fails
  - Applied to all Canvas role handlers: news_watcher, trickster, treasure_hunter, MC
  - Users now see helpful error messages instead of raw exceptions







---

**The RoleAgentBot architecture refactor is complete and production-ready.**

