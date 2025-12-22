"""
Presentation layer for validation responses.

This module applies output filtering based on user persona (OutputMode).
It acts as the final transformation before JSON response.

Architecture:
    SVRL → Humanization → Tiered → Dedup → Suppression → [MODE FILTER] → JSON
    
The "Brain" (validation logic) always produces full ValidationError objects.
The "Presentation" (this module) filters based on OutputMode.
"""
from typing import List, Dict, Any
from diagnostics.models import ValidationError, OutputMode


def apply_mode_filter(errors: List[ValidationError], mode: OutputMode) -> Dict[str, Any]:
    """
    Apply output filtering based on diagnostic mode.
    
    Three user personas:
    - SHORT (Supplier): Only id, summary, fix. No evidence, no technical details, no suppressed errors.
    - BALANCED (Developer): Add evidence, limit to 3 sample locations, show suppressed errors.
    - DETAILED (Auditor): Everything (all locations, full technical_details, suppressed errors).
    
    Args:
        errors: List of ValidationError objects (from "Brain")
        mode: OutputMode enum value
        
    Returns:
        Dict with filtered 'errors' and optionally 'suppressed' lists
    """
    # Separate root causes and suppressed errors
    root_causes = [e for e in errors if not e.suppressed]
    suppressed_errors = [e for e in errors if e.suppressed]
    
    if mode == OutputMode.SHORT:
        # SHORT: Strip everything except id, summary, fix
        filtered_errors = [
            {
                "id": error.id,
                "severity": error.severity,
                "action": {
                    "summary": error.action.summary,
                    "fix": error.action.fix,
                    "locations": []  # Hide locations in SHORT mode
                }
            }
            for error in root_causes
        ]
        return {"errors": filtered_errors}
    
    elif mode == OutputMode.BALANCED:
        # BALANCED: Keep evidence, limit locations to first 3, hide technical_details
        filtered_errors = [
            {
                "id": error.id,
                "severity": error.severity,
                "action": {
                    "summary": error.action.summary,
                    "fix": error.action.fix,
                    "locations": error.action.locations[:3]  # Limit to 3 samples
                },
                "evidence": error.evidence.dict() if error.evidence else None
                # technical_details omitted
            }
            for error in root_causes
        ]
        
        # Include suppressed errors with reasons
        suppressed_list = [
            {
                "id": error.id,
                "reason": f"Suppressed by root cause: {_extract_suppression_reason(error)}"
            }
            for error in suppressed_errors
        ]
        
        return {
            "errors": filtered_errors,
            "suppressed": suppressed_list if suppressed_list else []
        }
    
    else:  # OutputMode.DETAILED
        # DETAILED: Keep everything (all locations, full technical_details)
        filtered_errors = [
            {
                "id": error.id,
                "severity": error.severity,
                "action": {
                    "summary": error.action.summary,
                    "fix": error.action.fix,
                    "locations": error.action.locations  # All locations
                },
                "evidence": error.evidence.dict() if error.evidence else None,
                "technical_details": error.technical_details.dict() if error.technical_details else None
            }
            for error in root_causes
        ]
        
        # Include suppressed errors with full details
        suppressed_list = [
            {
                "id": error.id,
                "severity": error.severity,
                "reason": f"Suppressed by root cause: {_extract_suppression_reason(error)}",
                "action": {
                    "summary": error.action.summary,
                    "fix": error.action.fix,
                    "locations": error.action.locations
                },
                "technical_details": error.technical_details.dict() if error.technical_details else None
            }
            for error in suppressed_errors
        ]
        
        return {
            "errors": filtered_errors,
            "suppressed": suppressed_list if suppressed_list else []
        }


def _extract_suppression_reason(error: ValidationError) -> str:
    """
    Extract the reason why an error was suppressed from its summary.
    
    Args:
        error: ValidationError that was suppressed
        
    Returns:
        Reason string (e.g., "R051 present")
    """
    summary = error.action.summary
    
    # Look for "(Suppressed: reason)" pattern
    if "(Suppressed:" in summary:
        reason = summary.split("(Suppressed:")[-1].rstrip(")")
        return reason.strip()
    
    return "Cascade error"
