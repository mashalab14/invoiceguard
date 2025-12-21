#!/usr/bin/env python3
"""
PEPPOL-EN16931-R001 Rule Explainer
Handles business process identification validation errors
"""
from typing import Optional
from .base import BaseExplainer
from ..types import ErrorItem, InspectionContext


class PeppolR001Explainer(BaseExplainer):
    """
    PEPPOL-EN16931-R001: Business process MUST be provided
    
    This rule validates that the invoice contains a valid ProfileID
    indicating the business process being used.
    """
    
    def explain(self, error: ErrorItem, context: InspectionContext) -> ErrorItem:
        """
        Enrich PEPPOL-EN16931-R001 error with specific guidance.
        
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
            error["humanized_message"] = "Missing or invalid business process identifier. The invoice must include a ProfileID element specifying the PEPPOL business process (e.g., 'urn:fdc:peppol.eu:2017:poacc:billing:01:1.0')."
        
        return error
    
    def generate_explanation(self, error: ErrorItem, context: InspectionContext) -> Optional[str]:
        """
        Generate human-readable explanation for PEPPOL-EN16931-R001 violations.
        
        Args:
            error: The error item to explain
            context: Inspection context with XML document
            
        Returns:
            Human-readable explanation or None if evidence cannot be extracted
        """
        if not context.xml_tree:
            return "Missing business process identifier. The invoice must include a ProfileID element specifying the PEPPOL BIS process being used (typically 'urn:fdc:peppol.eu:2017:poacc:billing:01:1.0')."
        
        try:
            # Check if ProfileID exists and extract its value
            evidence = self._extract_profile_evidence(context.xml_tree, context.namespaces)
            
            if evidence['profile_id_exists']:
                # ProfileID exists but might be invalid
                if evidence['profile_id_value']:
                    return f"Invalid business process identifier. Found ProfileID: '{evidence['profile_id_value']}'. For PEPPOL BIS 3.0 invoicing, use 'urn:fdc:peppol.eu:2017:poacc:billing:01:1.0'. For credit notes, use 'urn:fdc:peppol.eu:2017:poacc:billing:01:1.0'."
                else:
                    return "Empty business process identifier. The ProfileID element exists but is empty. For PEPPOL BIS 3.0 invoicing, use 'urn:fdc:peppol.eu:2017:poacc:billing:01:1.0'."
            else:
                # ProfileID is completely missing
                return "Missing business process identifier. Add a ProfileID element with value 'urn:fdc:peppol.eu:2017:poacc:billing:01:1.0' for PEPPOL BIS 3.0 invoicing. This identifies which business process the invoice follows."
            
        except Exception:
            # Fallback explanation if evidence extraction fails
            return "Missing or invalid business process identifier. The invoice must include a ProfileID element specifying the PEPPOL business process (e.g., 'urn:fdc:peppol.eu:2017:poacc:billing:01:1.0')."
    
    def _extract_profile_evidence(self, xml_tree, namespaces: dict) -> dict:
        """
        Extract ProfileID evidence from the XML document.
        
        Args:
            xml_tree: The parsed XML tree
            namespaces: XML namespace mappings
            
        Returns:
            Dictionary containing ProfileID evidence
        """
        try:
            evidence = {
                'profile_id_exists': False,
                'profile_id_value': None
            }
            
            # Look for ProfileID element
            profile_id_xpath = ".//cbc:ProfileID"
            profile_elements = xml_tree.xpath(profile_id_xpath, namespaces=namespaces)
            
            if profile_elements:
                evidence['profile_id_exists'] = True
                profile_text = profile_elements[0].text
                evidence['profile_id_value'] = profile_text.strip() if profile_text else ''
            
            return evidence
            
        except Exception:
            return {
                'profile_id_exists': False,
                'profile_id_value': None
            }
