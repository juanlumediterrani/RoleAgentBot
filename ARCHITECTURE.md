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
└── commentary/                        ← role-aware commentary
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
| `Scheduled role task`     | Autonomous logic run on a timer as a `JobScheduler` job (in-process) | `news_watcher`, `treasure_hunter`, `banker`, plus the subrole ticker (`beggar`, `ring`) |

---

## 3. Entry Points

### 3.1 `run.py` (current entry point)

System orchestrator. Docker `CMD ["python", "run.py"]`. As of 0.6.2, `run.py` is intentionally
slim — it owns no per-role scheduling logic of its own:

- `main()` loads `agent_config.json` (with optional schema validation).
- Runs the **global RSS feed health check** once at startup
  (`roles/news_watcher/global_feed_health.py`).
- Instantiates `RunSupervisor` (`run_supervisor.py`) and registers:
  - The **MC actor** (`Supervisor`-managed persistent coroutine with restart policy, §20.3).
  - The **memory maintenance jobs** on `RunSupervisor.job_scheduler`:
    `daily_memory_summary`, `weekly_personality_evolution`, `recent_memory_summary`,
    `relationship_memory_refresh`, `gdpr_retention`.
- `asyncio.gather(discord_bot())`: only the in-process Discord client is gathered — there is no
  longer a separate `scheduler()` loop. The bot's `on_ready` (§3.2) registers the Discord-bound
  jobs onto the same `RunSupervisor.job_scheduler`, so the entire process runs on a **single
  `JobScheduler` instance** (single-scheduler architecture).

> **0.6.2 invariant**: there are no subprocesses anywhere in the runtime. There is exactly one
> `JobScheduler` driving every periodic task (memory, MC actor, subrole ticker, news_watcher,
> treasure_hunter, banker, database_cleanup) and one `Supervisor` for long-lived actors (MC).
> The legacy `launch_role()` subprocess launcher and `scheduler()` loop were removed.

### 3.2 `discord_bot/agent_discord.py`

Main Discord runtime (in-process, same asyncio loop as `RunSupervisor`):

- Builds the Discord client with limited intents.
- `on_ready()` calls `initialize_server_complete(guild, agent_config, is_startup=True)` per guild, then:
  - Registers **core commands** (`register_core_commands`).
  - Registers **role commands dynamically** (`register_all_role_commands` → `discord_role_loader._try_register_role`).
  - Starts the **chat message queue** (`ChatMessageQueue`, §19.1) via `get_chat_queue().start(_process_chat_message)`.
  - Starts the unified **JobScheduler-based scheduler** (`get_discord_scheduler().start()`) which
    owns the in-bot periodic tasks (subrole task ticker, treasure hunter scheduler, news watcher
    scheduler, DB cleanup). When that scheduler fails to start, the legacy `@tasks.loop` fallbacks kick in.
- `on_guild_join()` calls `initialize_server_complete(..., is_startup=False)`.
- `on_message()` performs taboo detection, applies the global rate limiter, and **enqueues** the
  message into `ChatMessageQueue` instead of awaiting `_process_chat_message` directly.

### 3.3 `agent_engine.py`

Personality + prompt orchestration:

- `_cargar_personalidad(server_id)` reads `databases/<server_id>/server_config.json`, copies the base personality into the server folder on first use, then loads the merged personality JSON (see §5).
- `_build_system_prompt(personality, server_id)` assembles identity + style + examples + active role missions.
- `_get_active_roles_section(server_id)` injects the missions of enabled roles into the system prompt.
- Exposes helpers for subrole internal prompts (e.g. beggar, ring).

### 3.4 `agent_mind.py`

LLM layer and memory synthesis:

- `call_llm(...)` — **blocking** entry point for sync contexts. Internally submits the Vertex AI
  SDK call to a shared `ThreadPoolExecutor` (`_VERTEXAI_EXECUTOR`).
- `call_llm_async(...)` — **awaitable** entry point for asyncio contexts (Discord, schedulers).
  Wraps `call_llm` with `asyncio.to_thread` plus `asyncio.wait_for`, so the event loop is never
  blocked. **All Discord-facing call sites use this variant.** See §8.2 for the fallback chain.
- Both share the `background: bool` parameter to select foreground (30 s) vs background (120 s)
  Vertex timeout.
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

