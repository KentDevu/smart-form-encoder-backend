"""
GLM-OCR Service - Vision-Language Model for Document Field Extraction

This service replaces the previous multi-pass Paddle OCR pipeline with a single,
unified GLM-OCR model that performs document understanding and field extraction
directly via prompts.

Architecture:
- Load GLM-OCR model once at startup (cached in memory)
- For each form: send image + JSON schema prompt → get structured JSON output
- Parse JSON output to extract field values
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

import torch
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor

logger = logging.getLogger(__name__)


class GLMOCRService:
    """
    Unified OCR service using GLM-OCR model for document field extraction.
    
    Replaces: PaddleOCR (Pass1 + Pass2), Groq Fallback, Checkbox Detection
    """
    
    _instance: Optional["GLMOCRService"] = None
    _model = None
    _processor = None
    
    def __init__(self, model_path: str):
        """
        Initialize GLM-OCR service.
        
        Args:
            model_path: Path to GLM-OCR model directory
        
        Raises:
            FileNotFoundError: If model path doesn't exist
            RuntimeError: If model loading fails
        """
        model_path_obj = Path(model_path)
        if not model_path_obj.exists():
            raise FileNotFoundError(f"GLM-OCR model not found at {model_path}")
        
        logger.info(f"Initializing GLM-OCR service from {model_path}")
        
        try:
            # Load processor (tokenizer + image processor)
            logger.debug("Loading GLM-OCR processor...")
            self._processor = AutoProcessor.from_pretrained(
                model_path,
                trust_remote_code=True,
            )
            
            # Load model
            logger.debug("Loading GLM-OCR model...")
            self._model = AutoModelForImageTextToText.from_pretrained(
                model_path,
                torch_dtype="auto",
                device_map="auto",
                trust_remote_code=True,
            )
            
            logger.info(f"✓ GLM-OCR model loaded successfully")
            logger.debug(f"  Model dtype: {self._model.dtype}")
            logger.debug(f"  Device: {self._model.device}")
            
        except Exception as e:
            logger.error(f"Failed to load GLM-OCR model: {e}")
            raise RuntimeError(f"GLM-OCR model initialization failed: {e}") from e
    
    @classmethod
    def get_instance(cls, model_path: Optional[str] = None) -> "GLMOCRService":
        """
        Singleton accessor - ensures only one model instance in memory.
        
        Args:
            model_path: Required on first call, ignored on subsequent calls
            
        Returns:
            Singleton GLMOCRService instance
        """
        if cls._instance is None:
            if model_path is None:
                raise ValueError("model_path required for initial instantiation")
            cls._instance = cls(model_path)
        return cls._instance
    
    async def extract_fields_from_image(
        self,
        image_path: str,
        field_schema: dict[str, str],
        form_type: str = "generic",
    ) -> list[dict[str, Any]]:
        """
        Extract structured fields from document image using GLM-OCR.
        
        Args:
            image_path: Path to form image file
            field_schema: Dict mapping field_name → field_description
                         Example: {"first_name": "Owner's first name", "date_of_birth": "DOB (YYYY-MM-DD)"}
            form_type: Form type for context (e.g., "dti_bnr")
            
        Returns:
            List of field dicts: [{"field_name": "...", "value": "...", "confidence": 0.9}, ...]
            
        Raises:
            FileNotFoundError: If image not found
            ValueError: If JSON parsing fails
            RuntimeError: If GLM inference fails
        """
        image_path_obj = Path(image_path)
        if not image_path_obj.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        try:
            # Load image
            logger.debug(f"Loading image: {image_path}")
            image = Image.open(image_path).convert("RGB")
            logger.debug(f"Image size: {image.size}")
            
            # Build JSON schema prompt (use English for Filipino form context)
            json_schema = self._build_json_schema(field_schema)
            prompt = self._build_extraction_prompt(form_type, json_schema)
            
            logger.debug(f"[GLM-OCR] Form type: {form_type}, Fields: {len(field_schema)}")
            logger.debug(f"[GLM-OCR] Prompt length: {len(prompt)} chars")
            
            # Prepare GLM-OCR inference input
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "image": image,
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ]
            
            # Run inference
            logger.debug("[GLM-OCR] Running inference...")
            with torch.no_grad():
                inputs = self._processor.apply_chat_template(
                    messages,
                    tokenize=True,
                    add_generation_prompt=True,
                    return_dict=True,
                    return_tensors="pt",
                )
                inputs.pop("token_type_ids", None)
                inputs = {k: v.to(self._model.device) for k, v in inputs.items()}
                
                generated_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=8192,
                    do_sample=False,
                    temperature=0.0,  # Deterministic for structured output
                )
                
                output_text = self._processor.decode(
                    generated_ids[0][inputs["input_ids"].shape[1] :],
                    skip_special_tokens=False,
                )
            
            logger.debug(f"[GLM-OCR] Raw output length: {len(output_text)} chars")
            logger.debug(f"[GLM-OCR] Output preview: {output_text[:200]}...")
            
            # Parse JSON from output
            extracted_fields = self._parse_glm_output(output_text, field_schema)
            
            logger.info(
                f"[GLM-OCR] ✓ Extraction complete: {len(extracted_fields)} fields extracted"
            )
            
            return extracted_fields
            
        except Exception as e:
            logger.error(f"[GLM-OCR] Extraction failed: {e}", exc_info=True)
            raise RuntimeError(f"GLM-OCR extraction failed: {e}") from e
    
    def _build_json_schema(self, field_schema: dict[str, str]) -> str:
        """
        Build JSON schema string for GLM-OCR prompt.
        
        Args:
            field_schema: Mapping of field_name → description
            
        Returns:
            JSON schema as string
        """
        schema = {}
        for field_name, field_desc in field_schema.items():
            schema[field_name] = ""
        
        return json.dumps(schema, indent=2, ensure_ascii=False)
    
    def _build_extraction_prompt(self, form_type: str, json_schema: str) -> str:
        """
        Build extraction prompt for GLM-OCR.
        
        Uses structured prompt format that GLM-OCR recognizes for information extraction.
        
        Args:
            form_type: Type of form (e.g., "dti_bnr", "cedula")
            json_schema: JSON schema string defining fields to extract
            
        Returns:
            Formatted prompt text
        """
        if form_type == "dti_bnr":
            context = (
                "This is a DTI (Department of Trade and Industry) Business Name Registration form "
                "from the Philippines. Extract all field values exactly as they appear in the form."
            )
        else:
            context = "Extract all field values exactly as they appear in the form."
        
        prompt = f"""{context}

