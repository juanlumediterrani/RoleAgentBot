"""
Bounded asyncio chat message queue with backpressure.

Decouples Discord's `on_message` event from the heavy `_process_chat_message`
pipeline (LLM calls, DB writes, fallbacks). A small pool of worker tasks
drains the queue, while the queue's bounded size enforces backpressure: when
full, new messages are dropped (with metrics) instead of accumulating in an
unbounded coroutine backlog and exhausting memory under floods.

The queue is intentionally minimal: no priority, no persistence. Discord
itself already redelivers nothing; dropping is the correct behaviour under
flood. Keep this layer simple.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Optional

from agent_logging import get_logger
from agent_metrics import incr as _metrics_incr, set_gauge as _metrics_set_gauge

logger = get_logger('message_queue')


class ChatMessageQueue:
    """Bounded async queue with worker pool for chat message processing."""

    def __init__(self, maxsize: int = 100, num_workers: int = 8):
        if maxsize <= 0:
            raise ValueError("maxsize must be > 0")
        if num_workers <= 0:
            raise ValueError("num_workers must be > 0")
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._num_workers = num_workers
        self._workers: list[asyncio.Task] = []
        self._processor: Optional[Callable[[object], Awaitable[None]]] = None
        # Counters (approximate; not lock-protected, single event loop)
        self._enqueued = 0
        self._dropped = 0
        self._processed = 0
        self._failed = 0
        self._last_drop_log_ts: float = 0.0

    async def start(self, processor: Callable[[object], Awaitable[None]]) -> None:
        """Start the worker pool. ``processor`` is awaited per dequeued message."""
        if self._workers:
            logger.warning("ChatMessageQueue already started; ignoring duplicate start()")
            return
        self._processor = processor
        self._workers = [
            asyncio.create_task(self._worker(idx), name=f"chat-worker-{idx}")
            for idx in range(self._num_workers)
        ]
        logger.info(
            f"📥 ChatMessageQueue started: maxsize={self._queue.maxsize}, "
            f"workers={self._num_workers}"
        )

    async def stop(self) -> None:
        """Cancel all workers and wait for them to exit. Pending items are discarded."""
        if not self._workers:
            return
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        logger.info("📥 ChatMessageQueue stopped")

    def enqueue(self, message: object) -> bool:
        """Try to enqueue a message. Returns False if the queue is full (dropped)."""
        try:
            self._queue.put_nowait(message)
            self._enqueued += 1
            _metrics_incr("chat_queue.enqueued")
            _metrics_set_gauge("chat_queue.size", self._queue.qsize())
            return True
        except asyncio.QueueFull:
            self._dropped += 1
            _metrics_incr("chat_queue.dropped")
            now = time.time()
            # Throttle drop logs to one per second
            if now - self._last_drop_log_ts >= 1.0:
                self._last_drop_log_ts = now
                logger.warning(
                    f"⚠️ ChatMessageQueue FULL (size={self._queue.maxsize}); "
                    f"dropping message. Total dropped: {self._dropped}"
                )
            return False

    async def _worker(self, idx: int) -> None:
        assert self._processor is not None
        logger.debug(f"chat-worker-{idx} started")
        while True:
            try:
                message = await self._queue.get()
            except asyncio.CancelledError:
                logger.debug(f"chat-worker-{idx} cancelled")
                return
            try:
                await self._processor(message)
                self._processed += 1
                _metrics_incr("chat_queue.processed")
            except asyncio.CancelledError:
                # Worker shutting down mid-process. Re-raise.
                raise
            except Exception as e:
                self._failed += 1
                _metrics_incr("chat_queue.failed")
                logger.exception(f"chat-worker-{idx} failed processing message: {e}")
            finally:
                self._queue.task_done()
                _metrics_set_gauge("chat_queue.size", self._queue.qsize())

    def stats(self) -> dict:
        """Return current queue counters and live size."""
        return {
            "size": self._queue.qsize(),
            "maxsize": self._queue.maxsize,
            "workers": len(self._workers),
            "enqueued": self._enqueued,
            "dropped": self._dropped,
            "processed": self._processed,
            "failed": self._failed,
        }


# Module-level singleton, started by the bot at on_ready and stopped on shutdown.
_chat_queue: Optional[ChatMessageQueue] = None


def get_chat_queue() -> ChatMessageQueue:
    """Lazy singleton accessor for the bot's chat queue."""
    global _chat_queue
    if _chat_queue is None:
        _chat_queue = ChatMessageQueue(maxsize=100, num_workers=8)
    return _chat_queue