- `news_watcher` (hourly) — Discord commands + scheduled subprocess.
- `treasure_hunter` (hourly; PoE2) — Discord commands + scheduled subprocess.
- `trickster` — Discord commands; subrole: `dice_game` (UI-driven, no timer).
- `shaman` — Discord commands; subrole: `nordic_runes` (interactive).
- `mc` (integrated, no interval) — voice features; runs as a `Supervisor` actor (§20.3).
- `banker` (24 h) — Discord commands + scheduled subprocess; subrole: `beggar` (12 h, in-bot ticker).
- `juggler` — System-prompt-only role (no `*_discord.py`); subrole: `ring` (24 h, in-bot ticker, accusation flow §9.4).
- `scholar` — System-prompt-only role (no `*_discord.py`); used in chat flow when the LLM emits a
  Wikipedia sentinel (§7.2). Performs Wikipedia fetch + second LLM call.

> **Note vs. older docs:** `beggar` moved from `trickster` → `banker`; `ring` moved from `trickster` → `juggler`; `nordic_runes` moved into the new `shaman` role; `scholar` is the latest addition (Wikipedia knowledge).

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

### 5.5 Personality development tools

`tools/compare_personality.py` helps when creating or translating personalities:

- **`translate <personality> <lang>`** — compares `<personality>/<lang>` against `<personality>/es-ES` to detect missing keys, empty values, list length mismatches, and extra keys. Useful for verifying translation completeness.
- **`extend <personality>`** — compares `<personality>/es-ES` against `rab/es-ES` (canonical reference) to identify missing sections when extending a personality with new roles/features.

The script recursively walks all JSON files (including `descriptions/*.json`) and reports:
- Missing files in the target
- Missing keys (present in reference, absent in target)
- Empty values (strings, lists, dicts)
- List length mismatches (with ratio)
- Extra keys (present only in target)
- JSON syntax errors

Example usage:

```bash
python3 tools/compare_personality.py extend yuki
python3 tools/compare_personality.py translate rab en-US
```

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
    └── record_pending_greeting() + log interaction
