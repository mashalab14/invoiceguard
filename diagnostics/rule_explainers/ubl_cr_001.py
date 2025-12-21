#!/usr/bin/env python3
"""
UBL-CR-001 Rule Explainer  
Handles UBL document structure validation errors
"""
from typing import Optional
from .base import BaseExplainer
from ..types import ErrorItem, InspectionContext


class UblCr001Explainer(BaseExplainer):
    """
    UBL-CR-001: Document MUST have a document level customization identifier
    
    This rule validates that the UBL document contains a proper
    CustomizationID identifying the document specification.
    """
    
    def explain(self, error: ErrorItem, context: InspectionContext) -> ErrorItem:
        """
        Enrich UBL-CR-001 error with specific guidance.
        
        Args:
            error: The error item to enrich
            context: Inspection context with XML document
            
        Returns:
            The enriched error item (mutated in place)
        """
        try:
            humanized_message = self.generate_explanation(error, context)
            if humanized_message:
                error["humanized_message"] = humanized_message
        except Exception:
            # Fallback to generic explanation
            error["humanized_message"] = "Missing document specification identifier. The document must include a CustomizationID element that identifies the specification being used (e.g., 'urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0')."
        
        return error
    
    def generate_explanation(self, error: ErrorItem, context: InspectionContext) -> Optional[str]:
        """
        Generate human-readable explanation for UBL-CR-001 violations.
        
        Args:
            error: The error item to explain
            context: Inspection context with XML document
            
        Returns:
            Human-readable explanation or None if evidence cannot be extracted
        """
        if not context.xml_tree:
            return "Missing document specification identifier. The document must include a CustomizationID element that identifies the specification being used (e.g., 'urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0')."
        
        try:
            # Check CustomizationID and document type
            evidence = self._extract_customization_evidence(context.xml_tree, context.namespaces)
            
            explanation_parts = []
            
            if evidence['customization_id_exists']:
                if evidence['customization_id_value']:
                    explanation_parts.append(f"Invalid document specification identifier. Found CustomizationID: '{evidence['customization_id_value']}'.")
                    explanation_parts.append("For PEPPOL BIS 3.0, use 'urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0'.")
                else:
                    explanation_parts.append("Empty document specification identifier. The CustomizationID element exists but is empty.")
                    explanation_parts.append("For PEPPOL BIS 3.0, use 'urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0'.")
            else:
                explanation_parts.append("Missing document specification identifier. Add a CustomizationID element.")
                explanation_parts.append("For PEPPOL BIS 3.0, use 'urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0'.")
            
            # Add document type context
            if evidence['document_type']:
                explanation_parts.append(f"Document type detected: {evidence['document_type']}.")
            
            explanation_parts.append("This identifier specifies which business document specification and rules the document should comply with.")
            
            return " ".join(explanation_parts)
            
        except Exception:
            # Fallback explanation if evidence extraction fails
            return "Missing or invalid document specification identifier. The document must include a CustomizationID element identifying the specification (e.g., PEPPOL BIS 3.0: 'urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0')."
    
    def _extract_customization_evidence(self, xml_tree, namespaces: dict) -> dict:
        """
        Extract CustomizationID evidence from the XML document.
        
        Args:
            xml_tree: The parsed XML tree
            namespaces: XML namespace mappings
            
        Returns:
            Dictionary containing customization evidence
        """
        try:
            evidence = {
                'customization_id_exists': False,
                'customization_id_value': None,
                'document_type': None
            }
            
            # Look for CustomizationID element
            customization_xpath = ".//cbc:CustomizationID"
            customization_elements = xml_tree.xpath(customization_xpath, namespaces=namespaces)
            
            if customization_elements:
                evidence['customization_id_exists'] = True
                customization_text = customization_elements[0].text
                evidence['customization_id_value'] = customization_text.strip() if customization_text else ''
            
            # Try to determine document type from root element
            root_element = xml_tree.getroot()
            if root_element is not None:
                root_tag = root_element.tag
                # Remove namespace prefix for readability
                if '}' in root_tag:
                    root_tag = root_tag.split('}')[1]
                evidence['document_type'] = root_tag
            
            return evidence
            
        except Exception:
            return {
                'customization_id_exists': False,
                'customization_id_value': None,
                'document_type': None
            }
