# RoleAgentBot — Architecture

> Living reference for the RoleAgentBot codebase.
> Optimized to be readable both by humans and by LLMs reasoning over the repo.
> Backup of the previous revision is kept at `ARCHITECTURE.md.bak`.

---

## 1. Purpose

RoleAgentBot is a personality-driven Discord agent that combines:

- A persistent **main Discord bot process** handling the gateway, commands, messages, presence and voice.
- A parallel **scheduler** that launches periodic **role subprocesses**, **internal subrole tasks** and **memory / personality maintenance**.
- A **multi-layer memory system** (recent dialogue → recent memory → daily memory → user relationship → weekly personality evolution).
- **Per-server isolation** of configuration, personality, databases and logs.
- A unified **LLM call chain** with automatic fallbacks (Vertex AI → Groq → Mistral) and a **fatigue rate-limit** layer.
- A **Canvas GUI** (interactive embeds with buttons and dropdowns) that mirrors the command suite.

The bot is **multi-tenant**: the same process serves many guilds simultaneously, and each guild keeps its own copy of the personality so it can evolve independently.

---

## 2. Runtime Topology

```text
run.py                                 ← orchestrator (asyncio.gather)
├── discord_bot() subprocess           ← main Discord process
│   └── discord_bot/agent_discord.py
│       ├── discord_core_commands.py   ← static commands (help, identity, role control, fatigue…)
│       ├── discord_role_loader.py     ← dynamic role command registration
│       ├── canvas/                    ← interactive UI layer
│       ├── db_init.py                 ← initialize_server_complete()
│       ├── fatigue_commands.py        ← admin slash commands
│       └── entitlement_manager.py     ← Discord entitlements / premium
│
└── scheduler() loop                   ← periodic background work
    ├── role subprocesses              ← news_watcher, treasure_hunter, trickster, shaman, banker, juggler
    ├── internal subrole tasks         ← beggar (banker), ring (juggler)
    └── memory maintenance
        ├── daily_memory (24 h)
        └── weekly_personality_evolution (7 d)

behavior/                              ← reactive systems mounted inside the main bot
├── greet.py                           ← offline → online presence greetings
├── welcome.py                         ← member join greetings
├── taboo/                             ← taboo word reactions
├── commentary/                        ← role-aware commentary
└── db_behavior.py                     ← per-server behavior DB
```

Two cooperating execution layers:

| Layer       | Responsibility                                                                         | Execution mode              |
| ----------- | -------------------------------------------------------------------------------------- | --------------------------- |
| `Main bot`  | Discord connection, commands, events, chat, greetings, Canvas, MC voice, subrole ticks | Persistent async process    |
| `Scheduler` | Launches optional role scripts and runs memory/personality maintenance                 | Async loop inside `run.py`  |

Two role integration modes:

| Mode                      | What it means                                 | Examples                                                                                |
| ------------------------- | --------------------------------------------- | --------------------------------------------------------------------------------------- |
| `Integrated Discord role` | Command handlers live inside the main bot    | `mc`, every `*_discord.py` module                                                       |
| `Scheduled role task`     | Autonomous logic run on a timer as subprocess | `news_watcher.py`, `treasure_hunter.py`, `trickster.py`, `shaman.py`, `banker.py`, `juggler.py` |

---

## 3. Entry Points

### 3.1 `run.py`

System orchestrator:

- `main()` loads `agent_config.json`.
- Runs **global RSS feed health check** once at startup (`roles/news_watcher/global_feed_health.py`).
- `asyncio.gather(discord_bot(), scheduler(config))` keeps both layers alive.
- The scheduler iterates enabled roles, computes `next_run`, launches due roles as subprocesses, and runs non-role periodic tasks (daily memory, weekly personality evolution).

### 3.2 `discord_bot/agent_discord.py`

Main Discord runtime:

- Builds the Discord client with limited intents.
- `on_ready()` calls `initialize_server_complete(guild, agent_config, is_startup=True)` per guild, then:
  - Registers **core commands** (`register_core_commands`).
  - Registers **role commands dynamically** (`register_all_role_commands` → `discord_role_loader._try_register_role`).
- `on_guild_join()` calls `initialize_server_complete(..., is_startup=False)`.
- Drives background loops: subrole task scheduler (1 min tick), daily DB cleanup, treasure hunter hourly loop, MC voice idle timeout, ring state refresh.

### 3.3 `agent_engine.py`

Personality + prompt orchestration:

- `_cargar_personalidad(server_id)` reads `databases/<server_id>/server_config.json`, copies the base personality into the server folder on first use, then loads the merged personality JSON (see §5).
- `_build_system_prompt(personality, server_id)` assembles identity + style + examples + active role missions.
- `_get_active_roles_section(server_id)` injects the missions of enabled roles into the system prompt.
- Exposes helpers for subrole internal prompts (e.g. beggar, ring).

### 3.4 `agent_mind.py`

