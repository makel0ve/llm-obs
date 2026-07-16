import asyncio
from collections import defaultdict

import structlog
from redis.asyncio import Redis

log = structlog.get_logger()


class PubSubManager:
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[str]]] = defaultdict(set)
        self._task: asyncio.Task[None] | None = None

    async def start(self, redis: Redis) -> None:
        if self._task and not self._task.done():
            return

        self._task = asyncio.create_task(self._listen(redis))

    async def stop(self) -> None:
        if not self._task or self._task.done():
            return

        self._task.cancel()
        try:
            await self._task

        except asyncio.CancelledError:
            pass

    async def _listen(self, redis: Redis) -> None:
        while True:
            try:
                pubsub = redis.pubsub()
                await pubsub.psubscribe("project:*:new_span")
                async for msg in pubsub.listen():
                    if msg["type"] != "pmessage":
                        continue

                    project_id = msg["channel"].decode().split(":")[1]
                    data = msg["data"].decode()
                    for q in list(self._queues.get(project_id, [])):
                        try:
                            q.put_nowait(data)

                        except asyncio.QueueFull:
                            pass

            except Exception as e:
                log.error("pubsub_listener_failed", error=str(e))
                await asyncio.sleep(3)

    def subscribe(self, project_id: str) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=50)
        self._queues[project_id].add(q)

        return q

    def unsubscribe(self, project_id: str, q: asyncio.Queue[str]) -> None:
        self._queues[project_id].discard(q)


pubsub_manager = PubSubManager()
