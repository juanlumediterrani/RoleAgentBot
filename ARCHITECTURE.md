# RoleAgentBot — Current Architecture

## 1. Purpose

RoleAgentBot is a personality-driven Discord agent with:

- **A single main Discord bot process**
- **Optional scheduled role and behavior processes**
- **Per-server persistence**
- **LLM-backed chat, greetings, memory synthesis, and role logic**
- **Dyncamically prompt building**

The command system is **registered dynamically** from configuration and available role modules.

## 2. Runtime Topology

```text
run.py
├── discord_bot()                          → keeps the main Discord bot alive
│   └── discord_bot/agent_discord.py
│       ├── discord_core_commands.py       → core commands and runtime controls
│       ├── discord_role_loader.py         → dynamic role command registration
│       ├── discord_utils.py               → shared Discord/runtime helpers

│
└── scheduler()                            → periodic background execution
    ├── role subprocesses                  → news_watcher, treasure_hunter, trickster, banker
    ├── subrole internal tasks             → beggar, ring
    └── memory maintenance    
    └── behavior/
        ├── greet.py                   → presence greetings
        └── welcome.py                 → member welcome messages
```

## 3. Core Execution Model

There are **two runtime layers**:

| Layer | Responsibility | Execution mode |
|------|------|------|
| `Main bot` | Discord connection, commands, events, chat, greetings, MC voice features | Persistent process |
| `Scheduler` | Launches optional role scripts and memory refresh tasks | Loop in `run.py` |

There are also **two role integration modes**:

| Mode | What it means | Examples |
|------|------|------|
| `Integrated Discord role` | Commands run inside the main bot process | `mc`, all `*_discord.py` command modules |
| `Scheduled role task` | Autonomous logic runs on a timer | `news_watcher.py`, `treasure_hunter.py`, `trickster.py`, `banker.py` |

## 4. Main Entry Points

### `run.py`

System orchestrator:

- Loads `agent_config.json`
- Starts the main Discord bot subprocess
- Builds the schedule for enabled roles
- Executes due role tasks
- Executes due internal subrole tasks
- Refreshes memory layers on their own cadence

### `discord_bot/agent_discord.py`

Main Discord runtime:

- Creates the Discord client with limited intents
- Loads core commands
- Dynamically loads enabled role commands
- Selects and persists the active server
- Starts automatic Discord-side loops
- Handles events, messages, mentions, greetings, and MC voice lifecycle

### `agent_engine.py`

LLM and prompt orchestration:

- Loads `agent_config.json`
- Loads the active personality from split JSON files
- Builds system prompts and contextual prompt additions
- Executes `think(...)`
- Generates daily, recent, and relationship memories
- Executes internal subrole prompts for autonomous behaviors

## 5. Configuration Model

### `agent_config.json`

Defines:

- Active personality
- Platform
- Enabled roles
- Role intervals
- Role scripts
- Trickster subrole settings
- MC mode and voice features

Current configured roles:

- `news_watcher`
- `treasure_hunter`
- `trickster`
- `mc`
- `banker`

### Personality files

The active personality is loaded from `personalities/<name>/`:

- `personality.json` → identity and style
- `prompts.json` → system prompts and role/subrole prompt content
- `answers.json` → Discord-facing text from the personality
- `descriptions.json` → UI/description strings

## 6. Discord Command Architecture

Command registration happens once during `on_ready()`:

1. `register_core_commands(bot, agent_config)`
2. `register_all_role_commands(bot, agent_config, PERSONALIDAD)`

### Core command layer

`discord_core_commands.py` contains the shared operational commands, including:

- Help and discovery
- Greeting toggles
- Insult/test utilities
- Role enable/disable controls
- Runtime state helpers for taboo and talk systems

### Dynamic role command layer

`discord_role_loader.py` registers commands for enabled roles using `ROLE_REGISTRY`.

Current canonical role registry:

- `news_watcher`
- `treasure_hunter`
- `trickster`
- `banker`

`mc` is registered separately and always attempted first.

## 7. Event and Message Flow

### Startup flow

```text
run.py
→ starts discord_bot/agent_discord.py
→ bot connects to Discord
→ on_ready()
→ register core commands
→ register enabled role commands
→ choose active guild
→ publish active server for DB/log usage
→ start automatic loops
```

### Chat flow

