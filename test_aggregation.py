"""
Test aggregation functionality in presentation layer.
Verifies that SHORT and BALANCED modes deduplicate repeated errors
while DETAILED mode preserves all instances.
"""
import pytest
from diagnostics.models import (
    ValidationError, ValidationResponse, ActionableError,
    Evidence, OutputMode, ValidationMeta
)
from diagnostics.presentation import apply_mode_filter


def create_test_error(error_id: str, summary: str, fix: str, 
                     locations: list = None, evidence: dict = None,
                     suppressed: bool = False):
    """Helper to create a ValidationError for testing."""
    return ValidationError(
        id=error_id,
        suppressed=suppressed,
        action=ActionableError(
            summary=summary,
            fix=fix,
            locations=locations or []
        ),
        evidence=Evidence(**evidence) if evidence else None
    )


def test_short_mode_aggregates_duplicates():
    """Test that SHORT mode aggregates duplicate errors and adds count."""
    # Create 3 instances of same error
    errors = [
        create_test_error("ERR001", "Missing invoice number", "Add invoice number", 
                         ["line 10"], {"field": "invoice_no"}),
        create_test_error("ERR001", "Missing invoice number", "Add invoice number",
                         ["line 25"], {"field": "invoice_no"}),
        create_test_error("ERR001", "Missing invoice number", "Add invoice number",
                         ["line 40"], {"field": "invoice_no"}),
    ]
    
    response = ValidationResponse(
        status="warning",
        errors=errors,
        meta=ValidationMeta(total_errors=3)
    )
    
    result = apply_mode_filter(OutputMode.SHORT, response)
    
    # Should have only 1 diagnosis entry
    assert len(result["diagnosis"]) == 1
    
    diagnosis = result["diagnosis"][0]
    # Should have count field showing 3 instances
    assert diagnosis["count"] == 3
    # Should have truncated title (SHORT uses 'title' not 'summary')
    assert "title" in diagnosis
    assert diagnosis["title"] == "Missing invoice number"
    # Should have fix field
    assert "fix" in diagnosis
    # Should have locations_sample with first 3 locations
    assert "locations_sample" in diagnosis
    assert len(diagnosis["locations_sample"]) == 3
    assert diagnosis["locations_sample"] == ["line 10", "line 25", "line 40"]
    # Should NOT have evidence in SHORT mode
    assert "evidence" not in diagnosis


def test_short_mode_truncates_long_strings():
    """Test that SHORT mode truncates summary and fix to specified lengths."""
    long_summary = "A" * 150  # 150 chars - should be truncated to 100
    long_fix = "B" * 200      # 200 chars - should be truncated to 140
    
    errors = [
        create_test_error("ERR002", long_summary, long_fix)
    ]
    
    response = ValidationResponse(
        status="error",
        errors=errors,
        meta=ValidationMeta(total_errors=1)
    )
    
    result = apply_mode_filter(OutputMode.SHORT, response)
    
    diagnosis = result["diagnosis"][0]
    # Title should be truncated to 100 chars (including ...)
    assert len(diagnosis["title"]) == 100
    assert diagnosis["title"].endswith("...")
    # Fix should be truncated to 140 chars (including ...)
    assert len(diagnosis["fix"]) == 140
    assert diagnosis["fix"].endswith("...")


def test_balanced_mode_aggregates_with_evidence():
    """Test that BALANCED mode aggregates and merges evidence."""
    errors = [
        create_test_error("ERR003", "Invalid date format", "Use YYYY-MM-DD format",
                         ["field: date1"], {"fields": ["date1"], "pattern": "DD/MM/YYYY"}),
        create_test_error("ERR003", "Invalid date format", "Use YYYY-MM-DD format",
                         ["field: date2"], {"fields": ["date2"], "pattern": "DD/MM/YYYY"}),
    ]
    
    response = ValidationResponse(
        status="warning",
        errors=errors,
        meta=ValidationMeta(total_errors=2)
    )
    
    result = apply_mode_filter(OutputMode.BALANCED, response)
    
    # Should have only 1 diagnosis entry
    assert len(result["diagnosis"]) == 1
    
    diagnosis = result["diagnosis"][0]
    # Should have count field showing 2 instances
    assert diagnosis["count"] == 2
    # Should have full summary (no truncation in BALANCED)
    assert diagnosis["summary"] == "Invalid date format"
    # Should have full fix
    assert diagnosis["fix"] == "Use YYYY-MM-DD format"
    # Should have locations_sample with first 3 locations
    assert "locations_sample" in diagnosis
    assert len(diagnosis["locations_sample"]) == 2
    # Should have merged evidence
    assert "evidence" in diagnosis
    # Evidence should merge list fields (unique values)
    assert "fields" in diagnosis["evidence"]
    assert set(diagnosis["evidence"]["fields"]) == {"date1", "date2"}


