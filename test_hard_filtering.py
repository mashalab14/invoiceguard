#!/usr/bin/env python3
"""
Test hard filtering to verify SHORT, BALANCED, and DETAILED modes produce distinct outputs.
"""
import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from diagnostics.models import (
    ValidationResponse, ValidationMeta, ValidationError, 
    ErrorAction, ErrorEvidence, DebugContext, OutputMode
)
from diagnostics.presentation import apply_mode_filter


def create_test_response():
    """Create a test ValidationResponse with full data."""
    return ValidationResponse(
        status="REJECTED",
        meta=ValidationMeta(
            engine="KoSIT 1.5.0",
            rules_tag="release-3.0.18",
            commit="abc123"
        ),
        errors=[
            ValidationError(
                id="PEPPOL-EN16931-R051",
                severity="error",
                action=ErrorAction(
                    summary="Currency Conflict detected",
                    fix="Make BT-5 and currencyID consistent",
                    locations=[
                        "/Invoice[1]/TaxExclusiveAmount[1]",
                        "/Invoice[1]/TaxInclusiveAmount[1]",
                        "/Invoice[1]/PayableAmount[1]",
                        "/Invoice[1]/LineExtensionAmount[1]",
                        "/Invoice[1]/PriceAmount[1]"
                    ]
                ),
                evidence=ErrorEvidence(
                    bt5_value="EUR",
                    currency_ids_found={"USD": 5},
                    occurrence_count=5
                ),
                technical_details=DebugContext(
                    raw_message="[BR-51] BT-5 must match currencyID",
                    raw_locations=[
                        "/cbc:TaxExclusiveAmount[1]",
                        "/cbc:TaxInclusiveAmount[1]"
                    ]
                ),
                suppressed=False
            ),
            ValidationError(
                id="BR-CO-15",
                severity="error",
                action=ErrorAction(
                    summary="Math Error (Suppressed: likely caused by R051)",
                    fix="Verify tax calculations",
                    locations=["/Invoice[1]/LegalMonetaryTotal[1]"]
                ),
                evidence=None,
                technical_details=DebugContext(
                    raw_message="Invoice total mismatch",
                    raw_locations=["/cac:LegalMonetaryTotal[1]"]
                ),
                suppressed=True
            )
        ],
        debug_log="Debug information here"
    )


