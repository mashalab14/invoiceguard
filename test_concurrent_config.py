#!/usr/bin/env python3
"""
Test Concurrent Config Access
Simulates high traffic scenario to validate file locking works correctly
"""
import sys
import os
import threading
import time
import json
import random
sys.path.insert(0, os.getcwd())

from diagnostics.dependency_filter import DependencyFilter
from safe_config_update import safe_update_dependencies


def reader_worker(worker_id: int, results: dict, num_reads: int = 50):
    """Simulate high-frequency config reads (pipeline processing)."""
    results[f"reader_{worker_id}"] = {"successes": 0, "failures": 0, "errors": []}
    
    dep_filter = DependencyFilter()
    
    for i in range(num_reads):
        try:
            # Simulate processing load
            time.sleep(random.uniform(0.01, 0.05))  # 10-50ms between reads
            
            # Try to reload if changed
            was_reloaded = dep_filter.reload_if_changed()
            
            # Verify we can access dependencies without errors
            dep_count = len(dep_filter.dependencies)
            
            results[f"reader_{worker_id}"]["successes"] += 1
            
            if was_reloaded:
                print(f"📖 Reader {worker_id}: Config reloaded successfully ({dep_count} rules)")
                
        except Exception as e:
            results[f"reader_{worker_id}"]["failures"] += 1
            results[f"reader_{worker_id}"]["errors"].append(str(e))
            print(f"❌ Reader {worker_id} error: {e}")


def writer_worker(worker_id: int, results: dict, num_writes: int = 10):
    """Simulate config updates during high traffic."""
    results[f"writer_{worker_id}"] = {"successes": 0, "failures": 0, "errors": []}
    
    config_path = "config/dependencies.json"
    
    for i in range(num_writes):
        try:
            # Simulate update intervals
            time.sleep(random.uniform(0.2, 0.5))  # 200-500ms between updates
            
            # Create a slightly different config each time
            test_config = {
                "BR-CO-15": ["UBL-CR-001", "PEPPOL-R001"],
                "BR-CO-16": ["BR-CO-15"],
                "PEPPOL-R001": [],
                f"TEST-RULE-{worker_id}-{i}": ["BR-CO-15"]  # Add unique rule
            }
            
            success = safe_update_dependencies(config_path, test_config)
            
            if success:
                results[f"writer_{worker_id}"]["successes"] += 1
                print(f"✏️  Writer {worker_id}: Config updated successfully (iteration {i+1})")
            else:
                results[f"writer_{worker_id}"]["failures"] += 1
                
        except Exception as e:
            results[f"writer_{worker_id}"]["failures"] += 1
            results[f"writer_{worker_id}"]["errors"].append(str(e))
            print(f"❌ Writer {worker_id} error: {e}")


def test_concurrent_access():
    """Test that file locking prevents race conditions during high traffic."""
    
    print("🧪 Testing Concurrent Config Access Under High Traffic")
    print("=" * 60)
    
    # Test parameters
    num_readers = 3
    num_writers = 2
    reads_per_reader = 30
    writes_per_writer = 8
    
    print(f"📊 Test configuration:")
    print(f"   Readers: {num_readers} (each performing {reads_per_reader} reads)")
    print(f"   Writers: {num_writers} (each performing {writes_per_writer} writes)")
    print(f"   Total operations: {num_readers * reads_per_reader + num_writers * writes_per_writer}")
    print()
    
    results = {}
    threads = []
    
    # Start reader threads (simulate pipeline processing)
    for i in range(num_readers):
        thread = threading.Thread(
            target=reader_worker, 
            args=(i, results, reads_per_reader)
        )
        threads.append(thread)
        thread.start()
    
    # Start writer threads (simulate config updates)
    for i in range(num_writers):
        thread = threading.Thread(
            target=writer_worker,
            args=(i, results, writes_per_writer)
        )
        threads.append(thread)
        thread.start()
    
    # Wait for all operations to complete
    for thread in threads:
        thread.join()
    
    # Analyze results
    print(f"\n📊 Concurrent Access Test Results")
    print("=" * 40)
    
    total_successes = 0
    total_failures = 0
    total_errors = []
    
    for worker_id, worker_results in results.items():
        successes = worker_results["successes"]
        failures = worker_results["failures"]
        errors = worker_results["errors"]
        
        total_successes += successes
        total_failures += failures
        total_errors.extend(errors)
        
        worker_type = "Reader" if "reader" in worker_id else "Writer"
        print(f"{worker_type} {worker_id.split('_')[1]}: {successes} successes, {failures} failures")
        
        if errors:
            for error in errors:
                print(f"   ❌ {error}")
    
    success_rate = (total_successes / (total_successes + total_failures)) * 100 if (total_successes + total_failures) > 0 else 0
    
    print(f"\n🎯 Overall Results:")
    print(f"   Total operations: {total_successes + total_failures}")
    print(f"   Successes: {total_successes}")
    print(f"   Failures: {total_failures}")
    print(f"   Success rate: {success_rate:.1f}%")
    
    # Check for JSON decode errors (the main concern)
    json_errors = [e for e in total_errors if "JSON" in e or "decode" in e.lower()]
    
    if json_errors:
        print(f"❌ JSON decode errors detected: {len(json_errors)}")
        for error in json_errors[:3]:  # Show first 3
            print(f"   {error}")
        print("🔧 File locking may need adjustment!")
        return False
    else:
        print("✅ No JSON decode errors - file locking working correctly!")
    
    if success_rate >= 95:
        print("🎉 HIGH TRAFFIC TEST PASSED: File locking prevents race conditions!")
        return True
    else:
        print("⚠️  Some failures detected - review file locking implementation")
        return False


if __name__ == "__main__":
    success = test_concurrent_access()
    sys.exit(0 if success else 1)
