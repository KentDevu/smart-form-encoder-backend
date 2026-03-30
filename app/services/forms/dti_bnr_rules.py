"""Form-specific post-processing rules for DTI Business Name Registration (DTI BNR) form."""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Common OCR correction mappings for letter ↔ number confusion
OCR_LETTER_TO_NUMBER_MAP = {
    "I": "1",  # Capital I → 1
    "l": "1",  # Lowercase L → 1
    "O": "0",  # Capital O → 0
    "o": "0",  # Lowercase O → 0
    "Z": "2",  # Capital Z → 2
    "S": "5",  # Capital S → 5
}

# Philippine cities and barangays (sample for fuzzy matching)
PH_MUNICIPALITIES = {
    "manila", "quezon city", "caloocan", "dagupan", "cebu",
    "davao", "cagayan de oro", "iloilo", "zamboanga", "antipolo",
}

PH_BARANGAYS_SAMPLE = {
    "makati", "taguig", "pasig", "mandaluyong", "san juan",
    "sampaloc", "quintin paredes", "radial road",
}


def _apply_ocr_substitutions(text: str, char_map: dict[str, str]) -> str:
    """Apply character substitutions for OCR error correction."""
    result = text
    for wrong, correct in char_map.items():
        result = result.replace(wrong, correct)
    return result


def _remove_non_numeric(text: str, keep_decimal: bool = False) -> str:
    """Remove all non-numeric characters from text."""
    if keep_decimal:
        return re.sub(r"[^0-9.]", "", text)
    return re.sub(r"[^0-9]", "", text)


def _fuzzy_match_city(text: str, threshold: float = 0.7) -> str | None:
    """Attempt fuzzy matching against known PH municipalities."""
    text_lower = text.lower().strip()
    
    # Exact match first
    if text_lower in PH_MUNICIPALITIES:
        return text_lower
    
    # Check for substring matches
    for city in PH_MUNICIPALITIES:
        if city in text_lower or text_lower in city:
            return city
    
    return None


# =============================================================================
# Field-Specific Validators & Correctors
# =============================================================================

def validate_certificate_no(value: str) -> dict[str, Any]:
    """
    Validate DTI certificate number format.
    
    Expected format: NR0:XXXXXX (8 characters)
    
    Args:
        value: Raw OCR value
        
    Returns:
        {value, confidence, corrected_value (optional)}
    """
    if not value:
        return {"value": "", "confidence": 0.0}
    
    # Remove whitespace
    value_clean = value.strip()
    
    # DTI cert format check: NR0: prefix + 6 digits
    match = re.match(r"NR0?(:| |)\d{6}", value_clean, re.IGNORECASE)
    
    if match:
        # Extract digits and reformat
        digits = _remove_non_numeric(value_clean[-6:])
        if len(digits) >= 6:
            corrected = f"NR0:{digits[:6]}"
            confidence = 0.90 if match.group(0) == value_clean else 0.80
            return {"value": corrected, "confidence": confidence}
    
    return {"value": value_clean, "confidence": 0.5}


def validate_phone_number(value: str) -> dict[str, Any]:
    """
    Validate and normalize Philippine phone numbers.
    
    Accepts formats: +639XX, 09XX, (0)9XX, with or without hyphens
    
    Args:
        value: Raw OCR value
        
    Returns:
        {value, confidence}
    """
    if not value:
        return {"value": "", "confidence": 0.0}
    
    # Remove non-digit characters except leading +
    digits_only = _remove_non_numeric(value)
    
    # Accept 10-12 digit lengths (flexible for PH numbers)
    if 10 <= len(digits_only) <= 12:
        # Normalize to 09XX-XXXXXX format
        if digits_only.startswith("63"):
            # +639XX format, convert to 09XX
            digits_only = "0" + digits_only[2:]
        elif digits_only.startswith("9"):
            # 9XX format, add leading 0
            digits_only = "0" + digits_only
        
        if digits_only.startswith("09") and len(digits_only) == 11:
            formatted = f"{digits_only[:4]}-{digits_only[4:]}"
            confidence = 0.85 if re.match(r"^\d{4}-\d+$", formatted) else 0.75
            return {"value": formatted, "confidence": confidence}
    
    # Low confidence if format doesn't match
    return {"value": value, "confidence": 0.4}


