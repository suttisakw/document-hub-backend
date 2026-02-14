"""
Output Formatter API Router

Endpoints for exporting documents in various formats:
- JSON export
- CSV export
- JSONL (JSON Lines) export
- ERP system mapping export
"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
import logging

from app.schemas.output_formatter import (
    JSONExportRequest,
    CSVExportRequest,
    ERPExportRequest,
    ExportResponse,
    ExportFormat,
    ERPSystem,
    BatchExportRequest,
    BatchExportResponse,
    ExportStatistics,
)
from app.services.output_formatter_service import OutputFormatterService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/documents/export",
    tags=["export"],
    responses={
        404: {"description": "Document not found"},
        422: {"description": "Invalid request"},
    },
)

# Initialize service
formatter_service = OutputFormatterService()


@router.get("/info")
async def get_export_info() -> dict:
    """
    Get information about available export options.
    
    Returns:
    - Supported formats: JSON, CSV, JSONL
    - Available ERP systems: SAP, Oracle, NetSuite, Custom
    - Example field mapping structure
    """
    return {
        "supported_formats": [fmt.value for fmt in ExportFormat],
        "supported_erp_systems": [sys.value for sys in ERPSystem],
        "erp_mappings_available": formatter_service.list_erp_mappings(),
        "features": {
            "field_mapping": True,
            "batch_export": True,
            "validation": True,
            "erp_integration": True,
        },
        "max_batch_size": 100,
        "max_documents_per_export": 1000,
    }


@router.post("/json")
async def export_to_json(request: JSONExportRequest) -> ExportResponse:
    """
    Export document as JSON.
    
    With optional field mapping to customize output field names.
    
    Example:
    ```json
    {
        "document_id": "doc123",
        "include_metadata": true,
        "include_corrections": true,
        "pretty_print": true,
        "field_mapping": None
    }
    ```
    
    Response includes:
    - export_id: Unique export identifier
    - file_size: Size of exported JSON
    - download_url: URL to download file
    """
    try:
        # Placeholder: In real implementation, fetch document from DB
        # doc = get_document(request.document_id)
        # if not doc:
        #     raise HTTPException(status_code=404, detail="Document not found")
        
        # Mock document for demonstration
        doc = {
            "id": request.document_id,
            "document_type": "invoice",
            "extracted_fields": {
                "invoice_number": "INV-2026-001",
                "invoice_date": "2026-02-13",
                "total_amount": "1500.00",
                "vendor_name": "Acme Corp",
            }
        }
        
        # Apply field mapping if specified
        mapping_rules = None
        if request.field_mapping:
            mapping_rules = formatter_service.get_mapping_by_name(request.field_mapping)
        
        # Export to JSON
        json_string = formatter_service.export_to_json(
            [doc],
            mapping_rules=mapping_rules,
            pretty_print=request.pretty_print
        )
        
        return ExportResponse(
            export_id="exp_" + request.document_id,
            export_format=ExportFormat.JSON,
            document_count=1,
            field_count=len(doc.get("extracted_fields", {})),
            exported_rows=1,
            conversion_status="success",
            error_count=0,
            file_size=len(json_string.encode('utf-8')),
            download_url=f"/api/v1/documents/export/download/exp_{request.document_id}",
        )
    except Exception as e:
        logger.error(f"JSON export failed: {e}")
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/csv")
async def export_to_csv(request: CSVExportRequest) -> ExportResponse:
    """
    Export documents as CSV.
    
    Supports batch export of multiple documents to single CSV file.
    
    Example:
    ```json
    {
        "document_ids": ["doc1", "doc2"],
        "include_header": true,
        "include_metadata": false,
        "field_delimiter": ",",
        "text_qualifier": "\"",
        "encoding": "utf-8",
        "field_mapping": None
    }
    ```
    
    Features:
    - Configurable delimiter (comma, semicolon, tab, etc.)
    - Text qualifier for fields with special characters
    - Optional metadata columns
    - UTF-8 or other encodings
    """
    try:
        # Placeholder: In real implementation, fetch documents from DB
        docs = []
        for doc_id in request.document_ids:
            docs.append({
                "id": doc_id,
                "document_type": "invoice",
                "extracted_fields": {
                    "invoice_number": f"INV-{doc_id}",
                    "invoice_date": "2026-02-13",
                    "total_amount": "1500.00",
                }
            })
        
        if not docs:
            raise HTTPException(status_code=404, detail="No documents found")
        
        # Get mapping rules if specified
        mapping_rules = None
        if request.field_mapping:
            mapping_rules = formatter_service.get_mapping_by_name(request.field_mapping)
        
        # Export to CSV
        csv_string = formatter_service.export_to_csv(
            docs,
            mapping_rules=mapping_rules,
            delimiter=request.field_delimiter,
            text_qualifier=request.text_qualifier,
            include_header=request.include_header,
            encoding=request.encoding
        )
        
        return ExportResponse(
            export_id="exp_csv_" + "_".join(request.document_ids[:3]),
            export_format=ExportFormat.CSV,
            document_count=len(docs),
            field_count=len(docs[0].get("extracted_fields", {})) if docs else 0,
            exported_rows=len(docs),
            conversion_status="success",
            error_count=0,
            file_size=len(csv_string.encode(request.encoding)),
            download_url=f"/api/v1/documents/export/download/exp_csv",
        )
    except Exception as e:
        logger.error(f"CSV export failed: {e}")
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/jsonl")
async def export_to_jsonl(
    document_ids: List[str] = Query(..., description="Document IDs to export"),
    field_mapping: Optional[str] = Query(None, description="Field mapping to apply")
) -> ExportResponse:
    """
    Export documents as JSONL (JSON Lines).
    
    One JSON object per line. Ideal for streaming large datasets
    or piping to downstream systems.
    
    Example:
    ```
    curl -X POST "http://localhost:8000/api/v1/documents/export/jsonl?document_ids=doc1&document_ids=doc2"
    ```
    
    Output format:
    ```
    {"document_id": "doc1", "fields": {...}, "exported_at": "..."}
    {"document_id": "doc2", "fields": {...}, "exported_at": "..."}
    ```
    """
    try:
        # Placeholder: Fetch documents
        docs = []
        for doc_id in document_ids:
            docs.append({
                "id": doc_id,
                "document_type": "invoice",
                "extracted_fields": {
                    "invoice_number": f"INV-{doc_id}",
                    "total_amount": "1500.00",
                }
            })
        
        if not docs:
            raise HTTPException(status_code=404, detail="No documents found")
        
        # Get mapping rules if specified
        mapping_rules = None
        if field_mapping:
            mapping_rules = formatter_service.get_mapping_by_name(field_mapping)
        
        # Export to JSONL
        jsonl_string = formatter_service.export_to_jsonl(docs, mapping_rules=mapping_rules)
        
        return ExportResponse(
            export_id="exp_jsonl_" + "_".join(document_ids[:3]),
            export_format=ExportFormat.JSONL,
            document_count=len(docs),
            field_count=len(docs[0].get("extracted_fields", {})) if docs else 0,
            exported_rows=len(docs),
            conversion_status="success",
            error_count=0,
            file_size=len(jsonl_string.encode('utf-8')),
            download_url=f"/api/v1/documents/export/download/exp_jsonl",
        )
    except Exception as e:
        logger.error(f"JSONL export failed: {e}")
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/erp")
async def export_to_erp(request: ERPExportRequest) -> ExportResponse:
    """
    Export documents in ERP system format.
    
    Applies ERP-specific field mapping and structure.
    
    Supports:
    - SAP: Maps to SAP DocumentHeader/TaxIndicator format
    - Oracle: Maps to Oracle Receivables format
    - NetSuite: Maps to NetSuite transaction format
    - Custom: User-defined ERP mapping
    
    Example:
    ```json
    {
        "document_ids": ["doc1", "doc2"],
        "erp_system": "sap",
        "document_type": "invoice",
        "include_validation": true,
        "create_audit_log": true
    }
    ```
    
    Features:
    - Automatic field name mapping (invoice_number → doc_no)
    - Data type conversion
    - Header and line item structure
    - Validation against ERP requirements
    - Audit logging for compliance
    """
    try:
        # Placeholder: Fetch documents
        docs = []
        for doc_id in request.document_ids:
            docs.append({
                "id": doc_id,
                "document_type": request.document_type,
                "extracted_fields": {
                    "invoice_number": f"INV-{doc_id}",
                    "invoice_date": "2026-02-13",
                    "total_amount": "1500.00",
                    "vendor_code": "VENDOR123",
                    "line_item_1_description": "Item 1",
                    "line_item_1_amount": "500.00",
                    "line_item_2_description": "Item 2",
                    "line_item_2_amount": "1000.00",
                }
            })
        
        if not docs:
            raise HTTPException(status_code=404, detail="No documents found")
        
        # Validate if requested
        if request.include_validation:
            # Validation logic would go here
            logger.info(f"Validating {len(docs)} documents for {request.erp_system.value} export")
        
        # Export to ERP format
        erp_format = ExportFormat.JSON  # Could be configurable per ERP
        erp_string = formatter_service.export_to_erp(
            docs,
            request.erp_system,
            request.document_type,
            format_output=erp_format
        )
        
        # Create audit log if requested
        if request.create_audit_log:
            logger.info(
                f"ERP export to {request.erp_system.value}: "
                f"{len(docs)} documents, type={request.document_type}"
            )
        
        return ExportResponse(
            export_id=f"exp_erp_{request.erp_system.value}",
            export_format=erp_format,
            document_count=len(docs),
            field_count=len(docs[0].get("extracted_fields", {})) if docs else 0,
            exported_rows=len(docs),
            conversion_status="success",
            error_count=0,
            file_size=len(erp_string.encode('utf-8')),
            download_url=f"/api/v1/documents/export/download/exp_erp",
        )
    except ValueError as e:
        logger.error(f"ERP mapping not found: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"ERP export failed: {e}")
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/batch")
async def batch_export(request: BatchExportRequest) -> BatchExportResponse:
    """
    Export multiple documents in multiple formats at once.
    
    Processes all requested formats asynchronously if async_mode=true.
    
    Example:
    ```json
    {
        "document_ids": ["doc1", "doc2", "doc3"],
        "formats": ["json", "csv"],
        "erp_systems": ["sap", "oracle"],
        "async_mode": true
    }
    ```
    
    Returns:
    - batch_id: Identifier for tracking batch progress
    - status: Current processing status
    - estimated_completion: When batch will be ready
    """
    try:
        batch_id = f"batch_{datetime.utcnow().timestamp()}"
        status = "queued" if request.async_mode else "processing"
        
        logger.info(
            f"Batch export created: batch_id={batch_id}, "
            f"documents={len(request.document_ids)}, "
            f"formats={request.formats}, "
            f"erp_systems={request.erp_systems}"
        )
        
        # In real implementation, queue async tasks here
        # celery.send_task('batch_export', args=(batch_id, request.dict()))
        
        return BatchExportResponse(
            batch_id=batch_id,
            document_count=len(request.document_ids),
            formats_requested=request.formats,
            erp_systems_requested=request.erp_systems,
            status=status,
            estimated_completion=datetime.utcnow() if not request.async_mode else None,
        )
    except Exception as e:
        logger.error(f"Batch export failed: {e}")
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/statistics")
async def get_export_statistics(
    days: int = Query(7, ge=1, le=365, description="Number of days to summarize")
) -> ExportStatistics:
    """
    Get statistics about exports in specified time period.
    
    Returns:
    - Total exports and documents exported
    - Breakdown by format (JSON, CSV, JSONL)
    - Breakdown by ERP system (SAP, Oracle, etc.)
    - Average file size
    - Most commonly used field mapping
    """
    # Placeholder: In real implementation, query database for statistics
    return ExportStatistics(
        total_exports=42,
        total_documents_exported=156,
        exports_by_format={
            "json": 15,
            "csv": 20,
            "jsonl": 7,
        },
        exports_by_erp={
            "sap": 10,
            "oracle": 8,
            "custom": 5,
        },
        average_export_size=45600.0,
        most_common_mapping="default_invoice_mapping",
    )


@router.post("/config/reload")
async def reload_config() -> dict:
    """
    Reload output formatter configuration from file.
    
    Useful for updating field mappings and ERP configurations
    without restarting the service.
    
    Returns:
    - status: "success" or "failed"
    - message: Explanation
    - config_version: Loaded config version
    """
    try:
        formatter_service.reload_config()
        logger.info("Output formatter config reloaded successfully")
        return {
            "status": "success",
            "message": "Configuration reloaded",
            "config_version": formatter_service.config.config_version if formatter_service.config else None,
        }
    except Exception as e:
        logger.error(f"Failed to reload config: {e}")
        raise HTTPException(status_code=422, detail=str(e))
