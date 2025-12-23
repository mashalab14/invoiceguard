#!/usr/bin/env python3
"""
Test message catalog and SHORT mode improvements.
Verifies:
1. Known error IDs use catalog titles/fixes
2. Unknown error IDs use fallback generator (no ellipsis)
3. BALANCED mode evidence alignment (occurrence_count = count)
4. No per-ID if/else blocks in presentation.py
"""
import sys
from typing import List
from pydantic import BaseModel

# Import only what we need
from diagnostics.models import ValidationError, ErrorAction, ErrorEvidence, DebugContext, OutputMode
from diagnostics.presentation import apply_mode_filter
from diagnostics.message_catalog import ERROR_CATALOG, get_title, get_short_fix


# Define minimal ValidationResponse model for testing
class ValidationMeta(BaseModel):
    engine: str = "test"
    rules_tag: str = "v1"
    commit: str = "abc123"


class ValidationResponse(BaseModel):
    status: str
    meta: ValidationMeta
    errors: List[ValidationError]
    debug_log: str = None


def create_test_error(error_id: str, summary: str, fix: str, 
                     locations: list = None, evidence: dict = None,
                     suppressed: bool = False):
    """Helper to create a ValidationError for testing."""
    return ValidationError(
        id=error_id,
        severity='error',
        suppressed=suppressed,
        action=ErrorAction(
            summary=summary,
            fix=fix,
            locations=locations or []
        ),
        evidence=ErrorEvidence(**evidence) if evidence else None,
        technical_details=DebugContext(
            raw_message='test message',
            raw_locations=[]
        )
    )


def test_catalog_lookup():
    """Test that known error IDs use catalog entries."""
    print('Test 1: Catalog lookup for known error IDs')
    
    # Test R051 - should use catalog
    title = get_title("PEPPOL-EN16931-R051", "Some long fallback summary that would be truncated")
    fix = get_short_fix("PEPPOL-EN16931-R051", "Some long fallback fix that would be truncated")
    
    print(f'  R051 title: "{title}"')
    assert title == "Currency mismatch: BT-5 vs currencyID", f"Expected catalog title, got: {title}"
    print(f'  R051 fix: "{fix}"')
    assert fix == "Ensure all currencyID attributes match BT-5.", f"Expected catalog fix, got: {fix}"
    
    # Test BR-CO-15 - should use catalog
    title = get_title("BR-CO-15", "Some long fallback summary")
    fix = get_short_fix("BR-CO-15", "Some long fallback fix")
    
    print(f'  BR-CO-15 title: "{title}"')
    assert title == "Totals mismatch: BT-112 vs BT-109 + BT-110", f"Expected catalog title, got: {title}"
    print(f'  BR-CO-15 fix: "{fix}"')
    assert fix == "Ensure BT-112 equals BT-109 plus BT-110.", f"Expected catalog fix, got: {fix}"
    
    print('  ✓ PASSED\n')


def test_fallback_generator_no_ellipsis():
    """Test that unknown error IDs use fallback generator without ellipsis."""
    print('Test 2: Fallback generator for unknown error IDs (no ellipsis)')
    
    # Test with delimiter splitting
    long_summary = "This is a very long summary. It has multiple sentences. And even more text after that."
    title = get_title("UNKNOWN-ERR-123", long_summary)
    
    print(f'  Generated title: "{title}"')
    print(f'  Title length: {len(title)}')
    assert '...' not in title, "Title should NOT contain ellipsis"
    assert len(title) <= 70, f"Title should be ≤70 chars, got {len(title)}"
    assert title == "This is a very long summary", f"Should take first sentence, got: {title}"
    
    # Test with long single segment
    very_long_summary = "A" * 100  # 100 chars, no delimiters
    title = get_title("UNKNOWN-ERR-456", very_long_summary)
    
    print(f'  Long single segment title length: {len(title)}')
    assert '...' not in title, "Title should NOT contain ellipsis"
    assert len(title) <= 70, f"Title should be ≤70 chars, got {len(title)}"
    
    # Test fix fallback
    long_fix = "First sentence is the fix. Second sentence is additional info. Third sentence is more."
    fix = get_short_fix("UNKNOWN-ERR-789", long_fix)
    
    print(f'  Generated fix: "{fix}"')
    print(f'  Fix length: {len(fix)}')
    assert '...' not in fix, "Fix should NOT contain ellipsis"
    assert len(fix) <= 120, f"Fix should be ≤120 chars, got {len(fix)}"
    
    print('  ✓ PASSED\n')


