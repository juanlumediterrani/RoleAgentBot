"""
Logica principal del modulo Arena.

Gestiona:
- Prompts de batalla (1v1, coliseo, torneo)
- Ejecucion de batallas via LLM
- Parsing de resultados
- Generacion de brackets de torneo
- Actualizacion de stats post-batalla
"""

import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from agent_logging import get_logger

logger = get_logger("arena")


def get_arena_system_prompt():
    """Get system prompt for the Arena role."""
    from agent_engine import PERSONALITY
    try:
        role_prompts = PERSONALITY.get("roles", {})
        return role_prompts.get("arena", {}).get(
            "active_duty",
            "ACTIVE MISSION - ARENA: You are the Arena Master of the server. Your mission is to narrate epic combat encounters (duels, coliseums and tournaments) with theatrical flair. You judge battles based on creativity, drama and the chosen weapons/personalities of fighters. You are impartial but theatrical, turning every clash into a memorable story.",
        )
    except Exception:
        return ""


# ── Prompt Builders ─────────────────────────────────────────────────

def build_battle_prompt(
    server_id: str,
    participant_a: dict,
    participant_b: dict,
    bot_personality_name: str,
    catalog_loader,  # arena_catalogs module
) -> str:
    """Construye el prompt de batalla 1v1."""
    from . import arena_catalogs

    user_a = participant_a
    user_b = participant_b

    weapon_a = arena_catalogs.get_weapon_by_id(server_id, user_a.get("weapon")) or {}
    weapon_b = arena_catalogs.get_weapon_by_id(server_id, user_b.get("weapon")) or {}

    adv_desc = ""
    if weapon_a and weapon_b:
        adv_desc = arena_catalogs.get_advantage_description_for_prompt(
            server_id, user_a.get("weapon"), user_b.get("weapon")
        )

    pa_name = user_a.get("username", "Usuario A")
    pb_name = user_b.get("username", "Usuario B")
    pa_fp = user_a.get("fighter_personality", "Desconocida")
    pb_fp = user_b.get("fighter_personality", "Desconocida")
    pa_xp = user_a.get("xp", 0)
    pb_xp = user_b.get("xp", 0)
    wa_name = weapon_a.get("name", user_a.get("weapon", "Arma A"))
    wb_name = weapon_b.get("name", user_b.get("weapon", "Arma B"))

    prompt = f"""Eres el maestro de ceremonias de una arena. Debes narrar una batalla siguiendo ESTRICTAMENTE estas reglas:

1. AMBIENTACION: Describe la arena en 1-2 frases. El tono debe ser epico y acorde a tu personalidad ({bot_personality_name}).

2. PARTICIPANTES:
   - Luchador A: @{pa_name} | Personalidad de combate: {pa_fp} | Experiencia: {pa_xp} batallas | Arma: {wa_name}
   - Luchador B: @{pb_name} | Personalidad de combate: {pb_fp} | Experiencia: {pb_xp} batallas | Arma: {wb_name}

3. MATRIZ DE VENTAJAS DE ARMAS (solo referencia narrativa):
   {adv_desc}

4. DESARROLLO DE LA BATALLA:
   - Divide la batalla en 3-5 "asaltos" o "intercambios".
   - En cada intercambio, describe la accion narrativa con tu estilo de personalidad.
   - La experiencia en combate influye en la destreza narrativa (mas experimentado = mas propositivo).
   - Las ventajas de arma deben reflejarse en la narrativa (ej: lanza mantiene distancia vs espada).
   - La personalidad de combate debe influir en las tacticas: un {pa_fp} actua segun su naturaleza, y un {pb_fp} tambien.

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
   - El tono debe ser acorde a tu personalidad del bot ({bot_personality_name}).

7. FORMATO DE SALIDA OBLIGATORIO:
   ```
   [BATALLA]
   Ambientacion: (1-2 frases)

   Asalto 1: (descripcion)
   Asalto 2: (descripcion)
   Asalto 3: (descripcion)
   [Asalto 4-5 opcional si la batalla lo requiere]

   Ganador: @{pa_name} O @{pb_name}
   Justificacion: (1 frase explicando por que gano)
   [FIN_BATALLA]
   ```
"""
    return prompt


