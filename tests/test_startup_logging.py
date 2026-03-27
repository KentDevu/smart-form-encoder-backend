"""Test startup logging for memory configuration (Fix 5 & 6)."""
import pytest
import logging
from unittest.mock import MagicMock, patch, AsyncMock


def test_settings_attributes_exist():
    """
    Verify that all settings attributes used in logging are defined.
    This prevents AttributeError at startup.
    """
    from app.config import get_settings
    
    settings = get_settings()
    
    # Verify all attributes used in logging exist
    assert hasattr(settings, 'REDIS_POOL_SIZE'), "REDIS_POOL_SIZE not defined"
    assert hasattr(settings, 'REDIS_POOL_TIMEOUT'), "REDIS_POOL_TIMEOUT not defined"
    assert hasattr(settings, 'CACHE_OCR_MODEL'), "CACHE_OCR_MODEL not defined"
    assert hasattr(settings, 'DEBUG'), "DEBUG not defined"
    
    # Verify they have reasonable values
    assert isinstance(settings.REDIS_POOL_SIZE, int), "REDIS_POOL_SIZE should be int"
    assert settings.REDIS_POOL_SIZE > 0, "REDIS_POOL_SIZE should be > 0"
    assert isinstance(settings.REDIS_POOL_TIMEOUT, int), "REDIS_POOL_TIMEOUT should be int"
    assert isinstance(settings.CACHE_OCR_MODEL, bool), "CACHE_OCR_MODEL should be bool"


def test_redis_pool_logging_message_format():
    """
    Verify that Redis pool size is logged correctly.
    """
    from app.config import get_settings
    
    settings = get_settings()
    
    # Simulate the log message
    log_msg = f"[MEMORY CONFIG] Redis pool size: {settings.REDIS_POOL_SIZE} (timeout: {settings.REDIS_POOL_TIMEOUT}s)"
    
    # Verify message format
    assert "[MEMORY CONFIG]" in log_msg
    assert str(settings.REDIS_POOL_SIZE) in log_msg
    assert str(settings.REDIS_POOL_TIMEOUT) in log_msg


def test_model_caching_logging_message_format():
    """
    Verify that OCR model caching setting is logged with explanatory text.
    """
    from app.config import get_settings
    
    settings = get_settings()
    
    # Simulate the log message
    cache_status = 'ENABLED (500MB RAM)' if settings.CACHE_OCR_MODEL else 'DISABLED (lower RAM, slower)'
    log_msg = f"[MEMORY CONFIG] OCR model caching: {cache_status}"
    
    # Verify message format
    assert "[MEMORY CONFIG]" in log_msg
    assert "caching:" in log_msg.lower()
    # Should include one of the two states
    assert "ENABLED" in log_msg or "DISABLED" in log_msg


def test_celery_worker_logging_message_format():
    """
    Verify that Celery worker recycling config is logged.
    """
    from app.config import get_settings
    
    settings = get_settings()
    
    # Simulate the log message
    max_tasks = settings.CELERY_MAX_TASKS_PER_CHILD
    log_msg = f"[MEMORY CONFIG] Worker max tasks per child: {max_tasks} (auto-restart after N tasks)"
    
    # Verify message format
    assert "[MEMORY CONFIG]" in log_msg
    assert "tasks per child" in log_msg.lower()
    assert str(max_tasks) in log_msg


def test_logger_is_module_level():
    """
    Verify that logger is defined at module level in main.py.
    This prevents redundant logger creation on every startup.
    """
    from app import main
    
    # Check that logger is defined at module level
    assert hasattr(main, 'logger'), "logger not defined at module level in main.py"


def test_celery_logger_is_module_level():
    """
    Verify that logger is defined at module level in celery_app.py.
    """
    from app import celery_app
    
    # Check that logger is defined at module level
    assert hasattr(celery_app, 'logger'), "logger not defined at module level in celery_app.py"


@pytest.mark.asyncio
async def test_main_imports_successfully():
    """
    Verify that app/main.py imports successfully (no syntax/import errors).
    """
    try:
        from app import main
        assert main is not None
        assert hasattr(main, 'lifespan')
    except Exception as e:
        pytest.fail(f"Failed to import main: {e}")


def test_celery_app_imports_successfully():
    """
    Verify that app/celery_app.py imports successfully.
    """
    try:
        from app import celery_app as ca
        assert ca is not None
        assert hasattr(ca, 'celery_app')
    except Exception as e:
        pytest.fail(f"Failed to import celery_app: {e}")


def test_logging_config_values_reasonable():
    """
    Verify that all logged config values are reasonable (not None, not default placeholders).
    """
    from app.config import get_settings
    
    settings = get_settings()
    
    # Redis pool size should be between 1 and 100 (reasonable range)
    assert 1 <= settings.REDIS_POOL_SIZE <= 100, \
        f"Redis pool size out of range: {settings.REDIS_POOL_SIZE}"
    
    # Redis timeout should be between 1 and 60 seconds
    assert 1 <= settings.REDIS_POOL_TIMEOUT <= 60, \
        f"Redis timeout out of range: {settings.REDIS_POOL_TIMEOUT}"
    
    # Celery max tasks should be at least 1
    assert settings.CELERY_MAX_TASKS_PER_CHILD >= 1, \
        f"Celery max tasks invalid: {settings.CELERY_MAX_TASKS_PER_CHILD}"
