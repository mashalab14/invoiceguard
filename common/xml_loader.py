import lxml.etree
from typing import Dict
import logging

logger = logging.getLogger(__name__)


class XMLParsingError(Exception):
    """Exception raised when XML parsing fails."""
    pass


class SafeXMLLoader:
    """Secure XML loader with proper error handling."""
    
    def parse(self, content: bytes) -> lxml.etree._ElementTree:
        """
        Parse XML content securely.
        
        Args:
            content: Raw XML bytes
            
        Returns:
            Parsed XML tree
            
        Raises:
            XMLParsingError: If parsing fails
        """
        try:
            # Configure secure parser
            parser = lxml.etree.XMLParser(
                resolve_entities=False,
                no_network=True,
                huge_tree=False
            )
            
            # Parse and wrap in ElementTree
            root = lxml.etree.fromstring(content, parser=parser)
            tree = lxml.etree.ElementTree(root)
            return tree
            
        except lxml.etree.XMLSyntaxError as e:
            raise XMLParsingError(f"XML syntax error: {e}")
        except lxml.etree.DocumentInvalid as e:
            raise XMLParsingError(f"XML document invalid: {e}")
        except Exception as e:
            raise XMLParsingError(f"XML parsing failed: {e}")
    
    def get_namespaces(self, tree: lxml.etree._ElementTree) -> Dict[str, str]:
        """
        Extract namespaces from XML tree.
        
        Args:
            tree: Parsed XML tree
            
        Returns:
            Dictionary of namespace mappings (strictly strings)
        """
        root = tree.getroot()
        nsmap = root.nsmap or {}
        
        result: Dict[str, str] = {}
        
        for key, value in nsmap.items():
            # Skip entries with None values
            if value is None:
                continue
            
            # Handle default namespace
            if key is None:
                # Check if "inv" already exists in the map
                if "inv" in nsmap.values():
                    key = "inv_default"
                else:
                    key = "inv"
            
            # Ensure both key and value are strings
            result[str(key)] = str(value)
        
        return result