```

`behavior/welcome.py` follows the same skeleton for `on_member_join`.

### 7.4 Greeting DM reply

Pending DM greetings are tracked in-memory by `behavior/greet.py` (`_pending_greeting_replies`). When a user sends a DM or messages in a guild, `_process_chat_message()` calls `mark_user_replied()` which clears the pending entry, allowing greeting cooldowns to reset naturally once the user engages.

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

The pipeline is exposed in two flavours:

- `call_llm(...)` — **blocking**. For sync contexts (background workers,
  thread-isolated tasks). Internally submits the SDK call to a shared
  `ThreadPoolExecutor` (`_VERTEXAI_EXECUTOR`, `max_workers=10`) and waits via
  `Future.result(timeout=...)`.
- `call_llm_async(...)` — **awaitable**. For asyncio contexts (Discord event
  handlers, schedulers). Wraps `call_llm` with `asyncio.to_thread` plus an
  `asyncio.wait_for` outer safety timeout, so the event loop and Discord
  heartbeat are never blocked.

```text
call_llm_async()                         call_llm()
├── asyncio.wait_for(outer_timeout)      ├── Attempt 1 — Vertex AI (gemini-2.5-flash)
│   └── asyncio.to_thread(call_llm) ────►│   └── _invoke_vertexai()
│                                        │       └── _VERTEXAI_EXECUTOR.submit(...).result(timeout)
│                                        │           foreground=30 s | background=120 s
│                                        │
│                                        ├── on None  → Attempt 2 — Groq (llama-3.3-70b-versatile)
│                                        │   └── _call_groq_fallback()
│                                        │
│                                        └── on error → Attempt 3 — Mistral (mistral-medium-latest)
│                                            └── _call_mistral_fallback()
└── on TimeoutError → _get_fallback_response(critical)
```

The `background: bool` parameter selects the Vertex timeout (30 s for
foreground/chat, 120 s for memory/personality-evolution tasks). If all three
providers fail the function returns an empty/fallback string and the caller
decides how to degrade (critical vs. tolerant).

### 8.3 Post-processing

`postprocessor.py::postprocess_response()` is intentionally minimal:

- Rejects internal-thinking leaks (returns empty string so the caller can fallback).
- Basic whitespace/text sanitization.
- **No length truncation** — responses are preserved at their natural length (`max_chars` kept only for signature compatibility).

---

## 9. Roles and Subroles

### 9.1 Role registration

Two distinct registration paths exist depending on whether a role exposes Discord commands:

**Roles with Discord commands** (`discord_bot/discord_role_loader.py::ROLE_REGISTRY`):

- Canonical registry: `news_watcher`, `treasure_hunter`, `trickster`, `banker`, `shaman`.
- `mc` is registered separately via `MC_REGISTRY` (always loaded if enabled).
- For each enabled role, `_try_register_role(bot, module_path, func_name, personality, agent_config)`
  imports the `<role>_discord.py` module and invokes its command-registration function. Most slash
  commands are now deprecated in favour of Canvas (§12); the legacy commands log a warning.

**System-prompt-only roles** (no `*_discord.py`):

- `juggler` — provides ring sentinel handling and prompt missions; never registers commands.
- `scholar` — provides Wikipedia/README handling and prompt missions; invoked by `agent_discord.py`
  when the LLM response starts with the `WIKIPEDIA <topic>` sentinel (§7.2).

These roles still appear under `agent_config.json::roles`, contribute to `_get_active_roles_section`
(prompt assembly, §5.2), and may declare subroles, but do not register top-level Discord commands.

### 9.2 Periodic role execution (single-scheduler model, 0.6.2)

Every periodic role task in the bot runs as a coroutine job on a **single
`JobScheduler` instance** (`RunSupervisor.job_scheduler`). There are no subprocesses, no
duplicate schedulers, and no role-script CLI entry points kept alive by the runtime.

The jobs are registered in two waves:

1. **At startup** (`run.py::main` → `RunSupervisor.register_memory_jobs`):
   - `daily_memory_summary` (1 h tick, per-server staggered).
   - `weekly_personality_evolution` (6 h tick, per-server staggered).
   - `recent_memory_summary` (4 h).
   - `relationship_memory_refresh` (1 h).
   - `gdpr_retention` (configurable, default 24 h).

2. **On Discord ready** (`agent_discord.py::on_ready` → `DiscordScheduler.start()` with
   `external_scheduler=RunSupervisor.job_scheduler`):
   - `discord_task_scheduler` (1 min) — drives the **subrole ticker**: iterates guilds, calls
     `get_due_subrole_tasks_for_server(server_id)`, executes due subroles in-process via
     `execute_subrole_internal_task(...)` (e.g. `roles/banker/subroles/beggar/beggar_task.py`),
     and updates `next_run = now + frequency_hours` per server.
   - `treasure_hunter_global_scheduler` (1 min ticker, runs on `interval_hours` from config) —
     `roles/treasure_hunter/treasure_hunter.py::ejecutar_mision_treasure_hunter`.
   - `news_watcher_global_scheduler` (1 min ticker, runs on `interval_hours`) — kicks
     `roles/news_watcher/news_downloader.py::download_all_feeds_global` in the background.
   - `news_watcher_subscription_processor` (1 min ticker, runs on global + per-server intervals)
     — `roles/news_watcher/subscription_processor.py::process_server_subscriptions`.
   - `database_cleanup` (24 h) — purges old interactions from the legacy SQLite DB.
   - `banker_global_scheduler` (24 h) — `roles/banker/banker.py::banker_task`: creates wallets,
     initializes the dice-game pot, distributes daily TAE.

> **Per-server enable/disable** is enforced inside each job: jobs read
> `server_config.json` via `discord_bot/canvas/server_config.py::is_role_enabled` and skip
> servers where the role is locally disabled. The single global scheduler stays simple; per-server
> gating lives next to the role logic.

> **DiscordScheduler is a registration helper, not a separate runtime.** It exposes the
> Discord-bound jobs as bound methods on its instance, but its `start()` method registers them
> on whatever `JobScheduler` it was constructed with. In production, that scheduler is
> `RunSupervisor.job_scheduler`; in standalone tests, it can fall back to creating its own.

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

- Global scheduled price watcher (controlled by `agent_config.json`), currently implemented for **Path of Exile 2**.
- Keeps a global `item_name → item_id` map and per-league price history stored in item-specific tables.
- Non-blocking subprocess updates prices with cooperative yielding; notifications are generated through `call_llm()` using role-specific task prompts.
- Frequency is configured globally via `roles.treasure_hunter.interval_hours` in `agent_config.json` (no per-server frequency control).

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

#### `scholar`

- System-prompt-only role: contributes a `CURRENT DUTY - SCHOLAR` mission section so the LLM
  knows it can answer encyclopaedic questions and may request Wikipedia content.
- **Wikipedia sentinel flow** (Trace 11):
  1. User asks a question. First LLM pass returns either a direct answer or
     `WIKIPEDIA <topic>` (URL-format, underscores instead of spaces).
  2. `agent_discord.py::_process_chat_message` detects the sentinel, fetches the article extract
     via `roles/scholar/wikipedia_fetcher.py` (cached in `roles/scholar/wikipedia_cache.db`).
  3. A second LLM call (`call_llm_async`, `call_type="wikipedia_enhanced"`) is issued with the
     user's question + the Wikipedia extract attached to the system prompt.
- A parallel `README` sentinel triggers `_build_readme_prompt` to inject the user-facing manual
  (per-language `manuals/<lang>/README_USER.md`) into the second pass — used when the user asks
  about bot capabilities (§9.4 README sentinel handler).

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

### 12.4 Canvas Shortcuts

The Canvas home view supports up to 5 configurable shortcut buttons that provide quick access to frequently used roles and subroles. This feature is admin-only and configured via the settings dropdown.

#### 12.4.1 Data model

Shortcuts are stored per-server in `server_config.json` under the `canvas.shortcuts` key:

```json
{
  "canvas": {
    "shortcuts": [
      {
        "id": 1,
        "enabled": true,
        "label": "Trickster - Dice",
        "target_role": "trickster",
        "target_subrole": "dice"
      },
      ...
    ]
  }
}
```

Each shortcut has:
- `id`: Position (1-5)
- `enabled`: Whether the shortcut is active
- `label`: Display text (cleaned of bold formatting and tree symbols)
- `target_role`: Target role name (e.g., "trickster")
- `target_subrole`: Optional target subrole (e.g., "dice")

#### 12.4.2 Subrole mapping

Some subroles use different names in the JSON configuration versus the Canvas surface names. A mapping table ensures correct navigation:

```python
SUBROLE_TO_SURFACE = {
    "nordic_runes": "runes",
    "dice_game": "dice",
    "poe2": "league",
    "beggar": "beggar",
}
```

#### 12.4.3 Button implementation

`CanvasShortcutButton` reuses existing navigation logic:

- For roles: Uses `CanvasRoleButton` logic via `_build_canvas_role_view`
- For subroles: Uses `CanvasRoleDetailButton` logic via `_build_canvas_role_detail_view`

This ensures consistency with the standard role navigation system.

#### 12.4.4 Configuration UI

The configuration flow uses a single ephemeral message with two modes:

**List mode**: Shows 5 buttons (one per shortcut position). Each button displays the current shortcut label or `#N` if unconfigured. Clicking enters config mode.

