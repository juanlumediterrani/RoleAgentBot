# SQLite → JSON Migration Documentation

## Overview
This migration moves role and behavior **toggles** from SQLite to JSON-based `server_config.json` to reduce I/O overhead on Raspberry Pi.

## What Was Migrated

### 1. Role Toggles (enabled/disabled)
**From**: `roles_{personality}.db` → `roles_config` table
**To**: `databases/{server_id}/server_config.json` → `roles` section

**Example structure in server_config.json**:
```json
{
  "active_personality": "putre",
  "language": "es-ES",
  "roles": {
    "news_watcher": {
      "enabled": true,
      "updated_at": "2026-04-22T12:00:00Z"
    },
    "treasure_hunter": {
      "enabled": false,
      "updated_at": "2026-04-22T12:00:00Z"
    },
    "banker": {
      "enabled": true,
      "config": {
        "tae": 5.0,
        "last_tae_distribution": "2026-04-22T12:00:00Z"
      },
      "updated_at": "2026-04-22T12:00:00Z"
    },
    "dice_game": {
      "enabled": true,
      "config": {
        "fixed_bet": 100,
        "announcements_active": true
      },
      "updated_at": "2026-04-22T12:00:00Z"
    },
    "poe2_subrole": {
      "enabled": true,
      "config": {
        "league": "Standard",
        "targets": ["item_1234", "item_5678"],
        "purchases": [
          {"item": "item_1234", "price": 100, "timestamp": "2026-04-22T10:00:00Z"}
        ]
      },
      "updated_at": "2026-04-22T12:00:00Z"
    },
    "ring": {
      "enabled": true,
      "config": {
        "extra": {}
      },
      "updated_at": "2026-04-22T12:00:00Z"
    },
    "beggar": {
      "enabled": true,
      "config": {
        "donation_limits": {"min": 10, "max": 1000},
        "weekly_stats": {"requests": 5, "donations": 50}
      },
      "updated_at": "2026-04-22T12:00:00Z"
    }
  },
  "behaviors": {
    "greetings": {
      "enabled": true,
      "config": null,
      "updated_at": "2026-04-22T12:00:00Z",
      "updated_by": "admin_command"
    },
    "welcome": {
      "enabled": true,
      "config": {
        "channel_id": "123456789"
      },
      "updated_at": "2026-04-22T12:00:00Z",
      "updated_by": "admin_command"
    },
    "commentary": {
      "enabled": true,
      "config": {
        "channel_id": "123456789",
        "interval_minutes": 180
      },
      "updated_at": "2026-04-22T12:00:00Z",
      "updated_by": "admin_command"
    }
  }
}
```

### 2. Behavior Toggles
**From**: `behavior_{personality}.db` → `behavior_states` table
**To**: `databases/{server_id}/server_config.json` → `behaviors` section

**Migrated behaviors**:
- `greetings` - Toggle enabled/disabled
- `welcome` - Toggle enabled/disabled + channel_id config
- `commentary` - Toggle enabled/disabled + channel_id, interval_minutes config

## Files Modified

### 1. discord_bot/canvas/server_config.py
**Added functions**:
- `get_role_config()` - Get role config from server_config.json
- `set_role_config()` - Set role config in server_config.json
- `is_role_enabled()` - Check if role is enabled
- `get_all_roles_config()` - Get all roles config
- `get_behavior_config()` - Get behavior config from server_config.json
- `set_behavior_config()` - Set behavior config in server_config.json
- `is_behavior_enabled()` - Check if behavior is enabled
- `get_all_behaviors_config()` - Get all behaviors config
- `get_welcome_enabled()` - Check if welcome is enabled
- `set_welcome_enabled()` - Set welcome enabled state
- `get_welcome_channel()` - Get welcome channel ID
- `set_welcome_channel()` - Set welcome channel ID
- `get_commentary_state()` - Get commentary state with config
- `set_commentary_state()` - Set commentary state with config
- `migrate_roles_from_sqlite()` - Migration helper
- `migrate_behaviors_from_sqlite()` - Migration helper

### 2. discord_bot/discord_utils.py
**Modified functions**:
- `is_role_enabled_check()` - Now uses `server_config.is_role_enabled()` instead of `roles_db.get_role_config()`
- `set_role_enabled()` - Now uses `server_config.set_role_config()` instead of `roles_db.save_role_config()`
- `should_enable_greetings()` - Now uses `server_config.is_behavior_enabled()` instead of `behavior_db.get_greetings_enabled()`
- `set_greeting_enabled()` - Now uses `server_config.set_behavior_config()` instead of `behavior_db.set_greetings_enabled()`

**Removed functions**:
- `get_feature_state()` - Not used in codebase
- `set_feature_state()` - Not used in codebase

### 3. behavior/welcome.py
**Modified functions**:
- `get_welcome_channel_info()` - Now uses `server_config.get_welcome_channel()` and `server_config.set_welcome_channel()` instead of `behavior_db.get_welcome_channel()` and `behavior_db.set_welcome_channel()`

### 4. discord_bot/canvas/ui.py
**Modified handlers**:
- `welcome_on` / `welcome_off` - Now uses `server_config.set_welcome_enabled()` instead of `behavior_db.set_welcome_enabled()`
- `commentary_on` / `commentary_off` - Now uses `server_config.set_commentary_state()` instead of `behavior_db.set_commentary_state()`