```text
Discord message
→ on_message()
→ if command prefix: process command
→ else if taboo trigger: generate taboo response
→ else if DM or mention: _process_chat_message()
→ think(...)
→ store interaction in AgentDatabase
→ send response
```

### Greeting flow

Presence and join behaviors are separated into `behavior/`:

- `behavior/welcome.py` handles member join greetings
- `behavior/greet.py` handles offline → online presence greetings

Both use:

- Persisted greeting state
- Personality prompt generation through `think(...)`
- Interaction logging in the server database

## 8. Persistence Model

### Server scoping

The system is server-aware. The active server is published through:

- `.active_server`
- `ACTIVE_SERVER_NAME` environment propagation

This affects:

- Database path selection
- Log path selection
- Memory summaries
- Role task context

### `agent_db.py`

Primary SQLite runtime storage. It persists:

- Interaction history
- Recent dialogue windows
- Daily memory
- Recent memory
- User relationship memory
- Daily user relationship snapshots
- Pending relationship refresh state
- Notable memories

The database is isolated per server, with fallback relocation when needed.

### Behavior and role-specific databases

Additional SQLite-backed stores exist for:

- Behavior state
- Taboo system state
- Banker state
- News watcher state
- MC state
- Treasure hunter / PoE2 state
- Trickster subrole state

## 9. Memory Architecture

The current memory system has four logical layers:

| Layer | Purpose | Refresh cadence |
|------|------|------|
| `recent_dialogue` | Short-lived prompt context from recent exchanges | Read on demand |
| `recent_memory` | Rolling summary of the current day since the last cursor | Every 4 hours |
| `daily_memory` | Daily synthesis of the server's interactions | Every 24 hours |
| `user_relationship_memory` | Per-user relationship summary | Every 1 hour when due |

This lets `think(...)` combine immediate context, short-term synthesis, and durable relational context.

## 10. Role Responsibilities

### `behaviors` Off role responsabilities
- Scheduled off roles tasks
- Some different bot interactions like: Greetings, Welcome, Taboo etc.
- Provides funtions to subscribe the server to recive alerts when some event happen.

### `news_watcher`

- Scheduled watcher role that you can configure frecuency.
- Give a subscriptions service that warn whit a message about news, previusly analyced by a method.
- Provides Discord administration commands for activation, notifications, channels, and help

### `treasure_hunter`

- Scheduled treasure search role
- Includes PoE2-specific persistent data and automation
- Also has a Discord-side automatic loop in the main bot for hourly in-process treasure checks

### `trickster`

- Scheduled role with subroles
- Includes:
  - `beggar` → autonomous/internal prompt task
  - `dice_game` → interactive game logic
  - `ring` → autonomous/internal prompt task

### `banker`

- Scheduled economic role
- Exposes balance, bonus, and TAE-related command flows

### `mc`

- Fully integrated Discord/voice role
- No scheduler subprocess in integrated mode
- Handles music playback, queueing, presence text, and auto-disconnect behavior

## 11. Automatic Tasks

### In `run.py`

- Enabled role subprocess scheduling
- Internal subrole task execution
- Recent memory refresh
- Daily memory refresh
- Relationship memory refresh

### In `discord_bot/agent_discord.py`

- Daily database cleanup
- Hourly treasure hunter loop when available
- Voice auto-disconnect for MC when channels become empty

## 12. Logging and Operational State

### `agent_logging.py`

Provides:

- Console logging
- Rotating file logging
- Server-aware log routing
- Personality-aware file naming

Observed active logs confirm current runtime use of server-scoped files and treasure hunter activity.

## 13. Key Design Rules

- **Single Discord connection**: only one main bot process owns the gateway connection
- **Dynamic command registration**: commands come from enabled modules, not a static monolith
- **Per-server isolation**: logs, DB state, and memory are server-scoped
- **Personality-driven UX**: user-facing behavior comes from JSON personality content
- **Split responsibility**: Discord interaction logic and scheduled autonomous logic are separated
- **Config-first activation**: roles are enabled by `agent_config.json`, then refined by persisted behavior state

## 14. Current Directory Map

```text
RoleAgentBot/
├── run.py
├── agent_engine.py
├── agent_db.py
├── agent_logging.py
├── agent_runtime.py
├── agent_config.json
├── behavior/
├── discord_bot/
├── roles/
├── personalities/
├── databases/
└── logs/
```

## 15. Step by step logic funcionally (writed by de user)

