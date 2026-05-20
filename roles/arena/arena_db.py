"""
Base de datos del modulo Arena usando JsonStore y JsonlRingBuffer.

Archivos:
- databases/<server_id>/roles/arena_stats.json      -> Stats por usuario (fighters)
- databases/<server_id>/roles/arena_history.jsonl   -> Historial de batallas
- databases/<server_id>/roles/arena_events.json     -> Eventos activos (coliseos, torneos)
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from persistence.json_store import JsonStore
from persistence.jsonl_store import JsonlRingBuffer
from agent_logging import get_logger

logger = get_logger("arena_db")

# ── Constantes ──────────────────────────────────────────────────────

DEFAULT_STATS = {
    "wins": 0,
    "participated": 0,
    "fighter_personality": None,
    "unlocked_weapons": [],
    "active_weapon": None,
    "xp": 0.0,
    "duel_wins": 0,
    "duel_participated": 0,
    "coliseo_wins": 0,
    "coliseo_participated": 0,
    "tournament_wins": 0,
    "tournament_participated": 0,
    "updated_at": None,
}

DEFAULT_EVENT = {
    "event_id": None,
    "type": None,  # "duelo" | "coliseo" | "torneo"
    "status": None,  # "registering" | "ready" | "in_progress" | "completed" | "cancelled"
    "scheduled_for": None,
    "participants": {},  # {user_id: {username, weapon, fighter_personality}}
    "retries": 0,
    "winner": None,
    "narrative": None,
    "created_at": None,
    "completed_at": None,
}


# ── Helpers de ruta ─────────────────────────────────────────────────

def _get_db_dir(server_id: str) -> Path:
    base = Path(__file__).parent.parent.parent / "databases" / server_id / "roles"
    base.mkdir(parents=True, exist_ok=True)
    return base


# ── Stats de Peleadores ─────────────────────────────────────────────

class ArenaStatsStore:
    """Almacena y recupera stats de peleadores por servidor."""

    def __init__(self, server_id: str):
        self.server_id = server_id
        self._store = JsonStore(
            _get_db_dir(server_id) / "arena_stats.json",
            default_factory=dict,
            keep_backup=False,
        )

    # -- Lectura --

    def get_fighter(self, user_id: str) -> Dict:
        """Devuelve las stats de un peleador. Inicializa si no existe."""
        state = self._store.load()
        uid = str(user_id)
        if uid not in state:
            fighter = dict(DEFAULT_STATS)
            fighter["updated_at"] = _now()
            state[uid] = fighter
            self._store.save()
        return dict(state.get(uid, DEFAULT_STATS))

    def get_all_fighters(self) -> Dict[str, Dict]:
        """Devuelve todos los peleadores del servidor."""
        return dict(self._store.load())

    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Devuelve el ranking por victorias (descendente)."""
        fighters = self.get_all_fighters()
        ranked = [
            {"user_id": uid, **stats}
            for uid, stats in fighters.items()
        ]
        ranked.sort(key=lambda x: (x.get("wins", 0), x.get("xp", 0.0)), reverse=True)
        return ranked[:limit]

    # -- Escritura --

    def update_fighter(self, user_id: str, **fields) -> bool:
        """Actualiza campos de un peleador. Crea si no existe."""
        try:
            uid = str(user_id)

            def updater(state: dict):
                if uid not in state:
                    state[uid] = dict(DEFAULT_STATS)
                state[uid].update(fields)
                state[uid]["updated_at"] = _now()
                return state

            self._store.update(updater)
            return True
        except Exception as e:
            logger.error(f"Error actualizando fighter {user_id}: {e}")
            return False

    def set_fighter_personality(self, user_id: str, personality: str) -> bool:
        """Asigna o actualiza la personalidad de combate de un usuario."""
        return self.update_fighter(user_id, fighter_personality=personality)

    def add_xp(self, user_id: str, amount: float) -> bool:
        """Suma XP a un peleador."""
        try:
            uid = str(user_id)

            def updater(state: dict):
                if uid not in state:
                    state[uid] = dict(DEFAULT_STATS)
                state[uid]["xp"] = state[uid].get("xp", 0.0) + amount
                state[uid]["updated_at"] = _now()
                return state

            self._store.update(updater)
            return True
        except Exception as e:
            logger.error(f"Error sumando XP a {user_id}: {e}")
            return False

    def record_battle_result(self, user_id: str, won: bool, battle_type: str, xp_gained: float = 0.0) -> bool:
        """Registra el resultado de una batalla para un usuario."""
        try:
            uid = str(user_id)
            type_key = battle_type.lower()  # duelo, coliseo, torneo

            def updater(state: dict):
                if uid not in state:
                    state[uid] = dict(DEFAULT_STATS)
                f = state[uid]

                f["participated"] = f.get("participated", 0) + 1
                f[f"{type_key}_participated"] = f.get(f"{type_key}_participated", 0) + 1
                f["xp"] = f.get("xp", 0.0) + xp_gained

                if won:
                    f["wins"] = f.get("wins", 0) + 1
                    f[f"{type_key}_wins"] = f.get(f"{type_key}_wins", 0) + 1

                f["updated_at"] = _now()
                return state

            self._store.update(updater)
            return True
        except Exception as e:
            logger.error(f"Error registrando resultado para {user_id}: {e}")
            return False

    def set_active_weapon(self, user_id: str, weapon_id: str) -> bool:
        """Cambia el arma activa de un peleador."""
        return self.update_fighter(user_id, active_weapon=weapon_id)

    def add_unlocked_weapon(self, user_id: str, weapon_id: str) -> bool:
        """Agrega un arma a la lista de desbloqueadas si no estaba."""
        try:
            uid = str(user_id)

            def updater(state: dict):
                if uid not in state:
                    state[uid] = dict(DEFAULT_STATS)
                unlocked = set(state[uid].get("unlocked_weapons", []))
                unlocked.add(weapon_id)
                state[uid]["unlocked_weapons"] = sorted(unlocked)
                state[uid]["updated_at"] = _now()
                return state

            self._store.update(updater)
            return True
        except Exception as e:
            logger.error(f"Error desbloqueando arma {weapon_id} para {user_id}: {e}")
            return False


