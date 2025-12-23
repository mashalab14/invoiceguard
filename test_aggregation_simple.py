#!/usr/bin/env python3
"""
Standalone test for aggregation functionality in presentation layer.
Tests without importing main.py to avoid config loading issues.
"""
import sys
from typing import List
from pydantic import BaseModel

# Import only what we need
from diagnostics.models import ValidationError, ErrorAction, ErrorEvidence, DebugContext, OutputMode
from diagnostics.presentation import apply_mode_filter


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


def test_short_mode_aggregates():
    """Test that SHORT mode aggregates duplicate errors."""
    print('Test 1: SHORT mode aggregates duplicates')
    errors = [
        create_test_error('ERR001', 'Missing invoice number', 'Add invoice number', 
                         ['line 10'], {'occurrence_count': 1}),
        create_test_error('ERR001', 'Missing invoice number', 'Add invoice number',
                         ['line 25'], {'occurrence_count': 1}),
        create_test_error('ERR001', 'Missing invoice number', 'Add invoice number',
                         ['line 40'], {'occurrence_count': 1}),
    ]
    
    response = ValidationResponse(
        status='REJECTED',
        errors=errors,
        meta=ValidationMeta()
    )
    
    result = apply_mode_filter(OutputMode.SHORT, response)
    print(f'  Diagnosis count: {len(result["diagnosis"])} (expected: 1)')
    assert len(result['diagnosis']) == 1, 'Should have only 1 diagnosis entry'
    
    diagnosis = result['diagnosis'][0]
    print(f'  Count: {diagnosis.get("count")} (expected: 3)')
    assert diagnosis['count'] == 3, 'Should have count=3'
    print(f'  Has title: {"title" in diagnosis}')
    assert 'title' in diagnosis, 'Should have title field'
    print(f'  Title value: {diagnosis["title"]}')
    assert diagnosis['title'] == 'Missing invoice number', 'Title should match summary'
    print(f'  Has fix: {"fix" in diagnosis}')
    assert 'fix' in diagnosis, 'Should have fix field'
    print(f'  Locations sample: {diagnosis.get("locations_sample")}')
    assert 'locations_sample' in diagnosis, 'Should have locations_sample'
    assert len(diagnosis['locations_sample']) == 3, 'Should have 3 locations'
    assert diagnosis['locations_sample'] == ['line 10', 'line 25', 'line 40'], 'Locations should match'
    print('  ✓ PASSED\n')


def test_balanced_mode_aggregates():
    """Test that BALANCED mode aggregates with evidence."""
    print('Test 2: BALANCED mode aggregates with evidence')
    errors = [
        create_test_error('ERR003', 'Invalid date format', 'Use YYYY-MM-DD format',
                         ['field: date1'], {'occurrence_count': 1, 'bt5_value': 'EUR'}),
        create_test_error('ERR003', 'Invalid date format', 'Use YYYY-MM-DD format',
                         ['field: date2'], {'occurrence_count': 1, 'bt5_value': 'EUR'}),
    ]
    
    response = ValidationResponse(
        status='REJECTED',
        errors=errors,
        meta=ValidationMeta()
    )
    
    result = apply_mode_filter(OutputMode.BALANCED, response)
    print(f'  Diagnosis count: {len(result["diagnosis"])} (expected: 1)')
    assert len(result['diagnosis']) == 1, 'Should have only 1 diagnosis entry'
    
    diagnosis = result['diagnosis'][0]
    print(f'  Count: {diagnosis.get("count")} (expected: 2)')
    assert diagnosis['count'] == 2, 'Should have count=2'
    print(f'  Summary: {diagnosis.get("summary")}')
    assert diagnosis['summary'] == 'Invalid date format', 'Should have full summary'
    print(f'  Has evidence: {"evidence" in diagnosis}')
    assert 'evidence' in diagnosis, 'Should have evidence'
    print(f'  Evidence: {diagnosis.get("evidence")}')
    assert diagnosis['evidence']['bt5_value'] == 'EUR', 'Evidence should be merged'
    print('  ✓ PASSED\n')


def test_detailed_mode_no_aggregation():
    """Test that DETAILED mode does NOT aggregate."""
    print('Test 3: DETAILED mode preserves all instances')
    errors = [
        create_test_error('ERR005', 'Duplicate item', 'Remove duplicate',
                         ['line 5'], {'occurrence_count': 1}),
        create_test_error('ERR005', 'Duplicate item', 'Remove duplicate',
                         ['line 10'], {'occurrence_count': 1}),
        create_test_error('ERR005', 'Duplicate item', 'Remove duplicate',
                         ['line 15'], {'occurrence_count': 1}),
    ]
    
    response = ValidationResponse(
        status='REJECTED',
        errors=errors,
        meta=ValidationMeta()
    )
    
    result = apply_mode_filter(OutputMode.DETAILED, response)
    print(f'  Diagnosis count: {len(result["diagnosis"])} (expected: 3)')
    assert len(result['diagnosis']) == 3, 'Should have 3 separate entries (no aggregation)'
    for diag in result['diagnosis']:
        print(f'    - {diag["id"]}: {diag["action"]["summary"]}')
    print('  ✓ PASSED\n')


