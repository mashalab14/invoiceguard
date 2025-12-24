"""
Tier 0 data models - minimal models for raw KoSIT output only.
No enrichment, no evidence, no humanization.
"""
from typing import List, Optional
from pydantic import BaseModel
from enum import Enum


class OutputMode(str, Enum):
    """Output mode - only TIER0 is supported."""
    TIER0 = "tier0"  # Raw KoSIT only: No enrichment, includes raw report


class ErrorAction(BaseModel):
    """User-facing action guidance - Tier 0 version with generic messages only."""
    summary: str  # Raw KoSIT message (verbatim)
    fix: str  # Generic constant string
    locations: List[str]  # Raw XPaths from KoSIT


class DebugContext(BaseModel):
    """Technical details for debugging - raw KoSIT data."""
    raw_message: str  # Original validator message
    raw_locations: List[str]  # Raw XPaths with namespaces


class ValidationError(BaseModel):
    """
    Validation error - Tier 0 structure with raw KoSIT data only.
    No enrichment, no evidence, no humanization.
    """
    id: str
    severity: str
    action: ErrorAction
    technical_details: DebugContext


class KoSITReport(BaseModel):
    """Raw KoSIT validation report content."""
    report_xml: str  # Full XML report content
    report_html: Optional[str] = None  # HTML report if available
