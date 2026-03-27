"""Field-level validators for OCR pipeline (Phase C - Validation & Hardening).

These validators normalize and validate extracted field values from OCR/AI:
- Date fields: Accept multiple formats, validate ranges (1950-2030)
- Phone fields: Philippine formats with internationalization
- Checkbox fields: Yes/No/True/False normalization  
- Amount fields: Currency formatting and standardization
- Required fields: Confidence adjustments based on presence

Each validator returns a (normalized_value, confidence_adjustment) tuple:
- normalized_value: str - Processed field value (empty on failure)
- confidence_adjustment: float - ∈ [-0.25, +0.10]
  
All validators are pure functions (no I/O, no exceptions raised).
"""

import logging
import re
from typing import Tuple

logger = logging.getLogger(__name__)

# Confidence adjustment constants
CONF_VALID = 0.10           # Valid/recognized format
CONF_CORRECTED = 0.08       # Corrected from common OCR errors
CONF_NORMALIZED = 0.05      # Normalized/standardized successfully
CONF_EMPTY = 0.0            # Empty optional field (no adjustment)
CONF_AMBIGUOUS = -0.05      # Ambiguous but recoverable
CONF_INVALID = -0.20        # Invalid/non-recoverable
CONF_REQUIRED_MISSING = -0.25  # Required field empty (critical)

# Date boundaries (form context: birth dates, dates on government forms)
DATE_MIN_YEAR = 1950
DATE_MAX_YEAR = 2030
MAX_INPUT_LENGTH = 1000


def validate_date(value: str, confidence: float) -> Tuple[str, float]:
    """Validate and normalize date to DD/MM/YYYY format.
    
    Accepts: DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD, "March 15, 2020", ISO formats
    Validates: Day 1-31, Month 1-12, Year 1950-2030, accounting for leap years
    
    Args:
        value: Date string from OCR
        confidence: Current confidence (unused, kept for consistency)
    
    Returns:
        (normalized_date, confidence_adjustment)
        - normalized_date: "DD/MM/YYYY" or ""
        - confidence_adjustment: float ∈ [-0.25, +0.10]
    """
    if not value or not isinstance(value, str) or not value.strip():
        logger.debug("[VALIDATOR-DATE] Empty date")
        return ("", CONF_INVALID)
    
    value_clean = value.strip()
    if len(value_clean) > MAX_INPUT_LENGTH:
        logger.warning("[VALIDATOR-DATE] Input too long")
        return ("", CONF_INVALID)
    
    day: int | None = None
    month: int | None = None
    year: int | None = None
    
    # Try ISO format: YYYY-MM-DD or YYYY/MM/DD
    iso_match = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", value_clean)
    if iso_match:
        year, month, day = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
    else:
        # Try DD/MM/YYYY or DD-MM-YYYY format
        dmy_match = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", value_clean)
        if dmy_match:
            day, month, year = int(dmy_match.group(1)), int(dmy_match.group(2)), int(dmy_match.group(3))
    
    # Try spelled-out month: "March 15, 2020", "Mar 15 2020", "15 March 2020"
    if day is None:
        months_map = {
            'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
            'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
            'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'october': 10, 'oct': 10,
            'november': 11, 'nov': 11, 'december': 12, 'dec': 12,
        }
        for month_name, month_num in months_map.items():
            # "March 15, 2020" or "15 March 2020"
            pattern = rf"(?:(\d{{1,2}})\s+)?{month_name}(?:\s+(\d{{1,2}}),?)?\s+(\d{{4}})"
            spelled_match = re.search(pattern, value_clean, re.IGNORECASE)
            if spelled_match:
                month = month_num
                # Extract day and year
                groups = spelled_match.groups()
                if groups[0]:  # "March 15, 2020"
                    day, year = int(groups[0]), int(groups[2]) if groups[2] else int(spelled_match.group(0)[-4:])
                elif groups[1]:  # "March 15"
                    day, year = int(groups[1]), int(groups[2]) if groups[2] else int(spelled_match.group(0)[-4:])
                break
    
    # Validate extracted components
    if day is None or month is None or year is None:
        logger.debug(f"[VALIDATOR-DATE] Could not parse '{value_clean}'")
        return ("", CONF_INVALID)
    
    # Range checks
    if not (1 <= month <= 12):
        logger.debug(f"[VALIDATOR-DATE] Invalid month {month}")
        return ("", CONF_INVALID)
    
    if not (DATE_MIN_YEAR <= year <= DATE_MAX_YEAR):
        logger.debug(f"[VALIDATOR-DATE] Year {year} outside range")
        return ("", CONF_INVALID)
    
    # Day validation (accounting for leap years)
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        days_in_month[1] = 29
    
    if not (1 <= day <= days_in_month[month - 1]):
        logger.debug(f"[VALIDATOR-DATE] Invalid day {day} for month {month}")
        return ("", CONF_INVALID)
    
    normalized = f"{day:02d}/{month:02d}/{year:04d}"
    logger.debug("[VALIDATOR-DATE] Date validation successful")
    return (normalized, CONF_VALID)


