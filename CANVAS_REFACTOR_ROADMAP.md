# Canvas-First Refactoring Roadmap

## Executive Summary

**Objective:** Migrate from Discord-first command architecture to Canvas-first UI architecture.

**Goal:** Simplify the codebase by making Canvas (`!canvas`) the primary user interface, keeping only 8 essential Discord commands (16%) and deprecating 40 commands (80%).

**Key Principle:** Simplification, not creation. The Canvas UI infrastructure already exists - we only need to remove redundant Discord commands that duplicate Canvas functionality.

---

## Success Criteria

- ✅ Users can complete all role workflows through Canvas UI
- ✅ Only 8 essential Discord commands remain functional
- ✅ 40 deprecated commands show warnings directing users to Canvas
- ✅ Personality messages reference Canvas instead of deprecated commands
- ✅ No loss of functionality - everything available via `!canvas`
- ✅ Bot identity management commands still work for admins

---

## Phase 1: Command Inventory & Categorization

### Core Commands (discord_core_commands.py)

| Command | Category | Rationale |
|---------|----------|-----------|
| `canvas` | **ESSENTIAL** | Primary entry point for Canvas UI |
| `agenthelp` | **DEPRECATE** | Help available in Canvas UI |
| `readme` | **DEPRECATE** | Documentation available in Canvas UI |
| `testpersonalityevolution` | **ESSENTIAL** | Development tool, not user-facing |
| `setnickname` | **ESSENTIAL** | Admin utility for bot identity |
| `identity` | **DEPRECATE** | Info available in Canvas UI |
| `setpersonality` | **ESSENTIAL** | Admin utility for personality switching |
| `role<personality>` | **ESSENTIAL** | Admin utility for role control |

### News Watcher Commands (news_watcher_discord.py)

| Command | Category | Rationale |
|---------|----------|-----------|
| `watcher` | **DEPRECATE** | Activation available in Canvas UI |
| `nowatcher` | **DEPRECATE** | Deactivation available in Canvas UI |
| `watchernotify` | **DEPRECATE** | Subscribe available in Canvas UI |
| `nowatchernotify` | **DEPRECATE** | Unsubscribe available in Canvas UI |
| `watcherhelp` | **DEPRECATE** | Help available in Canvas UI |
| `watcherchannelhelp` | **DEPRECATE** | Help available in Canvas UI |
| `watcherchannel` | **DEPRECATE** | All subcommands available in Canvas UI |
| `forcewatcher` | **ESSENTIAL** | Admin utility for forced execution |
| `testwatcher` | **ESSENTIAL** | Debug tool without admin permissions |

**Watcherchannel subcommands to migrate to Canvas:**
- `subscribe`, `unsubscribe` - User subscription management
- `status` - Subscription status display
- `keywords` - Keyword management
- `premises` - Premise management
- `feeds`, `categories` - Feed/category browsing
- `general` - General settings

### Treasure Hunter Commands (treasure_hunter_discord.py)

| Command | Category | Rationale |
|---------|----------|-----------|
| `hunter` (group) | **DEPRECATE** | All features available in Canvas UI |
| `hunter poe2 on` | **DEPRECATE** | Admin control available in Canvas UI |
| `hunter poe2 off` | **DEPRECATE** | Admin control available in Canvas UI |
| `hunter poe2 league` | **DEPRECATE** | League management available in Canvas UI |
| `hunter poe2 add` | **DEPRECATE** | Item addition available in Canvas UI |
| `hunter poe2 del` | **DEPRECATE** | Item deletion available in Canvas UI |
| `hunter poe2 list` | **DEPRECATE** | Item listing available in Canvas UI |
| `hunter poe2 help` | **DEPRECATE** | Help available in Canvas UI |
| `hunter help` | **DEPRECATE** | Help available in Canvas UI |
| `hunterfrequency` | **ESSENTIAL** | Admin utility for frequency control |

