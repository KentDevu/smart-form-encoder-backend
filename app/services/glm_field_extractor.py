"""
GLM Field Extractor - Adapter between GLM output and FormField database model

This module converts raw GLM-OCR output (field name → value pairs) into database-ready
FormField records with proper validation, normalization, and source tracking.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class GLMFieldExtractor:
    """
    Adapter to convert GLM-OCR output to FormField schema.
    
    Responsibilities:
    - Map GLM field names to canonical form field names
    - Normalize values (checkboxes, dates, text formatting)
    - Add metadata (source, confidence, field type)
    - Validate against form template schema
    """
    
    # Field name mapping: GLM output → canonical form field name
    # This handles variations in field naming from different OCR runs
    FIELD_NAME_MAPPING = {
        # DTI BNR Form - Section A
        "registration_type": "registration_type",
        "is_new_registration": "is_new_registration",
        "is_renewal": "is_renewal",
        "certificate_no": "certificate_no",
        "date_registered": "date_registered",
        
        # Section B - TIN
        "with_tin": "with_tin",
        "tin": "tin",
        "without_tin": "without_tin",
        
        # Section C - Owner's Information
        "first_name": "first_name",
        "middle_name": "middle_name",
        "last_name": "last_name",
        "date_of_birth": "date_of_birth",
        "civil_status": "civil_status",
        "gender": "gender",
        
        # Section D - Business Name Territorial Scope
        "barangay_registration": "barangay_registration",
        "city_municipality_registration": "city_municipality_registration",
        "regional_registration": "regional_registration",
        "national_registration": "national_registration",
        
        # Section E - Proposed Business Names
        "proposed_business_name_1": "proposed_business_name_1",
        "proposed_business_name_2": "proposed_business_name_2",
        "proposed_business_name_3": "proposed_business_name_3",
        
        # Section F - Business Details
        "business_house_no": "business_house_no",
        "business_street": "business_street",
        "business_barangay": "business_barangay",
        "business_city": "business_city",
        "business_province": "business_province",
        "business_region": "business_region",
        "business_phone": "business_phone",
        "business_mobile": "business_mobile",
        
        # Section G - PSIC
        "main_business_activity": "main_business_activity",
        "psic_code": "psic_code",
        "psic_description": "psic_description",
        
        # Section H - Owner Details
        "owner_same_as_business": "owner_same_as_business",
        "owner_house_no": "owner_house_no",
        "owner_street": "owner_street",
        "owner_barangay": "owner_barangay",
        "owner_city": "owner_city",
        "owner_province": "owner_province",
        "owner_region": "owner_region",
        "owner_phone": "owner_phone",
        "owner_mobile": "owner_mobile",
        "owner_email": "owner_email",
        
        # Section I - Partner Agencies
        "philhealth_registration": "philhealth_registration",
        "sss_registration": "sss_registration",
        "pagibig_registration": "pagibig_registration",
        
        # Section J - Other Details
        "asset_value": "asset_value",
        "capitalization": "capitalization",
        "male_employees": "male_employees",
        "female_employees": "female_employees",
        "total_employees": "total_employees",
    }
    
    # Field type mappings - for specialized normalization
    CHECKBOX_FIELDS = {
        "is_new_registration",
        "is_renewal",
        "with_tin",
        "without_tin",
        "barangay_registration",
        "city_municipality_registration",
        "regional_registration",
        "national_registration",
        "owner_same_as_business",
        "philhealth_registration",
        "sss_registration",
        "pagibig_registration",
    }
    
    DATE_FIELDS = {
        "date_registered",
        "date_of_birth",
    }
    
    NUMERIC_FIELDS = {
        "asset_value",
        "capitalization",
        "male_employees",
        "female_employees",
        "total_employees",
    }
    
    @staticmethod
    def adapt_glm_output(
        glm_fields: list[dict[str, Any]],
        form_template_id: Optional[str] = None,
        form_type: str = "dti_bnr",
    ) -> list[dict[str, Any]]:
        """
        Convert GLM-OCR output to FormField records.
        
        Args:
            glm_fields: List of dicts from GLM service 
                       [{"field_name": "...", "value": "...", "confidence": 0.9, "source": "glm_ocr"}, ...]
            form_template_id: Optional template ID for context
            form_type: Form type (e.g., "dti_bnr")
            
        Returns:
            List of FormField-ready dicts:
            [{"field_name": "...", "value": "...", "ocr_value": "...", "confidence": 0.9, "source": "glm_ocr"}, ...]
        """
        extractor = GLMFieldExtractor()
        form_fields = []
        
        logger.debug(f"[GLM-ADAPTER] Adapting {len(glm_fields)} GLM fields, form_type={form_type}")
        
        for glm_field in glm_fields:
            raw_field_name = glm_field.get("field_name", "")
            raw_value = glm_field.get("value", "")
            confidence = glm_field.get("confidence", 0.85)
            source = glm_field.get("source", "glm_ocr")
            
            # Map field name to canonical name
            canonical_name = GLMFieldExtractor.FIELD_NAME_MAPPING.get(
                raw_field_name, raw_field_name
            )
            
            # Normalize value based on field type
            normalized_value = extractor._normalize_field_value(
                canonical_name, raw_value, form_type
            )
            
            # Create FormField record
            form_field = {
                "field_name": canonical_name,
                "value": normalized_value,  # For database storage
                "ocr_value": normalized_value,  # Raw extraction value
                "confidence": confidence,
                "source": source,  # "glm_ocr"
                "was_corrected": False,
                "unresolved": False,
            }
            
            form_fields.append(form_field)
            
            logger.debug(
                f"[GLM-ADAPTER] {canonical_name}: raw='{raw_value}' → "
                f"normalized='{normalized_value}', confidence={confidence}"
            )
        
        logger.info(
            f"[GLM-ADAPTER] ✓ Adapted {len(form_fields)} fields, "
            f"source='{source}', form_type='{form_type}'"
        )
        
        return form_fields
    
    @staticmethod
    def _normalize_field_value(
        field_name: str,
        raw_value: str,
        form_type: str,
    ) -> str:
        """
        Normalize field value based on field type.
        
        Args:
            field_name: Canonical field name
            raw_value: Raw value from GLM
            form_type: Form type context
            
        Returns:
            Normalized value
        """
        extractor = GLMFieldExtractor()
        
        if not raw_value:
            return ""
        
        raw_value = str(raw_value).strip()
        
        # Checkbox normalization
        if field_name in extractor.CHECKBOX_FIELDS:
            if raw_value.lower() in ("true", "checked", "✓", "x", "yes", "1"):
                return "true"
            elif raw_value.lower() in ("false", "unchecked", "no", "0", ""):
                return "false"
            else:
                return "false"  # Default to unchecked if unclear
        
        # Date normalization
        if field_name in extractor.DATE_FIELDS:
            # Try to parse and reformat date
            # For now, just return as-is; in production, would use dateparser
            return raw_value
        
        # Numeric normalization
        if field_name in extractor.NUMERIC_FIELDS:
            # Remove currency symbols, commas, etc.
            cleaned = "".join(c for c in raw_value if c.isdigit() or c in ".,")
            return cleaned
        
        # Default: return as-is
        return raw_value
