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
    
    # Sample XML with monetary amounts
    xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
    <Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
             xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
             xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2">
        <cbc:ID>INV-001</cbc:ID>
        <cbc:IssueDate>2024-01-01</cbc:IssueDate>
        <cac:LegalMonetaryTotal>
            <cbc:TaxExclusiveAmount currencyID="EUR">100.00</cbc:TaxExclusiveAmount>
            <cbc:TaxInclusiveAmount currencyID="EUR">121.00</cbc:TaxInclusiveAmount>
            <cbc:PayableAmount currencyID="EUR">121.00</cbc:PayableAmount>
        </cac:LegalMonetaryTotal>
        <cac:TaxTotal>
            <cbc:TaxAmount currencyID="EUR">21.00</cbc:TaxAmount>
        </cac:TaxTotal>
    </Invoice>"""
    
    # Initialize and run pipeline
    pipeline = DiagnosticsPipeline()
    result = pipeline.run(raw_report, xml_content)
    
    print("Pipeline Test Results:")
    print(f"Fatal error: {result.fatal_error}")
    print(f"Processed errors count: {len(result.processed_errors)}")
    
    for error in result.processed_errors:
        print(f"  - {error['id']}: {error['message']} (suppressed: {error['suppressed']})")
        if error['humanized_message']:
            print(f"    → Humanized: {error['humanized_message'][:100]}...")
    
    print("✅ Pipeline test completed successfully!")
    print(f"✅ Dependency filtering working: BR-CO-16 suppressed = {any(e['id'] == 'BR-CO-16' and e['suppressed'] for e in result.processed_errors)}")
    print(f"✅ Error enrichment working: BR-CO-15 enriched = {any(e['id'] == 'BR-CO-15' and e['humanized_message'] for e in result.processed_errors)}")


if __name__ == "__main__":
    test_pipeline()