### Personalidad
La personalidad del bot se divide en 4 archivos. Cada uno tiene respectivamente la personalidad y las respuestas automaticas del bot.

### Memoria
El sistema de memoria intenta simular una consciencia contextual para el bot ayudando ser mas asertivo con sus respuestas y proporcionandole una persitencia a largo plazo, mediante sintesis y recuerdos remarcados.

#### Consciencia base (Parrafo de 500 characteres)
  - Se inicializa con parrafo neutro desde los archivos de personalidad. 
  - Una vez por dia, en la noche el bot hace una sintesis de suenyo de la siguiente manera:
    -Coge el parrafo que tiene para ese dia y el ultimo recibido de "recuerdos recientes"
    -Se le pasa un prompt a 'think' tal que (systempromt  es la personalidad, user prompt son los dos parrafos a sintetizar,reglas de oro para escribir el parrafo y la siguiente tarea: Anyade una sintesis del segundo parrafo al primero, sin perder la esencia del primero, el peso relativo en importancia es 80% para el primero) 
    -El prompt de la tarea que se pasan al LLM es inyectada desde el directorio de la personalidad, y en codigo solo hay un fallback.
    -Recibimos el nuevo parrafo y lo colocamos como Consciencia base de ese dia.
    -Antes de cerrar, se hace una tirada de "dreaming" (Tiene que ser del 33% si la tabla de recuerdos remarcados es mayor a 10, si no, su prob. es del 10%). Esta funcion hace lo siguiente:
      -Dreaming: Se vuelve a construir un prompt como el anterior pero solo con la consciencia base actual, y se le inyecta un recuerdo remarcado de la tabla relativa de la siguiente manera. Se inyecta un prompt especifico de la tarea desde el archivo de prompts.json(dejando un fallback en el codigo) con las reglas de oro y la siguiente tarea: Has sonyado con el siguiente recuerdo(recuerdo remarcado), anyade un pequenyo detalle del recuerdo a la consciencia base (parrafo).
    -De haber corrido la funcion dreaming, actualizamos el parrafo de consiencia base con el nuevo parrafo. Y dejamos ese parrafo como consciencia base para ese nuevo dia.

    
#### Recuerdos recientes (Parrafo de 250 characteres)
  - Se inicializa con parrafo neutro desde los archivos de personalidad.
  - Cada 4 horas hace una actualizacion de este parrafo de haber habido interaciones nuevas de la siguiente manera:
    -Coge el parrafo actual de recuerdos recientes y las ultimas interaciones con el bot en las ultimas 4 horas.
    -Llama a think inyectando recuerdos recientes+ ultimas interaciones + tarea + reglas de oro
    -Las reglas de oro contemplan como escribir el parrafo de 250 caracteres
    -La tarea: Sintetiza las ultimas interaciones, y anyadelas al parrafo de recuerdos recientes, sin perder su esencia. Ademas, extrae un recuerdo remarcado de haber ocurrido algo importante.
    -Ambos trozos de prompts se inyectan desde el directorio de personalidad y en el codigo hay un fallback en ingles.
    -Obtenemos el nuevo parrafoo y el recuerdo remarcado de haberlo.
    -Actualizamos el parrafo de recuerdos recientes y apuntamos el recuerdo remarcado.

#### Relacion con el usuario (Parrafo de 250 caracteres)
 - Se inicializa con parrafo neutro desde los archivos de personalidad.
  - Cada hora hace una actualizacion de este parrafo de haber habido interaciones nuevas de la siguiente manera:
    -Coge el parrafo actual de relacion con el usuario y las ultimas interaciones del bot con el usuario en la ultima hora.
    -Llama a think inyectando relacion con el usuario+ ultimas interaciones + tarea + reglas de oro
    -Las reglas de oro contemplan como escribir el parrafo de 250 caracteres
    -La tarea: Sintetiza las ultimas interaciones con el usuario, y modifica el parrafo de relacion con el usuario, sin perder su esencia.
    -Ambos trozos de prompts se inyectan desde el directorio de personalidad y en el codigo hay un fallback en ingles.
    -Obtenemos el nuevo parrafo y actualizamoos la relacion con el usuario.


  
  
  
### Interaciones y succesos
El bot registra en su base de datos personal cada interacion que hace con los usuarios y con el servidor. Las guarda por 4 horas, para sintetizarlas luego en memoria. Los diferentes roles escriben interaciones que el bot luego va usar.

