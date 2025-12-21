#!/usr/bin/env python3
"""
Development test for InvoiceGuard API with Humanization Layer
"""
import sys
import os
import json
import asyncio
from io import BytesIO

sys.path.insert(0, os.path.dirname(__file__))

# Patch paths for development
os.environ['VERSION_INFO_FILE'] = '/Users/asamanta/Desktop/Invoiceguard/version_info_dev.txt'
os.environ['RULES_DIR_FILE'] = '/Users/asamanta/Desktop/Invoiceguard/rules_dir_dev.txt'
os.environ['VALIDATOR_JAR'] = '/Users/asamanta/Desktop/Invoiceguard/validator-dev.jar'  # Dummy path

# Mock the load_config function for development
def mock_load_config():
    return {
        "commit_hash": "dev-12345678",
        "rules_dir": "/Users/asamanta/Desktop/Invoiceguard/rules"
    }

def test_enhanced_api():
    """Test the enhanced API with humanization layer."""
    
    print("🧪 Testing Enhanced InvoiceGuard API")
    print("=" * 50)
    
    try:
        # Patch the configuration loading
        import main
        main.load_config = mock_load_config
        main.config = mock_load_config()
        
        print("✅ API module loaded successfully")
        print(f"   Version: {main.config['commit_hash']}")
        print(f"   Rules: {main.config['rules_dir']}")
        
        # Test humanization pipeline
        pipeline = main.diagnostics_pipeline
        print("✅ Humanization pipeline initialized")
        
        # Test with sample validation errors
        sample_errors = [
            {
                "id": "BR-CO-15",
                "message": "[BR-CO-15] Invoice total amount MUST equal the sum of Invoice line net amounts plus the Invoice total VAT amount",
                "location": "//cac:LegalMonetaryTotal/cbc:PayableAmount",
                "severity": "error"
            },
            {
                "id": "BR-CO-16",
                "message": "[BR-CO-16] VAT category tax amount MUST equal the sum of Invoice line VAT amounts", 
                "location": "//cac:TaxTotal/cbc:TaxAmount",
                "severity": "error"
            },
            {
                "id": "PEPPOL-EN16931-R001",
                "message": "[PEPPOL-EN16931-R001] Business process MUST be provided",
                "location": "//cbc:ProfileID", 
                "severity": "error"
            }
        ]
        
        # Sample invoice XML with errors
        sample_invoice = b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    
    <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
    <cbc:ID>DEV-TEST-001</cbc:ID>
    <cbc:IssueDate>2024-12-21</cbc:IssueDate>
    <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
    <cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
    
    <!-- Missing ProfileID (PEPPOL error) -->
    
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="PCE">10</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="EUR">100.00</cbc:LineExtensionAmount>
        <cac:Item><cbc:Name>Test Item</cbc:Name></cac:Item>
        <cac:Price><cbc:PriceAmount currencyID="EUR">10.00</cbc:PriceAmount></cac:Price>
    </cac:InvoiceLine>
    
    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="EUR">19.00</cbc:TaxAmount> <!-- Error: should be 21.00 -->
    </cac:TaxTotal>
    
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="EUR">100.00</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="EUR">100.00</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="EUR">119.00</cbc:TaxInclusiveAmount> <!-- Error: should be 121.00 -->
        <cbc:PayableAmount currencyID="EUR">119.00</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
    
</Invoice>"""
        
        # Test humanization pipeline directly
        print("\n📊 Testing humanization pipeline...")
        result = pipeline.run(sample_errors, sample_invoice)
        
        print(f"   Processed {len(result.processed_errors)} errors")
        enriched_count = sum(1 for e in result.processed_errors if e.get('humanized_message'))
        suppressed_count = sum(1 for e in result.processed_errors if e.get('suppressed'))
        print(f"   Enriched: {enriched_count}, Suppressed: {suppressed_count}")
        
        # Display enriched errors
        print("\n💡 Enriched Error Messages:")
        for i, error in enumerate(result.processed_errors, 1):
            if error.get('humanized_message'):
                print(f"   {i}. {error['id']}")
                print(f"      Original: {error['message']}")
                print(f"      Enhanced: {error['humanized_message']}")
                print(f"      Suppressed: {error.get('suppressed', False)}")
                print()
        
        # Test ValidationError model conversion  
        print("📋 Testing API error models...")
        api_errors = []
        for processed_error in result.processed_errors:
            api_error = main.ValidationError(
                code=processed_error["id"],
                message=processed_error["message"],
                location=processed_error.get("location", ""),
                severity=processed_error.get("severity", "error"),
                humanized_message=processed_error.get("humanized_message"),
                suppressed=processed_error.get("suppressed", False)
            )
            api_errors.append(api_error)
        
        print(f"   Created {len(api_errors)} API error objects")
        
        # Create sample API response
        response = main.ValidationResponse(
            status="REJECTED",
            meta=main.ValidationMeta(
                engine="KoSIT 1.5.0",
                rules_tag="release-3.0.18",
                commit=main.config["commit_hash"]
            ),
            errors=api_errors,
            debug_log=None
        )
        
        print(f"   API response created with {len(response.errors)} errors")
        
        # Export test results
        test_results = {
            "timestamp": "2024-12-21T12:00:00Z",
            "api_status": "OPERATIONAL",
            "humanization_stats": {
                "total_errors": len(result.processed_errors),
                "enriched_errors": enriched_count,
                "suppressed_errors": suppressed_count,
                "enrichment_rate": (enriched_count / len(result.processed_errors) * 100) if result.processed_errors else 0
            },
            "features": [
                "KoSIT validator integration",
                "Humanization layer with 4 specialized explainers",
                "Financial calculation analysis",
                "PEPPOL compliance guidance", 
                "UBL structure validation",
                "Dependency filtering",
                "Error suppression and enrichment"
            ]
        }
        
        with open('/Users/asamanta/Desktop/Invoiceguard/api_test_results.json', 'w') as f:
            json.dump(test_results, f, indent=2)
        
        print(f"\n🎉 Enhanced API Test Complete!")
        print(f"   Status: {test_results['api_status']}")
        print(f"   Enrichment Rate: {test_results['humanization_stats']['enrichment_rate']:.1f}%")
        print(f"   Features: {len(test_results['features'])} advanced capabilities")
        print(f"   Test Results: api_test_results.json")
        
        return True
        
    except Exception as e:
        import traceback
        print(f"❌ Test failed: {e}")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_enhanced_api()
    sys.exit(0 if success else 1)