def validate_date_of_birth(year: str, month: str, day: str) -> dict[str, Any]:
    """
    Validate and correct date of birth fields with inference.
    
    Args:
        year: Year value (may be incomplete)
        month: Month value (may have I→1, S→5 errors)
        day: Day value (may have OCR errors)
        
    Returns:
        {value: "YYYY-MM-DD", confidence}
    """
    corrected_year = year.strip() if year else ""
    corrected_month = month.strip() if month else ""
    corrected_day = day.strip() if day else ""
    
    # Year inference: if < 100, assume 19XX or 20XX
    if corrected_year:
        corrected_year = _apply_ocr_substitutions(corrected_year, {"I": "1", "O": "0"})
        corrected_year_clean = _remove_non_numeric(corrected_year)
        
        if corrected_year_clean:
            year_int = int(corrected_year_clean)
            if year_int < 100:
                # Heuristic: if < 50, assume 20XX; else 19XX
                year_int = 2000 + year_int if year_int < 50 else 1900 + year_int
                corrected_year = str(year_int)
    
    # Month correction: fix I→1, S→5
    if corrected_month:
        corrected_month = _apply_ocr_substitutions(corrected_month, {"I": "1", "S": "5"})
        corrected_month_clean = _remove_non_numeric(corrected_month)
        
        if corrected_month_clean:
            month_int = int(corrected_month_clean)
            if 1 <= month_int <= 12:
                corrected_month = str(month_int).zfill(2)
            else:
                corrected_month = ""
    
    # Day correction
    if corrected_day:
        corrected_day_clean = _remove_non_numeric(corrected_day)
        
        if corrected_day_clean:
            day_int = int(corrected_day_clean)
            if 1 <= day_int <= 31:
                corrected_day = str(day_int).zfill(2)
            else:
                corrected_day = ""
    
    # Assemble date
    if corrected_year and corrected_month and corrected_day:
        date_str = f"{corrected_year}-{corrected_month}-{corrected_day}"
        confidence = 0.82
        return {"value": date_str, "confidence": confidence}
    
    # Partial date
    parts = [p for p in [corrected_year, corrected_month, corrected_day] if p]
    if parts:
        return {"value": "-".join(parts), "confidence": 0.6}
    
    return {"value": "", "confidence": 0.0}


def validate_amount(value: str) -> dict[str, Any]:
    """
    Validate currency amount with common OCR error fixes.
    
    Handles: ₱5,000, P5000, 5000, (bracket vs paren confusion)
    
    Args:
        value: Raw OCR value
        
    Returns:
        {value, confidence}
    """
    if not value:
        return {"value": "", "confidence": 0.0}
    
    # Check for negative sign and reject
    if "-" in value:
        return {"value": "", "confidence": 0.0}
    
    # Remove currency symbols and brackets
    value_clean = value.replace("₱", "").replace("P", "").replace("(", "").strip()
    
    # Extract digits (keep commas and decimal)
    amount_str = re.sub(r"[^0-9.,]", "", value_clean)
    
    # Remove commas for validation
    amount_numeric = amount_str.replace(",", "")
    
    # Validate it's numeric
    try:
        amount_float = float(amount_numeric) if amount_numeric else 0.0
        if amount_float >= 0:
            # Format with commas if large
            if amount_float >= 1000:
                formatted = f"₱{amount_float:,.2f}"
            else:
                formatted = f"₱{amount_float:.2f}"
            
            confidence = 0.85 if "," in amount_str else 0.75
            return {"value": formatted, "confidence": confidence}
    except ValueError:
        pass
    
    return {"value": "", "confidence": 0.2}


def validate_business_address(house_bldg: str, street: str, barangay: str, 
                               city: str, province: str) -> dict[str, Any]:
    """
    Validate business address with fuzzy matching for PH locations.
    
    Args:
        house_bldg: House/Building number
        street: Street name
        barangay: Barangay
        city: City/Municipality
        province: Province
        
    Returns:
        {value: "Formatted address", confidence}
    """
    parts = []
    
    # Add non-empty parts
    if house_bldg:
        parts.append(house_bldg.strip())
    if street:
        parts.append(street.strip())
    if barangay:
        parts.append(barangay.strip())
    if city:
        # Try fuzzy match
        matched_city = _fuzzy_match_city(city)
        parts.append(matched_city or city.strip())
    if province:
        parts.append(province.strip())
    
    if parts:
        address = ", ".join(parts)
        confidence = 0.75
        return {"value": address, "confidence": confidence}
    
    return {"value": "", "confidence": 0.0}


