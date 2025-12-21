from abc import ABC, abstractmethod
from diagnostics.types import ErrorItem, InspectionContext


class BaseExplainer(ABC):
    """Abstract base class for rule explainers."""
    
    @abstractmethod
    def explain(self, error: ErrorItem, context: InspectionContext) -> ErrorItem:
        """
        Explain and enrich an error with human-readable information.
        
        Args:
            error: Error item to enrich (will be mutated in place)
            context: Inspection context with XML tree and namespaces
            
        Returns:
            The same error item (mutated in place)
        """
        pass
