import re
from typing import Any, Dict, Optional
from app.extraction.validation.base import BaseValidator

class TaxIdValidator(BaseValidator):
    """Validator for Thai Tax ID (13 digits)."""

    def validate(self, value: Any, context: Optional[Dict[str, Any]] = None) -> bool:
        if not value:
            return False
        digits = re.sub(r"\D", "", str(value))
        return len(digits) == 13

    def normalize(self, value: Any) -> Any:
        if not value:
            return None
        return re.sub(r"\D", "", str(value))