def validate_name(first: str, middle: str, last: str, suffix: str = "") -> dict[str, Any]:
    """
    Validate and clean name fields.
    
    Args:
        first: First name
        middle: Middle name
        last: Last name
        suffix: Suffix (Jr, Sr, III, etc)
        
    Returns:
        {value: "First Middle Last Suffix", confidence}
    """
    parts = []
    
    for name_part in [first, middle, last]:
        if name_part:
            cleaned = name_part.strip()
            # Remove non-alphabetic except spaces and hyphens
            cleaned = re.sub(r"[^a-zA-Z\s\-']", "", cleaned)
            if cleaned:
                parts.append(cleaned.title())
    
    if suffix:
        suffix_clean = suffix.strip()
        parts.append(suffix_clean)
    
    if parts:
        full_name = " ".join(parts)
        confidence = 0.80
        return {"value": full_name, "confidence": confidence}
    
    return {"value": "", "confidence": 0.0}


# =============================================================================
# Main DTI BNR Post-Processing Function
# =============================================================================

def apply_dti_bnr_corrections(fields: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    Apply all DTI BNR form-specific corrections to extracted fields.
    
    Args:
        fields: {field_name: {value, confidence}, ...}
        
    Returns:
        {field_name: {value, confidence}, ...} with corrections applied
    """
    corrected = fields.copy()
    
    # ─────────────────────────────────────────────
    # 1. CHECKBOX FIELD HANDLING (Critical for Phase 3.2B)
    # ─────────────────────────────────────────────
    # Checkbox fields should return "true"/"false" strings.
    # If empty or just label text, try to infer from context.
    
    CHECKBOX_FIELDS = {
        # Activity types
        "activity_manufacturer", "activity_service", "activity_retailer",
        "activity_wholesaler", "activity_importer", "activity_exporter",
        # Partner agencies (checkboxes)
        "partner_philhealth", "partner_pagibig", "partner_sss",
        # Other checkboxes
        "same_as_business",
        # Other checkboxes that may be in template
        "is_refugee", "civil_status_single", "civil_status_married",
        "civil_status_widowed", "civil_status_legally_separated",
        "gender_male", "gender_female",
        "reg_type_new", "reg_type_renewal",
        "tin_status_with_tin", "tin_status_without_tin",
    }
    
    checkbox_count = 0
    for checkbox_field in ['activity_manufacturer', 'activity_service', 'activity_retailer',
                          'activity_wholesaler', 'activity_importer', 'activity_exporter',
                          'partner_philhealth', 'partner_pagibig', 'partner_sss',
                          'same_as_business', 'is_refugee',
                          'civil_status_single', 'civil_status_married', 'civil_status_widowed', 
                          'civil_status_legally_separated', 'gender_male', 'gender_female',
                          'reg_type_new', 'reg_type_renewal', 'tin_status_with_tin', 'tin_status_without_tin']:
        if checkbox_field in corrected:
            value = corrected[checkbox_field].get("value", "").strip()
            conf = corrected[checkbox_field].get("confidence", 0.5)
            source = corrected[checkbox_field].get("source", "")
            
            # CRITICAL: Skip DTI rules if this checkbox came from visual checkbox detection
            # (Phase 3.2B checkbox_field_mapping.py already determined true/false)
            if source == "checkbox_detection":
                # Preserve checkbox detection result as-is
                if value in ["true", "false"]:
                    checkbox_count += 1
                    continue
            
            # Priority 1: Already valid checkbox states ("true", "false") → keep them
            if value.lower() in ['true', 'yes', '1', 'checked', '✓', 'x']:
                # Saw explicit "true"/"yes" — checkbox is checked
                corrected[checkbox_field] = {
                    "value": "true",
                    "confidence": min(0.95, conf * 1.1)  # Slightly boost for explicit state
                }
                checkbox_count += 1
            elif value.lower() in ['false', 'no', '0', 'unchecked']:
                # Saw explicit "false"/"no" — checkbox is NOT checked
                corrected[checkbox_field] = {
                    "value": "false",
                    "confidence": min(0.95, conf * 1.1)
                }
                checkbox_count += 1
            # Priority 2: Value is empty or just a label → default to unchecked
            elif not value or (len(value) < 20 and value.lower() in [
                'yes.', 'no.',
                # Activity labels that might be returned by OCR
                'service', 'retailer', 'wholesaler', 'manufacturer', 'importer', 'exporter',
                'producer', 'single', 'married', 'widowed', 'legally separated',
                'male', 'female', 'new', 'renewal', 'with tin', 'without tin',
                # Partner agencies
                'philhealth', 'pag-ibig', 'pagibig', 'pag ibig', 'sss',
                # Other
                'same as business', 'refugee'
            ]):
                # For these cases, default to empty (unchecked)
                # Since we can't determine state from label alone, keep empty
                corrected[checkbox_field] = {
                    "value": "",  # Empty = unchecked by default
                    "confidence": max(0.5, conf * 0.7)  # Lower confidence for uncertain checkbox
                }
                checkbox_count += 1
            # Priority 3: Visual marks (✓, ×, etc.) → infer state from mark
            else:
                if any(mark in value for mark in ['✓', 'X', 'x', '||', '█', '■', '●']):
                    corrected[checkbox_field] = {"value": "true", "confidence": 0.80}
                    checkbox_count += 1
                elif any(mark in value for mark in ['□', '○', '()', '[]']):
                    corrected[checkbox_field] = {"value": "false", "confidence": 0.80}
                    checkbox_count += 1
    
    if checkbox_count > 0:
        logger.debug(f"[DTI-RULES] Processed {checkbox_count} checkbox fields")
    
    # Certificate number
    if "certificate_no" in corrected and corrected["certificate_no"].get("value"):
        corrected["certificate_no"] = validate_certificate_no(
            corrected["certificate_no"]["value"]
        )
        logger.debug("[DTI-RULES] Certificate number corrected")
    
    # Phone numbers
    for phone_field in ["biz_phone", "biz_mobile", "owner_phone", "owner_mobile"]:
        if phone_field in corrected and corrected[phone_field].get("value"):
            corrected[phone_field] = validate_phone_number(
                corrected[phone_field]["value"]
            )
            logger.debug(f"[DTI-RULES] {phone_field} corrected")
    
    # Date of birth (composite field)
    if any(k in corrected for k in ["dob_year", "dob_month", "dob_day"]):
        year = corrected.get("dob_year", {}).get("value", "")
        month = corrected.get("dob_month", {}).get("value", "")
        day = corrected.get("dob_day", {}).get("value", "")
        
        dob_corrected = validate_date_of_birth(year, month, day)
        # Store composite date (optional: could split back)
        if dob_corrected["value"]:
            corrected["dob_composite"] = dob_corrected
            logger.debug("[DTI-RULES] Date of birth corrected")
    
    # Amounts
    if "capitalization" in corrected and corrected["capitalization"].get("value"):
        corrected["capitalization"] = validate_amount(
            corrected["capitalization"]["value"]
        )
        logger.debug("[DTI-RULES] Capitalization (business amount) corrected")
    
    # Business address
    house = corrected.get("biz_house_building", {}).get("value", "")
    street = corrected.get("biz_street", {}).get("value", "")
    barangay = corrected.get("biz_barangay", {}).get("value", "")
    city = corrected.get("biz_city_municipality", {}).get("value", "")
    province = corrected.get("biz_province", {}).get("value", "")
    
    if any([house, street, barangay, city, province]):
        addr_corrected = validate_business_address(house, street, barangay, city, province)
        if addr_corrected["value"]:
            corrected["biz_address_composite"] = addr_corrected
            logger.debug("[DTI-RULES] Business address corrected")
    
    # Names
    first = corrected.get("first_name", {}).get("value", "")
    middle = corrected.get("middle_name", {}).get("value", "")
    last = corrected.get("last_name", {}).get("value", "")
    suffix = corrected.get("suffix", {}).get("value", "")
    
    if any([first, middle, last]):
        name_corrected = validate_name(first, middle, last, suffix)
        if name_corrected["value"]:
            corrected["owner_name_composite"] = name_corrected
            logger.debug("[DTI-RULES] Owner name corrected")
    
    logger.info(f"[DTI-RULES] Applied post-processing corrections to {len(corrected)} fields")
    
    return corrected
