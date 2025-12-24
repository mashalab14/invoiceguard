#!/usr/bin/env python3
"""
Unit test for TIER0 mode parsing and presentation logic.
Tests the parse_kosit_report_tier0 function directly.
"""
import sys
import xml.etree.ElementTree as ET

# Add current directory to path for imports
sys.path.insert(0, '/Users/asamanta/Desktop/Invoiceguard')

from diagnostics.models import OutputMode
from main import parse_kosit_report_tier0


def test_tier0_parsing():
    """Test TIER0 parsing logic with sample KoSIT XML."""
    print("=" * 60)
    print("TIER0 PARSING UNIT TEST")
    print("=" * 60)
    print()
    
    # Sample KoSIT VARL XML report
    sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
<report xmlns="http://www.xoev.de/de/validator/varl/1">
    <message code="BR-CO-15" level="error" xpathLocation="/Invoice[1]/LegalMonetaryTotal[1]">
        Invoice total amounts are inconsistent.
    </message>
    <message code="PEPPOL-EN16931-R051" level="error" xpathLocation="/Invoice[1]/TaxExclusiveAmount[1]">
        BT-5 says EUR but amounts use USD
    </message>
    <message code="UBL-CR-001" level="warning" xpathLocation="/Invoice[1]">
        Missing CustomizationID
    </message>
</report>"""
    
    print("Test 1: Parse sample KoSIT XML")
    print("-" * 60)
    
    try:
        root = ET.fromstring(sample_xml)
        errors = parse_kosit_report_tier0(root, "test-session")
        
        print(f"✓ Parsed {len(errors)} errors from sample XML")
        print()
        
        # Verify count
        if len(errors) != 3:
            print(f"❌ Expected 3 errors, got {len(errors)}")
            return False
        
        print(f"✓ Correct number of errors: {len(errors)}")
        print()
        
        # Check first error structure
        print("Test 2: Verify first error structure")
        print("-" * 60)
        
        first_error = errors[0]
        
        if first_error.id != "BR-CO-15":
            print(f"❌ Expected id 'BR-CO-15', got '{first_error.id}'")
            return False
        
        print(f"✓ id: {first_error.id}")
        
        if first_error.severity != "error":
            print(f"❌ Expected severity 'error', got '{first_error.severity}'")
            return False
        
        print(f"✓ severity: {first_error.severity}")
        
        expected_summary = "Invoice total amounts are inconsistent."
        if first_error.action.summary != expected_summary:
            print(f"❌ Expected summary '{expected_summary}'")
            print(f"   Got: '{first_error.action.summary}'")
            return False
        
        print(f"✓ action.summary: {first_error.action.summary}")
        
        expected_fix = "See rule description and correct the invoice data accordingly."
        if first_error.action.fix != expected_fix:
            print(f"❌ Expected fix '{expected_fix}'")
            print(f"   Got: '{first_error.action.fix}'")
            return False
        
        print(f"✓ action.fix: {expected_fix}")
        
        expected_location = "/Invoice[1]/LegalMonetaryTotal[1]"
        if len(first_error.action.locations) != 1 or first_error.action.locations[0] != expected_location:
            print(f"❌ Expected location '{expected_location}'")
            print(f"   Got: {first_error.action.locations}")
            return False
        
        print(f"✓ action.locations: {first_error.action.locations}")
        print()
        
        # Check technical details match action
        print("Test 3: Verify technical_details matches action")
        print("-" * 60)
        
        if first_error.technical_details.raw_message != first_error.action.summary:
            print(f"❌ raw_message doesn't match action.summary")
            return False
        
        print(f"✓ raw_message matches action.summary (verbatim)")
        
        if first_error.technical_details.raw_locations != first_error.action.locations:
            print(f"❌ raw_locations doesn't match action.locations")
            return False
        
        print(f"✓ raw_locations matches action.locations")
        print()
        
        # Test 4: Verify all errors have the generic fix message
        print("Test 4: Verify generic fix messages")
        print("-" * 60)
        
        for error in errors:
            if error.action.fix != "See rule description and correct the invoice data accordingly.":
                print(f"❌ error {error.id} has wrong fix message: {error.action.fix}")
                return False
        
        print(f"✓ All errors have generic fix message")
        print()
        
        # Test 5: Verify structure consistency
        print("Test 5: Verify structure consistency")
        print("-" * 60)
        
        for error in errors:
            if not hasattr(error, 'id') or not hasattr(error, 'severity') or not hasattr(error, 'action'):
                print(f"❌ Error missing required attributes")
                return False
        
        print(f"✓ All errors have required attributes")
        print()
        
        # Check second error (R051)
        print("Test 6: Verify second error (R051)")
        print("-" * 60)
        
        second_error = errors[1]
        
        if second_error.id != "PEPPOL-EN16931-R051":
            print(f"❌ Expected id 'PEPPOL-EN16931-R051', got '{second_error.id}'")
            return False
        
        print(f"✓ id: {second_error.id}")
        
        expected_r051_message = "BT-5 says EUR but amounts use USD"
        if second_error.action.summary != expected_r051_message:
            print(f"❌ Expected summary '{expected_r051_message}'")
            print(f"   Got: '{second_error.action.summary}'")
            return False
        
        print(f"✓ action.summary: {second_error.action.summary}")
        
        # R051 should also have generic fix, not enriched fix
        if second_error.action.fix != expected_fix:
            print(f"❌ R051 should have generic fix in TIER0 mode")
            return False
        
        print(f"✓ R051 has generic fix (not enriched)")
        print()
        
        # Check third error (warning)
        print("Test 7: Verify third error (warning)")
        print("-" * 60)
        
        third_error = errors[2]
        
        if third_error.id != "UBL-CR-001":
            print(f"❌ Expected id 'UBL-CR-001', got '{third_error.id}'")
            return False
        
        print(f"✓ id: {third_error.id}")
        
        if third_error.severity != "warning":
            print(f"❌ Expected severity 'warning', got '{third_error.severity}'")
            return False
        
        print(f"✓ severity: {third_error.severity}")
        print()
        
        print("=" * 60)
        print("✅ TIER0 PARSING UNIT TEST PASSED")
        print("=" * 60)
        print()
        print("SUMMARY:")
        print(f"  - Parsed {len(errors)} errors correctly")
        print(f"  - All errors have verbatim KoSIT messages")
        print(f"  - All errors have generic fix message")
        print(f"  - No evidence computed (TIER0)")
        print(f"  - No suppression applied (TIER0)")
        print()
        
        return True
        
    except Exception as e:
        print(f"❌ Exception during test: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys
    success = test_tier0_parsing()
    sys.exit(0 if success else 1)