LLM layer and memory synthesis:

- `call_llm()` is the **single entry point** for every LLM call in the system.
- Builds conversational prompts (`_build_conversation_user_prompt`, `_build_conversation_channel_prompt`, `_build_prompt_memory_block`, `_build_prompt_relationship_block`).
- Generates daily memory (`generate_daily_memory_summary`) and weekly personality evolution (`generate_weekly_personality_evolution`).

---

## 4. Configuration Model

### 4.1 `agent_config.json`

Global, cross-server defaults. Relevant keys:

- `default_personality`, `default_language`, `platform`.
- `llm.max_tokens`.
- `fatigue_limits` (see §10).
- `roles`: for each role `{ enabled, interval_hours, script, subroles: {...} }`.

Current canonical role set:

- `news_watcher` (hourly)
- `treasure_hunter` (hourly; PoE2)
- `trickster` (12 h) — subrole: `dice_game`
- `shaman` (24 h) — subrole: `nordic_runes`
- `mc` (integrated, no interval; voice features)
- `banker` (24 h) — subrole: `beggar`
- `juggler` (24 h) — subrole: `ring`

> **Note vs. older docs:** `beggar` moved from `trickster` → `banker`; `ring` moved from `trickster` → `juggler`; `nordic_runes` moved into the new `shaman` role.

### 4.2 Per-server configuration

`databases/<server_id>/server_config.json` stores per-guild overrides:

- `active_personality`
- `language`
- Any server-scoped toggles written by the Canvas / commands.

### 4.3 Personality assets

`personalities/<name>/` is the **base template** shipped with the repo. Each name typically contains one or more language folders (`es-ES`, `en-US`) with:

- `personality.json` — identity, style, examples, `identity_body`, `bot_display_name`.
- `prompts.json` — system prompt template and task prompts (daily memory, relationship memory, greetings, taboo, role missions, subrole tasks, weekly evolution rules…).
- `answers.json` — user-facing canned strings.
- `descriptions.json` — Canvas UI titles/descriptions.
- Optional assets: `avatar.png` / `avatar.webp`, banners.

Available personalities in-tree: `hans`, `igorrr`, `kronk`, `putre`, `rab` (default), `yuki`.

On first contact with a guild, `discord_bot/db_init.py::copy_personality_to_server()` copies this template into `databases/<server_id>/<personality_name>/` so the guild can evolve an independent copy.

---

## 5. Personality System

### 5.1 Loading flow (Trace 8)

```text
_cargar_personalidad(server_id)
├── read databases/<server_id>/server_config.json → active_personality, language
├── copy_personality_to_server() if local copy missing
│   └── shutil.copytree personalities/<name>/<lang>/ → databases/<server_id>/<name>/
├── resolve databases/<server_id>/<name>/ as the canonical path
└── load + merge personality.json, prompts.json, descriptions.json, answers.json
```

### 5.2 System prompt assembly

`_build_system_prompt()` composes the final system instruction from the merged personality:

- `identity_title + identity_body`
- `style_title + style_body`
- `examples_title + examples_body`
- Active roles section (`_get_active_roles_section(server_id)`) — missions of enabled roles.
- Dynamic replacements for the `{_bot_display_name}` placeholder (see §11).

### 5.3 Bot identity synchronization

When the personality changes (`!setpersonality` or during `initialize_server_complete`), the bot:

1. Reads `bot_display_name` from the guild's `personality.json`.
2. Looks for `avatar.webp` / `avatar.png` next to it.
3. Updates **nickname + per-guild avatar** in a single Discord REST call:

   ```
   PATCH /guilds/{guild.id}/members/@me
   Body: {"nick": "...", "avatar": "<base64>"}
   ```

Requires the *Change Nickname* permission. Per-guild identity is fully isolated.

Related commands: `!setpersonality <name>`, `!setnickname <name>`, `!identity`.

### 5.4 Weekly personality evolution (Trace 9)

Every 7 days, `execute_weekly_personality_evolution_all_servers` runs per guild:

1. `get_last_n_daily_memories(7)` retrieves the last week of daily memory paragraphs.
2. Loads the server's `personality.json`.
3. Builds a prompt with: `weekly_personality_evolution_task`, the 7 paragraphs, current `identity_body`, and the *golden rules* (max ~5% change, preserve identity).
4. `call_llm()` returns an evolved `identity_body`.
5. `_parse_identity_body_from_llm_response` validates the JSON array.
6. A timestamped backup (`personality_backup_YYYYMMDD.json`) is written next to the file.
7. `personality.json` is updated in place.

If the LLM or parsing fails, nothing is written (safe rollback). If the server personality has not been migrated yet, the task fails gracefully with a clear error.

---

## 6. Memory Architecture

Five logical layers, all server-scoped:

