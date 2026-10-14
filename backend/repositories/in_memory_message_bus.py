import asyncio
import logging
from typing import Callable, Awaitable, Any
from backend.models.schemas import TaskTriggerEvent
from backend.repositories.message_bus import MessageBus, MessageContext
from opentelemetry import propagate
from opentelemetry import context as otel_context

logger = logging.getLogger(__name__)

class InMemoryMessageContext(MessageContext):
    def __init__(self, message_id: str, queue: asyncio.Queue, message: TaskTriggerEvent,
                 dead_letters: asyncio.Queue, topic: str, max_deliveries: int,
                 retry_base_seconds: float):
        self.message_id = message_id
        self.queue = queue
        self.message = message
        self.dead_letters = dead_letters
        self.topic = topic
        self.max_deliveries = max_deliveries
        self.retry_base_seconds = retry_base_seconds
        self.settled = False
        
    async def ack(self) -> None:
        if self.settled:
            return
        self.settled = True
        logger.debug(f"Message {self.message_id} ACKed")
        self.queue.task_done()
        
    async def nack(self) -> None:
        if self.settled:
            return
        self.settled = True
        attempt = int(self.message.get("delivery_attempt", 1))
        if attempt >= self.max_deliveries:
            logger.error("Message %s on %s exhausted %s deliveries; moving to dead-letter queue",
                         self.message_id, self.topic, self.max_deliveries)
            await self.dead_letters.put({
                "topic": self.topic,
                "message": self.message.get("message"),
                "delivery_attempt": attempt,
                "message_id": self.message_id,
            })
            self.queue.task_done()
            return

        delay = self.retry_base_seconds * (2 ** (attempt - 1))
        logger.warning("Message %s NACKed on %s (attempt %s/%s); retrying in %.2fs",
                       self.message_id, self.topic, attempt, self.max_deliveries, delay)
        await asyncio.sleep(delay)
        retry = dict(self.message)
        retry["delivery_attempt"] = attempt + 1
        await self.queue.put(retry)
        self.queue.task_done()

class InMemoryMessageBus(MessageBus):
    def __init__(self, max_deliveries: int = 5, retry_base_seconds: float = 0.25):
        self.topics = {}
        self.dead_letters = asyncio.Queue()
        self.max_deliveries = max(1, max_deliveries)
        self.retry_base_seconds = max(0, retry_base_seconds)
        
    def _get_queue(self, topic: str) -> asyncio.Queue:
        if topic not in self.topics:
            self.topics[topic] = asyncio.Queue()
        return self.topics[topic]

    async def publish(self, topic: str, message: Any) -> None:
        queue = self._get_queue(topic)
        
        # Inject OTel context
        carrier = {}
        propagate.inject(carrier)
        
        payload = {
            "message": message,
            "carrier": carrier
        }
        
        await queue.put(payload)
        
        msg_id = getattr(message, "task_id", getattr(message, "schedule_id", str(message)))
        if isinstance(message, dict):
            msg_id = message.get("task_id") or message.get("schedule_id", str(message))
            
        logger.info(f"Published to {topic}: {msg_id}")
        
    async def consume(self, topic: str, handler: Callable[[TaskTriggerEvent, MessageContext], Awaitable[None]]) -> None:
        from backend.config.settings import settings
        queue = self._get_queue(topic)

        async def worker():
            while True:
                payload = await queue.get()
                ctx = InMemoryMessageContext(
                    str(id(payload)), queue, payload, self.dead_letters, topic,
                    max_deliveries=self.max_deliveries,
                    retry_base_seconds=self.retry_base_seconds,
                )
                token = otel_context.attach(propagate.extract(payload["carrier"]))
                try:
                    await handler(payload["message"], ctx)
                except asyncio.CancelledError:
                    if not ctx.settled:
                        await ctx.nack()
                    raise
                except Exception:
                    logger.exception("Error in consumer handler")
                    if not ctx.settled:
                        await ctx.nack()
                finally:
                    otel_context.detach(token)

        async with asyncio.TaskGroup() as group:
            for _ in range(settings.LOCAL_WORKER_CONCURRENCY):
                group.create_task(worker())
