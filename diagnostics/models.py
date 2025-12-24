"""
Data models for InvoiceGuard validation output.
Supports raw KoSIT, T0 (1:1 findings), and T1 (with evidence).
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from enum import Enum


class OutputType(str, Enum):
    """Output type selector."""
    RAW = "raw"  # Raw KoSIT report only, no parsed errors
    T0 = "t0"    # 1:1 KoSIT findings, verbatim messages, no evidence
    T1 = "t1"    # Deterministic evidence extraction from KoSIT + invoice XML


class GroupingMode(str, Enum):
    """Grouping mode for T1 output."""
    UNGROUPED = "ungrouped"  # One issue per KoSIT finding
    GROUPED = "grouped"      # Group by id + severity + message


class OutputMode(str, Enum):
    """Legacy output mode - kept for backward compatibility."""
    TIER0 = "tier0"  # Deprecated: use type=t0 instead


class ErrorEvidence(BaseModel):
    """
    Structured evidence for T1 output.
    Contains deterministically extracted values from invoice XML.
    """
    # Generic fields that can apply to any rule
    fields: Dict[str, Any] = {}  # e.g., {"bt_109_xpath": "...", "bt_109_value": "EUR", "bt_109_line": 42}


class ErrorAction(BaseModel):
    """User-facing action guidance."""
    summary: str  # Raw KoSIT message (verbatim for T0/T1)
    fix: str  # Generic constant string
    locations: List[str]  # Raw XPaths from KoSIT


class DebugContext(BaseModel):
    """Technical details for debugging - raw KoSIT data."""
    raw_message: str  # Original validator message
    raw_locations: List[str]  # Raw XPaths with namespaces


class ValidationError(BaseModel):
    """
    Validation error - supports T0 (raw) and T1 (with evidence).
    """
    id: str
    severity: str
    action: ErrorAction
    technical_details: DebugContext
    evidence: Optional[ErrorEvidence] = None  # Only present for T1 output
    occurrence_count: Optional[int] = None  # Only present for T1 grouped output
    occurrences: Optional[List[Dict[str, Any]]] = None  # For grouped mode: list of individual occurrences


class KoSITReport(BaseModel):
    """Raw KoSIT validation report content."""
    report_xml: str  # Full XML report content
    report_html: Optional[str] = None  # HTML report if available
