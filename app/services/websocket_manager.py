"""WebSocket manager using Redis pub/sub for memory-efficient progress updates."""

import json
import logging
import asyncio
from typing import Dict, Set, Any
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections using Redis pub/sub pattern.
    This is much more memory-efficient than polling because:
    - No database polling loops
    - One Redis subscription handles all progress updates
    - Connections only listen for relevant events
    """

    def __init__(self):
        # Active WebSocket connections: {form_id: set[websockets]}
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Lock for thread-safe connection management
        self._lock = asyncio.Lock()

        # Redis subscriber task (started on first connection)
        self._redis_task = None
        self._running = False

    async def connect(self, websocket: WebSocket, form_id: str) -> None:
        """Connect a WebSocket to listen for updates on a specific form."""
        try:
            await websocket.accept()
        except Exception as e:
            logger.warning(f"Failed to accept websocket for {form_id}: {e}")
            raise

        async with self._lock:
            if form_id not in self.active_connections:
                self.active_connections[form_id] = set()
            self.active_connections[form_id].add(websocket)

        logger.info(f"WebSocket connected for form {form_id} "
                    f"(total connections: {len(self.active_connections.get(form_id, []))})")

        # Start Redis subscriber if not already running
        if not self._running:
            self._running = True
            self._redis_task = asyncio.create_task(self._redis_subscriber())

    async def disconnect(self, websocket: WebSocket, form_id: str) -> None:
        """Disconnect a WebSocket from a form."""
        async with self._lock:
            if form_id in self.active_connections:
                self.active_connections[form_id].discard(websocket)
                # Clean up empty form connections
                if not self.active_connections[form_id]:
                    del self.active_connections[form_id]

        logger.info(f"WebSocket disconnected for form {form_id} "
                    f"(remaining connections: {len(self.active_connections)})")

        # Stop Redis subscriber if no more connections
        if not self.active_connections and self._redis_task:
            self._running = False
            self._redis_task.cancel()
            try:
                await self._redis_task
            except asyncio.CancelledError:
                pass

    async def broadcast_to_form(self, form_id: str, message: dict[str, Any]) -> None:
        """Broadcast a message to all WebSocket listeners for a form."""
        if form_id not in self.active_connections:
            return

        # Create a copy to avoid modifying while iterating
        to_remove = []
        for ws in list(self.active_connections[form_id]):
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to websocket: {e}")
                to_remove.append(ws)

        # Cleanup failed connections
        if to_remove:
            async with self._lock:
                for ws in to_remove:
                    self.active_connections[form_id].discard(ws)

    async def _redis_subscriber(self) -> None:
        """Subscribe to Redis pub/sub channel for progress updates."""
        import redis.asyncio as aioredis
        from app.config import get_settings

        settings = get_settings()
        redis_url = settings.REDIS_URL

        try:
            # Parse Redis URL
            if redis_url.startswith("redis://"):
                redis_client = await aioredis.from_url(redis_url, decode_responses=True)
                pubsub = redis_client.pubsub()

                # Subscribe to all form progress updates
                await pubsub.subscribe("form:progress:*")

                logger.info("Redis pub/sub subscriber started")

                while self._running:
                    try:
                        message = await pubsub.get_message(timeout=1.0)
                        if message and message["type"] == "message":
                            # Parse the channel to get form_id
                            # Format: "form:progress:{form_id}"
                            channel = message["channel"]
                            form_id = channel.split(":")[-1] if ":" in channel else channel

                            # Parse the message
                            try:
                                data = json.loads(message["data"])
                                await self.broadcast_to_form(form_id, data)
                            except json.JSONDecodeError:
                                logger.warning(f"Invalid JSON in Redis message: {message['data']}")

                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"Redis subscriber error: {e}")
                        # Brief pause before continuing
                        await asyncio.sleep(1.0)

                await pubsub.close()
                await redis_client.close()
                logger.info("Redis pub/sub subscriber stopped")

        except Exception as e:
            logger.error(f"Failed to start Redis subscriber: {e}")
            self._running = False

    async def publish_progress(self, form_id: str, status: str, confidence: float | None = None,
                               message: str | None = None) -> None:
        """
        Publish progress update to Redis. This is called by Celery tasks.
        Only publishes if there are active connections for this form.
        """
        if form_id not in self.active_connections:
            return  # No listeners, don't bother publishing

        try:
            import redis.asyncio as aioredis
            from app.config import get_settings

            settings = get_settings()
            redis_client = await aioredis.from_url(settings.REDIS_URL)

            data = {
                "status": status,
                "confidence_score": float(confidence) if confidence else None,
                "message": message or f"OCR status: {status}"
            }

            await redis_client.publish(f"form:progress:{form_id}", json.dumps(data))
            await redis_client.close()

        except Exception as e:
            logger.error(f"Failed to publish progress to Redis: {e}")

    def cleanup(self) -> None:
        """Clean up all connections and subscribers."""
        self._running = False
        self.active_connections.clear()


# Global singleton instance
manager = WebSocketManager()


async def publish_form_progress(form_id: str, status: str, confidence: float | None = None,
                                 message: str | None = None) -> None:
    """
    Convenience function to publish form progress updates from anywhere.
    This is called by Celery tasks to notify connected clients.
    """
    await manager.publish_progress(form_id, status, confidence, message)
