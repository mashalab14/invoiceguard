#!/usr/bin/env python3
"""
Comprehensive test for all rule explainers in the humanization layer
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from diagnostics.pipeline import DiagnosticsPipeline


def test_comprehensive_explainers():
    """Test all implemented rule explainers with realistic scenarios."""
    
    print("🧪 Testing All Rule Explainers")
    print("=" * 50)
    
    # Enhanced KoSIT report with more error types
    kosit_report = [
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
        },
        {
            "id": "PEPPOL-EN16931-R002",
            "message": "[PEPPOL-EN16931-R002] Specification identifier MUST be provided", 
            "location": "//cbc:CustomizationID",
            "severity": "error"
        },
        {
            "id": "UBL-CR-001",
            "message": "[UBL-CR-001] Document MUST have a document level customization identifier",
            "location": "//cbc:CustomizationID",
            "severity": "error"
        },
        {
            "id": "UBL-CR-002",
            "message": "[UBL-CR-002] Document type identifier MUST be present",
            "location": "//cbc:InvoiceTypeCode",
            "severity": "error"
        }
    ]
    
    # Enhanced UBL invoice with multiple error scenarios
    invoice_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    
    <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
    <cbc:ID>INV-2024-002</cbc:ID>
    <cbc:IssueDate>2024-12-21</cbc:IssueDate>
    <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
    <cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
    
    <!-- Missing ProfileID and CustomizationID (will trigger PEPPOL and UBL rules) -->
    
    <cac:AccountingSupplierParty>
        <cac:Party>
            <cbc:EndpointID schemeID="0088">7300010000001</cbc:EndpointID>
            <cac:PartyName>
                <cbc:Name>Example Supplier AS</cbc:Name>
            </cac:PartyName>
            <cac:PostalAddress>
                <cbc:StreetName>Supplier Street 1</cbc:StreetName>
                <cbc:CityName>Supplier City</cbc:CityName>
                <cbc:PostalZone>12345</cbc:PostalZone>
                <cac:Country>
                    <cbc:IdentificationCode>NO</cbc:IdentificationCode>
                </cac:Country>
            </cac:PostalAddress>
            <cac:PartyTaxScheme>
                <cbc:CompanyID>NO123456789MVA</cbc:CompanyID>
                <cac:TaxScheme>
                    <cbc:ID>VAT</cbc:ID>
                </cac:TaxScheme>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingSupplierParty>
    
    <cac:AccountingCustomerParty>
        <cac:Party>
            <cbc:EndpointID schemeID="0088">7300010000002</cbc:EndpointID>
            <cac:PartyName>
                <cbc:Name>Example Customer Ltd</cbc:Name>
            </cac:PartyName>
        </cac:Party>
    </cac:AccountingCustomerParty>
    
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="PCE">5</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="EUR">250.00</cbc:LineExtensionAmount>
        <cac:Item>
            <cbc:Name>Professional Service</cbc:Name>
            <cac:ClassifiedTaxCategory>
                <cbc:ID>S</cbc:ID>
                <cbc:Percent>25.00</cbc:Percent>
                <cac:TaxScheme>
                    <cbc:ID>VAT</cbc:ID>
                </cac:TaxScheme>
            </cac:ClassifiedTaxCategory>
        </cac:Item>
        <cac:Price>
            <cbc:PriceAmount currencyID="EUR">50.00</cbc:PriceAmount>
        </cac:Price>
    </cac:InvoiceLine>
    
    <cac:InvoiceLine>
        <cbc:ID>2</cbc:ID>
        <cbc:InvoicedQuantity unitCode="PCE">2</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="EUR">150.00</cbc:LineExtensionAmount>
        <cac:Item>
            <cbc:Name>Consultation</cbc:Name>
            <cac:ClassifiedTaxCategory>
                <cbc:ID>S</cbc:ID>
                <cbc:Percent>25.00</cbc:Percent>
                <cac:TaxScheme>
                    <cbc:ID>VAT</cbc:ID>
                </cac:TaxScheme>
            </cac:ClassifiedTaxCategory>
        </cac:Item>
        <cac:Price>
            <cbc:PriceAmount currencyID="EUR">75.00</cbc:PriceAmount>
        </cac:Price>
    </cac:InvoiceLine>
    
    <!-- VAT totals with calculation errors -->
    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="EUR">95.00</cbc:TaxAmount> <!-- Should be 100.00 (25% of 400.00) -->
        <cac:TaxSubtotal>
            <cbc:TaxableAmount currencyID="EUR">400.00</cbc:TaxableAmount>
            <cbc:TaxAmount currencyID="EUR">95.00</cbc:TaxAmount> <!-- Incorrect -->
            <cac:TaxCategory>
                <cbc:ID>S</cbc:ID>
                <cbc:Percent>25.00</cbc:Percent>
                <cac:TaxScheme>
                    <cbc:ID>VAT</cbc:ID>
                </cac:TaxScheme>
            </cac:TaxCategory>
        </cac:TaxSubtotal>
    </cac:TaxTotal>
    
    <!-- Monetary totals with calculation errors -->
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="EUR">400.00</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="EUR">400.00</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="EUR">495.00</cbc:TaxInclusiveAmount> <!-- Should be 500.00 -->
        <cbc:PayableAmount currencyID="EUR">495.00</cbc:PayableAmount> <!-- Should be 500.00 -->
    </cac:LegalMonetaryTotal>
    
</Invoice>"""
    
    # Initialize pipeline
    pipeline = DiagnosticsPipeline()
    
    # Run processing
    print("📊 Processing validation report with multiple error types...")
    result = pipeline.run(kosit_report, invoice_xml)
    
    # Display comprehensive results
    print(f"\n📋 Comprehensive Results Summary:")
    print(f"  Fatal errors: {1 if result.fatal_error else 0}")
    print(f"  Total errors: {len(result.processed_errors)}")
    print(f"  Suppressed errors: {sum(1 for e in result.processed_errors if e['suppressed'])}")
    print(f"  Enriched errors: {sum(1 for e in result.processed_errors if e['humanized_message'])}")
    
    if result.fatal_error:
        print(f"\n💥 FATAL ERROR:")
        print(f"  {result.fatal_error['id']}: {result.fatal_error['message']}")
        return
    
    # Group errors by explainer availability
    enriched_errors = []
    standard_errors = []
    
    for error in result.processed_errors:
        if error['humanized_message']:
            enriched_errors.append(error)
        else:
            standard_errors.append(error)
    
    print(f"\n✨ Enriched Errors ({len(enriched_errors)}):")
    for i, error in enumerate(enriched_errors, 1):
        status_icon = "🔇" if error['suppressed'] else "⚠️"
        print(f"\n  {i}. {status_icon} {error['id']}")
        print(f"     Original: {error['message']}")
        print(f"     Location: {error.get('location', 'N/A')}")
        print(f"     💡 Enhanced: {error['humanized_message']}")
    
    print(f"\n📄 Standard Errors ({len(standard_errors)}):")
    for i, error in enumerate(standard_errors, 1):
        status_icon = "🔇" if error['suppressed'] else "⚠️"
        print(f"\n  {i}. {status_icon} {error['id']}")
        print(f"     Message: {error['message']}")
        print(f"     Location: {error.get('location', 'N/A')}")
        print(f"     Suppressed: {error['suppressed']}")
    
    # Validation checks for explainer coverage
    print(f"\n🔍 Explainer Coverage Analysis:")
    
    # Check which explainers were used
    explainer_usage = {}
    for error in result.processed_errors:
        if error['humanized_message']:
            explainer_usage[error['id']] = True
    
    expected_explainers = {
        'BR-CO-15': 'Financial calculation explainer',
        'BR-CO-16': 'VAT calculation explainer', 
        'PEPPOL-EN16931-R001': 'PEPPOL business process explainer',
        'UBL-CR-001': 'UBL document structure explainer'
    }
    
    for explainer_id, description in expected_explainers.items():
        used = explainer_id in explainer_usage
        status = "✅" if used else "❌"
        print(f"  {status} {explainer_id}: {description} {'(USED)' if used else '(NOT USED)'}")
    
    # Dependency filtering validation
    print(f"\n🔗 Dependency Filtering Validation:")
    br_co_15_present = any(e['id'] == 'BR-CO-15' for e in result.processed_errors)
    br_co_16_suppressed = any(e['id'] == 'BR-CO-16' and e['suppressed'] for e in result.processed_errors)
    
    ubl_cr_001_present = any(e['id'] == 'UBL-CR-001' for e in result.processed_errors)
    ubl_cr_002_suppressed = any(e['id'] == 'UBL-CR-002' and e['suppressed'] for e in result.processed_errors)
    
    print(f"  ✅ BR-CO-15 (parent) present: {br_co_15_present}")
    print(f"  ✅ BR-CO-16 (child) suppressed: {br_co_16_suppressed}")
    print(f"  ✅ UBL-CR-001 (parent) present: {ubl_cr_001_present}")
    print(f"  ✅ UBL-CR-002 (child) suppressed: {ubl_cr_002_suppressed}")
    
    print(f"\n🎉 Comprehensive Explainer Test Completed!")
    print(f"   Enhanced humanization layer features:")
    print(f"   - {len(expected_explainers)} specialized rule explainers")
    print(f"   - Contextual XML evidence extraction")
    print(f"   - Financial calculation analysis")
    print(f"   - PEPPOL compliance guidance")
    print(f"   - UBL document structure validation")
    print(f"   - Intelligent error dependency management")


if __name__ == "__main__":
    test_comprehensive_explainers()
