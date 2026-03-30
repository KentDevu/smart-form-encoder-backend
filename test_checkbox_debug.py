"""Debug script to analyze checkbox detection on test form"""
import sys
import logging
from pathlib import Path
import os
sys.path.insert(0, str(Path(__file__).parent))
os.environ["SQLALCHEMY_SILENCE_UBER_WARNING"] = "1"

from app.services.ocr_region_classifier import classify_regions
from app.services.ocr_checkbox_detector import detect_checkboxes
from app.db import SessionLocal
from app.models import FormEntry
import json

# Enable detailed logging
logging.basicConfig(
    level=logging.WARNING,
    format='%(name)s - %(levelname)s - %(message)s'
)

entry_id = "7bb37468-590b-4551-bfc5-2f860ddb9bfb"

db = SessionLocal()
entry = db.query(FormEntry).filter(FormEntry.id == entry_id).first()

if not entry or not entry.raw_ocr_data:
    print("❌ No entry or raw OCR data found")
    sys.exit(1)

raw_ocr_data = json.loads(entry.raw_ocr_data)
raw_lines = raw_ocr_data.get("raw_lines", [])

print(f"\n{'='*60}")
print(f"DETAILED CHECKBOX ANALYSIS")
print(f"{'='*60}")
print(f"📋 Total OCR lines: {len(raw_lines)}")

# Step 1: Classify regions
print(f"\n--- STEP 1: Region Classification ---")
regions = classify_regions(raw_lines)
print(f"✅ Classified {len(regions)} regions")
for i, region in enumerate(regions[:5]):
   print(f"   {i+1}. {region.type.value:20} {region.name[:40]:40} ({len(region.lines)} lines)")
if len(regions) > 5:
    print(f"   ... and {len(regions)-5} more")

# Step 2: Detect checkboxes
print(f"\n--- STEP 2: Checkbox Detection ---")
detected_checkboxes = detect_checkboxes(regions=regions, raw_lines=raw_lines, field_schema={})
print(f"✅ Detected {len(detected_checkboxes)} checkboxes")

# Group by state
from collections import Counter
states = Counter(cb.state.value for cb in detected_checkboxes)
print(f"\nCheckbox states distribution:")
for state, count in sorted(states.items()):
    print(f"   {state:12} : {count:3} checkboxes")

# Group by confidence
conf_ranges = {
    "0.0-0.3": sum(1 for cb in detected_checkboxes if 0.0 <= cb.confidence < 0.3),
    "0.3-0.5": sum(1 for cb in detected_checkboxes if 0.3 <= cb.confidence < 0.5),
    "0.5-0.7": sum(1 for cb in detected_checkboxes if 0.5 <= cb.confidence < 0.7),
    "0.7-0.9": sum(1 for cb in detected_checkboxes if 0.7 <= cb.confidence < 0.9),
    "0.9-1.0": sum(1 for cb in detected_checkboxes if 0.9 <= cb.confidence <= 1.0),
}
print(f"\nCheckbox confidence distribution:")
for range_, count in conf_ranges.items():
    print(f"   {range_} : {count:3} checkboxes")

# Show high-confidence checkboxes
high_conf = [cb for cb in detected_checkboxes if cb.confidence >= 0.7]
print(f"\n✅ High-confidence (≥0.7) checkboxes: {len(high_conf)}")
for cb in high_conf[:10]:
    print(f"   • {cb.name:30} {cb.state.value:10} conf={cb.confidence:.2f}")
if len(high_conf) > 10:
    print(f"   ... and {len(high_conf)-10} more")

# Show low-confidence checkboxes  
low_conf = [cb for cb in detected_checkboxes if cb.confidence < 0.7]
print(f"\n⚠️  Low-confidence (<0.7) checkboxes: {len(low_conf)}")
for cb in low_conf[:10]:
    print(f"   • {cb.name:30} {cb.state.value:10} conf={cb.confidence:.2f}")
if len(low_conf) > 10:
    print(f"   ... and {len(low_conf)-10} more")

# Show unclear status checkboxes
unclear = [cb for cb in detected_checkboxes if cb.state.value == "unclear"]
print(f"\n❓ Unclear checkboxes: {len(unclear)}")
for cb in unclear[:5]:
    print(f"   • {cb.name:30} conf={cb.confidence:.2f}")
if len(unclear) > 5:
    print(f"   ... and {len(unclear)-5} more")

# Show checked checkboxes
checked = [cb for cb in detected_checkboxes if cb.state.value == "checked"]
print(f"\n✓ Checked checkboxes: {len(checked)}")
for cb in checked[:10]:
    print(f"   • {cb.name:30} conf={cb.confidence:.2f}")
if len(checked) > 10:
    print(f"   ... and {len(checked)-10} more")

print(f"\n{'='*60}\n")
db.close()