### Banker Commands (banker_discord.py)

| Command | Category | Rationale |
|---------|----------|-----------|
| `banker` (group) | **DEPRECATE** | All features available in Canvas UI |

**Banker subcommands to migrate to Canvas:**
- `balance` - User balance display
- `bonus` - Admin bonus setting
- `help` - Help available in Canvas UI

### Trickster Commands (trickster_discord.py)

| Command | Category | Rationale |
|---------|----------|-----------|
| `trickster beggar` | **DEPRECATE** | Beggar features available in Canvas UI |
| `trickster` (main) | **DEPRECATE** | All features available in Canvas UI |
| `trickster help` | **DEPRECATE** | Help available in Canvas UI |

### MC Commands (mc_discord.py)

| Command | Category | Rationale |
|---------|----------|-----------|
| `mc` (group) | **HYBRID** | Voice features need commands, UI features in Canvas |

**MC subcommands analysis:**
- `play`, `add`, `queue` - Voice control, keep as commands
- `skip`, `stop` - Voice control, keep as commands
- Volume/other settings - Can be Canvas-only

### Nordic Runes Commands (nordic_runes_discord.py)

| Command | Category | Rationale |
|---------|----------|-----------|
| `runes` | **DEPRECATE** | All features available in Canvas UI |
| `runes cast` | **DEPRECATE** | Casting available in Canvas UI |
| `runes history` | **DEPRECATE** | History available in Canvas UI |
| `runes types` | **DEPRECATE** | Type info available in Canvas UI |
| `runes list` | **DEPRECATE** | Rune list available in Canvas UI |
| `runes canvas_history` | **CANVAS-ONLY** | Already Canvas-specific |

### Dice Game Commands (dice_game_discord.py)

| Command | Category | Rationale |
|---------|----------|-----------|
| `dice` (group) | **DEPRECATE** | All features available in Canvas UI |
| `dice play` | **DEPRECATE** | Play available in Canvas UI |
| `dice help` | **DEPRECATE** | Help available in Canvas UI |
| `dice balance` | **DEPRECATE** | Balance available in Canvas UI |
| `dice stats` | **DEPRECATE** | Stats available in Canvas UI |
| `dice ranking` | **DEPRECATE** | Ranking available in Canvas UI |
| `dice history` | **DEPRECATE** | History available in Canvas UI |
| `dice config` | **DEPRECATE** | Configuration available in Canvas UI |

### Ring Commands (ring_discord.py)

| Command | Category | Rationale |
|---------|----------|-----------|
| `trickster ring` | **DEPRECATE** | Ring features available in Canvas UI |
| `accuse ring` | **DEPRECATE** | Accusation available in Canvas UI |

---

## Summary Statistics

| Category | Count | Percentage |
|----------|-------|------------|
| **ESSENTIAL** | 8 | 16% |
| **DEPRECATE** | 40 | 80% |
| **HYBRID** | 1 | 2% |
| **CANVAS-ONLY** | 1 | 2% |
| **TOTAL** | 50 | 100% |

---

## Essential Commands to Keep

These commands must remain as Discord commands:

1. **`canvas`** - Primary Canvas entry point
2. **`setnickname`** - Admin bot identity control
3. **`setpersonality`** - Admin personality switching
4. **`role<personality>`** - Admin role enable/disable
5. **`forcewatcher`** - Admin forced news execution
6. **`testwatcher`** - Debug tool without admin permissions
7. **`hunterfrequency`** - Admin frequency control
8. **MC voice commands** - Voice channel control (play, add, skip, stop)

---

## Commands to Deprecate

All other commands (40 total) should be migrated to Canvas-only functionality:
- All help commands (help available in Canvas)
- All user-facing role commands (available in Canvas UI)
- All subscription/management commands (better UX in Canvas)
- All status/display commands (visual in Canvas)

---

---

## Phase 1: Architecture Design (REVISED)