**Config mode**: Shows a dropdown to select a role/subrole and Confirm/Cancel buttons. The dropdown options use personality descriptions for labels. When a selection is made, the dropdown is recreated with the selected value shown in the placeholder.

All messages are injected from `descriptions.json` under `help_menu.shortcuts_messages` with per-personality translations.

#### 12.4.5 Label resolution

Shortcut labels are resolved in this order:

**For roles:**
1. Role-specific `button` field (e.g., `descriptions.json["role_descriptions"]["banker"]["button"]`)
2. Fallback to generated label (role name)

**For subroles:**
1. Subrole-specific `button` field (e.g., `descriptions.json["role_descriptions"]["trickster"]["dice_game"]["button"]`)
2. Fallback to subrole-specific `title` field if `button` doesn't exist
3. Fallback to `subrole_buttons` using surface name mapping
4. Final fallback to generated label (role name + subrole name)

Labels are cleaned of bold formatting (`**`) and tree symbols (`└`) before being used as button text.

### 12.5 Interaction flow (Trace 7)

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

```text
databases/
└── <server_id>/
    ├── server_config.json           ← active personality, language, toggles
    ├── <personality_name>/          ← personality working copy (evolvable)
    │   ├── personality.json
    │   ├── prompts.json
    │   ├── answers.json
    │   ├── descriptions.json
    │   └── personality_backup_*.json
    ├── state.json                   ← AgentState (NoSQL canonical store, §13.2)
    ├── interactions.jsonl           ← JsonlRingBuffer (§20.2)
    ├── memory_*.jsonl               ← daily/recent/relationship memory streams
    ├── recollections.jsonl
    ├── banker.db                    ← Banker SQLite (only legacy SQLite that remains)
    ├── agent.db                     ← AgentDatabase (DEPRECATED, kept for migration only)
    └── treasure_hunter/             ← PoE2 per-league state
```

Shared / cross-server stores:

- `data/global_feeds.db` — RSS feed health and shared article store.
- `databases/shared_poe2/` — PoE2 item map and price history.
- `databases/global/news/*.jsonl` — global news article tracking (NoSQL).

### 13.2 NoSQL canonical store (`persistence/agent_state.py`)

In 0.6.1+, the per-server canonical store is **NoSQL** (JSON + JSONL ring buffers) accessed through
`AgentState`. See §20.2 for the full module list. `AgentState` provides the same logical surface
as the legacy `AgentDatabase` (interactions, recent dialogue window, daily/recent/relationship
memory, notable recollections, pinned DM sessions, fatigue counters) but persists to disk via:

- `persistence/json_store.py` — atomic, schema-versioned JSON documents with backups.
- `persistence/jsonl_store.py` — append-only ring buffers with bounded retention.

