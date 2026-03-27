"""
P1 OPTIMIZATION: Error classification for intelligent retry logic.

Classifies OCR processing errors into categories:
- TRANSIENT: Network/API timeouts → Safe to retry immediately
- PERMANENT: Bad input/template errors → Don't retry
- PARTIAL: Some fields extracted successfully → Save and retry only missing fields
"""

import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """Error classification for intelligent retry handling."""
    
    TRANSIENT = "transient"  # Network, timeout, rate limit → safe to retry
    PERMANENT = "permanent"  # Bad input, missing template, bad config → don't retry
    PARTIAL = "partial"      # Some fields extracted, others failed → save progress
    UNKNOWN = "unknown"      # Unclear error → treat as transient


class ClassifiedError:
    """Structured error with category, reason, and recovery suggestion."""
    
    def __init__(
        self,
        category: ErrorCategory,
        reason: str,
        original_error: Optional[Exception] = None,
        retry_safe: bool = False,
        stage: str = "unknown",  # Which stage failed: download, ocr, groq, save
    ):
        self.category = category
        self.reason = reason
        self.original_error = original_error
        self.retry_safe = retry_safe
        self.stage = stage
    
    def __repr__(self) -> str:
        return f"ClassifiedError(category={self.category}, stage={self.stage}, reason={self.reason})"


def classify_error(error: Exception, stage: str = "unknown") -> ClassifiedError:
    """
    Classify an error to determine retry strategy.
    
    Args:
        error: The exception to classify
        stage: Which stage failed (download, ocr, groq, save, etc)
    
    Returns:
        ClassifiedError with category and retry guidance
    """
    
    error_type = type(error).__name__
    error_msg = str(error).lower()
    
    # TRANSIENT ERRORS (Safe to retry)
    if error_type == "TimeoutError" or "timeout" in error_msg:
        return ClassifiedError(
            category=ErrorCategory.TRANSIENT,
            reason=f"Request timeout during {stage}",
            original_error=error,
            retry_safe=True,
            stage=stage,
        )
    
    if error_type in ("ConnectionError", "ConnectionResetError", "BrokenPipeError"):
        return ClassifiedError(
            category=ErrorCategory.TRANSIENT,
            reason=f"Connection error during {stage}",
            original_error=error,
            retry_safe=True,
            stage=stage,
        )
    
    if "rate_limit" in error_msg or "429" in error_msg or "ratelimit" in error_msg:
        return ClassifiedError(
            category=ErrorCategory.TRANSIENT,
            reason=f"API rate limited during {stage}",
            original_error=error,
            retry_safe=True,
            stage=stage,
        )
    
    if "temporarily unavailable" in error_msg or "service unavailable" in error_msg:
        return ClassifiedError(
            category=ErrorCategory.TRANSIENT,
            reason=f"Service temporarily unavailable during {stage}",
            original_error=error,
            retry_safe=True,
            stage=stage,
        )
    
    # PERMANENT ERRORS (Don't retry)
    if error_type == "FileNotFoundError" or "not found" in error_msg:
        return ClassifiedError(
            category=ErrorCategory.PERMANENT,
            reason=f"Required resource not found during {stage} (image/template missing)",
            original_error=error,
            retry_safe=False,
            stage=stage,
        )
    
    if error_type == "ValueError" or error_type == "KeyError":
        return ClassifiedError(
            category=ErrorCategory.PERMANENT,
            reason=f"Invalid input/config during {stage} (bad field schema or image format)",
            original_error=error,
            retry_safe=False,
            stage=stage,
        )
    
    if "authentication" in error_msg or "unauthorized" in error_msg or "forbidden" in error_msg:
        return ClassifiedError(
            category=ErrorCategory.PERMANENT,
            reason=f"Authentication failure during {stage} (bad API key or perms)",
            original_error=error,
            retry_safe=False,
            stage=stage,
        )
    
    if "invalid_request" in error_msg or "bad request" in error_msg:
        return ClassifiedError(
            category=ErrorCategory.PERMANENT,
            reason=f"Invalid request during {stage} (malformed API call)",
            original_error=error,
            retry_safe=False,
            stage=stage,
        )
    
    # PARTIAL ERRORS (Retry only missing fields)
    if "json" in error_msg and "decode" in error_msg:
        return ClassifiedError(
            category=ErrorCategory.PARTIAL,
            reason=f"Failed to parse API response during {stage} (some fields may have been extracted)",
            original_error=error,
            retry_safe=False,  # Don't full retry, but can retry failed fields
            stage=stage,
        )
    
    # UNKNOWN (Default to transient to be safe)
    return ClassifiedError(
        category=ErrorCategory.UNKNOWN,
        reason=f"Unclassified error during {stage}: {error_type}",
        original_error=error,
        retry_safe=True,  # Default to transient (safer assumption)
        stage=stage,
    )


def should_retry_stage(classified_error: ClassifiedError) -> bool:
    """
    Determine if a stage should be retried given classified error.
    
    Rules:
    - TRANSIENT → Retry
    - PERMANENT → Don't retry (fail fast)
    - PARTIAL → Retry only specific fields
    - UNKNOWN → Retry (conservative)
    """
    return classified_error.category in (
        ErrorCategory.TRANSIENT,
        ErrorCategory.UNKNOWN,
    )


def get_retry_delay(attempt: int, classified_error: ClassifiedError) -> int:
    """
    Calculate exponential backoff delay with category consideration.
    
    Args:
        attempt: Retry attempt number (0, 1, 2, ...)
        classified_error: Classified error info
    
    Returns:
        Delay in seconds before retry
    """
    
    if classified_error.category == ErrorCategory.PERMANENT:
        return 0  # Don't retry
    
    if classified_error.category == ErrorCategory.PARTIAL:
        return 2  # Short delay for partial retry
    
    # TRANSIENT or UNKNOWN: Exponential backoff
    # attempt 0 → 10s, attempt 1 → 20s, attempt 2 → 40s
    base_delay = 10
    return base_delay * (2 ** attempt)


def log_error_classification(
    form_entry_id: str,
    classified_error: ClassifiedError,
    attempt: int = 0,
) -> None:
    """Log error classification for debugging."""
    retry_delay = get_retry_delay(attempt, classified_error)
    log_level = logging.ERROR if classified_error.category == ErrorCategory.PERMANENT else logging.WARNING
    
    logger.log(
        log_level,
        f"[P1-ERROR] Form {form_entry_id}: {classified_error.reason} | "
        f"Category={classified_error.category} | "
        f"Retry={'YES' if retry_delay > 0 else 'NO'} | "
        f"Delay={retry_delay}s | "
        f"Original={classified_error.original_error}"
    )