### Current Architecture Analysis

**The system already has Canvas UI infrastructure in place:**

- `discord_bot/canvas/canvas_news_watcher.py` - 1715 lines, contains modals, views, and action handlers
- `discord_bot/canvas/canvas_treasure_hunter.py` - 335 lines, contains POE2 modals and handlers
- `discord_bot/canvas/canvas_trickster.py` - 1441 lines, contains dice, beggar, ring, runes modals
- `discord_bot/canvas/canvas_banker.py` - Contains banker modals and views
- `discord_bot/canvas/canvas_mc.py` - Contains MC modals and action handlers
- `discord_bot/canvas/canvas_behavior.py` - Contains behavior modals
- `discord_bot/canvas/canvas_personality.py` - Contains personality switching views

**Existing Canvas Components:**
- Modals for user input (SubscribeModal, AddModal, DeleteModal, etc.)
- Views for navigation (CanvasRoleDetailView, CanvasPersonalityView, etc.)
- Action handlers (`_handle_canvas_*action` functions)
- Integration with role-specific business logic

### Revised Strategy: Simplification Not Creation

**The goal is NOT to create new files, but to:**
1. Remove redundant Discord commands that duplicate Canvas functionality
2. Keep only essential Discord commands (admin utilities, voice control)
3. Ensure all user-facing features work through Canvas UI
4. Update role loader to skip deprecated command registration

### File Structure (Current State)

```
discord_bot/canvas/
├── canvas_news_watcher.py      # EXISTING: All watcher Canvas UI components
├── canvas_treasure_hunter.py  # EXISTING: All hunter Canvas UI components
├── canvas_trickster.py        # EXISTING: All trickster Canvas UI components
├── canvas_banker.py           # EXISTING: All banker Canvas UI components
├── canvas_mc.py               # EXISTING: All MC Canvas UI components
├── canvas_behavior.py         # EXISTING: Behavior UI components
├── canvas_personality.py      # EXISTING: Personality switching UI
├── content.py                 # Shared content builders
├── state.py                   # State management
├── ui.py                      # Base UI components
└── command.py                 # Canvas command router

roles/
├── news_watcher/
│   ├── news_watcher_discord.py   # REDUNDANT: Most commands duplicate Canvas
│   ├── news_watcher.py            # SCHEDULED TASK: Keep as-is
│   └── db_role_news_watcher.py    # DATABASE: Keep as-is
├── treasure_hunter/
│   ├── treasure_hunter_discord.py # REDUNDANT: Most commands duplicate Canvas
│   ├── treasure_hunter.py         # SCHEDULED TASK: Keep as-is
│   └── db_role_treasure_hunter.py # DATABASE: Keep as-is
├── trickster/
│   ├── trickster_discord.py       # REDUNDANT: Most commands duplicate Canvas
│   ├── trickster.py               # SCHEDULED TASK: Keep as-is
│   └── subroles/
│       ├── dice_game/dice_game_discord.py  # REDUNDANT
│       ├── beggar/...             # REDUNDANT
│       ├── ring/...               # REDUNDANT
│       └── nordic_runes/...       # REDUNDANT
├── banker/
│   ├── banker_discord.py          # REDUNDANT: Most commands duplicate Canvas
│   ├── banker.py                  # SCHEDULED TASK: Keep as-is
│   └── banker_db.py               # DATABASE: Keep as-is
└── mc/
    ├── mc_discord.py              # KEEP: Voice commands needed
    └── mc.py                      # SCHEDULED TASK: Keep as-is
```

### Migration Strategy (Revised)

#### Phase 2: Remove Redundant Discord Commands

**For each role's `*_discord.py` file:**

1. **Identify commands that duplicate Canvas functionality:**
   - User subscription/management commands → Canvas already handles this
   - Status/display commands → Canvas already handles this
   - Configuration commands → Canvas already handles this
   - Help commands → Canvas has help sections

