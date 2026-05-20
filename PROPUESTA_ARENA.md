# Propuesta: Modulo Arena (Batallas, Armas y Personalidad de Combate)

> Documento de diseno aprobado. Version 1.0.

---

## 1. Decisiones de Diseno (Aprobadas)

| Aspecto                      | Decision |
|------------------------------|----------|
| **Canal Arena**              | El bot **crea automaticamente** un canal `#arena` al activar el rol. Requiere permisos de gestion de canales. Si no puede crearlo, notifica al admin. |
| **Mecanica de victoria**     | **Narrativa pura**. El LLM decide el ganador libremente basado en experiencia, armas, personalidad de combate y coherencia narrativa. No hay stats numericos ni formulas. |
| **Armas**                    | **6 armas** por personalidad del bot, con **matriz individual de ventajas** (cada arma tiene pros/contras especificos contra cada otra arma del mismo set). |
| **Participantes**            | Coliseo: **minimo 4**. Torneo: **minimo 8**. Si no se alcanza el minimo al expirar el timer, el evento se **retrasa 24h** (con notificacion). Si tras 3 retrasos no se alcanza, se cancela. |
| **Personalidad de combate**  | **Catalogo cerrado**: 5 opciones predefinidas por personalidad del bot. El LLM escoge una durante la sintesis de relacion. |
| **Frecuencia de eventos**    | **Solo Canvas bajo demanda**. Sin scheduler automatico. Los admin/usuarios programan eventos desde `!canvas role arena`. |
| **Armas cross-personalidad** | **NO**. Cada servidor solo usa el set de armas de la personalidad del bot activa en ese servidor. No hay mezcla de tematicas. |

---

## 2. Vision General

El modulo **Arena** introduce un sistema de batallas narrativas gestionadas por el LLM, donde los usuarios del servidor compiten con armas desbloqueables y una "personalidad de combate" que el bot asigna segun su relacion con cada usuario.

Se integra como un **rol** dentro del ecosistema RoleAgentBot, con sus propios:

- Subroles: `duelo`, `coliseo`, `torneo`
- Canvas UI (`!canvas role arena`)
- Prompts de batalla inyectados en el sistema prompt del bot
- Almacenamiento NoSQL de estadisticas, armas desbloqueadas y historial

---

## 3. Componentes Principales

### 3.1 Canal de Arena

Al activar el rol Arena en un servidor:

1. El bot intenta crear un canal de texto llamado `arena` (o `arena-{nombre-bot}` si `arena` ya existe).
2. Si no tiene permisos, envia un mensaje al admin solicitando que cree el canal manualmente y lo configure.
3. El ID del canal se almacena en `server_config.json` bajo `roles.arena.config.channel_id`.
4. **Funciones del canal**:
   - Anuncios de proximos coliseos/torneos (embeds con boton "Apuntarme" + timer)
   - Resultados de batallas (duelos, coliseos, torneos)
   - Ranking/leaderboard del servidor
   - Historial reciente de batallas

### 3.2 Atributos del Usuario (Peleador)

Para cada usuario, se almacenan en NoSQL:

| Campo | Descripcion |
|-------|-------------|
| `wins` | Batallas ganadas (total) |
| `participated` | Batallas participadas (total) |
| `fighter_personality` | Personalidad de combate asignada por el LLM |
| `unlocked_weapons` | Lista de IDs de armas desbloqueadas |
| `active_weapon` | Arma equipada actualmente |
| `xp` | Experiencia de arena (puntos de desbloqueo) |
| `duel_wins` / `duel_participated` | Stats especificas de duelo |
| `coliseo_wins` / `coliseo_participated` | Stats especificas de coliseo |
| `tournament_wins` / `tournament_participated` | Stats especificas de torneo |

### 3.3 Personalidad de Combate

Durante la actualizacion de memoria/relacion con el usuario, si el rol Arena esta activo, el LLM genera (ademas del parrafo de sintesis habitual) una **personalidad de peleador** elegida entre el catalogo de la personalidad del bot activa.

El catalogo se inyecta como contexto extra en el prompt de sintesis de relacion. Ejemplo para Hans:

```
Ademas del resumen de relacion habitual, asigna a este usuario una de las siguientes personalidades de combate:

- BERSERKER: Ataca sin pensar, furia descontrolada, cuanto mas herido mas peligroso.
- DUELISTA: Preciso, calculador, busca el golpe perfecto, evita riesgos innecesarios.
- ESTRATEGA: Manipula el entorno, usa trampas y enganos, nunca ataca frontalmente.
- GLADIADOR: Espectaculo y dominio, busca impresionar a la multitud, resistente.
- VANGUARDIA: Protege a aliados, cuerpo a cuerpo implacable, sacrificio controlado.

Elige la que mejor encaje con el comportamiento observado del usuario. Devuelve el resultado en el formato:
[FIGHTER_PERSONALITY: <nombre>]
```

Ver Seccion 8 para los catalogos completos de todas las personalidades del bot.

### 3.4 Sistema de Armas

Cada personalidad del bot ofrece un set tematico de **6 armas**. Las armas no otorgan stats numericos, pero tienen **pros/contras narrativas** contra otras armas del mismo set que el LLM DEBE respetar al narrar la batalla.

**Sistema de desbloqueo por XP**:

- Coliseo completado: **1.0 XP**
- Torneo completado: **1.0 XP**
- Duelo completado: **0.2 XP**

**Tabla de desbloqueo (provisional, ajustable por admin)**:

| Arma #          | Requisito XP | Ejemplo (Hans)       |
|-----------------|--------------|----------------------|
| 1 (por defecto) | 0            | Espada larga         |
| 2               | 2.0          | Hacha de guerra      |
| 3               | 5.0          | Lanza de caballeria  |
| 4               | 9.0          | Maza de acero        |
| 5               | 14.0         | Espadon a dos manos  |
| 6               | 20.0         | Alabarda ceremonial  |

El admin puede ajustar los umbrales de XP via Canvas (`!canvas role arena` → Configuracion).

### 3.5 Matriz de Ventajas de Armas

Cada arma tiene una relacion especifica con cada otra arma del mismo set. Las ventajas son **puramente narrativas**: el LLM debe tenerlas en cuenta al narrar, pero no modifican una formula de victoria (porque no hay formula).

Codigos de relacion:

- `++` Ventaja narrativa fuerte
- `+` Ventaja narrativa leve
- `=` Neutral
- `-` Desventaja narrativa leve
- `--` Desventaja narrativa fuerte

Ejemplo (Hans - ver Seccion 8 para matrices completas):

| Arma | vs Espada | vs Hacha | vs Lanza | vs Maza | vs Espadon | vs Alabarda |
|------|-----------|----------|----------|---------|------------|-------------|
| Espada | = | - | + | -- | ++ | - |
| Hacha | + | = | -- | ++ | - | + |

El LLM recibe esta matriz en el prompt de batalla como referencia.

### 3.6 Modos de Batalla

| Modo | Participantes | XP otorgado | Donde se juega | Requisitos | Si falla minimo |
|------|---------------|-------------|----------------|------------|-----------------|
| **Duelo** | 2 | 0.2 | DM (resultado en canal Arena) | 2 jugadores, invitacion aceptada | N/A (1v1) |
| **Coliseo** | 4+ | 1.0 | Canal Arena | 4+ jugadores apuntados | Retrasa 24h (max 3 retrasos) |
| **Torneo** | 8+ | 1.0 | Canal Arena | 8+ jugadores apuntados | Retrasa 24h (max 3 retrasos) |

**Coliseo**: El LLM recibe a todos los participantes y debe ir eliminando progresivamente hasta quedar uno. Divide la narrativa en "fases de eliminacion" donde en cada fase caen 1-2 participantes, hasta el enfrentamiento final.

**Torneo**: El codigo genera el bracket de eliminacion. Cada combate del bracket se resuelve con el prompt de batalla estandar (1v1). El LLM narra cada ronda. El bracket se actualiza y publica en el canal entre rondas.

---

## 4. Prompts de Batalla (Definitivos)

### 4.1 Prompt de Batalla Estandar (1v1)

