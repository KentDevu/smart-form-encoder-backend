from app.services.forms.template_schema import normalize_template_schema


def test_normalize_template_schema_injects_extraction_defaults():
    schema = {
        "fields": [
            {"name": "business_name", "label": "Business Name", "type": "text"},
        ]
    }

    normalized = normalize_template_schema(schema)
    field = normalized["fields"][0]

    assert "extraction" in field
    assert field["extraction"]["strategy"] == "label_nearby"
    assert field["extraction"]["search_region"]["x_min"] == 0.0
    assert field["extraction"]["search_region"]["x_max"] == 1.0


def test_normalize_template_schema_rejects_invalid_strategy():
    schema = {
        "fields": [
            {
                "name": "business_name",
                "label": "Business Name",
                "type": "text",
                "extraction": {"strategy": "unsupported_strategy"},
            },
        ]
    }

    try:
        normalize_template_schema(schema)
        assert False, "Expected ValueError for unsupported strategy"
    except ValueError as exc:
        assert "unsupported strategy" in str(exc)