| Layer                            | Purpose                                                          | Refresh cadence               |
| -------------------------------- | ---------------------------------------------------------------- | ----------------------------- |
| `recent_dialogue`                | Last exchanges, injected raw into the conversational prompt      | Read on demand                |
| `recent_memory`                  | Rolling summary of the current day since the last cursor         | Every 4 h (when new activity) |
| `daily_memory`                   | 500-char synthesis of the server's day                           | Every 24 h                    |
| `user_relationship_memory`       | 250-char per-user relationship summary                           | Every 1 h (per-user when due) |
| `weekly_personality_evolution`   | Subtle mutation of `identity_body` based on the last 7 days      | Every 7 d                     |

### 6.1 Base awareness (daily, ~500 chars)

- Seeded from the personality's neutral paragraph.
- Once per day `generate_daily_memory_summary(server_id)`:
  - Reads the previous daily paragraph and the current `recent_memory`.
  - Calls `call_llm()` with the personality as system prompt plus a task from `prompts.json` that merges the latest recent memory into the daily one without losing identity.
  - Optionally runs a **dreaming** step: with a probability tied to the number of stored *notable recollections*, it re-prompts the LLM to subtly weave one random recollection into the new paragraph.
  - Persists via `upsert_daily_memory()` and possibly `add_notable_recollection()`.

### 6.2 Recent memory (~250 chars)

- Every 4 h, if there has been activity, the task:
  - Feeds the current recent paragraph + new interactions.
  - Asks the LLM to update the paragraph and to extract a *notable recollection* if something relevant happened.
  - Saves both outputs.

### 6.3 User relationship memory (~250 chars per user)

- Every hour per user with recent activity:
  - Merges the prior relationship paragraph with the last hour of interactions using a dedicated task prompt.
  - Persists the new paragraph in the relationship table.

### 6.4 Notable recollections and "remember that?"

- Notable recollections are stored separately and used both for dreaming and for explicit recall.
- When a user's message contains recall-intent keywords (defined in `descriptions.json`), the bot searches notable recollections for fuzzy matches (~50% overlap, case-insensitive) and appends the best match to the memory block before calling the LLM.

### 6.5 Prompt assembly (chat)

`_build_conversation_user_prompt` / `_build_conversation_channel_prompt` produce:

```
[memory block: daily + recent + optional recollection]
[relationship block for this user]
[last interactions window]
---
[task + golden rules + incoming message]
```

---

## 7. Event and Message Flow

### 7.1 Startup (Trace 1)

```text
run.py main()
├── load_config()
├── check_global_feed_health()
└── asyncio.gather(
    ├── discord_bot() subprocess          → bot.start(token) → on_ready()
    │   ├── initialize_server_complete(guild, ..., is_startup=True)
    │   ├── register_core_commands()
    │   └── register_all_role_commands()  → _try_register_role per role
    └── scheduler(config) loop
        ├── _execute_optional_role_tasks()            → launch_role() subprocesses
        ├── _execute_optional_non_role_tasks()        → daily_memory, weekly_personality_evolution
        └── update next_run[name] = now + interval
)
```

### 7.2 Chat (Trace 2)

```text
on_message(message)
├── ignore bots
├── command prefix?       → dispatch to commands
├── rate-limit check
└── _process_chat_message()
    ├── taboo trigger?    → behavior/taboo response
    ├── DM or mention?    → build conversation prompt
    │   ├── _build_prompt_memory_block()
    │   ├── _build_prompt_relationship_block()
    │   ├── last interactions + golden rules
    │   └── asyncio.to_thread(call_llm, ...)          → [§8]
    ├── db.add_interaction(...)
    └── message.channel.send(response)
```

### 7.3 Presence greeting (Trace 6)

```text
on_presence_update(before, after)
├── detect offline → online
└── behavior/greet.handle_presence_greeting()
    ├── build_greeting_prompt()               (memory + relationship)
    ├── call_llm() async, critical=True
    ├── discord.ui.View + ReplyButton
    │   └── ReplyButton.callback → pin_dm_session(user_id, server_id)
    ├── member.send(greeting, view=view)
    └── record_greeting_sent() + log interaction
```

`behavior/welcome.py` follows the same skeleton for `on_member_join`.

### 7.4 Greeting DM reply

Greetings are tracked in `behavior/db_behavior.py::greetings` with `needs_reply` / `replied` flags. When a user sends a DM, `_process_chat_message()` scans all server DBs for an unreplied greeting, marks it replied, and resets the "should greet again" counter. This allows greeting cooldowns to reset naturally once the user engages in DM.

---

## 8. LLM Call Chain

### 8.1 Unified entry point

`agent_mind.py::call_llm(system_instruction, prompt, async_mode=False, call_type="default", temperature=None, max_tokens=1024, critical=True, user_id=None, user_name=None, server_id=None, metadata=None, logger=None)` is used by **every** component (chat, memory synthesis, greetings, welcome, commentary, taboo, roles, subroles).

Responsibilities:

- Logs the final prompt via `log_final_llm_prompt()` → `logs/<server_id>/prompt.log`.
- Runs the **fatigue check** for interactive calls (§10).
- Auto-selects temperature based on `call_type` when none is provided (0.9 for missions, ~0.95 for conversational/background).
- Dispatches through the fallback chain below.
- Calls `postprocess_response()` and `runtime_increment_usage()` on success.

### 8.2 Fallback chain (Trace 3)

```text
call_llm()
├── Attempt 1 — Vertex AI (gemini-2.5-flash)
│   └── _call_vertexai_sync() in a thread with 30 s timeout
│
├── on failure / timeout → Attempt 2 — Groq (llama-3.3-70b-versatile)
│   └── _call_groq_fallback() via agent_runtime.get_groq_client()
│
└── on failure → Attempt 3 — Mistral (mistral-medium-latest)
    └── _call_mistral_fallback()
```

If all three fail the function returns an empty/fallback string and the caller decides how to degrade (critical vs. tolerant).

### 8.3 Post-processing

`postprocessor.py::postprocess_response()` is intentionally minimal:

- Rejects internal-thinking leaks (returns empty string so the caller can fallback).
- Basic whitespace/text sanitization.
- **No length truncation** — responses are preserved at their natural length (`max_chars` kept only for signature compatibility).

---

## 9. Roles and Subroles

### 9.1 Role registration

`discord_bot/discord_role_loader.py`:

- Iterates a canonical registry (`news_watcher`, `treasure_hunter`, `trickster`, `shaman`, `banker`, `juggler`) and `mc` separately.
- Checks `is_role_enabled_check(role_name, agent_config)`.
- Calls `_try_register_role(bot, module_path, func_name, personality, agent_config)` for each enabled role.
- Every role provides a `<role>_discord.py` module with its own command registration function.

### 9.2 Scheduled role subprocesses

For every enabled role with a `script`, `run.py::launch_role()` runs the script as an isolated subprocess (`asyncio.create_subprocess_exec`) with its own stdout/stderr pipes. The scheduler schedules the next run by `interval_hours`.

### 9.3 Internal subrole task ticker

`discord_bot/agent_discord.py` runs a 1-minute loop that iterates guilds and invokes `get_due_subrole_tasks_for_server(server_id)`. Due subroles (e.g. `beggar`, `ring`) are executed in-process via `execute_subrole_internal_task(subrole_name, subrole_config, bot_instance=bot, ...)`, which delegates to the concrete task module (e.g. `roles/banker/subroles/beggar/beggar_task.py`). After execution, `mark_subrole_executed()` updates `next_run = now + frequency_hours`.

### 9.4 Role catalog

#### `news_watcher`

- Subscription service for users and channels.
- Scheduled subprocess fetches feeds and applies one of three analysis modes:
  - **Flat** — no analysis, personality reacts to title + description.
  - **Keyword** — filters by user-defined keywords.
  - **General / AI** — batched articles are validated against user premises using `call_llm()` (premises are hashed and cached across subscriptions with the same hash).
- Shared per-category article DB (`databases/shared_*`), per-server subscription DB.
- **Premises model**: on the first user premise, the 8 personality defaults are copied into the user's premise list; from then on the user has full control (add/delete/modify) — no global fallback.
- **Global feed health check**: run once at startup in `run.py`; healthy feeds live in `data/global_feeds.db` and servers sync from there instead of probing individually.

#### `treasure_hunter`

- Scheduled price watcher, currently implemented for **Path of Exile 2**.
- Keeps a global `item_name → item_id` map and a per-league shared price history.
- Hourly subprocess updates prices and checks thresholds; notifications are generated through `call_llm()` using role-specific task prompts.
- Also owns an in-process hourly loop inside the main bot for checks that need the Discord client.

#### `trickster` (subrole `dice_game`)

- Roleplay-style role. `dice_game` uses a shared Banker wallet as the pot.
- Fixed bet, three dice; `1-1-1` wins the pot; triples/straights/pairs pay according to rules.
- Commands expose: play, inspect pot, history, ranking.

#### `shaman` (subrole `nordic_runes`)

- Interpretive subrole: the user asks a question, the bot "casts" runes and answers with a personalized reading generated via `call_llm()`.

#### `banker` (subrole `beggar`)

- Tracks user gold accounts, transactions, and configurable daily bonus / account-opening flow.
- `beggar` (Trace 10): every `frequency_hours` the task picks an active user of the server, loads the current rotating daily reason, the banker fund balance, and the relationship memory, builds a prompt, calls the LLM, and sends a DM (or posts to a chosen channel with `BeggarDonationView` buttons).

#### `juggler` (subrole `ring`)

- Playful role where the bot looks for the "One Ring" by questioning users.
- **Accusation flow**: the LLM can emit the sentinel `ACCUSE <username>` in its reply. The bot catches this flag and:
  - If `<username>` matches a member of the guild → the accusation pointer in the ring DB moves to that user.
  - If it does not match → a follow-up prompt (memory + relationship + last interactions + "false accusation" task) is issued to the LLM so the bot replies accordingly.