# ── Historial de Batallas ───────────────────────────────────────────

class ArenaHistoryStore:
    """Almacena el historial de batallas como JSONL (max 500 entradas)."""

    def __init__(self, server_id: str):
        self.server_id = server_id
        self._buffer = JsonlRingBuffer(
            _get_db_dir(server_id) / "arena_history.jsonl",
            max_lines=500,
        )

    def save_battle(self, battle_record: dict) -> bool:
        """Guarda un registro de batalla."""
        try:
            record = dict(battle_record)
            record["timestamp"] = _now()
            self._buffer.append(record)
            return True
        except Exception as e:
            logger.error(f"Error guardando historial de batalla: {e}")
            return False

    def get_history(self, limit: int = 20) -> List[dict]:
        """Devuelve las N batallas mas recientes."""
        try:
            return list(self._buffer.tail(limit))
        except Exception as e:
            logger.error(f"Error leyendo historial: {e}")
            return []


# ── Eventos Activos ───────────────────────────────────────────────────

class ArenaEventsStore:
    """Almacena eventos activos (coliseos, torneos en registro)."""

    def __init__(self, server_id: str):
        self.server_id = server_id
        self._store = JsonStore(
            _get_db_dir(server_id) / "arena_events.json",
            default_factory=lambda: {"active": None, "history": []},
            keep_backup=False,
        )

    def get_active_event(self) -> Optional[dict]:
        """Devuelve el evento activo o None."""
        state = self._store.load()
        return state.get("active")

    def set_active_event(self, event: dict) -> bool:
        """Establece o actualiza el evento activo."""
        try:
            def updater(state: dict):
                state["active"] = dict(event)
                return state
            self._store.update(updater)
            return True
        except Exception as e:
            logger.error(f"Error guardando evento activo: {e}")
            return False

    def clear_active_event(self, move_to_history: bool = True) -> bool:
        """Limpia el evento activo. Opcionalmente lo mueve al historial."""
        try:
            def updater(state: dict):
                active = state.get("active")
                if active and move_to_history:
                    history = state.get("history", [])
                    history.append(active)
                    state["history"] = history[-50:]  # Mantener ultimos 50
                state["active"] = None
                return state
            self._store.update(updater)
            return True
        except Exception as e:
            logger.error(f"Error limpiando evento activo: {e}")
            return False

    def get_event_history(self, limit: int = 20) -> List[dict]:
        """Devuelve el historial de eventos completados."""
        state = self._store.load()
        history = state.get("history", [])
        return history[-limit:]

    def register_participant(self, user_id: str, username: str, weapon_id: str, fighter_personality: str = "") -> bool:
        """Registra un participante en el evento activo."""
        try:
            def updater(state: dict):
                active = state.get("active")
                if not active:
                    return state
                participants = active.get("participants", {})
                participants[str(user_id)] = {
                    "username": username,
                    "weapon": weapon_id,
                    "fighter_personality": fighter_personality,
                    "registered_at": _now(),
                }
                active["participants"] = participants
                state["active"] = active
                return state
            self._store.update(updater)
            return True
        except Exception as e:
            logger.error(f"Error registrando participante {user_id}: {e}")
            return False

    def unregister_participant(self, user_id: str) -> bool:
        """Elimina un participante del evento activo."""
        try:
            def updater(state: dict):
                active = state.get("active")
                if not active:
                    return state
                participants = active.get("participants", {})
                participants.pop(str(user_id), None)
                active["participants"] = participants
                state["active"] = active
                return state
            self._store.update(updater)
            return True
        except Exception as e:
            logger.error(f"Error desregistrando participante {user_id}: {e}")
            return False

    def is_registered(self, user_id: str) -> bool:
        """Verifica si un usuario esta registrado en el evento activo."""
        active = self.get_active_event()
        if not active:
            return False
        return str(user_id) in active.get("participants", {})

    def create_event(self, event_type: str, scheduled_for: str, min_participants: int = 4) -> bool:
        """Crea un nuevo evento activo (coliseo o torneo)."""
        try:
            event = dict(DEFAULT_EVENT)
            event["event_id"] = f"{event_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            event["type"] = event_type
            event["status"] = "registering"
            event["scheduled_for"] = scheduled_for
            event["min_participants"] = min_participants
            event["participants"] = {}
            event["retries"] = 0
            event["created_at"] = _now()
            self.set_active_event(event)
            return True
        except Exception as e:
            logger.error(f"Error creando evento {event_type}: {e}")
            return False


# ── Facade unificada ────────────────────────────────────────────────

class ArenaDatabase:
    """Facade que expone stats, historial y eventos de Arena."""

    def __init__(self, server_id: str):
        self.server_id = server_id
        self.stats = ArenaStatsStore(server_id)
        self.history = ArenaHistoryStore(server_id)
        self.events = ArenaEventsStore(server_id)


def _now() -> str:
    return datetime.utcnow().isoformat()
