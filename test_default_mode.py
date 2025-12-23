#!/usr/bin/env python3
"""
Test that /validate endpoint defaults to BALANCED mode when mode parameter is omitted.
"""
import sys
import json
import requests

def test_default_mode():
    """Test that omitting mode parameter results in BALANCED output."""
    print("=" * 60)
    print("DEFAULT MODE TEST")
    print("=" * 60)
    print()
    
    test_file = "test.xml"
    
    print(f"Testing /validate endpoint without mode parameter...")
    print(f"Using test file: {test_file}")
    print()
    
    # Test 1: Call without mode parameter
    print("TEST 1: Call /validate without mode parameter")
    print("-" * 60)
    try:
        with open(test_file, 'rb') as f:
            files = {'file': (test_file, f, 'application/xml')}
            # NO mode parameter provided
            response_no_mode = requests.post(
                'http://localhost:8000/validate',
                files=files,
                timeout=30
            )
        
        if response_no_mode.status_code != 200:
            print(f"❌ Request failed with status {response_no_mode.status_code}")
            print(f"Response: {response_no_mode.text}")
            return False
        
        result_no_mode = response_no_mode.json()
        print(f"✓ Request successful (status 200)")
    except Exception as e:
        print(f"❌ Error making request: {e}")
        return False
    
    print()
    
    # Test 2: Call explicitly with mode=balanced
    print("TEST 2: Call /validate with mode=balanced")
    print("-" * 60)
    try:
        with open(test_file, 'rb') as f:
            files = {'file': (test_file, f, 'application/xml')}
            params = {'mode': 'balanced'}
            response_balanced = requests.post(
                'http://localhost:8000/validate',
                files=files,
                params=params,
                timeout=30
            )
        
        if response_balanced.status_code != 200:
            print(f"❌ Request failed with status {response_balanced.status_code}")
            print(f"Response: {response_balanced.text}")
            return False
        
        result_balanced = response_balanced.json()
        print(f"✓ Request successful (status 200)")
    except Exception as e:
        print(f"❌ Error making request: {e}")
        return False
    
    print()
    
    # Test 3: Compare the two results
    print("TEST 3: Compare results")
    print("-" * 60)
    
    # Check that diagnosis exists in both
    if 'diagnosis' not in result_no_mode:
        print(f"❌ No 'diagnosis' key in response without mode")
        return False
    
    if 'diagnosis' not in result_balanced:
        print(f"❌ No 'diagnosis' key in response with mode=balanced")
        return False
    
    # Get diagnosis arrays
    diagnosis_no_mode = result_no_mode['diagnosis']
    diagnosis_balanced = result_balanced['diagnosis']
    
    print(f"Diagnosis entries (no mode): {len(diagnosis_no_mode)}")
    print(f"Diagnosis entries (balanced): {len(diagnosis_balanced)}")
    print()
    
    # Both should have the same number of entries
    if len(diagnosis_no_mode) != len(diagnosis_balanced):
        print(f"❌ Different number of diagnosis entries: {len(diagnosis_no_mode)} vs {len(diagnosis_balanced)}")
        return False
    
    print(f"✓ Same number of diagnosis entries")
    print()
    
    # Compare structure of first diagnosis entry (if exists)
    if len(diagnosis_no_mode) > 0 and len(diagnosis_balanced) > 0:
        first_no_mode = diagnosis_no_mode[0]
        first_balanced = diagnosis_balanced[0]
        
        keys_no_mode = set(first_no_mode.keys())
        keys_balanced = set(first_balanced.keys())
        
        print(f"First entry keys (no mode): {sorted(keys_no_mode)}")
        print(f"First entry keys (balanced): {sorted(keys_balanced)}")
        print()
        
        if keys_no_mode != keys_balanced:
            print(f"❌ Different keys in first entry")
            print(f"  Only in no_mode: {keys_no_mode - keys_balanced}")
            print(f"  Only in balanced: {keys_balanced - keys_no_mode}")
            return False
        
        print(f"✓ Same keys in first entry")
        print()
        
        # Check for BALANCED-specific features (should be present in both)
        balanced_features = {
            'evidence': 'Evidence data present in BALANCED mode',
            'action': 'Action with locations present in BALANCED mode'
        }
        
        for key, description in balanced_features.items():
            has_in_no_mode = key in first_no_mode
            has_in_balanced = key in first_balanced
            
            print(f"Feature '{key}': no_mode={has_in_no_mode}, balanced={has_in_balanced}")
            
            if has_in_no_mode != has_in_balanced:
                print(f"❌ Mismatch in '{key}' presence")
                return False
        
        print()
        print(f"✓ All BALANCED features present in both responses")
        print()
        
        # Check that locations are present (BALANCED should have locations, SHORT should not)
        if 'action' in first_no_mode and 'locations' in first_no_mode['action']:
            locations_no_mode = first_no_mode['action'].get('locations', [])
            locations_balanced = first_balanced['action'].get('locations', [])
            
            print(f"Locations (no mode): {len(locations_no_mode)}")
            print(f"Locations (balanced): {len(locations_balanced)}")
            
            if len(locations_no_mode) > 0 and len(locations_balanced) > 0:
                print(f"✓ Both have locations (confirms BALANCED mode, not SHORT)")
            elif len(locations_no_mode) == 0 and len(locations_balanced) == 0:
                print(f"⚠️ Both have 0 locations (might be aggregated entry)")
            else:
                print(f"❌ Location count mismatch")
                return False
        
        print()
        
        # Check that technical_details is NOT present (DETAILED would have it)
        has_technical_no_mode = 'technical_details' in first_no_mode
        has_technical_balanced = 'technical_details' in first_balanced
        
        print(f"Has technical_details (no mode): {has_technical_no_mode}")
        print(f"Has technical_details (balanced): {has_technical_balanced}")
        
        if has_technical_no_mode or has_technical_balanced:
            print(f"❌ technical_details should not be present in BALANCED mode")
            return False
        
        print(f"✓ No technical_details (confirms BALANCED mode, not DETAILED)")
        print()
    
    print("=" * 60)
    print("✅ DEFAULT MODE TEST PASSED")
    print("=" * 60)
    print()
    print("CONCLUSION: When mode parameter is omitted, the /validate endpoint")
    print("            uses BALANCED mode as the default.")
    print()
    
    return True


if __name__ == "__main__":
    success = test_default_mode()
    sys.exit(0 if success else 1)
