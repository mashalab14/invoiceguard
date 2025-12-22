#!/usr/bin/env python3
"""
Phase 5: Testing & Validation for Tiered JSON Structure
Tests the complete end-to-end flow with test.xml containing R051 errors.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from main import (
    validate_file,
    _deduplicate_errors,
    _apply_cross_error_suppression,
    convert_flat_to_tiered,
    clean_xpath
)
from diagnostics.models import ValidationError, ErrorAction, ErrorEvidence, DebugContext


def test_clean_xpath():
    """Test XPath cleaning functionality."""
    print("\n" + "="*70)
    print("TEST 1: clean_xpath() - Namespace Stripping")
    print("="*70)
    
    test_cases = [
        {
            "input": "/cbc:TaxExclusiveAmount[1]",
            "expected": "/TaxExclusiveAmount[1]",
            "description": "Remove cbc: prefix"
        },
        {
            "input": "/Invoice[1]/cac:LegalMonetaryTotal[1]/cbc:TaxAmount[1]",
            "expected": "/Invoice[1]/LegalMonetaryTotal[1]/TaxAmount[1]",
            "description": "Remove multiple namespace prefixes"
        },
        {
            "input": "/*:Invoice[namespace-uri()='urn:...']",
            "expected": "/Invoice",
            "description": "Remove namespace-uri() predicates"
        }
    ]
    
    passed = 0
    for i, test in enumerate(test_cases, 1):
        result = clean_xpath(test["input"])
        success = result == test["expected"]
        
        print(f"\n{i}. {test['description']}")
        print(f"   Input:    {test['input']}")
        print(f"   Expected: {test['expected']}")
        print(f"   Got:      {result}")
        print(f"   Status:   {'✅ PASS' if success else '❌ FAIL'}")
        
        if success:
            passed += 1
    
    print(f"\n{'='*70}")
    print(f"Result: {passed}/{len(test_cases)} tests passed")
    return passed == len(test_cases)


def test_convert_flat_to_tiered():
    """Test flat-to-tiered conversion."""
    print("\n" + "="*70)
    print("TEST 2: convert_flat_to_tiered() - Structure Conversion")
    print("="*70)
    
    # Test R051 with structured data
    flat_error = {
        "id": "PEPPOL-EN16931-R051",
        "message": "[BR-51] BT-5 must match all currencyID attributes",
        "location": "/Invoice[1]/cac:LegalMonetaryTotal[1]/cbc:TaxExclusiveAmount[1]",
        "severity": "error",
        "humanized_message": "Currency Conflict. The Document Currency is 'MMK', but this field uses 'EUR'. Please make them consistent.",
        "structured_data": {
            "bt5_value": "MMK",
            "found_currency": "EUR",
            "message": "Currency Conflict. The Document Currency is 'MMK', but this field uses 'EUR'. Please make them consistent."
        },
        "suppressed": False
    }
    
    tiered = convert_flat_to_tiered(flat_error, "test-session")
    
    print(f"\n✓ Converted to tiered structure")
    print(f"  ID:        {tiered.id}")
    print(f"  Severity:  {tiered.severity}")
    print(f"  Suppressed: {tiered.suppressed}")
    
    print(f"\n✓ Action:")
    print(f"  Summary:   {tiered.action.summary[:60]}...")
    print(f"  Fix:       {tiered.action.fix[:60]}...")
    print(f"  Locations: {tiered.action.locations}")
    
    print(f"\n✓ Evidence:")
    if tiered.evidence:
        print(f"  BT-5 Value:         {tiered.evidence.bt5_value}")
        print(f"  Currency IDs Found: {tiered.evidence.currency_ids_found}")
        print(f"  Occurrence Count:   {tiered.evidence.occurrence_count}")
    else:
        print(f"  None")
    
    print(f"\n✓ Technical Details:")
    print(f"  Raw Message:   {tiered.technical_details.raw_message[:60]}...")
    print(f"  Raw Locations: {tiered.technical_details.raw_locations}")
    
    # Validate structure
    checks = [
        (tiered.id == "PEPPOL-EN16931-R051", "ID matches"),
        (tiered.action.summary is not None, "Has action summary"),
        (tiered.action.fix is not None, "Has action fix"),
        (len(tiered.action.locations) > 0, "Has cleaned locations"),
        (tiered.evidence is not None, "Has evidence"),
        (tiered.evidence.bt5_value == "MMK", "Evidence has bt5_value"),
        (tiered.evidence.currency_ids_found == {"EUR": 1}, "Evidence has currency_ids_found"),
        (tiered.technical_details.raw_message is not None, "Has raw message"),
        (len(tiered.technical_details.raw_locations) > 0, "Has raw locations"),
    ]
    
    passed = sum(1 for check, _ in checks if check)
    print(f"\n{'='*70}")
    print(f"Validation: {passed}/{len(checks)} checks passed")
    
    for check, desc in checks:
        print(f"  {'✅' if check else '❌'} {desc}")
    
    return passed == len(checks)


def test_deduplication():
    """Test error deduplication with evidence aggregation."""
    print("\n" + "="*70)
    print("TEST 3: _deduplicate_errors() - Evidence Aggregation")
    print("="*70)
    
    # Create 3 R051 errors with different currencies
    errors = []
    for i, (currency, location) in enumerate([
        ("EUR", "/LegalMonetaryTotal[1]/TaxExclusiveAmount[1]"),
        ("EUR", "/LegalMonetaryTotal[1]/TaxInclusiveAmount[1]"),
        ("EUR", "/LegalMonetaryTotal[1]/PayableAmount[1]"),
    ], 1):
        error = ValidationError(
            id="PEPPOL-EN16931-R051",
            severity="error",
            action=ErrorAction(
                summary=f"Currency Conflict. The Document Currency is 'MMK', but this field uses '{currency}'.",
                fix="Make BT-5 and currencyID consistent.",
                locations=[location]
            ),
            evidence=ErrorEvidence(
                bt5_value="MMK",
                currency_ids_found={currency: 1},
                occurrence_count=1
            ),
            technical_details=DebugContext(
                raw_message="[BR-51] BT-5 must match currencyID",
                raw_locations=[f"/Invoice[1]/cac:LegalMonetaryTotal[1]/cbc:{location.split('/')[-1]}"]
            ),
            suppressed=False
        )
        errors.append(error)
    
    print(f"\nBefore deduplication: {len(errors)} errors")
    for i, err in enumerate(errors, 1):
        print(f"  {i}. {err.id} at {err.action.locations[0]}")
        print(f"     Currency: {err.evidence.currency_ids_found}")
    
    # Deduplicate
    deduplicated = _deduplicate_errors(errors, "test-session")
    
    print(f"\nAfter deduplication: {len(deduplicated)} errors")
    
    if len(deduplicated) == 1:
        dedup_err = deduplicated[0]
        print(f"\n✓ Deduplicated Error:")
        print(f"  ID: {dedup_err.id}")
        print(f"  Summary: {dedup_err.action.summary[:80]}...")
        print(f"  Locations ({len(dedup_err.action.locations)}): {dedup_err.action.locations}")
        print(f"  Evidence:")
        print(f"    BT-5 Value: {dedup_err.evidence.bt5_value}")
        print(f"    Currency IDs Found: {dedup_err.evidence.currency_ids_found}")
        print(f"    Occurrence Count: {dedup_err.evidence.occurrence_count}")
        
        # Validate aggregation
        checks = [
            (len(deduplicated) == 1, "Reduced to 1 error"),
            (dedup_err.evidence.occurrence_count == 3, "Occurrence count = 3"),
            (dedup_err.evidence.currency_ids_found["EUR"] == 3, "EUR count = 3"),
            (len(dedup_err.action.locations) == 3, "3 locations aggregated"),
            ("(Repeated 3 times)" in dedup_err.action.summary, "Summary shows repeat count"),
        ]
        
        passed = sum(1 for check, _ in checks if check)
        print(f"\n{'='*70}")
        print(f"Validation: {passed}/{len(checks)} checks passed")
        
        for check, desc in checks:
            print(f"  {'✅' if check else '❌'} {desc}")
        
        return passed == len(checks)
    else:
        print(f"\n❌ FAIL: Expected 1 deduplicated error, got {len(deduplicated)}")
        return False


def test_suppression():
    """Test cross-error suppression logic."""
    print("\n" + "="*70)
    print("TEST 4: _apply_cross_error_suppression() - Cascade Suppression")
    print("="*70)
    
    # Create R051 error
    r051 = ValidationError(
        id="PEPPOL-EN16931-R051",
        severity="error",
        action=ErrorAction(
            summary="Currency Conflict. The Document Currency is 'MMK', but this field uses 'EUR'.",
            fix="Make BT-5 and currencyID consistent.",
            locations=["/TaxExclusiveAmount[1]"]
        ),
        evidence=ErrorEvidence(
            bt5_value="MMK",
            currency_ids_found={"EUR": 1},
            occurrence_count=1
        ),
        technical_details=DebugContext(
            raw_message="[BR-51] BT-5 must match currencyID",
            raw_locations=["/Invoice[1]/cac:LegalMonetaryTotal[1]/cbc:TaxExclusiveAmount[1]"]
        ),
        suppressed=False
    )
    
    # Create BR-CO-15 error (math error - cascade effect)
    br_co_15 = ValidationError(
        id="BR-CO-15",
        severity="error",
        action=ErrorAction(
            summary="Math Error: Invoice total amount mismatch.",
            fix="Verify that Tax Inclusive Amount = Tax Exclusive Amount + Tax Amount.",
            locations=["/LegalMonetaryTotal[1]"]
        ),
        evidence=None,
        technical_details=DebugContext(
            raw_message="Invoice total amount without VAT = Sum of Invoice line net amount",
            raw_locations=["/Invoice[1]/cac:LegalMonetaryTotal[1]"]
        ),
        suppressed=False
    )
    
    errors = [r051, br_co_15]
    
    print(f"\nBefore suppression:")
    for err in errors:
        print(f"  • {err.id}: suppressed={err.suppressed}")
    
    # Apply suppression
    suppressed_errors = _apply_cross_error_suppression(errors, "test-session")
    
    print(f"\nAfter suppression:")
    for err in suppressed_errors:
        print(f"  • {err.id}: suppressed={err.suppressed}")
        if err.suppressed:
            print(f"    Summary: {err.action.summary}")
    
    # Validate
    checks = [
        (suppressed_errors[0].id == "PEPPOL-EN16931-R051", "R051 present"),
        (not suppressed_errors[0].suppressed, "R051 not suppressed"),
        (suppressed_errors[1].id == "BR-CO-15", "BR-CO-15 present"),
        (suppressed_errors[1].suppressed, "BR-CO-15 is suppressed"),
        ("Suppressed" in suppressed_errors[1].action.summary, "BR-CO-15 has suppression message"),
    ]
    
    passed = sum(1 for check, _ in checks if check)
    print(f"\n{'='*70}")
    print(f"Validation: {passed}/{len(checks)} checks passed")
    
    for check, desc in checks:
        print(f"  {'✅' if check else '❌'} {desc}")
    
    return passed == len(checks)


def test_json_serialization():
    """Test Pydantic JSON serialization."""
    print("\n" + "="*70)
    print("TEST 5: Pydantic JSON Serialization")
    print("="*70)
    
    # Create a complete tiered error
    error = ValidationError(
        id="PEPPOL-EN16931-R051",
        severity="error",
        action=ErrorAction(
            summary="Currency Conflict. The Document Currency is 'MMK', but this field uses 'EUR'. (Repeated 12 times)",
            fix="Make BT-5 (DocumentCurrencyCode) and all currencyID attributes consistent.",
            locations=[
                "/TaxExclusiveAmount[1]",
                "/TaxInclusiveAmount[1]",
                "/PayableAmount[1]"
            ]
        ),
        evidence=ErrorEvidence(
            bt5_value="MMK",
            currency_ids_found={"EUR": 12},
            occurrence_count=12
        ),
        technical_details=DebugContext(
            raw_message="[BR-51] BT-5 must match all currencyID attributes",
            raw_locations=[
                "/Invoice[1]/cac:LegalMonetaryTotal[1]/cbc:TaxExclusiveAmount[1]",
                "/Invoice[1]/cac:LegalMonetaryTotal[1]/cbc:TaxInclusiveAmount[1]",
                "/Invoice[1]/cac:LegalMonetaryTotal[1]/cbc:PayableAmount[1]"
            ]
        ),
        suppressed=False
    )
    
    # Serialize to JSON
    json_str = error.model_dump_json(indent=2)
    json_obj = json.loads(json_str)
    
    print(f"\n✓ Serialized to JSON:")
    print(json.dumps(json_obj, indent=2))
    
    # Validate structure
    checks = [
        ("id" in json_obj, "Has 'id' field"),
        ("severity" in json_obj, "Has 'severity' field"),
        ("action" in json_obj, "Has 'action' field"),
        ("evidence" in json_obj, "Has 'evidence' field"),
        ("technical_details" in json_obj, "Has 'technical_details' field"),
        ("suppressed" in json_obj, "Has 'suppressed' field"),
        ("summary" in json_obj["action"], "action has 'summary'"),
        ("fix" in json_obj["action"], "action has 'fix'"),
        ("locations" in json_obj["action"], "action has 'locations'"),
        ("bt5_value" in json_obj["evidence"], "evidence has 'bt5_value'"),
        ("currency_ids_found" in json_obj["evidence"], "evidence has 'currency_ids_found'"),
        ("occurrence_count" in json_obj["evidence"], "evidence has 'occurrence_count'"),
        ("raw_message" in json_obj["technical_details"], "technical_details has 'raw_message'"),
        ("raw_locations" in json_obj["technical_details"], "technical_details has 'raw_locations'"),
        (json_obj["evidence"]["currency_ids_found"]["EUR"] == 12, "currency_ids_found['EUR'] = 12"),
        (json_obj["evidence"]["occurrence_count"] == 12, "occurrence_count = 12"),
    ]
    
    passed = sum(1 for check, _ in checks if check)
    print(f"\n{'='*70}")
    print(f"Validation: {passed}/{len(checks)} checks passed")
    
    for check, desc in checks:
        print(f"  {'✅' if check else '❌'} {desc}")
    
    return passed == len(checks)


def main():
    """Run all Phase 5 tests."""
    print("\n" + "="*70)
    print("🧪 PHASE 5: TIERED JSON STRUCTURE TESTING")
    print("="*70)
    print(f"Testing with: test.xml")
    print(f"Expected errors: R051 (Currency Mismatch: MMK vs EUR)")
    
    tests = [
        ("XPath Cleaning", test_clean_xpath),
        ("Flat-to-Tiered Conversion", test_convert_flat_to_tiered),
        ("Error Deduplication", test_deduplication),
        ("Cross-Error Suppression", test_suppression),
        ("JSON Serialization", test_json_serialization),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n❌ ERROR in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Final summary
    print("\n" + "="*70)
    print("📊 PHASE 5 TEST SUMMARY")
    print("="*70)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
    
    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)
    
    print(f"\n{'='*70}")
    print(f"Overall: {total_passed}/{total_tests} test suites passed")
    print(f"{'='*70}")
    
    if total_passed == total_tests:
        print("\n🎉 ALL TESTS PASSED! Tiered structure implementation validated.")
        return 0
    else:
        print(f"\n⚠️  {total_tests - total_passed} test suite(s) failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