Output the extracted data as valid JSON matching this schema (fill in values from the image):

{json_schema}

IMPORTANT:
- For checkboxes, use "true" if checked/marked, "false" if unchecked, empty string if not visible
- For text fields, extract the exact text visible in the form
- For dates, use YYYY-MM-DD format if possible
- Leave empty strings for fields that are not visible or cannot be read
- Return ONLY valid JSON, no additional text
"""
        
        return prompt
    
    def _parse_glm_output(
        self,
        output_text: str,
        field_schema: dict[str, str],
    ) -> list[dict[str, Any]]:
        """
        Parse JSON output from GLM-OCR model.
        
        Extracts JSON, handles formatting issues, and converts to field records.
        
        Args:
            output_text: Raw model output text
            field_schema: Original field schema for validation
            
        Returns:
            List of field dicts with name, value, confidence
            
        Raises:
            ValueError: If JSON cannot be parsed
        """
        # Extract JSON from output (may be wrapped in markdown code blocks)
        json_str = output_text.strip()
        
        # Remove markdown code block if present
        if json_str.startswith("```"):
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", json_str, re.DOTALL)
            if match:
                json_str = match.group(1)
        
        # Remove any leading non-JSON characters
        json_start = json_str.find("{")
        if json_start > 0:
            json_str = json_str[json_start:]
        
        # Parse JSON
        try:
            logger.debug(f"[GLM-PARSE] Parsing JSON, length: {len(json_str)}")
            extracted_dict = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"[GLM-PARSE] JSON parse failed: {e}")
            logger.error(f"[GLM-PARSE] Output text: {json_str[:500]}")
            raise ValueError(f"Failed to parse GLM-OCR output as JSON: {e}") from e
        
        # Convert to field records
        field_records = []
        for field_name, field_value in extracted_dict.items():
            # Normalize checkbox values
            if isinstance(field_value, str):
                if field_value.lower() in ("true", "checked", "✓", "x", "yes"):
                    normalized_value = "true"
                elif field_value.lower() in ("false", "unchecked", "", "no"):
                    normalized_value = field_value if field_value else ""
                else:
                    normalized_value = field_value
            else:
                normalized_value = str(field_value) if field_value else ""
            
            # Estimate confidence based on whether field is empty
            confidence = 0.85 if normalized_value else 0.0
            
            field_records.append({
                "field_name": field_name,
                "value": normalized_value,
                "confidence": confidence,
                "source": "glm_ocr",  # Source attribution
            })
            
            logger.debug(
                f"[GLM-PARSE] {field_name}: value='{normalized_value}', "
                f"confidence={confidence}"
            )
        
        logger.info(f"[GLM-PARSE] ✓ Parsed {len(field_records)} fields from JSON")
        
        return field_records
