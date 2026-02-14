import json
from typing import Any, Optional
from sqlmodel import Session, select
from app.models import SystemConfig
from datetime import datetime

class ConfigService:
    """Service to handle dynamic system configurations."""

    def __init__(self, db: Session):
        self.db = db

    def get_config(self, key: str, default: Any = None) -> Any:
        """Fetch a configuration value from the database."""
        config = self.db.exec(select(SystemConfig).where(SystemConfig.key == key)).first()
        if not config:
            return default
        try:
            return json.loads(config.value)
        except (ValueError, TypeError):
            return config.value

    def set_config(self, key: str, value: Any, category: str = "general"):
        """Save or update a configuration value."""
        config = self.db.exec(select(SystemConfig).where(SystemConfig.key == key)).first()
        if not config:
            config = SystemConfig(key=key, value=json.dumps(value), category=category)
        else:
            config.value = json.dumps(value)
            config.updated_at = datetime.utcnow()
        
        self.db.add(config)
        self.db.commit()
        return config

    def get_thresholds(self) -> dict:
        """Helper to get all extraction thresholds."""
        return self.get_config("extraction_thresholds", {
            "sufficient_total_confidence": 0.8,
            "field_confidence_high": 0.85,
            "field_confidence_low": 0.4
        })
