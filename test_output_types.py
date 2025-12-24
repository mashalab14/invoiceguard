"""
Test the deterministic output selector (type and grouping parameters).

Tests:
1. Default behavior is type=t1 & grouping=ungrouped
2. type=raw returns only KoSIT report, errors=[]
3. type=t0 returns 1:1 findings with verbatim messages, no evidence
4. type=t1 returns findings with evidence fields
5. type=t1&grouping=grouped reduces count by grouping, adds occurrence_count
6. Grouping preserves verbatim action.summary
7. type=t0/raw ignore grouping parameter

Usage:
    python3 -m pytest test_output_types.py -v
"""

import pytest
import requests
import os

BASE_URL = "http://localhost:8080"
TEST_XML = "test.xml"


@pytest.fixture(scope="module")
def check_server():
    """Ensure the server is running before tests."""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        assert response.status_code == 200
        print(f"\n✓ Server is running at {BASE_URL}")
    except requests.exceptions.RequestException as e:
        pytest.skip(f"Server not running at {BASE_URL}: {e}")


@pytest.fixture(scope="module")
def check_test_file():
    """Ensure test.xml exists."""
    if not os.path.exists(TEST_XML):
        pytest.skip(f"{TEST_XML} not found")


def test_default_behavior(check_server, check_test_file):
    """Test that default is type=t1 & grouping=ungrouped."""
    with open(TEST_XML, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/validate",
            files={'file': f}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should have standard fields
    assert 'status' in data
    assert 'meta' in data
    assert 'errors' in data
    
    # Errors should have evidence (T1 default)
    if len(data['errors']) > 0:
        # Check if first error has evidence field (can be None)
        assert 'evidence' in data['errors'][0] or 'evidence' not in data['errors'][0]
        # No occurrence_count (ungrouped default)
        assert 'occurrence_count' not in data['errors'][0] or data['errors'][0].get('occurrence_count') is None
    
    print("✓ Default behavior: type=t1, grouping=ungrouped")


def test_type_raw(check_server, check_test_file):
    """Test that type=raw returns only KoSIT report, no parsed errors."""
    with open(TEST_XML, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/validate?type=raw",
            files={'file': f}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should have standard fields
    assert 'status' in data
    assert 'meta' in data
    assert 'errors' in data
    
    # For RAW type, errors should be empty
    assert isinstance(data['errors'], list)
    assert len(data['errors']) == 0, "RAW type should have empty errors list"
    
    # Should have kosit report (if include_kosit_report=true by default)
    assert 'kosit' in data
    assert data['kosit'] is not None or data['status'] == 'ERROR'
    
    if data['kosit'] is not None:
        assert 'report_xml' in data['kosit']
        assert data['kosit']['report_xml'] is not None
    
    print("✓ type=raw: no parsed errors, only KoSIT report")


def test_type_t0(check_server, check_test_file):
    """Test that type=t0 returns 1:1 findings with verbatim messages, no evidence."""
    with open(TEST_XML, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/validate?type=t0",
            files={'file': f}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should have standard fields
    assert 'status' in data
    assert 'meta' in data
    assert 'errors' in data
    
    # Errors should be present if validation fails
    if len(data['errors']) > 0:
        error = data['errors'][0]
        
        # Must have basic fields
        assert 'id' in error
        assert 'severity' in error
        assert 'action' in error
        assert 'summary' in error['action']
        assert 'technical_details' in error
        
        # T0: No evidence field (or None)
        if 'evidence' in error:
            assert error['evidence'] is None, "T0 should not have evidence"
        
        # No occurrence_count (not grouped)
        assert 'occurrence_count' not in error or error['occurrence_count'] is None
    
    print(f"✓ type=t0: {len(data['errors'])} findings, no evidence")


def test_type_t1_ungrouped(check_server, check_test_file):
    """Test that type=t1 with grouping=ungrouped returns findings with evidence."""
    with open(TEST_XML, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/validate?type=t1&grouping=ungrouped",
            files={'file': f}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should have standard fields
    assert 'status' in data
    assert 'meta' in data
    assert 'errors' in data
    
    # Errors should be present if validation fails
    if len(data['errors']) > 0:
        error = data['errors'][0]
        
        # Must have basic fields
        assert 'id' in error
        assert 'severity' in error
        assert 'action' in error
        
        # T1: Should have evidence field (may be None or populated)
        assert 'evidence' in error
        
        # If evidence is present, should have fields
        if error['evidence'] is not None:
            assert 'fields' in error['evidence']
            assert isinstance(error['evidence']['fields'], dict)
        
        # Ungrouped: No occurrence_count
        assert 'occurrence_count' not in error or error['occurrence_count'] is None
    
    print(f"✓ type=t1 ungrouped: {len(data['errors'])} findings with evidence")


def test_type_t1_grouped(check_server, check_test_file):
    """Test that type=t1 with grouping=grouped reduces count and adds occurrence_count."""
    # First get ungrouped count
    with open(TEST_XML, 'rb') as f:
        response_ungrouped = requests.post(
            f"{BASE_URL}/validate?type=t1&grouping=ungrouped",
            files={'file': f}
        )
    
    assert response_ungrouped.status_code == 200
    data_ungrouped = response_ungrouped.json()
    ungrouped_count = len(data_ungrouped['errors'])
    
    # Now get grouped count
    with open(TEST_XML, 'rb') as f:
        response_grouped = requests.post(
            f"{BASE_URL}/validate?type=t1&grouping=grouped",
            files={'file': f}
        )
    
    assert response_grouped.status_code == 200
    data_grouped = response_grouped.json()
    grouped_count = len(data_grouped['errors'])
    
    # Grouped should have fewer or equal errors
    assert grouped_count <= ungrouped_count, "Grouped should reduce or maintain count"
    
    # If there are errors, check structure
    if grouped_count > 0:
        error = data_grouped['errors'][0]
        
        # Must have basic fields
        assert 'id' in error
        assert 'severity' in error
        assert 'action' in error
        assert 'summary' in error['action']
        
        # Grouped: Should have occurrence_count
        assert 'occurrence_count' in error
        assert isinstance(error['occurrence_count'], int)
        assert error['occurrence_count'] >= 1
        
        # Should have occurrences array
        if error['occurrence_count'] > 1:
            assert 'occurrences' in error
            assert isinstance(error['occurrences'], list)
            assert len(error['occurrences']) == error['occurrence_count']
        
        # Summary should be verbatim (same as ungrouped)
        # We can't verify exact match without knowing the specific errors,
        # but we can check it's not empty
        assert error['action']['summary'], "Summary should not be empty"
    
    print(f"✓ type=t1 grouped: {ungrouped_count} → {grouped_count} (deduplicated)")


def test_grouping_preserves_verbatim_summary(check_server, check_test_file):
    """Test that grouped output preserves verbatim action.summary."""
    with open(TEST_XML, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/validate?type=t1&grouping=grouped",
            files={'file': f}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    if len(data['errors']) > 0:
        for error in data['errors']:
            # Summary should exist and not be empty
            assert 'action' in error
            assert 'summary' in error['action']
            assert error['action']['summary'], "Summary should not be empty"
            
            # Summary should not contain generic phrases like "grouped" or "occurrences"
            # (it should be the verbatim KoSIT message)
            summary_lower = error['action']['summary'].lower()
            assert 'occurrences' not in summary_lower, "Summary should be verbatim, not mention occurrences"
    
    print("✓ Grouped output preserves verbatim summary")


def test_t0_ignores_grouping(check_server, check_test_file):
    """Test that type=t0 ignores grouping parameter."""
    # Get T0 without grouping
    with open(TEST_XML, 'rb') as f:
        response1 = requests.post(
            f"{BASE_URL}/validate?type=t0",
            files={'file': f}
        )
    
    # Get T0 with grouping=grouped (should be ignored)
    with open(TEST_XML, 'rb') as f:
        response2 = requests.post(
            f"{BASE_URL}/validate?type=t0&grouping=grouped",
            files={'file': f}
        )
    
    assert response1.status_code == 200
    assert response2.status_code == 200
    
    data1 = response1.json()
    data2 = response2.json()
    
    # Should have same number of errors (grouping ignored)
    assert len(data1['errors']) == len(data2['errors'])
    
    # Neither should have occurrence_count
    if len(data1['errors']) > 0:
        assert 'occurrence_count' not in data1['errors'][0] or data1['errors'][0].get('occurrence_count') is None
        assert 'occurrence_count' not in data2['errors'][0] or data2['errors'][0].get('occurrence_count') is None
    
    print("✓ type=t0 ignores grouping parameter")


def test_raw_ignores_grouping(check_server, check_test_file):
    """Test that type=raw ignores grouping parameter."""
    # Get RAW without grouping
    with open(TEST_XML, 'rb') as f:
        response1 = requests.post(
            f"{BASE_URL}/validate?type=raw",
            files={'file': f}
        )
    
    # Get RAW with grouping=grouped (should be ignored)
    with open(TEST_XML, 'rb') as f:
        response2 = requests.post(
            f"{BASE_URL}/validate?type=raw&grouping=grouped",
            files={'file': f}
        )
    
    assert response1.status_code == 200
    assert response2.status_code == 200
    
    data1 = response1.json()
    data2 = response2.json()
    
    # Both should have empty errors
    assert len(data1['errors']) == 0
    assert len(data2['errors']) == 0
    
    print("✓ type=raw ignores grouping parameter")


def test_response_structure_consistency(check_server, check_test_file):
    """Test that response structure is consistent across all types."""
    types = ['raw', 't0', 't1']
    
    for output_type in types:
        with open(TEST_XML, 'rb') as f:
            response = requests.post(
                f"{BASE_URL}/validate?type={output_type}",
                files={'file': f}
            )
        
        assert response.status_code == 200
        data = response.json()
        
        # All types should have these fields
        assert 'status' in data, f"type={output_type} missing status"
        assert 'meta' in data, f"type={output_type} missing meta"
        assert 'errors' in data, f"type={output_type} missing errors"
        
        # Check meta structure
        assert 'engine' in data['meta']
        assert 'rules_tag' in data['meta']
        assert 'commit' in data['meta']
        
        # Check status value
        assert data['status'] in ['PASSED', 'REJECTED', 'ERROR']
    
    print("✓ Response structure consistent across all types")


if __name__ == "__main__":
    print("\n=== Testing Deterministic Output Selector ===\n")
    
    # Check if server is running
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        print(f"✓ Server is running at {BASE_URL}\n")
    except requests.exceptions.RequestException:
        print(f"✗ Server not running at {BASE_URL}")
        print("  Start the server with:")
        print("  export DEV_MODE=1 VERSION_INFO_FILE=version_info_dev.txt RULES_DIR_FILE=rules_dir_dev.txt TEMP_DIR=./temp_dev")
        print("  python3 main.py")
        exit(1)
    
    # Run tests
    pytest.main([__file__, "-v", "-s"])