def build_coliseo_prompt(
    server_id: str,
    participants: List[dict],
    bot_personality_name: str,
) -> str:
    """Construye el prompt de coliseo (todos contra todos)."""
    from . import arena_catalogs

    lines = []
    for p in participants:
        weapon = arena_catalogs.get_weapon_by_id(server_id, p.get("weapon")) or {}
        lines.append(
            f"   - @{p.get('username', 'Anon')} | Personalidad: {p.get('fighter_personality', 'Desconocida')} | "
            f"Experiencia: {p.get('xp', 0)} batallas | Arma: {weapon.get('name', p.get('weapon', '???'))}"
        )
    participant_block = "\n".join(lines)
    n = len(participants)

    prompt = f"""Eres el maestro de ceremonias de una arena. Debes narrar un COLISEO donde multiples luchadores entran y solo uno sale victorioso.

REGLAS DEL COLISEO:

1. AMBIENTACION: Describe la arena para multiples combatientes (2-4 frases).

2. PARTICIPANTES ({n} luchadores):
{participant_block}

3. DESARROLLO - FASES DE ELIMINACION:
   - El coliseo se divide en "fases". En cada fase, 1-2 participantes son eliminados narrativamente.
   - Numero de fases: para {n} participantes, usa aproximadamente {n - 1} fases (algunas fases pueden eliminar 2).
   - En cada fase, describe brevemente los enfrentamientos paralelos o secuenciales.
   - Considera alianzas temporales, traiciones, y caos general.
   - La experiencia y las ventajas de arma siguen siendo relevantes.
   - Las personalidades de combate deben influir: un Berserker ataca a todos, un Estratega espera a que otros se debiliten.

4. RESOLUCION FINAL:
   - Un solo ganador. Justifica con coherencia.
   - Puede haber remontadas, errores, momentos heroicos.
   - Maximo 1200 tokens (mas que 1v1 por la complejidad).

5. RESTRICCIONES: No gore explicito. Sangre/p permitidos en tono epico. Tono acorde a {bot_personality_name}.

6. FORMATO:
   ```
   [COLISEO]
   Ambientacion: ...

   Fase 1: ... (eliminados: @usuario1)
   Fase 2: ... (eliminados: @usuario2, @usuario3)
   ...
   Fase Final: ... (enfrentamiento entre @usuarioX y @usuarioY)

   Ganador: @nombre_del_ganador
   Justificacion: ...
   [FIN_COLISEO]
   ```
"""
    return prompt


# ── Parsing de Resultados ───────────────────────────────────────────

