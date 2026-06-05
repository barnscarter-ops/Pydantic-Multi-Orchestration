import yaml
from pathlib import Path
from typing import Dict, Any

class ConfigLoader:
    """Handles loading and parsing of the PACC routing configuration."""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self._config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found at {self.config_path}")

        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def get_routing_rule(self, agent_role: str) -> Dict[str, Any]:
        """Returns the routing rule for a specific agent role, or the default if not found."""
        rules = self._config.get("routing_rules", [])
        for rule in rules:
            if rule.get("agent_role") == agent_role:
                return rule

        # Fallback to a generic rule if role not found
        return {
            "primary": self._config.get("default_local_model", "llama3"),
            "fallbacks": [],
            "escalation_thresholds": {"max_retries": 1, "timeout_seconds": 30}
        }

    @property
    def all_config(self) -> Dict[str, Any]:
        return self._config