### Comportamientos
Aqui se agrupan un conjunto de funciones que crean tareas al bot o evetos que interactuan con los usuarios por dm y por canal.

#### Conversaciones
El bot responde a menciones por el canal y mensajes directos. Guarda las interaciones para futuras sintesis.

#### Saludos
El bot responde a cuando los usuarios pasan de desconectados a conectados, y les manda un saludoo. Se puede activar o desactivar. Tiene su propio prompt de la carpeta de la personalidad para este comportamiento, que propone la tarea para el LLM.

#### Bienvenida
El bot da la bienvenida a un usuario cuando se une al servidor, funciona de manera similar a 'Saludos'.

#### Comentarios
El bot hace un comentario en relacion a los roles activados. Se contruye un prompt donde se mandan los roles activados y se especifica la tarea para el LLM, ambas cosas se cargan desde la carpeta de la personalidad.

#### Tabu
El bot se siente aludido al usar ciertas palabras por un canal suscrito, responde a ello. Se carga un prompt especifico como anteriormente y una tarea para que escriba un comentario en el canal en cuestion.

#### Control de roles
Activa o desactiva los roles desde Discord, dinamicamente.

### Roles
Diferentes funcionalidades que se aplican bajo un rol activable al bot. Modifican parte de su contexto y proveen de diferentes servicios.

#### Vigia de noticias
Maneja diferentes suscripciones de un usuario o un servidor. Las suscripciones hacen que la tarea automatica del rol, envie mensajes con alertas personalizados sobre las noticias interesantes a los usuarios, cuenta con tres metodos para analizar el contenido de las noticias:
  -Flat: Sin analisis, se envia la opinion de la personalidad sobre el titulo y la descripcion de la noticia.
  -Keyword: Se filtra el titulos y la descripcion de las noticias por un cojunto de palabras clave configuradas por el usuario.
  -General: Se envia a Cohere la noticia con las premisas configuradas por el usuario, se le dice que verifique si coincide la noticia con alguna premisa. De ser asi, se pasa la noticia a la personalidad(func. think) para que de su opinion y avise al usuario.
Las bases de datos de las noticias descargadas por cartegorias son globales, compartidas por todos los servidores.
Las premisas estan hasheadas y guardadas tambien como hash, al comprobar una suscripcion por premisa, si esa noticia ya habia sido comprobada con ese mismo hash, se pasa el resultado en vez de volverlo a comprobar.
Maximo 3 suscripciones de cualquier tipo por usuario, y 5 para los servidores (repartidas por diferentes canales o en uno mismo)
Existen funciones para listar las suscripiones/categorias/feeds.
Cada categoria puede albergar diferentes feeds.
Para realizar una nueva suscripcion la categoria es obligatoria y feed opcional. Lo mismo para desactivar la suscripcion, eliminando la ultima de la lista de esa categoria de haber mas de una suscripcion.

#### Buscador de tesoros
Comprueba precios de objetos digitales y envia senyales interesantes para el usuario, ademas de mantener el precio actualizado de los objetos objetivo.

##### Tesoros Path of Exile 2
Subrole de buscador de tesoros, especifico para Path of Exile 2, mantiene un historico de precios sobre unos objetos en una lista suscrita por el usuario y le envia senyales de compra o venta cuandoo el precio llega a un umbral.
-Mantiene una lista de equivalencias de nombres de items y su id de manera global.
-Va anyadiendo historicos de los precios de una liga en concreto de forma global a medida que los usuarios le demanden mas objetos en sus suscripciones.
-Cada hora, el bot comprueba sus suscripciones y anyade el ultimo precio al historico que ya guarda de cada objeto.
-Una vez actualizado los precios, se comprueba si alguno esta en un umbral de maximo/minimo, si es asi se envia la notificacion al usuario llamando a (think) con unos prompts personalizados inyectado desde prompts.json que contienen las reglas de oro de esta tarea y la siguiente tarea: Avisa al usuario que el objeto {nombre del objeto} esta en un punto interante y es momento de {comprar/vender}
-El usuario puede consultar su lista personal con los precios actualizados. Solo puede tener una suscripcion limitada por la liga
-Un canal cuenta como un usuario, puede tener una suscripcion de una liga con sus respectivos objetos suscritos.

##### (Futuramente) Path of Exile 1

