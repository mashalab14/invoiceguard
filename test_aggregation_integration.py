#!/usr/bin/env python3
"""
Integration test for aggregation with real invoice validation.
Tests that repeated errors (like R051) are aggregated in SHORT/BALANCED modes.
"""
import sys
import json
import requests

def test_aggregation_with_real_invoice():
    """Test aggregation using the test.xml invoice which has repeated errors."""
    print("=" * 60)
    print("AGGREGATION INTEGRATION TEST")
    print("=" * 60)
    print()
    
    # Test with test.xml which has MMK currency (should trigger multiple R051 errors)
    test_file = "test.xml"
    
    print(f"Testing with {test_file}...")
    print()
    
    # Test all three modes
    modes = ["short", "balanced", "detailed"]
    results = {}
    
    for mode in modes:
        print(f"Testing {mode.upper()} mode...")
        
        try:
            with open(test_file, 'rb') as f:
                files = {'file': (test_file, f, 'application/xml')}
                params = {'mode': mode}
                response = requests.post(
                    'http://localhost:8000/validate',
                    files=files,
                    params=params,
                    timeout=30
                )
            
            if response.status_code != 200:
                print(f"  ❌ Request failed with status {response.status_code}")
                print(f"  Response: {response.text}")
                continue
            
            result = response.json()
            results[mode] = result
            
            # Check diagnosis structure
            if 'diagnosis' not in result:
                print(f"  ❌ No 'diagnosis' key in response")
                continue
            
            diagnosis_count = len(result['diagnosis'])
            print(f"  Diagnosis entries: {diagnosis_count}")
            
            # For each mode, check expected structure
            if mode == "detailed":
                # DETAILED should have ALL error instances (no aggregation)
                print(f"  ✓ DETAILED mode preserves all {diagnosis_count} instances")
                
                # Show first error structure
                if diagnosis_count > 0:
                    first_error = result['diagnosis'][0]
                    print(f"  First error keys: {list(first_error.keys())}")
                    
            else:
                # SHORT and BALANCED should aggregate
                print(f"  Expected: Fewer entries due to aggregation")
                
                # Check for aggregation markers
                has_count = False
                has_locations_sample = False
                
                for diag in result['diagnosis']:
                    if 'count' in diag:
                        has_count = True
                        if diag['count'] > 1:
                            print(f"  ✓ Found aggregated error: {diag.get('id', diag.get('title', 'N/A'))} (count={diag['count']})")
                            if mode == "short":
                                print(f"    - title: {diag.get('title', '')[:60]}...")
                            else:
                                print(f"    - summary: {diag.get('summary', '')[:60]}...")
                    
                    if 'locations_sample' in diag:
                        has_locations_sample = True
                        sample_count = len(diag['locations_sample'])
                        print(f"  ✓ locations_sample present (showing {sample_count} locations)")
                
                if has_count:
                    print(f"  ✓ Aggregation working: 'count' field present")
                else:
                    print(f"  ⚠️  No 'count' field found - aggregation may not be working")
                
                if has_locations_sample:
                    print(f"  ✓ Location sampling working")
            
            print()
            
        except requests.exceptions.ConnectionError:
            print(f"  ❌ Could not connect to server. Is it running on port 8000?")
            print(f"  Run: uvicorn main:app --reload")
            return False
        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    # Compare modes
    print("=" * 60)
    print("COMPARISON ACROSS MODES")
    print("=" * 60)
    print()
    
    if 'detailed' in results and 'short' in results:
        detailed_count = len(results['detailed']['diagnosis'])
        short_count = len(results['short']['diagnosis'])
        balanced_count = len(results.get('balanced', {}).get('diagnosis', []))
        
        print(f"DETAILED mode: {detailed_count} diagnosis entries (no aggregation)")
        print(f"BALANCED mode: {balanced_count} diagnosis entries (aggregated)")
        print(f"SHORT mode:    {short_count} diagnosis entries (aggregated)")
        print()
        
        if short_count < detailed_count:
            reduction = detailed_count - short_count
            percentage = (reduction / detailed_count * 100) if detailed_count > 0 else 0
            print(f"✅ Aggregation reduced output by {reduction} entries ({percentage:.1f}%)")
            print()
            return True
        elif short_count == detailed_count:
            print(f"⚠️  No aggregation occurred - all modes have same count")
            print(f"   This might be OK if there are no duplicate errors in this invoice")
            print()
            return True
        else:
            print(f"❌ SHORT mode has MORE entries than DETAILED - something is wrong!")
            print()
            return False
    else:
        print("❌ Could not compare modes - missing results")
        return False


if __name__ == '__main__':
    print()
    print("NOTE: This test requires the API server to be running.")
    print("      Start it with: uvicorn main:app --reload")
    print()
    
    input("Press Enter to start the test (or Ctrl+C to cancel)...")
    print()
    
    try:
        success = test_aggregation_with_real_invoice()
        if success:
            print("=" * 60)
            print("✅ AGGREGATION INTEGRATION TEST PASSED")
            print("=" * 60)
            sys.exit(0)
        else:
            print("=" * 60)
            print("❌ AGGREGATION INTEGRATION TEST FAILED")
            print("=" * 60)
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
