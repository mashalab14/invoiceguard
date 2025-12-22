from diagnostics.rule_explainers.base import BaseExplainer
from diagnostics.types import ErrorItem, InspectionContext
from common.terminology import InvoiceTerminology, FieldMapping
import logging

logger = logging.getLogger(__name__)


class BrCo15Explainer(BaseExplainer):
    """Explainer for BR-CO-15: Invoice total amount mismatch."""
    
    def explain(self, error: ErrorItem, context: InspectionContext) -> ErrorItem:
        """
        Enrich BR-CO-15 error with specific evidence from the XML.
        
        This rule checks that Tax Inclusive Amount (BT-112) = Tax Exclusive Amount (BT-109) + Tax Amount (BT-110).
        Also detects currency code mismatches which can cause correct math to be rejected.
        """
        try:
            xml_tree = context.xml_tree
            namespaces = context.namespaces
            
            if not xml_tree:
                error["humanized_message"] = (
                    "Invoice total calculation error. Please verify that the Tax Inclusive Amount (BT-112) "
                    "matches the sum of Tax Exclusive Amount (BT-109) and Tax Amount (BT-110)."
                )
                return error
            
            # Extract monetary amounts with robust fallback XPath strategies
            evidence = self._extract_monetary_evidence(xml_tree, namespaces)
            
            if evidence['extraction_successful']:
                # Check if math is correct but currency mismatch might be the issue
                math_correct = self._check_arithmetic(
                    evidence.get('tax_exclusive'),
                    evidence.get('tax_amount'),
                    evidence.get('payable')
                )
                
                # Build specific explanation with extracted values
                explanation_parts = ["Invoice total calculation error."]
                
                if math_correct:
                    # Math is correct, likely a currency mismatch issue
                    explanation_parts.append(
                        f"The calculation appears correct ({evidence['tax_exclusive']} + {evidence['tax_amount'] or '0'} = {evidence['payable']}), "
                        "but the validator rejected it. This is often caused by Currency Code mismatches between "
                        "the Document Currency Code (BT-5) and the currencyID attributes on amount fields. "
                        "Check for other currency-related errors (e.g., PEPPOL-EN16931-R051)."
                    )
                elif evidence['tax_exclusive'] and evidence['payable']:
                    explanation_parts.append(
                        f"The Tax Inclusive Amount (BT-112) does not match the sum of Tax Exclusive Amount (BT-109) plus Tax Amount (BT-110)."
                    )
                    
                    details = []
                    if evidence['tax_exclusive']:
                        details.append(f"Tax Exclusive Amount (BT-109): {evidence['tax_exclusive']}")
                    if evidence['tax_amount']:
                        details.append(f"Tax Amount (BT-110): {evidence['tax_amount']}")
                    else:
                        details.append("Tax Amount (BT-110): (not found or zero)")
                    if evidence['payable']:
                        details.append(f"Tax Inclusive Amount (BT-112): {evidence['payable']}")
                    
                    explanation_parts.append(f"Found: {', '.join(details)}.")
                    explanation_parts.append("Please verify the arithmetic calculation of the invoice totals.")
                else:
                    explanation_parts.append(
                        "Could not extract all required amounts for detailed analysis. "
                        "Please verify that Tax Inclusive Amount (BT-112) = Tax Exclusive Amount (BT-109) + Tax Amount (BT-110)."
                    )
                
                error["humanized_message"] = " ".join(explanation_parts)
            else:
                # Fallback when extraction fails completely
                error["humanized_message"] = (
                    "Invoice total calculation error. Could not extract monetary amounts "
                    "from the invoice XML. Please verify that the Tax Inclusive Amount (BT-112) equals "
                    "the Tax Exclusive Amount (BT-109) plus Tax Amount (BT-110) according to BR-CO-15."
                )
                
        except Exception as e:
            logger.warning(f"Failed to enrich BR-CO-15 error: {e}")
            error["humanized_message"] = (
                "Invoice total calculation error. Please verify that the Tax Inclusive Amount (BT-112) "
                "matches the sum of Tax Exclusive Amount (BT-109) and Tax Amount (BT-110)."
            )
        
        return error
    
    def _check_arithmetic(self, tax_exclusive: str, tax_amount: str, payable: str) -> bool:
        """
        Check if the arithmetic is correct (allowing for rounding tolerance).
        
        Args:
            tax_exclusive: Tax exclusive amount as string
            tax_amount: Tax amount as string (can be None)
            payable: Payable amount as string
            
        Returns:
            True if math is correct within tolerance, False otherwise
        """
        try:
            if not tax_exclusive or not payable:
                return False
            
            exclusive = float(tax_exclusive)
            tax = float(tax_amount) if tax_amount else 0.0
            pay = float(payable)
            
            calculated = exclusive + tax
            
            # Allow for small rounding differences (0.01 tolerance)
            tolerance = 0.01
            return abs(calculated - pay) <= tolerance
            
        except (ValueError, TypeError):
            return False
    
    def _extract_monetary_evidence(self, xml_tree, namespaces: dict) -> dict:
        """
        Extract monetary evidence using terminology system and multiple fallback strategies.
        
        Args:
            xml_tree: The parsed XML tree  
            namespaces: XML namespace mappings
            
        Returns:
            Dictionary with extraction results and success status
        """
        evidence = {
            'extraction_successful': False,
            'tax_exclusive': None,
            'tax_amount': None, 
            'payable': None,
            'extraction_method': None
        }
        
        # Get field mappings from terminology system
        field_mappings = {
            'tax_exclusive': InvoiceTerminology.get_field('tax_exclusive_amount'),
            'tax_amount': InvoiceTerminology.get_field('tax_amount'),
            'payable': InvoiceTerminology.get_field('payable_amount')
        }
        
        # Try extraction using terminology-defined XPath strategies
        extracted_count = 0
        
        for field_name, mapping in field_mappings.items():
            if not mapping:
                logger.debug(f"No terminology mapping found for {field_name}")
                continue
                
            field_value = None
            successful_xpath = None
            
            # Try each XPath strategy for this field
            for xpath in mapping.xpath_strategies:
                try:
                    # Use namespace-aware XPath if available
                    if xpath.startswith('.//cbc:') or xpath.startswith('.//cac:'):
                        if namespaces:
                            elements = xml_tree.xpath(xpath, namespaces=namespaces)
                        else:
                            # Skip namespace-dependent XPaths if no namespaces
                            continue
                    else:
                        # Use simple XPath for local-name and simple queries
                        elements = xml_tree.xpath(xpath)
                    
                    if elements and len(elements) > 0:
                        element = elements[0]
                        text_value = element.text
                        
                        if text_value and text_value.strip():
                            field_value = text_value.strip()
                            successful_xpath = xpath
                            break
                            
                except Exception as e:
                    logger.debug(f"XPath {xpath} failed for {field_name}: {e}")
                    continue
            
            # Store extracted value
            if field_value:
                evidence[field_name] = field_value
                extracted_count += 1
                logger.debug(f"Extracted {field_name}={field_value} using XPath: {successful_xpath}")
            else:
                logger.debug(f"Failed to extract {field_name} using any XPath strategy")
        
        # Consider successful if we got at least payable amount (minimum for BR-CO-15)
        if evidence['payable']:
            evidence['extraction_successful'] = True
            evidence['extraction_method'] = 'terminology_system'
            logger.debug(f"BR-CO-15 extraction successful using terminology system, extracted {extracted_count}/3 fields")
        else:
            logger.debug("BR-CO-15 extraction failed: no payable amount found")
        
        return evidence
        
        return error
