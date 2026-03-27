"""OCR text correction module for Philippine handwritten form processing.

Apply field-specific corrections to OCR output with confidence scoring adjustments.
Handles character substitutions, location names, phone numbers, amounts, dates,
and other form field types.
"""

import re
import logging
from typing import Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# ============================================================================
# CONSTANTS
# ============================================================================

MAX_TEXT_LENGTH = 10_000  # 10KB per field safety limit

VALID_FIELD_TYPES = {
    'name',
    'address',
    'amount',
    'date',
    'phone',
    'id_number',
    'checkbox',
}

# Character substitution map: OCR misread → correct digit
CHAR_SUBSTITUTIONS = {
    'O': '0',  # Uppercase letter O → zero
    'I': '1',  # Uppercase letter I → one
    'l': '1',  # Lowercase L → one
    'S': '5',  # Uppercase S → five
    'Z': '2',  # Uppercase Z → two
    'B': '8',  # Uppercase B → eight
}

# Common English words that should NOT have character substitutions
COMMON_ENGLISH_WORDS = {
    'smith', 'john', 'james', 'robert', 'michael', 'william', 'david', 'richard',
    'joseph', 'thomas', 'charles', 'christopher', 'daniel', 'matthew', 'other',
    'time', 'some', 'side', 'is', 'as', 'so', 'no', 'do', 'be', 'see', 'use',
    'very', 'only', 'also', 'just', 'over', 'such', 'these', 'those', 'his',
    'her', 'yes', 'boss', 'boss', 'lose', 'case', 'base', 'rose', 'dose',
}

# Safelist: exact phrases where substitutions should not apply
SUBSTITUTION_SAFELIST = {
    'bgc',  # Bonifacio Global City - B should not become 8
    'no',   # Number abbreviation
}

# Filipino location corrections (case-insensitive key, title-case value)
LOCATION_CORRECTIONS = {
    'qurzon': 'Quezon',
    'quorzon': 'Quezon',
    'quezón': 'Quezon',
    'qezon': 'Quezon',
    'cavitee': 'Cavite',
    'cavit': 'Cavite',
    'laguna': 'Laguna',
    'makati': 'Makati',
    'bgc': 'BGC',
}

# Abbreviation standardizations for addresses - extended to cover more variations
ADDRESS_ABBREVIATIONS = [
    (r'\bst\.?\b', 'Street', re.IGNORECASE),
    (r'\bst$', 'Street', re.IGNORECASE),
    (r'\bave\.?\b', 'Avenue', re.IGNORECASE),
    (r'\bav\.?\b', 'Avenue', re.IGNORECASE),  # AV or AV.
    (r'\bav$', 'Avenue', re.IGNORECASE),      # AV at end of string
    (r'\bblvd\.?\b', 'Boulevard', re.IGNORECASE),
    (r'\bno\.?\b', 'No.', re.IGNORECASE),
]

# Currency symbols to remove
CURRENCY_SYMBOLS = {'$', '€', '£', '¥', '₱', '¢'}

