# RoleAgentBot - Agente interactivo con diferentes personalidades
-----------------------------------------------------------------------------------------

Un bot de Discord modular con sistema de roles autónomos programables, motor de IA integrado y persistencia de datos.

# 🚀 Características

- **Bot Discord Modular**: Sistema extensible con arquitectura basada en roles
- **Roles Autónomos**: Ejecución automática de tareas programadas en intervalos configurables
- **Motor de IA**: Integración con múltiples APIs (Google Gemini, Groq) para procesamiento de lenguaje natural
- **Personalidad Configurable**: Sistema de personalidad ajustable para el bot
- **Persistencia de Datos**: Base de datos SQLite para almacenar interacciones y contexto
- **Logging Completo**: Sistema de logging estructurado para depuración y monitoreo

# 📋 Requisitos

- Python 3.8+
- Cuenta de Bot de Discord
- API Keys para servicios de IA (Google Gemini y/o Groq)

# 🔧 Comandos del Bot

- **Menciones**: `@NombreDelBot tu mensaje` - Conversación con IA
- **DM**: Mensaje directo al bot para conversación privada
- **Prefijo**: Usa el prefijo configurado para comandos específicos
- Roles:
  - vigia_noticias: !vigianoticias, !vigianoticias
  - buscar_anillo: !acusaranillo
**Desarrollado con ❤️ para la comunidad**
-----------------------------------------------------------------------------------------

# 🛠️ Instalación en entorno virtual python
-----------------------------------------------------------------------------------------

1. **Clonar el repositorio**
   ```bash
   git clone https://github.com/tu-usuario/RoleAgentBot.git
   cd RoleAgentBot
   ```

2. **Crear entorno virtual**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # o
   venv\Scripts\activate  # Windows
   ```

3. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar variables de entorno**
   ```bash
   cp .env.example .env
   # Editar .env con tus API keys y configuración
   ```

5. **Configurar el bot**
   - Editar `agent_config.json` según tus necesidades
   - Configurar los roles automáticos deseados
   - Ajustar la personalidad del bot en `personality.json`

# ⚙️ Configuración

## Archivos de Configuración

- **`.env`**: Variables de entorno (API keys, tokens)
- **`agent_config.json`**: Configuración principal del bot y roles
- **`personality.json`**: Configuración de personalidad del bot

## Variables de Entorno (.env)

```env
DISCORD_TOKEN=tu_token_de_discord
GOOGLE_API_KEY=tu_api_key_de_google
GROQ_API_KEY=tu_api_key_de_groq
```

## Configuración de Roles (agent_config.json)

```json
{
  "platform": "discord",
  "roles": {
    "nombre_del_rol": {
      "script": "roles/nombre_del_rol.py",
      "interval_hours": 1,
      "enabled": true
    }
  }
}
```

# 🚀 Ejecución

```bash
python run.py
```

El bot iniciará automáticamente:
- El bot de Discord principal
- El planificador de roles automáticos
- Todos los roles configurados y habilitados

-----------------------------------------------------------------------------------------

# 🐳 Despliegue con Docker
-----------------------------------------------------------------------------------------

## 1️⃣ Preparación inicial (una sola vez)

```bash
# Clonar el repositorio
git clone https://github.com/tu-usuario/RoleAgentBot.git
cd RoleAgentBot

# Configurar variables de entorno (API keys) .Editar .env con tus tokens y API keys
cp .env.example .env
 
# Construir la imagen base (solo cuando cambia requirements.txt)
docker build -f Dockerfile.base -t roleagentbot-base:latest .
```

## 2️⃣ Despliegue con volumen compartido Python (método por defecto)

```bash
# Lanza múltiples bots compartiendo librerías Python (ahorro máximo)
docker compose -f docker-compose.shared.yml up --build -d

# Verificar uso de memoria compartida
docker stats --no-stream
```

### 2️⃣b Despliegue de instancia única (si prefieres)

```bash
# Opción A: Docker Compose (instancia separada)
PERSONALITY=kronk ACTIVE_ROLES=vigia_noticias,buscar_anillo \
  docker compose up --build -d

# Opción B: Docker manual
docker build \
  --build-arg PERSONALITY=kronk \
  --build-arg ACTIVE_ROLES=vigia_noticias,buscar_anillo \
  -t roleagentbot:latest .

docker run --env-file .env \
  -v $(pwd)/databases:/app/databases \
  -v $(pwd)/logs:/app/logs \
  --name roleagentbot \
  -d \
  roleagentbot:latest
```
### 2️⃣c Añadir un tercer bot compartiendo el volumen Python

#### Construir imagen para el tercer bot
docker build --build-arg PERSONALITY=default \
  --build-arg ACTIVE_ROLES=rol_extra1,rol_extra2 \
  -t roleagentbot:extra .

#### Lanzar tercer bot compartiendo el volumen Python
docker run -d \
  --name roleagentbot-extra \
  --env-file .env \
  -e DISCORD_TOKEN=$DISCORD_TOKEN_EXTRA \
  -e PERSONALITY=default \
  -e ACTIVE_ROLES=rol_extra1,rol_extra2 \
  -v $(pwd)/databases-extra:/app/databases \
  -v $(pwd)/logs-extra:/app/logs \
  -v roleagentbot_python-shared:/usr/local/lib/python3.13/site-packages \
  roleagentbot:extra

#### Reconstruir y levantar todos los contenedores
docker compose -f docker-compose.shared.yml up --build -d

## 3️⃣ Verificación y monitoreo

```bash
# Ver logs del contenedor
docker compose logs -f

# Ver logs específicos del bot
docker exec roleagentbot tail -f /app/logs/agent.log

# Verificar estado
docker compose ps
```

## 4️⃣ Cambiar personalidad o roles

```bash
# Detener contenedor actual
docker compose down

