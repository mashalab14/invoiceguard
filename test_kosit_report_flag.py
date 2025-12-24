"""
Test the include_kosit_report flag functionality.

This test suite validates the include_kosit_report query parameter on the /validate endpoint.

Tests:
1. include_kosit_report=true includes kosit field (even if None in error cases)
2. include_kosit_report=false omits kosit field entirely
3. Missing flag uses default behavior (true)
4. Alternative truthy/falsy values (1, 0) work correctly
5. Response structure is valid in both cases

Usage:
    python3 -m pytest test_kosit_report_flag.py -v
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


def test_kosit_report_included_explicit_true(check_server, check_test_file):
    """Test that include_kosit_report=true includes the kosit field."""
    with open(TEST_XML, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/validate?mode=tier0&include_kosit_report=true",
            files={'file': f}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    # kosit field must be present when include_kosit_report=true
    assert 'kosit' in data, "kosit field missing when include_kosit_report=true"
    print("✓ include_kosit_report=true: kosit field included")


def test_kosit_report_excluded_explicit_false(check_server, check_test_file):
    """Test that include_kosit_report=false omits the kosit field."""
    with open(TEST_XML, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/validate?mode=tier0&include_kosit_report=false",
            files={'file': f}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    # kosit field must NOT be present when include_kosit_report=false
    assert 'kosit' not in data, "kosit field present when include_kosit_report=false"
    
    # Other required fields should still be present
    assert 'status' in data
    assert 'meta' in data
    assert 'errors' in data
    
    print("✓ include_kosit_report=false: kosit field omitted")


def test_kosit_report_default_behavior(check_server, check_test_file):
    """Test that omitting the flag uses default behavior (true)."""
    with open(TEST_XML, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/validate?mode=tier0",
            files={'file': f}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    # Default should be true, so kosit field should be present
    assert 'kosit' in data, "kosit field missing when flag omitted (default should be true)"
    print("✓ Flag omitted: kosit field included (default=true)")


def test_kosit_report_truthy_value_1(check_server, check_test_file):
    """Test that include_kosit_report=1 works as true."""
    with open(TEST_XML, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/validate?mode=tier0&include_kosit_report=1",
            files={'file': f}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    # 1 is truthy, so kosit should be present
    assert 'kosit' in data, "kosit field missing when include_kosit_report=1"
    print("✓ include_kosit_report=1: kosit field included")


def test_kosit_report_falsy_value_0(check_server, check_test_file):
    """Test that include_kosit_report=0 works as false."""
    with open(TEST_XML, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/validate?mode=tier0&include_kosit_report=0",
            files={'file': f}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    # 0 is falsy, so kosit should NOT be present
    assert 'kosit' not in data, "kosit field present when include_kosit_report=0"
    print("✓ include_kosit_report=0: kosit field omitted")


def test_response_structure_without_kosit(check_server, check_test_file):
    """Test that response structure is valid when kosit is excluded."""
    with open(TEST_XML, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/validate?mode=tier0&include_kosit_report=false",
            files={'file': f}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    # Check required fields
    assert 'status' in data
    assert data['status'] in ['PASSED', 'REJECTED', 'ERROR']
    
    assert 'meta' in data
    assert 'engine' in data['meta']
    assert 'rules_tag' in data['meta']
    assert 'commit' in data['meta']
    
    assert 'errors' in data
    assert isinstance(data['errors'], list)
    
    # kosit should NOT be present
    assert 'kosit' not in data
    
    print("✓ Response structure valid without kosit field")


if __name__ == "__main__":
    print("\n=== Testing include_kosit_report Flag ===\n")
    
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

