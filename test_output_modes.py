#!/usr/bin/env python3
"""
Test the new OutputMode filtering implementation.
"""
from diagnostics.models import ValidationError, ErrorAction, ErrorEvidence, DebugContext, OutputMode
from diagnostics.presentation import apply_mode_filter

# Create sample validation errors
def create_sample_errors():
    """Create sample ValidationError objects for testing."""
    errors = []
    
    # Error 1: R051 with evidence (currency mismatch)
    errors.append(ValidationError(
        id="PEPPOL-EN16931-R051",
        severity="error",
        action=ErrorAction(
            summary="Currency Mismatch: BT-5 says EUR but amounts use USD",
            fix="Make BT-5 (DocumentCurrencyCode) and all currencyID attributes consistent.",
            locations=[
                "/Invoice[1]/TaxExclusiveAmount[1]",
                "/Invoice[1]/TaxInclusiveAmount[1]",
                "/Invoice[1]/PayableAmount[1]"
            ]
        ),
        evidence=ErrorEvidence(
            bt5_value="EUR",
            currency_ids_found={"USD": 3},
            occurrence_count=3
        ),
        technical_details=DebugContext(
            raw_message="BT-5 says EUR but amounts use USD",
            raw_locations=[
                "/*:Invoice[namespace-uri()='...']/cac:TaxExclusiveAmount[1]",
                "/*:Invoice[namespace-uri()='...']/cac:TaxInclusiveAmount[1]",
                "/*:Invoice[namespace-uri()='...']/cbc:PayableAmount[1]"
            ]
        ),
        suppressed=False
    ))
    
    # Error 2: BR-CO-15 suppressed by R051
    errors.append(ValidationError(
        id="BR-CO-15",
        severity="error",
        action=ErrorAction(
            summary="Math Error (Suppressed: Likely caused by Currency Mismatch R051)",
            fix="Verify that Tax Inclusive Amount (BT-112) = Tax Exclusive Amount (BT-109) + Tax Amount (BT-110).",
            locations=["/Invoice[1]/LegalMonetaryTotal[1]"]
        ),
        evidence=ErrorEvidence(
            occurrence_count=1
        ),
        technical_details=DebugContext(
            raw_message="[BR-CO-15]-Sum of Invoice line net amount (BT-106) = Σ Invoice line net amount (BT-131).",
            raw_locations=["/*:Invoice[namespace-uri()='...']/cac:LegalMonetaryTotal[1]"]
        ),
        suppressed=True
    ))
    
    return errors


def print_filtered_result(mode: OutputMode, result: dict):
    """Pretty print the filtered result."""
    print(f"\n{'='*60}")
    print(f"Mode: {mode.value.upper()}")
    print(f"{'='*60}")
    print(f"\nNumber of root cause errors: {len(result.get('errors', []))}")
    if 'suppressed' in result:
        print(f"Number of suppressed errors: {len(result.get('suppressed', []))}")
    
    print(f"\n--- Errors ---")
    import json
    print(json.dumps(result, indent=2))


def main():
    """Test all three modes."""
    print("Testing OutputMode Filtering Implementation")
    print("=" * 60)
    
    # Create sample errors
    errors = create_sample_errors()
    print(f"\nCreated {len(errors)} sample errors:")
    for err in errors:
        print(f"  - {err.id} (suppressed={err.suppressed})")
    
    # Test SHORT mode
    short_result = apply_mode_filter(errors, OutputMode.SHORT)
    print_filtered_result(OutputMode.SHORT, short_result)
    
    # Test BALANCED mode
    balanced_result = apply_mode_filter(errors, OutputMode.BALANCED)
    print_filtered_result(OutputMode.BALANCED, balanced_result)
    
    # Test DETAILED mode
    detailed_result = apply_mode_filter(errors, OutputMode.DETAILED)
    print_filtered_result(OutputMode.DETAILED, detailed_result)
    
    # Verify expected behavior
    print(f"\n{'='*60}")
    print("VERIFICATION")
    print(f"{'='*60}")
    
    # SHORT: should have 1 error, no suppressed, no locations
    assert len(short_result['errors']) == 1, f"SHORT should have 1 error, got {len(short_result['errors'])}"
    assert 'suppressed' not in short_result, "SHORT should not have suppressed field"
    assert short_result['errors'][0]['action']['locations'] == [], "SHORT should have no locations"
    print("✓ SHORT mode: Only root causes, no locations, no suppressed")
    
    # BALANCED: should have 1 error, 1 suppressed, max 3 locations
    assert len(balanced_result['errors']) == 1, f"BALANCED should have 1 error, got {len(balanced_result['errors'])}"
    assert len(balanced_result['suppressed']) == 1, f"BALANCED should have 1 suppressed, got {len(balanced_result['suppressed'])}"
    assert len(balanced_result['errors'][0]['action']['locations']) <= 3, "BALANCED should have max 3 locations"
    print("✓ BALANCED mode: Root causes + suppressed, max 3 locations, has evidence")
    
    # DETAILED: should have 1 error, 1 suppressed, all locations
    assert len(detailed_result['errors']) == 1, f"DETAILED should have 1 error, got {len(detailed_result['errors'])}"
    assert len(detailed_result['suppressed']) == 1, f"DETAILED should have 1 suppressed, got {len(detailed_result['suppressed'])}"
    assert detailed_result['errors'][0]['technical_details'] is not None, "DETAILED should have technical_details"
    print("✓ DETAILED mode: Everything including technical_details")
    
    print(f"\n{'='*60}")
    print("✅ All tests passed!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
