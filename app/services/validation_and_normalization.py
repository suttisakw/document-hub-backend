"""
ValidationAndNormalization: Multi-stage validation and normalization module.

Pipeline:
1. Normalize Thai date formats (DD/MM/YYYY, Thai months, Buddhist year)
2. Normalize currency (remove commas, convert to float)
3. Validate fields (tax_id 13 digits, amounts logical, dates valid)
4. Reduce confidence on validation failures
5. Flag fields needing review
6. Return updated Document object

Handles edge cases:
- Missing data
- Partial dates
- Various currency formats
- Invalid thai dates
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Any
from enum import Enum
from datetime import datetime, date
import re
from abc import ABC, abstractmethod


# ====== ENUMS & CONSTANTS ======

class ValidationStatus(str, Enum):
    """Validation result status."""
    VALID = "valid"
    INVALID = "invalid"
    PARTIAL = "partial"
    WARNING = "warning"
    NEEDS_REVIEW = "needs_review"


class FieldType(str, Enum):
    """Field data types."""
    DATE = "date"
    CURRENCY = "currency"
    INTEGER = "integer"
    TAX_ID = "tax_id"
    TEXT = "text"


# Thai month mapping
THAI_MONTH_NAMES = {
    "มกราคม": 1, "มค": 1,
    "กุมภาพันธ์": 2, "กพ": 2,
    "มีนาคม": 3, "มีค": 3,
    "เมษายน": 4, "เมย": 4,
    "พฤษภาคม": 5, "พค": 5,
    "มิถุนายน": 6, "มิย": 6,
    "กรกฎาคม": 7, "กค": 7,
    "สิงหาคม": 8, "สค": 8,
    "กันยายน": 9, "กย": 9,
    "ตุลาคม": 10, "ตค": 10,
    "พฤศจิกายน": 11, "พย": 11,
    "ธันวาคม": 12, "ธค": 12,
}

THAI_MONTH_NAMES_REVERSE = {v: k for k, v in THAI_MONTH_NAMES.items()}

# Thai digit mapping
THAI_DIGITS = {
    "๐": "0", "๑": "1", "๒": "2", "๓": "3", "๔": "4",
    "๕": "5", "๖": "6", "๗": "7", "๘": "8", "๙": "9"
}

# Buddhist year offset (BE = CE + 543)
BUDDHIST_YEAR_OFFSET = 543


# ====== DATA CLASSES ======

@dataclass
class ValidationResult:
    """Result of field validation."""
    field_name: str
    original_value: str
    normalized_value: Optional[str] = None
    status: ValidationStatus = ValidationStatus.VALID
    is_valid: bool = True
    confidence_adjustment: float = 0.0  # Reduction amount (0-1.0)
    needs_review: bool = False
    error_message: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentValidationReport:
    """Report of all validations for a document."""
    document_id: str
    overall_valid: bool
    validation_count: int
    valid_count: int
    invalid_count: int
    warnings_count: int
    needs_review_count: int
    results: List[ValidationResult] = field(default_factory=list)
    overall_confidence_adjustment: float = 0.0
    fields_needing_review: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


# ====== DATE NORMALIZATION ======

class ThaiDateParser:
    """Parse and normalize Thai date formats."""

    def __init__(self):
        """Initialize Thai date parser."""
        pass

    def convert_thai_digits_to_arabic(self, text: str) -> str:
        """Convert Thai digits (๐-๙) to Arabic digits (0-9)."""
        for thai_digit, arabic_digit in THAI_DIGITS.items():
            text = text.replace(thai_digit, arabic_digit)
        return text

    def replace_thai_month_names(self, text: str) -> str:
        """Replace Thai month names with numbers."""
        for thai_name, month_num in THAI_MONTH_NAMES.items():
            text = text.replace(thai_name, str(month_num))
        return text

    def convert_buddhist_to_gregorian(self, year: int) -> int:
        """Convert Buddhist year to Gregorian."""
        if year > 2000:  # Already Gregorian
            return year
        if year > 500:  # Buddhist year (BE)
            return year - BUDDHIST_YEAR_OFFSET
        return year  # Unknown format, return as-is

    def parse_date(self, text: str) -> Tuple[Optional[date], float, str]:
        """
        Parse Thai date format.
        
        Args:
            text: Date text (e.g., "15/02/2567", "15 กุมภาพันธ์ 2567")
            
        Returns:
            (parsed_date, confidence, format_detected)
        """
        if not text or not isinstance(text, str):
            return None, 0.0, "empty"

        text = text.strip()

        # Convert Thai digits to Arabic
        text = self.convert_thai_digits_to_arabic(text)

        # Replace Thai month names
        text = self.replace_thai_month_names(text)

        # Try various formats
        formats = [
            (r"(\d{1,2})[/\-\s]+(\d{1,2})[/\-\s]+(\d{4})", "DD/MM/YYYY"),
            (r"(\d{4})[/\-\s]+(\d{1,2})[/\-\s]+(\d{1,2})", "YYYY/MM/DD"),
            (r"(\d{1,2})[/\-\s]+(\d{1,2})[/\-\s]+(\d{2})", "DD/MM/YY"),
        ]

        for pattern, format_name in formats:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                
                if format_name == "DD/MM/YYYY":
                    day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                elif format_name == "YYYY/MM/DD":
                    year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                else:  # DD/MM/YY
                    day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                    year = year + 2000 if year < 100 else year

                # Convert Buddhist year to Gregorian
                year = self.convert_buddhist_to_gregorian(year)

                # Validate ranges
                if 1 <= month <= 12 and 1 <= day <= 31 and year > 1900:
                    try:
                        parsed_date = date(year, month, day)
                        confidence = 0.95 if format_name == "DD/MM/YYYY" else 0.85
                        return parsed_date, confidence, format_name
                    except ValueError:
                        # Invalid day for month
                        continue

        return None, 0.0, "unrecognized"

    def normalize_date(self, text: str) -> Tuple[Optional[str], Optional[date], float, str]:
        """
        Normalize date to ISO format (YYYY-MM-DD).
        
        Returns:
            (normalized_string, date_object, confidence, format_detected)
        """
        parsed_date, confidence, format_name = self.parse_date(text)

        if parsed_date:
            normalized = parsed_date.isoformat()
            return normalized, parsed_date, confidence, format_name

        return None, None, 0.0, "invalid"


# ====== CURRENCY NORMALIZATION ======

class CurrencyNormalizer:
    """Normalize currency values."""

    @staticmethod
    def normalize(text: str) -> Tuple[Optional[float], float]:
        """
        Parse and normalize currency string.
        
        Args:
            text: Currency text (e.g., "1,000.50", "1000", "$1000.50")
            
        Returns:
            (value_as_float, confidence)
        """
        if not text or not isinstance(text, str):
            return None, 0.0

        # Convert Thai digits to Arabic
        for thai_digit, arabic_digit in THAI_DIGITS.items():
            text = text.replace(thai_digit, arabic_digit)

        # Remove common currency symbols
        currency_symbols = ["$", "₽", "€", "¥", "₹", "£", "฿"]
        for symbol in currency_symbols:
            text = text.replace(symbol, "")

        # Remove spaces
        text = text.replace(" ", "")

        # Handle different decimal separators
        # Pattern: thousands separator + decimal separator
        # Common: 1,000.50 or 1.000,50
        
        # Count commas and periods/dots
        comma_count = text.count(",")
        period_count = text.count(".")

        # Remove all non-numeric except first separator
        # Try to identify format
        if comma_count > 0 and period_count > 0:
            # Has both - determine which is decimal
            last_comma = text.rfind(",")
            last_period = text.rfind(".")
            
            if last_period > last_comma:
                # Period is decimal: remove commas, keep period
                text = text.replace(",", "")
            else:
                # Comma is decimal: remove periods, replace comma with period
                text = text.replace(".", "")
                text = text.replace(",", ".")
        elif comma_count > 0:
            # Only commas - assume format: 1,000.00 (remove commas)
            # OR format: 1.000,00 (check distance)
            last_comma = text.rfind(",")
            part_after = text[last_comma + 1:]
            
            if len(part_after) == 2:
                # European format: 1.000,00
                text = text.replace(".", "")
                text = text.replace(",", ".")
            else:
                # US format: remove commas
                text = text.replace(",", "")
        elif period_count > 1:
            # Multiple periods - likely thousands separator
            text = text.replace(".", "")

        # Clean up
        text = text.strip()

        # Try to parse
        try:
            value = float(text)
            confidence = 0.95 if abs(value) > 0 else 0.7
            return value, confidence
        except ValueError:
            return None, 0.0


# ====== VALIDATORS ======

class FieldValidator:
    """Validate individual fields."""

    @staticmethod
    def validate_tax_id(value: str) -> Tuple[bool, float, str]:
        """
        Validate Thai tax ID (13 digits).
        
        Returns:
            (is_valid, confidence, error_message)
        """
        if not value:
            return False, 0.0, "Tax ID is empty"

        # Remove all non-digits
        tax_id = re.sub(r"\D", "", str(value))

        # Must be 13 digits
        if len(tax_id) != 13:
            return False, 0.0, f"Tax ID must be 13 digits, got {len(tax_id)}"

        # Validate checksum (Thai tax ID checksum algorithm)
        try:
            digits = [int(d) for d in tax_id]
            
            # Checksum calculation
            weights = list(range(13, 1, -1))  # [13, 12, 11, ..., 2]
            checksum = sum(d * w for d, w in zip(digits[:-1], weights[:-1])) % 11
            check_digit = (11 - checksum) % 10

            if digits[-1] == check_digit:
                return True, 0.98, ""
            else:
                return False, 0.5, "Tax ID checksum failed"
        except Exception as e:
            return False, 0.3, f"Tax ID validation error: {str(e)}"

    @staticmethod
    def validate_amounts(
        subtotal: Optional[float],
        vat: Optional[float],
        total: Optional[float],
        tolerance: float = 0.05
    ) -> Tuple[bool, float, List[str]]:
        """
        Validate amount relationships with tolerance.
        
        Returns:
            (is_valid, confidence, errors)
        """
        errors = []

        if subtotal is None or total is None:
            return True, 0.9, [] # Cannot fully validate without both

        # Logic consistency check (Subtotal + VAT = Total)
        calculated_vat = vat if vat is not None else 0.0
        calculated_diff = abs((subtotal + calculated_vat) - total)
        
        if calculated_diff > tolerance:
            errors.append(
                f"Amount mismatch: {subtotal} + {calculated_vat} != {total} (diff: {calculated_diff})"
            )

        # Check for negative values
        for name, value in [("subtotal", subtotal), ("vat", vat), ("total", total)]:
            if value is not None and value < 0:
                errors.append(f"{name} should not be negative")

        is_valid = len(errors) == 0
        confidence = 1.0 if is_valid else 0.5
        
        return is_valid, confidence, errors

    @staticmethod
    def resolve_numeric_mismatch(
        subtotal: float,
        vat: float,
        total: float,
        confidences: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Determine which numeric field is likely wrong based on confidences
        and suggest the corrected value.
        """
        # Scenario 1: Total is wrong (Subtotal and VAT are correct)
        s1_total = subtotal + vat
        s1_conf = (confidences.get("subtotal", 0.5) + confidences.get("vat", 0.5)) / 2

        # Scenario 2: VAT is wrong (Subtotal and Total are correct)
        s2_vat = total - subtotal
        s2_conf = (confidences.get("subtotal", 0.5) + confidences.get("total_amount", 0.5)) / 2

        # Scenario 3: Subtotal is wrong (VAT and Total are correct)
        s3_subtotal = total - vat
        s3_conf = (confidences.get("vat", 0.5) + confidences.get("total_amount", 0.5)) / 2

        scenarios = [
            {"target": "total_amount", "suggested_value": s1_total, "confidence": s1_conf},
            {"target": "vat", "suggested_value": s2_vat, "confidence": s2_conf},
            {"target": "subtotal", "suggested_value": s3_subtotal, "confidence": s3_conf},
        ]

        # Pick the scenario with the highest confidence
        scenarios.sort(key=lambda x: x["confidence"], reverse=True)
        return scenarios[0]

    @staticmethod
    def validate_date(parsed_date: Optional[date]) -> Tuple[bool, float, str]:
        """
        Validate a date.
        
        Returns:
            (is_valid, confidence, error_message)
        """
        if parsed_date is None:
            return False, 0.0, "Date could not be parsed"

        # Check if date is reasonable (not too far in future or past)
        today = date.today()
        
        if parsed_date > today:
            return False, 0.3, f"Date {parsed_date} is in the future"

        if parsed_date.year < 1900:
            return False, 0.1, f"Date {parsed_date} is too old"

        return True, 0.95, ""


