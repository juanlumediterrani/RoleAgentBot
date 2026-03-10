# ROLEAGENTBOT - STRUCTURED COMMAND REFERENCE

## CONTROL COMMANDS
- !agenthelp [personality] - Show comprehensive help (personality-specific optional)
- !readme - Get complete user guide by private message (NEW)
- !greet[personality] - Enable presence greetings (admin)
- !nogreet[personality] - Disable presence greetings (admin)
- !welcome[personality] - Enable new member welcome (admin)
- !nowelcome[personality] - Disable new member welcome (admin)
- !insult[personality] - Send character-appropriate insult
- !role[personality] <role> <on/off> - Enable/disable roles dynamically (admin)
- !test - Test bot functionality

## ROLE COMMANDS
### News Watcher (news_watcher)
- Purpose: Smart news alerts and monitoring
- Main Commands: !watcher | !nowatcher | !watchernotify
- Help Commands: !watcherhelp (users) | !watcherchannelhelp (admins)
- Channel Management: !watcherchannel subscribe/unsubscribe/status/keywords/premises
- Subscription: !watcher feeds/categories/status/subscribe/unsubscribe/keywords/general/reset
- Admin: !forcewatcher (manual check)

### Treasure Hunter (treasure_hunter)
- Purpose: POE2 item price monitoring and alerts
- Admin Control: !hunter poe2 on/off | !hunterfrequency <hours>
- League Management: !hunter poe2 league "Standard" | !hunter poe2 "Fate of the Vaal"
- Item Management: !hunteradd "item" | !hunterdel "item"/<number> | !hunterlist
- Help: !hunterhelp | !hunter poe2 help

### Trickster (trickster)
- Purpose: Entertainment mini-games and subroles
- Main Help: !trickster help
- Ring Accusation: !accuse @user (legacy)
- Dice Game: !dice play/help/balance/stats/ranking/history
- Dice Configuration: !dice config bet <amount> | !dice config announcements on/off
- Subroles (when enabled): !trickster beggar/ring enable/disable/frequency/help

### Banker (banker)
- Purpose: Virtual economy management
- Main: !banker help
- Balance: !banker balance (DMs user in channels)
- Admin Config: !banker bonus <amount>

### Music Controller (mc)
- Purpose: Music playback in voice channels
- Common: !mc play "song" | !mc add "song" | !mc queue
- Help: !mc help

## LLM LOGIC STRUCTURE
### Golden Rule System
1. User asks for help about commands/functions
2. LLM responds with "README" (following personality golden rule)
3. System detects README response + help request
4. System loads structured documentation
5. System resends original question + documentation to LLM
6. LLM provides character-appropriate explanation

### Response Guidelines
- Keep explanations SHORT and focused
- Maintain personality speech patterns
- Reference only relevant commands for user's question
- Use character-appropriate language (Putre: aggressive/simple, Kronk: formal, Agumon: friendly)

### Personality Context
- Putre: Orc character - aggressive speech, no tildes, simple vocabulary
- Kronk: Empire character - formal, loyal speech patterns
- Agumon: Digital monster - friendly, tech-savvy language

## BASIC INTERACTION
- Mention bot (@botname) for casual conversation
- Bot responds using active personality
- Each personality has unique speech patterns and vocabulary

## ADMINISTRATION
- Most configuration requires admin permissions
- Role intervals configurable by server administrators
- Use role-specific help commands for detailed setup

## USAGE NOTES
- Commands start with ! prefix
- Some commands work only in DMs (watcher commands)
- Bot maintains character consistency in all responses
- Help requests trigger automatic README explanations
- Control commands are personality-prefixed (e.g., !greetputre, !insultputre)
- !readme sends comprehensive user guide via private message for better user experience
