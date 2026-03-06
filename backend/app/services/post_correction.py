"""Post-OCR text correction for Philippine forms.

Rule-based correction engine that fixes common OCR errors without
needing ML training. Applied after AI field extraction as a cleanup step.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Common OCR character confusion pairs for handwritten text
OCR_DIGIT_FIXES = {
    "O": "0", "o": "0",
    "l": "1", "I": "1",
    "S": "5", "s": "5",
    "B": "8",
    "G": "6",
}

# Philippine-specific abbreviation patterns (regex pattern → replacement)
# Uses negative lookahead (?!\w) to avoid matching partial words
PH_ABBREVIATION_PATTERNS: list[tuple[str, str]] = [
    (r"\bbrgy\.?(?!\w)", "Brgy."),
    (r"\bbarangay(?!\w)", "Barangay"),
    (r"\bmun\.?(?!\w)", "Mun."),
    (r"\bprov\.?(?!\w)", "Prov."),
    (r"\bst\.?(?!\w)", "St."),
    (r"\bave\.?(?!\w)", "Ave."),
    (r"\bblvd\.?(?!\w)", "Blvd."),
]

# Common Filipino first names (for fuzzy matching)
FILIPINO_FIRST_NAMES = {
    "JUAN", "MARIA", "JOSE", "PEDRO", "ROSA", "CARLOS", "ANA",
    "ANTONIO", "FRANCISCO", "MANUEL", "LOURDES", "ELENA", "GABRIEL",
    "CHRISTOPHER", "MICHAEL", "PRINCESS", "ANGEL", "MARK", "JOHN",
    "MARY", "GRACE", "JOY", "FAITH", "HOPE", "LOVE", "DIVINE",
    "ROMEO", "JULIET", "BENJAMIN", "DIEGO", "ISABELLA", "SOPHIA",
    "ALTHEA", "DENISE", "MARIE", "ROSE", "MAE", "LYN", "ANN",
    "JAMES", "ROBERT", "DAVID", "DANIEL", "PAUL", "PETER",
    "ANDREA", "CHRISTINE", "PATRICIA", "JENNIFER", "ELIZABETH",
}

# Common Filipino surnames
FILIPINO_SURNAMES = {
    "SANTOS", "REYES", "CRUZ", "GARCIA", "DELA CRUZ", "GONZALES",
    "RAMOS", "AQUINO", "BAUTISTA", "MENDOZA", "TORRES", "FERNANDEZ",
    "VILLANUEVA", "CASTILLO", "RIVERA", "HERNANDEZ", "SANTIAGO",
    "MARTINEZ", "FLORES", "LOPEZ", "MORALES", "NAVARRO", "PEREZ",
    "DIZON", "ESPIRITU", "MANALO", "SORIANO", "PASCUAL", "ENRIQUEZ",
    "DELOS SANTOS", "DELOS REYES", "DEL ROSARIO", "DE LEON",
    "DE GUZMAN", "DE JESUS", "DE LA CRUZ", "DE LOS SANTOS",
}

ALL_PH_NAMES = FILIPINO_FIRST_NAMES | FILIPINO_SURNAMES

# Field name → correction type mapping for DTI BNR form
FIELD_TYPE_MAP: dict[str, str] = {
    # Names
    "first_name": "name",
    "middle_name": "name",
    "last_name": "name",
    "suffix": "name",
    # Dates
    "birth_year": "year",
    "birth_month": "month",
    "birth_day": "day",
    # Phone
    "biz_phone": "phone",
    "biz_mobile": "phone",
    "owner_phone": "phone",
    "owner_mobile": "phone",
    # TIN
    "owners_tin": "tin",
    # Address fields
    "biz_house_building": "address",
    "biz_street": "address",
    "biz_barangay": "address",
    "biz_city_municipality": "address",
    "biz_province": "address",
    "biz_region": "address",
    "owner_house_building": "address",
    "owner_street": "address",
    "owner_barangay": "address",
    "owner_city_municipality": "address",
    "owner_province": "address",
    "owner_region": "address",
    # Currency
    "asset": "currency",
    "capitalization": "currency",
    "gross_sale_receipt": "currency",
    # Numeric
    "employees_male": "integer",
    "employees_female": "integer",
    "employees_total": "integer",
    # Email — leave as-is (no correction needed)
    "owner_email": "email",
}


def correct_field(field_name: str, value: str) -> str:
    """
    Apply rule-based post-OCR correction to a single field value.

    Returns the corrected value (unchanged if no correction needed).
    """
    if not value or not value.strip():
        return value

    field_type = FIELD_TYPE_MAP.get(field_name, "text")
    corrected = _clean_whitespace(value)

    if field_type == "name":
        corrected = _correct_name(corrected)
    elif field_type in ("year", "month", "day"):
        corrected = _correct_date_part(corrected, field_type)
    elif field_type == "phone":
        corrected = _correct_phone(corrected)
    elif field_type == "tin":
        corrected = _correct_tin(corrected)
    elif field_type == "address":
        corrected = _correct_address(corrected)
    elif field_type == "currency":
        corrected = _correct_currency(corrected)
    elif field_type == "integer":
        corrected = _correct_integer(corrected)

    return corrected


def apply_post_corrections(
    fields: list[dict],
) -> list[dict]:
    """
    Apply post-OCR corrections to all extracted fields.

    Args:
        fields: List of field dicts with 'field_name', 'value', 'confidence'

    Returns:
        Same list with corrected values and updated confidence.
    """
    corrections_made = 0

    for field in fields:
        name = field.get("field_name", "")
        value = field.get("value", "")

        if not value:
            continue

        corrected = correct_field(name, value)

        if corrected != value:
            logger.info(
                f"Post-correction: '{name}' '{value}' → '{corrected}'"
            )
            field["value"] = corrected
            # Slightly boost confidence for corrected fields
            # (rule-based corrections are high-confidence fixes)
            field["confidence"] = min(
                float(field.get("confidence", 0.9)) + 0.02, 0.98
            )
            corrections_made += 1

    if corrections_made:
        logger.info(f"Post-correction: {corrections_made} fields corrected")

    return fields


# ── Correction functions ──


def _clean_whitespace(text: str) -> str:
    """Normalize whitespace."""
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    return text


def _correct_name(text: str) -> str:
    """Correct name fields — title case, PH name dictionary lookup."""
    words = text.split()
    corrected_words = []
    for word in words:
        word_upper = word.upper()
        if word_upper in ALL_PH_NAMES:
            corrected_words.append(word.title())
        elif word.isalpha() and len(word) > 1:
            corrected_words.append(word.title())
        else:
            corrected_words.append(word)
    return " ".join(corrected_words)


def _correct_date_part(text: str, part_type: str) -> str:
    """Correct date parts (year, month, day) — fix digit OCR errors."""
    # Replace common letter→digit confusions
    corrected = text
    for letter, digit in OCR_DIGIT_FIXES.items():
        corrected = corrected.replace(letter, digit)

    # Strip non-digits
    digits = re.sub(r"[^\d]", "", corrected)

    if part_type == "year" and len(digits) == 4:
        return digits
    elif part_type == "year" and len(digits) == 2:
        y = int(digits)
        return f"20{digits}" if y < 50 else f"19{digits}"
    elif part_type in ("month", "day") and digits:
        num = int(digits)
        if part_type == "month":
            num = max(1, min(12, num))
        elif part_type == "day":
            num = max(1, min(31, num))
        return f"{num:02d}"

    return text


def _correct_phone(text: str) -> str:
    """Correct phone number formats — keep valid phone characters."""
    # First fix digit confusions
    corrected = text
    for letter, digit in OCR_DIGIT_FIXES.items():
        corrected = corrected.replace(letter, digit)
    # Keep only phone-valid characters
    corrected = re.sub(r"[^\d+\-()\s]", "", corrected)
    return corrected.strip()


def _correct_tin(text: str) -> str:
    """Correct TIN format: XXX-XXX-XXX-XXX."""
    # Fix digit confusions first
    corrected = text
    for letter, digit in OCR_DIGIT_FIXES.items():
        corrected = corrected.replace(letter, digit)
    # Extract pure digits
    digits = re.sub(r"[^\d]", "", corrected)
    if len(digits) == 12:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:9]}-{digits[9:12]}"
    elif len(digits) == 9:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:9]}"
    return text


def _correct_address(text: str) -> str:
    """Correct address fields — standardize PH abbreviations."""
    corrected = text
    for pattern, replacement in PH_ABBREVIATION_PATTERNS:
        corrected = re.sub(pattern, replacement, corrected, flags=re.IGNORECASE)
    return corrected


def _correct_currency(text: str) -> str:
    """Correct currency amounts — fix digits, standardize format."""
    # Fix digit confusions
    corrected = text
    for letter, digit in OCR_DIGIT_FIXES.items():
        corrected = corrected.replace(letter, digit)
    # Remove everything except digits, commas, dots
    corrected = re.sub(r"[^\d,.]", "", corrected)
    return corrected


def _correct_integer(text: str) -> str:
    """Correct integer fields — extract digits only."""
    corrected = text
    for letter, digit in OCR_DIGIT_FIXES.items():
        corrected = corrected.replace(letter, digit)
    digits = re.sub(r"[^\d]", "", corrected)
    return digits if digits else text