# Checkbox value mappings (normalized to Yes/No)
CHECKBOX_YES_VARIATIONS = {
    'yes', 'y', 'yeah', 'true', '1', '✓', '☑', 'checked', 'ok', 'yes.',
}
CHECKBOX_NO_VARIATIONS = {
    'no', 'n', 'nope', 'false', '0', '✗', '☐', 'unchecked', 'x',
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _is_valid_field_type(field_type: str) -> bool:
    """Check if field type is valid."""
    return field_type in VALID_FIELD_TYPES


def _clamp_confidence(confidence: float) -> float:
    """Clamp confidence to [0.0, 1.0] range."""
    return max(0.0, min(1.0, confidence))


def _is_in_safelist(text: str) -> bool:
    """Check if text contains words in substitution safelist."""
    text_lower = text.lower()
    return any(word in text_lower for word in SUBSTITUTION_SAFELIST)


def _looks_like_normal_name(text: str) -> bool:
    """Check if text looks like a normal English name (not OCR corruption).
    
    A normal name typically consists of common English words/names,
    not OCR artifacts.
    """
    text_lower = text.lower()
    words = text_lower.split()
    
    # If any word is in the common English words list, likely a normal name
    for word in words:
        if word in COMMON_ENGLISH_WORDS:
            return True
    
    return False


def _apply_char_substitutions(text: str, field_type: str = '') -> Tuple[str, bool]:
    """Apply OCR character substitutions contextually.
    
    For name fields: be conservative, skip if looks like normal name
    For other fields: apply more liberally
    
    Returns:
        Tuple[corrected_text, any_substitution_made]
    """
    # Check safelist first to avoid changing known words
    if _is_in_safelist(text):
        return text, False
    
    # For name fields, check if it looks like a normal name
    if field_type == 'name' and _looks_like_normal_name(text):
        return text, False
    
    corrected = text
    made_substitution = False
    
    for ocr_char, correct_char in CHAR_SUBSTITUTIONS.items():
        if ocr_char in corrected:
            # Apply substitution
            corrected = corrected.replace(ocr_char, correct_char)
            made_substitution = True
    
    return corrected, made_substitution


def _standardize_phone(text: str) -> Tuple[str, bool]:
    """Standardize phone number format.
    
    Removes formatting characters, validates digit count,
    standardizes +63 prefix.
    
    Returns:
        Tuple[cleaned_phone, is_valid]
    """
    # Extract leading + if present
    has_plus = text.lstrip().startswith('+')
    
    # Remove all non-digit characters except leading +
    stripped = ''.join(c for c in text if c.isdigit())
    
    # Handle country code +63 or leading 63
    if stripped.startswith('63'):
        # Country code prefix: extract phone number part (should be 10 digits)
        phone_part = stripped[2:]
        if len(phone_part) != 10:
            return text, False
        standardized = f"+63{phone_part}"
    elif len(stripped) == 11 and stripped.startswith('0'):
        # PH number with leading 0: convert to +639XX...
        standardized = f"+63{stripped[1:]}"
    elif len(stripped) == 10:
        # 10-digit number: add +63 prefix
        standardized = f"+63{stripped}"
    else:
        # Invalid length
        return text, False
    
    return standardized, True


def _standardize_amount(text: str) -> Tuple[str, bool]:
    """Standardize currency amount format.
    
    Removes currency symbols, normalizes decimal places.
    
    Returns:
        Tuple[cleaned_amount, is_valid]
    """
    # Remove currency symbols first
    cleaned = text
    for symbol in CURRENCY_SYMBOLS:
        cleaned = cleaned.replace(symbol, '')
    
    # Remove commas in thousands
    cleaned = cleaned.replace(',', '')
    
    # Attempt to extract numeric part
    # Allow leading minus, digits, single decimal point
    match = re.match(r'^(-?)(\d+)(?:\.(\d+))?$', cleaned.strip())
    if not match:
        return text, False
    
    sign, integer_part, decimal_part = match.groups()
    
    # Normalize to 2 decimal places
    if decimal_part is None:
        decimal_part = '00'
    elif len(decimal_part) == 1:
        decimal_part = decimal_part + '0'
    elif len(decimal_part) > 2:
        decimal_part = decimal_part[:2]
    
    standardized = f"{sign}{integer_part}.{decimal_part}"
    return standardized, True


def _standardize_date(text: str) -> Tuple[str, bool]:
    """Standardize date to DD/MM/YYYY format.
    
    Accepts DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY formats.
    Validates day, month, year ranges.
    Validates actual date (e.g., rejects Feb 30).
    
    Returns:
        Tuple[standardized_date, is_valid]
    """
    # Try to parse various date formats
    text_clean = text.strip()
    
    # Try different separators
    for separator in ['/', '-', '.']:
        if separator in text_clean:
            parts = text_clean.split(separator)
            if len(parts) == 3:
                try:
                    day, month, year = [int(p.strip()) for p in parts]
                    
                    # Basic range validation
                    if not (1 <= day <= 31):
                        continue
                    if not (1 <= month <= 12):
                        continue
                    if not (1950 <= year <= 2030):
                        continue
                    
                    # Validate actual date (leap years, days in month, etc.)
                    try:
                        datetime(year, month, day)
                    except ValueError:
                        continue
                    
                    # Valid date found
                    return f"{day:02d}/{month:02d}/{year:04d}", True
                except (ValueError, IndexError):
                    continue
    
    return text, False


def _standardize_id_number(text: str) -> Tuple[str, bool]:
    """Standardize ID number format.
    
    Removes non-alphanumeric characters, converts to uppercase,
    validates length.
    
    Returns:
        Tuple[cleaned_id, is_valid]
    """
    # Remove non-alphanumeric characters
    cleaned = ''.join(c for c in text if c.isalnum())
    
    # Uppercase
    cleaned = cleaned.upper()
    
    # Validate length (typically 8-12 characters)
    if len(cleaned) < 8 or len(cleaned) > 12:
        return text, False
    
    return cleaned, True


def _normalize_checkbox(text: str) -> Tuple[str, float]:
    """Normalize checkbox value to Yes/No.
    
    Returns:
        Tuple[normalized_value, confidence_adjustment]
    """
    text_lower = text.lower().strip()
    
    # Check for yes variations (high confidence)
    if text_lower in CHECKBOX_YES_VARIATIONS:
        return 'Yes', 0.05
    
    # Check for no variations (high confidence)
    if text_lower in CHECKBOX_NO_VARIATIONS:
        return 'No', 0.05
    
    # Default to Yes for ambiguous input
    logger.warning(f"Ambiguous checkbox value: '{text}', defaulting to Yes")
    return 'Yes', 0.0


def _title_case_name(text: str) -> str:
    """Apply title case to name field.
    
    Capitalizes first letter of each word.
    """
    return ' '.join(word.capitalize() for word in text.split())


def _apply_location_corrections(text: str) -> Tuple[str, int]:
    """Apply Filipino location name corrections.
    
    Case-insensitive matching, preserves output case.
    
    Returns:
        Tuple[corrected_text, num_corrections]
    """
    corrected = text
    correction_count = 0
    
    for misspelled, correct in LOCATION_CORRECTIONS.items():
        pattern = re.compile(re.escape(misspelled), re.IGNORECASE)
        if pattern.search(corrected):
            corrected = pattern.sub(correct, corrected)
            correction_count += 1
    
    return corrected, correction_count


def _standardize_abbreviations(text: str) -> Tuple[str, int]:
    """Standardize common address abbreviations.
    
    Returns:
        Tuple[standardized_text, num_corrections]
    """
    corrected = text
    correction_count = 0
    
    for pattern, replacement, flags in ADDRESS_ABBREVIATIONS:
        if re.search(pattern, corrected, flags):
            corrected = re.sub(pattern, replacement, corrected, flags=flags)
            correction_count += 1
    
    return corrected, correction_count


# ============================================================================
# MAIN CORRECTION FUNCTION
# ============================================================================

def correct_ocr_text(
    text: str,
    field_type: str,
    confidence: float = 0.5,
) -> Tuple[str, float]:
    """Apply field-specific OCR corrections with confidence adjustment.
    
    Args:
        text: Raw OCR output text
        field_type: Type of form field (name, address, amount, date, phone, id_number, checkbox)
        confidence: Current confidence score (0.0-1.0)
    
    Returns:
        Tuple[corrected_text, confidence_adjustment]
        - confidence_adjustment: value to add to confidence (-0.20 to +0.10)
        - Final confidence is always clamped to [0.0, 1.0]
    
    Raises:
        TypeError: If text is not a string
        ValueError: If field_type is invalid, confidence out of range, or text exceeds maximum length
    """
    # Input validation
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"Text exceeds maximum length of {MAX_TEXT_LENGTH} characters")
    
    if not _is_valid_field_type(field_type):
        raise ValueError(f"Invalid field_type: {field_type}. Must be one of {VALID_FIELD_TYPES}")
    
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence must be in [0.0, 1.0], got {confidence}")
    
    # Strip leading/trailing whitespace and normalize internal spaces
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)  # Normalize multiple spaces
    
    # Handle empty string
    if not text:
        return '', 0.0
    
    confidence_adjustment = 0.0
    corrected = text
    
    # ========================================================================
    # APPLY FIELD-SPECIFIC CORRECTIONS
    # ========================================================================
    
    if field_type == 'name':
        # For name fields: apply char substitutions conservatively
        corrected, made_sub = _apply_char_substitutions(corrected, field_type='name')
        if made_sub:
            confidence_adjustment += 0.05
        
        # Apply title case only if it changes the text
        title_cased = _title_case_name(corrected)
        if title_cased != corrected:
            corrected = title_cased
            confidence_adjustment += 0.05
    
    elif field_type == 'address':
        # Apply location corrections first (before char substitutions)
        corrected, num_location_corrections = _apply_location_corrections(corrected)
        confidence_adjustment += num_location_corrections * 0.08
        
        # Only apply char substitutions if no location was corrected
        if num_location_corrections == 0:
            corrected, made_sub = _apply_char_substitutions(corrected)
            if made_sub:
                confidence_adjustment += 0.05
        
        # Standardize abbreviations
        corrected, num_abbr = _standardize_abbreviations(corrected)
        confidence_adjustment += num_abbr * 0.03
    
    elif field_type == 'phone':
        # Apply character substitutions first
        corrected, made_sub = _apply_char_substitutions(corrected)
        if made_sub:
            confidence_adjustment += 0.05
        
        # Standardize phone format
        standardized, is_valid = _standardize_phone(corrected)
        if is_valid:
            corrected = standardized
            confidence_adjustment += 0.10
        else:
            # Invalid phone: char substitutions already applied
            logger.warning(f"Invalid phone format: '{text}'")
            confidence_adjustment = -0.20
    
    elif field_type == 'amount':
        # Apply character substitutions first
        corrected, made_sub = _apply_char_substitutions(corrected)
        if made_sub:
            confidence_adjustment += 0.05
        
        # Standardize amount format
        standardized, is_valid = _standardize_amount(corrected)
        if is_valid:
            corrected = standardized
            confidence_adjustment += 0.08
        else:
            # Invalid amount: char substitutions already applied above
            logger.warning(f"Invalid amount format: '{text}'")
            confidence_adjustment = -0.20
    
    elif field_type == 'date':
        # Apply character substitutions first
        corrected, made_sub = _apply_char_substitutions(corrected)
        if made_sub:
            confidence_adjustment += 0.05
        
        # Standardize date format
        standardized, is_valid = _standardize_date(corrected)
        if is_valid:
            corrected = standardized
            confidence_adjustment += 0.10
        else:
            # Invalid date: char substitutions already applied
            logger.warning(f"Invalid date format: '{text}'")
            confidence_adjustment = -0.20
    
    elif field_type == 'id_number':
        # Apply character substitutions first
        corrected, made_sub = _apply_char_substitutions(corrected)
        if made_sub:
            confidence_adjustment += 0.05
        
        # Standardize ID format
        standardized, is_valid = _standardize_id_number(corrected)
        if is_valid:
            corrected = standardized
            confidence_adjustment += 0.05
        else:
            # Invalid ID format: use char-substituted version
            logger.warning(f"Invalid ID number format: '{text}'")
            confidence_adjustment -= 0.05
    
    elif field_type == 'checkbox':
        # Normalize checkbox value
        normalized, checkbox_conf = _normalize_checkbox(corrected)
        corrected = normalized
        confidence_adjustment += checkbox_conf
    
    # ========================================================================
    # CALCULATE FINAL CONFIDENCE
    # ========================================================================
    
    final_confidence = _clamp_confidence(confidence + confidence_adjustment)
    
    logger.info(
        f"Corrected {field_type} field: '{text}' → '{corrected}' "
        f"(confidence adj: {confidence_adjustment:+.2f}, final: {final_confidence:.2f})"
    )
    
    return corrected, confidence_adjustment