`AgentState` instances are cached per server (`get_agent_state(server_id)`).

### 13.3 Legacy `agent_db.py` (`AgentDatabase`)

`agent_db.py::AgentDatabase` is **legacy SQLite** retained for:

- Read paths still used by older code that has not yet been migrated to `AgentState`.
- A 1-week post-migration validation window (see §20.9).

New code MUST go through `AgentState`. `AgentDatabase` writes are no longer the source of truth.
Its SQLite file (`databases/<server_id>/agent.db`) is configured with WAL +
`busy_timeout=5000` + `synchronous=NORMAL` for safety during the deprecation window.

### 13.4 Banker — the lone SQLite holdout

Banker remains on SQLite by design (`databases/<server_id>/banker.db`, managed by
`roles/banker/db_banker_core.py`). The decision is documented in §20.9: banker's transactional
semantics over wallets/transfers benefit from SQLite's atomicity guarantees, and the migration
cost-benefit was deemed unfavourable.

### 13.5 Server initialization

`discord_bot/db_init.py::initialize_server_complete(guild, agent_config, is_startup)` is the
**single unified entry point** for setting up a guild. It runs:

1. Initialize NoSQL stores (`AgentState`, role-specific NoSQL stores).
2. Initialize remaining SQLite stores (banker; legacy AgentDatabase if not yet retired).
3. Default roles loading (enabled set).
4. News-watcher feed health bootstrap (if enabled).
5. Server-specific logging setup.
6. Mark as active server (only on startup).

Called both by `on_ready()` (per guild, `is_startup=True`) and by `on_guild_join()`
(`is_startup=False`). The legacy `initialize_databases_for_guild()` is kept with a deprecation
warning for backward compatibility.

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
│   └── commentary/
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

### 19.1 Concurrency & Backpressure Architecture

The bot is designed to absorb message floods (≫1 000 concurrent inbound
messages) without blocking the Discord gateway heartbeat or exhausting memory.
Defense in depth is enforced at six layers, ordered from outermost to innermost:

```text
Discord on_message
    │
    ▼
[1] check_global_chat_rate_limit()        ← discord_bot/discord_utils.py
    │  Token bucket: capacity=50, refill=50 msg/s. Drops if empty.
    ▼
[2] check_chat_rate_limit(user_id)        ← discord_bot/discord_utils.py
    │  Per-user 3 s cooldown.
    ▼
[3] ChatMessageQueue.enqueue(message)     ← discord_bot/message_queue.py
    │  Bounded asyncio.Queue (maxsize=100). Drops on overflow.
    │  Drained by 8 worker tasks running _process_chat_message.
    ▼
[4] async with _LLM_SEMAPHORE: ...        ← discord_bot/agent_discord.py
    │  asyncio.Semaphore(10) caps concurrent LLM orchestrations.
    ▼
[5] await call_llm_async(...)             ← agent_mind.py
    │  asyncio.wait_for(asyncio.to_thread(call_llm), outer_timeout)
    ▼
[6] _VERTEXAI_EXECUTOR (max_workers=10)   ← agent_mind.py
       Future.result(timeout=30 s | 120 s) per provider.
       Falls back: Vertex → Groq → Mistral → canned response.
```

**Key implementation files**:

- `agent_mind.py` — `call_llm`, `call_llm_async`, `_invoke_vertexai`, the shared
  `concurrent.futures.ThreadPoolExecutor` (`_VERTEXAI_EXECUTOR`), and the
  fallback chain.
- `discord_bot/discord_utils.py` — `check_chat_rate_limit` (per user) and
  `check_global_chat_rate_limit` (global token bucket).
- `discord_bot/message_queue.py` — `ChatMessageQueue` with bounded queue and
  worker pool. Started in `on_ready`, drained on shutdown.
- `discord_bot/agent_discord.py` — `_LLM_SEMAPHORE`, the wired-up `on_message`
  → `enqueue` handoff, and `_process_chat_message` running under workers.
- `agent_metrics.py` — thread-safe counters / gauges / latency rings consumed
  by all the layers above.

**Database concurrency**: SQLite databases use `journal_mode=WAL` with
`busy_timeout=5000` so that readers and writers do not block each other under
load (`agent_db.py`, `news_watcher/global_news_db.py`, plus the per-role DBs
in `roles/treasure_hunter/`). Per-instance `threading.Lock()` is retained
within each DB class to serialise multi-statement operations on a single
connection.

**Observability**: `agent_metrics.py` exposes `incr`, `set_gauge`, and
`record_latency` to the hot paths. Snapshots via `get_metrics()` /
`format_metrics()` include:

- `llm.vertexai.{ok,timeout,error,empty}`, `llm.groq.{ok,error}`,
  `llm.mistral.ok`, `llm.async.outer_timeout`.
- `chat_queue.{enqueued,dropped,processed,failed}` and gauge `chat_queue.size`.
- `rate_limit.global.{allowed,dropped}`.
- Per-`call_type` latency stats (`avg`, `p50`, `p95`, `p99`, `max`) for each
  provider, e.g. `vertexai:think`, `groq:scholar`.

**Tuning knobs** (constants, not config — change in code):

- `agent_mind.py::VERTEXAI_TIMEOUT_FOREGROUND` (30 s) /
  `VERTEXAI_TIMEOUT_BACKGROUND` (120 s).
- `agent_mind.py::_VERTEXAI_EXECUTOR` `max_workers` (10).
- `discord_utils.py::GLOBAL_CHAT_RATE_CAPACITY` (50) /
  `GLOBAL_CHAT_RATE_REFILL_PER_SEC` (50.0).
- `agent_discord.py::_LLM_SEMAPHORE` size (10).
- `message_queue.py::ChatMessageQueue` `maxsize` (100) / `num_workers` (8).

---

## 20. NoSQL + Supervisor + JobScheduler Architecture (2026 Refactor)

### 20.1 Overview

The bot has been refactored from SQLite + subprocess-based architecture to NoSQL (JSON/JSONL) + in-process Supervisor + JobScheduler. This eliminates ~5000 LOC of subprocess management code and provides unified process management with restart policies, timeouts, semaphores, circuit breakers, and observability.

### 20.2 Persistence Layer (NoSQL)

**Modules:**
- `persistence/json_store.py`: Thread-safe atomic JSON document storage with schema versioning and backups
- `persistence/jsonl_store.py`: Append-only JSONL with rotation and retention limits
- `persistence/agent_state.py`: Facade for agent state using NoSQL backend (same API as AgentDatabase)
- `agent_memory_nosql.py`: NoSQL backend for agent memory (state.json + interactions.jsonl)
- `global_news_nosql.py`: NoSQL backend for global news tracking
- `role_configs_nosql.py`: NoSQL backend for role configurations (except banker)
- `poe2_nosql.py`: NoSQL backend for POE2 price history and items catalog

**File Structure:**
```
databases/shared/
├── news/
│   ├── seen.json              # Global news tracking
│   └── feeds_health.json      # Feed health status
├── poe2/
│   ├── prices_latest.json     # Latest prices per item
│   ├── prices_history.jsonl   # Price history (rotating)
│   └── items_catalog.json     # Items catalog
└── scheduler_state.json       # Job scheduler state persistence

databases/{server_id}/
├── state.json                 # Agent state (daily/recent memory, relationships, recollections)
└── interactions.jsonl         # Interaction log (rotating)
```

**Retention Limits:**
- Daily memory: 14 paragraphs
- Recent memory: 12 paragraphs
- Recollections: 50 entries
- Relationships: 200 entries
- Interactions: 250 entries (last 90 days)
- POE2 price history: 30 days
- News history: 30 days

### 20.3 Process Management (Supervisor + JobScheduler)

**Modules:**
- `supervisor/supervisor.py`: Actor manager with restart policies and backoff
- `supervisor/scheduler.py`: Async job scheduler with retries, timeouts, semaphores, circuit breakers
- `supervisor/heartbeat.py`: Health monitoring for actors
- `supervisor/policies.py`: Restart policies (permanent, transient, one-shot)
- `supervisor/ipc.py`: Unix-socket IPC for runtime control
- `supervisor/scheduler_state.py`: Scheduler state persistence (next_run, status, last_shutdown)
- `run_supervisor.py`: RunSupervisor wrapper integrating Supervisor + JobScheduler
- `rabctl.py`: CLI tool for IPC control (status, trigger, pause, resume, restart, shutdown, health, metrics)

**Runtime Topology (0.6.2 — single-scheduler):**

