"""In-process publish/subscribe for SSE. One uvicorn process (Dockerfile CMD) — no cross-process bus."""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field

QUEUE_SIZE = 256


@dataclass(eq=False)
class Subscriber:
    key: tuple[str, ...]
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(QUEUE_SIZE))


class Broker:
    def __init__(self) -> None:
        self._subscribers: dict[tuple[str, ...], set[Subscriber]] = defaultdict(set)

    def subscribe(self, *key: str) -> Subscriber:
        """Call inside the event loop that reads the queue."""
        subscriber = Subscriber(key, asyncio.get_running_loop())
        self._subscribers[key].add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self._subscribers[subscriber.key].discard(subscriber)

    def publish(self, key: tuple[str, ...], message: object) -> None:
        """Thread-safe: sync endpoints run in a thread pool, queues belong to the event loop."""
        for subscriber in list(self._subscribers.get(key, ())):
            subscriber.loop.call_soon_threadsafe(self._put, subscriber.queue, message)

    @staticmethod
    def _put(queue: asyncio.Queue, message: object) -> None:
        if queue.full():  # a stuck client loses its oldest message, not the newest
            queue.get_nowait()
        queue.put_nowait(message)


broker = Broker()
