# RoleAgentBot — Current Architecture

## 1. Purpose

RoleAgentBot is a personality-driven Discord agent with:

- **A single main Discord bot process**
- **Optional scheduled role and behavior processes**
- **Per-server persistence**
- **LLM-backed chat, greetings, memory synthesis, and role logic**
- **Dyncamically prompt building**

The command system is **registered dynamically** from configuration and available role modules.

## 2. Runtime Topology

```text
run.py
├── discord_bot()                          → keeps the main Discord bot alive
│   └── discord_bot/agent_discord.py
│       ├── discord_core_commands.py       → core commands and runtime controls
│       ├── discord_role_loader.py         → dynamic role command registration
│       ├── discord_utils.py               → shared Discord/runtime helpers

│
└── scheduler()                            → periodic background execution
    ├── role subprocesses                  → news_watcher, treasure_hunter, trickster, banker
    ├── subrole internal tasks             → beggar, ring
    └── memory maintenance    
    └── behavior/
        ├── greet.py                   → presence greetings
        └── welcome.py                 → member welcome messages
```

## 3. Core Execution Model

There are **two runtime layers**:

| Layer | Responsibility | Execution mode |
|------|------|------|
| `Main bot` | Discord connection, commands, events, chat, greetings, MC voice features | Persistent process |
| `Scheduler` | Launches optional role scripts and memory refresh tasks | Loop in `run.py` |

There are also **two role integration modes**:

| Mode | What it means | Examples |
|------|------|------|
| `Integrated Discord role` | Commands run inside the main bot process | `mc`, all `*_discord.py` command modules |
| `Scheduled role task` | Autonomous logic runs on a timer | `news_watcher.py`, `treasure_hunter.py`, `trickster.py`, `banker.py` |

## 4. Main Entry Points

### `run.py`

System orchestrator:

- Loads `agent_config.json`
- Starts the main Discord bot subprocess
- Builds the schedule for enabled roles
- Executes due role tasks
- Executes due internal subrole tasks
- Refreshes memory layers on their own cadence

### `discord_bot/agent_discord.py`

Main Discord runtime:

- Creates the Discord client with limited intents
- Loads core commands
- Dynamically loads enabled role commands
- Selects and persists the active server
- Starts automatic Discord-side loops
- Handles events, messages, mentions, greetings, and MC voice lifecycle

### `agent_engine.py`

LLM and prompt orchestration:

- Loads `agent_config.json`
- Loads the active personality from split JSON files
- Builds system prompts and contextual prompt additions
- Executes `think(...)`
- Generates daily, recent, and relationship memories
- Executes internal subrole prompts for autonomous behaviors

## 5. Configuration Model

### `agent_config.json`

Defines:

- Active personality
- Platform
- Enabled roles
- Role intervals
- Role scripts
- Trickster subrole settings
- MC mode and voice features

Current configured roles:

- `news_watcher`
- `treasure_hunter`
- `trickster`
- `mc`
- `banker`

### Personality files

The active personality is loaded from `personalities/<name>/`:

- `personality.json` → identity and style
- `prompts.json` → system prompts and role/subrole prompt content
- `answers.json` → Discord-facing text from the personality
- `descriptions.json` → UI/description strings

## 6. Discord Command Architecture

Command registration happens once during `on_ready()`:

1. `register_core_commands(bot, agent_config)`
2. `register_all_role_commands(bot, agent_config, PERSONALIDAD)`

### Core command layer

`discord_core_commands.py` contains the shared operational commands, including:

- Help and discovery
- Greeting toggles
- Insult/test utilities
- Role enable/disable controls
- Runtime state helpers for taboo and talk systems
- **Bot identity management (`!setpersonality`, `!setnickname`, `!identity`)**

#### Bot Identity Management

The bot supports complete server-specific identity (nickname + avatar) based on personality configuration:

**Commands:**
- `!setpersonality <name>` - Change server personality with automatic identity sync (admin only)
- `!setnickname <name>` - Manually set bot nickname (admin only)
- `!identity` - Show current identity configuration (nickname + avatar status)

**Automatic sync on personality change:**
During `initialize_server_complete()` or `!setpersonality`, the bot:
1. Reads `bot_display_name` from `databases/<server_id>/<personality>/personality.json`
2. Searches for avatar image (`avatar.webp` or `avatar.png`) in the same directory
3. Updates both nickname and avatar in a **single API call** to minimize rate limit risk

**API Used:**
```
PATCH /guilds/{guild.id}/members/@me
Body: {"nick": "Name", "avatar": "base64_image_data"}
```

**Requirements:**
- Bot needs "Change Nickname" permission
- Avatar formats supported: WebP, PNG (1024x1024px max, < 2MB recommended)
- Identity changes are local to each guild (multitenant)
- Falls back gracefully if permissions are missing

### Dynamic role command layer

`discord_role_loader.py` registers commands for enabled roles using `ROLE_REGISTRY`.

Current canonical role registry:

- `news_watcher`
- `treasure_hunter`
- `trickster`
- `banker`

`mc` is registered separately and always attempted first.

## 7. Event and Message Flow

### Startup flow

```text
run.py
→ starts discord_bot/agent_discord.py
→ bot connects to Discord
→ on_ready()
→ register core commands
→ register enabled role commands
→ choose active guild
→ publish active server for DB/log usage
→ start automatic loops
```

### Chat flow

```text
Discord message
→ on_message()
→ if command prefix: process command
→ else if taboo trigger: generate taboo response
→ else if DM or mention: _process_chat_message()
→ think(...)
→ store interaction in AgentDatabase
→ send response
```

### Greeting flow

Presence and join behaviors are separated into `behavior/`:

- `behavior/welcome.py` handles member join greetings
- `behavior/greet.py` handles offline → online presence greetings

Both use:

- Persisted greeting state
- Personality prompt generation through `think(...)`
- Interaction logging in the server database

## 8. Persistence Model

### Server scoping

The system is server-aware. The active server is published through:

- `.active_server`
- `ACTIVE_SERVER_NAME` environment propagation

This affects:

- Database path selection
- Log path selection
- Memory summaries
- Role task context

### `agent_db.py`

Primary SQLite runtime storage. It persists:

- Interaction history
- Recent dialogue windows
- Daily memory
- Recent memory
- User relationship memory
- Daily user relationship snapshots
- Pending relationship refresh state
- Notable memories

The database is isolated per server, with fallback relocation when needed.

### Behavior and role-specific databases

Additional SQLite-backed stores exist for:

- Behavior state
- Taboo system state
- Banker state
- News watcher state
- MC state
- Treasure hunter / PoE2 state
- Trickster subrole state

## 9. Memory Architecture

The current memory system has five logical layers:

| Layer | Purpose | Refresh cadence |
|------|------|------|
| `recent_dialogue` | Short-lived prompt context from recent exchanges | Read on demand |
| `recent_memory` | Rolling summary of the current day since the last cursor | Every 4 hours |
| `daily_memory` | Daily synthesis of the server's interactions | Every 24 hours |
| `user_relationship_memory` | Per-user relationship summary | Every 1 hour when due |
| `weekly_personality_evolution` | Subtle personality evolution based on weekly experiences | Every 7 days |

This lets `think(...)` combine immediate context, short-term synthesis, and durable relational context, while the personality itself evolves slowly over time based on accumulated experiences.

### Weekly Personality Evolution

- **Purpose**: Gently evolve the bot's identity based on the week's experiences through daily memory synthesis
- **Trigger**: Every 7 days (weekly scheduled task in `run.py`)
- **Process**:
  1. Retrieves the last 7 days of daily memory paragraphs from the database
  2. Loads the current server-specific `personality.json` from `databases/{server_id}/{personality_name}/`
  3. Constructs a prompt containing:
     - Task instructions from `prompts.json` → `weekly_personality_evolution_task`
     - The 7 daily memory paragraphs, enumerated by date
     - Golden rules from `prompts.json` → `weekly_personality_evolution_rules` (max 5% change, preserve identity)
     - The current `identity_body` array from personality
  4. Sends the prompt to the LLM to generate an evolved `identity_body`
  5. Parses and validates the JSON response
  6. Creates a timestamped backup of the current personality
  7. Writes the evolved personality back to the server-specific location
- **Constraints**:
  - Maximum 5% change to personality (enforced via prompt rules)
  - Only `identity_body` section is modified (background, history, likes, hates, character)
  - Style rules, dialect instructions, examples, and other sections remain unchanged
  - If the LLM fails or parsing fails, no changes are made (safe rollback)
- **Location**: Server-specific personalities stored at `databases/{server_id}/{personality_name}/`
- **Migration**: When a server joins, `copy_personality_to_server()` copies all personality files (personality.json, prompts.json, descriptions.json, answers.json) from the base to the server-specific folder
- **Fallback**: If server personality doesn't exist, evolution task fails gracefully with error "Server personality not migrated" and the bot continues running

## 10. Role Responsibilities

### `behaviors`
- Scheduled non-role tasks
- Core bot interaction systems such as greetings, welcome flows, taboo handling, and commentary
- Server-level event subscriptions and behavior toggles

### `news_watcher`

- Scheduled watcher role with configurable frequency
- Subscription service that sends news alerts after the selected filtering or analysis method is applied
- Discord administration commands for activation, notifications, channels, and help
- **Global RSS Feed Health System**: 
  - Feed health is checked once at startup in `run.py` via `global_feed_health.py`
  - Healthy feeds are stored in a shared global database (`data/global_feeds.db`)
  - Each server syncs healthy feeds during initialization instead of checking individually
  - This prevents redundant network requests and improves startup performance
  - Feed status is tracked with health logs and automatic disabling of broken feeds

### `treasure_hunter`

- Scheduled treasure-search role
- Includes PoE2-specific persistent data and automation
- Also includes a Discord-side automatic loop in the main bot for hourly in-process treasure checks

### `trickster`

- Scheduled role with multiple subroles
- Includes:
  - `beggar` → autonomous/internal prompt task
  - `dice_game` → interactive game logic
  - `ring` → autonomous/internal prompt task

### `banker`

- Scheduled economy role
- Exposes balance, bonus, and TAE-related command flows

### `mc`

- Fully integrated Discord and voice role
- No scheduler subprocess in integrated mode
- Handles music playback, queueing, presence text, and auto-disconnect behavior

## 11. Automatic Tasks

### In `run.py`

- **Global RSS Feed Health Check**: Checks all RSS feeds once at startup and shares results with all servers
- Enabled role subprocess scheduling
- Internal subrole task execution
- Recent memory refresh
- Daily memory refresh
- Relationship memory refresh
- **Weekly personality evolution**: Evolves the server-specific personality based on 7 days of daily memory (every 7 days)

### In `discord_bot/agent_discord.py`

- Daily database cleanup
- Hourly treasure hunter loop when available
- Voice auto-disconnect for MC when channels become empty

## 12. Logging and Operational State

### `agent_logging.py`

Provides:

- Console logging
- Rotating file logging
- Server-aware log routing
- Personality-aware file naming

Observed active logs confirm current runtime use of server-scoped files and treasure hunter activity.

## 13. Key Design Rules

- **Single Discord connection**: only one main bot process owns the gateway connection
- **Dynamic command registration**: commands come from enabled modules, not a static monolith
- **Per-server isolation**: logs, DB state, and memory are server-scoped
- **Personality-driven UX**: user-facing behavior comes from JSON personality content
- **Split responsibility**: Discord interaction logic and scheduled autonomous logic are separated
- **Config-first activation**: roles are enabled by `agent_config.json`, then refined by persisted behavior state

## 14. Current Directory Map

```text
RoleAgentBot/
├── run.py
├── agent_engine.py
├── agent_db.py
├── agent_logging.py
├── agent_runtime.py
├── agent_config.json
├── behavior/
├── discord_bot/
├── roles/
├── personalities/
├── databases/
└── logs/
```

## 15. Step-by-Step Functional Logic (NEVER ERASE)

### Personality
The bot personality is split into four files. Together they define the bot persona, behavioral framing, and automatic response content.

### Memory
The memory system is designed to simulate contextual continuity so the bot can answer more consistently over time and preserve long-term state through synthesis and highlighted memories.

#### Base awareness (500-character paragraph)
- It starts from a neutral paragraph loaded from personality files.
- Once per day, typically at night, the bot performs a synthesis step:
  - It takes the base paragraph for the day and the latest recent-memory paragraph.
  - It sends both to `think` using the personality as system context, plus writing rules and a task prompt that asks the model to merge the second paragraph into the first without losing the original identity.
  - Task-specific prompt content is injected from the personality directory, with only an English fallback in code.
  - The returned paragraph becomes the new base awareness for that day.
- Before finishing, the system may run a `dreaming` step:
  - The probability is higher when the highlighted-memory table is large.
  - The system rebuilds a prompt using the current base awareness plus one highlighted memory.
  - A dedicated task prompt from `prompts.json` asks the model to subtly incorporate that remembered detail into the paragraph.
  - If the dreaming step runs, the resulting paragraph replaces the previous base awareness for the new day.