def validate_phone(value: str, confidence: float) -> Tuple[str, float]:
    """Validate and standardize Philippine phone numbers.
    
    Accepts: +639XXXXXXXXX, 09XXXXXXXXX, 9XXXXXXXXX with separators
    Validates: PH country code, mobile prefixes (91X, 92X), 10-11 digits
    Standardizes to: +639XXXXXXXXX
    
    Args:
        value: Phone number from OCR
        confidence: Current confidence (unused)
    
    Returns:
        (standardized_phone, confidence_adjustment)
        - standardized_phone: "+639XXXXXXXXX" or ""
        - confidence_adjustment: float ∈ [-0.20, +0.05]
    """
    if not value or not isinstance(value, str) or not value.strip():
        logger.debug("[VALIDATOR-PHONE] Empty phone")
        return ("", CONF_INVALID)
    
    value_clean = value.strip()
    
    # Remove separators: spaces, hyphens, parentheses
    cleaned = re.sub(r"[\s\-\(\)]+", "", value_clean)
    
    # Extract numeric and leading + sign only
    digits_only = re.sub(r"[^\d\+]", "", cleaned)
    
    # Normalize format
    if digits_only.startswith("+63"):
        phone_digits = digits_only[1:]  # Remove leading +
    elif digits_only.startswith("63"):
        phone_digits = digits_only
    elif digits_only.startswith("09"):
        phone_digits = "63" + digits_only[1:]
    elif digits_only.startswith("9") and len(digits_only) >= 10:
        phone_digits = "63" + digits_only
    else:
        logger.debug(f"[VALIDATOR-PHONE] Invalid format '{value_clean}'")
        return ("", CONF_INVALID)
    
    # Validate length
    if len(phone_digits) != 12:
        logger.debug(f"[VALIDATOR-PHONE] Invalid length {len(phone_digits)}")
        return ("", CONF_INVALID)
    
    # Validate PH country code
    if not phone_digits.startswith("63"):
        logger.debug(f"[VALIDATOR-PHONE] Not a PH number")
        return ("", CONF_INVALID)
    
    # Validate mobile prefix (3rd-4th digits after country code)
    mobile_prefix = phone_digits[2:4]
    # Valid prefixes: 908-915 (DITO), 917-919 (Globe), 920-921, 928-929 (Smart), etc.
    # Accept: 90X, 91X, 92X (covers all major PH carriers)
    if not (mobile_prefix[0] in ['9'] and mobile_prefix[1] in ['0', '1', '2']):
        logger.debug(f"[VALIDATOR-PHONE] Invalid mobile prefix '{mobile_prefix}'")
        return ("", CONF_INVALID)
    
    standardized = f"+{phone_digits}"
    logger.debug("[VALIDATOR-PHONE] Phone validation successful")
    return (standardized, CONF_NORMALIZED)


def validate_checkbox(value: str, confidence: float) -> Tuple[str, float]:
    """Validate and normalize checkbox values to Yes/No or empty.
    
    Accepts: Yes/No and 12+ variations (y, true, ✓, false, no, 0, etc.)
    Normalizes to: "Yes", "No", or "" (ambiguous/empty)
    
    Args:
        value: Checkbox value from OCR
        confidence: Current confidence (unused)
    
    Returns:
        (normalized_value, confidence_adjustment)
        - normalized_value: "Yes", "No", or ""
        - confidence_adjustment: float ∈ [-0.05, +0.05]
    """
    if not value or not isinstance(value, str) or not value.strip():
        logger.debug("[VALIDATOR-CHECKBOX] Empty checkbox")
        return ("", CONF_EMPTY)
    
    value_clean = value.strip().lower()
    
    # Yes variations
    yes_patterns = ["yes", "y", "true", "1", "✓", "✔", "checked", "x"]
    if value_clean in yes_patterns:
        logger.debug("[VALIDATOR-CHECKBOX] Checkbox validated as Yes")
        return ("Yes", CONF_NORMALIZED)
    
    # No variations
    no_patterns = ["no", "n", "false", "0", "☐", "unchecked", "empty"]
    if value_clean in no_patterns:
        logger.debug("[VALIDATOR-CHECKBOX] Checkbox validated as No")
        return ("No", CONF_NORMALIZED)
    
    # Ambiguous values
    ambiguous_patterns = ["maybe", "unknown", "?", "unclear", "n/a", "na"]
    if value_clean in ambiguous_patterns:
        logger.debug(f"[VALIDATOR-CHECKBOX] Ambiguous '{value}'")
        return ("", CONF_AMBIGUOUS)
    
    # Unrecognized
    logger.debug(f"[VALIDATOR-CHECKBOX] Unrecognized '{value}'")
    return ("", CONF_AMBIGUOUS)


