#!/usr/bin/env python3
"""
Test script for the Humanization Layer
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from diagnostics.pipeline import DiagnosticsPipeline
from diagnostics.types import DiagnosticsResult


def test_pipeline():
    """Test the diagnostics pipeline with sample data."""
    
    # Sample raw report
    raw_report = [
        {
            "id": "BR-CO-15", 
            "message": "Invoice total amount mismatch",
            "severity": "error",
            "location": "/Invoice/LegalMonetaryTotal/TaxExclusiveAmount"
        },
        {
            "id": "BR-CO-16",
            "message": "Tax amount calculation error", 
            "severity": "error",
            "location": "/Invoice/TaxTotal/TaxAmount"
        },
        {
            "id": "UNKNOWN-ERROR",
            "message": "Some other error",
            "severity": "warning"
        }
    ]
    
    # Sample XML
    xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
    <Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
             xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
        <cbc:ID>INV-001</cbc:ID>
        <cbc:IssueDate>2024-01-01</cbc:IssueDate>
    </Invoice>"""
    
    # Initialize and run pipeline
    pipeline = DiagnosticsPipeline()
    result = pipeline.run(raw_report, xml_content)
    
    print("Pipeline Test Results:")
    print(f"Fatal error: {result.fatal_error}")
    print(f"Processed errors count: {len(result.processed_errors)}")
    
    for error in result.processed_errors:
        print(f"  - {error['id']}: {error['message']} (suppressed: {error['suppressed']})")
    
    print("✅ Pipeline test completed successfully!")


if __name__ == "__main__":
    test_pipeline()
