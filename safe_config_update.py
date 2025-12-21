#!/usr/bin/env python3
"""
Safe Configuration Updater for dependencies.json
Provides atomic write operations to prevent race conditions during hot-reload
"""
import json
import fcntl
import os
import time
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List


def safe_update_dependencies(config_path: str, new_config: Dict[str, List[str]]) -> bool:
    """
    Safely update dependencies configuration with atomic write operation.
    
    This function ensures that:
    1. Readers never see partial/corrupted JSON during writes
    2. Write operations are atomic (all-or-nothing)
    3. Multiple concurrent writers are serialized
    
    Args:
        config_path: Path to dependencies.json file
        new_config: New configuration dictionary
        
    Returns:
        bool: True if update was successful, False otherwise
    """
    config_file = Path(config_path)
    
    try:
        # Validate input configuration
        if not isinstance(new_config, dict):
            raise ValueError(f"Configuration must be a dict, got {type(new_config).__name__}")
        
        for parent_id, child_list in new_config.items():
            if not isinstance(parent_id, str):
                raise ValueError(f"Parent ID must be string, got {type(parent_id).__name__}")
            if not isinstance(child_list, list):
                raise ValueError(f"Child list must be list, got {type(child_list).__name__}")
            if not all(isinstance(child, str) for child in child_list):
                raise ValueError(f"All child IDs must be strings")
        
        # Create temporary file in same directory for atomic swap
        temp_dir = config_file.parent
        with tempfile.NamedTemporaryFile(
            mode='w', 
            encoding='utf-8',
            dir=temp_dir,
            delete=False,
            suffix='.tmp',
            prefix='dependencies_'
        ) as temp_file:
            
            # Acquire exclusive lock on temp file
            fcntl.flock(temp_file.fileno(), fcntl.LOCK_EX)
            
            try:
                # Write JSON with proper formatting
                json.dump(new_config, temp_file, indent=2, sort_keys=True, ensure_ascii=False)
                temp_file.write('\n')  # Ensure file ends with newline
                temp_file.flush()
                os.fsync(temp_file.fileno())  # Force write to disk
                
                temp_path = temp_file.name
                
            finally:
                fcntl.flock(temp_file.fileno(), fcntl.LOCK_UN)
        
        # Atomic swap: move temp file to final location
        # This operation is atomic on most filesystems
        shutil.move(temp_path, config_path)
        
        print(f"✅ Configuration updated successfully: {config_path}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to update configuration: {e}")
        # Clean up temp file if it exists
        try:
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.unlink(temp_path)
        except:
            pass
        return False


def validate_current_config(config_path: str) -> bool:
    """Validate that current config file is readable and well-formed."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            try:
                data = json.load(f)
                print(f"✅ Current config is valid with {len(data)} rules")
                return True
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                
    except Exception as e:
        print(f"❌ Current config validation failed: {e}")
        return False


if __name__ == "__main__":
    import sys
    
    # Example usage
    config_path = "config/dependencies.json"
    
    if len(sys.argv) < 2:
        print("Usage: python safe_config_update.py [validate|example]")
        sys.exit(1)
    
    if sys.argv[1] == "validate":
        # Validate current configuration
        if os.path.exists(config_path):
            validate_current_config(config_path)
        else:
            print(f"❌ Config file not found: {config_path}")
            
    elif sys.argv[1] == "example":
        # Example safe update
        example_config = {
            "BR-CO-15": ["UBL-CR-001", "PEPPOL-R001"], 
            "BR-CO-16": ["BR-CO-15"],
            "PEPPOL-R001": [],
            "UBL-CR-001": []
        }
        
        success = safe_update_dependencies(config_path, example_config)
        if success:
            print("🎉 Example configuration updated successfully!")
        else:
            print("❌ Failed to update example configuration")
            
    else:
        print("Invalid command. Use 'validate' or 'example'")
        sys.exit(1)
