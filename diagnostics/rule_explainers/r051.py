from diagnostics.rule_explainers.base import BaseExplainer
from diagnostics.types import ErrorItem, InspectionContext
import logging

logger = logging.getLogger(__name__)


class R051Explainer(BaseExplainer):
    """Explainer for PEPPOL-EN16931-R051: Currency code mismatch."""
    
    def explain(self, error: ErrorItem, context: InspectionContext) -> ErrorItem:
        """
        Enrich R051 error with specific guidance about currency code mismatches.
        
        This rule validates that the Document Currency Code (BT-5) matches 
        the currencyID attribute on all monetary amounts throughout the invoice.
        """
        try:
            xml_tree = context.xml_tree
            namespaces = context.namespaces
            
            if not xml_tree:
                error["humanized_message"] = (
                    "Currency Conflict. The Document Currency Code (BT-5) and the currencyID attributes "
                    "on monetary amounts are inconsistent. Please decide which currency is correct "
                    "and make them consistent throughout the invoice."
                )
                return error
            
            # Try to extract the document currency code
            document_currency = None
            
            # XPath strategies for finding DocumentCurrencyCode
            currency_xpaths = [
                ".//cbc:DocumentCurrencyCode",
                ".//*[local-name()='DocumentCurrencyCode']",
            ]
            
            for xpath in currency_xpaths:
                try:
                    if xpath.startswith('.//cbc:') and namespaces:
                        elements = xml_tree.xpath(xpath, namespaces=namespaces)
                    else:
                        elements = xml_tree.xpath(xpath)
                    
                    if elements and len(elements) > 0 and elements[0].text:
                        document_currency = elements[0].text.strip()
                        break
                except Exception as e:
                    logger.debug(f"XPath {xpath} failed: {e}")
                    continue
            
            # Try to extract the actual currencyID from the failing element
            found_currency = None
            error_location = error.get("location", "")
            
            if error_location:
                try:
                    # Try to find the element at the error location
                    # Error location is usually an XPath like "/Invoice[1]/cac:LegalMonetaryTotal[1]/cbc:TaxExclusiveAmount[1]"
                    if namespaces:
                        element = xml_tree.xpath(error_location, namespaces=namespaces)
                    else:
                        element = xml_tree.xpath(error_location)
                    
                    if element and len(element) > 0:
                        # Try to get currencyID attribute
                        found_currency = element[0].get('currencyID')
                        logger.debug(f"Found currencyID='{found_currency}' at {error_location}")
                except Exception as e:
                    logger.debug(f"Failed to extract currencyID from location {error_location}: {e}")
            
            # If we couldn't get it from location, try to find any amount with wrong currency
            if not found_currency:
                try:
                    # Find all elements with currencyID attribute
                    amount_xpaths = [
                        ".//*[@currencyID]",
                        ".//cbc:TaxExclusiveAmount",
                        ".//cbc:TaxInclusiveAmount",
                        ".//cbc:PayableAmount",
                    ]
                    
                    for xpath in amount_xpaths:
                        try:
                            if xpath.startswith('.//cbc:') and namespaces:
                                elements = xml_tree.xpath(xpath, namespaces=namespaces)
                            else:
                                elements = xml_tree.xpath(xpath)
                            
                            for elem in elements:
                                curr_id = elem.get('currencyID')
                                # If it doesn't match document currency, we found the mismatch
                                if curr_id and document_currency and curr_id != document_currency:
                                    found_currency = curr_id
                                    logger.debug(f"Found mismatched currencyID='{curr_id}' (expected '{document_currency}')")
                                    break
                            
                            if found_currency:
                                break
                        except Exception as e:
                            logger.debug(f"XPath {xpath} failed: {e}")
                            continue
                except Exception as e:
                    logger.debug(f"Failed to find currencyID mismatch: {e}")
            
            # Build explanation with specific evidence
            if document_currency and found_currency:
                error["humanized_message"] = (
                    f"Currency Conflict. The Document Currency is '{document_currency}', "
                    f"but this field uses '{found_currency}'. Please make them consistent."
                )
            elif document_currency:
                error["humanized_message"] = (
                    f"Currency Conflict. The Document Currency Code (BT-5) is '{document_currency}', "
                    "but amounts use a different currencyID. Please decide which currency is correct "
                    "and make them consistent (either update BT-5, or update the currencyID on all amounts)."
                )
            else:
                error["humanized_message"] = (
                    "Currency Conflict. The Document Currency Code (BT-5) and the currencyID attributes "
                    "on monetary amounts are inconsistent. Please decide which currency is correct "
                    "and make them consistent throughout the invoice."
                )
                
        except Exception as e:
            logger.warning(f"Failed to enrich R051 error: {e}")
            error["humanized_message"] = (
                "Currency Conflict. The Document Currency Code (BT-5) and currencyID attributes "
                "on amounts are inconsistent. Please make them consistent."
            )
        
        return error
