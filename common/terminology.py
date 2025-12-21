#!/usr/bin/env python3
"""
Terminology definitions for e-invoicing field mappings
Centralizes field names and XPath expressions to avoid hardcoding
"""
from typing import Dict, List, NamedTuple
from dataclasses import dataclass


@dataclass
class FieldMapping:
    """Mapping for a specific invoice field with multiple XPath strategies."""
    canonical_name: str
    description: str
    xpath_strategies: List[str]
    validation_pattern: str = None
    data_type: str = "string"


class InvoiceTerminology:
    """Centralized terminology and field mapping definitions."""
    
    # Standard UBL namespace URIs
    NAMESPACES = {
        'ubl': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
        'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2'
    }
    
    # Field mappings for common invoice elements
    FIELDS = {
        'invoice_id': FieldMapping(
            canonical_name='invoice_id',
            description='Unique invoice identifier',
            xpath_strategies=[
                './/cbc:ID',
                './/*[local-name()="ID"]',
                './/ID'
            ],
            data_type='string'
        ),
        'issue_date': FieldMapping(
            canonical_name='issue_date', 
            description='Invoice issue date',
            xpath_strategies=[
                './/cbc:IssueDate',
                './/*[local-name()="IssueDate"]',
                './/IssueDate'
            ],
            validation_pattern=r'^\d{4}-\d{2}-\d{2}$',
            data_type='date'
        ),
        'document_currency': FieldMapping(
            canonical_name='document_currency',
            description='Invoice currency code',
            xpath_strategies=[
                './/cbc:DocumentCurrencyCode',
                './/*[local-name()="DocumentCurrencyCode"]',
                './/DocumentCurrencyCode'
            ],
            validation_pattern=r'^[A-Z]{3}$',
            data_type='string'
        ),
        'profile_id': FieldMapping(
            canonical_name='profile_id',
            description='PEPPOL business process identifier',
            xpath_strategies=[
                './/cbc:ProfileID',
                './/*[local-name()="ProfileID"]',
                './/ProfileID'
            ],
            data_type='string'
        ),
        'customization_id': FieldMapping(
            canonical_name='customization_id',
            description='Document specification identifier',
            xpath_strategies=[
                './/cbc:CustomizationID',
                './/*[local-name()="CustomizationID"]',
                './/CustomizationID'
            ],
            data_type='string'
        ),
        'line_extension_amount': FieldMapping(
            canonical_name='line_extension_amount',
            description='Total line amounts excluding tax',
            xpath_strategies=[
                './/cac:LegalMonetaryTotal/cbc:LineExtensionAmount',
                './/cbc:LineExtensionAmount',
                './/*[local-name()="LegalMonetaryTotal"]/*[local-name()="LineExtensionAmount"]',
                './/*[local-name()="LineExtensionAmount"]'
            ],
            data_type='decimal'
        ),
        'tax_exclusive_amount': FieldMapping(
            canonical_name='tax_exclusive_amount',
            description='Invoice total excluding tax',
            xpath_strategies=[
                './/cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount',
                './/cbc:TaxExclusiveAmount',
                './/*[local-name()="LegalMonetaryTotal"]/*[local-name()="TaxExclusiveAmount"]',
                './/*[local-name()="TaxExclusiveAmount"]'
            ],
            data_type='decimal'
        ),
        'tax_inclusive_amount': FieldMapping(
            canonical_name='tax_inclusive_amount',
            description='Invoice total including tax',
            xpath_strategies=[
                './/cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount',
                './/cbc:TaxInclusiveAmount', 
                './/*[local-name()="LegalMonetaryTotal"]/*[local-name()="TaxInclusiveAmount"]',
                './/*[local-name()="TaxInclusiveAmount"]'
            ],
            data_type='decimal'
        ),
        'payable_amount': FieldMapping(
            canonical_name='payable_amount',
            description='Total amount due for payment',
            xpath_strategies=[
                './/cac:LegalMonetaryTotal/cbc:PayableAmount',
                './/cbc:PayableAmount',
                './/*[local-name()="LegalMonetaryTotal"]/*[local-name()="PayableAmount"]',
                './/*[local-name()="PayableAmount"]'
            ],
            data_type='decimal'
        ),
        'tax_amount': FieldMapping(
            canonical_name='tax_amount',
            description='Total tax amount',
            xpath_strategies=[
                './/cac:TaxTotal/cbc:TaxAmount',
                './/cbc:TaxAmount',
                './/*[local-name()="TaxTotal"]/*[local-name()="TaxAmount"]',
                './/*[local-name()="TaxAmount"]'
            ],
            data_type='decimal'
        ),
        'supplier_name': FieldMapping(
            canonical_name='supplier_name',
            description='Supplier party name',
            xpath_strategies=[
                './/cac:AccountingSupplierParty/cac:Party/cac:PartyName/cbc:Name',
                './/*[local-name()="AccountingSupplierParty"]//*[local-name()="Name"]',
                './/cac:SellerSupplierParty/cac:Party/cac:PartyName/cbc:Name'
            ],
            data_type='string'
        ),
        'customer_name': FieldMapping(
            canonical_name='customer_name',
            description='Customer party name',
            xpath_strategies=[
                './/cac:AccountingCustomerParty/cac:Party/cac:PartyName/cbc:Name',
                './/*[local-name()="AccountingCustomerParty"]//*[local-name()="Name"]',
                './/cac:BuyerCustomerParty/cac:Party/cac:PartyName/cbc:Name'
            ],
            data_type='string'
        )
    }
    
    @classmethod
    def get_field(cls, field_name: str) -> FieldMapping:
        """Get field mapping by canonical name."""
        return cls.FIELDS.get(field_name)
    
    @classmethod
    def get_monetary_fields(cls) -> List[str]:
        """Get list of monetary field names."""
        return [
            name for name, field in cls.FIELDS.items() 
            if field.data_type == 'decimal'
        ]
    
    @classmethod
    def get_identification_fields(cls) -> List[str]:
        """Get list of identification field names.""" 
        return ['profile_id', 'customization_id', 'invoice_id']
    
    @classmethod
    def get_calculation_fields(cls) -> List[str]:
        """Get list of calculation-related field names."""
        return [
            'line_extension_amount', 'tax_exclusive_amount', 
            'tax_inclusive_amount', 'payable_amount', 'tax_amount'
        ]
    
    @classmethod
    def get_field_descriptions(cls) -> Dict[str, str]:
        """
        Get descriptions for all available fields.
        
        Returns:
            Dictionary mapping field names to their descriptions
        """
        return {name: mapping.description for name, mapping in cls.FIELDS.items()}