def parse_battle_result(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parsea la respuesta del LLM buscando el bloque [BATALLA]/[FIN_BATALLA]
    o [COLISEO]/[FIN_COLISEO].

    Returns:
        (ganador_mention, justificacion, narrativa_completa)
    """
    text = text.strip()

    # Buscar bloques delimitados
    markers = [
        ("[BATALLA]", "[FIN_BATALLA]"),
        ("[COLISEO]", "[FIN_COLISEO]"),
    ]

    narrative = text
    for start, end in markers:
        if start in text and end in text:
            idx_start = text.find(start)
            idx_end = text.find(end) + len(end)
            narrative = text[idx_start:idx_end]
            break

    # Extraer ganador
    winner = None
    for line in text.split("\n"):
        line_stripped = line.strip()
        if line_stripped.lower().startswith("ganador:"):
            winner_part = line_stripped.split(":", 1)[1].strip()
            # Extraer mencion @usuario si existe
            if "@" in winner_part:
                # Tomar la primera palabra que empiece con @
                parts = winner_part.split()
                for p in parts:
                    if p.startswith("@"):
                        winner = p[1:].strip()
                        break
            if not winner:
                winner = winner_part
            break

    # Extraer justificacion
    justification = None
    for line in text.split("\n"):
        line_stripped = line.strip()
        if line_stripped.lower().startswith("justificacion:"):
            justification = line_stripped.split(":", 1)[1].strip()
            break

    return winner, justification, narrative


# ── Brackets de Torneo ──────────────────────────────────────────────

def generate_tournament_bracket(participants: List[dict]) -> List[List[dict]]:
    """
    Genera los brackets de un torneo de eliminacion simple.

    Args:
        participants: Lista de dicts con al menos 'user_id' y 'username'

    Returns:
        Lista de rondas, donde cada ronda es una lista de combates (pares).
        Un combate es un dict con 'player_a' y 'player_b'.
    """
    n = len(participants)
    if n < 2:
        return []

    # Barajar aleatoriamente
    shuffled = list(participants)
    random.shuffle(shuffled)

    # Calcular potencia de 2 superior
    import math
    next_pow2 = 2 ** math.ceil(math.log2(n))
    byes = next_pow2 - n

    # Añadir byes como participantes None
    bracket_pool = shuffled + [None] * byes

    rounds = []
    current = bracket_pool

    while len(current) > 1:
        round_matches = []
        for i in range(0, len(current), 2):
            a = current[i]
            b = current[i + 1] if i + 1 < len(current) else None
            round_matches.append({"player_a": a, "player_b": b})
        rounds.append(round_matches)

        # Preparar siguiente ronda (ganadores avanzan; byes avanzan automaticamente)
        next_round = []
        for match in round_matches:
            if match["player_a"] is None:
                next_round.append(match["player_b"])
            elif match["player_b"] is None:
                next_round.append(match["player_a"])
            else:
                # Placeholder: se resolvera despues
                next_round.append({"pending": True, "match": match})
        current = next_round

    return rounds


def resolve_bracket_round(
    round_matches: List[dict],
    winners: List[Optional[dict]],
) -> List[dict]:
    """
    Resuelve una ronda de bracket con los ganadores conocidos.

    Args:
        round_matches: La ronda actual (lista de combates)
        winners: Lista de ganadores (uno por combate, en el mismo orden)

    Returns:
        Lista de participantes que avanzan a la siguiente ronda.
    """
    next_round = []
    for match, winner in zip(round_matches, winners):
        if winner is not None:
            next_round.append(winner)
        elif match["player_a"] is None:
            next_round.append(match["player_b"])
        elif match["player_b"] is None:
            next_round.append(match["player_a"])
        else:
            # No deberia pasar siempre que haya un winner
            next_round.append(match["player_a"])
    return next_round


# ── Ejecucion de Batalla via LLM ────────────────────────────────────

async def execute_battle_1v1(
    server_id: str,
    participant_a: dict,
    participant_b: dict,
    bot_personality_name: str,
) -> dict:
    """
    Ejecuta una batalla 1v1 via LLM.

    Returns:
        dict con 'winner_id', 'loser_id', 'winner_name', 'loser_name',
        'justification', 'narrative', 'success', 'error'
    """
    try:
        from agent_engine import _get_personality, _build_system_prompt
        from agent_mind import call_llm_async
    except ImportError as e:
        logger.error(f"Error importando modulos de LLM: {e}")
        return {"success": False, "error": str(e)}

    try:
        personality = _get_personality(server_id)
        system_instruction = _build_system_prompt(personality, server_id)
    except Exception as e:
        logger.error(f"Error construyendo system prompt: {e}")
        return {"success": False, "error": str(e)}

    prompt = build_battle_prompt(server_id, participant_a, participant_b, bot_personality_name, None)

    try:
        llm_response = await call_llm_async(
            system_instruction=system_instruction,
            prompt=prompt,
            background=False,
            call_type="arena_battle",
            temperature=0.85,
            max_tokens=1024,
        )
    except Exception as e:
        logger.error(f"Error llamando al LLM: {e}")
        return {"success": False, "error": str(e)}

    winner_name, justification, narrative = parse_battle_result(llm_response)

    # Resolver ganador por nombre
    a_name = participant_a.get("username", "")
    b_name = participant_b.get("username", "")
    a_id = participant_a.get("user_id", "")
    b_id = participant_b.get("user_id", "")

    winner_id = None
    loser_id = None
    winner_name_resolved = None
    loser_name_resolved = None

    if winner_name:
        # Comparar de forma flexible
        wn_lower = winner_name.lower()
        if wn_lower in a_name.lower() or a_name.lower() in wn_lower:
            winner_id = a_id
            loser_id = b_id
            winner_name_resolved = a_name
            loser_name_resolved = b_name
        elif wn_lower in b_name.lower() or b_name.lower() in wn_lower:
            winner_id = b_id
            loser_id = a_id
            winner_name_resolved = b_name
            loser_name_resolved = a_name
        else:
            # Fallback: si no coincide claramente, elegir al mas experimentado
            if participant_a.get("xp", 0) >= participant_b.get("xp", 0):
                winner_id = a_id
                loser_id = b_id
                winner_name_resolved = a_name
                loser_name_resolved = b_name
            else:
                winner_id = b_id
                loser_id = a_id
                winner_name_resolved = b_name
                loser_name_resolved = a_name
    else:
        # Sin ganador identificado: fallback a mas experimentado
        if participant_a.get("xp", 0) >= participant_b.get("xp", 0):
            winner_id = a_id
            loser_id = b_id
            winner_name_resolved = a_name
            loser_name_resolved = b_name
        else:
            winner_id = b_id
            loser_id = a_id
            winner_name_resolved = b_name
            loser_name_resolved = a_name

    return {
        "success": True,
        "winner_id": winner_id,
        "loser_id": loser_id,
        "winner_name": winner_name_resolved,
        "loser_name": loser_name_resolved,
        "justification": justification or "Victoria por decision narrativa del maestro de ceremonias.",
        "narrative": narrative or llm_response,
    }


async def execute_coliseo(
    server_id: str,
    participants: List[dict],
    bot_personality_name: str,
) -> dict:
    """
    Ejecuta un coliseo via LLM.

    Returns:
        dict con 'winner_id', 'winner_name', 'justification', 'narrative',
        'eliminated', 'success', 'error'
    """
    try:
        from agent_engine import _get_personality, _build_system_prompt
        from agent_mind import call_llm_async
    except ImportError as e:
        logger.error(f"Error importando modulos de LLM: {e}")
        return {"success": False, "error": str(e)}

    try:
        personality = _get_personality(server_id)
        system_instruction = _build_system_prompt(personality, server_id)
    except Exception as e:
        logger.error(f"Error construyendo system prompt: {e}")
        return {"success": False, "error": str(e)}

    prompt = build_coliseo_prompt(server_id, participants, bot_personality_name)

    try:
        llm_response = await call_llm_async(
            system_instruction=system_instruction,
            prompt=prompt,
            background=False,
            call_type="arena_coliseo",
            temperature=0.85,
            max_tokens=1536,
        )
    except Exception as e:
        logger.error(f"Error llamando al LLM para coliseo: {e}")
        return {"success": False, "error": str(e)}

    winner_name, justification, narrative = parse_battle_result(llm_response)

    # Resolver ganador
    winner_id = None
    winner_name_resolved = None
    eliminated = []

    if winner_name:
        wn_lower = winner_name.lower()
        for p in participants:
            pname = p.get("username", "").lower()
            if wn_lower in pname or pname in wn_lower:
                winner_id = p.get("user_id")
                winner_name_resolved = p.get("username")
            else:
                eliminated.append(p.get("user_id"))
    else:
        # Fallback: ganador aleatorio (no ideal pero evita bloqueo)
        winner = random.choice(participants)
        winner_id = winner.get("user_id")
        winner_name_resolved = winner.get("username")
        eliminated = [p.get("user_id") for p in participants if p.get("user_id") != winner_id]

    return {
        "success": True,
        "winner_id": winner_id,
        "winner_name": winner_name_resolved,
        "justification": justification or "Victoria en el coliseo.",
        "narrative": narrative or llm_response,
        "eliminated": eliminated,
    }


# ── Utilidades de Eventos ────────────────────────────────────────────

def generate_event_id(event_type: str) -> str:
    """Genera un ID unico para un evento."""
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    rand = random.randint(1000, 9999)
    return f"{event_type}_{ts}_{rand}"


def can_create_event(server_id: str, db) -> Tuple[bool, Optional[str]]:
    """
    Verifica si se puede crear un nuevo evento en el servidor.

    Returns:
        (puede_crear, razon_si_no)
    """
    active = db.events.get_active_event()
    if active and active.get("status") in ("registering", "ready", "in_progress"):
        return False, "Ya hay un evento activo en este servidor."
    return True, None


def calculate_xp(battle_type: str, server_config: dict) -> float:
    """Calcula el XP otorgado segun el tipo de batalla y la configuracion."""
    cfg = server_config.get("roles", {}).get("arena", {}).get("config", {})
    mapping = {
        "duelo": cfg.get("xp_per_duel", 0.2),
        "coliseo": cfg.get("xp_per_coliseo", 1.0),
        "torneo": cfg.get("xp_per_tournament", 1.0),
    }
    return mapping.get(battle_type.lower(), 0.0)


def get_arena_config(server_id: str) -> dict:
    """Carga la configuracion de Arena para un servidor desde agent_config.json."""
    import json
    import os
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "agent_config.json")
    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("roles", {}).get("arena", {}).get("config", {})
    except Exception as e:
        logger.error(f"Error cargando config de Arena: {e}")
        return {}
