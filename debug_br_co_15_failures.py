#!/usr/bin/env python3
"""
BR-CO-15 Enrichment Failure Analysis
Investigates the 25% gap in det    ]
    
    pipeline = DiagnosticsPipeline()
    explainer = BrCo15Explainer()
    xml_loader = SafeXMLLoader()
    
    success_count = 0
    failure_count = 0tic math enrichment
"""
import sys
import os
sys.path.insert(0, os.getcwd())

from diagnostics.pipeline import DiagnosticsPipeline
from diagnostics.rule_explainers.br_co_15 import BrCo15Explainer
from common.xml_loader import SafeXMLLoader


def analyze_br_co_15_failures():
    """Deep dive into BR-CO-15 enrichment failures."""
    
    print("🔍 BR-CO-15 Enrichment Failure Analysis")
    print("=" * 50)
    
    xml_loader = SafeXMLLoader()
    explainer = BrCo15Explainer()
    
    # Test scenarios with different XML structures
    test_cases = [
        {
            "name": "Perfect UBL 2.1 with namespaces",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>TEST-001</cbc:ID>
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="EUR">100.00</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="EUR">100.00</cbc:TaxExclusiveAmount>
        <cbc:TaxAmount currencyID="EUR">20.00</cbc:TaxAmount>
        <cbc:TaxInclusiveAmount currencyID="EUR">120.00</cbc:TaxInclusiveAmount>
        <cbc:PayableAmount currencyID="EUR">119.00</cbc:PayableAmount> <!-- Error: should be 120.00 -->
    </cac:LegalMonetaryTotal>
</Invoice>"""
        },
        {
            "name": "Missing namespace declarations",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice>
    <ID>TEST-002</ID>
    <LegalMonetaryTotal>
        <TaxExclusiveAmount currencyID="EUR">100.00</TaxExclusiveAmount>
        <TaxAmount currencyID="EUR">20.00</TaxAmount>
        <PayableAmount currencyID="EUR">119.00</PayableAmount>
    </LegalMonetaryTotal>
</Invoice>"""
        },
        {
            "name": "Mixed namespace usage",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">
    <cbc:ID xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">TEST-003</cbc:ID>
    <cac:LegalMonetaryTotal xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2">
        <cbc:TaxExclusiveAmount xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" currencyID="EUR">100.00</cbc:TaxExclusiveAmount>
        <cbc:PayableAmount xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2" currencyID="EUR">119.00</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
</Invoice>"""
        },
        {
            "name": "Minimal structure",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice>
    <PayableAmount>119.00</PayableAmount>
    <TaxExclusiveAmount>100.00</TaxExclusiveAmount>
</Invoice>"""
        },
        {
            "name": "Nested structure",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="EUR">100.00</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="EUR">100.00</cbc:TaxExclusiveAmount>
        <cbc:PayableAmount currencyID="EUR">119.00</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="EUR">20.00</cbc:TaxAmount>
    </cac:TaxTotal>
</Invoice>"""
        }
    ]
    
    br_co_15_error = {
        "id": "BR-CO-15",
        "message": "[BR-CO-15] Invoice total amount MUST equal the sum of Invoice line net amounts plus the Invoice total VAT amount",
        "location": "//cac:LegalMonetaryTotal/cbc:PayableAmount",
        "severity": "error"
    }
    
    pipeline = DiagnosticsPipeline()
    explainer = BrCo15Explainer()        xml_loader = SafeXMLLoader()
    
    success_count = 0
    failure_count = 0
    failure_details = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📋 Test Case {i}: {test_case['name']}")
        print("-" * 40)
        
        try:
            # Test XML loading and namespace detection
            xml_tree = xml_loader.load_xml(test_case['xml'])
            namespaces = xml_loader.extract_namespaces(xml_tree)
            
            print(f"   XML parsed: ✅")
            print(f"   Namespaces: {list(namespaces.keys()) if namespaces else 'None'}")
            
            # Test pipeline processing
            result = pipeline.run([br_co_15_error], test_case['xml'])
            processed_error = result.processed_errors[0]
            
            if processed_error.get('humanized_message'):
                success_count += 1
                print(f"   Enrichment: ✅")
                print(f"   Message: {processed_error['humanized_message'][:100]}...")
            else:
                failure_count += 1
                print(f"   Enrichment: ❌ FAILED")
                
                # Debug the specific failure
                from diagnostics.types import InspectionContext
                context = InspectionContext(
                    xml_tree=xml_tree,
                    namespaces=namespaces,
                    original_invoice=test_case['xml']
                )
                
                # Try to understand why it failed
                try:
                    test_error = {
                        "id": "BR-CO-15",
                        "message": br_co_15_error["message"],
                        "location": br_co_15_error["location"],
                        "severity": "error",
                        "humanized_message": None,
                        "suppressed": False
                    }
                    
                    enriched = explainer.explain(test_error, context)
                    
                    if enriched.get('humanized_message'):
                        print(f"   Direct explainer: ✅ (pipeline issue)")
                    else:
                        print(f"   Direct explainer: ❌ (extraction issue)")
                        
                        # Test XML extraction directly
                        if xml_tree is not None:
                            root = xml_tree.getroot()
                            
                            # Test different XPath approaches
                            xpath_tests = [
                                (".//cbc:TaxExclusiveAmount", "Standard cbc namespace"),
                                (".//TaxExclusiveAmount", "No namespace"),
                                (".//*[local-name()='TaxExclusiveAmount']", "Local name"),
                                (".//cbc:PayableAmount", "Payable amount cbc"),
                                (".//*[local-name()='PayableAmount']", "Payable amount local")
                            ]
                            
                            for xpath, description in xpath_tests:
                                try:
                                    if 'cbc:' in xpath and 'cbc' in namespaces:
                                        elements = root.xpath(xpath, namespaces=namespaces)
                                    else:
                                        elements = xml_tree.xpath(xpath)
                                    
                                    if elements:
                                        value = elements[0].text if hasattr(elements[0], 'text') else str(elements[0])
                                        print(f"     {description}: ✅ → {value}")
                                    else:
                                        print(f"     {description}: ❌")
                                except Exception as e:
                                    print(f"     {description}: ❌ ({str(e)[:30]})")
                        
                except Exception as debug_e:
                    print(f"   Debug failed: {debug_e}")
                
                failure_details.append({
                    'case': test_case['name'],
                    'namespaces': list(namespaces.keys()) if namespaces else [],
                    'xml_size': len(test_case['xml'])
                })
        
        except Exception as e:
            failure_count += 1
            print(f"   EXCEPTION: {e}")
            failure_details.append({
                'case': test_case['name'],
                'error': str(e),
                'xml_size': len(test_case['xml'])
            })
    
    # Summary analysis
    print(f"\n📊 Analysis Results")
    print("=" * 30)
    print(f"Total test cases: {len(test_cases)}")
    print(f"Successful enrichments: {success_count}")
    print(f"Failed enrichments: {failure_count}")
    print(f"Success rate: {success_count / len(test_cases) * 100:.1f}%")
    print(f"Failure rate: {failure_count / len(test_cases) * 100:.1f}%")
    
    if failure_details:
        print(f"\n🔍 Failure Pattern Analysis:")
        namespace_failures = sum(1 for f in failure_details if not f.get('namespaces'))
        exception_failures = sum(1 for f in failure_details if 'error' in f)
        extraction_failures = failure_count - exception_failures
        
        print(f"   Namespace issues: {namespace_failures}")
        print(f"   Extraction issues: {extraction_failures}")
        print(f"   Exception errors: {exception_failures}")
        
        for failure in failure_details:
            print(f"   - {failure['case']}: {failure.get('error', 'extraction failed')}")
    
    return {
        'success_rate': success_count / len(test_cases) * 100,
        'failure_details': failure_details,
        'total_cases': len(test_cases)
    }


if __name__ == "__main__":
    analyze_br_co_15_failures()
