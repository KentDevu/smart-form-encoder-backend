from app.services.forms.template_field_extractor import extract_fields_with_template_map


def test_extract_fields_with_template_map_label_nearby():
    raw_lines = [
        {
            "text": "Business Name: ACME Trading",
            "confidence": 0.92,
            "bbox": [[10, 10], [300, 10], [300, 40], [10, 40]],
        },
        {
            "text": "Owner Name",
            "confidence": 0.90,
            "bbox": [[10, 60], [160, 60], [160, 90], [10, 90]],
        },
        {
            "text": "Juan Dela Cruz",
            "confidence": 0.88,
            "bbox": [[180, 60], [360, 60], [360, 90], [180, 90]],
        },
    ]
    schema = {
        "fields": [
            {
                "name": "business_name",
                "label": "Business Name",
                "type": "text",
                "extraction": {"anchor_labels": ["Business Name"]},
            },
            {
                "name": "owner_name",
                "label": "Owner Name",
                "type": "text",
                "extraction": {"anchor_labels": ["Owner Name"]},
            },
        ]
    }

    result = extract_fields_with_template_map(raw_lines=raw_lines, field_schema=schema)
    assert result["business_name"]["value"] == "ACME Trading"
    assert result["owner_name"]["value"] == "Juan Dela Cruz"
    assert result["business_name"]["source"] == "deterministic"
    assert result["business_name"]["unresolved"] is False


def test_extract_fields_with_template_map_marks_unresolved():
    raw_lines = []
    schema = {
        "fields": [
            {
                "name": "business_name",
                "label": "Business Name",
                "type": "text",
                "extraction": {"anchor_labels": ["Business Name"]},
            }
        ]
    }
    result = extract_fields_with_template_map(raw_lines=raw_lines, field_schema=schema)
    assert result["business_name"]["value"] == ""
    assert result["business_name"]["unresolved"] is True
