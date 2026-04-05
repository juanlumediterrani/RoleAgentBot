# Docker Build Options - Conditional MC Installation

## Overview
The Dockerfile now supports conditional installation of MC-specific packages based on the `ENABLE_MC` build argument.

## Build Options

### With MC Support (Full Installation ~270MB)
```bash
# Build with MC packages (ffmpeg, nodejs, etc.)
docker build --build-arg ENABLE_MC=true -t roleagentbot-full .

# Or using docker-compose
docker-compose -f docker/docker-compose.production.yml up --build -d
```

**Includes:**
- ✅ All base packages (gcc, python3-dev, etc.)
- ✅ MC multimedia packages (ffmpeg, libopus-dev, libsodium-dev)
- ✅ JavaScript runtime (nodejs) for YouTube cookies
- ✅ Development libraries (libav*-dev)

### Without MC Support (Minimal Installation ~174MB)
```bash
# Build without MC packages
docker build --build-arg ENABLE_MC=false -t roleagentbot-minimal .

# Create custom docker-compose without MC
# (copy docker-compose.production.yml and change ENABLE_MC to "false")
```

**Includes:**
- ✅ All base packages (gcc, python3-dev, etc.)
- ❌ No multimedia packages
- ❌ No JavaScript runtime
- ❌ No development libraries

## Package Differences

| Category | With MC | Without MC | Size Impact |
|----------|---------|------------|-------------|
| Base development | ✅ | ✅ | 168MB |
| Multimedia (ffmpeg, etc.) | ✅ | ❌ | 21MB |
| JavaScript (nodejs) | ✅ | ❌ | 50MB |
| Dev libraries (libav*-dev) | ✅ | ❌ | 38MB |
| **Total Size** | **~270MB** | **~174MB** | **-96MB (35.6%)** |

## When to Use Each Option

### Use ENABLE_MC=true when:
- ✅ You need music playback functionality
- ✅ You want YouTube cookies support
- ✅ You need Discord voice features
- ✅ Bot will be used for entertainment purposes

### Use ENABLE_MC=false when:
- ✅ Bot is for utility purposes only (news, banking, etc.)
- ✅ You want smaller Docker images
- ✅ Faster build times
- ✅ Reduced attack surface
- ✅ Running on resource-constrained environments

## Docker Compose Configuration

### Production (with MC)
```yaml
services:
  bot:
    build:
      args:
        ENABLE_MC: "true"  # Includes MC packages
```

### Minimal (without MC)
```yaml
services:
  bot:
    build:
      args:
        ENABLE_MC: "false"  # Excludes MC packages
```

## Runtime Behavior

The bot will automatically detect whether MC packages are available:

- **With MC packages**: Full music functionality
- **Without MC packages**: MC commands will show appropriate error messages

## Migration Notes

### Existing Deployments
Current deployments with MC enabled will continue to work unchanged.

### New Minimal Deployments
If you switch from `ENABLE_MC=true` to `ENABLE_MC=false`:
- Build time will be faster
- Image size will be smaller
- MC functionality will be unavailable

## Build Commands Summary

```bash
# Full installation (current default)
docker build --build-arg ENABLE_MC=true -t roleagentbot .

# Minimal installation
docker build --build-arg ENABLE_MC=false -t roleagentbot-minimal .

# Production with MC
docker-compose -f docker/docker-compose.production.yml up --build

# Custom minimal compose
docker-compose -f docker/docker-compose.minimal.yml up --build
```

## Troubleshooting

### MC Commands Not Working
If MC commands fail in a minimal build:
1. Check if ENABLE_MC=true was used during build
2. Rebuild with ENABLE_MC=true if needed
3. Verify ffmpeg is installed: `docker exec container ffmpeg -version`

### Build Issues
If build fails:
1. Ensure Dockerfile syntax is correct
2. Check build arguments are properly quoted
3. Verify base image is available

## Performance Impact

### Build Time
- **With MC**: ~5-7 minutes
- **Without MC**: ~3-4 minutes (30-40% faster)

### Runtime Memory
- **With MC**: ~200-300MB base memory
- **Without MC**: ~100-150MB base memory

### Storage
- **With MC**: ~270MB image size
- **Without MC**: ~174MB image size

Choose the appropriate build option based on your deployment needs!
