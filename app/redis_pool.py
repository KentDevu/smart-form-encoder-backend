"""Redis connection pool management for async and sync operations."""

import logging
from typing import Optional

import redis
import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool as AsyncConnectionPool
from redis.connection import ConnectionPool as SyncConnectionPool

logger = logging.getLogger(__name__)

# Global pool instances
_async_pool: Optional[AsyncConnectionPool] = None
_sync_pool: Optional[SyncConnectionPool] = None


def init_async_redis_pool(redis_url: str, pool_size: int = 10, timeout: int = 5) -> AsyncConnectionPool:
    """
    Initialize async Redis connection pool.
    
    Args:
        redis_url: Redis connection URL (e.g., "redis://localhost:6379/0")
        pool_size: Maximum number of connections in pool
        timeout: Connection timeout in seconds
    
    Returns:
        AsyncConnectionPool instance
    """
    global _async_pool
    
    try:
        # Parse URL to extract components
        redis_url_lower = redis_url.lower()
        if redis_url_lower.startswith("redis://"):
            redis_url_parsed = redis_url[8:]  # Remove "redis://"
            if "@" in redis_url_parsed:
                # Has password
                auth, rest = redis_url_parsed.split("@")
                host, port_db = rest.split(":", 1)
                port_db_parts = port_db.split("/")
                port = int(port_db_parts[0])
                db = int(port_db_parts[1]) if len(port_db_parts) > 1 else 0
            else:
                host, port_db = redis_url_parsed.split(":", 1)
                port_db_parts = port_db.split("/")
                port = int(port_db_parts[0])
                db = int(port_db_parts[1]) if len(port_db_parts) > 1 else 0
        else:
            host = "localhost"
            port = 6379
            db = 0
        
        # Create the pool directly
        _async_pool = AsyncConnectionPool(
            host=host,
            port=port,
            db=db,
            max_connections=pool_size,
            socket_connect_timeout=timeout,
            socket_keepalive=True,
            decode_responses=True,
        )
        logger.info(f"Async Redis pool initialized: {pool_size} connections, {host}:{port}/{db}")
        return _async_pool
    except Exception as e:
        logger.error(f"Failed to initialize async Redis pool: {e}")
        raise


def init_sync_redis_pool(redis_url: str, pool_size: int = 10, timeout: int = 5) -> SyncConnectionPool:
    """
    Initialize sync Redis connection pool.
    
    Args:
        redis_url: Redis connection URL (e.g., "redis://localhost:6379/0")
        pool_size: Maximum number of connections in pool
        timeout: Connection timeout in seconds
    
    Returns:
        SyncConnectionPool instance
    """
    global _sync_pool
    
    try:
        # Parse URL to extract components
        if redis_url.startswith("redis://"):
            redis_url_parsed = redis_url.replace("redis://", "")
            host, rest = redis_url_parsed.split(":", 1)
            port_db = rest.split("/")
            port = int(port_db[0])
            db = int(port_db[1]) if len(port_db) > 1 else 0
        else:
            host = "localhost"
            port = 6379
            db = 0
        
        _sync_pool = SyncConnectionPool(
            host=host,
            port=port,
            db=db,
            max_connections=pool_size,
            socket_connect_timeout=timeout,
            socket_keepalive=True,
            decode_responses=False,
        )
        logger.info(f"Sync Redis pool initialized: {pool_size} connections, {host}:{port}/{db}")
        return _sync_pool
    except Exception as e:
        logger.error(f"Failed to initialize sync Redis pool: {e}")
        raise


async def get_async_redis_client() -> aioredis.Redis:
    """Get async Redis client from pool."""
    global _async_pool
    if _async_pool is None:
        raise RuntimeError("Async Redis pool not initialized. Call init_async_redis_pool() first.")
    return aioredis.Redis(connection_pool=_async_pool)


def get_sync_redis_client() -> redis.Redis:
    """Get sync Redis client from pool."""
    global _sync_pool
    if _sync_pool is None:
        raise RuntimeError("Sync Redis pool not initialized. Call init_sync_redis_pool() first.")
    return redis.Redis(connection_pool=_sync_pool)


async def close_async_redis_pool() -> None:
    """Close async Redis pool."""
    global _async_pool
    if _async_pool:
        try:
            await _async_pool.disconnect()
            _async_pool = None
            logger.info("Async Redis pool closed")
        except Exception as e:
            logger.error(f"Error closing async Redis pool: {e}")


def close_sync_redis_pool() -> None:
    """Close sync Redis pool."""
    global _sync_pool
    if _sync_pool:
        try:
            _sync_pool.disconnect()
            _sync_pool = None
            logger.info("Sync Redis pool closed")
        except Exception as e:
            logger.error(f"Error closing sync Redis pool: {e}")


async def health_check() -> bool:
    """Check Redis pool health."""
    try:
        client = await get_async_redis_client()
        await client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False
