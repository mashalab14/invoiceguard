import json
import logging
import os
import fcntl
import time
from pathlib import Path
from typing import Dict, List, Set
from diagnostics.types import ErrorItem

logger = logging.getLogger(__name__)


class DependencyFilter:
    """Filter for suppressing dependent errors based on parent-child relationships."""
    
    def __init__(self):
        """Initialize the dependency filter and load configuration."""
        self.dependencies: Dict[str, List[str]] = {}
        self._config_path = Path(__file__).resolve().parent.parent / "config" / "dependencies.json"
        self._last_modified = 0
        self._load_dependencies()
    
    def _should_reload_config(self) -> bool:
        """Check if the configuration file has been modified since last load."""
        try:
            current_modified = os.path.getmtime(self._config_path)
            return current_modified > self._last_modified
        except OSError:
            return False
    
    def _load_dependencies(self) -> None:
        """Load dependencies configuration from JSON file with atomic read and file locking."""
        try:
            # Update last modified time first
            self._last_modified = os.path.getmtime(self._config_path)
            
            # Atomic read with file locking to prevent race conditions during high traffic
            config_data = self._atomic_read_config()
            if config_data is None:
                logger.warning("Failed to read config file atomically, keeping current configuration")
                return
                
            # Validate schema: Dict[str, List[str]]
            if not isinstance(config_data, dict):
                logger.warning(f"Invalid dependencies config: expected dict, got {type(config_data).__name__}")
                return
            
            new_dependencies = {}
            for parent_id, child_list in config_data.items():
                if not isinstance(parent_id, str):
                    logger.warning(f"Invalid parent ID type: {type(parent_id).__name__}, skipping")
                    continue
                
                if not isinstance(child_list, list):
                    logger.warning(f"Invalid child list type for {parent_id}: {type(child_list).__name__}, skipping")
                    continue
                
                # Validate all children are strings
                valid_children = []
                for child in child_list:
                    if isinstance(child, str):
                        valid_children.append(child)
                    else:
                        logger.warning(f"Invalid child ID type for {parent_id}: {type(child).__name__}, skipping child")
                
                new_dependencies[parent_id] = valid_children
            
            # Atomic update
            old_count = len(self.dependencies)
            self.dependencies = new_dependencies
            new_count = len(self.dependencies)
            
            if old_count != new_count:
                logger.info(f"Dependencies config reloaded: {old_count} → {new_count} parent-child relationships")
            else:
                logger.debug(f"Dependencies config reloaded: {new_count} relationships")
                
        except FileNotFoundError:
            logger.warning(f"Dependencies config not found at {self._config_path}, using empty configuration")
            self.dependencies = {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in dependencies config: {e}")
        except Exception as e:
            logger.error(f"Failed to load dependencies config: {e}")
    
    def _atomic_read_config(self) -> dict:
        """
        Atomically read configuration file with file locking to prevent race conditions.
        
        Returns:
            dict: Parsed JSON configuration, or None if read fails
        """
        max_retries = 3
        retry_delay = 0.1  # 100ms
        
        for attempt in range(max_retries):
            try:
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    # Acquire shared lock for reading (multiple readers, no writers)
                    fcntl.flock(f.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                    
                    try:
                        # Read entire file content first
                        content = f.read()
                        
                        # Parse JSON from complete content (not streaming)
                        data = json.loads(content)
                        
                        logger.debug(f"Successfully loaded config atomically (attempt {attempt + 1})")
                        return data
                        
                    finally:
                        # Always release the lock
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        
            except (OSError, IOError) as e:
                if e.errno == 11:  # EAGAIN - file is locked by writer
                    logger.debug(f"Config file locked by writer, retrying in {retry_delay}s (attempt {attempt + 1})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    logger.warning(f"File system error reading config: {e}")
                    break
                    
            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode error in config file: {e}")
                # On decode error, try once more in case file was partially written
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                break
                
            except Exception as e:
                logger.warning(f"Unexpected error reading config: {e}")
                break
        
        return None
    
    def reload_if_changed(self) -> bool:
        """
        Reload configuration if file has changed.
        
        Returns:
            True if configuration was reloaded, False otherwise
        """
        if self._should_reload_config():
            logger.info("Dependencies configuration file changed, reloading...")
            self._load_dependencies()
            return True
        return False
    
    def apply(self, errors: List[ErrorItem]) -> None:
        """
        Apply dependency filtering to suppress dependent errors with hot-reload support.
        
        Args:
            errors: List of error items to process (modified in place)
        """
        # Check for config changes before processing
        self.reload_if_changed()
        
        if not self.dependencies:
            return
        
        # Build set of all present error IDs (O(N))
        present_ids: Set[str] = {error["id"] for error in errors}
        
        # Collect all children to suppress (O(N))
        children_to_suppress: Set[str] = set()
        
        for parent_id in present_ids:
            if parent_id in self.dependencies:
                for child_id in self.dependencies[parent_id]:
                    # Constraint: Don't suppress parent itself
                    if child_id != parent_id:
                        children_to_suppress.add(child_id)
        
        # Apply suppression (O(N))
        for error in errors:
            if error["id"] in children_to_suppress:
                error["suppressed"] = True
