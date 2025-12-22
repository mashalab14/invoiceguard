# ✅ Tiered JSON Structure Implementation - COMPLETE

**Date:** December 22, 2025  
**Status:** Ready for Testing (Phase 5)

## Overview
Successfully implemented "Gold Standard" tiered JSON structure for InvoiceGuard validation errors. All error creation paths now produce structured responses with action guidance, evidence data, and technical details.

---

## ✅ Completed Phases

### Phase 1: Foundation ✅
**File:** `diagnostics/models.py` (NEW)

Created tiered data models:
- `ErrorAction` - User-facing guidance (summary, fix, locations)
- `ErrorEvidence` - Structured data (bt5_value, currency_ids_found, occurrence_count)
- `DebugContext` - Technical details (raw_message, raw_locations)
- `ValidationError` - Complete tiered structure

### Phase 2: Error Creation Logic ✅  
**File:** `main.py`

Updated **10 error creation sites** to use tiered structure:
1. INTERNAL_ERROR (line ~193) - Top-level exception handler
2. INVALID_XML (line ~495) - XML parsing failure
3. TIMEOUT (line ~552) - Validation timeout
4. VALIDATOR_CRASH (line ~588) - Validator crash
5. EXECUTION_ERROR (line ~613) - Execution failure
6. REPORT_MISSING (line ~656) - No report generated
7. MALFORMED_REPORT (line ~688) - Report parsing error
8. SVRL parsing (line ~759) - Initial flat dict creation
9. Humanization (line ~791) - Convert flat → tiered
10. PARSING_MISMATCH (line ~847) - Report/exit code mismatch

### Phase 3: R051 Explainer Enhancement ✅
**File:** `diagnostics/rule_explainers/r051.py`

Enhanced R051 explainer to return structured data:
- Extracts `bt5_value` (DocumentCurrencyCode)
- Extracts `found_currency` (mismatched currencyID)
- Returns `structured_data` dict in all 4 code paths
- Backwards compatible (still returns `humanized_message`)

### Phase 4: Suppression Logic Update ✅
**File:** `main.py` - `_apply_cross_error_suppression()`

Updated suppression to work with tiered structure:
- Modifies `error.action.summary` (not flat message)
- Sets `error.suppressed = True`
- Clean suppression messages for BR-CO-15 errors

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ Data Flow: SVRL → Humanization → Tiered → Dedup → Suppression  │
└─────────────────────────────────────────────────────────────────┘

1. SVRL Parsing → Flat dicts
   {id, message, location, severity}

2. Humanization Pipeline → Enriched flat dicts
   + humanized_message
   + structured_data (R051)
   + suppressed flag

3. convert_flat_to_tiered() → Tiered ValidationError
   ├── action: {summary, fix, locations[]}
   ├── evidence: {bt5_value, currency_ids_found{}, occurrence_count}
   ├── technical_details: {raw_message, raw_locations[]}
   └── suppressed: bool

4. _deduplicate_errors() → Aggregated evidence
   - Groups by error ID
   - Collects all locations
   - Aggregates currency_ids_found: {"EUR": 3, "MMK": 12}
   - Updates occurrence_count

5. _apply_cross_error_suppression() → Marked cascades
   - BR-CO-15 suppressed if R051 present
   - Updates action.summary with suppression note

6. Pydantic Serialization → JSON
   {
     "id": "PEPPOL-EN16931-R051",
     "severity": "error",
     "action": {
       "summary": "Currency Conflict...",
       "fix": "Make BT-5 and currencyID consistent",
       "locations": ["/TaxExclusiveAmount[1]", "/PayableAmount[1]"]
     },
     "evidence": {
       "bt5_value": "EUR",
       "currency_ids_found": {"MMK": 12},
       "occurrence_count": 12
     },
     "technical_details": {
       "raw_message": "Original validator message",
       "raw_locations": ["/cbc:TaxExclusiveAmount[1]", ...]
     },
     "suppressed": false
   }
