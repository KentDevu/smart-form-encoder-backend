"""
P2 OPTIMIZATION: Redis-based caching for OCR extraction results.

Replaces in-memory caching with Redis to enable:
- Multi-worker shared cache (horizontal scaling)
- Persistent cache for retrench scenarios
- Fallback to cached OCR if API call fails (graceful degradation)
"""

import json
import hashlib
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


def _get_redis_client():
    """Get sync Redis client from pool."""
    from app.redis_pool import get_sync_redis_client
    return get_sync_redis_client()


def _hash_image_content(image_bytes: bytes) -> str:
    """Create stable hash of image content for cache key."""
    return hashlib.md5(image_bytes).hexdigest()


def get_ocr_cache_key(form_entry_id: str, template_id: str, image_hash: str) -> str:
    """Generate cache key for OCR extraction results."""
    return f"ocr:extract:{template_id}:{image_hash}"


def get_extraction_cache_key(form_entry_id: str, template_id: str, image_hash: str) -> str:
    """Generate cache key for field extraction results."""
    return f"extract:fields:{template_id}:{image_hash}"


def cache_ocr_result(
    form_entry_id: str,
    template_id: str,
    image_bytes: bytes,
    ocr_result: dict[str, Any],
    ttl_seconds: int = 3600,  # 1 hour
) -> bool:
    """
    Cache OCR extraction result in Redis.
    
    Returns: True if cached successfully, False otherwise
    """
    try:
        image_hash = _hash_image_content(image_bytes)
        key = get_ocr_cache_key(form_entry_id, template_id, image_hash)
        
        # Store as JSON, exclude raw_lines to save space (can be re-extracted from full_text)
        cache_data = {
            "full_text": ocr_result.get("full_text", ""),
            "avg_confidence": ocr_result.get("avg_confidence", 0.0),
            "processing_time": ocr_result.get("processing_time", 0.0),
            "line_count": len(ocr_result.get("raw_lines", [])),
        }
        
        r = _get_redis_client()
        r.setex(key, ttl_seconds, json.dumps(cache_data))
        logger.debug(f"[P2-Cache] Cached OCR result: {key} (ttl={ttl_seconds}s)")
        return True
        
    except Exception as e:
        logger.warning(f"[P2-Cache] Failed to cache OCR result: {e}")
        return False


def get_cached_ocr_result(
    form_entry_id: str,
    template_id: str,
    image_bytes: bytes,
) -> Optional[dict[str, Any]]:
    """
    Retrieve cached OCR result from Redis.
    
    Returns: Cached OCR result dict, or None if not found/expired
    """
    try:
        image_hash = _hash_image_content(image_bytes)
        key = get_ocr_cache_key(form_entry_id, template_id, image_hash)
        
        r = _get_redis_client()
        cached = r.get(key)
        
        if cached:
            result = json.loads(cached)
            logger.info(f"[P2-Cache] HIT: Retrieved cached OCR for {form_entry_id}")
            return result
        else:
            logger.debug(f"[P2-Cache] MISS: No cached OCR for {form_entry_id}")
            return None
            
    except Exception as e:
        logger.warning(f"[P2-Cache] Failed to retrieve cached OCR: {e}")
        return None


def cache_field_extraction(
    form_entry_id: str,
    template_id: str,
    image_bytes: bytes,
    fields_dict: dict[str, dict[str, Any]],
    ttl_seconds: int = 3600,  # 1 hour
) -> bool:
    """
    Cache field extraction results in Redis.
    
    Returns: True if cached successfully, False otherwise
    """
    try:
        image_hash = _hash_image_content(image_bytes)
        key = get_extraction_cache_key(form_entry_id, template_id, image_hash)
        
        r = _get_redis_client()
        r.setex(key, ttl_seconds, json.dumps(fields_dict))
        logger.debug(f"[P2-Cache] Cached field extraction: {key} (ttl={ttl_seconds}s)")
        return True
        
    except Exception as e:
        logger.warning(f"[P2-Cache] Failed to cache field extraction: {e}")
        return False


def get_cached_field_extraction(
    form_entry_id: str,
    template_id: str,
    image_bytes: bytes,
) -> Optional[dict[str, dict[str, Any]]]:
    """
    Retrieve cached field extraction from Redis.
    
    Returns: Cached fields dict, or None if not found/expired
    """
    try:
        image_hash = _hash_image_content(image_bytes)
        key = get_extraction_cache_key(form_entry_id, template_id, image_hash)
        
        r = _get_redis_client()
        cached = r.get(key)
        
        if cached:
            result = json.loads(cached)
            logger.info(f"[P2-Cache] HIT: Retrieved cached field extraction for {form_entry_id}")
            return result
        else:
            logger.debug(f"[P2-Cache] MISS: No cached field extraction for {form_entry_id}")
            return None
            
    except Exception as e:
        logger.warning(f"[P2-Cache] Failed to retrieve cached field extraction: {e}")
        return None


def invalidate_cache_for_template(template_id: str) -> bool:
    """
    Invalidate all cache entries for a template (when template changes).
    
    Returns: True if successfully searched/deleted, False on error
    """
    try:
        r = _get_redis_client()
        
        # Find all keys matching pattern
        pattern = f"*:{template_id}:*"
        cursor = 0
        deleted = 0
        
        while True:
            cursor, keys = r.scan(cursor, match=pattern, count=100)
            for key in keys:
                r.delete(key)
                deleted += 1
            
            if cursor == 0:
                break
        
        logger.info(f"[P2-Cache] Invalidated {deleted} cache entries for template {template_id}")
        return True
        
    except Exception as e:
        logger.warning(f"[P2-Cache] Failed to invalidate template cache: {e}")
        return False
