# ML Training Pipeline — Colab Notebooks

> Google Colab-based ML training pipeline for improving OCR accuracy on Philippine City Hall forms.

## Feedback Loop

```
Upload Form → OCR Extract → Human Verify → Corrections = Training Data → Fine-tune Models → Better OCR
```

## Notebooks

| # | Notebook | Purpose | Status |
|---|---|---|---|
| 01 | [01_data_export](01_data_export.ipynb) | Export verified entries from DB/API as training dataset | **Ready** |
| 02 | [02_preprocessing_experiments](02_preprocessing_experiments.ipynb) | Test deskew, denoise, binarization, contrast | Placeholder |
| 03 | [03_layout_detection](03_layout_detection.ipynb) | Train YOLOv8 for field region detection | Placeholder |
| 04 | [04_ocr_finetuning](04_ocr_finetuning.ipynb) | Fine-tune PaddleOCR on PH handwriting | Placeholder |
| 05 | [05_field_mapping_model](05_field_mapping_model.ipynb) | Train LayoutLMv3 for field classification | Placeholder |
| 06 | [06_post_correction](06_post_correction.ipynb) | Text correction for Filipino/English names | Placeholder |
| 07 | [07_evaluation](07_evaluation.ipynb) | Benchmark: field accuracy, CER, WER per template | **Ready** |

## Quick Start

1. Deploy the SmartForm API with some verified form entries
2. Open `01_data_export.ipynb` in Google Colab
3. Configure your API URL and admin credentials
4. Run all cells to download the training dataset
5. Open `07_evaluation.ipynb` to establish your accuracy baseline
6. Use the baseline to identify which forms/fields need the most improvement

## API Endpoints

The backend provides three ML-specific endpoints (admin only):

| Endpoint | Description |
|---|---|
| `GET /api/v1/ml/export-training-data` | Export verified entries with OCR vs verified field data |
| `GET /api/v1/ml/training-stats` | Summary statistics about available training data |
| `GET /api/v1/ml/evaluation` | Accuracy metrics for the current OCR pipeline |

## Models Being Trained

| Model | Purpose | Replaces |
|---|---|---|
| Fine-tuned PaddleOCR | PH handwriting recognition | Generic PaddleOCR |
| YOLOv8 | Field region detection | Manual template regions |
| LayoutLMv3 | Field classification (text + layout → field) | Groq/LLM API calls |
| T5 / Rule-based | Post-OCR text correction | New capability |

## Evaluation Targets

| Metric | Target |
|---|---|
| Field Accuracy | > 85% |
| Character Error Rate (CER) | < 5% |
| Word Error Rate (WER) | < 10% |
| Correction Rate | < 15% |
