# DTI BNR Extraction Error Analysis

## Overview
Current DTI BNR extraction: 19/55 fields (34.5%), avg confidence 0.21

## Identified OCR Errors (from actual form)

### 1. Character Misidentification
- **Pattern:** Numbers ↔ Letters
- **Examples:**
  - "I" (letter) → "1" (number) and vice versa
  - "O" (letter) → "0" (number) and vice versa
  - "Z" (letter) → "2" (number)
  - "S" (letter) → "5" (number)
  - "l" (lowercase L) → "1" (number)

### 2. Name Fields
- **Current:** "Marte" (0.63), "Dereny" (0.52), "mir" (0.62)
- **Issue:** Contains OCR artifacts; expected format: [First] [Middle] [Last]
- **Action:** Validate against expected patterns, flag unusual characters

### 3. Date of Birth Fields
- **Current (broken):** year="198" (0.83), month="I5", day="Sngir" (0.62)
- **Expected Format:** YYYY-MM-DD or MM/DD/YYYY
- **Common Issues:**
  - Incomplete year (198 instead of 1985/1990)
  - Letter/number confusion in month (I5 = 15?)
  - Non-numeric characters in day
- **Action:** Infer missing year digits, map letter→number, validate ranges

### 4. Phone Numbers
- **Current:** "091-123496" (0.53)
- **Expected Format:** +639XX, 09XX, (+63)9XX
- **Common Issues:**
  - Non-numeric characters beyond formatting
  - Missing digits
  - Wrong area codes
- **Action:** Validate format, extract digits, check length

### 5. Address Fields
- **Current:** "Bontlcoreel" (street), "Baraneay san kadio" (barangay)
- **Expected:** [House/Building] [Street] [Barangay] [City/Municipality]
- **Common Issues:**
  - Abbreviation inconsistency (Brgy, Brgy., Barangay)
  - Misspellings in place names
  - OCR misreads "Barangay" → "Baraneay"
- **Action:** Match against known city/barangay databases, fuzzy matching

### 6. Amount/Currency Fields
- **Current:** "(00,090.00" (0.78)
- **Expected Format:** ₱5,000, P5000, 5,000.00
- **Common Issues:**
  - Missing opening paren vs actual digit: ( vs [
  - Thousand separator placement
  - Currency symbol variations
- **Action:** Extract digits, remove formatting, validate numeric ranges

### 7. PSIC Code
- **Current:** "Iot ar olitood; oewages" (0.58)
- **Expected:** 5-digit code (e.g., 01011, 47191)
- **Issue:** Completely garbled; needs better extraction or lookup
- **Action:** Attempt pattern matching, fall back to manual entry flag

## Error Patterns by Field Type

| Field Type | Error Pattern | Confidence Impact | Fix Strategy |
|-----------|---------------|-------------------|--------------|
| Text (name, address) | Letter↔Number confusion | -0.15 to -0.25 | Fuzzy matching, dictionaries |
| Phone | Format mismatch | -0.10 to -0.20 | Regex validation, digit extraction |
| Amount | Bracket/paren confusion, separators | -0.20 to -0.30 | Regex for numeric extraction |
| Date | Incomplete/mixed alphanumeric | -0.25 to -0.40 | Year inference, letter→digit mapping |
| Code (PSIC) | Severe garbling | -0.30 to -0.50 | Pattern matching or business logic |

## Correction Rules to Implement

### R1: Letter↔Number Substitution
```
Corrections:
  I → 1, l → 1, O → 0, Z → 2, S → 5
  Apply in specific contexts (year, month, ID codes)
  Not in names/addresses
```

### R2: Phone Number Validation
```
Format: 09XX-XXXXXX or +639XX-XXXX or (0)9XX-XXXX
Extract digits, validate length (10-12), format as 09XX-XXXXXX
```

### R3: Date Inference
```
Year: If < 100, assume 19XX or 20XX based on context
Month: Map I→1, S→5, validate 1-12 range
Day: Remove letters, validate 1-31 range
```

### R4: Amount Parsing
```
Remove all non-numeric except . and commas
Map ( → nothing (bracket misread)
Extract numeric value, validate ≥ 0
```

### R5: Address Parsing
```
Split by keywords: Brgy/Barangay, St/Street, Mun/Municipality, Prov/Province
Match against PH administrative boundaries (fuzzy match)
Flag suspicious entries
```

## DTI BNR Specific Field Adjustments

| Field | Current Confidence | Expected After Fix | Rule Applied |
|-------|-------------------|-------------------|--------------|
| certificate_no | 0.58 | 0.90 | Digit validation |
| first_name | 0.63 | 0.75 | Fuzzy dict match |
| last_name | 0.62 | 0.80 | Fuzzy dict match |
| dob_year | 0.83 | 0.90 | Year inference |
| dob_month | 0.51 | 0.75 | Letter→digit + range |
| biz_phone | 0.53 | 0.80 | Phone validation |
| biz_barangay | 0.62 | 0.75 | City/Barangay dict |
| capitalization | 0.78 | 0.85 | Numeric extraction |

## Implementation Order

1. **R1:** Letter↔Number (universal, ~5 mins)
2. **R2:** Phone validation (~10 mins)
3. **R3:** Date inference (~15 mins)
4. **R4:** Amount parsing (~10 mins)
5. **R5:** Address parsing (~20 mins, requires reference data)

**Estimated total:** ~60 minutes for all rules + tests