def validate_amount(value: str, confidence: float) -> Tuple[str, float]:
    """Validate and normalize currency amounts to X,XXX.XX format.
    
    Accepts: 5000, "₱5000", "P5000", "5,000.50", "-5000", etc.
    Normalizes to: X,XXX.XX (with thousands comma, 2 decimals)
    Preserves negative sign for refunds
    
    Args:
        value: Currency amount from OCR
        confidence: Current confidence (unused)
    
    Returns:
        (formatted_amount, confidence_adjustment)
        - formatted_amount: "X,XXX.XX" or ""
        - confidence_adjustment: float ∈ [-0.20, +0.08]
    """
    if not value or not isinstance(value, str) or not value.strip():
        logger.debug("[VALIDATOR-AMOUNT] Empty amount")
        return ("", CONF_INVALID)
    
    value_clean = value.strip()
    if len(value_clean) > MAX_INPUT_LENGTH:
        logger.warning("[VALIDATOR-AMOUNT] Input too long")
        return ("", CONF_INVALID)
    
    # Count currency symbols (max 1)
    currency_symbols = ["₱", "$", "€", "£", "¥"]
    symbol_count = sum(value_clean.count(sym) for sym in currency_symbols)
    
    # Count 'P' as currency only if followed by digit or space
    p_as_currency = len(re.findall(r"P(?=[\d\s])", value_clean))
    symbol_count += p_as_currency
    
    if symbol_count > 1:
        logger.debug("[VALIDATOR-AMOUNT] Multiple currency symbols")
        return ("", CONF_INVALID)
    
    # Remove currency symbols
    no_currency = re.sub(r"[₱P$€£¥]", "", value_clean)
    no_spaces = no_currency.replace(" ", "")
    
    # Extract numeric part
    numeric_match = re.match(r"^(-?)(\d{1,3}(?:,?\d{3})*\.?\d{0,2})$", no_spaces)
    if not numeric_match:
        logger.debug(f"[VALIDATOR-AMOUNT] Non-numeric format")
        return ("", CONF_INVALID)
    
    is_negative = numeric_match.group(1) == "-"
    digits_part = numeric_match.group(2)
    
    try:
        amount_value = float(digits_part.replace(",", ""))
    except ValueError:
        logger.debug("[VALIDATOR-AMOUNT] Failed to parse")
        return ("", CONF_INVALID)
    
    # Format: X,XXX.XX
    if is_negative:
        formatted = f"-{abs(amount_value):,.2f}"
    else:
        formatted = f"{amount_value:,.2f}"
    
    logger.debug("[VALIDATOR-AMOUNT] Amount validation successful")
    return (formatted, CONF_CORRECTED)


def validate_required(value: str, is_required: bool, confidence: float) -> Tuple[str, float]:
    """Validate required fields are populated.
    
    Args:
        value: Field value
        is_required: Whether field is marked required
        confidence: Current confidence (unused)
    
    Returns:
        (value_unchanged, confidence_adjustment)
        - value_unchanged: Original value (never modified)
        - confidence_adjustment: float ∈ [-0.25, +0.05]
            - Required empty: -0.25 (critical)
            - Required filled: +0.05 (verified)
            - Optional: 0.0 (no adjustment)
    """
    if not is_required:
        return (value, CONF_EMPTY)
    
    # Check if empty or whitespace-only
    is_empty = not value or (isinstance(value, str) and not value.strip())
    
    if is_empty:
        logger.warning("[VALIDATOR-REQUIRED] Empty required field")
        return (value, CONF_REQUIRED_MISSING)
    else:
        logger.debug(f"[VALIDATOR-REQUIRED] Filled required field")
        return (value, CONF_NORMALIZED)
