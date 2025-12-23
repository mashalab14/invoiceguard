"""
Message catalog for SHORT mode output.

This module provides human-friendly titles and fixes for known error codes.
Adding support for a new error requires only updating this catalog, not the
presentation logic.

Structure:
- title: Short, actionable headline (target: ≤70 chars, no ellipsis)
- short_fix: Concise fix instruction (target: ≤120 chars, no ellipsis)
"""

# Error message catalog
# Maps error_id -> {title, fix}
ERROR_CATALOG = {
    "PEPPOL-EN16931-R051": {
        "title": "Currency mismatch: BT-5 vs currencyID",
        "fix": "Ensure all currencyID attributes match BT-5."
    },
    "BR-CO-15": {
        "title": "Totals mismatch: BT-112 vs BT-109 + BT-110",
        "fix": "Ensure BT-112 equals BT-109 plus BT-110."
    },
    "BR-CO-16": {
        "title": "Tax sum mismatch in line items",
        "fix": "Verify tax amounts sum correctly across all line items."
    },
    "PEPPOL-EN16931-R001": {
        "title": "Missing mandatory business term",
        "fix": "Add the required field according to Peppol BIS 3.0."
    },
    "UBL-CR-001": {
        "title": "Invalid code value",
        "fix": "Use a valid code from the specified code list."
    },
}


def get_title(error_id: str, fallback_summary: str) -> str:
    """
    Get SHORT mode title for an error.
    
    Args:
        error_id: Error identifier
        fallback_summary: Full summary to use if not in catalog
        
    Returns:
        Title string (≤70 chars, no ellipsis)
    """
    if error_id in ERROR_CATALOG:
        return ERROR_CATALOG[error_id]["title"]
    
    # Generate fallback title using safe heuristic
    return _generate_fallback_title(fallback_summary)


def get_short_fix(error_id: str, fallback_fix: str) -> str:
    """
    Get SHORT mode fix instruction for an error.
    
    Args:
        error_id: Error identifier
        fallback_fix: Full fix to use if not in catalog
        
    Returns:
        Fix string (≤120 chars, no ellipsis)
    """
    if error_id in ERROR_CATALOG:
        return ERROR_CATALOG[error_id]["fix"]
    
    # Generate fallback fix using safe heuristic
    return _generate_fallback_fix(fallback_fix)


def _generate_fallback_title(summary: str) -> str:
    """
    Generate a fallback title from a summary without sentence parsing.
    
    Strategy:
    1. Normalize whitespace
    2. Split on earliest delimiter: '. ', '; ', ' - ', ': ', '\n'
    3. Take first segment
    4. If still >70 chars, cut at word boundary to ≤70
    5. No ellipsis added
    
    Args:
        summary: Full summary text
        
    Returns:
        Title string (≤70 chars)
    """
    if not summary:
        return "Validation error"
    
    # Normalize whitespace
    normalized = " ".join(summary.split())
    
    # Try splitting on common delimiters (in order of preference)
    delimiters = ['. ', '; ', ' - ', ': ', '\n']
    first_segment = normalized
    
    for delimiter in delimiters:
        if delimiter in normalized:
            first_segment = normalized.split(delimiter)[0]
            break
    
    # If still too long, cut at word boundary
    if len(first_segment) > 70:
        # Cut to ≤70 at last space
        cutoff = first_segment[:70].rfind(' ')
        if cutoff > 0:
            first_segment = first_segment[:cutoff]
        else:
            # No space found, hard cut
            first_segment = first_segment[:70]
    
    return first_segment.strip()


def _generate_fallback_fix(fix: str) -> str:
    """
    Generate a fallback fix instruction from full fix text.
    
    Strategy:
    1. Normalize whitespace
    2. Split on earliest delimiter: '. ', '; ', '\n'
    3. Take first segment
    4. If still >120 chars, cut at word boundary to ≤120
    5. No ellipsis added
    
    Args:
        fix: Full fix text
        
    Returns:
        Fix string (≤120 chars)
    """
    if not fix:
        return "Review and correct according to Peppol BIS 3.0 specification."
    
    # Normalize whitespace
    normalized = " ".join(fix.split())
    
    # Try splitting on common delimiters
    delimiters = ['. ', '; ', '\n']
    first_segment = normalized
    
    for delimiter in delimiters:
        if delimiter in normalized:
            first_segment = normalized.split(delimiter)[0]
            break
    
    # If still too long, cut at word boundary
    if len(first_segment) > 120:
        # Cut to ≤120 at last space
        cutoff = first_segment[:120].rfind(' ')
        if cutoff > 0:
            first_segment = first_segment[:cutoff]
        else:
            # No space found, hard cut
            first_segment = first_segment[:120]
    
    return first_segment.strip()
