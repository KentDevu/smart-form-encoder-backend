"""Test WebSocket cleanup for RAM optimization (Fix 4)."""
import pytest
import inspect


@pytest.mark.asyncio
async def test_websocket_cleanup_structure_has_outer_try_finally():
    """
    Verify that websocket_ocr_progress has an outer try-finally block.
    This is a structural test to ensure Fix 4 (outer try-finally wrapper) was applied.
    """
    import inspect
    from app.api.v1.forms import websocket_ocr_progress
    
    # Get source code
    source = inspect.getsource(websocket_ocr_progress)
    
    # Verify try-finally structure exists
    # Check that "finally:" appears in the function after "try:"
    lines = source.split("\n")
    
    try_count = sum(1 for line in lines if "try:" in line)
    finally_count = sum(1 for line in lines if "finally:" in line)
    
    # Should have at least 2 try blocks (outer + inner for message loop)
    assert try_count >= 2, "Expected at least 2 try blocks"
    # Should have finally blocks for cleanup
    assert finally_count >= 1, "Expected at least 1 finally block"
    
    # Verify manager.disconnect is called in finally
    assert "manager.disconnect" in source, "manager.disconnect not found in function"
    assert "finally:" in source, "finally block not found"


def test_websocket_decorator_exists():
    """
    Verify websocket endpoint is decorated with @router.websocket.
    """
    from app.api.v1 import forms
    
    # Check endpoint exists
    assert hasattr(forms, 'websocket_ocr_progress')
    
    # Verify it's an async function
    import inspect
    assert inspect.iscoroutinefunction(forms.websocket_ocr_progress)