# Lanzar con nueva configuración
PERSONALITY=putre ACTIVE_ROLES=pedir_oro,buscar_anillo \
  docker compose up --build -d
```

## 5️⃣ Actualizar dependencias

```bash
# Reconstruir solo la imagen base (más rápido)
docker build -f Dockerfile.base -t roleagentbot-base:latest .

# Volver a construir la imagen del bot
docker compose up --build -d
```

## Variables inyectables en build-time

| Argumento | Descripción | Ejemplo |
|-----------|-------------|---------|
| `PERSONALITY` | Nombre del JSON de personalidad (sin extensión) | `kronk` |
| `ACTIVE_ROLES` | Roles a habilitar, separados por coma | `vigia_noticias,buscar_anillo` |

Si se omiten, se usan los valores definidos en `agent_config.json`.

## Volúmenes persistentes

| Volumen host | Ruta contenedor | Contenido |
|-------------|-----------------|-----------|
| `./databases` | `/app/databases` | Base de datos SQLite |
| `./logs` | `/app/logs` | Ficheros de log rotativos |

# Instancias individuales (si necesitas aislamiento total)

```bash
# Instancia 1: Kronk con vigía y buscador de anillos
docker compose -f docker-compose.kronk.yml up --build -d

# Instancia 2: Putre con peticiones de oro y buscador de anillos  
docker compose -f docker-compose.putre.yml up --build -d

# Instancia 3: Default (usa agent_config.json tal cual)
docker compose -f docker-compose.default.yml up --build -d
```

#### Gestión de múltiples instancias

```bash
# Ver todas las instancias corriendo
docker ps --filter "name=roleagentbot"

# Ver logs de una instancia específica
docker compose -f docker-compose.kronk.yml logs -f

# Detener una instancia específica
docker compose -f docker-compose.kronk.yml down

# Reiniciar una instancia específica
docker compose -f docker-compose.kronk.yml restart

# Detener todas las instancias
docker compose -f docker-compose.kronk.yml down
docker compose -f docker-compose.putre.yml down
docker compose -f docker-compose.default.yml down
docker compose -f docker-compose.minimal.yml down
```

### Arquitectura optimizada: Capas + Volumen compartido

El proyecto combina dos técnicas de optimización para máximo ahorro de recursos:

```
┌─ Capas Docker (disco) ──────────────────────┐
│ roleagentbot-base: 150MB (librerías pip)    │
│ roleagentbot:kronk: +5MB (código fuente)    │
│ roleagentbot:putre: +5MB (código fuente)    │
└──────────────────────────────────────────────┘
           ↓
┌─ Volumen compartido (memoria RAM) ───────────┐
│ python-shared: 150MB (librerías cargadas)   │
│ ↳ Ambos contenedores usan las mismas libs   │
└──────────────────────────────────────────────┘
```

### ¿Cómo funciona la optimización completa?

| Nivel | Técnica | Ahorro | Cuándo se aplica |
|-------|---------|--------|------------------|
| **Disco** | Capas Docker | 48% | Al construir imágenes |
| **Memoria** | Volumen compartido | 37% | Al ejecutar contenedores |
| **Red** | Descarga única | 50% | Al instalar dependencias |

### Flujo de construcción y ejecución

```bash
# 1️⃣ Imagen base (capa compartida en disco)
docker build -f Dockerfile.base -t roleagentbot-base:latest .
# ↓ 150MB guardados una sola vez

# 2️⃣ Imágenes específicas (heredan la base)
docker build --build-arg PERSONALITY=kronk -t roleagentbot:kronk .
docker build --build-arg PERSONALITY=putre -t roleagentbot:putre .
# ↓ Solo +5MB por cada imagen

# 3️⃣ Ejecución con volumen compartido (memoria compartida)
docker compose -f docker-compose.shared.yml up --build -d
# ↓ ~250MB RAM total vs ~400MB sin optimización
```

### Resumen visual de la arquitectura completa

```
📦 DOCKER IMAGES (Capas - Disco)
┌─────────────────────────────────────┐
│ roleagentbot-base: 150MB             │ ← Librerías pip (compartido)
│  ├── discord.py, groq, cohere...   │
│  └── python:3.13-slim               │
├─────────────────────────────────────┤
│ roleagentbot:kronk: 155MB (+5MB)     │ ← Hereda base + código
│  ├── run.py, agent_*.py             │
│  ├── personalities/kronk.json        │
│  └── roles/                          │
├─────────────────────────────────────┤
│ roleagentbot:putre: 155MB (+5MB)     │ ← Hereda base + código
│  ├── run.py, agent_*.py             │
│  ├── personalities/putre.json        │
│  └── roles/                          │
└─────────────────────────────────────┘
           ↓ build-time optimization
🚀 DOCKER CONTAINERS (Runtime - Memoria)
┌─────────────────┐    ┌─────────────────┐
│ roleagentbot-    │    │ roleagentbot-    │
│ kronk            │    │ putre            │
│ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │ App: 50MB   │ │    │ │ App: 50MB   │ │
│ └─────────────┘ │    │ └─────────────┘ │
│ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │ Python:150MB│◄───┼──►│ Python:150MB│ │ ← Volumen compartido
│ └─────────────┘ │    │ └─────────────┘ │
│ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │ DB: 10MB    │ │    │ │ DB: 10MB    │ │ ← Individual
│ └─────────────┘ │    │ └─────────────┘ │
│ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │ Logs: 5MB   │ │    │ │ Logs: 5MB   │ │ ← Individual
│ └─────────────┘ │    │ └─────────────┘ │
└─────────────────┘    └─────────────────┘
Total RAM: ~250MB vs ~400MB tradicional
```