def test_short_mode_uses_catalog():
    """Test that SHORT mode uses catalog for known errors."""
    print('Test 3: SHORT mode uses message catalog')
    
    errors = [
        create_test_error('PEPPOL-EN16931-R051', 
                         'Very long original summary that would normally be truncated with ellipsis',
                         'Very long original fix that would normally be truncated with ellipsis',
                         ['line 10'], {'occurrence_count': 1}),
        create_test_error('PEPPOL-EN16931-R051',
                         'Very long original summary that would normally be truncated with ellipsis',
                         'Very long original fix that would normally be truncated with ellipsis',
                         ['line 20'], {'occurrence_count': 1}),
    ]
    
    response = ValidationResponse(
        status='REJECTED',
        errors=errors,
        meta=ValidationMeta()
    )
    
    result = apply_mode_filter(OutputMode.SHORT, response)
    diagnosis = result['diagnosis'][0]
    
    print(f'  Title: "{diagnosis["title"]}"')
    assert diagnosis['title'] == "Currency mismatch: BT-5 vs currencyID", "Should use catalog title"
    
    print(f'  Fix: "{diagnosis["fix"]}"')
    assert diagnosis['fix'] == "Ensure all currencyID attributes match BT-5.", "Should use catalog fix"
    
    print(f'  No ellipsis in title: {"..." not in diagnosis["title"]}')
    assert '...' not in diagnosis['title'], "Title should not have ellipsis"
    
    print(f'  No ellipsis in fix: {"..." not in diagnosis["fix"]}')
    assert '...' not in diagnosis['fix'], "Fix should not have ellipsis"
    
    print(f'  Count: {diagnosis["count"]} (expected: 2)')
    assert diagnosis['count'] == 2, "Should aggregate 2 instances"
    
    print('  ✓ PASSED\n')


def test_short_mode_fallback_no_ellipsis():
    """Test that SHORT mode fallback generator doesn't add ellipsis."""
    print('Test 4: SHORT mode fallback generator (no ellipsis)')
    
    errors = [
        create_test_error('CUSTOM-UNKNOWN-ERROR', 
                         'This is a test error. It has multiple sentences. But we only need the first one.',
                         'Fix the issue by doing X. Then do Y. Finally do Z.',
                         [], {'occurrence_count': 1}),
    ]
    
    response = ValidationResponse(
        status='REJECTED',
        errors=errors,
        meta=ValidationMeta()
    )
    
    result = apply_mode_filter(OutputMode.SHORT, response)
    diagnosis = result['diagnosis'][0]
    
    print(f'  Title: "{diagnosis["title"]}"')
    print(f'  Title length: {len(diagnosis["title"])}')
    assert '...' not in diagnosis['title'], "Title should NOT contain ellipsis"
    assert diagnosis['title'] == "This is a test error", "Should extract first sentence"
    
    print(f'  Fix: "{diagnosis["fix"]}"')
    print(f'  Fix length: {len(diagnosis["fix"])}')
    assert '...' not in diagnosis['fix'], "Fix should NOT contain ellipsis"
    assert diagnosis['fix'] == "Fix the issue by doing X", "Should extract first sentence"
    
    print('  ✓ PASSED\n')