```
Eres el maestro de ceremonias de una arena. Debes narrar una batalla siguiendo ESTRICTAMENTE estas reglas:

1. AMBIENTACION: Describe la arena en 1-2 frases. El tono debe ser epico y acorde a tu personalidad ({bot_personality}).

2. PARTICIPANTES:
   - Luchador A: @{user_a_name} | Personalidad de combate: {fighter_personality_a} | Experiencia: {xp_a} batallas | Arma: {weapon_a_name}
   - Luchador B: @{user_b_name} | Personalidad de combate: {fighter_personality_b} | Experiencia: {xp_b} batallas | Arma: {weapon_b_name}

3. MATRIZ DE VENTAJAS DE ARMAS (solo referencia narrativa):
   {weapon_a_name} vs {weapon_b_name}: {relation} ({relation_desc})
   Ejemplos: ++ = ventaja clara en alcance/velocidad/fuerza | -- = desventaja clara | = = parejo

4. DESARROLLO DE LA BATALLA:
   - Divide la batalla en 3-5 "asaltos" o "intercambios".
   - En cada intercambio, describe la accion narrativa con tu estilo de personalidad.
   - La experiencia en combate influye en la destreza narrativa (mas experimentado = mas propositivo).
   - Las ventajas de arma deben reflejarse en la narrativa (ej: lanza mantiene distancia vs espada).
   - La personalidad de combate debe influir en las tacticas: un Berserker carga, un Estratega espera.

5. RESOLUCION:
   - El ganador se decide NARRATIVAMENTE por ti. DEBES justificarlo coherente con:
     a) La experiencia de los contrincantes
     b) Las ventajas/desventajas de armas enfrentadas
     c) La personalidad de combate de cada uno
   - No hagas que el ganador siempre sea el mas experimentado; la narrativa debe ser entretenida.
   - Puedes dar sorpresas, remontadas, errores costosos, momentos de inspiracion.
   - Maximo 800 tokens de narrativa total.

6. RESTRICCIONES:
   - No generes contenido violento grafico explicito (gore detallado, heridas descritas anatomicamente).
   - Sangre y dolor permitidos en tono epico, no terrorifico.
   - El tono debe ser acorde a tu personalidad del bot ({bot_personality}).

7. FORMATO DE SALIDA OBLIGATORIO:
   ```
   [BATALLA]
   Ambientacion: (1-2 frases)

   Asalto 1: (descripcion)
   Asalto 2: (descripcion)
   Asalto 3: (descripcion)
   [Asalto 4-5 opcional si la batalla lo requiere]

   Ganador: @{winner_name}
   Justificacion: (1 frase explicando por que gano)
   [FIN_BATALLA]
   ```
```

### 4.2 Prompt de Coliseo (Todos contra todos, 4+ participantes)

```
Eres el maestro de ceremonias de una arena. Debes narrar un COLISEO donde multiples luchadores entran y solo uno sale victorioso.

REGLAS DEL COLISEO:

1. AMBIENTACION: Describe la arena para multiples combatientes (2-4 frases).

2. PARTICIPANTES (lista completa):
   {participant_list}
   Cada uno con: nombre, personalidad de combate, experiencia, arma.

3. DESARROLLO - FASES DE ELIMINACION:
   - El coliseo se divide en "fases". En cada fase, 1-2 participantes son eliminados narrativamente.
   - Numero de fases: para N participantes, usa aproximadamente N-1 fases (algunas fases pueden eliminar 2).
   - En cada fase, describe brevemente los enfrentamientos paralelos o secuenciales.
   - Considera alianzas temporales, traiciones, y caos general.
   - La experiencia y las ventajas de arma siguen siendo relevantes.
   - Las personalidades de combate deben influir: un Berserker ataca a todos, un Estratega espera a que otros se debiliten.

4. RESOLUCION FINAL:
   - Un solo ganador. Justifica con coherencia.
   - Puede haber remontadas, errores, momentos heroicos.
   - Maximo 1200 tokens (mas que 1v1 por la complejidad).

5. RESTRICCIONES: Mismas que batalla 1v1. No gore explicito.

6. FORMATO:
   ```
   [COLISEO]
   Ambientacion: ...

   Fase 1: ... (eliminados: @user1)
   Fase 2: ... (eliminados: @user2, @user3)
   ...
   Fase Final: ... (enfrentamiento entre @userX y @userY)

   Ganador: @{winner_name}
   Justificacion: ...
   [FIN_COLISEO]
   ```
```

### 4.3 Prompt de Torneo (Bracket de eliminacion)

El torneo NO usa un prompt especial. Cada combate del bracket se resuelve con el **Prompt de Batalla Estandar (1v1)**. El codigo gestiona:
1. Generacion del bracket inicial (random seed o por experiencia).
2. Ejecucion secuencial de cada ronda.
3. Publicacion del bracket actualizado entre rondas.
4. Narrativa del torneo completo publicada al final.

