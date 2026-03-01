# MC (Master of Ceremonies) - Bot de Música para Discord

El rol MC es un bot de música completo para Discord, inspirado en los mejores bots DJ. Proporciona funcionalidades completas de reproducción de música con una interfaz amigable y características avanzadas.

## 🎵 Características Principales

### Comandos de Música
- **!mc play <canción>** - Reproduce o agrega una canción a la cola (soporta URLs y búsquedas)
- **!mc skip** - Salta la canción actual
- **!mc queue** - Muestra la cola de reproducción actual
- **!mc clear** - Limpia toda la cola (requiere rol DJ)
- **!mc pause** - Pausa la reproducción
- **!mc resume** - Reanuda la reproducción
- **!mc nowplaying** - Muestra la canción actual
- **!mc history** - Muestra el historial de reproducción
- **!mc leave** - Sale del canal de voz (requiere rol DJ)
- **!mc help** - Muestra ayuda completa

### Gestión Inteligente
- **Conexión automática** a canales de voz
- **Desconexión por inactividad** (5 minutos sin música)
- **Desconexión cuando no hay usuarios** en el canal
- **Sistema de permisos** para roles DJ y administradores
- **Persistencia de datos** en base de datos SQLite

### Base de Datos
- **Playlists** por usuario
- **Cola de reproducción** persistente
- **Historial** de canciones reproducidas
- **Preferencias** de usuarios

## 🚀 Instalación y Configuración

### Dependencias Requeridas
```bash
pip install -r requirements.txt
```

Las dependencias principales para el MC son:
- `discord.py==2.6.4` - Interfaz con Discord
- `yt-dlp` - Descarga y streaming de audio desde YouTube
- `ffmpeg-python` - Procesamiento de audio

### Requisitos del Sistema
- **Python 3.8+**
- **FFmpeg** instalado y disponible en el PATH
- **Acceso a internet** para streaming de música

### Instalación de FFmpeg

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**CentOS/RHEL:**
```bash
sudo yum install epel-release
sudo yum install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Windows:**
1. Descargar desde https://ffmpeg.org/download.html
2. Agregar a PATH del sistema

## 🎧 Uso Básico

### 1. Iniciar el Bot
```bash
python roles/mc/mc.py
```

### 2. Comandos Básicos
```
!mc play Bohemian Rhapsody Queen
!mc queue
!mc skip
!mc nowplaying
```

### 3. Permisos
Para usar comandos administrativos como `!mc clear` o `!mc leave`, los usuarios necesitan:
- Rol de administrador, O
- Uno de estos roles: "DJ", "dj", "Music", "music", "DJ Role", "dj role"

## 📊 Estructura de Archivos

```
roles/mc/
├── mc.py              # Bot principal del MC
├── mc_commands.py     # Definición de comandos
├── db_role_mc.py      # Base de datos especializada
└── README_MC.md       # Esta documentación
```

## 🗄️ Base de Datos

El MC utiliza una base de datos SQLite con las siguientes tablas:

### `playlists`
- Almacena playlists personalizadas por usuario
- Campos: nombre, usuario_id, servidor_id, fechas

### `queue`
- Cola de reproducción actual por servidor/canal
- Campos: título, url, duración, artista, posición, usuario

### `history`
- Historial de canciones reproducidas
- Campos: título, url, duración, artista, fecha_reproducción

### `preferences`
- Preferencias personalizadas de usuarios
- Campos: volumen_default, calidad_default, autoplay

## 🔧 Configuración Avanzada

### Variables de Entorno
El bot respeta las mismas variables de entorno que el sistema principal:
- `ROLE_AGENT_ENV_FILE` - Archivo de configuración personalizado
- `DISCORD_TOKEN` - Token del bot de Discord

### Calidad de Audio
Por defecto, el bot usa la mejor calidad de audio disponible. Esto se puede modificar en `mc_commands.py` ajustando las opciones de FFmpeg.

## 🎵 Características Técnicas

### Streaming de Audio
- Usa `yt-dlp` para extraer audio de YouTube
- FFmpeg para procesamiento y streaming
- Soporte para reconexión automática

### Gestión de Voz
- Detección automática de usuarios en canales
- Desconexión inteligente por inactividad
- Manejo de múltiples servidores simultáneamente

### Base de Datos
- SQLite con thread-safe operations
- Bloqueos para evitar concurrencia
- Limpieza automática de datos antiguos

## 🚨 Solución de Problemas

### FFmpeg no encontrado
```
Error: ffmpeg not found in PATH
```
**Solución:** Instalar FFmpeg y agregar al PATH del sistema

### Problemas de permisos
```
🚫 Necesitas rol de DJ o ser administrador
```
**Solución:** Asignar rol apropiado o dar permisos de administrador

### Error de conexión
```
❌ No pude conectarme al canal de voz
```
**Solución:** Verificar que el bot tenga permisos de conectar y hablar en canales

## 🎶 Ejemplos de Uso

### Sesión Típica
```
# Usuario se une a canal de voz
!mc play "Sweet Child O Mine" Guns N Roses

# El bot se conecta y empieza a reproducir
!mc queue

# Agregar más canciones
!mc play "Bohemian Rhapsody" Queen
!mc play "Hotel California" Eagles

# Ver qué está sonando
!mc nowplaying

# Saltar canción
!mc skip

# Ver historial
!mc history
```

### Gestión de DJ
```
# Limpiar cola (requiere rol DJ)
!mc clear

# Desconectar bot (requiere rol DJ)
!mc leave
```

## 🔮 Características Futuras

- [ ] Playlists personalizadas
- [ ] Soporte para Spotify
- [ ] Efectos de audio
- [ ] Control de volumen
- [ ] Modo radio
- [ ] Estadísticas detalladas
- [ ] Integración con otros servicios de streaming

## 📝 Notas de Desarrollo

El MC está diseñado siguiendo la arquitectura del sistema RoleAgentBot:
- Integración completa con el sistema de logging
- Base de datos especializada por servidor
- Compatibilidad con personalidades existentes
- Manejo robusto de errores y excepciones

## 🤝 Contribuir

Para agregar nuevas características al MC:
1. Modificar `mc_commands.py` para nuevos comandos
2. Actualizar `db_role_mc.py` para nuevas funcionalidades de BD
3. Probar exhaustivamente con diferentes escenarios
4. Actualizar esta documentación

---

**¡Disfruta de la música con MC!** 🎵🎤🎶