```text
run.py main()                                       (Docker CMD: python run.py)
├── RunSupervisor (in-process)
│   ├── Supervisor (actors)
│   │   └── mc (Music Controller — persistent actor with restart policy)
│   ├── job_scheduler  ← THE SINGLE JobScheduler instance for the whole bot
│   │   ├── (registered at startup by RunSupervisor.register_memory_jobs)
│   │   │   ├── daily_memory_summary        (tick=1h, per-server staggered)
│   │   │   ├── recent_memory_summary       (4h)
│   │   │   ├── relationship_memory_refresh (1h)
│   │   │   ├── weekly_personality_evolution (tick=6h, per-server staggered)
│   │   │   └── gdpr_retention              (configurable, default 24h)
│   │   └── (registered on Discord on_ready by DiscordScheduler.start with
│   │        external_scheduler=RunSupervisor.job_scheduler)
│   │       ├── discord_task_scheduler           (1min, subrole ticker)
│   │       ├── treasure_hunter_global_scheduler (1min ticker, runs on interval_hours)
│   │       ├── news_watcher_global_scheduler    (1min ticker, runs on interval_hours)
│   │       ├── news_watcher_subscription_processor (1min, per-server intervals)
│   │       ├── database_cleanup                 (24h)
│   │       └── banker_global_scheduler          (24h)
│   ├── IPC Server (/tmp/rab_ipc.sock)  — see §20.5 (rabctl)
│   └── Scheduler State Persistence    (next_run, status, last_shutdown)
└── discord_bot() (in-process, same asyncio loop)
    ├── ChatMessageQueue (8 workers, maxsize=100, §19.1)
    ├── _LLM_SEMAPHORE (max 10 concurrent orchestrations, §19.1)
    ├── DiscordScheduler (registration helper; uses RunSupervisor.job_scheduler)
    └── on_message → enqueue → workers → call_llm_async (§8.2)
```

There are **no subprocesses**, **no `@tasks.loop` legacy schedulers**, and **no second
`JobScheduler` instance**. The legacy `run.py::launch_role` and `scheduler()` loop, plus the
five `@tasks.loop` schedulers in `agent_discord.py`, were removed in 0.6.2.

**JobScheduler Features:**
- Jobs with schedules (interval, cron-like)
- Retry policies with backoff
- Timeout enforcement
- Semaphore for concurrency control
- Circuit breaker for fault tolerance
- Pause/resume/trigger runtime control
- Prometheus metrics export

### 20.4 Migration Scripts

- `migrate_sqlite_to_json.py`: One-shot SQLite → NoSQL migration for global databases
- `migrate_agent_to_nosql.py`: One-shot agent_*.db → state.json migration with backup

### 20.5 CLI Control (rabctl)

```bash
# Get status
rabctl status

# Trigger a job manually
rabctl trigger daily_memory_summary

# Pause/resume a job
rabctl pause recent_memory_refresh
rabctl resume recent_memory_refresh

# Restart an actor
rabctl restart mc

# Shutdown supervisor
rabctl shutdown

# Health check (for systemd)
rabctl health  # exit 0/1

# Get Prometheus metrics
rabctl metrics
```

### 20.6 Systemd Unit

See `roleagentbot.service` for systemd configuration:
- `Restart=on-failure` with `RestartSec=10`
- Health check via `rabctl health`
- Metrics exposed via `rabctl metrics`

### 20.7 Roadmap Completion Status

**Fase A** — Infrastructure: COMPLETED ✓

- `persistence/` + `supervisor/` with tests (105 tests passing).

**Fase B** — NoSQL Volatiles: COMPLETED ✓

- `global_news.db` → NoSQL.
- `poe2STDpricehistory.db` → NoSQL.
- `PoE2Standard.db` → NoSQL.
- `global_news_db` replaced with `global_news_nosql`.

**Fase C** — Process Refactor: COMPLETED ✓ (0.6.2)

- 5 `@tasks.loop` → `JobScheduler` (`discord_bot/discord_scheduler.py`).
- Memory maintenance jobs in `RunSupervisor.job_scheduler`.
- Persistent roles (`mc`) → `Supervisor`-managed actors.
- `scheduler_state.json` persistence.
- IPC + `rabctl.py`.
- **0.6.2 finalisation**: `run.py::launch_role` and the slim `scheduler()` loop were
  removed. `banker_task()` is now a job on the shared scheduler. `DiscordScheduler` was
  refactored to register its jobs onto `RunSupervisor.job_scheduler` via the new
  `external_scheduler` parameter, eliminating the second `JobScheduler` instance and the
  duplicate news_watcher/treasure_hunter execution paths. The runtime now has exactly one
  task launcher (`RunSupervisor.job_scheduler`) and zero subprocesses.

**Fase D** — Agent Memory NoSQL: COMPLETED ✓ (validation period)

- `persistence/agent_state.py` is the canonical facade.
- Table-by-table migration to `state.json` + `interactions.jsonl`.
- One-shot `agent_*.db → state.json` converter (`migrate_agent_to_nosql.py`).
- `agent_db.py` deletion is pending the validation window in §20.9.

**Fase E** — Roles NoSQL: COMPLETED ✓ (banker exempted by design)