---

## 5. Flujo de Usuario

### 5.1 Inscripcion a Coliseo / Torneo

1. Desde Canvas: `!canvas role arena` → submenu Coliseo o Torneo → "Programar evento" (solo admin) o "Apuntarme".
2. El bot publica un embed en el canal Arena con:
   - Titulo: "Coliseo programado - Registro abierto"
   - Timer de cuenta atras (ej: 24h)
   - Lista de participantes apuntados
   - Boton "Apuntarme" (interactivo)
3. Al hacer clic en "Apuntarme", aparece un dropdown para escoger arma entre las disponibles para ese usuario.
4. Una vez apuntado, el bot actualiza el embed con la lista.
5. Cuando se alcanza el minimo de participantes + el timer expira, la batalla se ejecuta automaticamente.
6. Si no se alcanza el minimo, se retrasa 24h y se actualiza el embed.

### 5.2 Flujo de Duelo

1. Usuario A abre Canvas: `!canvas role arena` → Duelo → "Retar a un usuario".
2. Selecciona a Usuario B de una lista de miembros del servidor.
3. Usuario A escoge su arma entre las disponibles.
4. El bot envia DM a Usuario B:
   ```
   @{user_a} te ha retado a un duelo en la Arena.
   Arma elegida por {user_a}: {weapon_a_name}
   Aceptas el reto?
   [Boton: Aceptar] [Boton: Rechazar]
   ```
5. Si Usuario B acepta, escoge su arma.
6. Se ejecuta la batalla via LLM con el Prompt de Batalla Estandar.
7. El resultado se publica en el canal Arena como embed epico.
8. Ambos usuarios reciben DM con el resultado y sus stats actualizados.

---

## 6. Integracion Tecnica (Arquitectura RoleAgentBot)

### 6.1 Archivos Nuevos

```
roles/arena/
├── __init__.py
├── arena.py                    # Logica principal (gestion de eventos, brackets)
├── arena_db.py                 # Wrapper NoSQL para stats/armas/batallas/eventos
├── arena_discord.py            # Handlers de comandos (legacy/Canvas actions)
├── arena_messages.py           # Mensajes localizados
├── weapons_catalogs.py         # Catalogos de armas y matrices por personalidad
└── fighter_personalities.py    # Catalogos de personalidades de combate por bot

discord_bot/canvas/canvas_arena.py     # Builders de Canvas para Arena
personalities/*/descriptions/arena.json # Descripciones localizadas del rol
```

### 6.2 Integracion con Memoria

En `agent_memory_nosql.py`, durante `schedule_relationship_update` o `generate_daily_memory_summary`, si el rol Arena esta activo para el servidor, se inyecta la instruccion de generar/actualizar `fighter_personality` junto al parrafo de sintesis.

El prompt adicional se carga desde `roles/arena/fighter_personalities.py` segun la personalidad del bot activa.

### 6.3 Estructura de Datos NoSQL

```json
{
  "arena": {
    "fighters": {
      "user_id": {
        "wins": 10,
        "participated": 25,
        "fighter_personality": "Berserker",
        "unlocked_weapons": ["espada_larga", "hacha_guerra"],
        "active_weapon": "hacha_guerra",
        "xp": 12.5,
        "duel_wins": 3,
        "duel_participated": 5,
        "coliseo_wins": 5,
        "coliseo_participated": 15,
        "tournament_wins": 2,
        "tournament_participated": 5,
        "updated_at": "2026-05-20T10:00:00"
      }
    },
    "events": {
      "active_coliseo": {
        "event_id": "coliseo_20260520_1",
        "status": "registering|ready|in_progress|completed|cancelled",
        "scheduled_for": "2026-05-21T18:00:00",
        "participants": {
          "user_id": {
            "username": "...",
            "weapon": "arma_id",
            "fighter_personality": "..."
          }
        },
        "retries": 0,
        "created_at": "..."
      },
      "active_tournament": { ... }
    },
    "history": [
      {
        "type": "duelo|coliseo|torneo",
        "event_id": "...",
        "participants": [
          {"user_id": "...", "username": "...", "weapon": "...", "fighter_personality": "...", "xp_at_fight": 12}
        ],
        "winner": "user_id",
        "narrative": "...",
        "timestamp": "2026-05-20T10:00:00"
      }
    ]
  }
}
```

### 6.4 Configuracion en agent_config.json

