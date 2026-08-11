"""Shared configuration loading for preflight scripts."""

import logging
import yaml
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "test-config.yaml"


def load_config() -> Optional[Dict[str, Any]]:
    """Load workflow configuration from test-config.yaml."""
    if not CONFIG_PATH.exists():
        logger.warning(f"Config not found at {CONFIG_PATH}")
        return None

    try:
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse config: {e}")
        return None