def test_different_summaries_not_aggregated():
    """Test that errors with different summaries are NOT aggregated."""
    print('Test 4: Different summaries are NOT aggregated')
    errors = [
        create_test_error('ERR006', 'Missing field A', 'Add field A', [], {'occurrence_count': 1}),
        create_test_error('ERR006', 'Missing field B', 'Add field B', [], {'occurrence_count': 1}),
    ]
    
    response = ValidationResponse(
        status='REJECTED',
        errors=errors,
        meta=ValidationMeta()
    )
    
    result = apply_mode_filter(OutputMode.SHORT, response)
    print(f'  Diagnosis count: {len(result["diagnosis"])} (expected: 2)')
    assert len(result['diagnosis']) == 2, 'Should have 2 separate entries (different summaries)'
    print('  ✓ PASSED\n')


def test_suppressed_errors_excluded():
    """Test that suppressed errors are excluded from aggregation."""
    print('Test 5: Suppressed errors are excluded')
    errors = [
        create_test_error('ERR007', 'Tax error', 'Fix tax', [], {'occurrence_count': 1}, suppressed=False),
        create_test_error('ERR007', 'Tax error', 'Fix tax', [], {'occurrence_count': 1}, suppressed=True),
        create_test_error('ERR007', 'Tax error', 'Fix tax', [], {'occurrence_count': 1}, suppressed=False),
    ]
    
    response = ValidationResponse(
        status='REJECTED',
        errors=errors,
        meta=ValidationMeta()
    )
    
    result = apply_mode_filter(OutputMode.SHORT, response)
    print(f'  Diagnosis count: {len(result["diagnosis"])} (expected: 1)')
    assert len(result['diagnosis']) == 1, 'Should have 1 entry (suppressed excluded)'
    print(f'  Count: {result["diagnosis"][0]["count"]} (expected: 2)')
    assert result['diagnosis'][0]['count'] == 2, 'Should have count=2 (2 non-suppressed)'
    print('  ✓ PASSED\n')


def test_string_truncation():
    """Test that SHORT mode truncates long strings."""
    print('Test 6: String truncation in SHORT mode')
    long_summary = 'A' * 150  # 150 chars - should be truncated to 70
    long_fix = 'B' * 200      # 200 chars - should be truncated to 120
    
    errors = [
        create_test_error('ERR002', long_summary, long_fix, [], {'occurrence_count': 1})
    ]
    
    response = ValidationResponse(
        status='REJECTED',
        errors=errors,
        meta=ValidationMeta()
    )
    
    result = apply_mode_filter(OutputMode.SHORT, response)
    diagnosis = result['diagnosis'][0]
    
    print(f'  Title length: {len(diagnosis["title"])} (expected: ≤70)')
    assert len(diagnosis['title']) <= 70, 'Title should be ≤70 chars'
    assert '...' not in diagnosis['title'], 'Title should NOT end with ellipsis'
    
    print(f'  Fix length: {len(diagnosis["fix"])} (expected: ≤120)')
    assert len(diagnosis['fix']) <= 120, 'Fix should be ≤120 chars'
    assert '...' not in diagnosis['fix'], 'Fix should NOT end with ellipsis'
    print('  ✓ PASSED\n')


def test_locations_sample_limited():
    """Test that locations_sample only includes first 3 locations."""
    print('Test 7: Locations sample limited to 3')
    errors = [
        create_test_error('ERR008', 'Format error', 'Fix format',
                         ['loc1', 'loc2'], {'occurrence_count': 1}),
        create_test_error('ERR008', 'Format error', 'Fix format',
                         ['loc3', 'loc4'], {'occurrence_count': 1}),
        create_test_error('ERR008', 'Format error', 'Fix format',
                         ['loc5', 'loc6'], {'occurrence_count': 1}),
    ]
    
    response = ValidationResponse(
        status='REJECTED',
        errors=errors,
        meta=ValidationMeta()
    )
    
    result = apply_mode_filter(OutputMode.BALANCED, response)
    diagnosis = result['diagnosis'][0]
    
    print(f'  Locations count: {len(diagnosis["locations_sample"])} (expected: 3)')
    assert len(diagnosis['locations_sample']) == 3, 'Should have exactly 3 locations (not 6)'
    assert diagnosis['locations_sample'] == ['loc1', 'loc2', 'loc3'], 'Should be first 3 locations'
    print('  ✓ PASSED\n')


if __name__ == '__main__':
    try:
        test_short_mode_aggregates()
        test_balanced_mode_aggregates()
        test_detailed_mode_no_aggregation()
        test_different_summaries_not_aggregated()
        test_suppressed_errors_excluded()
        test_string_truncation()
        test_locations_sample_limited()
        
        print('=' * 50)
        print('All aggregation tests passed! ✅')
        print('=' * 50)
        sys.exit(0)
    except AssertionError as e:
        print(f'\n❌ TEST FAILED: {e}')
        sys.exit(1)
    except Exception as e:
        print(f'\n❌ ERROR: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