- Admins enable the subrole and set frequency via Canvas or commands.

#### `mc` (integrated)

- Fully integrated voice role — no scheduler subprocess.
- Handles music search (YouTube), queue, voice presence and auto-disconnect (`voice_settings.auto_disconnect_timeout`).
- YouTube access uses a browser-like User-Agent, optional cookie file (`/app/cookies.txt`), alternate player clients (`android`, `web`) and robust retry. On "bot detection" errors, the current song is skipped and a user-facing hint is posted.

---

## 10. Fatigue Limit System

Rate-limit layer in front of `call_llm()` to protect LLM quotas.

### 10.1 Configuration (`agent_config.json`)

```json
"fatigue_limits": {
  "user":   { "daily_max": 50,  "hourly_max": 10,  "burst_max": 5  },
  "server": { "daily_max": 500, "hourly_max": 100, "burst_max": 20 },
  "exemptions": {
    "admin_users": [],
    "critical_tasks": ["daily_memory", "relationship_memory", "recent_memory"]
  },
  "behavior": {
    "strict_mode":    false,   // false = friendly warning, true = hard block
    "grace_period":   3,       // first N daily requests always allowed
    "cooldown_minutes": 15
  }
}
```

### 10.2 Components

- **`agent_fatigue_limits.py`** — validation (burst → hourly → daily), exemptions, grace-period logic, limit-exceeded messages.
- **`agent_db.py`** — SQLite table `fatigue` with counters for daily/hourly/burst + last timestamps; auto-migration adds missing columns.
- **`agent_mind.py::call_llm`** — checkpoint. Critical system tasks (memory synthesis) bypass the check.
- **`discord_bot/fatigue_commands.py`** — admin slash commands: `/fatigue_stats`, `/fatigue_limits`, `/fatigue_check`.

### 10.3 Flow

```text
message → rate-limit (3 s) → fatigue check → call_llm → response
                           └─ limited → friendly message, no LLM call
```

Reset rules:

- **Daily** — 00:00 UTC.
- **Hourly** — top of the hour.
- **Burst** — rolling 5-minute window.

---

## 11. Dynamic Bot Naming

- All user-facing personality texts reference the bot via the placeholder `{_bot_display_name}`.
- At runtime the placeholder is replaced with the real Discord display name (falls back to `"Bot"` if unavailable).
- Used across `personalities/*/prompts.json`, `descriptions.json`, `answers.json`, plus Python sites (`agent_engine.py`, `agent_mind.py`, `postprocessor.py`, `discord_bot/canvas/*`, `behavior/commentary/commentary.py`, `roles/shaman/subroles/nordic_runes/*`, `roles/trickster/*`).
- Consequence: renaming the bot (new personality / `setnickname`) propagates everywhere without code edits.

---

## 12. Canvas UI

Interactive embed-based UI that mirrors the command suite. Implementation lives under `discord_bot/canvas/`:

- `command.py` — the `!canvas` command entry point.
- `ui.py` — `discord.ui.View` subclasses, buttons, dropdowns, navigation and error handling (`_is_unknown_interaction_error` etc.).
- `content.py` — content resolvers that read titles/descriptions from `descriptions.json` (and answers from `answers.json`).
- `state.py`, `server_config.py` — per-user / per-guild transient state and config helpers.
- `canvas_<role>.py` — one module per role (`news_watcher`, `treasure_hunter`, `trickster`, `banker`, `mc`, `juggler`, `shaman`, `behavior`, `personality`).

### 12.1 View anatomy

Typical view structure:

1. **Embed title** — injected from `descriptions.json`.
2. **Block 1** — description of the current view.
3. **Block 2** — dynamic payload (changes as dropdowns are used).
4. **Block 3** — bot follow-up comment from `answers.json`.
5. **Shared controls** — sibling buttons, config dropdown, action dropdown, `Back`, `Home`.

### 12.2 Navigation tree

```
!canvas → home/overview
home/
├── overview
roles/
├── watcher/               (news_watcher)
│   └── admin
├── hunter/
│   └── poe2/
│       └── admin/admin    (enable/disable)
├── trickster/
│   └── dice/{,admin}
├── juggler/
│   └── ring/{,admin}
├── banker/
│   ├── admin
│   └── beggar/{,admin}
├── shaman/
│   └── nordic_runes/{,admin}
└── mc/
behavior/
├── conversation
├── greetings
├── welcome
├── commentary
├── taboo
└── role_control
help/
├── personal
└── admin
```

> The historical layout placed `beggar` and `ring` under `trickster`; they now live under `banker` and `juggler` respectively. If any Canvas module still references the old location it should be migrated.

### 12.3 Multi-bot name filtering

`!canvas` supports targeting when multiple bots share a guild:

```
!canvas [section] [target] [detail]
!canvas <bot_name> [section] [target] [detail]
```

- Bot name detection: `ctx.bot.user.name.lower()`.
- Case-insensitive matching. When `section_lower == bot_name`, parameters shift left.
- `valid_sections = {"home", "role", "roles", "personal", "help", "behavior"}`.
- Unknown leading token that is neither a valid section nor this bot's name → the command is **ignored** (so other bots can handle it). See `discord_bot/canvas/command.py::cmd_canvas`.

| Command pattern             | Behavior                 |
| --------------------------- | ------------------------ |
| `!canvas`                   | All bots respond         |
| `!canvas <valid_section>`   | All bots respond         |
| `!canvas <bot_name> …`      | Only matching bot replies |
| `!canvas <unknown_name> …`  | No bot responds          |

### 12.4 Interaction flow (Trace 7)

```
!canvas received
├── bot-name filter / param shift
├── render_view()
│   ├── get_view_content()          ← descriptions.json + answers.json
│   └── build embed + View with buttons/dropdowns
└── ctx.send(embed, view)

Dropdown/Button.callback()
├── execute_canvas_action()          ← apply change
└── interaction.response.edit_message(embed, view)   ← refresh
```

---

## 13. Persistence Model

### 13.1 Per-server layout

```
databases/
└── <server_id>/
    ├── server_config.json           ← active personality, language, toggles
    ├── <personality_name>/          ← personality working copy (evolvable)
    │   ├── personality.json
    │   ├── prompts.json
    │   ├── answers.json
    │   ├── descriptions.json
    │   └── personality_backup_*.json
    ├── agent.db                     ← AgentDatabase (§13.2)
    ├── behavior.db                  ← behaviors + greetings + role toggles
    ├── banker.db, news_watcher.db, mc.db, trickster.db, shaman.db, juggler.db …
    └── treasure_hunter/             ← PoE2 per-league state
```

Shared DBs (cross-server):

- `data/global_feeds.db` — RSS feed health and shared article store.
- `databases/shared_poe2/` — PoE2 item map and price history.

### 13.2 `agent_db.py` (AgentDatabase)

Core SQLite store per server. Tracks:

- Interaction history.
- Recent dialogue window.
- Daily memory records.
- Recent memory records.
- User relationship memory (+ daily snapshots, pending refresh queue).
- Notable recollections.
- Pinned DM sessions (`pin_dm_session`).
- Fatigue counters.

Falls back to relocation-by-id when the active server is ambiguous.

### 13.3 Server initialization

`discord_bot/db_init.py::initialize_server_complete(guild, agent_config, is_startup)` is the **single unified entry point** for setting up a guild. It runs:

1. Database initialization (agent, roles, behavior, role-specific).
2. Default roles loading (enabled set).
3. News-watcher feed health bootstrap (if enabled).
4. Roles configuration migration from `behavior.db`.
5. Server-specific logging setup.
6. Mark as active server (only on startup).

Called both by `on_ready()` (per guild, `is_startup=True`) and by `on_guild_join()` (`is_startup=False`). The legacy `initialize_databases_for_guild()` is kept with a deprecation warning for backward compatibility.

---

## 14. Logging

### 14.1 Core logger (`agent_logging.py`)

- Console + rotating file handlers.
- Server-aware routing: logs are redirected to `logs/<server_id>/` when the active server is known.
- Personality-aware file naming (`logs/<server_id>/<PERSONALITY>.log`).

### 14.2 Prompt logger (`prompts_logger.py`)

Separated from general logging to preserve LLM trace fidelity:

- `get_prompts_logger(server_id=None)` returns a server-scoped logger writing to `logs/<server_id>/prompt.log` (falls back to `logs/prompt.log` when no server is known).
- All prompt logging helpers accept a `server_id` argument:
  - `log_prompt`, `log_system_prompt`, `log_user_prompt`.
  - `log_final_llm_prompt(provider, call_type, system_instruction, user_prompt, …)` — invoked by `call_llm`.
  - `log_consolidated_context`, `log_readme_enhanced_prompt`, `log_subrole_prompt`, `log_agent_response`.
- News watcher and other subprocesses pass `server_id=server_name` so even subprocess prompts land in the right folder.

Layout:

```
logs/
├── prompt.log                     ← fallback (no server context)
└── <server_id>/
    ├── prompt.log
    ├── agent.log
    └── <PERSONALITY>.log
```

---

## 15. Behaviors

Grouped under `behavior/`, mounted inside the main bot process.

- **Greetings** (`greet.py`) — reactive on `on_presence_update`, offline → online. Generates a personality-driven DM with a `ReplyButton` that pins the DM session to the guild via `pin_dm_session`.
- **Welcome** (`welcome.py`) — same skeleton, triggered by `on_member_join`.
- **Taboo** (`taboo/`) — configured per guild; on a taboo word match in a subscribed channel the bot builds a dedicated prompt:

  ```
  [memory block]
  [relationship block for the author]
  [last channel interactions]
  ----- separator -----
  [task from prompts.json → behavior.taboo]
  [golden rules]
  [message_title + user message]
  [response_title]
  ```

