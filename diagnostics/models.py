"""
Data models for validation errors with tiered information structure.
"""
from typing import List, Optional, Dict
from pydantic import BaseModel


class ErrorAction(BaseModel):
    """User-facing action guidance."""
    summary: str  # Brief description of the error
    fix: str  # Step-by-step fix instructions
    locations: List[str]  # Human-readable XPaths (cleaned, no namespaces)


class ErrorEvidence(BaseModel):
    """Structured evidence data for the error."""
    bt5_value: Optional[str] = None  # Document Currency Code (BT-5)
    currency_ids_found: Optional[Dict[str, int]] = None  # Dict of {currency: count}
    occurrence_count: int  # Total number of occurrences


class DebugContext(BaseModel):
    """Technical details for debugging."""
    raw_message: str  # Original validator message
    raw_locations: List[str]  # Raw XPaths with namespaces


class ValidationError(BaseModel):
    """
    Validation error with tiered information structure.
    
    Structure:
    - action: User-facing guidance (what to do)
    - evidence: Structured data (facts)
    - technical_details: Raw debugging info
    """
    id: str
    severity: str
    action: ErrorAction
    evidence: Optional[ErrorEvidence] = None
    technical_details: DebugContext
    suppressed: bool = False
