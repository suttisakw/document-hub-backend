import re
from typing import Any, Dict, Optional
from app.extraction.validation.base import BaseValidator

class CurrencyValidator(BaseValidator):
    """Validator for currency/amount fields."""

    def validate(self, value: Any, context: Optional[Dict[str, Any]] = None) -> bool:
        if not value:
            return False
        clean_val = str(value).replace(",", "").replace("$", "").strip()
        try:
            float(clean_val)
            return True
        except ValueError:
            return False

    def normalize(self, value: Any) -> Any:
        if value is None:
            return None
        clean_val = str(value).replace(",", "").replace("$", "").strip()
        try:
            return float(clean_val)
        except ValueError:
            return value