2. **Keep only essential commands:**
   - Admin-only utilities (force execution, frequency control)
   - Emergency/debug tools
   - Voice control (for MC)

3. **Add deprecation warnings:**
   ```python
   @bot.command(name="old_command")
   async def cmd_old(ctx):
       logger.warning(f"DEPRECATED: {ctx.author.name} used deprecated command 'old_command'")
       await ctx.send("⚠️ This command is deprecated. Please use Canvas UI (!canvas).")
   ```

#### Phase 3: Update Role Loader

Modify `discord_role_loader.py` to:
- Skip registration of deprecated commands
- Only register essential/admin commands
- Log skipped commands for tracking

#### Phase 4: Update Help Messages

Update `discord_core_commands.py` to:
- Remove deprecated commands from help text
- Direct users to Canvas for role management
- Keep only essential command documentation

#### Phase 5: Personality Message Cleanup

**Clean up putre/es-ES personality files to remove command-specific messages:**

**Files to clean:**
- `personalities/putre/es-ES/answers.json`
- `personalities/putre/es-ES/descriptions/news_watcher.json`
- `personalities/putre/es-ES/descriptions/treasure_hunter.json`
- `personalities/putre/es-ES/descriptions/trickster.json`
- `personalities/putre/es-ES/descriptions/banker.json`

**Messages to remove (command-specific):**
- `watcher_messages` section (command-specific success/error messages)
- `dice_game_messages` section (command help and error messages)
- Command help texts in descriptions files
- Command-specific footers (e.g., "Use `!banker tae` to...")
- Command usage instructions

**Messages to keep (Canvas/UI-specific):**
- `canvas_*` prefixed messages (Canvas UI components)
- `subrole_messages` (scheduled task messages)
- `mc_messages` (voice control messages - kept as commands)
- General personality messages (greetings, behavior)

**Strategy:**
1. Identify all command-specific message keys
2. Remove keys that reference deprecated commands
3. Keep Canvas-specific messages (prefixed with `canvas_`)
4. Keep scheduled task messages (subrole_messages)
5. Update descriptions to reference Canvas instead of commands

#### Phase 6: Testing

Verify that:
- All Canvas UI features work without Discord commands
- Essential Discord commands still function
- Users can complete all workflows through Canvas
- Admin utilities remain accessible
- Personality messages work correctly after cleanup

---

## Execution Plan

### Recommended Implementation Order

1. **Phase 2** (All Roles) → Add deprecation warnings to redundant commands
2. **Phase 3** → Update role loader to skip deprecated commands  
3. **Phase 4** → Update help messages to reference Canvas
4. **Phase 5** → Clean up personality messages
5. **Phase 6** → Full testing and validation

### Backward Compatibility Strategy

**During transition period (1-2 weeks):**
- Deprecated commands remain functional but show warnings
- Users can still use old commands while learning Canvas
- Canvas UI fully functional as primary interface

**After transition period:**
- Remove deprecated command code entirely
- Keep only essential commands
- Full Canvas-first architecture

### Risk Mitigation

- **Rollback plan:** Keep git commits for each phase
- **Testing:** Verify each role's Canvas UI before deprecating its commands
- **User communication:** Announce changes in advance with `!canvas` tutorial
- **Monitoring:** Log deprecated command usage to track adoption

---

## 🚦 GREEN LIGHT - READY FOR IMPLEMENTATION

**Status:** Roadmap reviewed, adjusted, and approved.

**Next Action:** Begin Phase 2 - Add deprecation warnings to redundant Discord commands in each role's `*_discord.py` file.

**Estimated Effort:** 
- Phase 2: 2-3 hours (deprecation warnings)
- Phase 3: 30 minutes (role loader update)
- Phase 4: 30 minutes (help update)
- Phase 5: 1-2 hours (personality cleanup)
- Phase 6: 1-2 hours (testing)

**Total:** ~5-8 hours of development work
