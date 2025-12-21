import json
import logging
from pathlib import Path
from typing import Dict, List, Set
from diagnostics.types import ErrorItem

logger = logging.getLogger(__name__)


class DependencyFilter:
    """Filter for suppressing dependent errors based on parent-child relationships."""
    
    def __init__(self):
        """Initialize the dependency filter and load configuration."""
        self.dependencies: Dict[str, List[str]] = {}
        self._load_dependencies()
    
    def _load_dependencies(self) -> None:
        """Load dependencies configuration from JSON file."""
        config_path = Path(__file__).resolve().parent.parent / "config" / "dependencies.json"
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Validate schema: Dict[str, List[str]]
            if not isinstance(data, dict):
                logger.warning(f"Invalid dependencies config: expected dict, got {type(data).__name__}")
                return
            
            for parent_id, child_list in data.items():
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
                
                self.dependencies[parent_id] = valid_children
                
        except FileNotFoundError:
            logger.warning(f"Dependencies config not found at {config_path}, using empty configuration")
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in dependencies config: {e}, using empty configuration")
        except Exception as e:
            logger.warning(f"Failed to load dependencies config: {e}, using empty configuration")
    
    def apply(self, errors: List[ErrorItem]) -> None:
        """
        Apply dependency filtering to suppress dependent errors.
        
        Args:
            errors: List of error items to process (modified in place)
        """
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