- **Commentary** (`commentary/`) — emits short comments about currently active roles using a prompt that includes the active-role context and a personality task.
- **"Remember that?"** — detects recall-intent keywords (from `descriptions.json`), searches notable recollections with ~50% fuzzy match (case-insensitive) and appends the match to the memory block before the LLM call.
- **Role control** — commands and Canvas controls to enable/disable roles dynamically.

---

## 16. Key Design Rules

- **Single Discord connection** — only the main bot process holds the gateway.
- **Dynamic command registration** — commands are registered from enabled modules, not a monolith.
- **Per-server isolation** — logs, SQLite DBs, personality copy and memory all scoped by `server_id`.
- **Personality-driven UX** — user-facing strings live in JSON (`prompts.json`, `answers.json`, `descriptions.json`), not in code.
- **Split responsibility** — interactive Discord logic vs. autonomous scheduled logic live in different processes.
- **Config-first activation** — `agent_config.json` gates roles; persisted per-server state refines behavior.
- **Single LLM entry point** — everything routes through `call_llm()` so fatigue, logging, fallbacks and postprocessing are consistent.
- **Placeholder-first naming** — `{_bot_display_name}` everywhere, never hardcoded names.

---

## 17. Directory Map

```text
RoleAgentBot/
├── run.py
├── agent_config.json
├── agent_engine.py         ← personality + prompt orchestration
├── agent_mind.py           ← call_llm, memory synthesis, fallbacks
├── agent_db.py             ← AgentDatabase
├── agent_roles_db.py       ← roles_config DB (next_run, frequencies)
├── agent_runtime.py        ← client factories (groq, mistral, vertex)
├── agent_fatigue_limits.py
├── agent_logging.py
├── prompts_logger.py
├── postprocessor.py
├── init_roles_config.py
├── behavior/
│   ├── greet.py
│   ├── welcome.py
│   ├── taboo/
│   ├── commentary/
│   └── db_behavior.py
├── discord_bot/
│   ├── agent_discord.py
│   ├── db_init.py
│   ├── discord_core_commands.py
│   ├── discord_role_loader.py
│   ├── discord_utils.py
│   ├── discord_http.py
│   ├── fatigue_commands.py
│   ├── entitlement_manager.py
│   └── canvas/
│       ├── command.py
│       ├── ui.py
│       ├── content.py
│       ├── state.py
│       ├── server_config.py
│       └── canvas_<role>.py …
├── roles/
│   ├── news_watcher/
│   ├── treasure_hunter/
│   ├── trickster/ (subroles/dice_game)
│   ├── shaman/    (subroles/nordic_runes)
│   ├── banker/    (subroles/beggar)
│   ├── juggler/   (subroles/ring)
│   └── mc/
├── personalities/
│   ├── rab/ (default), hans/, igorrr/, kronk/, putre/, yuki/
│   └── test.json
├── databases/               ← per-server runtime state (git-ignored)
├── data/                    ← shared caches (global feeds, etc.)
├── logs/                    ← server-scoped logs
├── manuals/                 ← human + LLM documentation
├── docker/                  ← deployment assets
└── banners/, descriptions/  ← static assets
```

---

## 18. GDPR & Privacy

Self-service data erasure and retention policies compliant with GDPR Art. 17 (right to erasure).

### 18.1 `!forget_me` command and Canvas integration

- **`discord_bot/gdpr.py`** — `ForgetMeConfirmView` provides a two-button confirmation UI (Confirm / Cancel) restricted to the requesting user.
- **Entry points**:
  - `!forget_me` prefix command (`discord_bot/discord_core_commands.py`).
  - Canvas dropdown option in the **Behavior → Conversation** section (`discord_bot/canvas/canvas_behavior.py`).
- **Flow**:
  1. User triggers the action.
  2. Bot sends an ephemeral confirmation prompt (or DM for classic context if DMs are open).
  3. On confirm, `agent_db.forget_user_across_servers()` is called with the user's `display_name` and `user_name` for redaction.
  4. Erasure runs across **all servers** where the bot operates:
     - Deletes interaction log rows keyed by `user_id`.
     - Deletes per-user relationship memories.
     - Deletes fatigue counters.
     - Redacts user name mentions in narrative LLM-generated tables (daily memory, relationship daily memory, notable recollections) to ``[redactado]``.
  5. Results are reported back to the user ephemerally.

### 18.2 Retention policies

Configured in `agent_config.json` under the `gdpr` block:

```json
"gdpr": {
  "retention_enabled": true,
  "interactions_days": 90,
  "derived_memory_days": 365,
  "run_every_hours": 24
}
```