- Roles migrated to NoSQL except `banker` (transactional SQLite, §13.4).
- `agent_roles_db.py` is now a thin compatibility facade that delegates to NoSQL stores.

**Fase F** — Observability: COMPLETED ✓

- Prometheus metrics per job (via `supervisor/scheduler.py`).
- Healthcheck: `rabctl health` → exit 0/1.
- Systemd unit + `Restart=on-failure`.
- Documentation in ARCHITECTURE.md.

**Fase G** — Concurrency & Backpressure (0.6.2): COMPLETED ✓

- `agent_mind.call_llm_async` + shared `_VERTEXAI_EXECUTOR` (`concurrent.futures`) replaces the
  old `threading.Thread + thread.join` blocking pattern. Discord heartbeat is no longer blocked.
- `discord_utils.check_global_chat_rate_limit` token bucket (50 msg/s) ahead of per-user cooldown.
- `discord_bot/agent_discord.py::_LLM_SEMAPHORE` caps concurrent chat LLM orchestrations at 10.
- `discord_bot/message_queue.py::ChatMessageQueue` bounded queue (maxsize=100) with 8 workers;
  drops on overflow rather than accumulating an unbounded coroutine backlog.
- SQLite WAL + `busy_timeout=5000` on all remaining SQL stores.
- `agent_metrics.py` thread-safe counters/gauges/latency rings consumed by all hot paths.
- Full architecture documented in §19.1.

### 20.8 Migration Guidelines

**For existing deployments:**
1. Backup databases: `cp -r databases databases.bak`
2. Run migration: `python3 migrate_sqlite_to_json.py`
3. Run agent migration: `python3 migrate_agent_to_nosql.py --db-path databases/{server_id}/agent_{server_id}.db --server-id {server_id}`
4. Install systemd unit: `sudo cp roleagentbot.service /etc/systemd/system/`
5. Enable service: `sudo systemctl enable roleagentbot`
6. Start service: `sudo systemctl start roleagentbot`
7. Verify health: `./rabctl health`
8. Check metrics: `./rabctl metrics`

**Rollback:**
1. Stop service: `sudo systemctl stop roleagentbot`
2. Restore databases: `rm -rf databases && mv databases.bak databases`
3. Start service: `sudo systemctl start roleagentbot`

### 20.9 Known Limitations & Open Items (0.6.2)

**By design:**

- Banker role remains in SQLite (transactional semantics over wallets/transfers — see §13.4).
- Markdown lint warnings throughout this file (MD031/MD032/MD040/MD060) are pre-existing and
  intentionally untouched to keep refactor diffs focused on substantive content.

**Pending validation (deletion deferred):**

- `agent_db.py` (`AgentDatabase`) — full removal pending the post-migration validation window.
- `agent_roles_db.py` further reduction — pending validation that all callers go through NoSQL.

**Single-launcher convergence — DONE in 0.6.2.** `run.py::launch_role`, `scheduler()`, and the
five `@tasks.loop` schedulers in `agent_discord.py` were deleted. The runtime has exactly one
`JobScheduler` (`RunSupervisor.job_scheduler`) hosting both the memory maintenance jobs and the
Discord-bound jobs (registered on `on_ready` via `DiscordScheduler.start(external_scheduler=...)`).
`run.py` is now a thin entry point: load config → start RunSupervisor → run `discord_bot()`.

**Optional next step — single entry point:** `run.py` could be reduced to a 5-line shim that
delegates to `run_supervisor.py::main()`, or `run_supervisor.py` could be promoted to be the
Docker `CMD`/systemd `ExecStart`. Today both work; the choice is purely cosmetic.

**Cohesion follow-ups (not blocking, see §9.1):**

- `agent_discord.py` still detects the `WIKIPEDIA` and `README` sentinels emitted by the LLM.
  This logic could move into `roles/scholar/` for full role cohesion.
- Several `discord_bot/canvas/canvas_*.py` modules import role internals (DBs, message helpers).
  Each role could expose a public Canvas-facing API to keep its internals private.
- Thin role scripts `roles/juggler/juggler.py`, `roles/shaman/shaman.py`, `roles/trickster/trickster.py`,
  `roles/scholar/scholar.py` no longer have any scheduled callers; only their helper functions
  (system prompts, sentinel handlers) are imported. Consider renaming/dropping the empty `main()`
  entry points to make the dead code obvious.

**Test coverage gaps:**

- E2E tests for news_watcher + PoE2 (medium priority).
- No automated load-test harness for the §19.1 backpressure layers; smoke-tested manually with
  a `ChatMessageQueue(maxsize=3, num_workers=2)` + 5-message flood (see refactor session).