### 5. discord_bot/canvas/canvas_behavior.py
**Modified functions**:
- `build_canvas_behavior_detail()` - Now uses `server_config.get_welcome_enabled()` and `server_config.get_commentary_state()` instead of `behavior_db.get_welcome_enabled()` and `behavior_db.get_commentary_state()`

### 6. discord_bot/db_init.py
**Modified function**:
- `copy_personality_to_server()` - Now initializes `roles` and `behaviors` sections in server_config.json

### 7. migrate_sqlite_to_json.py (NEW)
**Purpose**: One-time migration script to move existing data from SQLite to server_config.json

**Usage**:
```bash
python migrate_sqlite_to_json.py
```

## What Was NOT Migrated

### Role Config Data (config_data)
The `config_data` field in `roles_config` table contains role-specific settings stored as JSON in a TEXT field - this is an anti-pattern.

**Current structure (anti-pattern)**:
```sql
-- roles_config table
role_name | enabled | config_data (TEXT with JSON)
banker    | 1       | '{"tae": 5.0, "last_tae_distribution": "..."}'
dice_game | 1       | '{"fixed_bet": 100, "announcements_active": true}'
```

**Proposed NoSQL structure in server_config.json**:
```json
{
  "roles": {
    "banker": {
      "enabled": true,
      "config": {
        "tae": 5.0,
        "last_tae_distribution": "2026-04-22T12:00:00Z"
      }
    },
    "dice_game": {
      "enabled": true,
      "config": {
        "fixed_bet": 100,
        "announcements_active": true
      }
    }
  }
}
```

**Role-specific data**:
- **Banker**: TAE (interest rate), last distribution timestamp
- **Dice Game**: fixed_bet, announcements_active
- **POE2**: league, targets, purchases
- **Ring**: extra config
- **Beggar**: donation limits, weekly stats

**Why migrate to proper NoSQL structure**:
- Eliminates anti-pattern of JSON-in-TEXT
- Native JSON is faster than JSON parsing from SQLite TEXT
- Human-readable and editable
- No need for schema migrations
- Consistent with current toggle migration

**Current status**: These remain in SQLite temporarily, but should be migrated to the proper NoSQL structure above.

**Methods kept in agent_roles_db.py** (temporary):
- `save_role_config()` - Still used by banker, dice_game, poe2, ring, beggar
- `get_role_config()` - Still used by all roles above
- `migrate_roles_from_agent_config()` - Still used for initialization

### Feature States (no usados actualmente)
The `get_feature_state()` and `set_feature_state()` functions in discord_utils.py were not used in the codebase and have been removed.

## Migration Benefits

### For Raspberry Pi
- **Reduced I/O**: No SQLite writes for toggle changes
- **No WAL files**: Eliminates .wal and .shm file overhead
- **Simpler**: JSON is human-readable and easier to debug
- **Thread-safe**: Uses existing lock mechanism in server_config.py

### For Development
- **Easier inspection**: server_config.json can be viewed directly
- **Version control friendly**: JSON diffs are clearer than binary DB
- **No schema migrations**: Adding new config fields doesn't require ALTER TABLE

## Testing Checklist

After running `migrate_sqlite_to_json.py`:

1. **Verify role toggles work**:
   - Enable/disable a role from Canvas UI
   - Check that server_config.json is updated
   - Restart bot and verify toggle persists

2. **Verify greetings toggle**:
   - Enable/disable greetings from Canvas UI
   - Check that server_config.json is updated
   - Verify bot behavior changes accordingly

3. **Verify welcome toggle and channel**:
   - Enable/disable welcome from Canvas UI
   - Check that server_config.json is updated
   - Configure welcome channel
   - Verify channel_id is saved in server_config.json

4. **Verify commentary toggle and config**:
   - Enable/disable commentary from Canvas UI
   - Check that server_config.json is updated
   - Configure commentary channel and interval
   - Verify config is saved in server_config.json

5. **Verify role-specific config still works**:
   - Configure banker TAE
   - Configure dice game fixed bet
   - Configure POE2 targets
   - Verify these still save to SQLite config_data

## Rollback Plan

If issues arise, rollback steps:

1. Disable the new code changes
2. Restore SQLite as primary source
3. Revert discord_utils.py to use roles_db/behavior_db
4. Revert behavior/welcome.py to use behavior_db
5. Revert canvas/ui.py and canvas/canvas_behavior.py to use behavior_db
6. Data remains in SQLite (migration script doesn't delete it)

## Next Steps (Recommended)

### Phase 2: Migrate Role Config Data to Proper NoSQL Structure

**Goal**: Eliminate the anti-pattern of JSON-in-TEXT by migrating role-specific config_data to the proper NoSQL structure in server_config.json.

**Steps**:
1. Update `server_config.py` functions to handle nested config objects
2. Update each role module (banker, dice_game, poe2, ring, beggar) to use server_config instead of SQLite
3. Update `migrate_sqlite_to_json.py` to parse and migrate config_data to proper structure
4. Remove `roles_config` table methods from `agent_roles_db.py`
5. Remove `behavior_states` table methods from `behavior/db_behavior.py`

**Benefits**:
- Eliminates JSON-in-TEXT anti-pattern
- Faster access (native JSON vs parsing TEXT)
- Consistent data structure across all config
- Human-readable and editable
- No SQLite I/O overhead for config changes

**Estimated effort**: Medium - requires updating each role module's config access patterns.