def test_balanced_evidence_alignment():
    """Test that BALANCED mode sets occurrence_count = count."""
    print('Test 5: BALANCED mode evidence alignment')
    
    errors = [
        create_test_error('PEPPOL-EN16931-R051',
                         'Currency conflict',
                         'Fix currency',
                         ['field1'],
                         {'occurrence_count': 1, 'bt5_value': 'EUR', 'currency_ids_found': {'USD': 1}}),
        create_test_error('PEPPOL-EN16931-R051',
                         'Currency conflict',
                         'Fix currency',
                         ['field2'],
                         {'occurrence_count': 1, 'bt5_value': 'EUR', 'currency_ids_found': {'USD': 1}}),
        create_test_error('PEPPOL-EN16931-R051',
                         'Currency conflict',
                         'Fix currency',
                         ['field3'],
                         {'occurrence_count': 1, 'bt5_value': 'EUR', 'currency_ids_found': {'GBP': 1}}),
    ]
    
    response = ValidationResponse(
        status='REJECTED',
        errors=errors,
        meta=ValidationMeta()
    )
    
    result = apply_mode_filter(OutputMode.BALANCED, response)
    diagnosis = result['diagnosis'][0]
    
    print(f'  Count: {diagnosis["count"]}')
    assert diagnosis['count'] == 3, "Should have count=3"
    
    print(f'  Evidence occurrence_count: {diagnosis["evidence"]["occurrence_count"]}')
    assert diagnosis['evidence']['occurrence_count'] == 3, "occurrence_count should equal count"
    
    print(f'  Evidence bt5_value: {diagnosis["evidence"]["bt5_value"]}')
    assert diagnosis['evidence']['bt5_value'] == 'EUR', "Should preserve bt5_value"
    
    print(f'  Evidence currency_ids_found: {diagnosis["evidence"]["currency_ids_found"]}')
    # Should sum the counts: USD appears twice (1+1=2), GBP once (1)
    assert diagnosis['evidence']['currency_ids_found']['USD'] == 2, "Should sum USD counts"
    assert diagnosis['evidence']['currency_ids_found']['GBP'] == 1, "Should have GBP count"
    
    print('  ✓ PASSED\n')


def test_no_presentation_logic_per_id():
    """Verify that presentation.py doesn't have per-ID if/else blocks."""
    print('Test 6: No per-ID logic in presentation.py')
    
    # Read presentation.py and check for per-ID conditionals
    with open('diagnostics/presentation.py', 'r') as f:
        content = f.read()
    
    # Check for specific error ID strings that would indicate hardcoded logic
    forbidden_patterns = [
        'if error_id == "PEPPOL',
        'if error_id == "BR-CO',
        'elif error.id == "PEPPOL',
        'elif error.id == "BR-CO',
    ]
    
    found_violations = []
    for pattern in forbidden_patterns:
        if pattern in content:
            found_violations.append(pattern)
    
    if found_violations:
        print(f'  ❌ Found per-ID logic in presentation.py: {found_violations}')
        assert False, f"presentation.py should not have per-ID if/else blocks: {found_violations}"
    else:
        print('  ✓ No per-ID if/else blocks found in presentation.py')
    
    # Verify catalog import exists
    assert 'from diagnostics.message_catalog import' in content, "Should import from message_catalog"
    print('  ✓ Catalog import found')
    
    print('  ✓ PASSED\n')


def test_catalog_extensibility():
    """Test that adding new errors to catalog is easy."""
    print('Test 7: Catalog extensibility')
    
    # Check that catalog is simple dict structure
    print(f'  Catalog entries: {len(ERROR_CATALOG)}')
    assert len(ERROR_CATALOG) >= 2, "Should have at least R051 and BR-CO-15"
    
    # Verify structure
    for error_id, entry in ERROR_CATALOG.items():
        assert 'title' in entry, f"{error_id} should have 'title'"
        assert 'fix' in entry, f"{error_id} should have 'short_fix'"
        assert isinstance(entry['title'], str), f"{error_id} title should be string"
        assert isinstance(entry['fix'], str), f"{error_id} fix should be string"
        print(f'  ✓ {error_id}: "{entry["title"]}"')
    
    print('  ✓ PASSED\n')


if __name__ == '__main__':
    try:
        test_catalog_lookup()
        test_fallback_generator_no_ellipsis()
        test_short_mode_uses_catalog()
        test_short_mode_fallback_no_ellipsis()
        test_balanced_evidence_alignment()
        test_no_presentation_logic_per_id()
        test_catalog_extensibility()
        
        print('=' * 60)
        print('✅ All message catalog tests passed!')
        print('=' * 60)
        print()
        print('Summary:')
        print('  • Known error IDs use catalog titles/fixes')
        print('  • Unknown error IDs use safe fallback (no ellipsis)')
        print('  • BALANCED evidence aligned (occurrence_count = count)')
        print('  • No per-ID if/else in presentation.py')
        print('  • Catalog is easily extensible')
        print()
        sys.exit(0)
    except AssertionError as e:
        print(f'\n❌ TEST FAILED: {e}')
        sys.exit(1)
    except Exception as e:
        print(f'\n❌ ERROR: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