#### Recent memory (250-character paragraph)
- It starts from a neutral paragraph loaded from personality files.
- Every 4 hours, if there were new interactions:
  - It takes the current recent-memory paragraph and recent interactions from the last 4 hours.
  - It calls `think` with the existing paragraph, the recent interactions, the task prompt, and writing rules.
  - The task asks the model to synthesize the new interactions into the paragraph while preserving continuity, and to extract a highlighted memory if something important happened.
  - Prompt fragments come from the personality directory, with English code fallbacks.
  - The system stores the updated recent-memory paragraph and the extracted highlighted memory when present.

#### User relationship memory (250-character paragraph)
- It starts from a neutral paragraph loaded from personality files.
- Every hour, if there were new interactions with a given user:
  - It takes the current relationship paragraph and the recent bot-user interactions from the last hour.
  - It calls llm with the relationship paragraph, the recent interactions, the task prompt, and writing rules.
  - The task asks the model to update the relationship summary without losing its prior continuity.
  - Prompt fragments come from the personality directory, with English code fallbacks.
  - The new paragraph becomes the updated relationship memory for that user.

### Interactions and events
The bot records interactions with users and the server in its own database. These entries are kept long enough to be synthesized into memory. Different roles can also write interactions that later become part of the bot memory pipeline.

### Behaviors
This layer groups functions that create tasks for the bot or trigger events that interact with users through DM or channel messages.

#### Conversations
The bot responds to channel mentions and direct messages. These interactions are also stored for later synthesis.
Taboo detection(a behavior): The bot have tabooo words that its reading from the channels.
Keyword detection(trickster subrole): The bot recognize some keywords from the roles.
Remember that?(a behavior): Recognize that the user is asking for something that happened.


#### Greetings
The bot reacts when users move from offline to online and can send a greeting. This behavior can be enabled or disabled and uses its own personality-driven prompt.

#### Welcome
The bot welcomes users when they join the server. It follows a structure similar to greetings.

#### Comments
The bot can emit comments related to currently active roles. The prompt includes active-role context and a task definition loaded from personality content.

#### Taboo
The bot reacts when configured taboo words appear in a subscribed channel. It uses a dedicated prompt and task definition to generate the response.
                //bloque de memoria
                //bloque de relacion con el usuario (el que ha usado la palabra taboo)
                //bloque ultimas interaciones con el canal (en cuestion)
                //-------------separador -*45
                //tarea desde prompts.json/behavior/taboo
                //golden rules desde el mismo lugar
                //message_title desde el mismo lugar seguido del mensaje en cuestion
                //response_title desde el mismo lugar
#### Remember that?
-The bot recognize when someone is asking for a specific recollection while are holding a conversations or having a mencion, and aswer in consecuence.
-The aim words to know if is a one this kind of question are injected from personalities/personality_name/descriptions.json.
-If is true, we load the question without the 'question aim words' and compare with all the notable recollections, trying to find some equivalence like 50% (unsensitive caps).
-If found some coincidence, we append on the tail of the memory paragraphs to give to the LLM that recollection.
#### Role control
Roles can be enabled or disabled dynamically from Discord commands.

### Roles
Roles are activatable feature sets that modify the bot context and provide specialized services.

#### News Watcher
This role manages subscriptions for users and channels. Its automated task sends customized alerts about relevant news and supports three analysis modes:
- **Flat**: No analysis. The bot sends the personality reaction to the title and description.
- **Keyword**: The title and description are filtered using user-defined keywords.
- **General / AI**: The articles are checked against user premises (all the news article at the same time). If it matches, the articles are passed to the personality pipeline so the bot can react and notify the user for each article matched.

Downloaded-news databases are global and shared across servers by category.
Premises are hashed, and repeated checks can reuse cached results for the same premise hash instead of recomputing them.
The system limits subscriptions per user and per server/channel context.
There are dedicated commands to list subscriptions, categories, and feeds.
Each category can contain multiple feeds.
To create a subscription, the category is required and the feed is optional. Unsubscribing follows the same structure.

#### Treasure Hunter
This role tracks digital item prices and sends useful signals to the user while maintaining updated price history for tracked targets.

##### Path of Exile 2
This Treasure Hunter subrole keeps price history for tracked items and notifies the user when an item reaches a relevant buy or sell threshold.
- It maintains a global mapping between item names and item identifiers.
- It keeps shared price history by league as users subscribe to more tracked items.
- Every hour, the bot checks subscriptions and appends the latest price to each tracked item history.
- After prices are updated, threshold checks can trigger a notification generated through `think` with task-specific prompts loaded from `prompts.json`.
- Users can consult their tracked list with updated prices.
- Channel subscriptions are treated similarly to user subscriptions in this flow.

##### Future Path of Exile 1 support
This section is reserved for future expansion.

#### Trickster
This role groups game-like and roleplay-oriented interactions.

##### Dice game / pot
The dice game uses a special Banker wallet as the shared pot. The user places a fixed bet and rolls three six-sided dice. Rolling `1-1-1` wins the full pot. Other rewarded outcomes include triples, straights, and pairs depending on the game rules. The role also provides commands to inspect the pot, play, review history, and view ranking data.

