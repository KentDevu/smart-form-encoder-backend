"""Analyze what OCR is capturing for checkbox regions"""
import json
from app.db import SessionLocal
from app.models import FormEntry

db = SessionLocal()
entry = db.query(FormEntry).filter(FormEntry.id == '11630dc4-e1c6-465c-858a-21cd637c76b8').first()

if entry and entry.raw_ocr_data:
    raw_ocr_data = json.loads(entry.raw_ocr_data)
    raw_lines = raw_ocr_data.get("raw_lines", [])
    
    print("\n" + "="*70)
    print("OCR LINE ANALYSIS - Looking for checkbox marks")
    print("="*70)
    
    # Checkbox mark symbols    
    checkbox_marks = {'✓', '✔', '☑', '☐', '○', '●', '■', '█', '[', ']', '(', ')', 'x', 'X'}
    
    # Statistics
    lines_with_marks = []
    lines_with_activity_words = []
    lines_with_brackets = []
    
    # Activity type keywords
    activity_words = {'manufacturer', 'producer', 'service', 'retailer', 'wholesaler', 'importer', 'exporter'}
    
    for i, line in enumerate(raw_lines):
        text = line.get("text", "").strip()
        conf = line.get("confidence", 0)
        
        # Check for checkbox marks
        has_marks = any(mark in text for mark in checkbox_marks)
        
        # Check for activity words
        has_activity = any(activity_word in text.lower() for activity_word in activity_words)
        
        # Check for bracket style
        has_brackets = '[' in text or ']' in text
        
        if has_marks:
            lines_with_marks.append((i, text, conf))
        if has_activity:
            lines_with_activity_words.append((i, text, conf))
        if has_brackets:
            lines_with_brackets.append((i, text, conf))
    
    print(f"\n📊 STATISTICS:")
    print(f"  Total OCR lines: {len(raw_lines)}")
    print(f"  Lines with checkbox marks: {len(lines_with_marks)}")
    print(f"  Lines with activity keywords: {len(lines_with_activity_words)}")
    print(f"  Lines with brackets: {len(lines_with_brackets)}")
    
    if lines_with_marks:
        print(f"\n✓ Lines WITH checkbox marks ({len(lines_with_marks)} total):")
        for idx, (i, text, conf) in enumerate(lines_with_marks[:10]):
            print(f"  {idx+1}. Line {i:3}: \"{text[:60]:60}\" (conf={conf:.2f})")
        if len(lines_with_marks) > 10:
            print(f"  ... and {len(lines_with_marks)-10} more")
    else:
        print(f"\n❌ NO lines with checkbox marks found!")
        
    if lines_with_activity_words:
        print(f"\n🏷️  Lines WITH activity keywords ({len(lines_with_activity_words)} total):")
        for idx, (i, text, conf) in enumerate(lines_with_activity_words[:10]):
            mark_indicator = " ✓" if any(m in text for m in checkbox_marks) else ""
            print(f"  {idx+1}. Line {i:3}: \"{text[:60]:60}\" (conf={conf:.2f}){mark_indicator}")
        if len(lines_with_activity_words) > 10:
            print(f"  ... and {len(lines_with_activity_words)-10} more")
    
    db.close()
    print("\n" + "="*70 + "\n")
