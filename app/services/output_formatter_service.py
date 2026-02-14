"""
Output Formatter Service

Handles export logic for:
- JSON export
- CSV export  
- ERP system mapping with field transformation
"""

import json
import csv
import io
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import logging

from app.schemas.output_formatter import (
    ExportFormat,
    ERPSystem,
    ExportResponse,
    ExportValidationResult,
    ExportDataRow,
    FieldMappingRule,
    ERPMapping,
    OutputFormatConfig,
)

logger = logging.getLogger(__name__)


class OutputFormatterService:
    """Service for exporting documents in various formats with field mapping."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize output formatter service.
        
        Args:
            config_path: Path to output formatter config file
        """
        self.config_path = config_path or "output_formatter_config.json"
        self.config: Optional[OutputFormatConfig] = None
        self.field_mappings: Dict[str, List[FieldMappingRule]] = {}
        self.erp_mappings: Dict[str, Dict[str, ERPMapping]] = {}
        
        # Load configuration
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from file."""
        try:
            if isinstance(self.config_path, str) and Path(self.config_path).exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config_dict = json.load(f)
                    self.config = OutputFormatConfig(**config_dict)
                    logger.info(f"Loaded output formatter config from {self.config_path}")
            else:
                # Create default config
                self.config = OutputFormatConfig()
                logger.warning(f"Config file not found at {self.config_path}, using defaults")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.config = OutputFormatConfig()
    
    def reload_config(self) -> None:
        """Reload configuration from file."""
        self._load_config()
    
    def apply_field_mapping(
        self,
        fields: Dict[str, Any],
        mapping_rules: List[FieldMappingRule]
    ) -> Dict[str, Any]:
        """
        Apply field mapping rules to fields.
        
        Transforms field names and values according to mapping rules.
        
        Args:
            fields: Source fields dict
            mapping_rules: Mapping rules to apply
            
        Returns:
            Mapped fields dict
        """
        mapped_fields = {}
        
        for rule in mapping_rules:
            # Get source value
            source_value = fields.get(rule.source_field, rule.default_value)
            
            # Skip if required and missing
            if rule.required and source_value is None:
                logger.warning(
                    f"Required field {rule.source_field} not found, "
                    f"using default: {rule.default_value}"
                )
            
            # Transform value if needed
            if source_value is not None and rule.transformation:
                source_value = self._apply_transformation(
                    source_value,
                    rule.transformation
                )
            
            # Cast to expected data type
            if source_value is not None:
                source_value = self._cast_to_type(
                    source_value,
                    rule.data_type
                )
            
            # Add to mapped fields using target field name
            mapped_fields[rule.target_field] = source_value
        
        return mapped_fields
    
    def _apply_transformation(self, value: Any, transformation: str) -> Any:
        """Apply value transformation."""
        if not isinstance(value, str):
            return value
        
        transformations = {
            "uppercase": lambda v: v.upper(),
            "lowercase": lambda v: v.lower(),
            "trim": lambda v: v.strip(),
            "title": lambda v: v.title(),
            "capitalize": lambda v: v.capitalize(),
        }
        
        transform_func = transformations.get(transformation)
        if transform_func:
            return transform_func(value)
        
        logger.warning(f"Unknown transformation: {transformation}")
        return value
    
    def _cast_to_type(self, value: Any, target_type: str) -> Any:
        """Cast value to target data type."""
        if value is None:
            return None
        
        try:
            if target_type == "string":
                return str(value)
            elif target_type == "number":
                if isinstance(value, (int, float)):
                    return value
                return float(value)
            elif target_type == "date":
                if isinstance(value, str):
                    # Try parsing ISO format
                    return datetime.fromisoformat(value)
                return value
            elif target_type == "boolean":
                if isinstance(value, bool):
                    return value
                return str(value).lower() in ("true", "yes", "1")
            elif target_type == "decimal":
                if isinstance(value, (int, float)):
                    return value
                return float(value)
        except Exception as e:
            logger.warning(f"Type cast failed for {value} to {target_type}: {e}")
        
        return value
    
    def export_to_json(
        self,
        documents: List[Dict[str, Any]],
        mapping_rules: Optional[List[FieldMappingRule]] = None,
        pretty_print: bool = True
    ) -> str:
        """
        Export documents as JSON.
        
        Args:
            documents: List of document dicts with extracted fields
            mapping_rules: Optional field mapping rules
            pretty_print: Whether to pretty print JSON
            
        Returns:
            JSON string
        """
        export_id = str(uuid4())
        
        # Apply mapping if provided
        if mapping_rules:
            formatted_docs = []
            for doc in documents:
                mapped_fields = self.apply_field_mapping(
                    doc.get("extracted_fields", {}),
                    mapping_rules
                )
                doc_copy = doc.copy()
                doc_copy["extracted_fields"] = mapped_fields
                formatted_docs.append(doc_copy)
        else:
            formatted_docs = documents
        
        # Prepare export payload
        export_data = {
            "export_id": export_id,
            "export_format": ExportFormat.JSON.value,
            "document_count": len(documents),
            "exported_at": datetime.utcnow().isoformat(),
            "documents": formatted_docs
        }
        
        # Serialize to JSON
        json_str = json.dumps(
            export_data,
            indent=2 if pretty_print else None,
            default=str  # Handle datetime and other non-serializable objects
        )
        
        logger.info(f"Exported {len(documents)} documents to JSON (export_id: {export_id})")
        return json_str
    
    def export_to_csv(
        self,
        documents: List[Dict[str, Any]],
        mapping_rules: Optional[List[FieldMappingRule]] = None,
        delimiter: str = ",",
        text_qualifier: str = '"',
        include_header: bool = True,
        encoding: str = "utf-8"
    ) -> str:
        """
        Export documents as CSV.
        
        Args:
            documents: List of document dicts
            mapping_rules: Optional field mapping rules
            delimiter: CSV delimiter
            text_qualifier: Text qualifier (quote char)
            include_header: Whether to include header row
            encoding: Output encoding
            
        Returns:
            CSV string
        """
        export_id = str(uuid4())
        
        if not documents:
            return ""
        
        # Prepare field names
        first_doc = documents[0].get("extracted_fields", {})
        
        if mapping_rules:
            field_names = [rule.target_field for rule in mapping_rules]
        else:
            field_names = list(first_doc.keys())
        
        # Build CSV
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=field_names,
            delimiter=delimiter,
            quotechar=text_qualifier,
            quoting=csv.QUOTE_MINIMAL
        )
        
        if include_header:
            writer.writeheader()
        
        # Write rows
        for doc in documents:
            fields = doc.get("extracted_fields", {})
            
            # Apply mapping if provided
            if mapping_rules:
                mapped_fields = self.apply_field_mapping(fields, mapping_rules)
            else:
                mapped_fields = fields
            
            # Ensure all field names are present
            row_data = {
                field_name: mapped_fields.get(field_name, "")
                for field_name in field_names
            }
            
            writer.writerow(row_data)
        
        csv_str = output.getvalue()
        logger.info(f"Exported {len(documents)} documents to CSV (export_id: {export_id})")
        
        return csv_str
    
    def export_to_jsonl(
        self,
        documents: List[Dict[str, Any]],
        mapping_rules: Optional[List[FieldMappingRule]] = None
    ) -> str:
        """
        Export documents as JSONL (JSON Lines).
        
        One JSON object per line, suitable for streaming.
        
        Args:
            documents: List of document dicts
            mapping_rules: Optional field mapping rules
            
        Returns:
            JSONL string
        """
        export_id = str(uuid4())
        lines = []
        
        for doc in documents:
            fields = doc.get("extracted_fields", {})
            
            # Apply mapping if provided
            if mapping_rules:
                mapped_fields = self.apply_field_mapping(fields, mapping_rules)
            else:
                mapped_fields = fields
            
            # Create line object
            line_obj = {
                "document_id": doc.get("id"),
                "document_type": doc.get("document_type"),
                "fields": mapped_fields,
                "exported_at": datetime.utcnow().isoformat()
            }
            
            lines.append(json.dumps(line_obj, default=str))
        
        jsonl_str = "\n".join(lines)
        logger.info(f"Exported {len(documents)} documents to JSONL (export_id: {export_id})")
        
        return jsonl_str
    
    def export_to_erp(
        self,
        documents: List[Dict[str, Any]],
        erp_system: ERPSystem,
        document_type: str,
        format_output: ExportFormat = ExportFormat.JSON
    ) -> str:
        """
        Export document to ERP system format.
        
        Applies ERP-specific field mapping and structure.
        
        Args:
            documents: List of document dicts
            erp_system: Target ERP system
            document_type: Document type in ERP
            format_output: Output format (json, csv, jsonl)
            
        Returns:
            Formatted string for ERP
        """
        # Get ERP mapping for this system and document type
        if not self.config or erp_system.value not in self.config.erp_mappings:
            raise ValueError(f"No ERP mapping configured for {erp_system.value}")
        
        system_mappings = self.config.erp_mappings[erp_system.value]
        if document_type not in system_mappings:
            raise ValueError(
                f"No mapping for document type '{document_type}' in {erp_system.value}"
            )
        
        erp_mapping = system_mappings[document_type]
        
        # Format documents for ERP
        erp_docs = []
        for doc in documents:
            fields = doc.get("extracted_fields", {})
            
            # Apply ERP field mapping
            mapped_fields = self.apply_field_mapping(
                fields,
                erp_mapping.field_mappings
            )
            
            # Structure for ERP (header + line items if applicable)
            erp_doc = {
                "document_type": erp_mapping.document_type,
                "header": self._extract_header_fields(
                    mapped_fields,
                    erp_mapping.header_fields
                ),
                "fields": mapped_fields
            }
            
            # Add line items if configured
            if erp_mapping.line_item_fields:
                erp_doc["line_items"] = self._extract_line_items(
                    mapped_fields,
                    erp_mapping.line_item_fields,
                    erp_mapping.line_item_prefix
                )
            
            erp_docs.append(erp_doc)
        
        # Export in requested format
        if format_output == ExportFormat.JSON:
            return self._format_erp_json(erp_docs, pretty_print=True)
        elif format_output == ExportFormat.CSV:
            return self._format_erp_csv(erp_docs)
        elif format_output == ExportFormat.JSONL:
            return self._format_erp_jsonl(erp_docs)
        else:
            raise ValueError(f"Unsupported format: {format_output}")
    
    def _extract_header_fields(
        self,
        fields: Dict[str, Any],
        header_field_names: List[str]
    ) -> Dict[str, Any]:
        """Extract header fields from mapped fields."""
        return {
            field_name: fields.get(field_name)
            for field_name in header_field_names
            if field_name in fields
        }
    
    def _extract_line_items(
        self,
        fields: Dict[str, Any],
        line_item_fields: List[str],
        prefix: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Extract line item fields from mapped fields."""
        line_items = []
        
        # Find fields with line item prefix
        if prefix:
            item_number = 1
            while True:
                line_item = {}
                found_any = False
                
                for field_name in line_item_fields:
                    prefixed_name = f"{prefix}{item_number}_{field_name}"
                    if prefixed_name in fields:
                        line_item[field_name] = fields[prefixed_name]
                        found_any = True
                
                if not found_any:
                    break
                
                line_items.append(line_item)
                item_number += 1
        
        return line_items
    
    def _format_erp_json(
        self,
        erp_docs: List[Dict[str, Any]],
        pretty_print: bool = True
    ) -> str:
        """Format ERP documents as JSON."""
        return json.dumps(
            erp_docs,
            indent=2 if pretty_print else None,
            default=str
        )
    
    def _format_erp_csv(self, erp_docs: List[Dict[str, Any]]) -> str:
        """Format ERP documents as CSV."""
        # Flatten ERP structure to CSV
        if not erp_docs:
            return ""
        
        flattened = []
        for erp_doc in erp_docs:
            row = erp_doc.get("header", {})
            row.update(erp_doc.get("fields", {}))
            flattened.append(row)
        
        if not flattened:
            return ""
        
        output = io.StringIO()
        field_names = list(flattened[0].keys())
        writer = csv.DictWriter(output, fieldnames=field_names)
        writer.writeheader()
        writer.writerows(flattened)
        
        return output.getvalue()
    
    def _format_erp_jsonl(self, erp_docs: List[Dict[str, Any]]) -> str:
        """Format ERP documents as JSONL."""
        lines = [json.dumps(doc, default=str) for doc in erp_docs]
        return "\n".join(lines)
    
    def validate_export(
        self,
        documents: List[Dict[str, Any]],
        mapping_rules: List[FieldMappingRule]
    ) -> ExportValidationResult:
        """
        Validate documents for export.
        
        Checks required fields and data types.
        
        Args:
            documents: Documents to validate
            mapping_rules: Mapping rules to validate against
            
        Returns:
            Validation result
        """
        errors = []
        warnings = []
        missing_fields = []
        total_fields = 0
        exported_fields = 0
        
        for doc in documents:
            fields = doc.get("extracted_fields", {})
            
            for rule in mapping_rules:
                total_fields += 1
                
                # Check if field exists
                if rule.source_field not in fields:
                    if rule.required:
                        errors.append(
                            f"Required field '{rule.source_field}' "
                            f"not found in document {doc.get('id')}"
                        )
                        missing_fields.append(rule.source_field)
                    elif rule.default_value is None:
                        warnings.append(
                            f"Field '{rule.source_field}' "
                            f"not found in document {doc.get('id')}"
                        )
                else:
                    exported_fields += 1
                    
                    # Validate data type
                    value = fields[rule.source_field]
                    try:
                        self._cast_to_type(value, rule.data_type)
                    except Exception as e:
                        warnings.append(
                            f"Type conversion issue for '{rule.source_field}' "
                            f"in document {doc.get('id')}: {e}"
                        )
        
        is_valid = len(errors) == 0
        
        return ExportValidationResult(
            is_valid=is_valid,
            error_messages=errors,
            warning_messages=warnings,
            required_fields_missing=missing_fields,
            field_count_exported=exported_fields,
            field_count_total=total_fields
        )
    
    def get_mapping_by_name(self, mapping_name: str) -> Optional[List[FieldMappingRule]]:
        """Get field mapping rules by name."""
        if not self.config:
            return None
        
        # Check global mappings
        for rule in self.config.global_field_mappings:
            if rule.source_field == mapping_name:
                return self.config.global_field_mappings
        
        # Add support for named mappings if needed
        return None
    
    def list_erp_mappings(self) -> Dict[str, List[str]]:
        """List all available ERP mappings."""
        result = {}
        if self.config:
            for system, mappings in self.config.erp_mappings.items():
                result[system] = list(mappings.keys())
        return result
