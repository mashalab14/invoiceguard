from typing import List, Dict, Any
import logging
from diagnostics.types import ErrorItem, DiagnosticsResult, InspectionContext, ExtractorRegistry
from diagnostics.dependency_filter import DependencyFilter
from diagnostics.rule_explainers.factory import ExplainerFactory
from common.xml_loader import SafeXMLLoader, XMLParsingError

logger = logging.getLogger(__name__)


class DiagnosticsPipeline:
    """Main pipeline for processing and enriching validation errors."""
    
    def __init__(self):
        """Initialize the diagnostics pipeline."""
        self.dependency_filter = DependencyFilter()
        self.explainer_factory = ExplainerFactory()
        self.xml_loader = SafeXMLLoader()
    
    def run(self, raw_report: List[Dict[str, Any]], xml_bytes: bytes) -> DiagnosticsResult:
        """
        Process raw validation report and enrich errors.
        
        Args:
            raw_report: Raw error report from validator
            xml_bytes: Original XML document bytes
            
        Returns:
            Processed diagnostics result
        """
        # Strict normalization - create fresh ErrorItem dicts
        normalized_errors: List[ErrorItem] = []
        
        for raw_item in raw_report:
            # Validate required fields
            if "id" not in raw_item or "message" not in raw_item:
                raw_snippet = repr(raw_item)[:200]
                logger.warning(f"Dropping invalid item (missing id/msg): {raw_snippet}")
                continue
            
            # Whitelist keys only - no unknown keys copied
            error_id = raw_item["id"]
            message = raw_item["message"]
            
            # Validate and normalize severity
            raw_severity = raw_item.get("severity", "error")
            if isinstance(raw_severity, str):
                severity = raw_severity.lower()
                if severity not in {"fatal", "error", "warning"}:
                    logger.warning(f"Invalid severity '{raw_severity}' for {error_id}, defaulting to error")
                    severity = "error"
            else:
                logger.warning(f"Invalid severity type '{type(raw_severity).__name__}' for {error_id}, defaulting to error")
                severity = "error"
            
            # Validate and normalize location
            raw_location = raw_item.get("location")
            if raw_location is not None and isinstance(raw_location, str):
                location = raw_location
            elif raw_location is not None:
                logger.warning(f"Invalid location type '{type(raw_location).__name__}' for {error_id}, setting location=None")
                location = None
            else:
                location = None
            
            # Create fresh ErrorItem dict
            error_item: ErrorItem = {
                "id": error_id,
                "message": message,
                "location": location,
                "severity": severity,
                "suppressed": False,
                "humanized_message": None
            }
            
            normalized_errors.append(error_item)
        
        # Parse XML document
        try:
            xml_tree = self.xml_loader.parse(xml_bytes)
        except XMLParsingError as e:
            # Return fatal error for XML parsing failure
            fatal_error: ErrorItem = {
                "id": "SYS-XML-001",
                "message": str(e),
                "severity": "fatal",
                "location": None,
                "suppressed": False,
                "humanized_message": None
            }
            return DiagnosticsResult(fatal_error=fatal_error, processed_errors=[])
        
        # Build inspection context
        namespaces = self.xml_loader.get_namespaces(xml_tree)
        extractors = ExtractorRegistry(totals=None, currency=None)
        context = InspectionContext(
            xml_tree=xml_tree,
            namespaces=namespaces,
            extractors=extractors
        )
        
        # Apply dependency filtering
        self.dependency_filter.apply(normalized_errors)
        
        # Inspect and enrich errors
        for error in normalized_errors:
            # Skip suppressed errors
            if error["suppressed"]:
                continue
            
            # Get explainer for this error
            explainer = self.explainer_factory.get_explainer(error["id"])
            if explainer is None:
                continue
            
            # Apply explanation with error handling
            try:
                explainer.explain(error, context)
            except Exception as e:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.exception(f"Explainer failed for error {error['id']}: {e}")
                else:
                    logger.warning(f"Explainer failed for error {error['id']}: {e}")
                
                # Reset humanized_message on failure
                error["humanized_message"] = None
        
        return DiagnosticsResult(fatal_error=None, processed_errors=normalized_errors)
