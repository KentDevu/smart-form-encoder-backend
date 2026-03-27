from unittest.mock import MagicMock

from app.services.ocr_unified import extract_fields_unified


def test_extract_fields_unified_only_resolves_unresolved_fields():
    client = MagicMock()
    completion = MagicMock()
    completion.choices = [MagicMock(message=MagicMock(content='{"fields":{"owner_name":{"value":"Juan","confidence":0.87}}}'))]
    client.chat.completions.create.return_value = completion

    field_schema = {
        "fields": [
            {"name": "business_name", "label": "Business Name", "type": "text"},
            {"name": "owner_name", "label": "Owner Name", "type": "text"},
        ]
    }
    deterministic_results = {
        "business_name": {"value": "ACME", "confidence": 0.9, "unresolved": False},
        "owner_name": {"value": "", "confidence": 0.0, "unresolved": True},
    }
    ocr_result = {"raw_lines": [], "full_text": "Owner Name: Juan"}

    result = extract_fields_unified(
        client=client,
        field_schema=field_schema,
        ocr_result=ocr_result,
        unresolved_field_names=["owner_name"],
        deterministic_results=deterministic_results,
        model="test-model",
    )

    assert "owner_name" in result
    assert result["owner_name"]["value"] == "Juan"
    create_call = client.chat.completions.create.call_args.kwargs
    assert create_call["model"] == "test-model"
