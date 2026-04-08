# 🐳 Docker Compose Configurations

## 📋 Descripción

Este proyecto contiene múltiples configuraciones de Docker Compose para diferentes entornos de despliegue del RoleAgentBot.

## 🚀 Configuraciones Disponibles

### 1. **Producción** (`docker-compose.production.yml`)
- **Propósito**: Entorno de producción con alta disponibilidad
- **Contenedores**: 2 bots (Kronk y Putre)
- **Características**:
  - Librerías Python compartidas (ahorro de recursos)
  - Todos los roles activos en ambos contenedores
  - Personalidades diferentes para cada bot
  - Volúmenes compartidos para persistencia
  - Reinicio automático
  - Sistema de límites de fatiga integrado

**Roles Activos**:
- ✅ news_watcher
- ✅ treasure_hunter  
- ✅ trickster
- ✅ banker
- ✅ mc

**Uso**:
```bash
docker compose -f docker/docker-compose.production.yml up --build -d
```

### 2. **Desarrollo** (`docker-compose.dev.yml`)
- **Propósito**: Entorno de desarrollo y pruebas
- **Contenedores**: 1 bot (Hans)
- **Características**:
  - Todos los roles activos
  - Personalidad Hans (nueva personalidad mejorada)
  - Recursos limitados (512MB RAM, 0.5 CPU)
  - Logging detallado para debugging
  - Sin reinicio automático
  - Sistema de límites de fatiga activo

**Uso**:
```bash
docker compose -f docker/docker-compose.dev.yml up --build -d
```

### 3. **Por Defecto** (`docker-compose.default.yml`)
- **Propósito**: Configuración original compatible
- **Contenedores**: 1 bot
- **Características**: Usa `agent_config.json` tal cual

**Uso**:
```bash
docker compose -f docker/docker-compose.default.yml up --build -d
```

## 🔧 Variables de Entorno Requeridas

Asegúrate de tener configuradas estas variables en tu archivo `.env`:

```env
DISCORD_TOKEN_KRONK=tu_token_kronk
DISCORD_TOKEN_PUTRE=tu_token_putre
```

##  Personalidades Disponibles

### Personalidades Principales
- **Putre**: Personalidad principal del proyecto (español)
- **Putre(English)**: Versión en inglés de Putre
- **Hans**: Nueva personalidad mejorada (alemán)
- **Igorrr**: Personalidad experimental (ruso)
- **Kronk**: Personalidad en desarrollo (incompleta)

### Configuración de Personalidades
Las personalidades se configuran mediante:
- Variable de entorno `PERSONALITY` en docker-compose
- Archivo `agent_config.json` 
- Estructura: `personalities/[nombre]/personality.json`

##  Sistema de Límites de Fatiga

### Características
- **Protección contra abuso**: Limita el uso excesivo del LLM
- **Configuración multi-nivel**: Diario, horario y ráfaga
- **Exenciones automáticas**: Tareas críticas y administradores
- **Mensajes amigables**: Informa tiempos de reset

### Umbrales Por Defecto
| Tipo | Diario | Horario | Ráfaga (5min) |
|------|--------|---------|---------------|
| **Usuario** | 50 | 10 | 5 |
| **Servidor** | 500 | 100 | 20 |

### Configuración
Los límites se configuran en `agent_config.json`:
```json
{
  "fatigue_limits": {
    "user": {
      "daily_max": 50,
      "hourly_max": 10,
      "burst_max": 5
    },
    "exemptions": {
      "admin_users": [],
      "critical_tasks": ["daily_memory", "relationship_memory"]
    }
  }
}
```

## 📁 Estructura de Volúmenes

```
../databases/     # Bases de datos SQLite
../logs/          # Logs de ejecución
../fatiga/        # Sistema de fatiga
../personalities/ # Personalidades
```

## 🔧 Dependencias Incluidas

El Dockerfile incluye:
- **FFmpeg**: Requerido para el rol MC (Master of Ceremonies)
- **yt-dlp**: Para streaming de audio desde YouTube
- **ffmpeg-python**: Interfaz Python para FFmpeg
- **PyNaCl**: Requerido para conexiones de voz de Discord

## 📄 Archivos Docker

- `Dockerfile` - Imagen principal con todas las dependencias
- `docker-entrypoint.sh` - Script de entrada para contenedores

## 📋 Comparación de Entornos

| Característica | Producción | Desarrollo | Por Defecto |
|---------------|------------|-------------|-------------|
| Contenedores | 2 (Kronk + Putre) | 1 (Hans) | 1 |
| Personalidades | Diferentes | Hans | JSON |
| Librerías Python | Compartidas | Individuales | Individuales |
| Recursos | Ilimitados | Limitados | Ilimitados |
| Reinicio | Automático | Manual | Manual |
| Logging | Estándar | Detallado | Estándar |
| Fatiga Limits | Integrado | Activo | Configurable |

## 🎭 Roles y Comandos

### Comandos de Ayuda
- `!agenthelp` - Ayuda general del bot
- `!watcherhelp` - Ayuda del News Watcher
- `!hunterhelp` - Ayuda del Treasure Hunter
- `!tricksterhelp` - Ayuda del Trickster
- `!bankerhelp` - Ayuda del Banker
- `!mchelp` - Ayuda del MC (música)

### Roles Disponibles
1. **🦅 News Watcher**: Alertas de noticias críticas
2. **💎 Treasure Hunter**: Alertas de oportunidades POE2
3. **🎭 Trickster**: Solicitudes de donaciones y juegos
4. **💰 Banker**: Gestión de economía y transacciones
5. **🎵 MC**: Master of Ceremonies (música)

## 🛠️ Comandos Útiles

### Ver logs en tiempo real
```bash
# Producción
docker logs -f roleagentbot-kronk
docker logs -f roleagentbot-putre

# Desarrollo
docker logs -f roleagentbot-dev
```

### Reiniciar servicios
```bash
# Producción
docker compose -f docker/docker-compose.production.yml restart

# Desarrollo
docker compose -f docker/docker-compose.dev.yml restart
```

### Detener servicios
```bash
# Producción
docker compose -f docker/docker-compose.production.yml down

# Desarrollo
docker compose -f docker/docker-compose.dev.yml down
```

## 📁 Estructura de Volúmenes

```
../databases/     # Bases de datos SQLite
../logs/          # Logs de ejecución
../fatiga/        # Sistema de fatiga
```

## 🔍 Troubleshooting

### Problemas Comunes
1. **Tokens inválidos**: Verifica tus tokens de Discord en `.env`
2. **Permisos insuficientes**: Asegúrate de tener permisos de Docker
3. **Puertos en uso**: Los bots usan diferentes tokens, no hay conflicto de puertos

### Verificar Estado
```bash
docker ps
docker compose -f docker/docker-compose.production.yml ps
docker compose -f docker/docker-compose.dev.yml ps
```

## 🚨 Notas Importantes

- Los contenedores de producción comparten librerías Python para optimizar recursos
- Cada contenedor usa su propio token de Discord
- Todos los roles están habilitados por defecto en ambas configuraciones
- Los datos persisten a través de reinicios gracias a los volúmenes compartidos

## 🔧 Dependencias Incluidas

El Dockerfile incluye:
- **FFmpeg**: Requerido para el rol MC (Master of Ceremonies)
- **yt-dlp**: Para streaming de audio desde YouTube
- **ffmpeg-python**: Interfaz Python para FFmpeg
- **PyNaCl**: Requerido para conexiones de voz de Discord

## 📄 Archivos Docker

- `Dockerfile` - Imagen principal con todas las dependencias
- `docker-entrypoint.sh` - Script de entrada para contenedores
