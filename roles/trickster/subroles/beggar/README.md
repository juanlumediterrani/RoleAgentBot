# Beggar Subrole - Restructured System

## Overview

The beggar subrole has been completely restructured to use centralized configuration in `roles.db/roles_config` instead of separate databases. This provides better integration with the overall roles system and enables advanced features like minigames and relationship improvements.

## Architecture

### Core Components

1. **beggar_config.py** - Centralized configuration management
   - Toggle on/off status
   - Frequency control (24h default)
   - Weekly reason rotation
   - Channel selection
   - Minigame settings

2. **beggar_task.py** - Automated public messaging system
   - Sends messages to public channels
   - Uses LLM for content generation
   - Context-aware with recent channel messages
   - Automatic channel selection

3. **beggar_minigame.py** - Reason change celebration system
   - Triggers when reason changes (weekly)
   - Awards prizes to top donors
   - Generates narrative using LLM
   - Relationship improvements

4. **Database Integration**
   - **roles.db/beggar_subrole** - User donation tracking
   - **roles.db/roles_config** - Centralized configuration
   - **banker.db** - Gold fund management

## Key Features

### 1. Centralized Configuration
- All settings stored in `roles_config` table
- Server-specific configuration
- JSON metadata for complex settings
- Backward compatibility maintained

### 2. Weekly Reason Rotation
- Automatically selects new reason every 7 days
- Reasons loaded from `prompts.json`
- Tracks reason start date and duration
- Triggers minigame on reason change

### 3. Automated Public Messages
- Executes on configurable frequency (default 24h)
- Sends to auto-selected or specific channel
- Uses recent channel context for relevance
- LLM-generated content with Putre personality

### 4. Minigame System
- Triggers when reason changes
- Calculates prizes for top donors
- Returns 10-30% of fund as prizes
- Generates celebration narrative
- Improves relationship levels

### 5. Enhanced Donation Tracking
- Per-user donation statistics
- Total donated and donation count
- First/last donation timestamps
- Server leaderboard system

## Configuration Schema

```json
{
  "enabled": true,
  "frequency_hours": 24,
  "current_reason": "traer a tu familia orka kontigo",
  "reason_started": "2026-03-29T01:00:00",
  "last_reason_change": "2026-03-29T01:00:00",
  "target_channel_id": null,
  "auto_channel_selection": true,
  "minigame_enabled": true,
  "relationship_improvements": true
}
```

## Database Schema

### beggar_subrole table
```sql
CREATE TABLE beggar_subrole (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    user_name TEXT NOT NULL,
    total_donated INTEGER DEFAULT 0,
    donation_count INTEGER DEFAULT 0,
    first_donation TEXT,
    last_donation TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(server_id, user_id)
)
```

### roles_config table
```sql
CREATE TABLE roles_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_name TEXT NOT NULL,
    server_id TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1,
    config_data TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(role_name, server_id)
)
```

## Usage Examples

### Enable/Disable Beggar
```bash
!trickster beggar enable
!trickster beggar disable
```

### Set Frequency
```bash
!trickster beggar frequency 12  # Every 12 hours
```

### View Status
```bash
!trickster beggar status
```

### Donate Gold
```bash
!trickster beggar donate 100
```

## Integration Points

### Agent Engine Integration
- Uses `execute_subrole_internal_task()` in `agent_engine.py`
- Calls `execute_beggar_task()` for automated messages
- Passes bot instance for channel access

### Discord Commands
- Updated `trickster_discord.py` to use new config
- Maintains backward compatibility with old commands
- Enhanced status display with leaderboard

### Canvas UI Integration
- Uses `get_canvas_beggar_state()` for UI display
- Shows current reason, fund balance, statistics
- Supports donations through modal interface

## Migration Notes

### From Old System
1. Configuration moved from `beggar_config` table to `roles_config`
2. Donation tracking moved to `beggar_subrole` table in `roles.db`
3. All existing commands continue to work

### Data Migration
- Existing subscriptions automatically converted
- Donation history preserved in both systems
- No data loss during migration
- Gradual transition supported

## Future Enhancements

1. **Advanced Minigames**
   - Different game types
   - Seasonal events
   - Multi-server competitions

2. **Relationship System Integration**
   - Direct memory system updates
   - Personalized narratives
   - Relationship level bonuses

3. **Channel Analytics**
   - Message effectiveness tracking
   - Optimal timing analysis
   - A/B testing for content

4. **Economic Balancing**
   - Dynamic prize calculations
   - Fund management strategies
   - Economic impact analysis

## Troubleshooting

### Common Issues

1. **Configuration Not Saving**
   - Check `roles.db` permissions
   - Verify server ID format
   - Check JSON serialization

2. **Messages Not Sending**
   - Verify bot permissions in channel
   - Check channel selection settings
   - Review frequency configuration

3. **Minigame Not Triggering**
   - Verify reason change timing
   - Check fund balance
   - Ensure minigame is enabled

### Debug Commands
```bash
!trickster beggar status  # Shows full configuration
!testwatcher            # Tests news watcher (similar beggar test could be added)
```

## Development Notes

### Code Style
- All hardcoded strings in English
- User-facing content loaded from JSON files
- Consistent error handling and logging
- Type hints for better maintainability

### Testing
- Unit tests for configuration management
- Integration tests for task execution
- Mock Discord for testing
- Database transaction testing

### Performance
- Efficient database queries with indexes
- Cached configuration to reduce DB calls
- Async operations for Discord interactions
- LLM calls with appropriate timeouts
