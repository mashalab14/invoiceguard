#!/usr/bin/env python3
"""
BR-CO-16 Rule Explainer
Handles VAT category tax amount validation errors with contextual evidence extraction
"""
from typing import Optional
from .base import BaseExplainer
from ..types import ErrorItem, InspectionContext


class BrCo16Explainer(BaseExplainer):
    """
    BR-CO-16: VAT category tax amount MUST equal the sum of Invoice line VAT amounts
    
    This rule validates that the total VAT amount declared in tax totals
    matches the sum of VAT amounts from all invoice lines.
    """
    
    def explain(self, error: ErrorItem, context: InspectionContext) -> ErrorItem:
        """
        Enrich BR-CO-16 error with specific evidence from the XML.
        
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
            # Fallback to generic explanation if evidence extraction fails
            error["humanized_message"] = "VAT calculation error. The declared total VAT amount does not match the sum of VAT amounts from invoice lines. Please check your VAT calculations."
        
        return error
    
    def generate_explanation(self, error: ErrorItem, context: InspectionContext) -> Optional[str]:
        """
        Generate human-readable explanation for BR-CO-16 violations.
        
        Args:
            error: The error item to explain
            context: Inspection context with XML document
            
        Returns:
            Human-readable explanation or None if evidence cannot be extracted
        """
        if not context.xml_tree:
            return "VAT calculation error. The total VAT amount in tax totals does not match the sum of line-level VAT amounts. Please verify VAT calculations across all invoice lines."
        
        try:
            # Extract VAT-related amounts from XML
            evidence = self._extract_vat_evidence(context.xml_tree, context.namespaces)
            
            if not evidence:
                return "VAT calculation error. Unable to extract tax amounts from the invoice. Please verify that all VAT amounts are correctly calculated and declared."
            
            # Build detailed explanation with evidence
            explanation_parts = [
                "VAT calculation mismatch detected.",
                f"Total VAT Amount declared: {evidence['total_vat_amount']}",
                f"Number of invoice lines: {evidence['line_count']}"
            ]
            
            if evidence['line_vat_amounts']:
                line_total = sum(float(amount) for amount in evidence['line_vat_amounts'] if amount)
                explanation_parts.append(f"Sum of line VAT amounts: {line_total:.2f}")
                explanation_parts.append(f"Line VAT details: {', '.join(evidence['line_vat_amounts'])}")
            
            explanation_parts.append("Please verify that the total VAT amount equals the sum of all line-level VAT calculations.")
            
            return " ".join(explanation_parts)
            
        except Exception:
            # Fallback explanation if evidence extraction fails
            return "VAT calculation error. The declared total VAT amount does not match the sum of VAT amounts from invoice lines. Please check your VAT calculations."
    
    def _extract_vat_evidence(self, xml_tree, namespaces: dict) -> Optional[dict]:
        """
        Extract VAT-related evidence from the XML document.
        
        Args:
            xml_tree: The parsed XML tree
            namespaces: XML namespace mappings
            
        Returns:
            Dictionary containing VAT evidence or None if extraction fails
        """
        try:
            evidence = {
                'total_vat_amount': 'N/A',
                'line_count': 0,
                'line_vat_amounts': []
            }
            
            # Extract total VAT amount from tax totals
            tax_total_xpath = ".//cac:TaxTotal/cbc:TaxAmount"
            tax_total_elements = xml_tree.xpath(tax_total_xpath, namespaces=namespaces)
            if tax_total_elements:
                evidence['total_vat_amount'] = tax_total_elements[0].text or '0.00'
            
            # Extract VAT amounts from invoice lines
            line_xpath = ".//cac:InvoiceLine"
            line_elements = xml_tree.xpath(line_xpath, namespaces=namespaces)
            evidence['line_count'] = len(line_elements)
            
            # Look for line-level VAT amounts (various possible locations)
            for line in line_elements:
                # Check for line VAT total
                line_vat_xpath = ".//cac:TaxTotal/cbc:TaxAmount"
                line_vat_elements = line.xpath(line_vat_xpath, namespaces=namespaces)
                
                if line_vat_elements:
                    vat_amount = line_vat_elements[0].text or '0.00'
                    evidence['line_vat_amounts'].append(vat_amount)
                else:
                    # Calculate from line extension amount and tax rate if available
                    line_amount_xpath = ".//cbc:LineExtensionAmount"
                    tax_percent_xpath = ".//cac:ClassifiedTaxCategory/cbc:Percent"
                    
                    amount_elements = line.xpath(line_amount_xpath, namespaces=namespaces)
                    percent_elements = line.xpath(tax_percent_xpath, namespaces=namespaces)
                    
                    if amount_elements and percent_elements:
                        try:
                            line_amount = float(amount_elements[0].text or '0')
                            tax_percent = float(percent_elements[0].text or '0')
                            calculated_vat = line_amount * (tax_percent / 100)
                            evidence['line_vat_amounts'].append(f"{calculated_vat:.2f}")
                        except ValueError:
                            evidence['line_vat_amounts'].append('0.00')
                    else:
                        evidence['line_vat_amounts'].append('0.00')
            
            return evidence
            
        except Exception:
            return None
