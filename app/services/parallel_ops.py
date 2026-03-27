"""
P3 OPTIMIZATION: Parallel operations for OCR pipeline.

Within sync context (Celery tasks), use ThreadPoolExecutor for I/O operations:
- Parallel cache lookups
- Parallel downloads (if batch processing)
Enables async-like parallelization without full async refactor.
"""

import concurrent.futures
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)


def parallel_cache_check(
    form_entry_id: str,
    template_id: str,
    image_bytes: bytes,
    cache_getters: dict[str, callable],
) -> dict[str, Optional[Any]]:
    """
    Check multiple cache sources in parallel.
    
    Args:
        form_entry_id: Form ID for logging
        template_id: Template ID for cache keys
        image_bytes: Image content
        cache_getters: Dict of {cache_name: callable} where callable(template_id, image_bytes)
                       Returns cache result or None
    
    Returns:
        Dict of {cache_name: result} where result is the cached value or None
    """
    
    results = {}
    
    # For now, sequential is fine (typically 2-3 cache checks)
    # In the future, use ThreadPoolExecutor if more caches are added
    for cache_name, getter in cache_getters.items():
        try:
            result = getter(form_entry_id, template_id, image_bytes)
            results[cache_name] = result
            logger.debug(f"[P3-Parallel] Cache check {cache_name}: {'HIT' if result else 'MISS'}")
        except Exception as e:
            logger.warning(f"[P3-Parallel] Cache check {cache_name} failed: {e}")
            results[cache_name] = None
    
    return results


def parallel_downloads(
    r2_keys: list[str],
    download_fn: callable,
    max_workers: int = 3,
) -> dict[str, Optional[bytes]]:
    """
    Download multiple files from R2 in parallel.
    
    Args:
        r2_keys: List of S3/R2 object keys
        download_fn: Function that takes key and returns bytes
        max_workers: Thread pool size
    
    Returns:
        Dict of {key: bytes} or {key: None} if download failed
    """
    
    results = {}
    
    if len(r2_keys) <= 1:
        # No parallelization benefit for single item
        for key in r2_keys:
            try:
                results[key] = download_fn(key)
            except Exception as e:
                logger.error(f"[P3-Parallel] Download failed for {key}: {e}")
                results[key] = None
        return results
    
    # Use thread pool for parallel downloads
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_fn, key): key for key in r2_keys}
        
        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            try:
                result = future.result(timeout=30)
                results[key] = result
                logger.debug(f"[P3-Parallel] Downloaded {key}")
            except Exception as e:
                logger.error(f"[P3-Parallel] Download failed for {key}: {e}")
                results[key] = None
    
    return results


def parallel_caching(
    cache_operations: list[tuple[callable, tuple]],
    max_workers: int = 3,
) -> dict[int, bool]:
    """
    Execute multiple cache write operations in parallel.
    
    Args:
        cache_operations: List of (cache_fn, (args_tuple,)) to execute
        max_workers: Thread pool size
    
    Returns:
        Dict of {index: success} for each operation
    """
    
    results = {}
    
    if len(cache_operations) <= 1:
        # No parallelization benefit for single operation
        for i, (fn, args) in enumerate(cache_operations):
            try:
                result = fn(*args)
                results[i] = bool(result)
            except Exception as e:
                logger.warning(f"[P3-Parallel] Cache operation {i} failed: {e}")
                results[i] = False
        return results
    
    # Use thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fn, *args): i
            for i, (fn, args) in enumerate(cache_operations)
        }
        
        for future in concurrent.futures.as_completed(futures):
            i = futures[future]
            try:
                result = future.result(timeout=10)
                results[i] = bool(result)
                logger.debug(f"[P3-Parallel] Cache operation {i} completed: {result}")
            except Exception as e:
                logger.warning(f"[P3-Parallel] Cache operation {i} failed: {e}")
                results[i] = False
    
    return results


# For future async refactoring: async versions using asyncio
def create_async_wrapper():
    """
    Future enhancement: Create async versions for full asyncio support.
    
    When the OCR pipeline is fully async (FastAPI endpoints → async Celery tasks),
    these functions can be replaced with native asyncio.gather() calls.
    
    Example:
        async def parallel_extractions(forms: list) -> list:
            tasks = [extract_form_async(form) for form in forms]
            return await asyncio.gather(*tasks)
    """
    pass
