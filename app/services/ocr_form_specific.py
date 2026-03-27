"""Form-specific OCR optimization.

Detects form type and applies optimized extraction per form layout.
Currently optimized for DTI Business Name Registration form.
"""

import cv2
import numpy as np
import logging
from typing import Literal, Any

logger = logging.getLogger(__name__)

# DTI Form constants (based on standard Philippine DTI BNR form)
DTI_BNR_FORM_REGIONS = {
    # Section A: Type of DTI Registration
    'reg_type_section': {
        'name': 'reg_type',
        'bounds': (0.0, 0.03, 1.0, 0.12),  # Relative bounds (top, left, bottom, right)
        'field_labels': ['NEW', 'RENEWAL', 'AMENDMENT'],
        'type': 'checkbox_group',
    },
    # Section B: Tax ID Number
    'tin_section': {
        'name': 'tin_section',
        'bounds': (0.08, 0.0, 0.25, 1.0),
        'field_labels': ['TIN', 'TAX', 'ID'],
        'type': 'text_block',
    },
    # Section C: Owner Information
    'owner_section': {
        'name': 'owner_info',
        'bounds': (0.20, 0.0, 0.45, 1.0),
        'field_labels': ['FIRST NAME', 'MIDDLE NAME', 'LAST NAME', 'SUFFIX'],
        'type': 'form_fields',
    },
    # Section D: Business Scope
    'business_scope': {
        'name': 'business_scope',
        'bounds': (0.30, 0.0, 0.50, 1.0),
        'field_labels': ['BARANGAY', 'CITY', 'REGIONAL'],
        'type': 'checkbox_group',
    },
    # Section E: Proposed Business Names
    'business_names': {
        'name': 'business_names',
        'bounds': (0.45, 0.0, 0.70, 1.0),
        'field_labels': ['BUSINESS NAME', 'FIRST', 'SECOND', 'THIRD'],
        'type': 'text_block',
    },
    # Section F: Business Details
    'business_details': {
        'name': 'business_details',
        'bounds': (0.60, 0.0, 0.85, 1.0),
        'field_labels': ['STREET', 'BARANGAY', 'CITY', 'PROVINCE'],
        'type': 'form_fields',
    },
    # Section G: PSIC and Activities
    'activities_section': {
        'name': 'activities_section',
        'bounds': (0.75, 0.0, 0.95, 1.0),
        'field_labels': ['MANUFACTURER', 'SERVICE', 'RETAILER', 'IMPORTER'],
        'type': 'checkbox_group',
    },
}


