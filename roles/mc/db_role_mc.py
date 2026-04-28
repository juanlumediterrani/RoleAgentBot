from pathlib import Path

try:
    from agent_logging import get_logger
    logger = get_logger('db_role_mc')
except Exception:
    import logging
    logger = logging.getLogger('db_role_mc')


class DatabaseRoleMC:
    """Specialized database for the MC (Master of Ceremonies) — NoSQL-backed.
    Manages music queues, playlists and preferences via role_configs_nosql.
    """

    def __init__(self, server_id: str = "default", db_path: Path = None):
        self.server_id = server_id
        self._nosql_cache = None

    @property
    def _nosql(self):
        """Lazy accessor for the NoSQL role-configs facade (per server)."""
        if self._nosql_cache is None:
            from roles.role_configs_nosql import get_role_configs_nosql
            self._nosql_cache = get_role_configs_nosql(self.server_id)
        return self._nosql_cache

    def create_playlist(self, name: str, user_id: str, user_name: str,
                        server_id: str, server_name: str) -> bool:
        """Create a new playlist (NoSQL-backed)."""
        return self._nosql.mc_create_playlist(name, user_id, user_name, server_id, server_name)

    def get_user_playlists(self, user_id: str) -> list:
        """Get all playlists for a user (NoSQL-backed)."""
        return self._nosql.mc_get_user_playlists(user_id)

    def add_song_to_queue(self, server_id: str, channel_id: str, user_id: str,
                          title: str, url: str, duration: str = None, artist: str = None,
                          position: int = None) -> bool:
        """Add a song to the playback queue (NoSQL-backed)."""
        return self._nosql.mc_add_song_to_queue(
            server_id, channel_id, user_id, title, url, duration, artist, position
        )

    def get_queue(self, server_id: str, channel_id: str) -> list:
        """Get current playback queue (NoSQL-backed)."""
        return self._nosql.mc_get_queue(server_id, channel_id)

    def get_queue_all_channels(self, server_id: str) -> list:
        """Get all queue entries for a server across all channels (NoSQL-backed)."""
        return self._nosql.mc_get_queue_all_channels(server_id)

    def remove_song_from_queue(self, server_id: str, channel_id: str, position: int) -> bool:
        """Remove a specific song from queue (NoSQL-backed)."""
        return self._nosql.mc_remove_song_from_queue(server_id, channel_id, position)

    def clear_queue(self, server_id: str, channel_id: str) -> bool:
        """Clear entire playback queue (NoSQL-backed)."""
        return self._nosql.mc_clear_queue(server_id, channel_id)

    def register_history(self, server_id: str, channel_id: str, user_id: str,
                         title: str, url: str, duration: str = None, artist: str = None) -> bool:
        """Register a song in playback history (NoSQL-backed)."""
        return self._nosql.mc_register_history(server_id, channel_id, user_id, title, url, duration, artist)

    def get_history(self, server_id: str, channel_id: str, limit: int = 10) -> list:
        """Get recent playback history (NoSQL-backed)."""
        return self._nosql.mc_get_history(server_id, channel_id, limit)

    def get_statistics(self, server_id: str = None) -> dict:
        """Get basic MC statistics (NoSQL-backed)."""
        return self._nosql.mc_get_statistics(server_id)

    def clean_old_queue(self, days: int = 7) -> int:
        """Clean old queue entries (NoSQL-backed)."""
        return self._nosql.mc_clean_old_queue(days)

    def clean_old_history(self, days: int = 30) -> int:
        """Clean old history entries (NoSQL-backed, auto-managed by ring buffer)."""
        return self._nosql.mc_clean_old_history(days)


def get_mc_db_instance(server_id: str = "default") -> DatabaseRoleMC:
    """Get an instance of the MC database."""
    return DatabaseRoleMC(server_id)