##### The One Ring
The bot searches for the One Ring by questioning users. Users can accuse one another so the bot shifts attention to the accused target. Administrators can enable it and configure its frequency.
Actualmente el subrol ring, buscamos keywords durante del chat para averiguar contexto, vamos a retirar este metodo.
En vez de eso, he introducido una clausula que el LLM puede enviarnos: ACCUSE username, cuando un usuario este acusando a otro durante la charla.
Deberemos caapturar esa flag, buscaar en el servidor si el nombre del usuario coincide con alguno del servidor.
-SI no coincide le enviaremos un prompt al llm (system_prompt + memorias + relacion con el usuario + ultimas interaciones con el umaano + prompt/tarea(el umano a acusado en falso del anillo... respondele)
- Si coincide se movera el puntero de acusasion de la base de datos al nuevo usuario. 
##### Beggar
The bot asks users for gold according to a rotating daily motive. Administrators control both activation and frequency.
##### Nordic Runes
The bot interpret the question of the user and intrepret his runes call with his question, and give to him a personalized opinion.
#### MC
This role lets users search for songs and add them to a playback queue for a voice channel. It includes queue-management commands and also records relevant interactions that can feed memory and user-relationship synthesis.

#### Banker
The Banker role maintains user gold accounts and transaction history for the bot and related roles. It also supports configurable account-opening and daily bonuses managed by administrators.


### Command suite
This suite exposes the bot's useful functionality to both users and administrators through Discord commands. Some commands are always available, while others are registered dynamically depending on which roles are enabled.

### Canvas GUI suite
The Canvas suite is the highest-level interactive UI layer. It reuses titles, descriptions, and response tone from the command suite and related personality description files.

Views generally follow this structure:
- Embed title injected from `descriptions.json`
- First block: description of the current view injected from `descriptions.json`
- Second block: dynamic output that changes as the user selects options from dropdowns
- Third block: a follow-up comment from the bot, typically sourced from `answers.json`

Shared navigation elements can include:
- Buttons for sibling views
- A configuration dropdown when the view exposes editable settings (like method)
- An action dropdown for the functions associated with the current view
- Back and home buttons

The current Canvas structure is:

`!canvas` -> `home/overview`

- `home/`
- `home/overview` (same as `home` and the default `!canvas` entry point)
- `roles/`
- `roles/watcher`(Watcher overview)
- `roles/watcher/admin` (channels and configuration)
- `roles/hunter`
- `roles/hunter/poe2`(POE2 overview )
- `roles/hunter/poe2/admin`(POE2 channel overview)
- `roles/hunter/poe2/admin/admin` (enable or disable the POE2 role)
- `roles/trickster/`
- `roles/trickster/dice`(Dice overview)
- `roles/trickster/dice/admin` (server admin configuration)
- `roles/trickster/ring` (Ring overview)
- `roles/trickster/ring/admin` (server admin configuration)
- `roles/trickster/beggar` (Beggar overview)
- `roles/trickster/beggar/admin` (server admin configuration)
- `roles/mc`
- `roles/banker`(Banker overview)
- `roles/banker/admin`
- `behavior/`
- `behavior/conversation` (Behavior overview)
- `behavior/greetings`
- `behavior/welcome`
- `behavior/commentary`
- `behavior/taboo`
- `behavior/role_control`
- `help`
- `help/personal` (Help overview)
- `help/admin`

## 15. Fatigue Limit System

### 15.1 Purpose and Overview

The Fatigue Limit System provides comprehensive LLM usage management and rate limiting to prevent abuse while maintaining service availability. It implements multi-level tracking (daily, hourly, burst) with intelligent exemptions and user-friendly limit enforcement.

### 15.2 Architecture Components

#### 15.2.1 Configuration Layer (`agent_config.json`)
```json
{
  "fatigue_limits": {
    "user": {
      "daily_max": 50,      // Daily requests per user
      "hourly_max": 10,     // Hourly requests per user  
      "burst_max": 5        // 5-minute burst limit per user
    },
    "server": {
      "daily_max": 500,     // Daily requests per server
      "hourly_max": 100,    // Hourly requests per server
      "burst_max": 20       // 5-minute burst limit per server
    },
    "exemptions": {
      "admin_users": [],                    // Exempt user IDs
      "critical_tasks": ["daily_memory", "relationship_memory", "recent_memory"]
    },
    "behavior": {
      "strict_mode": false,     // true=hard block, false=warning message
      "grace_period": 3,         // First N requests always allowed
      "cooldown_minutes": 15     // Suggested wait time when limited
    }
  }
}
```

#### 15.2.2 Database Layer (`agent_db.py`)
- **Enhanced Schema**: SQLite with automatic migration support
- **Tracking Fields**:
  - `daily_requests` - Resets at 00:00 UTC
  - `hourly_requests` - Resets every hour
  - `burst_requests` - Resets every 5 minutes
  - `last_*_timestamp` - Controls reset logic
- **Dual Tracking**: User-specific + server-wide counters
- **Migration**: Automatic schema updates for existing databases

#### 15.2.3 Validation Layer (`agent_fatigue_limits.py`)
- **Multi-level Validation**: burst → hourly → daily (in order of strictness)
- **Intelligent Exemptions**: Admin users + critical system tasks
- **Grace Period**: First 3 daily requests always allowed
- **User-friendly Responses**: Clear messages with reset times

#### 15.2.4 Integration Layer (`agent_mind.py`)
- **Central Checkpoint**: All LLM calls pass through `call_llm()`
- **Pre-call Validation**: Fatigue check before LLM invocation
- **Seamless Integration**: No changes needed to existing LLM call sites

#### 15.2.5 Administration Layer (`discord_bot/fatigue_commands.py`)
- **Slash Commands**:
  - `/fatigue_stats [@user]` - Usage statistics
  - `/fatigue_limits` - Current configuration
  - `/fatigue_check @user` - Test user limit status
- **Admin-only**: Requires administrator permissions
- **Rich Embeds**: Visual representation of usage data

### 15.3 Request Flow

```text
User Message → Discord Event → Rate Limit (3s) → Fatigue Check → LLM Call → Response
                                                        ↓
                                              [If Limited] → Friendly Message → No LLM Call
```

### 15.4 Limit Enforcement Logic

#### 15.4.1 Validation Order (Most to Least Strict)
1. **Burst Limit** (5-minute window) - Prevents rapid-fire requests
2. **Hourly Limit** - Controls sustained usage
3. **Daily Limit** - Prevents daily quota exhaustion

#### 15.4.2 Exemption Logic
```python
# Critical system tasks always exempt
if call_type in ["daily_memory", "relationship_memory", "recent_memory"]:
    return ALLOWED

# Admin users exempt (configurable)
if user_id in config["exemptions"]["admin_users"]:
    return ALLOWED

# Grace period for new users
if daily_requests <= config["behavior"]["grace_period"]:
    return ALLOWED
```

#### 15.4.3 Reset Mechanisms
- **Daily**: Calendar day reset at 00:00 UTC
- **Hourly**: Top of the hour reset (XX:00:00)
- **Burst**: 5-minute sliding window (last_request > now - 5min)

### 15.5 Database Schema Evolution

#### 15.5.1 Original Schema
```sql
CREATE TABLE fatigue (
    id INTEGER PRIMARY KEY,
    user_id TEXT UNIQUE,
    user_name TEXT,
    daily_requests INTEGER DEFAULT 0,
    total_requests INTEGER DEFAULT 0,
    last_request_date TEXT
);
```

#### 15.5.2 Enhanced Schema (with Migration)
```sql
CREATE TABLE fatigue (
    id INTEGER PRIMARY KEY,
    user_id TEXT UNIQUE,
    user_name TEXT,
    daily_requests INTEGER DEFAULT 0,
    total_requests INTEGER DEFAULT 0,
    last_request_date TEXT,
    hourly_requests INTEGER DEFAULT 0,        -- NEW
    last_hour_timestamp TEXT,                  -- NEW
    burst_requests INTEGER DEFAULT 0,         -- NEW
    last_burst_timestamp TEXT,                 -- NEW
    created_at TEXT DEFAULT CURRENT_TIMESTAMP, -- NEW
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP  -- NEW
);
```

### 15.6 Message Examples

#### 15.6.1 Burst Limit Exceeded
```
⚡ **Límite de ráfaga alcanzado** (Username).

Demasiadas solicitudes rápidas. Espera **5 minutos** para continuar.

💡 **Consejos:**
• Usa comandos específicos en vez de conversación general
• Espera a que se reinicie el contador
• Contacta a un admin si necesitas más solicitudes
```

#### 15.6.2 Daily Limit Exceeded
```
📅 **Límite diario alcanzado** (Username).

Has alcanzado tu límite de solicitudes diarias. El contador se reinicia a las **00:00 UTC**.

💡 **Consejos:**
• Usa comandos específicos en vez de conversación general
• Espera a que se reinicie el contador
• Contacta a un admin si necesitas más solicitudes
```

### 15.7 Performance Considerations

#### 15.7.1 Database Optimization
- **Connection Pooling**: Reuse database connections
- **Indexing**: `user_id` indexed for fast lookups
- **Batch Operations**: Server stats updated with user stats

#### 15.7.2 Memory Efficiency
- **Lazy Loading**: Configuration loaded on demand
- **Minimal State**: No in-memory counters (database-backed)
- **Error Handling**: Graceful degradation on database errors

#### 15.7.3 Scalability
- **Per-server Isolation**: Separate databases per Discord server
- **Horizontal Scaling**: Multiple bot instances can share same database
- **Monitoring**: Built-in logging for performance tracking

### 15.8 Security Features

#### 15.8.1 Abuse Prevention
- **Rate Limiting**: 3-second cooldown between messages
- **Burst Detection**: Rapid-fire request detection
- **Daily Quotas**: Prevent sustained abuse

#### 15.8.2 Privacy Protection
- **Per-server Data**: User data isolated by server
- **Minimal Logging**: No prompt content stored
- **Data Retention**: Configurable cleanup policies

### 15.9 Monitoring and Maintenance

#### 15.9.1 Built-in Monitoring
```python
# Usage statistics available via commands
/fatigue_stats @user    # Individual user usage
/fatigue_stats          # Server-wide usage
/fatigue_check @user    # Test limit status
```

#### 15.9.2 Administrative Tools
- **Dynamic Configuration**: Edit `agent_config.json` without restart
- **User Management**: Add/remove admin exemptions
- **Usage Analytics**: Track patterns and optimize limits

#### 15.9.3 Troubleshooting
- **Comprehensive Logging**: All limit checks logged
- **Error Recovery**: Graceful fallback on database errors
- **Debug Commands**: Test validation logic without affecting users

### 15.10 Integration Points

#### 15.10.1 LLM Call Integration (`agent_mind.py`)
```python
def call_llm(system_instruction, prompt, user_id=None, user_name=None, call_type="default"):
    # Fatigue check before LLM call
    if user_id:
        fatigue_check = await check_fatigue_limit(user_id, user_name, call_type)
        if not fatigue_check.allowed:
            return format_limit_exceeded_message(fatigue_check, user_name)
    
    # Proceed with LLM call...
```

#### 15.10.2 Discord Command Registration
```python
# Auto-registered in discord_bot/fatigue_commands.py
await bot.add_cog(FatigueCommands(bot))
```

#### 15.10.3 Database Migration
```python
# Automatic schema upgrade in agent_db.py
if 'hourly_requests' not in columns:
    db.execute('ALTER TABLE fatigue ADD COLUMN hourly_requests INTEGER DEFAULT 0')
```

### 15.11 Future Enhancements

#### 15.11.1 Planned Features
- **Adaptive Limits**: Machine learning for dynamic limit adjustment
- **User Tiers**: Different limits for different user roles
- **Global Dashboard**: Web interface for cross-server monitoring
- **API Integration**: External monitoring system hooks

#### 15.11.2 Configuration Extensions
- **Time-based Limits**: Different limits for different times of day
- **Channel-specific Limits**: Vary limits by Discord channel
- **Custom Exemptions**: Role-based exemption rules

### 15.12 Best Practices

#### 15.12.1 Configuration Management
- **Conservative Defaults**: Start with lower limits, increase as needed
- **Regular Review**: Monitor usage patterns quarterly
- **User Communication**: Clear documentation of limits

#### 15.12.2 Operational Guidelines
- **Monitor Performance**: Track database query times
- **Backup Strategy**: Regular database backups
- **Incident Response**: Clear escalation procedures for limit breaches

#### 15.12.3 User Experience
- **Clear Messaging**: User-friendly limit exceeded messages
- **Fair Enforcement**: Consistent application of rules
- **Appeal Process**: Method for users to request limit increases

This fatigue limit system provides robust protection against LLM abuse while maintaining excellent user experience through intelligent exemptions and clear communication.

## 16. Canvas Command Name Filtering

### 16.1 Purpose and Overview

The Canvas command system supports bot name filtering to allow multiple bots with different personalities and configurations to coexist in the same Discord server without command conflicts.

### 16.2 Command Syntax

#### Basic Usage (responds to any bot)
```
!canvas [section] [target] [detail]
```

#### Name-Filtered Usage (responds only to specific bot)
```
!canvas <bot_name> [section] [target] [detail]
```

### 16.3 Implementation Logic

#### Parameter Processing
1. **Name Detection**: Bot name extracted from `ctx.bot.user.name`
2. **Case Insensitive Matching**: Bot names compared in lowercase
3. **Parameter Shifting**: When name filter activated, parameters shift left:
   - Input: `!canvas bot_name section target`
   - Processed as: `section target`

#### Response Logic
| Command Pattern | Bot Response Behavior |
|-----------------|---------------------|
| `!canvas` | All bots respond |
| `!canvas <valid_section>` | All bots respond |
| `!canvas <bot_name>` | Only matching bot responds |
| `!canvas <unknown_name>` | No bots respond |

#### Valid Sections
```python
valid_sections = {"home", "role", "roles", "personal", "help", "behavior"}
```

### 16.4 Multi-Bot Server Examples

#### Scenario: Three bots in one server
- **Herr Hans** - German personality bot
- **Putre** - Spanish personality bot  
- **Kronk** - Friendly assistant bot

#### Command Behaviors
| Command | Herr Hans | Putre | Kronk |
|---------|-----------|-------|-------|
| `!canvas home` | ✅ Responds | ✅ Responds | ✅ Responds |
| `!canvas herr hans role news_watcher` | ✅ Responds | ❌ Ignores | ❌ Ignores |
| `!canvas putre role news_watcher` | ❌ Ignores | ✅ Responds | ❌ Ignores |
| `!canvas kronk role news_watcher` | ❌ Ignores | ❌ Ignores | ✅ Responds |
| `!canvas unknownbot role news_watcher` | ❌ Ignores | ❌ Ignores | ❌ Ignores |

### 16.5 Technical Implementation

#### Core Function Location
- **File**: `discord_bot/canvas/command.py`
- **Function**: `cmd_canvas()`
- **Lines**: 20-35 (name filtering logic)

#### Key Code Components
```python
# Bot name detection and matching
bot_name = ctx.bot.user.name.lower()
section_lower = (section or "").strip().lower()

# Name filter activation
if section_lower == bot_name:
    logger.info(f"Canvas command targeted to bot '{section}' - name filter activated")
    # Shift parameters left
    section = target or "home"
    target = detail or ""
    detail = ""
elif section_lower and section_lower not in valid_sections:
    logger.info(f"Canvas command with unknown name '{section}' - ignoring as it's for another bot")
    return  # Don't respond
```

### 16.6 Bot-Specific Configurations

Each bot can maintain independent:
- **Personalities**: Different character traits and response styles
- **Enabled Roles**: Different sets of available commands and features
- **Database Instances**: Separate data storage per bot
- **Configurations**: Individual settings and preferences

### 16.7 Logging and Monitoring

#### Log Messages
- **Name Filter Activation**: `Canvas command targeted to bot '{name}' - name filter activated`
- **Command Ignored**: `Canvas command with unknown name '{name}' - ignoring as it's for another bot`
- **Parameter Processing**: `Canvas command parameters after processing: section='{section}', target='{target}', detail='{detail}'`

#### Debugging Information
- Original command parameters logged
- Final processed parameters logged
- Bot name matching decisions logged

### 16.8 Error Handling and User Experience

#### Updated Help Messages
- **Section Help**: Includes name filtering examples
- **Role Help**: Shows bot-specific targeting options
- **Error Messages**: Clear guidance on proper syntax

#### Examples of Updated Messages
```
❌ Unknown canvas section. Use: `!canvas home`, `!canvas roles`, `!canvas role <name>`, 
`!canvas personal`, `!canvas help`, or `!canvas <bot_name> [section]` to target a specific bot.
```

### 16.9 Backward Compatibility

#### Maintained Functionality
- All existing `!canvas` commands continue to work unchanged
- No breaking changes to current command syntax
- Name filtering is purely additive enhancement

#### Migration Path
- **Immediate**: Existing commands work without modification
- **Optional**: Users can gradually adopt name filtering for specific bot targeting
- **Seamless**: No configuration changes required

### 16.10 Use Cases and Benefits

#### Multi-Bot Environments
1. **Specialized Bots**: Different bots for different purposes (news, gaming, administration)
2. **Language Variants**: Same functionality with different language personalities
3. **Testing Environments**: Production and test bots running simultaneously
4. **Role Separation**: Different bots with different permission levels

#### Operational Benefits
1. **Conflict Prevention**: No command interference between bots
2. **User Control**: Precise bot targeting when needed
3. **Scalability**: Easy addition of new bots to existing servers
4. **Maintainability**: Clear separation of bot responsibilities

### 16.11 Future Enhancements

#### Potential Improvements
- **Bot Aliases**: Multiple names for same bot
- **Priority Systems**: Bot response ordering when multiple bots could respond
- **Dynamic Bot Discovery**: Automatic detection of available bots in server
- **Configuration-Driven Names**: Bot names configurable per server

#### Extension Points
- **Custom Name Matching**: Regex patterns for complex name filtering
- **Bot Groups**: Target multiple bots with similar characteristics
- **Conditional Filtering**: Different behavior based on user permissions or context

This Canvas name filtering system provides a robust foundation for multi-bot environments while maintaining full backward compatibility and excellent user experience.

## 17. Server-Specific Prompt Logging

### 17.1 Purpose and Overview

The Server-Specific Prompt Logging system provides isolated log directories for each Discord server, preventing mixed and fragmented logs across different servers. This enables easier debugging, maintenance, and privacy protection.

### 17.2 Architecture Components

#### 17.2.1 Directory Structure
```
logs/
├── prompt.log                    # Fallback for non-server-specific logs
├── <server_id>/                  # Server-specific directory
│   ├── prompt.log                # Server-specific prompt logs
│   ├── agent.log                 # Other server logs
│   └── <PERSONALITY>.log         # Personality-specific logs
```

#### 17.2.2 Logger Configuration (`prompts_logger.py`)
- **Function**: `get_prompts_logger(server_id=None)`
- **Server-Specific Directories**: Creates `logs/<server_id>/prompt.log` when server_id provided
- **Logger Naming**: Uses `prompts_<server_id>` for unique logger instances
- **Backward Compatibility**: Falls back to `logs/prompt.log` when no server_id provided

#### 17.2.3 Updated Logging Functions
All logging functions now accept `server_id` parameter:
- `log_prompt(prompt_type, content, metadata=None, server_id=None)`
- `log_system_prompt(content, role=None, server=None, server_id=None)`
- `log_user_prompt(content, user_id=None, server=None, role=None, server_id=None)`
- `log_final_llm_prompt(provider, call_type, system_instruction, user_prompt, role=None, server=None, metadata=None, server_id=None)`
- `log_consolidated_context(content, role=None, server=None, interaction_count=None, server_id=None)`
- `log_readme_enhanced_prompt(original_question, readme_content, enhanced_prompt, system_instruction=None, role=None, server=None, server_id=None)`
- `log_subrole_prompt(subrole_name, content, role=None, server=None, server_id=None)`
- `log_agent_response(content, role=None, server=None, response_length=None, server_id=None)`

### 17.3 Integration Points

#### 17.3.1 Agent Mind Integration (`agent_mind.py`)
```python
# All log_agent_response() calls now include server_id
log_agent_response(content, role=role, server=server_name, response_length=len(content), server_id=server_id)
```

#### 17.3.2 Role Integration (`roles/news_watcher/news_watcher.py`)
```python
# News watcher logging includes server_id
log_final_llm_prompt(provider, call_type, system_instruction, user_prompt, role=role, server=server_name, server_id=server_name)
log_prompt("news_analysis", analysis_content, metadata, server_id=server_name)
```

### 17.4 Benefits

1. **Isolation**: Each server's prompts are logged separately
2. **Debugging**: Easy to trace prompts to specific servers
3. **Maintenance**: Server-specific log management
4. **Privacy**: Better separation of data between servers
5. **Scalability**: Supports unlimited servers with individual logging

### 17.5 Usage

- **Automatic**: Most calls automatically use active server ID
- **Manual**: Can specify server_id for custom logging scenarios
- **Fallback**: Uses global prompt.log when no server specified

## 18. Server Initialization Unification

### 18.1 Purpose and Overview

The Server Initialization Unification consolidates multiple scattered initialization methods into a single unified entry point, ensuring consistent behavior across startup and new guild joins.

### 18.2 Unified Method

#### 18.2.1 Function Signature
```python
def initialize_server_complete(guild, agent_config: dict = None, is_startup: bool = False) -> bool:
```

#### 18.2.2 Location
- **File**: `discord_bot/db_init.py`
- **Lines**: 120-221

#### 18.2.3 Parameters
- **guild**: Discord guild object
- **agent_config**: Agent configuration dictionary (optional)
- **is_startup**: True for startup initialization, False for new guild joins

### 18.3 Initialization Tasks

1. **Database initialization** - All databases (agent, roles, behavior, role-specific)
2. **Default roles loading** - news_watcher, treasure_hunter, trickster, banker
3. **News watcher feeds** - Health check if role enabled
4. **Roles configuration** - Migration and defaults from behavior.db
5. **Logging setup** - Server-specific log file paths
6. **Server activation** - Set as active server (startup only)

### 18.4 Event Handler Updates

#### 18.4.1 `on_ready()` in `agent_discord.py`
- **Before**: Manual database setup, role loading, logging configuration
- **After**: Single call to `initialize_server_complete(guild, agent_config, is_startup=True)`

#### 18.4.2 `on_guild_join()` in `agent_discord.py`
- **Before**: Manual database setup, news watcher initialization, logging
- **After**: Single call to `initialize_server_complete(guild, agent_config, is_startup=False)`

### 18.5 Context-Specific Behavior

- **Startup mode**: Sets server as active server, configures global logging
- **New guild mode**: Only initializes the new server, no global changes

### 18.6 Benefits

- **Code Consolidation**: -50+ lines of duplicate initialization code eliminated
- **Consistency**: Identical initialization for startup and new guild joins
- **Maintainability**: Easy to extend - add new initialization tasks in one location
- **Reliability**: Comprehensive coverage with proper error handling

### 18.7 Backward Compatibility

- **Legacy function**: `initialize_databases_for_guild()` preserved with deprecation warning
- **No breaking changes**: Existing code continues to work
- **Gradual migration**: Path for any external callers

## 19. LLM Function Unification

### 19.1 Purpose and Overview

The LLM Function Unification consolidates `think()` and `_call_llm_async()` into a single `call_llm()` function, reducing code duplication and improving maintainability.

### 19.2 Unified Function Design

#### 19.2.1 Function Signature
```python
def call_llm(
    system_instruction: str,
    prompt: str,
    async_mode: bool = False,
    call_type: str = "default",
    temperature: float | None = None,
    max_tokens: int = 1024,
    critical: bool = True,
    metadata: dict | None = None,
    logger: logging.Logger | None = None
) -> str:
```

#### 19.2.2 Parameters
- **async_mode**: False for think(), True for _call_llm_async()
- **call_type**: "think", "subrole_async", "daily_memory", etc.
- **temperature**: Auto-detect based on call_type if None
- **critical**: Whether errors should break execution
- **metadata**: Additional context for logging

### 19.3 Behavior

- **sync mode**: Direct call, return response
- **async mode**: Threading with queues, return response
- **temperature**: 0.9 for missions, 0.95 for others
- **logging**: Detailed for critical calls, simple for background

### 19.4 Key Differences Preserved

1. **Execution Mode**: Sync vs Async
2. **Temperature**: 0.9/0.95 (missions) vs 0.95 (background)
3. **Logging Level**: Detailed vs Simple
4. **Error Criticality**: Critical vs Tolerant
5. **Call Type Tracking**: "think" vs "subrole_async"/memory types

### 19.5 Integration Points

- **agent_mind.py**: All memory calls updated, old functions removed
- **agent_engine.py**: Subrole calls updated

### 19.6 Benefits

- **Code Reduction**: -100+ lines of duplicate LLM logic eliminated
- **Single Source of Truth**: Consistent error handling across all operations
- **Unified Logging**: Centralized monitoring
- **Easier Testing**: Single function to test

## 20. Dynamic Bot Naming System

### 20.1 Purpose and Overview

The Dynamic Bot Naming System replaces hardcoded personality references with dynamic placeholders, allowing easy bot renaming without code changes.

### 20.2 Implementation

#### 20.2.1 Placeholder System
- **Placeholder**: `{_bot_display_name}`
- **Fallback**: Uses "Bot" if Discord not available
- **Runtime Replacement**: All placeholders replaced with actual bot name

#### 20.2.2 JSON Configuration
- **27 placeholders** configured across personality JSON files
- **Location**: `personalities/*/prompts.json`, `descriptions.json`, `answers.json`

#### 20.2.3 Python Integration
- **agent_mind.py**: Memory formatting functions updated
- **agent_engine.py**: Mission prompts updated
- **postprocessor.py**: Comment updated to generic
- **discord_bot/canvas/**: Role manager and behavior sections updated
- **behavior/commentary/commentary.py**: Commentary prompts updated
- **roles/trickster/**: Donation context and transaction descriptions updated
- **roles/trickster/subroles/nordic_runes/**: Analysis section updated

### 20.3 Benefits

- **No Hardcoded Names**: System uses dynamic bot name everywhere
- **Easy Bot Renaming**: Change name once, updates everywhere
- **Language Consistency**: English legacy code cleaned up
- **Future-Proof**: New bot names automatically propagate

## 21. Premises System Redesign

### 21.1 Purpose and Overview

The Premises System Redesign changes from a global/custom mixing system to a "copy defaults to user" approach, giving users full control over their premises.

### 21.2 Core Principle

**"Copy defaults to user, then manage only user premises"**

### 21.3 Behavior Changes

1. **First premise**: Automatically copies all 8 default premises to user
2. **User control**: User can modify/delete ALL their premises (including copied defaults)
3. **No global fallback**: System never uses global premises directly
4. **Consistent context**: Always returns "custom" context

### 21.4 Implementation Details

#### 21.4.1 Modified Functions

**`add_user_premise()`**:
- Checks if user has no premises
- If empty: Copies all 8 default premises first
- Then adds user's new premise
- If limit reached: Replaces last default with user's premise

**`get_premises_with_context()`**:
- **Removed**: Global premises fallback logic
- **Now**: Returns user premises or empty list
- **Context**: Always "custom" or "empty" (never "global")

#### 21.4.2 New Helper Functions

**`_get_default_premises()`**:
- Retrieves default premises from personality file
- Uses `PERSONALIDAD['watcher_premises']['premises']`
- Returns list of 8 default premises

**`_insert_user_premise()`**:
- Direct insertion bypassing duplicate checks
- Used for copying default premises efficiently
- Handles database locking properly

### 21.5 User Experience

#### Before (Old System)
- User adds "Crimson Desert" → Sees 1/7 in UI
- AI prompt shows 8 global premises → Confusion
- Can't modify global premises

#### After (New System)
- User adds "Crimson Desert" → System copies 8 defaults + adds user's
- User sees 8 premises: 7 defaults + 1 custom
- AI prompt shows user's 8 premises → Consistent
- User can modify/delete any of the 8 premises

### 21.6 Benefits

- **Simplified Logic**: No more global/custom switching
- **User Control**: Full control over all premises they see
- **Consistent Behavior**: Always uses user premises
- **Predictable Results**: What user sees is what AI uses
- **Better Debugging**: Single source of truth for premises

## 22. Postprocessor Simplification

### 22.1 Purpose and Overview

The Postprocessor Simplification removes artificial length limits and phrase cutting, allowing LLM responses to be returned in their natural form.

### 22.2 Removed Features

- **Character limit enforcement** (280 default)
- **Smart truncation** at sentence boundaries
- **Response cut-off detection** and repair
- **Dangling preposition removal**
- **Complex multi-step processing pipeline**

### 22.3 Preserved Features

- **Internal thinking detection** and rejection
- **Basic text sanitization** (whitespace normalization)
- **Function signature compatibility** (`max_chars` parameter kept)

### 22.4 Current Simplified Function

```python
def postprocess_response(text, max_chars=None):
    """
    Simplified post-processing - only cleans internal thinking and blocked responses.
    
    Args:
        text: Original text generated by the LLM
        max_chars: Unused parameter kept for compatibility
        
    Returns:
        Clean text without length limits
    """
    if not text:
        return ""
    
    # First check if it's internal thinking and reject immediately
    if is_internal_thinking(text):
        logger.warning(f"🧠 Internal thinking detected and rejected: {text[:100]}...")
        return ""  # Return empty so system uses fallback
    
    # Only sanitize text, no length limits
    return _sanitize_text(text)
```

### 22.5 Impact

- **No length limits**: Responses can be any length
- **Only basic cleaning**: Internal thinking rejection, sanitization
- **Simpler, faster processing**
- **Full LLM responses preserved**

## 23. YouTube Bot Detection Fix

### 23.1 Purpose and Overview

The YouTube Bot Detection Fix addresses VPS environment issues where YouTube blocks automated access with "Sign in to confirm you're not a bot" errors.

### 23.2 Enhanced Configuration

#### 23.2.1 Browser Emulation
```python
'http_headers': {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}
```

#### 23.2.2 Authentication Options
- **Cookie file support**: `/app/cookies.txt`
- **Player client variants**: `['android', 'web']`
- **Player skip**: `['configs', 'webpage']`
- **Socket timeout**: 30 seconds
- **Retries**: 3 attempts

### 23.3 Smart Error Handling

#### 23.3.1 Bot Detection Detection
```python
if "Sign in to confirm you're not a bot" in error_msg:
    await self._send_message(message.channel, 
        "🚫 **YouTube bot detection detected**\n\n"
        "This happens when YouTube blocks automated access. Try:\n"
        "• Using a direct YouTube URL instead of search\n"
        "• Waiting a few minutes and trying again\n"
        "• Using a different song or source\n\n"
        "If this persists, consider using YouTube cookies for authentication.")
```

#### 23.3.2 Automatic Recovery
- Automatically skips problematic songs in `_play_next()`
- Continues with next song in queue
- Prevents playback interruption

### 23.4 Integration Points

- **cmd_play()**: Immediate playback configuration
- **cmd_add()**: Queue addition configuration
- **_play_next()**: Continuous playback configuration

### 23.5 Benefits

- **Multi-layer Approach**: Browser headers + cookies + player clients
- **Fallback Mechanism**: Works with or without cookies
- **User-Friendly Errors**: Clear guidance when issues occur
- **Automatic Recovery**: System continues working despite blocks

## 24. Greeting DM Reply System

### 24.1 Purpose and Overview

The Greeting DM Reply System allows users to reset the greeting counter by sending a DM to the bot, implementing the exact behavior requested for greeting management.

### 24.2 User Flow

1. **User connects** → Bot sends greeting
2. **User disconnects** → No greeting
3. **User comes online** → Bot doesn't greet (has unreplied greeting)
4. **User sends DM to bot** → Marks as replied, resets counter
5. **User disconnects and returns after cooldown** → Bot greets again

### 24.3 Technical Implementation

#### 24.3.1 Database Schema (`behavior/db_behavior.py`)
- **Table**: `greetings`
- **Fields**: user_id, user_name, guild_id, greeting_sent_at, needs_reply, replied, replied_at, greeting_type, greeting_message

#### 24.3.2 Database Functions
- **`record_greeting_sent()`**: Records when a greeting is sent
- **`mark_user_replied()`**: Marks user as replied when they message the bot
- **`get_last_greeting_status()`**: Checks if user has unreplied greeting
- **`cleanup_old_greetings()`**: Maintenance for old records

#### 24.3.3 DM Message Processing (`discord_bot/agent_discord.py`)
- **DM detection logic** in `_process_chat_message()`
- For DMs: searches all server databases for unreplied greetings
- For server messages: uses existing guild-specific logic

### 24.4 Benefits

- **Reliable tracking**: Dedicated table prevents data loss
- **Clear logic**: Simple boolean flag instead of complex interaction parsing
- **Better debugging**: Explicit greeting records with timestamps
- **Scalable**: Can extend to different greeting types (welcome, etc.)