#### Trilero
Rol que recopila un cojunto de juegos y funciones de rol para interactuar con el bot.

##### El bote
Juego de dados, el bot tiene una cuenta especial en el rol tesorero para el bote. Y propone un juego de dados para el usuario. El juego consiste en consguir una tirada de 3 dados de 6 con un 'Uno' en cada cara, si el usuario consigue este resultado se lleva el bote. Otras jugadas premiadas son 'tripe' multiplica la apuesta por 3,'escalera(cualquier tipo)' y 'doble' multiplican la apuesta por dos, otros casos pierde la apuesta fija por el juego.
El rol tiene funciones para mostrar el bote, realizar una jugada, mostrar el historial de jugadas incluso mostrar un ranking de el mayor premio otorgado.

##### El anillo unico
El bot tiene la mision de buscar el anillo unico, y va interrogando a los usuarios por el. Los usuarios pueden acusarse entre si para que el bot vaya a buscar al acusado. Se activa y configura con una frecuencia por administrador del servidor.

##### Limosna
El bot tiene la mision de pedir oro a los usuarios por diferentes razones, el subrol elige una razon para el dia y va pidiendo oro a los usuarios configurada una frecuencia y activacion por administrador.

#### MC
Permite al usuario buscar canciones y anyadirlas a una lista reproduccion para escucharlas en un canal de voz.
Tiene diferentes funciones para realizar cada tarea y gestionar la cola de reproduccion. Ademas las interaciones se guardan como una iteracion resumida en el historial. Y tambien cuenta para la relacion con el usuario.

#### Tesorero
Mantiene una base de datos con cuentas y transacciones de monedas de oro de los usuarios y los roles implicados.
Reparte una bonificacion por apertura de cuenta y otra diaria configurables por administrador.


### Suite de comandos
Esta suite resuelve todas las funciones utiles para el usuario y los administradores en una serie de comandoos para discord, hay comandos fijos y otros que se cargan dinamicamente si el rol esta o no activo.

### Suite Canvas GUI
La suite de canvas es la experiencia ultima del usuario para interactuar con el bot. Comparte titulos y descripciones y respuestas de la suite de comandos.
Las vistas se construyen con la siguiente estructura general:
-Titulo del embeded (Inyectado desde el archivo de descritions.json)
-Primer bloque: Descripcion de la vista actual desde descriptions.json
-Segundo bloque: lista o estado de las funciones relevantes para esa vista
-Tercer bloque: Dinamico, va cambiando segun el usuario vaya eligiendo opciones el el dropdown, muestra la salida de la funcion ejecutada.
-Cuarto bloque: Comentario de vuelta por parte del bot de los mensajes automaticos de anwsers.json

-Botones de las views hermanas
-Dropdown de configuracion de un metodo de haberlo
-Dropdown para interactuar con las diferentes funciones relacionadas con la vista
-Botones de back y home.

La estructura actual del canvas es:
!canvas -> home/overview
-home/
-home/overview ( es lo mismo que home, y que !canvas)
-roles/
-roles/watcher
-roles/watcher/personal(esta vista overview de watcher)
-roles/watcher/admin(channels and config)
-roles/hunter
-roles/hunter/poe2
-roles/hunter/poe2/items(esta vista es el overview de poe2)
-roles/hunter/poe2/league
-roles/hunter/poe2/admin
-roles/hunter/poe2/admin/items(esta vista es el overview de poe2/admin)
-roles/hunter/poe2/admin/league
-roles/hunter/poe2/admin/config (permite activar y desactivar el rol poe2)
-roles/trickster/
-roles/trickster/dice
-roles/trickster/dice/personal (esta vista es el overview de dice)
-roles/trickster/dice/admin (config admin server)
-roles/trickster/ring
-roles/trickster/ring/personal (esta vista es el overview de ring)
-roles/trickster/ring/admin (config admin server)
-roles/trickster/beggar
-roles/trickster/beggar/personal (esta vista es el overview de beggar)
-roles/trickster/beggar/admin (config admin server)
-roles/mc
-roles/banker
-roles/banker/personal(esta vista es el overview de banker)
-roles/banker/admin

-behavior/
-behavior/conversation(esta vista es el overview de behavior)
-behavior/greetings
-behavior/welcome
-behavior/comentary
-behavior/taboo
-behavior/role_control

-help
-help/personal(esta vista es el overview de help)
-help/admin
