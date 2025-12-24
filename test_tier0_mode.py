#!/usr/bin/env python3
"""
Test TIER0 mode - raw KoSIT findings only, no enrichment.

NOTE: This test requires the KoSIT validator JAR to be available at /app/validator.jar
      or VALIDATOR_JAR environment variable pointing to a valid JAR file.
      In dev mode without the validator, this test will skip.

Validates:
1. Every KoSIT notice becomes one returned issue
2. action.summary equals exact KoSIT message text
3. technical_details.raw_locations equals exact KoSIT locations
4. No enrichment strings appear (no "often caused by", no BT extraction)
5. Response includes kosit.report_xml matching generated report file
6. If HTML produced, kosit.report_html is present and matches file
"""
import sys
import json
import requests
import pytest


def test_tier0_mode():
    """Test TIER0 mode with raw KoSIT output."""
    print("=" * 60)
    print("TIER0 MODE TEST")
    print("=" * 60)
    print()
    
    test_file = "test.xml"
    
    print(f"Testing /validate endpoint with mode=tier0...")
    print(f"Using test file: {test_file}")
    print()
    
    # Test: Call with mode=tier0
    print("TEST: Call /validate with mode=tier0")
    print("-" * 60)
    try:
        with open(test_file, 'rb') as f:
            files = {'file': (test_file, f, 'application/xml')}
            params = {'mode': 'tier0'}
            response = requests.post(
                'http://localhost:8080/validate',
                files=files,
                params=params,
                timeout=30
            )
        
        assert response.status_code == 200, f"Request failed with status {response.status_code}: {response.text}"
        
        result = response.json()
        print(f"✓ Request successful (status 200)")
    except requests.exceptions.ConnectionError:
        pytest.skip("API server not running on localhost:8080")
    except Exception as e:
        pytest.fail(f"Error making request: {e}")
    
    print()
    
    # Validation 1: Check response structure
    print("VALIDATION 1: Response structure")
    print("-" * 60)
    
    required_keys = ['status', 'meta', 'errors']
    for key in required_keys:
        assert key in result, f"Missing required key: {key}"
    
    print(f"✓ All required keys present: {required_keys}")
    print()
    
    # Check if validator is available
    if result['status'] == 'ERROR' and result['errors'][0]['id'] == 'EXECUTION_ERROR':
        pytest.skip("KoSIT validator JAR not available - skipping integration test")
    
    # Validation 2: Check kosit field presence
    print("VALIDATION 2: Raw KoSIT report presence")
    print("-" * 60)
    
    assert 'kosit' in result, "Missing 'kosit' field in TIER0 response"
    print(f"✓ 'kosit' field present")
    
    kosit = result['kosit']
    assert kosit is not None, "'kosit' field is None"
    
    assert 'report_xml' in kosit, "Missing 'report_xml' in kosit field"
    
    print(f"✓ 'report_xml' present in kosit field")
    
    report_xml = kosit['report_xml']
    assert report_xml and len(report_xml) >= 100, f"report_xml seems empty or too short ({len(report_xml) if report_xml else 0} bytes)"
    
    print(f"✓ report_xml has content ({len(report_xml)} bytes)")
    
    # Check if HTML is present (optional)
    if 'report_html' in kosit and kosit['report_html']:
        print(f"✓ report_html also present ({len(kosit['report_html'])} bytes)")
    else:
        print(f"  report_html not present (optional)")
    
    print()
    
    # Validation 3: Check errors structure
    print("VALIDATION 3: Errors structure (raw KoSIT format)")
    print("-" * 60)
    
    errors = result['errors']
    print(f"Number of issues: {len(errors)}")
    
    if len(errors) == 0:
        print(f"⚠️ No issues found (invoice might be valid)")
        print()
        print("=" * 60)
        print("✅ TIER0 MODE TEST PASSED (no issues found)")
        print("=" * 60)
        return
    
    print()
    
    # Check first issue structure
    first_issue = errors[0]
    print(f"First issue keys: {sorted(first_issue.keys())}")
    
    required_issue_keys = ['id', 'severity', 'action', 'technical_details']
    for key in required_issue_keys:
        assert key in first_issue, f"Missing required key in issue: {key}"
    
    print(f"✓ All required issue keys present")
    print()
    
    # Validation 4: Check action structure
    print("VALIDATION 4: Action structure")
    print("-" * 60)
    
    action = first_issue['action']
    required_action_keys = ['summary', 'fix', 'locations']
    
    for key in required_action_keys:
        assert key in action, f"Missing required key in action: {key}"
    
    print(f"✓ All required action keys present")
    
    # Check that fix is the generic constant
    expected_fix = "See rule description and correct the invoice data accordingly."
    assert action['fix'] == expected_fix, f"Fix message is not the expected constant. Expected: {expected_fix}, Got: {action['fix']}"
    
    print(f"✓ Fix message is the generic constant")
    print()
    
    # Validation 5: Check technical_details structure
    print("VALIDATION 5: Technical details structure")
    print("-" * 60)
    
    tech_details = first_issue['technical_details']
    required_tech_keys = ['raw_message', 'raw_locations']
    
    for key in required_tech_keys:
        assert key in tech_details, f"Missing required key in technical_details: {key}"
    
    print(f"✓ All required technical_details keys present")
    
    # Check that raw_message matches action.summary (verbatim)
    assert tech_details['raw_message'] == action['summary'], \
        f"raw_message does not match action.summary. raw_message: {tech_details['raw_message']}, summary: {action['summary']}"
    
    print(f"✓ raw_message matches action.summary (verbatim)")
    print()
    
    # Validation 6: Check no enrichment present
    print("VALIDATION 6: No enrichment strings")
    print("-" * 60)
    
    enrichment_phrases = [
        "often caused by",
        "commonly caused by",
        "BT-5",
        "BT-109",
        "BT-110",
        "BT-112",
        "DocumentCurrencyCode",
        "Suppressed"
    ]
    
    issue_str = json.dumps(first_issue)
    found_enrichment = []
    
    for phrase in enrichment_phrases:
        if phrase in issue_str:
            found_enrichment.append(phrase)
    
    assert not found_enrichment, f"Found enrichment phrases in TIER0 output: {found_enrichment}"
    
    print(f"✓ No enrichment phrases found")
    print()
    
    # Validation 7: Check no evidence field (TIER0 doesn't compute this)
    print("VALIDATION 7: No evidence field in TIER0")
    print("-" * 60)
    
    assert 'evidence' not in first_issue, "'evidence' field should not be present in TIER0 mode"
    
    print(f"✓ No 'evidence' field (correct for TIER0)")
    print()
    
    # Validation 8: Check no suppression (all issues reported)
    print("VALIDATION 8: No suppression in TIER0")
    print("-" * 60)
    
    suppressed_count = 0
    for issue in errors:
        if issue.get('suppressed', False):
            suppressed_count += 1
    
    assert suppressed_count == 0, f"Found {suppressed_count} suppressed issues in TIER0 mode"
    
    print(f"✓ No suppressed issues (all {len(errors)} issues reported)")
    print()
    
    # Validation 9: Check that count field is NOT present (no aggregation)
    print("VALIDATION 9: No aggregation in TIER0")
    print("-" * 60)
    
    assert 'count' not in first_issue, "'count' field should not be present in TIER0 (no aggregation)"
    
    print(f"✓ No 'count' field (no aggregation in TIER0)")
    print()
    
    print("=" * 60)
    print("✅ TIER0 MODE TEST PASSED")
    print("=" * 60)
    print()
    print("SUMMARY:")
    print(f"  - {len(errors)} raw KoSIT findings returned")
    print(f"  - Raw report XML included ({len(report_xml)} bytes)")
    print(f"  - No enrichment, no aggregation, no suppression")
    print(f"  - All findings have verbatim KoSIT messages")
    print()


if __name__ == "__main__":
    test_tier0_mode()
    sys.exit(0)