```json
{
  "roles": {
    "arena": {
      "enabled": true,
      "script": "roles/arena/arena.py",
      "config": {
        "channel_name": "arena",
        "min_coliseo_participants": 4,
        "min_tournament_participants": 8,
        "registration_timeout_hours": 24,
        "max_retries": 3,
        "xp_per_coliseo": 1.0,
        "xp_per_tournament": 1.0,
        "xp_per_duel": 0.2,
        "weapon_unlocks": {
          "weapon_1": 0,
          "weapon_2": 2.0,
          "weapon_3": 5.0,
          "weapon_4": 9.0,
          "weapon_5": 14.0,
          "weapon_6": 20.0
        }
      }
    }
  }
}
```

### 6.5 Canvas Integration

Crear `discord_bot/canvas/canvas_arena.py` con:

```python
def build_canvas_role_arena(agent_config: dict, admin_visible: bool, guild=None) -> str:
    """Build Arena role overview."""
    # Estado actual del servidor: eventos activos, ranking top 5, armas disponibles

def build_canvas_role_arena_detail(detail_name: str, admin_visible: bool, guild=None, ...) -> str | None:
    """Build Arena detail views."""
    if detail_name == "overview": return build_canvas_role_arena(...)
    if detail_name == "duelo": return duel_interface
    if detail_name == "coliseo": return coliseo_interface
    if detail_name == "torneo": return tournament_interface
    if detail_name == "ranking": return leaderboard
    if detail_name == "armas": return weapon_catalog
    if detail_name == "config": return admin_config (solo admin_visible)
```

---

## 7. Reglas Detalladas para el LLM (Resumen Ejecutivo)

Para que el modulo Arena funcione consistentemente, el LLM debe respetar estas reglas inyectadas en su system prompt cuando este activo el rol Arena:

1. **Armas**: Cada usuario tiene un arma equipada del catalogo de la personalidad del bot. Las armas tienen relaciones de ventaja entre si que deben influir en la narrativa.
2. **Personalidad de combate**: Cada usuario tiene una personalidad de combate asignada. Debe influir en sus tacticas narrativas.
3. **Experiencia**: El numero de batallas participadas otorga "ventaja narrativa" (mas experimentado = mas propositivo, no invencible).
4. **No stats numericos**: No hay HP, no hay daño numerico, no hay tiradas de dados. Todo es narrativa coherente.
5. **Formato de salida**: El LLM debe usar los delimitadores `[BATALLA]` / `[FIN_BATALLA]` y especificar Ganador + Justificacion.
6. **Tono**: La narrativa debe ser epica, acorde a la personalidad del bot, sin gore explicito.
7. **Coliseo**: En modo coliseo, eliminar progresivamente participantes hasta uno.

---

## 8. Catalogos Completos

### 8.1 Catalogo de Armas y Matrices

#### HANS (Oficial disciplinario aleman - Armas militares germanicas)

**Armas**:
1. **Espada Larga** (Degen) - Versatil, equilibrada. Arma inicial.
2. **Hacha de Guerra** (Streitaxt) - Brutal, cortante. Desbloqueo: 2 XP.
3. **Lanza de Caballeria** (Lanze) - Alcance, precision. Desbloqueo: 5 XP.
4. **Maza de Acero** (Streitkolben) - Contundente, rompe escudos. Desbloqueo: 9 XP.
5. **Espadon a Dos Manos** (Zweihander) - Masivo, destruye formaciones. Desbloqueo: 14 XP.
6. **Alabarda Ceremonial** (Hellebarde) - Versatil de guardia, elegante. Desbloqueo: 20 XP.

**Matriz de Ventajas (Hans)**:

| | Espada | Hacha | Lanza | Maza | Espadon | Alabarda |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Espada** | = | - | + | -- | ++ | - |
| **Hacha** | + | = | -- | ++ | - | + |
| **Lanza** | - | ++ | = | + | -- | + |
| **Maza** | ++ | -- | - | = | + | - |
| **Espadon** | -- | + | ++ | - | = | -- |
| **Alabarda** | + | - | - | + | ++ | = |

*Descripciones narrativas*: ++ = ventaja clara | + = ventaja leve | = = parejo | - = desventaja leve | -- = desventaja clara

---

#### PUTRE (Guerrero orko - Armas brutales y salvajes)

