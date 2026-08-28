from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from app.events.models import DomainEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[DomainEvent], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[type[DomainEvent], list[EventHandler]] = {}

    def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    async def publish(self, event: DomainEvent) -> None:
        for handler in self._subscribers.get(type(event), []):
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "event handler failed",
                    extra={"event": type(event).__name__},
                )