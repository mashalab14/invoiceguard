"""
Presentation layer for filtering validation responses based on output mode.

This module implements the "Presentation" side of the Brain-Presentation architecture.
The Brain (deduplication, suppression) always produces full data-rich objects.
This layer applies final transformations based on user persona (SHORT, BALANCED, DETAILED).
"""
from typing import Any, Dict, List, Union
import logging

logger = logging.getLogger(__name__)

# Disallowed technical keys for BALANCED mode (recursive removal)
TECHNICAL_KEYS = {
    "technical_details", "debug_log", "raw_locations", "stacktrace", 
    "trace", "paths", "raw", "internal", "raw_message"
}


def _normalize_mode(mode: Any) -> str:
    """
    Normalize mode input to lowercase string.
    
    Args:
        mode: Can be OutputMode enum, string, or any type with .value attribute
        
    Returns:
        Normalized mode string: "short", "balanced", or "detailed"
        
    Raises:
        ValueError: If mode is invalid (strict behavior)
    """
    # Extract string representation
    if hasattr(mode, "value"):
        mode_str = str(mode.value).lower()
    else:
        mode_str = str(mode).lower()
    
    # Validate
    valid_modes = {"short", "balanced", "detailed"}
    if mode_str not in valid_modes:
        # Strict behavior: raise error for invalid mode
        raise ValueError(f"Invalid mode '{mode_str}'. Must be one of: {valid_modes}")
    
    return mode_str


def _remove_technical_keys(data: Any) -> Any:
    """
    Recursively remove technical keys from nested dictionaries.
    
    Args:
        data: Dictionary, list, or primitive value
        
    Returns:
        Cleaned data structure with technical keys removed
    """
    if isinstance(data, dict):
        return {
            k: _remove_technical_keys(v)
            for k, v in data.items()
            if k not in TECHNICAL_KEYS
        }
    elif isinstance(data, list):
        return [_remove_technical_keys(item) for item in data]
    else:
        return data


def _filter_short(errors: List[Any]) -> List[Dict[str, Any]]:
    """
    Filter errors for SHORT mode - only id, summary, fix.
    
    Args:
        errors: List of ValidationError objects
        
    Returns:
        List of minimal dicts with whitelist fields only
    """
    filtered = []
    for error in errors:
        # Skip suppressed errors
        if error.suppressed:
            continue
            
        # Build dict with only allowed fields
        item = {
            "id": error.id,
            "summary": error.action.summary,
            "fix": error.action.fix
        }
        filtered.append(item)
    
    return filtered


def _filter_balanced(errors: List[Any]) -> List[Dict[str, Any]]:
    """
    Filter errors for BALANCED mode - add evidence and first 3 locations.
    
    Args:
        errors: List of ValidationError objects
        
    Returns:
        List of dicts with evidence and sample locations
    """
    filtered = []
    for error in errors:
        # Skip suppressed errors
        if error.suppressed:
            continue
            
        # Build base dict
        item = {
            "id": error.id,
            "summary": error.action.summary,
            "fix": error.action.fix
        }
        
        # Add first 3 locations if available
        if error.action.locations:
            item["locations"] = error.action.locations[:3]
        
        # Add evidence if available (with technical keys removed)
        if error.evidence:
            evidence_dict = error.evidence.model_dump(exclude_none=True, exclude_unset=True)
            # Recursively remove technical keys
            cleaned_evidence = _remove_technical_keys(evidence_dict)
            if cleaned_evidence:  # Only include if non-empty after cleaning
                item["evidence"] = cleaned_evidence
        
        filtered.append(item)
    
    return filtered


def _filter_detailed(errors: List[Any]) -> List[Dict[str, Any]]:
    """
    Filter errors for DETAILED mode - include everything.
    
    Args:
        errors: List of ValidationError objects
        
    Returns:
        List of full error dicts with all fields
    """
    return [error.model_dump(exclude_none=False) for error in errors]


def apply_mode_filter(mode: Any, validation_response: Any) -> Dict[str, Any]:
    """
    Apply presentation filtering based on output mode.
    
    This is the final transformation step that converts the full Brain output
    into a JSON-safe envelope appropriate for the user persona.
    
    Args:
        mode: Output mode (SHORT, BALANCED, or DETAILED)
        validation_response: Full validation response from Brain
        
    Returns:
        JSON-safe dictionary envelope with filtered content
        
    Raises:
        ValueError: If mode is invalid
    """
    # Normalize mode to string
    mode_str = _normalize_mode(mode)
    
    logger.debug(f"Applying {mode_str.upper()} mode filter")
    
    # Filter errors based on mode
    if mode_str == "short":
        diagnosis = _filter_short(validation_response.errors)
    elif mode_str == "balanced":
        diagnosis = _filter_balanced(validation_response.errors)
    else:  # detailed
        diagnosis = _filter_detailed(validation_response.errors)
    
    # Build meta - handle both Pydantic and dict
    if hasattr(validation_response.meta, 'model_dump'):
        if mode_str in ("short", "balanced"):
            meta_dict = validation_response.meta.model_dump(exclude_none=True, exclude_unset=True)
        else:  # detailed
            meta_dict = validation_response.meta.model_dump(exclude_none=False)
    elif isinstance(validation_response.meta, dict):
        if mode_str in ("short", "balanced"):
            # Remove None values from dict
            meta_dict = {k: v for k, v in validation_response.meta.items() if v is not None}
        else:  # detailed
            meta_dict = validation_response.meta.copy()
    else:
        meta_dict = {}
    
    # Build JSON-safe envelope
    envelope = {
        "status": validation_response.status,
        "meta": meta_dict,
        "diagnosis": diagnosis
    }
    
    # Add debug_log only in DETAILED mode
    if mode_str == "detailed" and validation_response.debug_log:
        envelope["debug_log"] = validation_response.debug_log
    
    return envelope