**Armas**:
1. **Machete Oxidado** - Desgastado pero letal. Arma inicial.
2. **Hacha Rompe-Craneos** - Peso brutal, aplasta. Desbloqueo: 2 XP.
3. **Garrote con Clavos** (Maza de pinchos) - Sangrado garantizado. Desbloqueo: 5 XP.
4. **Cadena con Piedra** (Flail improvisado) - Impredecible, dificil de bloquear. Desbloqueo: 9 XP.
5. **Mandoble de Dientes** (Espada de sierra) - Desgarra armaduras. Desbloqueo: 14 XP.
6. **Guantelete de Puas** - Cuerpo a cuerpo extremo. Desbloqueo: 20 XP.

**Matriz de Ventajas (Putre)**:

| | Machete | Hacha | Garrote | Cadena | Mandoble | Guantelete |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Machete** | = | - | + | -- | ++ | - |
| **Hacha** | + | = | -- | ++ | - | + |
| **Garrote** | - | ++ | = | + | -- | + |
| **Cadena** | ++ | -- | - | = | + | -- |
| **Mandoble** | -- | + | ++ | - | = | + |
| **Guantelete** | + | - | - | ++ | - | = |

---

#### YUKI (Geisha/artesana - Armas asiaticas elegantes)

**Armas**:
1. **Katana** - Filo perfecto, precision. Arma inicial.
2. **Naginata** (Alabarda japonesa) - Alcance y fluidez. Desbloqueo: 2 XP.
3. **Kusarigama** (Hoz con cadena) - Versatil, atrapar. Desbloqueo: 5 XP.
4. **Tanto** (Daga ceremonial) - Rapida, letal en cercania. Desbloqueo: 9 XP.
5. **Bo Staff** (Baston largo) - Defensa y control de distancia. Desbloqueo: 14 XP.
6. **Kanabo** (Maza con pinchos japonesa) - Poder oni, aplasta. Desbloqueo: 20 XP.

**Matriz de Ventajas (Yuki)**:

| | Katana | Naginata | Kusarigama | Tanto | Bo Staff | Kanabo |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Katana** | = | - | + | -- | ++ | - |
| **Naginata** | + | = | -- | ++ | - | + |
| **Kusarigama** | - | ++ | = | + | -- | + |
| **Tanto** | ++ | -- | - | = | + | -- |
| **Bo Staff** | -- | + | ++ | - | = | + |
| **Kanabo** | + | - | - | ++ | - | = |

---

#### KRONK (Orko herrero - Armas forjadas, pesadas, industriales)

**Armas**:
1. **Martillo de Herrero** - Confiado, versatil. Arma inicial.
2. **Cincel de Guerra** (Punta afilada, pesada) - Perfora armaduras. Desbloqueo: 2 XP.
3. **Tenazas Gigantes** (Pinzas de forja) - Atrapa y rompe. Desbloqueo: 5 XP.
4. **Yunque Portatil** (Maza colosal) - Destruye todo. Desbloqueo: 9 XP.
5. **Sierra de Forja** (Hoja dentada grande) - Corta metales y huesos. Desbloqueo: 14 XP.
6. **Cadena de Forja** (Cadena incandescente) - Arde al contacto. Desbloqueo: 20 XP.

**Matriz de Ventajas (Kronk)**:

| | Martillo | Cincel | Tenazas | Yunque | Sierra | Cadena |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Martillo** | = | - | + | -- | ++ | - |
| **Cincel** | + | = | -- | ++ | - | + |
| **Tenazas** | - | ++ | = | + | -- | + |
| **Yunque** | ++ | -- | - | = | + | -- |
| **Sierra** | -- | + | ++ | - | = | + |
| **Cadena** | + | - | - | ++ | - | = |

---

#### PANIGORR (Ayudante del horno - Armas improvisadas, asquerosas, de panaderia)

**Armas**:
1. **Pala de Leña** - Simple, contundente. Arma inicial.
2. **Rodillo con Clavos** - Aplasta y perfora. Desbloqueo: 2 XP.
3. **Horno Movil** (Brasero portatil) - Quema al contacto. Desbloqueo: 5 XP.
4. **Cuchillo de Amasar** (Hoja larga y curva) - Corta masas y carne. Desbloqueo: 9 XP.
5. **Soga de Tripa** (Latigo organico) - Atrapa y estrangula. Desbloqueo: 14 XP.
6. **Piedra de Molino** (Maza redonda gigante) - Aplasta con peso ancestral. Desbloqueo: 20 XP.

