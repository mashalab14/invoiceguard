"""
Presentation layer for filtering validation responses based on output mode.

This module implements the "Presentation" side of the Brain-Presentation architecture.
The Brain (deduplication, suppression) always produces full data-rich objects.
This layer applies final transformations based on user persona (SHORT, BALANCED, DETAILED).

Aggregation: SHORT and BALANCED group repeated error instances by (id, summary, fix)
to produce one diagnosis entry per underlying issue with count and location sampling.
"""
from typing import Any, Dict, List, Tuple
from collections import defaultdict
import logging

from diagnostics.message_catalog import get_title, get_short_fix

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


def _group_errors(errors: List[Any]) -> Dict[Tuple[str, str, str], List[Any]]:
    """
    Group errors by (id, summary, fix) to identify repeated issues.
    
    Args:
        errors: List of ValidationError objects
        
    Returns:
        Dictionary mapping (id, summary, fix) tuple to list of error instances
    """
    groups = defaultdict(list)
    for error in errors:
        if error.suppressed:
            continue
        key = (error.id, error.action.summary, error.action.fix)
        groups[key].append(error)
    return groups


def _aggregate_locations(errors: List[Any]) -> List[str]:
    """
    Aggregate locations from multiple error instances, returning first 3.
    
    Args:
        errors: List of error instances with same underlying issue
        
    Returns:
        List of up to 3 location strings
    """
    locations = []
    for error in errors:
        if error.action.locations:
            locations.extend(error.action.locations)
    return locations[:3]


def _aggregate_evidence(errors: List[Any]) -> Dict[str, Any]:
    """
    Merge evidence from multiple error instances conservatively.
    
    Strategy:
    - Set occurrence_count to the total number of instances
    - For numeric dict values (e.g., currency_ids_found), sum the counts
    - For list fields, collect unique values
    - For scalar fields, use first instance value
    
    Args:
        errors: List of error instances with same underlying issue
        
    Returns:
        Merged evidence dictionary
    """
    if not errors:
        return {}
    
    # Collect all evidence dicts
    evidence_dicts = []
    for error in errors:
        if error.evidence:
            evidence_dict = error.evidence.model_dump(exclude_none=True, exclude_unset=True)
            if evidence_dict:
                evidence_dicts.append(evidence_dict)
    
    if not evidence_dicts:
        return {}
    
    # Start with first evidence as base
    merged = evidence_dicts[0].copy()
    
    # Set occurrence_count to total number of instances
    merged['occurrence_count'] = len(errors)
    
    # For numeric dict fields (like currency_ids_found), sum the values
    for key in list(merged.keys()):
        if isinstance(merged[key], dict):
            # Check if values are numeric (summable)
            first_val = next(iter(merged[key].values()), None)
            if isinstance(first_val, (int, float)):
                # Sum counts across all instances
                summed = {}
                for ev in evidence_dicts:
                    if key in ev and isinstance(ev[key], dict):
                        for k, v in ev[key].items():
                            if isinstance(v, (int, float)):
                                summed[k] = summed.get(k, 0) + v
                merged[key] = summed
        
        # For lists/arrays, merge by collecting unique values
        elif isinstance(merged[key], list):
            all_values = []
            for ev in evidence_dicts:
                if key in ev and isinstance(ev[key], list):
                    all_values.extend(ev[key])
            # Keep unique values, preserve order
            merged[key] = list(dict.fromkeys(all_values))
    
    return merged


def _filter_short(errors: List[Any]) -> List[Dict[str, Any]]:
    """
    Filter errors for SHORT mode with aggressive aggregation.
    Groups by (id, summary, fix) and uses message catalog for titles/fixes.
    
    Output per group:
    - id: Error identifier
    - title: Short headline from catalog or generated (≤70 chars, no ellipsis)
    - fix: Short fix from catalog or generated (≤120 chars, no ellipsis)
    - count: Number of merged instances
    - locations_sample: First 3 locations (optional)
    
    Args:
        errors: List of ValidationError objects
        
    Returns:
        List of minimal dicts with aggregated data
    """
    # Group errors by (id, summary, fix)
    groups = _group_errors(errors)
    
    filtered = []
    for (error_id, summary, fix), error_instances in groups.items():
        # Build aggregated item using message catalog
        item = {
            "id": error_id,
            "title": get_title(error_id, summary),
            "fix": get_short_fix(error_id, fix),
            "count": len(error_instances)
        }
        
        # Add location sample if available
        locations = _aggregate_locations(error_instances)
        if locations:
            item["locations_sample"] = locations
        
        filtered.append(item)
    
    return filtered


def _filter_balanced(errors: List[Any]) -> List[Dict[str, Any]]:
    """
    Filter errors for BALANCED mode with aggregation.
    Groups by (id, summary, fix) and merges evidence conservatively.
    
    Output per group:
    - id: Error identifier
    - summary: Full summary (no truncation)
    - fix: Full fix (no truncation)
    - count: Number of merged instances
    - locations_sample: First 3 locations (optional)
    - evidence: Aggregated evidence with technical keys removed (optional)
    
    Note: Technical key removal happens AFTER evidence merging.
    
    Args:
        errors: List of ValidationError objects
        
    Returns:
        List of dicts with aggregated evidence and sample locations
    """
    # Group errors by (id, summary, fix)
    groups = _group_errors(errors)
    
    filtered = []
    for (error_id, summary, fix), error_instances in groups.items():
        # Build base item
        item = {
            "id": error_id,
            "summary": summary,
            "fix": fix,
            "count": len(error_instances)
        }
        
        # Add location sample if available
        locations = _aggregate_locations(error_instances)
        if locations:
            item["locations_sample"] = locations
        
        # Add aggregated evidence if available
        # First merge, then clean technical keys
        merged_evidence = _aggregate_evidence(error_instances)
        if merged_evidence:
            # Remove technical keys recursively AFTER merging
            cleaned_evidence = _remove_technical_keys(merged_evidence)
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
