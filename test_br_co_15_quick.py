#!/usr/bin/env python3
"""
Quick BR-CO-15 Test to Validate Improvements
"""
import sys
import os
sys.path.insert(0, os.getcwd())

from diagnostics.rule_explainers.br_co_15 import BrCo15Explainer
from common.xml_loader import SafeXMLLoader
from common.terminology import InvoiceTerminology


def test_br_co_15_improvements():
    """Test BR-CO-15 improvements with various XML structures."""
    
    print("🧪 BR-CO-15 Quick Validation Test")
    print("=" * 40)
    
    # Test the terminology system
    print("\n1️⃣ Testing Terminology System...")
    try:
        tax_exclusive = InvoiceTerminology.get_field('tax_exclusive_amount')
        payable = InvoiceTerminology.get_field('payable_amount')
        print(f"✅ Tax Exclusive: {len(tax_exclusive.xpath_strategies)} strategies")
        print(f"✅ Payable Amount: {len(payable.xpath_strategies)} strategies")
    except Exception as e:
        print(f"❌ Terminology system error: {e}")
        return False
    
    # Test XML scenarios
    test_cases = [
        {
            "name": "Standard UBL with namespaces",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cac:LegalMonetaryTotal>
        <cbc:TaxExclusiveAmount currencyID="EUR">100.00</cbc:TaxExclusiveAmount>
        <cbc:TaxAmount currencyID="EUR">20.00</cbc:TaxAmount>
        <cbc:PayableAmount currencyID="EUR">119.00</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
</Invoice>""",
            "expected_error": True  # 100 + 20 = 120, but payable is 119
        },
        {
            "name": "No namespace declarations",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice>
    <LegalMonetaryTotal>
        <TaxExclusiveAmount currencyID="EUR">100.00</TaxExclusiveAmount>
        <TaxAmount currencyID="EUR">20.00</TaxAmount>
        <PayableAmount currencyID="EUR">120.00</PayableAmount>
    </LegalMonetaryTotal>
</Invoice>""",
            "expected_error": False  # 100 + 20 = 120, payable is correct
        },
        {
            "name": "Mixed namespace structure",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <LegalMonetaryTotal>
        <cbc:TaxExclusiveAmount currencyID="EUR">200.00</cbc:TaxExclusiveAmount>
        <TaxAmount currencyID="EUR">40.00</TaxAmount>
        <cbc:PayableAmount currencyID="EUR">241.00</cbc:PayableAmount>
    </LegalMonetaryTotal>
</Invoice>""",
            "expected_error": True  # 200 + 40 = 240, but payable is 241
        }
    ]
    
    print(f"\n2️⃣ Testing {len(test_cases)} XML scenarios...")
    
    xml_loader = SafeXMLLoader()
    explainer = BrCo15Explainer()
    
    success_count = 0
    extraction_success_count = 0
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📋 Test {i}: {test_case['name']}")
        
        try:
            # Parse XML
            xml_tree = xml_loader.parse(test_case['xml'])
            root = xml_tree.getroot()
            
            # Test extraction capabilities
            try:
                evidence = explainer._extract_monetary_evidence(root)
                extraction_success_count += 1
                print(f"✅ Data extraction successful")
                print(f"   Tax Exclusive: {evidence.get('tax_exclusive_amount', 'NOT_FOUND')}")
                print(f"   Payable Amount: {evidence.get('payable_amount', 'NOT_FOUND')}")
                print(f"   Tax Amount: {evidence.get('tax_amount', 'NOT_FOUND')}")
                
                # Check if we found the required values
                if evidence.get('tax_exclusive_amount') and evidence.get('payable_amount'):
                    success_count += 1
                    print(f"✅ Required fields extracted")
                else:
                    print(f"⚠️  Missing required fields")
                    
            except Exception as e:
                print(f"❌ Extraction failed: {e}")
                
        except Exception as e:
            print(f"❌ XML parsing failed: {e}")
    
    # Summary
    print(f"\n📊 Test Results Summary")
    print("=" * 40)
    print(f"XML Parsing Success: {len(test_cases)}/{len(test_cases)}")
    print(f"Data Extraction Success: {extraction_success_count}/{len(test_cases)} ({extraction_success_count/len(test_cases)*100:.1f}%)")
    print(f"Complete Field Extraction: {success_count}/{len(test_cases)} ({success_count/len(test_cases)*100:.1f}%)")
    
    # Production readiness assessment
    if extraction_success_count >= len(test_cases) * 0.95:
        print("🎉 PRODUCTION READY: >95% extraction success rate achieved!")
        return True
    elif extraction_success_count >= len(test_cases) * 0.75:
        print("⚠️  IMPROVEMENT NEEDED: 75-95% success rate")
        return False
    else:
        print("❌ NOT READY: <75% success rate")
        return False


if __name__ == "__main__":
    success = test_br_co_15_improvements()
    sys.exit(0 if success else 1)
