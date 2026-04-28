"""Public API for News Watcher role.

This module provides a stable public API for Canvas and other external callers.
Internal implementations may change, but this API should remain stable.
"""

from roles.news_watcher.watcher_commands import WatcherCommands
from roles.news_watcher.news_watcher import process_subscriptions

__all__ = [
    "WatcherCommands",
    "process_subscriptions",
]