def test_balanced_mode_no_truncation():
    """Test that BALANCED mode does NOT truncate strings."""
    long_summary = "A" * 150
    long_fix = "B" * 200
    
    errors = [
        create_test_error("ERR004", long_summary, long_fix)
    ]
    
    response = ValidationResponse(
        status="error",
        errors=errors,
        meta=ValidationMeta(total_errors=1)
    )
    
    result = apply_mode_filter(OutputMode.BALANCED, response)
    
    diagnosis = result["diagnosis"][0]
    # Summary should be full length (no truncation)
    assert len(diagnosis["summary"]) == 150
    assert not diagnosis["summary"].endswith("...")
    # Fix should be full length
    assert len(diagnosis["fix"]) == 200
    assert not diagnosis["fix"].endswith("...")


def test_detailed_mode_no_aggregation():
    """Test that DETAILED mode does NOT aggregate duplicates."""
    errors = [
        create_test_error("ERR005", "Duplicate item", "Remove duplicate",
                         ["line 5"], {"item_id": "123"}),
        create_test_error("ERR005", "Duplicate item", "Remove duplicate",
                         ["line 10"], {"item_id": "123"}),
        create_test_error("ERR005", "Duplicate item", "Remove duplicate",
                         ["line 15"], {"item_id": "123"}),
    ]
    
    response = ValidationResponse(
        status="warning",
        errors=errors,
        meta=ValidationMeta(total_errors=3)
    )
    
    result = apply_mode_filter(OutputMode.DETAILED, response)
    
    # Should have 3 separate diagnosis entries (no aggregation)
    assert len(result["diagnosis"]) == 3
    
    # Each should be a full model_dump with all fields
    for diagnosis in result["diagnosis"]:
        assert "id" in diagnosis
        assert "suppressed" in diagnosis
        assert "action" in diagnosis
        assert "evidence" in diagnosis


def test_aggregation_respects_different_summaries():
    """Test that errors with different summaries are NOT aggregated."""
    errors = [
        create_test_error("ERR006", "Missing field A", "Add field A"),
        create_test_error("ERR006", "Missing field B", "Add field B"),
    ]
    
    response = ValidationResponse(
        status="warning",
        errors=errors,
        meta=ValidationMeta(total_errors=2)
    )
    
    result = apply_mode_filter(OutputMode.SHORT, response)
    
    # Should have 2 separate entries (different summaries)
    assert len(result["diagnosis"]) == 2


def test_aggregation_respects_suppressed_flag():
    """Test that suppressed errors are excluded from aggregation."""
    errors = [
        create_test_error("ERR007", "Tax error", "Fix tax", suppressed=False),
        create_test_error("ERR007", "Tax error", "Fix tax", suppressed=True),  # Suppressed
        create_test_error("ERR007", "Tax error", "Fix tax", suppressed=False),
    ]
    
    response = ValidationResponse(
        status="warning",
        errors=errors,
        meta=ValidationMeta(total_errors=3)
    )
    
    result = apply_mode_filter(OutputMode.SHORT, response)
    
    # Should have 1 entry with count=2 (suppressed one excluded)
    assert len(result["diagnosis"]) == 1
    assert result["diagnosis"][0]["count"] == 2


def test_locations_sample_limited_to_three():
    """Test that locations_sample only includes first 3 locations."""
    errors = [
        create_test_error("ERR008", "Format error", "Fix format",
                         ["loc1", "loc2"]),
        create_test_error("ERR008", "Format error", "Fix format",
                         ["loc3", "loc4"]),
        create_test_error("ERR008", "Format error", "Fix format",
                         ["loc5", "loc6"]),
    ]
    
    response = ValidationResponse(
        status="warning",
        errors=errors,
        meta=ValidationMeta(total_errors=3)
    )
    
    result = apply_mode_filter(OutputMode.BALANCED, response)
    
    diagnosis = result["diagnosis"][0]
    # Should have exactly 3 locations (not 6)
    assert len(diagnosis["locations_sample"]) == 3
    assert diagnosis["locations_sample"] == ["loc1", "loc2", "loc3"]


def test_short_mode_field_names():
    """Test that SHORT mode uses 'title' not 'summary'."""
    errors = [
        create_test_error("ERR009", "Test summary", "Test fix")
    ]
    
    response = ValidationResponse(
        status="warning",
        errors=errors,
        meta=ValidationMeta(total_errors=1)
    )
    
    result = apply_mode_filter(OutputMode.SHORT, response)
    
    diagnosis = result["diagnosis"][0]
    # SHORT mode should use 'title' field
    assert "title" in diagnosis
    assert "summary" not in diagnosis
    # Should have id, title, fix, count
    assert set(diagnosis.keys()) >= {"id", "title", "fix", "count"}


def test_balanced_mode_removes_technical_keys():
    """Test that BALANCED mode removes technical keys from evidence."""
    errors = [
        create_test_error("ERR010", "Test error", "Test fix",
                         evidence={
                             "field": "test",
                             "technical_details": "internal info",
                             "debug_log": "debug data"
                         })
    ]
    
    response = ValidationResponse(
        status="error",
        errors=errors,
        meta=ValidationMeta(total_errors=1)
    )
    
    result = apply_mode_filter(OutputMode.BALANCED, response)
    
    diagnosis = result["diagnosis"][0]
    # Evidence should exist but without technical keys
    assert "evidence" in diagnosis
    assert "field" in diagnosis["evidence"]
    assert "technical_details" not in diagnosis["evidence"]
    assert "debug_log" not in diagnosis["evidence"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
