"""
Output Formatter Schemas

Supports:
- JSON export
- CSV export
- ERP system mapping with configurable field mapping

Example mapping:
  invoice_number → doc_no
  invoice_date → date
  total_amount → grand_total
"""

from typing import Any, Dict, List, Optional, Literal
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class ExportFormat(str, Enum):
    """Supported export formats."""
    JSON = "json"
    CSV = "csv"
    JSONL = "jsonl"  # JSON Lines for streaming


class ERPSystem(str, Enum):
    """Supported ERP systems."""
    SAP = "sap"
    ORACLE = "oracle"
    NETSUISSE = "netsuisse"
    CUSTOM = "custom"


class FieldMappingRule(BaseModel):
    """
    Field mapping rule for format conversion.
    
    Maps source field name to target field name and optionally transforms the value.
    
    Example:
        source_field: "invoice_number"
        target_field: "doc_no"
        data_type: "string"
        required: true
        transformation: None
    """
    source_field: str = Field(
        ..., description="Source field name from extracted_fields"
    )
    target_field: str = Field(
        ..., description="Target field name in output"
    )
    data_type: Literal["string", "number", "date", "boolean", "decimal"] = Field(
        default="string", description="Expected data type"
    )
    required: bool = Field(
        default=False, description="Whether field is required in output"
    )
    default_value: Optional[Any] = Field(
        default=None, description="Default value if source field not found"
    )
    transformation: Optional[str] = Field(
        default=None, 
        description="Optional transformation function name (e.g., 'uppercase', 'lowercase', 'trim')"
    )


class ERPMapping(BaseModel):
    """
    ERP system specific mapping configuration.
    
    Defines how document fields map to ERP system fields.
    
    Example:
        erp_system: "sap"
        document_type: "invoice"
        field_mappings: [
            FieldMappingRule(...)
        ]
        header_fields: ["company_code", "document_type"]
        line_item_prefix: "ITEM_"
    """
    erp_system: ERPSystem = Field(..., description="Target ERP system")
    document_type: str = Field(..., description="Document type in ERP (e.g., 'invoice', 'po')")
    field_mappings: List[FieldMappingRule] = Field(
        ..., description="Field mapping rules"
    )
    header_fields: List[str] = Field(
        default_factory=list,
        description="Fields that go to header section (ERP specific)"
    )
    line_item_fields: Optional[List[str]] = Field(
        default=None,
        description="Fields for line items (if applicable)"
    )
    line_item_prefix: Optional[str] = Field(
        default=None,
        description="Prefix for line item fields in output"
    )
    date_format: str = Field(
        default="YYYY-MM-DD",
        description="Date format for ERP system"
    )
    decimal_precision: int = Field(
        default=2,
        description="Decimal precision for amounts"
    )
    encoding: str = Field(
        default="utf-8",
        description="Character encoding for export"
    )


class OutputFormatConfig(BaseModel):
    """
    Complete output formatter configuration.
    
    Loads from config file and provides all mapping rules.
    """
    config_version: str = Field(default="1.0", description="Config version")
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # JSON export configuration
    json_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON export specific settings"
    )
    
    # CSV export configuration
    csv_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="CSV export specific settings"
    )
    
    # ERP mappings per system
    erp_mappings: Dict[str, Dict[str, ERPMapping]] = Field(
        default_factory=dict,
        description="ERP mappings by system and document type"
    )
    
    # Global field mappings (applies to all exports)
    global_field_mappings: List[FieldMappingRule] = Field(
        default_factory=list,
        description="Field mappings applied to all exports"
    )


class ExportFieldValue(BaseModel):
    """
    Single field value in export.
    
    Includes original and mapped field names.
    """
    source_field: str
    target_field: str
    value: Any
    data_type: str
    is_corrected: bool = False
    correction_version: Optional[int] = None