class JsonSchemaValidator:
    """Validate against a JSON Schema."""
    
    def validate(self, data: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
        """Returns a list of error messages."""
        try:
            import jsonschema
            from jsonschema import validate as validate_schema
            validate_schema(instance=data, schema=schema)
            return []
        except ImportError:
            return ["jsonschema library not installed"]
        except Exception as e:
            return [str(e)]


# ====== MAIN ORCHESTRATOR ======

class ValidationAndNormalizationEngine:
    """
    Main validation and normalization orchestrator.
    
    Processes document fields:
    1. Normalizes Thai dates (to ISO YYYY-MM-DD)
    2. Normalizes currency (to float)
    3. Validates all fields against dynamic JSON Schema
    4. Adjusts confidence scores
    5. Flags fields needing review
    6. Returns updated document
    """

    def __init__(self):
        """Initialize validation engine."""
        self.date_parser = ThaiDateParser()
        self.currency_normalizer = CurrencyNormalizer()
        self.validator = FieldValidator()
        self.schema_validator = JsonSchemaValidator()

    def validate_and_normalize_field(
        self,
        field_name: str,
        field_value: Optional[str],
        field_type: FieldType,
        original_confidence: float = 0.9
    ) -> ValidationResult:
        """
        Validate and normalize single field.
        
        Args:
            field_name: Name of field
            field_value: Value to validate
            field_type: Type of field
            original_confidence: Original extraction confidence
            
        Returns:
            ValidationResult with normalized value and adjustments
        """
        result = ValidationResult(
            field_name=field_name,
            original_value=str(field_value) if field_value else ""
        )

        if not field_value:
            result.is_valid = False
            result.status = ValidationStatus.INVALID
            result.error_message = "Field is empty"
            result.confidence_adjustment = 0.3
            result.needs_review = True
            return result

        # Process by type
        if field_type == FieldType.DATE:
            return self._validate_date(result, field_value)
        elif field_type == FieldType.CURRENCY:
            return self._validate_currency(result, field_value)
        elif field_type == FieldType.TAX_ID:
            return self._validate_tax_id(result, field_value)
        elif field_type == FieldType.INTEGER:
            return self._validate_integer(result, field_value)
        else:
            # TEXT type - always valid if non-empty
            result.normalized_value = str(field_value)
            result.status = ValidationStatus.VALID
            return result

    def _validate_date(self, result: ValidationResult, field_value: str) -> ValidationResult:
        """Validate and normalize date field."""
        normalized, parsed_date, parse_conf, format_detected = self.date_parser.normalize_date(field_value)

        result.evidence["format_detected"] = format_detected
        result.evidence["parse_confidence"] = parse_conf

        if parsed_date is None:
            result.normalized_value = field_value  # Return original
            result.is_valid = False
            result.status = ValidationStatus.INVALID
            result.error_message = "Could not parse date"
            result.confidence_adjustment = 0.4
            result.needs_review = True
            return result

        # Validate the parsed date
        is_valid, val_conf, error = self.validator.validate_date(parsed_date)
        result.evidence["validation_confidence"] = val_conf

        result.normalized_value = normalized
        result.is_valid = is_valid

        if is_valid:
            result.status = ValidationStatus.VALID
            result.confidence_adjustment = max(0, 1.0 - parse_conf)  # Only adjust if confidence is low
        else:
            result.status = ValidationStatus.INVALID
            result.error_message = error
            result.confidence_adjustment = 0.2
            result.needs_review = True

        return result

    def _validate_currency(self, result: ValidationResult, field_value: str) -> ValidationResult:
        """Validate and normalize currency field."""
        value, parse_conf = self.currency_normalizer.normalize(field_value)
        result.evidence["parse_confidence"] = parse_conf

        if value is None:
            result.normalized_value = field_value
            result.is_valid = False
            result.status = ValidationStatus.INVALID
            result.error_message = "Could not parse currency"
            result.confidence_adjustment = 0.3
            result.needs_review = True
            return result

        result.normalized_value = str(value)
        result.is_valid = True
        result.status = ValidationStatus.VALID
        result.confidence_adjustment = max(0, 1.0 - parse_conf)

        return result

    def _validate_tax_id(self, result: ValidationResult, field_value: str) -> ValidationResult:
        """Validate tax ID field."""
        is_valid, val_conf, error = self.validator.validate_tax_id(field_value)
        result.evidence["validation_confidence"] = val_conf

        # Normalize to 13 digits
        normalized = re.sub(r"\D", "", str(field_value))
        result.normalized_value = normalized if len(normalized) == 13 else field_value

        result.is_valid = is_valid
        result.status = ValidationStatus.VALID if is_valid else ValidationStatus.INVALID
        result.error_message = error if error else None
        result.confidence_adjustment = 0 if is_valid else 0.3
        result.needs_review = not is_valid

        return result

    def _validate_integer(self, result: ValidationResult, field_value: str) -> ValidationResult:
        """Validate integer field."""
        try:
            # Remove commas and parse
            normalized = re.sub(r"\D", "", str(field_value))
            value = int(normalized)
            
            result.normalized_value = str(value)
            result.is_valid = True
            result.status = ValidationStatus.VALID
            return result
        except (ValueError, AttributeError):
            result.normalized_value = field_value
            result.is_valid = False
            result.status = ValidationStatus.INVALID
            result.error_message = "Could not parse as integer"
            result.confidence_adjustment = 0.2
            result.needs_review = True
            return result

    def validate_document_fields(
        self,
        document: Dict[str, Any],
        validation_schema: Optional[Dict[str, Any]] = None
    ) -> Tuple[DocumentValidationReport, Dict[str, Any]]:
        """
        Validate and normalize all document fields.
        
        Args:
            document: Document dict with fields
            validation_schema: Optional JSON Schema for validation
            
        Returns:
            (report, updated_document)
        """
        report = DocumentValidationReport(
            document_id=document.get("id", "unknown"),
            overall_valid=True,
            validation_count=0,
            valid_count=0,
            invalid_count=0,
            warnings_count=0,
            needs_review_count=0
        )

        updated_doc = document.copy()
        field_updates = {}

        # Map of field name to (field_type, original_confidence)
        field_configs = {
            "invoice_date": (FieldType.DATE, document.get("confidence", {}).get("invoice_date", 0.9)),
            "vendor_tax_id": (FieldType.TAX_ID, document.get("confidence", {}).get("vendor_tax_id", 0.9)),
            "subtotal": (FieldType.CURRENCY, document.get("confidence", {}).get("subtotal", 0.9)),
            "vat": (FieldType.CURRENCY, document.get("confidence", {}).get("vat", 0.9)),
            "total_amount": (FieldType.CURRENCY, document.get("confidence", {}).get("total_amount", 0.9)),
            "vendor_name": (FieldType.TEXT, document.get("confidence", {}).get("vendor_name", 0.9)),
        }

        # Validate each field
        for field_name, (field_type, orig_conf) in field_configs.items():
            field_value = document.get(field_name)
            
            if field_value is None:
                continue

            result = self.validate_and_normalize_field(
                field_name, field_value, field_type, orig_conf
            )

            report.results.append(result)
            report.validation_count += 1

            if result.is_valid:
                report.valid_count += 1
            else:
                report.invalid_count += 1

            if result.needs_review:
                report.needs_review_count += 1
                report.fields_needing_review.append(field_name)

            # Update document
            if result.normalized_value:
                field_updates[field_name] = result.normalized_value

            # Adjust confidence
            if result.confidence_adjustment > 0:
                new_conf = max(0.0, orig_conf - result.confidence_adjustment)
                if "confidence" not in updated_doc:
                    updated_doc["confidence"] = {}
                updated_doc["confidence"][field_name] = new_conf

        # Validate amount relationships (if all present)
        subtotal = field_updates.get("subtotal") or document.get("subtotal")
        vat = field_updates.get("vat") or document.get("vat")
        total = field_updates.get("total_amount") or document.get("total_amount")

        # Convert to float for validation
        subtotal_float = float(subtotal) if isinstance(subtotal, (int, float, str)) else None
        vat_float = float(vat) if isinstance(vat, (int, float, str)) else None
        total_float = float(total) if isinstance(total, (int, float, str)) else None

        if subtotal_float is not None and total_float is not None:
            amounts_valid, amounts_conf, amount_errors = self.validator.validate_amounts(
                subtotal_float, vat_float, total_float
            )

            if not amounts_valid:
                report.invalid_count += 1
                report.needs_review_count += 1
                report.fields_needing_review.append("amount_relationship")
                report.overall_confidence_adjustment += 0.1
                
                # Conflict Resolution
                resolution = self.validator.resolve_numeric_mismatch(
                    subtotal_float, 
                    vat_float or 0.0, 
                    total_float, 
                    document.get("confidence", {})
                )
                
                if "resolution" not in updated_doc:
                    updated_doc["resolution_suggestions"] = []
                
                updated_doc["resolution_suggestions"].append({
                    "reason": "amount_mismatch",
                    "best_guess": resolution
                })

        # Apply field updates
        updated_doc.update(field_updates)

        # JSON Schema Validation (Phase 4.3)
        if validation_schema:
            schema_errors = self.schema_validator.validate(field_updates, validation_schema)
            for error in schema_errors:
                report.invalid_count += 1
                report.needs_review_count += 1
                report.overall_valid = False
                # We add it as a general issue
                if "schema_validation" not in updated_doc:
                    updated_doc["schema_errors"] = []
                updated_doc["schema_errors"].append(error)

        # Determine overall validity
        report.overall_valid = report.overall_valid and report.invalid_count == 0
        report.overall_confidence_adjustment = sum(
            r.confidence_adjustment for r in report.results
        ) / max(len(report.results), 1)

        return report, updated_doc

    def validate_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Public interface: validate and normalize document.
        
        Args:
            document: Document dict
            
        Returns:
            Updated document with normalized values and adjusted confidence
        """
        report, updated_doc = self.validate_document_fields(document)
        
        # Add validation metadata
        updated_doc["validation"] = {
            "status": "valid" if report.overall_valid else "invalid",
            "fields_needing_review": report.fields_needing_review,
            "issues_count": report.invalid_count,
            "confidence_adjustment": report.overall_confidence_adjustment,
            "timestamp": report.timestamp.isoformat()
        }

        return updated_doc


# ====== FACTORY FUNCTION ======

def create_validation_engine() -> ValidationAndNormalizationEngine:
    """Factory function to create validation engine."""
    return ValidationAndNormalizationEngine()