# Human-readable field descriptions
FIELD_DESCRIPTIONS = {
    'BR-CO-15': {
        'title': 'Invoice Total Calculation',
        'description': 'Validates that payable amount equals tax exclusive amount plus tax amount',
        'calculation': 'Payable Amount = Tax Exclusive Amount + Tax Amount',
        'related_fields': ['payable_amount', 'tax_exclusive_amount', 'tax_amount']
    },
    'BR-CO-16': {
        'title': 'VAT Calculation Consistency', 
        'description': 'Validates that total VAT amount matches sum of line-level VAT amounts',
        'calculation': 'Tax Total Amount = Sum of Line VAT Amounts',
        'related_fields': ['tax_amount']
    },
    'PEPPOL-EN16931-R001': {
        'title': 'Business Process Identification',
        'description': 'Requires ProfileID to identify the PEPPOL business process',
        'expected_values': ['urn:fdc:peppol.eu:2017:poacc:billing:01:1.0'],
        'related_fields': ['profile_id']
    },
    'UBL-CR-001': {
        'title': 'Document Specification',
        'description': 'Requires CustomizationID to identify document specification',
        'expected_values': ['urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0'],
        'related_fields': ['customization_id']
    }
}


# Common XPath utilities
class XPathBuilder:
    """Utility for building robust XPath expressions."""
    
    @staticmethod
    def namespace_aware(element_name: str, namespace_prefix: str = 'cbc') -> str:
        """Build namespace-aware XPath."""
        return f'.//{namespace_prefix}:{element_name}'
    
    @staticmethod
    def local_name(element_name: str) -> str:
        """Build namespace-agnostic XPath using local-name()."""
        return f'.//*[local-name()="{element_name}"]'
    
    @staticmethod
    def simple(element_name: str) -> str:
        """Build simple XPath without namespace."""
        return f'.//{element_name}'
    
    @staticmethod
    def build_strategies(element_name: str, namespace_prefix: str = 'cbc') -> List[str]:
        """Build list of XPath strategies for an element."""
        return [
            XPathBuilder.namespace_aware(element_name, namespace_prefix),
            XPathBuilder.local_name(element_name),
            XPathBuilder.simple(element_name)
        ]