**Matriz de Ventajas (Panigorr)**:

| | Pala | Rodillo | Horno | Cuchillo | Soga | Piedra |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Pala** | = | - | + | -- | ++ | - |
| **Rodillo** | + | = | -- | ++ | - | + |
| **Horno** | - | ++ | = | + | -- | + |
| **Cuchillo** | ++ | -- | - | = | + | -- |
| **Soga** | -- | + | ++ | - | = | + |
| **Piedra** | + | - | - | ++ | - | = |

---

#### RAB (Androide profeta del desierto - Armas futuristas/misticas)

**Armas**:
1. **Cimitarra de Silicio** (Hoja curva con circuitos) - Corta frecuencias. Arma inicial.
2. **Baston de Datos** (Baston tecnologico con punta energetica) - Alcance y precision. Desbloqueo: 2 XP.
3. **Latigo de Cable** (Cable de cobre con chispas) - Atrapa y electrocuta. Desbloqueo: 5 XP.
4. **Daga de Memoria** (Punzal que "recuerda" heridas) - Letal, repetitivo. Desbloqueo: 9 XP.
5. **Escudo de Arena** (Barrera de nanodunas) - Defensa y contraataque. Desbloqueo: 14 XP.
6. **Guantelete de Sobrecarga** (Mano robotica que libera energia) - Destruccion masiva. Desbloqueo: 20 XP.

**Matriz de Ventajas (Rab)**:

| | Cimitarra | Baston | Latigo | Daga | Escudo | Guantelete |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Cimitarra** | = | - | + | -- | ++ | - |
| **Baston** | + | = | -- | ++ | - | + |
| **Latigo** | - | ++ | = | + | -- | + |
| **Daga** | ++ | -- | - | = | + | -- |
| **Escudo** | -- | + | ++ | - | = | + |
| **Guantelete** | + | - | - | ++ | - | = |

---

### 8.2 Catalogo de Personalidades de Combate

#### HANS (Militarismo germanico)
1. **BERSERKER** - Furia descontrolada, ataca sin pensar. Cuanto mas herido, mas peligroso.
2. **DUELISTA** - Preciso, calculador, busca el golpe perfecto. Evita riesgos innecesarios.
3. **ESTRATEGA** - Manipula el entorno, usa enganos y posicionamiento. Nunca ataca frontalmente.
4. **GLADIADOR** - Espectaculo y dominio. Busca impresionar a la multitud. Resiliente.
5. **VANGUARDIA** - Protege posiciones, cuerpo a cuerpo implacable. Sacrificio controlado.

#### PUTRE (Salvajismo orko)
1. **MAQUINA DE CARNE** - Aplasta todo a su paso. No siente dolor. Avanza sin detenerse.
2. **REBANADOR** - Busca sangre. Ataca por los flancos. Disfruta el caos.
3. **TANQUE** - Resiste golpes que matarian a otros. Espera al rival exhausto.
4. **SALTA-CUCHILLOS** - Agil para un orko. Usa el entorno contra el enemigo.
5. **JEFE DE TRIBU** - Liderazgo brutal. Inspira miedo. Ataca con autoridad.

#### YUKI (Disciplina asiatica)
1. **RONIN** - Samurai sin amo. Codigo propio. Duelos honorables. Precision extrema.
2. **SHINOBI** - Sombra. Invisible hasta el golpe final. Veneno y engano permitidos.
3. **MONJE GUERRERO** - Cuerpo como arma. Control del ki. Meditacion en combate.
4. **ONNA-BUGEISHA** (Mujer guerrera) - Elegancia letal. Fluidez sobre fuerza.
5. **YAKUZA** - Codigo del submundo. Lealtad al clan. Violencia ritual y calculada.

#### KRONK (Fuerza industrial)
1. **TRITURADOR** - Golpea hasta que no queda nada. Fuerza bruta pura.
2. **FORJALOPE** - Usa el fuego y el calor como arma. Quema al contacto.
3. **YUNQUERO** - Inmovil como el metal. Espera y destruye con un solo golpe.
4. **SOLDADOR** - Une y rompe. Atrapa armas enemigas y las desarma.
5. **MINERO** - Conoce los puntos debiles. Golpea donde duele. Eficiente.

