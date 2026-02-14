"""
Document Correction System - Complete Reference Guide

This module provides document correction capabilities:
1. Manual field correction with history tracking
2. Denormalized correction data for analytics
3. Training data export for ML model improvement
4. Override mechanism (corrected values supersede extractions)
5. Audit trail and compliance support

Architecture Overview
====================

The correction system extends the existing document extraction pipeline with
four new components:

1. **Correction Data Models** (document_correction.py)
   - FieldCorrection: Single correction event with metadata
   - CorrectionHistory: Complete history per field with override logic
   - CorrectionFeedback: Standalone feedback for training
   - FieldValue: Field with correction support and override logic

2. **Database Models** (correction_models.py)
   - FieldCorrectionRecord: Stores individual corrections
   - DocumentCorrectionAudit: Tracks correction sessions
   - CorrectionSnapshot: Backup of document state
   - CorrectionTrainingDataRecord: Pre-processed training records

3. **API Layer** (correction_api.py)
   - Request schemas: SubmitCorrectionRequest, BatchCorrectionRequest
   - Response schemas: CorrectionResponse, CorrectionHistoryResponse
   - Filter schemas: CorrectionFilterRequest, CorrectionAnalyticsRequest
   - Export schemas: TrainingDataExportResponse

4. **Service Layer** (correction_service.py)
   - CorrectionService: Business logic for corrections
   - apply_correction(): Apply single correction
   - apply_batch_corrections(): Batch operation
   - get_field_correction_history(): Retrieve history
   - export_training_data(): Create training dataset
   - get_correction_statistics(): Analytics

5. **REST API** (corrections.py)
   - POST /documents/{id}/corrections: Submit correction
   - POST /documents/{id}/corrections/batch: Batch submit
   - GET /documents/{id}/corrections/{field_name}: Get history
   - GET /documents/{id}/corrections/summary: Get summary
   - POST /documents/corrections/export/training-data: Export training
   - GET /documents/corrections/statistics: Analytics


Core Concepts
=============

Override Mechanism
------------------
When a field is corrected:
1. Original extracted value is PRESERVED in database
2. Corrected value OVERRIDES in:
   - API responses
   - Document storage
   - Downstream processing
3. Both values available for:
   - Audit trail
   - Training data
   - Compliance reporting

This allows:
- Transparent corrections (always documentable)
- Training on extraction errors
- Impact analysis (what changed and why)

Correction Types
----------------
1. VALUE_CHANGE: Value itself was modified
2. VALUE_CLEARED: Value was removed (set to null)
3. VALUE_ADDED: Missing value was filled
4. CONFIDENCE_ADJUSTED: Confidence score adjusted
5. TYPE_CHANGED: Field data type was corrected
6. FORMAT_CORRECTED: Format/normalization issue fixed

Correction Reasons
------------------
Used for categorizing errors:
- extraction_error: Wrong field extracted
- ocr_error: OCR misread text
- wrong_field: Value from wrong location
- typo: User typo during manual entry
- ambiguous: Value was ambiguous
- missing: Field was missing
- format_error: Format incorrect
- incomplete: Value truncated
- validation_failure: Failed validation
- confidence_low: Low confidence extraction
- other: Unclassified

These reasons enable:
- Error analytics (identify systematic issues)
- Model improvement (focus on common errors)
- Performance metrics (accuracy tracking)
- User feedback (sentiment-based learning)


Database Schema Extensions
==========================

1. field_corrections table
   - Stores individual corrections
   - Links to extracted_field via foreign key
   - Includes metadata: who, when, why, sentiment
   - Supports audit trail queries

2. document_correction_audits table
   - Tracks correction sessions
   - Summarizes corrections per document
   - Records session timing and notes
   - Enables workflow tracking

3. correction_snapshots table (optional)
   - Full document state before/after
   - Useful for rollback/recovery
   - Retention policy for storage

4. correction_training_data table
   - Denormalized training records
   - Optimized for ML pipeline consumption
   - Includes full context (document, field, extraction)
   - Export version tracking

Extension to existing tables:
- ExtractedField: Add is_corrected boolean, version number
- Document: Add has_corrections boolean, correction_status
- User: Add relationships to corrections_made, correction_audits


API Usage Examples
==================

1. Single Correction
-------------------
POST /documents/123/corrections
Content-Type: application/json

{
  "field_name": "invoice_number",
  "corrected_value": "INV-2024-001",
  "correction_reason": "format_error",
  "reason_details": "OCR output numeric only, added standard format",
  "feedback_sentiment": "good",
  "feedback_comment": "OCR misread hyphens as spaces",
  "is_critical": false,
  "confidence_adjustment": -0.1
}

Response:
{
  "correction_id": "550e8400-e29b-41d4-a716-446655440000",
  "field_name": "invoice_number",
  "original_value": "NV2024001",
  "corrected_value": "INV-2024-001",
  "corrected_at": "2024-01-15T10:30:00Z",
  "corrected_by": "user@example.com",
  "correction_reason": "format_error",
  "is_applied": true,
  "confidence_adjustment": -0.1,
  "feedback_sentiment": "good"
}

2. Batch Corrections
-------------------
POST /documents/123/corrections/batch
Content-Type: application/json

{
  "corrections": [
    {
      "field_name": "invoice_number",
      "corrected_value": "INV-2024-001",
      "correction_reason": "format_error"
    },
    {
      "field_name": "total_amount",
      "corrected_value": 1500.50,
      "correction_reason": "extraction_error",
      "feedback_sentiment": "good",
      "feedback_comment": "Currency parsing failed"
    },
    {
      "field_name": "invoice_date",
      "corrected_value": "2024-01-15",
      "correction_reason": "ocr_error",
      "is_critical": true
    }
  ],
  "session_notes": "Manual review of invoice OCR results",
  "verify_corrections": true
}

Response:
{
  "total_submissions": 3,
  "successful": 3,
  "failed": 0,
  "results": [...],
  "total_corrections_applied": 3,
  "session_duration_seconds": 45.2
}

3. Get Correction History
-----------------------
GET /documents/123/corrections/invoice_number

Response:
{
  "field_name": "invoice_number",
  "original_extraction": "NV2024001",
  "original_confidence": 0.95,
  "original_source": "ocr",
  "current_value": "INV-2024-001",
  "is_corrected": true,
  "correction_count": 1,
  "correction_severity": "medium",
  "corrections": [
    {
      "correction_id": "550e8400-...",
      "field_name": "invoice_number",
      "original_value": "NV2024001",
      "corrected_value": "INV-2024-001",
      "corrected_at": "2024-01-15T10:30:00Z",
      "corrected_by": "alice@example.com",
      "correction_reason": "format_error",
      "reason_details": "OCR output numeric only",
      "is_applied": true
    }
  ]
}

4. Document Correction Summary
------------------------------
GET /documents/123/corrections/summary

Response:
{
  "document_id": "550e8400-...",
  "total_fields": 25,
  "total_corrected_fields": 3,
  "total_corrections": 4,
  "correction_rate": 12.0,
  "has_critical": true,
  "critical_count": 1,
  "feedback_provided_count": 3,
  "corrections_by_reason": {
    "ocr_error": 2,
    "format_error": 1,
    "extraction_error": 1
  },
  "corrections_by_type": {
    "value_change": 3,
    "format_corrected": 1
  },
  "first_correction_at": "2024-01-15T10:00:00Z",
  "last_correction_at": "2024-01-15T11:30:00Z",
  "requires_review": false,
  "feedback_distribution": {
    "good": 3
  }
}

5. Export Training Data
-----------------------
POST /documents/corrections/export/training-data
Content-Type: application/json

{
  "document_ids": ["550e8400-...", "..."],
  "date_range": {
    "start": "2024-01-01T00:00:00Z",
    "end": "2024-01-31T23:59:59Z"
  },
  "correction_reasons": ["ocr_error", "extraction_error"],
  "min_feedback_sentiment": "good",
  "include_metadata": true,
  "format": "jsonl"
}

Response:
{
  "export_id": "550e8400-e29b-41d4-a716-446655440000",
  "record_count": 1250,
  "file_url": "https://api.example.com/exports/training-data/550e8400.jsonl",
  "file_format": "jsonl",
  "file_size_bytes": 2500000,
  "created_at": "2024-01-15T10:30:00Z",
  "expires_at": "2024-01-22T10:30:00Z",
  "documents_included": 150,
  "correction_types_included": ["value_change", "format_corrected"],
  "feedback_records": 450
}

6. Get Statistics
-----------------
GET /documents/corrections/statistics?days=30

Response:
{
  "period": "last_30_days",
  "total_corrections": 1250,
  "total_corrected_fields": 850,
  "unique_documents": 200,
  "unique_users": 15,
  "corrections_by_reason": {
    "ocr_error": 450,
    "extraction_error": 350,
    "format_error": 250,
    "other": 200
  },
  "corrections_by_user": {
    "alice@example.com": 400,
    "bob@example.com": 350,
    ...
  },
  "avg_corrections_per_document": 6.25,
  "feedback_coverage": 0.68,
  "feedback_sentiment_distribution": {
    "excellent": 200,
    "good": 600,
    "poor": 350,
    "unusable": 100
  },
  "daily_corrections": {
    "2024-01-01": 35,
    "2024-01-02": 42,
    ...
  }
}


Integration with Document Extraction
=====================================

The correction system integrates with document extraction at three points:

1. **value** property (automatic override)
   ```python
   # Get corrected value (if available) or extracted
   field_value.value  # Returns corrected if is_corrected=True

   # Get source
   field_value.source  # "corrected" or "extracted"

   # Check if corrected
   field_value.is_correction_applied  # boolean
   ```

2. **API Responses**
   ```python
   # When returning field values in API, use:
   field_value.to_dict()  # Returns effective value

   # Include audit trail for compliance:
   field_value.to_dict(include_history=True)
   ```

3. **Document Serialization**
   ```python
   document = DocumentWithCorrections(
       fields=[field_value],
       correction_summary=summary
   )

   # Get effective values (with corrections applied)
   document.get_corrected_fields  # Dict[field_name, value]

   # Get extracted values only
   document.get_extracted_only    # Dict[field_name, value]

   # Get audit trail
   document.get_audit_trail       # Dict[field_name, List[corrections]]
   ```


Training Data Support
=====================

The correction system is designed for continuous ML improvement:

1. **Data Collection**
   - Every correction is a training example
   - Original extraction + correction = ground truth
   - User feedback (sentiment + comment) = annotation

2. **Data Preparation**
   - Corrections denormalized in correction_training_data table
   - Full context (document, field, bbox, etc.) included
   - Export in multiple formats (JSONL, CSV, Parquet)

3. **Training Pipeline Integration**
   ```bash
   # Export corrections as training data
   POST /documents/corrections/export/training-data

   # Use in fine-tuning pipeline:
   curl https://api.example.com/exports/training-data/550e8400.jsonl | \
     python train_ocr_improver.py

   # Track export version in correction_training_data.export_version
   ```

4. **Feedback Loop**
   - Corrections with feedback_sentiment marked for training
   - Analytics track feedback_coverage metric
   - Target: >70% of corrections have training feedback

5. **Error Analysis**
   - Group corrections by reason (ocr_error, extraction_error, etc.)
   - Identify systematic issues
   - Prioritize model improvements

Example training record:
```json
{
  "document_id": "550e8400-...",
  "document_type": "invoice",
  "page_number": 1,
  "field_name": "invoice_number",
  "extraction_method": "ocr",
  "extracted_value": "NV2024001",
  "extraction_confidence": 0.95,
  "corrected_value": "INV-2024-001",
  "correction_reason": "format_error",
  "was_correct": false,
  "feedback_sentiment": "good",
  "feedback_comment": "OCR output numeric only, format standardization needed",
  "document_characteristics": {
    "language": "en",
    "layout": "structured",
    "image_quality": "high"
  },
  "field_characteristics": {
    "bbox": [100, 50, 300, 80],
    "font_size": 12,
    "font_style": "regular"
  }
}
```


Backward Compatibility
======================

The correction system maintains backward compatibility:

1. **No Breaking Changes**
   - All existing API endpoints unchanged
   - Existing schemas extended (not modified)
   - Optional correction fields (can ignore if not used)

2. **Gradual Adoption**
   - Add corrections as needed per document type
   - No requirement to adopt for all documents
   - Mix corrected and non-corrected fields

3. **Migration Path**
   - Existing documents unaffected
   - Add ExtractedField.is_corrected in migration
   - Populate FieldCorrectionRecord incrementally

4. **Data Preservation**
   - Original extracted values always preserved
   - No destructive operations
   - Full audit trail maintained


Performance Considerations
==========================

1. **Indexing**
   - FieldCorrectionRecord.extracted_field_id (foreign key)
   - FieldCorrectionRecord.corrected_at (timeline queries)
   - DocumentCorrectionAudit.document_id (document filtering)
   - DocumentCorrectionAudit.correction_started_at (reporting)
   - CorrectionTrainingDataRecord.document_id (export queries)

2. **Query Optimization**
   - Denormalized correction_training_data table
   - Aggregated stats cached in DocumentCorrectionAudit
   - Snapshots optional (for storage optimization)

3. **Batch Operations**
   - Max 100 corrections per batch
   - Single transaction for atomicity
   - Audit record created per session

4. **Export Performance**
   - Streaming export for large datasets
   - Format conversion (JSONL, CSV, Parquet)
   - Temporary S3 storage (7-day expiration)


Security & Access Control
==========================

1. **Authentication**
   - All endpoints require JWT token
   - User ID extracted from token

2. **Authorization**
   - User can only correct their own documents
   or documents in their project
   - Supervisor role can correct any document
   - Admin role can access all analytics

3. **Audit Trail**
   - Every correction has user attribution
   - Timestamps recorded (UTC)
   - Cannot modify existing corrections (only add new)
   - Cannot delete corrections (mark inactive instead)

4. **Compliance**
   - Critical corrections flagged
   - Backup snapshots for rollback
   - Correction session logging
   - Training data with export version tracking


Monitoring & Alerts
===================

Recommended metrics to track:

1. **Correction Volume**
   - Corrections per document
   - Corrections per day
   - Trend analysis

2. **Quality Metrics**
   - Correction rate by field and document type
   - Most common correction reasons
   - Average confidence adjustment

3. **Training Data**
   - Records with feedback sentiment
   - Feedback coverage rate
   - Export frequency and volume

4. **User Performance**
   - Corrections per user
   - Session duration
   - Critical corrections flagged

5. **Error Patterns**
   - Group corrections by reason
   - Identify systematic issues
   - Priority areas for model improvement
"""

# Configuration constants
CORRECTION_REASONS = [
    "extraction_error",
    "ocr_error",
    "wrong_field",
    "typo",
    "ambiguous",
    "missing",
    "format_error",
    "incomplete",
    "validation_failure",
    "confidence_low",
    "other",
]

CORRECTION_TYPES = [
    "value_change",
    "value_cleared",
    "value_added",
    "confidence_adjusted",
    "type_changed",
    "format_corrected",
]

FEEDBACK_SENTIMENTS = [
    "excellent",
    "good",
    "poor",
    "unusable",
]

EXPORT_FORMATS = [
    "jsonl",
    "csv",
    "parquet",
]

# Limits and constraints
MAX_BATCH_SIZE = 100
CORRECTION_RETENTION_DAYS = 365 * 2  # 2 years
EXPORT_EXPIRATION_DAYS = 7
FEEDBACK_COVERAGE_TARGET = 0.70  # 70% of corrections should have feedback