def test_mode(mode: OutputMode, mode_name: str):
    """Test a specific mode and verify output structure."""
    print(f"\n{'='*70}")
    print(f"Testing {mode_name} mode")
    print(f"{'='*70}")
    
    response = create_test_response()
    filtered = apply_mode_filter(mode, response)
    
    # Print JSON output
    print(f"\nJSON Output:")
    print(json.dumps(filtered, indent=2))
    
    # Verify structure
    print(f"\n{'='*70}")
    print(f"Verification for {mode_name} mode:")
    print(f"{'='*70}")
    
    checks = []
    
    # Common checks
    checks.append(("status" in filtered, "Has 'status' field"))
    checks.append(("meta" in filtered, "Has 'meta' field"))
    checks.append(("diagnosis" in filtered, "Has 'diagnosis' field"))
    checks.append(("errors" not in filtered, "'errors' field NOT present (should be 'diagnosis')"))
    
    if mode == OutputMode.SHORT:
        # SHORT mode checks
        checks.append((len(filtered["diagnosis"]) == 1, "Only 1 error (suppressed filtered out)"))
        
        if filtered["diagnosis"]:
            item = filtered["diagnosis"][0]
            checks.append(("id" in item, "Has 'id'"))
            checks.append(("summary" in item, "Has 'summary'"))
            checks.append(("fix" in item, "Has 'fix'"))
            checks.append(("action" not in item, "NO 'action' nested object"))
            checks.append(("evidence" not in item, "NO 'evidence'"))
            checks.append(("locations" not in item, "NO 'locations'"))
            checks.append(("technical_details" not in item, "NO 'technical_details'"))
            checks.append(("suppressed" not in item, "NO 'suppressed'"))
            checks.append((len(item) == 3, f"Exactly 3 keys (got {len(item)})"))
        
        checks.append(("debug_log" not in filtered, "NO 'debug_log'"))
        checks.append((None not in str(filtered["meta"]), "meta has no None values"))
    
    elif mode == OutputMode.BALANCED:
        # BALANCED mode checks
        checks.append((len(filtered["diagnosis"]) == 1, "Only 1 error (suppressed filtered out)"))
        
        if filtered["diagnosis"]:
            item = filtered["diagnosis"][0]
            checks.append(("id" in item, "Has 'id'"))
            checks.append(("summary" in item, "Has 'summary'"))
            checks.append(("fix" in item, "Has 'fix'"))
            checks.append(("locations" in item, "Has 'locations'"))
            checks.append((len(item.get("locations", [])) <= 3, f"Max 3 locations (got {len(item.get('locations', []))})"))
            checks.append(("evidence" in item, "Has 'evidence'"))
            checks.append(("technical_details" not in item, "NO 'technical_details' at top level"))
            checks.append(("action" not in item, "NO 'action' nested object"))
            
            # Check evidence doesn't have technical keys
            if "evidence" in item and item["evidence"]:
                ev = item["evidence"]
                technical_keys = ["technical_details", "debug_log", "raw_locations", "raw_message"]
                has_technical = any(k in ev for k in technical_keys)
                checks.append((not has_technical, f"evidence has NO technical keys"))
        
        checks.append(("debug_log" not in filtered, "NO 'debug_log'"))
    
    else:  # DETAILED
        # DETAILED mode checks
        checks.append((len(filtered["diagnosis"]) == 2, "All 2 errors present (including suppressed)"))
        
        if filtered["diagnosis"]:
            item = filtered["diagnosis"][0]
            checks.append(("technical_details" in item, "Has 'technical_details'"))
            checks.append(("action" in item, "Has 'action' nested object"))
            checks.append(("locations" in item["action"], "action has 'locations'"))
            checks.append((len(item["action"]["locations"]) == 5, "All 5 locations present"))
        
        checks.append(("debug_log" in filtered, "Has 'debug_log'"))
    
    # Print results
    passed = 0
    failed = 0
    for check, desc in checks:
        status = "✅" if check else "❌"
        print(f"{status} {desc}")
        if check:
            passed += 1
        else:
            failed += 1
    
    print(f"\n{'='*70}")
    print(f"Result: {passed}/{len(checks)} checks passed")
    if failed > 0:
        print(f"⚠️  {failed} checks FAILED")
    else:
        print(f"✅ All checks PASSED")
    
    return failed == 0


def main():
    """Run all mode tests."""
    print(f"\n{'='*70}")
    print(f"HARD FILTERING TEST - Output Mode Verification")
    print(f"{'='*70}")
    
    results = []
    
    # Test SHORT mode
    results.append(("SHORT", test_mode(OutputMode.SHORT, "SHORT")))
    
    # Test BALANCED mode
    results.append(("BALANCED", test_mode(OutputMode.BALANCED, "BALANCED")))
    
    # Test DETAILED mode
    results.append(("DETAILED", test_mode(OutputMode.DETAILED, "DETAILED")))
    
    # Summary
    print(f"\n{'='*70}")
    print(f"FINAL SUMMARY")
    print(f"{'='*70}")
    
    for mode_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {mode_name} mode")
    
    all_passed = all(passed for _, passed in results)
    
    print(f"\n{'='*70}")
    if all_passed:
        print(f"✅ ALL MODES PASSED - Hard filtering is working correctly!")
        print(f"{'='*70}")
        return 0
    else:
        print(f"❌ SOME MODES FAILED - Check output above for details")
        print(f"{'='*70}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
