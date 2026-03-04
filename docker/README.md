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

**Roles Activos**:
- ✅ vigia_noticias
- ✅ buscador_tesoros  
- ✅ trilero
- ✅ buscar_anillo
- ✅ mc

**Uso**:
```bash
docker compose -f docker/docker-compose.production.yml up --build -d
```

### 2. **Desarrollo** (`docker-compose.dev.yml`)
- **Propósito**: Entorno de desarrollo y pruebas
- **Contenedores**: 1 bot (Kronk)
- **Características**:
  - Todos los roles activos
  - Personalidad Kronk
  - Recursos limitados (512MB RAM, 0.5 CPU)
  - Logging detallado para debugging
  - Sin reinicio automático

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

## � Comparación de Entornos

| Característica | Producción | Desarrollo | Por Defecto |
|---------------|------------|-------------|-------------|
| Contenedores | 2 (Kronk + Putre) | 1 (Kronk) | 1 |
| Personalidades | Diferentes | Kronk | JSON |
| Librerías Python | Compartidas | Individuales | Individuales |
| Recursos | Ilimitados | Limitados | Ilimitados |
| Reinicio | Automático | Manual | Manual |
| Logging | Estándar | Detallado | Estándar |

## 🎭 Roles y Comandos

### Comandos de Ayuda
- `!ayudakronk` - Ayuda general del bot Kronk
- `!ayudaputre` - Ayuda general del bot Putre
- `!vigiaayuda` - Ayuda del Vigía de Noticias
- `!poe2ayuda` - Ayuda del Buscador de Tesoros
- `!mcayuda` - Ayuda del MC (música)
- `!acusaranillo` - Acusar por el anillo

### Roles Disponibles
1. **🦅 Vigía de Noticias**: Alertas de noticias críticas
2. **💎 Buscador de Tesoros**: Alertas de oportunidades POE2
3. **🎭 Trilero**: Solicitudes de limosna y engaños
4. **�️ Buscar Anillo**: Acusaciones por el anillo único
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