```

---

## Key Helper Functions

### `clean_xpath(xpath: str)`
Strips namespace prefixes from XPaths:
- `/cbc:TaxExclusiveAmount[1]` → `/TaxExclusiveAmount[1]`
- `/*:Invoice[namespace-uri()='...']` → `/Invoice[1]`

### `convert_flat_to_tiered(flat_error: dict, session_id: str)`
Bridges humanization pipeline (flat) → API response (tiered):
1. Extracts structured_data from R051 explainer
2. Builds ErrorEvidence with currency info
3. Creates ErrorAction with fix guidance
4. Constructs complete tiered ValidationError

### `_deduplicate_errors(errors: List[ValidationError], session_id: str)`
Aggregates repeated errors:
- Groups by error ID
- Collects all unique locations
- Sums currency occurrences: {"EUR": 1} + {"EUR": 1} → {"EUR": 2}
- Updates summary: "Currency Conflict (Repeated 12 times)"

### `_apply_cross_error_suppression(errors: List[ValidationError], session_id: str)`
Suppresses cascade errors:
- If R051 present → suppress BR-CO-15
- Updates action.summary with suppression note
- Maintains suppressed flag for sorting

---

## Example Output

### R051 Currency Mismatch (Repeated 12 times)
```json
{
  "id": "PEPPOL-EN16931-R051",
  "severity": "error",
  "action": {
    "summary": "Currency Conflict. The Document Currency is 'EUR', but this field uses 'MMK'. Please make them consistent. (Repeated 12 times)",
    "fix": "Make BT-5 (DocumentCurrencyCode) and all currencyID attributes consistent. Either change BT-5 to match the amounts, or convert amounts and update currencyID to match BT-5.",
    "locations": [
      "/TaxExclusiveAmount[1]",
      "/TaxInclusiveAmount[1]",
      "/PayableAmount[1]",
      "/LineExtensionAmount[1]",
      "/PriceAmount[1]"
    ]
  },
  "evidence": {
    "bt5_value": "EUR",
    "currency_ids_found": {
      "MMK": 12
    },
    "occurrence_count": 12
  },
  "technical_details": {
    "raw_message": "[BR-51] BT-5 must match all currencyID attributes",
    "raw_locations": [
      "/cbc:TaxExclusiveAmount[1]",
      "/cbc:TaxInclusiveAmount[1]",
      "/cbc:PayableAmount[1]",
      "/cbc:LineExtensionAmount[1]",
      "/cac:Price[1]/cbc:PriceAmount[1]"
    ]
  },
  "suppressed": false
}
```

### BR-CO-15 Math Error (Suppressed)
```json
{
  "id": "BR-CO-15",
  "severity": "error",
  "action": {
    "summary": "Math Error (Suppressed: Likely caused by Currency Mismatch R051)",
    "fix": "Verify that Tax Inclusive Amount (BT-112) = Tax Exclusive Amount (BT-109) + Tax Amount (BT-110).",
    "locations": ["/LegalMonetaryTotal[1]"]
  },
  "evidence": null,
  "technical_details": {
    "raw_message": "Invoice total amount without VAT = Sum of Invoice line net amount + Sum of charges on document level - Sum of allowances on document level.",
    "raw_locations": ["/Invoice[1]/cac:LegalMonetaryTotal[1]"]
  },
  "suppressed": true
}
```

---

## Testing Checklist (Phase 5)

### Basic Validation
- [ ] Test with valid invoice (PASSED status)
- [ ] Test with invalid XML (INVALID_XML error)
- [ ] Test with timeout scenario (TIMEOUT error)

### R051 Currency Mismatch
- [ ] Single R051 error → verify structured_data
- [ ] Multiple R051 (same currency) → verify aggregation
- [ ] Multiple R051 (different currencies) → verify currency_ids_found map
- [ ] R051 + BR-CO-15 → verify BR-CO-15 suppression

### Error Deduplication
- [ ] Repeated errors → verify occurrence_count
- [ ] Repeated errors → verify location aggregation
- [ ] Repeated R051 → verify currency count aggregation

### Error Sorting
- [ ] Active errors appear first
- [ ] Suppressed errors appear last
- [ ] Verify sort order in JSON response

### System Errors
- [ ] VALIDATOR_CRASH → verify tiered structure
- [ ] REPORT_MISSING → verify tiered structure
- [ ] MALFORMED_REPORT → verify tiered structure
- [ ] PARSING_MISMATCH → verify tiered structure

---

## Files Modified

1. **diagnostics/models.py** (NEW)
   - Created tiered data models

2. **diagnostics/rule_explainers/r051.py**
   - Added structured_data to all return paths
   - +40 lines

3. **main.py**
   - Added convert_flat_to_tiered()
   - Rewrote _deduplicate_errors()
   - Updated _apply_cross_error_suppression()
   - Updated 10 error creation sites
   - +200 lines, -100 lines

---

## Next Steps

1. **Run integration tests** to verify end-to-end flow
2. **Test with real invoices** containing R051 errors
3. **Validate JSON output** against "Gold Standard" format
4. **Verify performance** with multiple concurrent validations
5. **Update API documentation** with new response structure

---

## Benefits

✅ **Clear User Guidance** - action.summary + action.fix  
✅ **Structured Evidence** - Parseable data (currency_ids_found)  
✅ **Debug Support** - Raw technical details preserved  
✅ **Deduplication** - Aggregated evidence across instances  
✅ **Suppression** - Cascade errors marked clearly  
✅ **Clean XPaths** - Namespace-free locations for users  

---

**Implementation Status:** ✅ COMPLETE  
**Ready For:** Phase 5 Testing
