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

The current memory system has four logical layers:

| Layer | Purpose | Refresh cadence |
|------|------|------|
| `recent_dialogue` | Short-lived prompt context from recent exchanges | Read on demand |
| `recent_memory` | Rolling summary of the current day since the last cursor | Every 4 hours |
| `daily_memory` | Daily synthesis of the server's interactions | Every 24 hours |
| `user_relationship_memory` | Per-user relationship summary | Every 1 hour when due |

This lets `think(...)` combine immediate context, short-term synthesis, and durable relational context.

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
  - Healthy feeds are stored in a shared global database (`data/global_feeds_{personality}.db`)
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
        fatigue_check = check_fatigue_limit(user_id, user_name, call_type)
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
