# 🤖 RoleAgentBot - User Guide

Welcome! RoleAgentBot is a multi-personality Discord bot that provides various entertainment and utility functions. Each personality has unique characteristics and speech patterns.

## 📜 License and Terms of Service

**IMPORTANT:** Before using RoleAgentBot, please review:
- **License:** See [LICENSE](LICENSE) file for usage rights and commercial use requirements
- **Terms of Service:** See [TERMS_OF_SERVICE.md](TERMS_OF_SERVICE.md) for usage guidelines, privacy policy, and important restrictions

**Key Points:**
- Free for non-commercial use
- Commercial use requires prior consent
- Software is in development - use at your own risk
- Adult use only (18+)
- Not recommended for individuals with mental health conditions

## 🎭 Available Personalities

- **Putre** - An aggressive orc character who speaks directly and simply
- **Kronk** - A formal, loyal empire character  
- **Agumon** - A friendly digital monster with tech-savvy language

## 🚀 Quick Start

### Basic Interaction
- **Talk to the bot**: Simply mention the bot (@botname) in any message
- **Get help**: Type `!agenthelp` to see all available commands
- **Get full guide**: Type `!readme` to receive this complete guide via private message

## 🎛️ Essential Commands

### Control & Administration
- `!agenthelp` - Show help menu with all available commands
- `!test` - Verify the bot is working correctly
- `!insult[personality]` - Get a character-appropriate insult (e.g., `!insultputre`)

### Greeting Management (Admin Only)
- `!greet[personality]` - Enable automatic presence greetings
- `!nogreet[personality]` - Disable presence greetings
- `!welcome[personality]` - Enable new member welcome messages
- `!nowelcome[personality]` - Disable welcome messages

### Role Management (Admin Only)
- `!role[personality] <role> <on/off>` - Enable/disable specific roles

## 🎭 Role Commands

### 📡 News Watcher
**Purpose**: Get smart news alerts and monitoring
**Basic Usage**: `!watcher` | `!nowatcher` | `!watchernotify`
**Help**: `!watcherhelp` (users) | `!watcherchannelhelp` (admins)
**Channel Management**: `!watcherchannel subscribe/unsubscribe/status/keywords/premises`
**Subscription**: `!watcher feeds/categories/status/subscribe/unsubscribe/keywords/general/reset`

### 💎 Treasure Hunter  
**Purpose**: Path of Exile 2 item price monitoring and alerts
**Admin Control**: `!hunter poe2 on/off` | `!hunterfrequency <hours>`
**League Management**: `!hunter poe2 league "Standard"` | `!hunter poe2 "Fate of the Vaal"`
**Item Management**: `!hunteradd "item"` | `!hunterdel "item"/<number>` | `!hunterlist`
**Help**: `!hunterhelp` | `!hunter poe2 help`

### 🎭 Trickster
**Purpose**: Entertainment mini-games and activities
**Main Help**: `!trickster help`
**Dice Game**: `!dice play/help/balance/stats/ranking/history`
**Dice Config**: `!dice config bet <amount>` | `!dice config announcements on/off`
**Ring Target Selection**: `!trickster ring target @user`
**Subroles**: `!trickster beggar/ring enable/disable/frequency/help`

### 💰 Banker
**Purpose**: Virtual economy management and daily TAE
**Main**: `!banker help`
**Balance**: `!banker balance` (sends you a private message)
**Admin Config**: `!banker bonus <amount>`

### 🎵 Music Controller
**Purpose**: Music playback in voice channels
**Common Usage**: `!mc play "song name"` | `!mc add "song"` | `!mc queue`
**Help**: `!mc help`

## 💬 Conversation Tips

### How to Talk to the Bot
- **Mention the bot**: @RoleAgentBot Your message here
- **Natural conversation**: The bot responds using its personality
- **Context awareness**: The bot remembers recent conversations

### Personality Examples
- **Putre**: "Putre smash! Putre help with news!"
- **Kronk**: "At your service, commander. How may I assist you today?"
- **Agumon**: "Digital monster detected! Let me help you with that!"

## 🔧 Advanced Features

### Mission Commentary
- **Enable**: `!talk[personality] on` (admin only)
- **Disable**: `!talk[personality] off` (admin only)
- **Status**: `!talk[personality] status`
- **Speak now**: `!talk[personality] now`

### Private vs Public Commands
- **DM-only**: Some commands (like news watcher) work best in private messages
- **Channel commands**: Most commands work in server channels
- **Admin commands**: Require administrator permissions

## 📋 Command Reference Summary

| Category | Commands | Description |
|----------|----------|-------------|
| **Basic** | `!agenthelp`, `!test`, `!readme` | Help and testing |
| **Control** | `!greet*`, `!welcome*`, `!insult*` | Bot management |
| **News** | `!watcher*` | News monitoring |
| **Gaming** | `!hunter*`, `!dice*`, `!accuse` | Game-related features |
| **Economy** | `!banker*` | Virtual banking |
| **Music** | `!mc*` | Voice channel music |
| **Admin** | `!role*`, `!talk*` | Server administration |

## 🎯 Getting Help

### Self-Service Help
- `!agenthelp` - Interactive help menu
- `!readme` - Complete user guide (private message)
- `![role]help` - Role-specific help (e.g., `!watcherhelp`)

### Common Issues
- **Command not working**: Check if you have required permissions
- **No response**: The bot might be restarting or experiencing issues
- **Wrong channel**: Some commands work only in specific channels

## 🌟 Pro Tips

1. **Start with `!agenthelp`** - See what's available on your server
2. **Use `!readme`** - Get this complete guide for future reference
3. **Talk naturally** - Just mention the bot to start a conversation
4. **Check permissions** - Admin commands require server administrator role
5. **Explore roles** - Try different role commands to discover features

## 🛡️ Safety & Privacy

- The bot respects Discord's Terms of Service
- Private messages are only visible to you and the bot
- Admin commands are logged for security
- No personal data is stored beyond what's necessary for functionality

---

**Need more help?**
- Type `!agenthelp` for interactive assistance
- Contact your server administrator for configuration issues
- Check the specific role help commands for detailed feature explanations

*Enjoy your RoleAgentBot experience! 🎉*
