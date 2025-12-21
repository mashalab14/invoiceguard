from typing import Optional
from diagnostics.rule_explainers.base import BaseExplainer
from diagnostics.rule_explainers.br_co_15 import BrCo15Explainer
from diagnostics.rule_explainers.br_co_16 import BrCo16Explainer
from diagnostics.rule_explainers.peppol_r001 import PeppolR001Explainer
from diagnostics.rule_explainers.ubl_cr_001 import UblCr001Explainer
import logging

logger = logging.getLogger(__name__)

# Import concrete explainer classes here
# Add more imports as explainers are implemented

class ExplainerFactory:
    """Factory for creating rule explainers."""
    
    # Static registry mapping IDs to explainer instances
    REGISTRY = {
        "BR-CO-15": BrCo15Explainer(),
        "BR-CO-16": BrCo16Explainer(),
        "PEPPOL-EN16931-R001": PeppolR001Explainer(),
        "UBL-CR-001": UblCr001Explainer(),
        # Add more explainers here as they are implemented
    }
    
    def get_explainer(self, error_id: str) -> Optional[BaseExplainer]:
        """
        Get explainer for a specific error ID.
        
        Args:
            error_id: The error ID to find explainer for
            
        Returns:
            Explainer instance or None if not found
        """
        return self.REGISTRY.get(error_id)
