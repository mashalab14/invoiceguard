from diagnostics.rule_explainers.base import BaseExplainer
from diagnostics.types import ErrorItem, InspectionContext
import logging

logger = logging.getLogger(__name__)


class BrCo15Explainer(BaseExplainer):
    """Explainer for BR-CO-15: Invoice total amount mismatch."""
    
    def explain(self, error: ErrorItem, context: InspectionContext) -> ErrorItem:
        """
        Enrich BR-CO-15 error with specific evidence from the XML.
        
        This rule typically checks that the invoice total matches 
        the sum of line amounts plus taxes.
        """
        try:
            root = context.xml_tree.getroot()
            ns = context.namespaces
            
            # Try to extract relevant amounts from XML
            evidence = []
            
            # Look for tax exclusive amount
            tax_exclusive_xpath = ".//cbc:TaxExclusiveAmount"
            if "cbc" in ns:
                tax_exclusive_xpath = f".//{{{ns['cbc']}}}TaxExclusiveAmount"
            
            tax_exclusive_elem = root.find(tax_exclusive_xpath)
            if tax_exclusive_elem is not None:
                evidence.append(f"Tax Exclusive Amount: {tax_exclusive_elem.text}")
            
            # Look for tax amount
            tax_amount_xpath = ".//cbc:TaxAmount"
            if "cbc" in ns:
                tax_amount_xpath = f".//{{{ns['cbc']}}}TaxAmount"
            
            tax_amount_elem = root.find(tax_amount_xpath)
            if tax_amount_elem is not None:
                evidence.append(f"Tax Amount: {tax_amount_elem.text}")
            
            # Look for payable amount
            payable_xpath = ".//cbc:PayableAmount"
            if "cbc" in ns:
                payable_xpath = f".//{{{ns['cbc']}}}PayableAmount"
            
            payable_elem = root.find(payable_xpath)
            if payable_elem is not None:
                evidence.append(f"Payable Amount: {payable_elem.text}")
            
            if evidence:
                error["humanized_message"] = (
                    "Invoice total calculation error. The payable amount does not match "
                    f"the sum of tax exclusive amount plus tax amount. Found: {', '.join(evidence)}. "
                    "Please verify the arithmetic calculation of the invoice totals."
                )
            else:
                error["humanized_message"] = (
                    "Invoice total calculation error. Could not extract monetary amounts "
                    "from the invoice to provide specific guidance. Please verify that "
                    "the payable amount equals the tax exclusive amount plus tax amount."
                )
                
        except Exception as e:
            logger.warning(f"Failed to enrich BR-CO-15 error: {e}")
            error["humanized_message"] = (
                "Invoice total calculation error. Please verify that the total payable "
                "amount matches the sum of line amounts and applicable taxes."
            )
        
        return error