#### PANIGORR (Desesperacion panadera)
1. **HOLLINERO** - Usa ceniza y humo para cegar. Ataca desde la oscuridad.
2. **MASA VIVA** - Resiliente como la levadura. Se reconstruye. Agotador.
3. **HORNO ANDANTE** - Quema todo a su alrededor. Autodestructivo pero letal.
4. **RATA DE PANADERIA** - Rapido, escurridizo. Atrapa y muerde.
5. **AMASADOR** - Aplasta lentamente. Estrangula. No deja escapar.

#### RAB (Tecnologia mistica)
1. **GLITCH** - Se mueve de forma impredecible. Realidad distorsionada.
2. **PROTOCOLO OFENSIVO** - Calcula cada movimiento. Eficiencia del 100%.
3. **ESPEJISMO** - Ilusiones y copias. El enemigo nunca sabe cual es el verdadero.
4. **SOBRECARGA** - Acumula energia. Un golpe devastador. Luego, vulnerabilidad.
5. **PEREGRINO** - Adapta estilos de todos los que ha "vivido". Impredecible.

---

## 9. Plan de Implementacion

### Fase 1: Fundamentos (est. 1 sesion)
- [ ] Crear `roles/arena/` con estructura de archivos base
- [ ] Implementar `weapons_catalogs.py` con todos los catalogos y matrices
- [ ] Implementar `fighter_personalities.py` con catalogos de personalidades
- [ ] Implementar `arena_db.py` (wrapper NoSQL)
- [ ] Implementar creacion automatica de canal Arena en `initialize_server_complete`
- [ ] Actualizar `agent_config.json` con configuracion de Arena

### Fase 2: Logica de Batalla (est. 1 sesion)
- [ ] Implementar `arena.py`: gestion de eventos, brackets, flujo de batalla
- [ ] Implementar prompts de batalla (archivos `.txt` o templates en codigo)
- [ ] Implementar integracion con `agent_mind.py` para llamar al LLM con prompts de Arena
- [ ] Implementar parsing de respuesta del LLM (extraer ganador, justificacion)
- [ ] Implementar actualizacion de stats post-batalla

### Fase 3: Memoria y Personalidad de Combate (est. 1 sesion)
- [ ] Integrar prompt de personalidad de combate en `agent_memory_nosql.py`
- [ ] Implementar parsing de `[FIGHTER_PERSONALITY: X]` en sintesis de relacion
- [ ] Almacenar `fighter_personality` en el estado del usuario
- [ ] Asegurar que se actualiza periodicamente (no solo una vez)

### Fase 4: Canvas UI (est. 1 sesion)
- [ ] Crear `discord_bot/canvas/canvas_arena.py`
- [ ] Implementar builders: overview, duelo, coliseo, torneo, ranking, armas, config
- [ ] Implementar botones y selects interactivos
- [ ] Integrar en `discord_bot/canvas/content.py`

### Fase 5: Discord Integration (est. 1 sesion)
- [ ] Implementar flujo de duelo por DM (invitacion, aceptacion, seleccion de arma)
- [ ] Implementar flujo de coliseo/torneo (registro, timer, ejecucion)
- [ ] Implementar publicacion de resultados en canal Arena
- [ ] Implementar leaderboard y ranking
- [ ] Implementar `arena_messages.py` con localizacion

### Fase 6: Testing y Refinamiento (est. 1 sesion)
- [ ] Tests de unidad para logica de batalla
- [ ] Tests para brackets de torneo
- [ ] Tests para matriz de armas
- [ ] Validacion de prompts con LLM
- [ ] Ajuste de balance (XP, ventajas) segun feedback

---

## 10. Notas de Diseno Adicionales

- **Seguridad**: Las batallas narrativas deben tener un filtro de contenido para evitar que el LLM genere contenido excesivamente violento, aunque sea narrativa. Se puede anadir una capa de moderacion post-LLM.
- **Performance**: Las batallas de coliseo con 8+ participantes pueden generar narrativas largas. Considerar split en mensajes si excede 2000 caracteres.
- **Persistencia**: Los eventos activos deben ser resilientes a reinicios. Almacenar estado de evento en NoSQL, no en memoria.
- **Scalability**: Si un servidor tiene muchos usuarios, el ranking puede paginarse.
- **Fallback**: Si el LLM falla o no respeta el formato, reintentar una vez. Si persiste, abortar la batalla y notificar.

---

*Documento aprobado. Listo para implementacion.*
