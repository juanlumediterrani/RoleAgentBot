# Docker Update Notes - 2025-04-03

## Overview
Updated Docker configuration to match the current program functionality after major refactoring and architecture changes.

## Issues Found and Fixed

### 1. Missing Critical Files
**Problem**: Dockerfile was missing several essential Python files added during monolith refactoring
**Fixed**: Added missing files:
- `agent_mind.py` - Core LLM and memory functionality
- `agent_roles_db.py` - Roles database management  
- `agent_runtime.py` - Runtime utilities
- `discord_force_watcher_command.py` - Force watcher command
- `init_roles_config.py` - Roles configuration initialization
- `prompts_logger.py` - Prompts logging functionality
- `ARCHITECTURE.md` - System documentation
- `README_USER.md` - User documentation
- `start_clean.sh` - Debugging script
- `behavior/` directory - Complete behavior system

### 2. Environment Variables Inconsistency
**Problem**: .env file and docker-compose files had mismatched variable names
**Fixed**: 
- .env uses `DISCORD_TOKEN` but compose files looked for `DISCORD_TOKEN_PUTRE`
- Added missing `DISCORD_TOKEN_AGUMON` to compose files
- Added `MISTRAL_API_KEY` support
- Added `HOST_UID/HOST_GID` for proper permissions

### 3. Deprecated Configuration
**Problem**: Production compose used deprecated individual role flags
**Fixed**: Removed deprecated flags:
- `NEWS_WATCHER_ENABLED=true`
- `TREASURE_HUNTER_ENABLED=true`
- `TRICKSTER_ENABLED=true`
- `BANKER_ENABLED=true`
- `MC_ENABLED=true`
Now uses unified `ACTIVE_ROLES=news_watcher,treasure_hunter,trickster,banker,mc`

## Changes Made

### 1. Dockerfile Updates
- **Added missing Python files**: The Dockerfile was missing several critical files added during the monolith refactoring
  - `agent_mind.py` - Core LLM and memory functionality
  - `agent_roles_db.py` - Roles database management
  - `agent_runtime.py` - Runtime utilities
  - `discord_force_watcher_command.py` - Force watcher command
  - `init_roles_config.py` - Roles configuration initialization
  - `prompts_logger.py` - Prompts logging functionality
- **Added behavior directory**: Missing from COPY commands
- **Reorganized file copying**: All Python files now copied before directories for better layer caching

### 2. Environment Variables Updates
- **Added MISTRAL_API_KEY**: New LLM provider support
- **Added HOST_UID/HOST_GID**: Proper user mapping for volume permissions
- **Removed deprecated role flags**: Individual role flags (NEWS_WATCHER_ENABLED, etc.) replaced with ACTIVE_ROLES

### 3. Docker Compose Updates
- **docker-compose.dev.yml**: Updated with current environment variables
- **docker-compose.production.yml**: 
  - Added missing API keys (MISTRAL_API_KEY)
  - Removed deprecated individual role flags
  - Added HOST_UID/HOST_GID for proper permissions
  - Maintained dual-bot setup (Kronk + Putre)

### 4. .dockerignore Updates
- **Added .windsurf/**: Exclude Windsurf workflow files
- **Added .active_server**: Exclude active server marker file
- **Fixed docker-compose pattern**: Now excludes all docker-compose*.yml files

## Current Architecture Support

### Files Now Included
```
Core Engine:
- agent_engine.py
- agent_mind.py (NEW)
- agent_runtime.py (NEW)
- agent_roles_db.py (NEW)

Discord Integration:
- discord_bot/ (entire directory)
- discord_force_watcher_command.py (NEW)

Configuration & Utilities:
- agent_config.json
- agent_db.py
- agent_logging.py
- init_roles_config.py (NEW)
- prompts_logger.py (NEW)
- postprocessor.py

Behavior System:
- behavior/ (entire directory) (NEW)

Roles & Personalities:
- roles/ (entire directory)
- personalities/ (entire directory)
```

### Environment Variables Required
```bash
# Discord Tokens
DISCORD_TOKEN_PUTRE=your_token_here
DISCORD_TOKEN_KRONK=your_token_here (optional)
DISCORD_TOKEN_AGUMON=your_token_here (optional)

# LLM API Keys
GROQ_API_KEY=your_key_here
GOOGLE_CLOUD_PROJECT=your_project_id
GOOGLE_CLOUD_LOCATION=us-central1
COHERE_API_KEY=your_key_here
MISTRAL_API_KEY=your_key_here (NEW)

# System Configuration
HOST_UID=1001
HOST_GID=1001
PERSONALITY=agumon|kronk|putre|hans
ACTIVE_ROLES=news_watcher,treasure_hunter,trickster,banker,mc
```

## Usage Instructions

### Development
```bash
# Build and run development container
docker compose -f docker/docker-compose.dev.yml up --build -d

# View logs
docker compose -f docker/docker-compose.dev.yml logs -f

# Stop container
docker compose -f docker/docker-compose.dev.yml down
```

### Production
```bash
# Build and run production containers (dual bots)
docker compose -f docker/docker-compose.production.yml up --build -d

# View logs for specific bot
docker logs roleagentbot-kronk -f
docker logs roleagentbot-putre -f

# Stop containers
docker compose -f docker/docker-compose.production.yml down
```

### Custom Build
```bash
# Build with specific personality
docker build \
  --build-arg PERSONALITY=putre \
  --build-arg ACTIVE_ROLES=news_watcher,trickster \
  -t roleagentbot:custom \
  -f docker/Dockerfile .

# Run custom container
docker run -d \
  --name roleagentbot-custom \
  -v $(pwd)/databases:/app/databases \
  -v $(pwd)/logs:/app/logs \
  -e DISCORD_TOKEN=your_token \
  -e GROQ_API_KEY=your_key \
  roleagentbot:custom
```

## Testing Verification

### Build Test ✅
- Docker build completes successfully
- All Python files copied correctly
- Dependencies installed without errors

### Configuration Test ✅
- Docker compose configuration validates
- Environment variables properly mapped
- Volume mounts configured correctly

### Functional Test
To verify functionality:
1. Run development container
2. Check logs for proper startup
3. Test Discord commands
4. Verify role functionality

## Migration Notes

### From Previous Setup
- No breaking changes to volume mounts
- Existing databases and logs will work
- Environment variables backward compatible

### New Features
- Support for MISTRAL AI provider
- Better user permission handling
- Complete behavior system support
- All new Python modules included

## Troubleshooting

### Common Issues
1. **Permission errors**: Ensure HOST_UID/HOST_GID match your user ID
2. **Missing API keys**: Add MISTRAL_API_KEY to .env file
3. **Build failures**: Check all Python files are present in project root

### Debug Commands
```bash
# Check container file structure
docker run --rm roleagentbot:test ls -la /app

# Test entrypoint
docker run --rm -e PERSONALITY=agumon roleagentbot:test python -c "import agent_engine; print('OK')"

# Check environment variables
docker run --rm roleagentbot:test env | grep -E "(DISCORD|API_KEY|PERSONALITY)"
```

## Future Considerations

### Potential Improvements
- Multi-stage build for smaller production images
- Health checks for container monitoring
- Separate volume for configuration files
- Automated testing in CI/CD pipeline

### Maintenance
- Review requirements.txt updates quarterly
- Update base Python version annually
- Monitor security advisories for dependencies
- Test with new Discord.py releases