class ExportDataRow(BaseModel):
    """
    Single row of export data.
    
    Contains fields mapped according to export configuration.
    """
    export_id: str = Field(..., description="Unique export identifier")
    document_id: str
    document_type: str
    export_format: ExportFormat
    fields: Dict[str, Any] = Field(..., description="Field name -> value mapping")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (timestamps, user, etc.)"
    )


class JSONExportRequest(BaseModel):
    """Request to export document as JSON."""
    document_id: str
    include_metadata: bool = Field(default=True)
    include_corrections: bool = Field(default=True)
    pretty_print: bool = Field(default=True)
    field_mapping: Optional[str] = Field(default=None, description="Field mapping name to apply")


class CSVExportRequest(BaseModel):
    """Request to export documents as CSV."""
    document_ids: List[str] = Field(..., description="Document IDs to export")
    include_header: bool = Field(default=True)
    include_metadata: bool = Field(default=False)
    field_delimiter: str = Field(default=",")
    text_qualifier: str = Field(default='"')
    encoding: str = Field(default="utf-8")
    field_mapping: Optional[str] = Field(default=None, description="Field mapping name to apply")


class ERPExportRequest(BaseModel):
    """Request to export documents in ERP format."""
    document_ids: List[str] = Field(..., description="Document IDs to export")
    erp_system: ERPSystem = Field(..., description="Target ERP system")
    document_type: str = Field(..., description="Document type in ERP")
    include_validation: bool = Field(default=True)
    create_audit_log: bool = Field(default=True)


class ExportResponse(BaseModel):
    """Response from export operation."""
    export_id: str
    export_format: ExportFormat
    document_count: int
    field_count: int
    exported_rows: int
    conversion_status: Literal["success", "partial", "failed"]
    error_count: int = 0
    warning_count: int = 0
    file_size: Optional[int] = None
    file_path: Optional[str] = None
    download_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    details: List[Dict[str, Any]] = Field(default_factory=list)


class ExportValidationResult(BaseModel):
    """Validation result for export."""
    is_valid: bool
    error_messages: List[str] = Field(default_factory=list)
    warning_messages: List[str] = Field(default_factory=list)
    required_fields_missing: List[str] = Field(default_factory=list)
    field_count_exported: int = 0
    field_count_total: int = 0
    validation_timestamp: datetime = Field(default_factory=datetime.utcnow)


class ERPValidationRule(BaseModel):
    """Validation rule for ERP export."""
    field_name: str
    rule_type: Literal["required", "format", "length", "range", "custom"]
    rule_value: Any
    error_message: str


class MappingTemplate(BaseModel):
    """Template for field mapping."""
    name: str = Field(..., description="Unique name for this mapping")
    description: Optional[str] = None
    export_format: ExportFormat
    field_mappings: List[FieldMappingRule]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None


class ExportHistory(BaseModel):
    """History entry for document export."""
    export_id: str
    document_id: str
    export_format: ExportFormat
    exported_by: str
    export_timestamp: datetime
    record_count: int
    file_path: Optional[str] = None
    status: Literal["success", "failed", "archived"]
    notes: Optional[str] = None


class BatchExportRequest(BaseModel):
    """Request to batch export multiple documents."""
    document_ids: List[str]
    formats: List[ExportFormat] = Field(
        default_factory=lambda: [ExportFormat.JSON, ExportFormat.CSV],
        description="Export formats to generate"
    )
    erp_systems: List[ERPSystem] = Field(
        default_factory=list,
        description="ERP systems to export to"
    )
    async_mode: bool = Field(
        default=True,
        description="Whether to process asynchronously"
    )


class BatchExportResponse(BaseModel):
    """Response from batch export request."""
    batch_id: str
    document_count: int
    formats_requested: List[ExportFormat]
    erp_systems_requested: List[ERPSystem]
    status: Literal["queued", "processing", "completed", "failed"]
    estimated_completion: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ExportStatistics(BaseModel):
    """Statistics about exports."""
    total_exports: int
    total_documents_exported: int
    exports_by_format: Dict[ExportFormat, int]
    exports_by_erp: Dict[str, int]
    average_export_size: float
    most_common_mapping: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