def detect_form_type(img_array: np.ndarray) -> Literal['dti_bnr', 'barangay_clearance', 'community_tax', 'unknown']:
    """
    Detect form type from image using multiple strategies:
    1. Header text matching (top 30%)
    2. Form structure analysis (look for DTI-specific field labels)
    3. Visual similarity patterns
    
    Returns:
        Form type identifier (dti_bnr, barangay_clearance, community_tax, unknown)
    """
    if img_array is None or img_array.size == 0:
        logger.warning("Form detection: invalid image")
        return 'unknown'
    
    try:
        from app.services.ocr_service import _get_paddle_ocr
        ocr = _get_paddle_ocr()
        
        h, w = img_array.shape[:2]
        
        # Strategy 1: Check multiple horizontal bands for form keywords
        # (form headers might not always be at very top)
        search_regions = [
            (0.0, 0.15, "top_region"),      # Top 15%
            (0.15, 0.30, "upper_region"),   # 15-30%
            (0.30, 0.50, "middle_region"),  # 30-50% (some forms have header here)
        ]
        
        all_text = ""
        for start_frac, end_frac, region_name in search_regions:
            y1 = int(start_frac * h)
            y2 = int(end_frac * h)
            region = img_array[y1:y2, 0:w]
            
            result = ocr.ocr(region)
            region_text = ""
            if result and result[0]:
                for line in result[0]:
                    region_text += line[1][0].lower() + " "
            
            all_text += region_text + " "
            logger.debug(f"[FORM-DETECT] {region_name}: {region_text[:80]}")
        
        # Strategy 2: Match keywords with confidence scoring
        keywords = {
            'dti_bnr': [
                ('business name', 1.0),
                ('dti', 1.0),
                ('registration', 0.8),
                ('new renewal', 0.7),
                ('barangay', 0.6),
                ('tin', 0.6),
            ],
            'barangay_clearance': [
                ('barangay clearance', 1.0),
                ('barangay', 0.8),
                ('clearance', 0.9),
            ],
            'community_tax': [
                ('community tax', 1.0),
                ('cedula', 1.0),
                ('tax certificate', 0.9),
            ],
        }
        
        # Score each form type
        scores = {}
        for form_type, keywords_list in keywords.items():
            score = 0.0
            for keyword, weight in keywords_list:
                if keyword in all_text:
                    score += weight
                    logger.debug(f"[FORM-DETECT] Found '{keyword}' for {form_type} (+{weight})")
            scores[form_type] = score
        
        # Find best match
        best_form = max(scores, key=scores.get)
        best_score = scores[best_form]
        
        logger.info(
            f"[FORM-DETECT] Score summary: DTI={scores.get('dti_bnr', 0):.1f}, "
            f"Barangay={scores.get('barangay_clearance', 0):.1f}, "
            f"CTC={scores.get('community_tax', 0):.1f}"
        )
        
        # Decision logic
        if best_score >= 1.5:
            logger.info(f"[FORM-DETECT] High confidence: {best_form} (score={best_score:.1f})")
            return best_form
        elif best_score >= 0.8:
            logger.info(f"[FORM-DETECT] Medium confidence: {best_form} (score={best_score:.1f})")
            return best_form
        else:
            logger.warning(f"[FORM-DETECT] Low confidence, defaulting to unknown (best={best_form}, score={best_score:.1f})")
            logger.debug(f"[FORM-DETECT] Scanned text samples: {all_text[:200]}")
            return 'unknown'
            
    except Exception as e:
        logger.error(f"Form detection failed: {e}", exc_info=True)
        return 'unknown'


