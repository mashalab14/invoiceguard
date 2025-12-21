from typing import TypedDict, Optional, List, Dict, Any, Literal
from dataclasses import dataclass
import lxml.etree


class ErrorItem(TypedDict, total=True):
    """Error item with strict typing requirements."""
    id: str
    message: str
    location: Optional[str]
    severity: Literal["fatal", "error", "warning"]
    suppressed: bool
    humanized_message: Optional[str]


@dataclass
class ExtractorRegistry:
    """Registry for data extractors."""
    totals: Optional[Any] = None
    currency: Optional[Any] = None


@dataclass
class InspectionContext:
    """Context for error inspection and enrichment."""
    xml_tree: lxml.etree._ElementTree
    namespaces: Dict[str, str]
    extractors: ExtractorRegistry


@dataclass
class DiagnosticsResult:
    """Result of diagnostics processing."""
    fatal_error: Optional[ErrorItem]
    processed_errors: List[ErrorItem]
