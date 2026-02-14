import dateutil.parser
from typing import Any, Dict, Optional
from app.extraction.validation.base import BaseValidator

class DateValidator(BaseValidator):
    """Validator for date fields."""

    def validate(self, value: Any, context: Optional[Dict[str, Any]] = None) -> bool:
        if not value:
            return False
        try:
            dateutil.parser.parse(str(value))
            return True
        except (ValueError, OverflowError):
            return False

    def normalize(self, value: Any) -> Any:
        if not value:
            return None
        try:
            dt = dateutil.parser.parse(str(value))
            return dt.date().isoformat()
        except (ValueError, OverflowError):
            return str(value)