def preprocess_dti_bnr_image(img_array: np.ndarray) -> np.ndarray:
    """
    DTI Business Name Registration form-specific preprocessing.
    
    DTI forms typically have:
    - Printed form with handwritten values
    - Complex multi-column layout
    - Checkboxes and structured fields
    - Black text on white background
    
    Strategy:
    1. Increase contrast (adaptive histogram equalization)
    2. Denoising (clean up scanner artifacts)
    3. Deskew if needed
    4. Light morphological operations to connect characters
    """
    if img_array is None or img_array.size == 0:
        logger.warning("DTI preprocessing: invalid image")
        return img_array
    
    try:
        # Convert to grayscale
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
        else:
            gray = img_array.copy()
        
        # 1. MODERATE CLAHE (balance between standard + detection needs)
        # Lower clipLimit than standard to avoid over-enhancement
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        logger.debug("[DTI-PREP] Applied moderate CLAHE contrast enhancement")
        
        # 2. BILATERAL DENOISING (moderate - preserve text edges)
        denoised = cv2.bilateralFilter(enhanced, 9, 75, 75)
        logger.debug("[DTI-PREP] Applied bilateral denoising")
        
        # 3. DESKEW detection (light - only for obvious skew)
        try:
            edges = cv2.Canny(denoised, 50, 150)
            lines = cv2.HoughLinesP(
                edges, 1, np.pi/180, 100,
                minLineLength=100, maxLineGap=10
            )
            
            if lines is not None:
                angles = []
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    angle = np.arctan2(y2-y1, x2-x1) * 180 / np.pi
                    if abs(angle) < 45:
                        angles.append(angle)
                
                if angles:
                    median_angle = np.median(angles)
                    if abs(median_angle) > 2:  # Only if skew > 2 degrees
                        h, w = denoised.shape
                        center = (w//2, h//2)
                        matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
                        denoised = cv2.warpAffine(
                            denoised, matrix, (w, h),
                            borderMode=cv2.BORDER_REPLICATE
                        )
                        logger.debug(f"[DTI-PREP] Deskewed by {median_angle:.1f}°")
        except Exception as e:
            logger.debug(f"[DTI-PREP] Deskew skipped: {e}")
        
        # 4. LIGHT MORPHOLOGICAL CLOSING (connect nearby text strokes)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        morph = cv2.morphologyEx(denoised, cv2.MORPH_CLOSE, kernel, iterations=1)
        logger.debug("[DTI-PREP] Applied light morphological closing")
        
        return morph
        
    except Exception as e:
        logger.error(f"DTI preprocessing failed: {e}, returning original image")
        return img_array


def extract_field_from_region(
    img_array: np.ndarray,
    region_bounds: tuple[float, float, float, float],  # top, left, bottom, right (relative 0.0-1.0)
    field_name: str,
) -> dict[str, Any]:
    """
    Extract text from a specific form region.
    
    Args:
        img_array: Image array
        region_bounds: Relative bounds (top, left, bottom, right)
        field_name: Name of field for logging
        
    Returns:
        {"text": str, "confidence": float, "raw_lines": list}
    """
    if img_array is None or img_array.size == 0:
        return {"text": "", "confidence": 0.0, "raw_lines": []}
    
    try:
        h, w = img_array.shape[:2]
        top, left, bottom, right = region_bounds
        
        # Convert relative bounds to pixel coords
        y1 = int(top * h)
        x1 = int(left * w)
        y2 = int(bottom * h)
        x2 = int(right * w)
        
        # Crop region
        region = img_array[y1:y2, x1:x2]
        
        if region is None or region.size == 0:
            logger.warning(f"[DTI-EXTRACT] Empty region for {field_name}")
            return {"text": "", "confidence": 0.0, "raw_lines": []}
        
        # Run OCR on cropped region
        from app.services.ocr_service import _get_paddle_ocr
        ocr = _get_paddle_ocr()
        result = ocr.ocr(region)
        
        raw_lines = []
        full_text = ""
        total_conf = 0.0
        
        if result and result[0]:
            for line in result[0]:
                text = line[1][0]
                confidence = float(line[1][1])
                raw_lines.append({
                    "text": text,
                    "confidence": confidence,
                })
                full_text += text + " "
                total_conf += confidence
            
            avg_confidence = total_conf / len(raw_lines) if raw_lines else 0.0
        else:
            avg_confidence = 0.0
        
        result_dict = {
            "text": full_text.strip(),
            "confidence": avg_confidence,
            "raw_lines": raw_lines,
        }
        
        logger.info(f"[DTI-EXTRACT] {field_name}: '{full_text.strip()[:50]}' (conf={avg_confidence:.2f})")
        return result_dict
        
    except Exception as e:
        logger.error(f"Field extraction failed for {field_name}: {e}")
        return {"text": "", "confidence": 0.0, "raw_lines": []}


def extract_all_dti_bnr_regions(img_array: np.ndarray) -> dict[str, dict[str, Any]]:
    """
    Extract all major sections from DTI BNR form as separate regions.
    
    Returns:
        {section_name: {extracted fields dict}}
        
    This allows model to see structured form data (section by section)
    rather than jumbled text that confuses AI extraction.
    """
    logger.info("[DTI-EXTRACT] Starting region-based extraction for DTI BNR form")
    
    results = {}
    for region_name, region_def in DTI_BNR_FORM_REGIONS.items():
        results[region_name] = extract_field_from_region(
            img_array,
            region_def['bounds'],
            region_name,
        )
    
    return results