- **`interactions_days`** — purges raw `interacciones` table rows older than N days (direct PII).
- **`derived_memory_days`** — purges date-scoped LLM summaries (`daily_memory`, `user_relationship_daily_memory`, `notable_recollections`) older than N days.
- **`run_every_hours`** — cadence of the scheduled retention sweep in `run.py`.

The sweep runs in `execute_gdpr_retention_all_servers()` via the scheduler loop.

### 18.3 Prompt log retention

- **`prompts_logger.py::purge_old_prompt_logs(max_age_days)`** — deletes `prompt.log*` files older than the configured threshold from `logs/` and all `logs/<server_id>/` subdirectories.
- **Configuration** — `agent_config.json` → `dev_options.prompt_log_retention_days` (default 15 days).
- **Safety net** — runs regardless of the `prompt_logging` flag so stale files are cleaned even after the flag is turned off.
- **Purpose** — prevents indefinite storage of user-authored content from the dev-only prompt logging feature.

### 18.4 Localized GDPR UI strings

All user-facing GDPR strings are loaded at runtime from the active personality's `answers.json` → `general` section:

| Key | Purpose |
| --- | --- |
| `forget_me_label` | Canvas dropdown label |
| `forget_me_description` | Canvas dropdown description |
| `forget_me_confirm_title` | Confirmation embed title |
| `forget_me_confirm_prompt` | Confirmation prompt text |
| `forget_me_btn_confirm` | Confirm button label |
| `forget_me_btn_cancel` | Cancel button label |
| `forget_me_result_header` | Success message header |
| `forget_me_no_data` | "No data found" message |
| `forget_me_cancelled` | Cancelled message |
| `forget_me_not_yours` | "Not your confirmation" error |
| `forget_me_timed_out` | Timeout message |
| `forget_me_dm_sent` | "DM sent" fallback message |

The loader (`gdpr.py::_load_gdpr_strings()`) uses `get_personality_message()` with English fallback constants so the flow works even without a personality loaded. Button labels are set dynamically in `ForgetMeConfirmView.__init__()` to honor the server language.

### 18.5 Help text

The `!agenthelp` command includes `!forget_me` in the **ESSENTIAL COMMANDS** section with the description "Request erasure of your personal data (GDPR Art. 17)".

---

## 19. Known Gaps / TODO

The following items exist in the codebase but warrant deeper documentation in future passes:

- **Ring accusation flow**: the `ACCUSE <username>` sentinel contract between LLM output and `juggler/ring` parser is specified in §9.4 but the exact regex and edge-cases (partial matches, nicknames vs. usernames) are not centralized — worth locking down in code comments and here.
- **Entitlement manager** (`discord_bot/entitlement_manager.py`): handles Discord entitlements (premium features); not yet described here.
- **Juggler role missions** injected into the system prompt: confirm `_get_active_roles_section` reads from `prompts.json` sections for `shaman` and `juggler` consistently with the older roles.
- **Per-server Canvas state** persistence rules between views (`canvas/state.py`) — timeout/cleanup semantics.
- **News watcher cache keys**: premise hash format and cache invalidation rules.
- **Treasure hunter PoE1 support**: reserved, not implemented.

### 19.1 Performance & Scalability Improvements (Future Implementation)

The current architecture has known concurrency limitations that need mitigation to handle high-volume message floods (10,000+ concurrent messages):

- **LLM Call Architecture**: `agent_mind.py::call_llm()` uses synchronous threading with `thread.join(timeout=30.0)` which blocks the asyncio event loop. Needs migration to fully async using `asyncio.to_thread` or HTTP async client.
- **Global Concurrency Control**: No global semaphore limits concurrent LLM calls. Current rate limiting is per-user only (`discord_utils.py::check_chat_rate_limit()`). Needs global rate limit and semaphore (e.g., max 10 concurrent messages).
- **Message Queue System**: No queue with backpressure for handling message spikes. Messages are processed immediately in `on_message()` without queuing. Needs async message queue with priority and backpressure when queue is full.
- **Database Lock Contention**: `agent_db.py` and `agent_roles_db.py` use global `threading.Lock()` which causes contention under high load. Needs connection pooling with thread-local connections and WAL mode.
- **Load Monitoring**: No metrics for active LLM calls, latency tracking, or queue depth. Needs instrumentation for observability.

**Planned Mitigation Roadmap**:
1. Add `asyncio.Semaphore(10)` in `discord_bot/agent_discord.py::_process_chat_message()`
2. Implement global rate limiting in `discord_utils.py` (e.g., 50 messages/second)
3. Create `call_llm_async()` using `asyncio.to_thread()` in `agent_mind.py`
4. Implement message queue with backpressure in new `discord_bot/message_queue.py`
5. Replace global DB locks with connection pooling and WAL mode
6. Add metrics for active calls, latency, and queue depth

When any of these is specified more precisely in code, extend the corresponding section above rather than adding historical "refactor note" sections at the bottom.
