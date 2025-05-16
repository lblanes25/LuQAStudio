"""
Excel Formula Converter: Project Configuration

This module provides configuration options for the Excel Formula Converter
integration, allowing for flexible deployment and testing.
"""

import logging
import os
import yaml
from typing import Dict, Any, Optional

# Configure logging
logger = logging.getLogger("qa_analytics")

# Default configuration
DEFAULT_CONFIG = {
    "parser": {
        "use_new_converter": True,      # Whether to use the new converter if available
        "fallback_to_legacy": True,     # Whether to fall back to legacy parser if new fails
        "strict_mode": False,           # Whether to fail on formula errors
        "safe_evaluation": True         # Whether to use safe evaluation
    },
    "ui": {
        "show_parser_info": True,       # Whether to show which parser is being used
        "enable_examples": True,        # Whether to enable example buttons
        "enable_testing": True          # Whether to enable formula testing
    },
    "testing": {
        "max_sample_records": 100,      # Maximum number of sample records to generate
        "runtime_validation": True,     # Whether to validate formulas at runtime
        "allow_complex_formulas": True  # Whether to allow complex formulas
    },
    "performance": {
        "timeout_seconds": 5,           # Maximum time for formula evaluation
        "cache_parsed_formulas": True   # Whether to cache parsed formulas
    }
}


class ConfigManager:
    """Configuration manager for Excel Formula Converter"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the configuration manager.
        
        Args:
            config_path: Optional path to configuration file
        """
        self.config_path = config_path
        self.config = DEFAULT_CONFIG.copy()
        
        # Load configuration from file if available
        if config_path and os.path.exists(config_path):
            self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from file"""
        try:
            with open(self.config_path, 'r') as f:
                file_config = yaml.safe_load(f)
            
            # Update configuration with values from file
            if file_config:
                self._update_nested_dict(self.config, file_config)
                
            logger.info(f"Loaded formula converter configuration from {self.config_path}")
            
        except Exception as e:
            logger.error(f"Error loading configuration from {self.config_path}: {e}")
    
    def _update_nested_dict(self, d: Dict, u: Dict) -> Dict:
        """
        Update a nested dictionary with values from another dictionary.
        
        Args:
            d: Dictionary to update
            u: Dictionary with values to update
            
        Returns:
            Updated dictionary
        """
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                d[k] = self._update_nested_dict(d[k], v)
            else:
                d[k] = v
        return d
    
    def save_config(self, config_path: Optional[str] = None) -> bool:
        """
        Save the current configuration to a file.
        
        Args:
            config_path: Optional path to save configuration to
            
        Returns:
            True if successful, False otherwise
        """
        path = config_path or self.config_path
        if not path:
            logger.error("No configuration path specified")
            return False
        
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            # Save configuration
            with open(path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False)
                
            logger.info(f"Saved formula converter configuration to {path}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving configuration to {path}: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key.
        
        Args:
            key: Configuration key (can be nested using dots)
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        keys = key.split('.')
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value by key.
        
        Args:
            key: Configuration key (can be nested using dots)
            value: Value to set
        """
        keys = key.split('.')
        config = self.config
        
        # Navigate to the nested dictionary
        for k in keys[:-1]:
            if k not in config or not isinstance(config[k], dict):
                config[k] = {}
            config = config[k]
        
        # Set the value
        config[keys[-1]] = value
    
    def reset_to_defaults(self) -> None:
        """Reset configuration to defaults"""
        self.config = DEFAULT_CONFIG.copy()


# Create a singleton instance for use throughout the application
config = ConfigManager()


# Simple CLI for testing configuration
def main():
    """Command-line interface for testing configuration"""
    import argparse
    import pprint
    
    parser = argparse.ArgumentParser(description="Excel Formula Converter Configuration")
    parser.add_argument("--config", help="Path to configuration file")
    parser.add_argument("--save", help="Save configuration to file")
    parser.add_argument("--get", help="Get configuration value (e.g. parser.use_new_converter)")
    parser.add_argument("--set", help="Set configuration value (KEY=VALUE)")
    parser.add_argument("--reset", action="store_true", help="Reset configuration to defaults")
    parser.add_argument("--print", action="store_true", help="Print current configuration")
    
    args = parser.parse_args()
    
    # Create configuration manager
    config_manager = ConfigManager(args.config)
    
    # Process commands
    if args.get:
        value = config_manager.get(args.get)
        print(f"{args.get} = {value}")
    
    if args.set:
        if "=" not in args.set:
            print("Error: --set requires KEY=VALUE format")
        else:
            key, value = args.set.split("=", 1)
            
            # Convert value to appropriate type
            if value.lower() in ("true", "yes", "1"):
                value = True
            elif value.lower() in ("false", "no", "0"):
                value = False
            elif value.isdigit():
                value = int(value)
            elif value.replace(".", "", 1).isdigit():
                value = float(value)
                
            config_manager.set(key, value)
            print(f"Set {key} = {value}")
    
    if args.reset:
        config_manager.reset_to_defaults()
        print("Reset configuration to defaults")
    
    if args.save:
        if config_manager.save_config(args.save):
            print(f"Saved configuration to {args.save}")
        else:
            print(f"Failed to save configuration to {args.save}")
    
    if args.print or not any([args.get, args.set, args.reset, args.save]):
        print("Current configuration:")
        pprint.pprint(config_manager.config)


if __name__ == "__main__":
    main()
