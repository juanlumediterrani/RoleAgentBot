# 🤖 RoleAgentBot

A sophisticated Discord bot that integrates Large Language Models (LLMs) with multiple personalities, modular roles, and advanced memory systems to create engaging AI-driven interactions.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Discord](https://img.shields.io/badge/Discord-2.7.0-green)
![License](https://img.shields.io/badge/License-Custom%20License-orange)

## ✨ Features

### 🎭 Multi-Personality System
- **Multiple Personalities**: Switch between different AI personalities (Putre, Kronk, and more)
- **Character Voice**: Each personality has unique speech patterns, vocabulary, and behavioral traits
- **Dynamic Responses**: AI maintains character consistency across all interactions

### 🧠 Advanced Memory Architecture
- **Four-Layer Memory System**:
  - Daily Memory: Synthesizes important events every 24 hours
  - Recent Memory: Rolling window of interactions (4-hour synthesis)
  - Relationship Memory: Per-user relationship summaries refreshed hourly
  - Recent Dialogue: Direct message window for ongoing conversations
- **"Remember That?"**: Detects when users ask about past events and retrieves relevant memories
- **Notable Recollections**: Stores significant events for future reference

### 🎮 Modular Role System
- **News Watcher**: RSS feed monitoring with AI-powered content filtering
- **Treasure Hunter**: Path of Exile item price tracking and market analysis
- **Trickster**: Minigames with virtual currency (dice, beggar, ring, runes)
- **Banker**: Virtual wallet management and transaction processing
- **Music Controller**: YouTube music playback in voice channels

### 🎨 Canvas UI System
- **Interactive Interface**: Button-based navigation for complex configurations
- **Role-Specific Views**: Customized UI for each role's capabilities
- **Admin Panels**: Advanced configuration views for administrators
- **DM/Channel Fallback**: Respects user privacy preferences

### 🛡️ Safety & Rate Limiting
- **Fatigue Limit System**: Configurable rate limits (burst, hourly, daily) with intelligent exemptions
- **Permission Controls**: Admin-only commands and restricted operations
- **Graceful Degradation**: Fallback mechanisms for service failures
- **Server-Specific Logging**: Isolated log directories per Discord server for better debugging and privacy

### 🔄 Reactive Behaviors
- **Presence Greetings**: Proactive DMs when users come online
- **Welcome Messages**: Contextual greetings for new server members
- **Commentary System**: Character-driven reactions to events
- **Cross-Server Coordination**: Consistent behavior across multiple servers

## 🏗️ Architecture

### Subprocess-Based Design
```
run.py (Main Orchestrator)
├── discord_bot() → Persistent Discord connection
│   ├── Core commands
│   ├── Dynamic role registration
│   └── Event handling
└── scheduler() → Periodic background tasks
    ├── Role subprocesses (isolated)
    ├── Memory maintenance
    └── Behavior tasks
```

### Key Components
- **agent_engine.py**: LLM orchestration and prompt construction
- **agent_mind.py**: Memory system and unified LLM calls
- **agent_db.py**: SQLite database management with fatigue limit tracking
- **discord_bot/**: Discord client and command system
- **roles/**: Modular role implementations
- **behavior/**: Reactive behavior modules
- **personalities/**: JSON-based personality definitions with dynamic bot naming

### Database Architecture
- Server-scoped SQLite databases
- Per-role data isolation
- Cross-server coordination for global operations
- Automatic schema migration support

## 🚀 Installation

### Prerequisites
- Python 3.8 or higher
- Discord bot token
- LLM API keys (Google Cloud Vertex AI, Groq, or others)
- Docker (optional, for containerized deployment)

### Quick Start

1. **Clone the repository**:
```bash
git clone https://github.com/yourusername/RoleAgentBot.git
cd RoleAgentBot
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Configure the bot**:
```bash
cp .env.example .env
# Edit .env with your Discord token and API keys
```

4. **Set up personality**:
```bash
# Edit agent_config.json to select personality and enable roles
```

5. **Run the bot**:
```bash
python run.py
```

### Docker Deployment

```bash
# Build the image
docker build -t roleagentbot .

# Run the container
docker run -d --name roleagentbot \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/.env:/app/.env \
  roleagentbot
```

## ⚙️ Configuration

### Main Configuration (`agent_config.json`)
```json
{
  "personality": "putre",
  "active_roles": ["news_watcher", "trickster", "banker"],
  "fatigue_limits": {
    "user": {
      "daily_max": 50,
      "hourly_max": 10,
      "burst_max": 5
    }
  }
}
```

### Personality Structure
Each personality is defined in `personalities/<name>/`:
- `personality.json`: Core identity and traits
- `prompts.json`: Behavior-specific prompts
- `descriptions.json`: UI descriptions and templates
- `answers.json`: Predefined responses

## 📖 Usage

### Basic Commands
- `!agenthelp` - Show available commands
- `!test` - Verify bot connectivity
- `!canvas` - Open interactive UI
- `!readme` - Receive user guide via DM

### Role Commands
- `!watcher` - News watcher commands
- `!trickster` - Minigames and entertainment
- `!banker` - Virtual wallet operations
- `!mc` - Music playback control
- `!hunter` - Treasure hunter for Path of Exile

### Behavior Control
- `!greet[personality]` - Enable presence greetings
- `!nogreet[personality]` - Disable presence greetings
- `!welcome[personality]` - Enable welcome messages
- `!nowelcome[personality]` - Disable welcome messages

## 🧪 Development

### Adding a New Role
1. Create directory in `roles/<role_name>/`
2. Implement main role logic
3. Add Discord command integration
4. Register in `discord_role_loader.py`
5. Add personality descriptions

### Adding a New Personality
1. Create directory in `personalities/<name>/`
2. Define JSON files (personality, prompts, descriptions, answers)
3. Configure in `agent_config.json`
4. Test character voice consistency

### Running Tests
```bash
# Run specific role tests
python roles/news_watcher/news_watcher.py

# Test memory system
python agent_mind.py

# Verify Discord connection
python discord_bot/agent_discord.py
```

## 📊 Monitoring & Logging

### Log Structure
```
logs/
├── <server_id>/
│   ├── prompt.log       # LLM prompts per server
│   ├── agent.log        # Main bot logs
│   └── <PERSONALITY>.log # Personality-specific logs
```

### Fatigue Monitoring
- `!fatigue_stats [@user]` - View usage statistics
- `!fatigue_limits` - Display current configuration
- `!fatigue_check @user` - Test limit status

## 📄 License & Terms

This project is licensed under a custom license that permits free non-commercial use but requires consent for commercial applications.

- **License**: See [LICENSE](LICENSE) for full terms
- **Terms of Service**: See [TERMS_OF_SERVICE.md](TERMS_OF_SERVICE.md) for usage guidelines

**Key License Points**:
- ✅ Free to use, modify, and distribute for non-commercial purposes
- ✅ Open source with attribution requirements
- ⚠️ Commercial use requires prior written consent
- ⚠️ Provided "AS IS" without warranty

**Important Terms**:
- Software is in active development - use at your own risk
- Adult use only (18+)
- Not recommended for individuals with mental health conditions
- Privacy considerations apply to LLM conversations

## 🙏 Acknowledgments

### Software & Libraries
This project wouldn't be possible without these amazing open-source tools:

- **[discord.py](https://github.com/Rapptz/discord.py)** - Discord API wrapper for Python
- **[Google Cloud Vertex AI](https://cloud.google.com/vertex-ai)** - Vertex AI LLM integration
- **[Groq](https://github.com/groq/groq-python)** - Fast LLM inference
- **[Cohere](https://github.com/cohere-ai/cohere-python)** - NLP and LLM services
- **[Mistral AI](https://github.com/mistralai/client-python)** - LLM provider
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** - YouTube media downloader
- **[feedparser](https://github.com/kurtmckee/feedparser)** - RSS feed parsing
- **[aiohttp](https://github.com/aio-libs/aiohttp)** - Async HTTP client
- **[python-dotenv](https://github.com/theskumar/python-dotenv)** - Environment variable management
- **[PyNaCl](https://github.com/pyca/pynacl)** - Python binding for NaCl cryptography
- **[ffmpeg-python](https://github.com/kkroening/ffmpeg-python)** - FFmpeg Python bindings

### Special Thanks

**Poe2Scout Team**
Special thanks to the [Poe2Scout](https://github.com/poe2scout/poe2scout) team for their excellent Path of Exile 2 item price tracking tools and API. Their work has been invaluable for the treasure hunter role implementation.

**Discord Community**
Thanks to the Discord.py community for excellent documentation and support.

**LLM Providers**
Special appreciation to Google, Groq, Cohere, and Mistral for providing accessible LLM APIs that power this bot's intelligence.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

### Development Guidelines
- Follow the existing code structure and naming conventions
- Add tests for new features
- Update documentation as needed
- Ensure personality consistency in AI interactions
- Respect the modular architecture when adding features

## 📞 Support

- **Documentation**: See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed technical documentation
- **User Guide**: See [README_USER.md](README_USER.md) for end-user documentation
- **Issues**: Report bugs via GitHub Issues
- **Discussions**: Use GitHub Discussions for questions and ideas

## 🔮 Future Roadmap

- [ ] Voice MC management.
- [ ] Enhanced memory recolletions for the relationships.
- [ ] Personality evolution
- [ ] Personality EX customization inside Discord.
- [ ] More role modules (shaman, blacksmith, dungeon master...)
- [ ] Another platforms (telegram, whatsapp, minecraft?)
- [ ] Fine-Tunning to a LLM to improve his socials capabilities, even adaptors for race and roles.

---

**Made with ❤️ for the Discord community**

*Note: This project is in active development. Features and APIs may change as the system evolves.*
