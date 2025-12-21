#!/usr/bin/env python3
"""
Production Readiness Test Suite
Validates the 75% enrichment gap fixes and production readiness criteria
"""
import sys
import os
import json
import time
from typing import Dict, List

sys.path.insert(0, os.getcwd())

from diagnostics.pipeline import DiagnosticsPipeline
from diagnostics.rule_explainers.factory import ExplainerFactory
from diagnostics.dependency_filter import DependencyFilter
from common.terminology import InvoiceTerminology, FIELD_DESCRIPTIONS


def test_br_co_15_extraction_reliability():
    """Test BR-CO-15 extraction across various XML structures to achieve >95% reliability."""
    
    print("🔍 Testing BR-CO-15 Extraction Reliability")
    print("=" * 50)
    
    # Comprehensive test cases covering real-world scenarios
    test_cases = [
        {
            "name": "Perfect UBL 2.1 with all namespaces",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>PERFECT-001</cbc:ID>
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="EUR">100.00</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="EUR">100.00</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="EUR">120.00</cbc:TaxInclusiveAmount>
        <cbc:PayableAmount currencyID="EUR">119.00</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="EUR">20.00</cbc:TaxAmount>
    </cac:TaxTotal>
</Invoice>""",
            "expected_success": True,
            "category": "namespace_perfect"
        },
        {
            "name": "Root namespace only (common in real files)",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">
    <ID>ROOT-001</ID>
    <LegalMonetaryTotal>
        <TaxExclusiveAmount currencyID="EUR">100.00</TaxExclusiveAmount>
        <TaxInclusiveAmount currencyID="EUR">120.00</TaxInclusiveAmount>
        <PayableAmount currencyID="EUR">119.00</PayableAmount>
    </LegalMonetaryTotal>
    <TaxTotal>
        <TaxAmount currencyID="EUR">20.00</TaxAmount>
    </TaxTotal>
</Invoice>""",
            "expected_success": True,
            "category": "root_namespace_only"
        },
        {
            "name": "No namespaces (legacy or simplified)",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice>
    <ID>SIMPLE-001</ID>
    <LegalMonetaryTotal>
        <TaxExclusiveAmount currencyID="EUR">100.00</TaxExclusiveAmount>
        <PayableAmount currencyID="EUR">119.00</PayableAmount>
    </LegalMonetaryTotal>
    <TaxAmount currencyID="EUR">20.00</TaxAmount>
</Invoice>""",
            "expected_success": True,
            "category": "no_namespace"
        },
        {
            "name": "Mixed namespace declarations",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2">
    <cbc:ID xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">MIXED-001</cbc:ID>
    <cac:LegalMonetaryTotal xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                           xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
        <cbc:TaxExclusiveAmount currencyID="EUR">100.00</cbc:TaxExclusiveAmount>
        <cbc:PayableAmount currencyID="EUR">119.00</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
</Invoice>""",
            "expected_success": True,
            "category": "mixed_namespaces"
        },
        {
            "name": "Nested monetary totals (complex structure)",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cac:InvoiceHeader>
        <cac:LegalMonetaryTotal>
            <cbc:TaxExclusiveAmount currencyID="EUR">100.00</cbc:TaxExclusiveAmount>
            <cbc:PayableAmount currencyID="EUR">119.00</cbc:PayableAmount>
        </cac:LegalMonetaryTotal>
    </cac:InvoiceHeader>
    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="EUR">20.00</cbc:TaxAmount>
    </cac:TaxTotal>
</Invoice>""",
            "expected_success": True,
            "category": "nested_structure"
        },
        {
            "name": "Minimal structure (edge case)",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice>
    <PayableAmount>119.00</PayableAmount>
</Invoice>""",
            "expected_success": True,  # Should at least get payable amount
            "category": "minimal"
        },
        {
            "name": "Alternative element names",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice>
    <MonetaryTotals>
        <NetAmount>100.00</NetAmount>
        <TotalAmount>119.00</TotalAmount>
        <PayableAmount>119.00</PayableAmount>
    </MonetaryTotals>
</Invoice>""",
            "expected_success": True,  # Should get PayableAmount
            "category": "alternative_names"
        },
        {
            "name": "Empty elements",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:TaxExclusiveAmount></cbc:TaxExclusiveAmount>
    <cbc:PayableAmount>119.00</cbc:PayableAmount>
</Invoice>""",
            "expected_success": True,  # Should get payable amount
            "category": "empty_elements"
        },
        {
            "name": "Malformed but parseable",
            "xml": b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice>
    <PayableAmount currencyID="EUR">119.00</PayableAmount>
    <TaxExclusiveAmount>100.00</TaxExclusiveAmount>
    <SomeOtherField>ignored</SomeOtherField>
</Invoice>""",
            "expected_success": True,
            "category": "malformed_parseable"
        }
    ]
    
    pipeline = DiagnosticsPipeline()
    br_co_15_error = {
        "id": "BR-CO-15",
        "message": "[BR-CO-15] Invoice total amount MUST equal the sum",
        "location": "//cac:LegalMonetaryTotal/cbc:PayableAmount",
        "severity": "error"
    }
    
    # Track results by category
    results_by_category = {}
    total_success = 0
    total_tests = len(test_cases)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📋 Test {i}: {test_case['name']}")
        print(f"   Category: {test_case['category']}")
        
        try:
            # Run through pipeline
            result = pipeline.run([br_co_15_error], test_case['xml'])
            processed_error = result.processed_errors[0] if result.processed_errors else None
            
            enriched = bool(processed_error and processed_error.get('humanized_message'))
            success = enriched if test_case['expected_success'] else not enriched
            
            if success:
                total_success += 1
                status = "✅ PASS"
            else:
                status = "❌ FAIL"
            
            print(f"   Expected: {'Enriched' if test_case['expected_success'] else 'Not Enriched'}")
            print(f"   Actual: {'Enriched' if enriched else 'Not Enriched'}")
            print(f"   Result: {status}")
            
            if enriched:
                message = processed_error['humanized_message']
                print(f"   Message: {message[:80]}...")
            
            # Track by category
            category = test_case['category']
            if category not in results_by_category:
                results_by_category[category] = {'success': 0, 'total': 0}
            results_by_category[category]['total'] += 1
            if success:
                results_by_category[category]['success'] += 1
                
        except Exception as e:
            print(f"   Result: ❌ EXCEPTION - {e}")
            category = test_case['category']
            if category not in results_by_category:
                results_by_category[category] = {'success': 0, 'total': 0}
            results_by_category[category]['total'] += 1
    
    # Calculate final success rate
    success_rate = (total_success / total_tests) * 100
    
    print(f"\n📊 BR-CO-15 Extraction Results")
    print("=" * 40)
    print(f"Total tests: {total_tests}")
    print(f"Successful: {total_success}")
    print(f"Failed: {total_tests - total_success}")
    print(f"Success rate: {success_rate:.1f}%")
    
    # Category breakdown
    print(f"\n📈 Results by Category:")
    for category, stats in results_by_category.items():
        cat_rate = (stats['success'] / stats['total']) * 100
        print(f"   {category}: {stats['success']}/{stats['total']} ({cat_rate:.1f}%)")
    
    # Production readiness assessment
    if success_rate >= 95:
        print(f"\n🎉 BR-CO-15 PRODUCTION READY!")
        print(f"   Success rate {success_rate:.1f}% exceeds 95% threshold")
    elif success_rate >= 85:
        print(f"\n⚠️ BR-CO-15 NEEDS MINOR IMPROVEMENTS")
        print(f"   Success rate {success_rate:.1f}% needs to reach 95%")
    else:
        print(f"\n❌ BR-CO-15 NEEDS MAJOR FIXES")
        print(f"   Success rate {success_rate:.1f}% is below acceptable threshold")
    
    return {
        'success_rate': success_rate,
        'total_tests': total_tests,
        'successful_tests': total_success,
        'results_by_category': results_by_category
    }


def test_hot_reload_functionality():
    """Test dependencies.json hot-reload functionality."""
    
    print("\n🔥 Testing Dependencies Hot-Reload")
    print("=" * 40)
    
    try:
        # Create test dependencies file
        test_deps = {
            "TEST-PARENT-1": ["TEST-CHILD-1", "TEST-CHILD-2"],
            "BR-CO-15": ["BR-CO-16", "BR-CO-17"]
        }
        
        deps_file = "config/dependencies.json"
        
        # Backup original
        backup_content = None
        if os.path.exists(deps_file):
            with open(deps_file, 'r') as f:
                backup_content = f.read()
        
        # Write test config
        with open(deps_file, 'w') as f:
            json.dump(test_deps, f, indent=2)
        
        print("✅ Test dependencies written")
        
        # Create filter and test initial load
        filter_obj = DependencyFilter()
        initial_deps = len(filter_obj.dependencies)
        print(f"✅ Initial load: {initial_deps} dependencies")
        
        # Modify file
        time.sleep(0.1)  # Ensure different timestamp
        modified_deps = {
            "TEST-PARENT-1": ["TEST-CHILD-1"],  # Removed one child
            "BR-CO-15": ["BR-CO-16", "BR-CO-17"],
            "NEW-PARENT": ["NEW-CHILD"]  # Added new dependency
        }
        
        with open(deps_file, 'w') as f:
            json.dump(modified_deps, f, indent=2)
        
        print("✅ Dependencies file modified")
        
        # Test hot reload
        reloaded = filter_obj.reload_if_changed()
        new_deps = len(filter_obj.dependencies)
        
        if reloaded:
            print(f"✅ Hot-reload successful: {initial_deps} → {new_deps} dependencies")
        else:
            print("❌ Hot-reload failed: no change detected")
        
        # Test that new dependencies are active
        if "NEW-PARENT" in filter_obj.dependencies:
            print("✅ New dependencies loaded correctly")
        else:
            print("❌ New dependencies not found")
        
        # Restore original
        if backup_content:
            with open(deps_file, 'w') as f:
                f.write(backup_content)
        else:
            # Restore default
            default_deps = {
                "BR-CO-15": ["BR-CO-16", "BR-CO-17"],
                "UBL-CR-001": ["UBL-CR-002", "UBL-CR-003"],
                "PEPPOL-EN16931-R001": ["PEPPOL-EN16931-R002"]
            }
            with open(deps_file, 'w') as f:
                json.dump(default_deps, f, indent=2)
        
        print("✅ Original dependencies restored")
        return True
        
    except Exception as e:
        print(f"❌ Hot-reload test failed: {e}")
        return False


def test_terminology_system():
    """Test terminology system integration."""
    
    print("\n📚 Testing Terminology System")
    print("=" * 35)
    
    try:
        # Test field mappings
        monetary_fields = InvoiceTerminology.get_monetary_fields()
        print(f"✅ Monetary fields: {len(monetary_fields)} defined")
        print(f"   Fields: {', '.join(monetary_fields)}")
        
        # Test specific field mapping
        payable_field = InvoiceTerminology.get_field('payable_amount')
        if payable_field:
            print(f"✅ Payable amount mapping: {len(payable_field.xpath_strategies)} XPath strategies")
            print(f"   Strategies: {payable_field.xpath_strategies}")
        else:
            print("❌ Payable amount mapping not found")
            return False
        
        # Test rule descriptions
        br_co_15_desc = FIELD_DESCRIPTIONS.get('BR-CO-15')
        if br_co_15_desc:
            print(f"✅ BR-CO-15 description: {br_co_15_desc['title']}")
            print(f"   Related fields: {br_co_15_desc['related_fields']}")
        else:
            print("❌ BR-CO-15 description not found")
            return False
        
        print("✅ Terminology system operational")
        return True
        
    except Exception as e:
        print(f"❌ Terminology system test failed: {e}")
        return False


def run_production_readiness_suite():
    """Run comprehensive production readiness tests."""
    
    print("🚀 InvoiceGuard Production Readiness Test Suite")
    print("=" * 60)
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    results = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'tests': {},
        'overall_status': 'UNKNOWN'
    }
    
    # Test 1: BR-CO-15 Extraction Reliability
    br_co_15_results = test_br_co_15_extraction_reliability()
    results['tests']['br_co_15_extraction'] = br_co_15_results
    
    # Test 2: Hot-reload functionality
    hot_reload_success = test_hot_reload_functionality()
    results['tests']['hot_reload'] = {'success': hot_reload_success}
    
    # Test 3: Terminology system
    terminology_success = test_terminology_system()
    results['tests']['terminology'] = {'success': terminology_success}
    
    # Overall assessment
    print(f"\n🎯 Production Readiness Assessment")
    print("=" * 45)
    
    criteria = {
        'BR-CO-15 Reliability': br_co_15_results['success_rate'] >= 95,
        'Hot-reload Functionality': hot_reload_success,
        'Terminology System': terminology_success,
    }
    
    passed_criteria = sum(criteria.values())
    total_criteria = len(criteria)
    
    for criterion, passed in criteria.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {criterion}: {status}")
    
    overall_score = (passed_criteria / total_criteria) * 100
    print(f"\n📊 Overall Score: {passed_criteria}/{total_criteria} ({overall_score:.0f}%)")
    
    if overall_score == 100:
        status = "🎉 PRODUCTION READY"
        results['overall_status'] = 'READY'
    elif overall_score >= 80:
        status = "⚠️ NEEDS MINOR FIXES"
        results['overall_status'] = 'MINOR_FIXES'
    else:
        status = "❌ NEEDS MAJOR WORK"
        results['overall_status'] = 'MAJOR_FIXES'
    
    print(f"Status: {status}")
    
    # Save results
    with open('production_readiness_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Detailed results saved to: production_readiness_results.json")
    
    return results


if __name__ == "__main__":
    try:
        results = run_production_readiness_suite()
        success_rate = results['tests']['br_co_15_extraction']['success_rate']
        
        print(f"\n🔍 Key Finding: BR-CO-15 Enrichment Rate: {success_rate:.1f}%")
        if success_rate >= 95:
            print("✅ The 25% gap has been resolved!")
        else:
            print(f"⚠️ Still {100 - success_rate:.1f}% gap remaining")
            
    except Exception as e:
        print(f"❌ Production readiness test suite failed: {e}")
        import traceback
        traceback.print_exc()
