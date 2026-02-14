"""
Document Correction Service

Business logic for:
1. Applying corrections to fields
2. Managing correction history
3. Validation of corrections
4. Exporting training data
5. Analytics and reporting
"""

from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlmodel import Session, select

from app.models import (
    Document,
    DocumentCorrectionAudit,
    ExtractedField,
    FieldCorrectionRecord,
)
from app.schemas.document_correction import (
    CorrectionFeedback,
    CorrectionHistory,
    CorrectionReason,
    CorrectionTrainingRecord,
    CorrectionType,
    DocumentCorrectionSummary,
    FieldCorrection,
    FieldValue,
    FeedbackSentiment,
)
from app.schemas.correction_api import (
    BatchCorrectionResponse,
    CorrectionErrorResponse,
    CorrectionHistoryResponse,
    CorrectionResponse,
    CorrectionStatisticsResponse,
    DocumentCorrectionSummaryResponse,
    SubmitCorrectionRequest,
    TrainingDataExportResponse,
    TrainingDataRecordResponse,
)


class CorrectionService:
    """Service for handling document field corrections."""

    def __init__(self, db: Session):
        self.db = db
        self.user_id: Optional[str] = None  # Set by API middleware

    def set_current_user(self, user_id: str) -> None:
        """Set the current user making corrections."""
        self.user_id = user_id

    # ====== APPLY CORRECTIONS ======

    def apply_correction(
        self,
        document_id: int,
        extracted_field_id: int,
        request: SubmitCorrectionRequest,
    ) -> CorrectionResponse:
        """
        Apply a single correction to a field.

        Args:
            document_id: Document being corrected
            extracted_field_id: Field being corrected
            request: Correction details

        Returns:
            CorrectionResponse with applied correction

        Raises:
            ValueError: If field not found or correction invalid
        """
        # Validate field exists
        field = self.db.get(ExtractedField, extracted_field_id)
        if not field:
            raise ValueError(f"Field {extracted_field_id} not found")

        if field.document_id != document_id:
            raise ValueError("Field does not belong to this document")

        # Create correction record
        correction_id = uuid4()
        original_value = field.field_value

        # Determine correction type
        correction_type = self._determine_correction_type(
            original_value, request.corrected_value
        )

        # Create database record
        correction_record = FieldCorrectionRecord(
            extracted_field_id=extracted_field_id,
            corrected_by_user_id=self._get_user_db_id(),
            original_value=str(original_value) if original_value else None,
            corrected_value=str(request.corrected_value)
            if request.corrected_value is not None
            else None,
            correction_type=correction_type.value,
            correction_reason=request.correction_reason,
            reason_details=request.reason_details,
            confidence_adjustment=request.confidence_adjustment,
            feedback_sentiment=request.feedback_sentiment,
            feedback_comment=request.feedback_comment,
            is_critical=request.is_critical,
            corrected_at=datetime.utcnow(),
        )

        self.db.add(correction_record)

        # Phase 3.2: Trigger feedback learning
        from app.services.feedback_service import FeedbackService
        feedback_service = FeedbackService(self.db)
        feedback_service.log_correction_feedback(correction_record)

        # Update extracted field
        field.field_value = str(request.corrected_value)
        if request.confidence_adjustment:
            field.confidence = max(
                0.0,
                min(1.0, (field.confidence or 0.0) + request.confidence_adjustment),
            )

        # Mark field as edited
        field.is_edited = True
        field.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(correction_record)

        # Return response
        return CorrectionResponse(
            correction_id=UUID(int=correction_record.id or 0),
            field_name=field.field_name,
            original_value=original_value,
            corrected_value=request.corrected_value,
            corrected_at=correction_record.corrected_at,
            corrected_by=self.user_id or "system",
            correction_reason=request.correction_reason,
            is_applied=True,
            confidence_adjustment=request.confidence_adjustment,
            feedback_sentiment=request.feedback_sentiment,
        )

    def apply_batch_corrections(
        self,
        document_id: int,
        requests: list[SubmitCorrectionRequest],
        session_notes: Optional[str] = None,
    ) -> BatchCorrectionResponse:
        """
        Apply multiple corrections to a document.

        Args:
            document_id: Document being corrected
            requests: List of corrections
            session_notes: Notes about correction session

        Returns:
            BatchCorrectionResponse with results

        Validates document exists and tracks as correction session.
        """
        start_time = datetime.utcnow()
        results = []
        successful = 0
        failed = 0

        # Get document
        document = self.db.get(Document, document_id)
        if not document:
            raise ValueError(f"Document {document_id} not found")

        # Process each correction
        for request in requests:
            try:
                # Find field
                field_stmt = select(ExtractedField).where(
                    (ExtractedField.document_id == document_id)
                    & (ExtractedField.field_name == request.field_name)
                )
                field = self.db.exec(field_stmt).first()

                if not field:
                    raise ValueError(f"Field '{request.field_name}' not found")

                # Apply correction
                response = self.apply_correction(
                    document_id, field.id, request  # type: ignore
                )
                results.append(response)
                successful += 1

            except Exception as e:
                failed += 1
                results.append(
                    CorrectionErrorResponse(
                        error_code="correction_failed",
                        message=str(e),
                    )
                )

        # Create audit record
        audit = DocumentCorrectionAudit(
            document_id=document_id,
            corrected_by_user_id=self._get_user_db_id(),
            total_fields_corrected=successful,
            total_corrections=len(requests),
            has_critical_corrections=any(
                isinstance(r, CorrectionResponse) and getattr(r, "is_critical", False)
                for r in results
            ),
            feedback_provided_count=sum(
                1
                for r in results
                if isinstance(r, CorrectionResponse)
                and getattr(r, "feedback_sentiment", None)
            ),
            correction_started_at=start_time,
            correction_completed_at=datetime.utcnow(),
            session_notes=session_notes,
        )

        self.db.add(audit)
        self.db.commit()

        return BatchCorrectionResponse(
            total_submissions=len(requests),
            successful=successful,
            failed=failed,
            results=results,
            total_corrections_applied=successful,
            session_duration_seconds=(
                datetime.utcnow() - start_time
            ).total_seconds(),
        )

    # ====== RETRIEVE CORRECTION HISTORY ======

    def get_field_correction_history(
        self, document_id: int, field_name: str
    ) -> CorrectionHistoryResponse:
        """
        Get complete correction history for a field.

        Args:
            document_id: Document containing field
            field_name: Name of field

        Returns:
            CorrectionHistoryResponse with full history
        """
        # Get field
        field_stmt = select(ExtractedField).where(
            (ExtractedField.document_id == document_id)
            & (ExtractedField.field_name == field_name)
        )
        field = self.db.exec(field_stmt).first()

        if not field:
            raise ValueError(f"Field '{field_name}' not found")

        # Get all corrections
        correction_stmt = select(FieldCorrectionRecord).where(
            FieldCorrectionRecord.extracted_field_id == field.id
        )
        corrections = self.db.exec(correction_stmt).all()

        # Convert to responses
        correction_responses = [
            CorrectionResponse(
                correction_id=UUID(int=c.id or 0),
                field_name=c.extracted_field.field_name,  # type: ignore
                original_value=c.original_value,
                corrected_value=c.corrected_value,
                corrected_at=c.corrected_at,
                corrected_by=c.corrected_by.email if c.corrected_by else "unknown",  # type: ignore
                correction_reason=c.correction_reason,
                is_applied=True,
                confidence_adjustment=c.confidence_adjustment,
                feedback_sentiment=c.feedback_sentiment,
            )
            for c in corrections
        ]

        # Calculate severity
        severity = "none" if not corrections else self._assess_severity(corrections)

        return CorrectionHistoryResponse(
            field_name=field_name,
            original_extraction=field.field_value,
            original_confidence=field.confidence,
            original_source=getattr(field, "source", None),
            current_value=field.field_value,
            is_corrected=len(corrections) > 0,
            correction_count=len(corrections),
            corrections=correction_responses,
            correction_severity=severity,
        )

    def get_document_correction_summary(
        self, document_id: int
    ) -> DocumentCorrectionSummaryResponse:
        """
        Get correction summary for entire document.

        Args:
            document_id: Document ID

        Returns:
            DocumentCorrectionSummaryResponse with statistics
        """
        # Get all fields
        fields_stmt = select(ExtractedField).where(
            ExtractedField.document_id == document_id
        )
        fields = self.db.exec(fields_stmt).all()

        # Get all corrections for this document
        field_ids = [f.id for f in fields]
        if field_ids:
            corrections_stmt = select(FieldCorrectionRecord).where(
                FieldCorrectionRecord.extracted_field_id.in_(field_ids)
            )
            corrections = self.db.exec(corrections_stmt).all()
        else:
            corrections = []

        # Build statistics
        corrected_fields = set(c.extracted_field_id for c in corrections)
        corrections_by_reason = {}
        corrections_by_type = {}
        critical_count = 0
        feedback_count = 0
        feedback_dist = {}

        for c in corrections:
            # By reason
            corrections_by_reason[c.correction_reason] = (
                corrections_by_reason.get(c.correction_reason, 0) + 1
            )

            # By type
            corrections_by_type[c.correction_type] = (
                corrections_by_type.get(c.correction_type, 0) + 1
            )

            # Critical
            if c.is_critical:
                critical_count += 1

            # Feedback
            if c.feedback_sentiment:
                feedback_count += 1
                feedback_dist[c.feedback_sentiment] = (
                    feedback_dist.get(c.feedback_sentiment, 0) + 1
                )

        # Timeline
        first_correction = None
        last_correction = None
        if corrections:
            first_correction = min(c.corrected_at for c in corrections)
            last_correction = max(c.corrected_at for c in corrections)

        return DocumentCorrectionSummaryResponse(
            document_id=UUID(int=document_id),
            total_fields=len(fields),
            total_corrected_fields=len(corrected_fields),
            total_corrections=len(corrections),
            correction_rate=len(corrected_fields) / len(fields) * 100
            if fields
            else 0,
            corrections_by_reason=corrections_by_reason,
            corrections_by_type=corrections_by_type,
            has_critical=critical_count > 0,
            critical_count=critical_count,
            feedback_provided_count=feedback_count,
            feedback_distribution=feedback_dist,
            first_correction_at=first_correction,
            last_correction_at=last_correction,
            requires_review=critical_count > 0 or len(corrections) > 5,
        )

    # ====== EXPORT TRAINING DATA ======

    def export_training_data(
        self,
        document_ids: Optional[list[int]] = None,
        date_range: Optional[dict[str, datetime]] = None,
        correction_reasons: Optional[list[str]] = None,
    ) -> TrainingDataExportResponse:
        """
        Export corrections as training data.

        Args:
            document_ids: Specific documents (None = all)
            date_range: Filter by date
            correction_reasons: Filter by reason

        Returns:
            TrainingDataExportResponse with export details
        """
        # Build query
        query = select(FieldCorrectionRecord)

        if document_ids:
            # Get fields for these documents
            field_stmt = select(ExtractedField.id).where(
                ExtractedField.document_id.in_(document_ids)
            )
            field_ids = [f[0] for f in self.db.exec(field_stmt).all()]
            query = query.where(FieldCorrectionRecord.extracted_field_id.in_(field_ids))

        if date_range:
            query = query.where(
                FieldCorrectionRecord.corrected_at >= date_range.get("start")
            )
            if "end" in date_range:
                query = query.where(
                    FieldCorrectionRecord.corrected_at <= date_range.get("end")
                )

        if correction_reasons:
            query = query.where(
                FieldCorrectionRecord.correction_reason.in_(correction_reasons)
            )

        corrections = self.db.exec(query).all()

        # Create training records
        training_records = [
            TrainingDataRecordResponse(
                record_id=uuid4(),
                document_id=UUID(int=c.extracted_field.document_id),  # type: ignore
                document_type="unknown",  # TODO: get from document
                page_number=c.extracted_field.page_number,  # type: ignore
                field_name=c.extracted_field.field_name,  # type: ignore
                extracted_value=c.original_value,
                extraction_confidence=None,  # TODO: get from field
                extraction_method="ocr",  # TODO: get from field
                corrected_value=c.corrected_value,
                correction_reason=c.correction_reason,
                was_correct=c.field_correction_id is None,
                feedback_sentiment=c.feedback_sentiment,
            )
            for c in corrections
        ]

        # Export response
        export_id = uuid4()

        return TrainingDataExportResponse(
            export_id=export_id,
            record_count=len(training_records),
            file_url=f"/exports/training-data/{export_id}",
            file_format="jsonl",
            file_size_bytes=sum(len(str(r.model_dump_json())) for r in training_records),
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=7),
            documents_included=len(set(r.document_id for r in training_records)),
            correction_types_included=list(set(r.correction_reason for r in training_records)),
            feedback_records=sum(
                1 for r in training_records if r.feedback_sentiment
            ),
        )

    # ====== STATISTICS ======

    def get_correction_statistics(
        self, days: int = 7
    ) -> CorrectionStatisticsResponse:
        """
        Get correction statistics for the given period.

        Args:
            days: Number of days to analyze

        Returns:
            CorrectionStatisticsResponse with metrics
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Get all corrections in period
        corrections_stmt = select(FieldCorrectionRecord).where(
            FieldCorrectionRecord.corrected_at >= cutoff_date
        )
        corrections = self.db.exec(corrections_stmt).all()

        # Build statistics
        corrections_by_reason = {}
        corrections_by_type = {}
        corrections_by_user = {}
        feedback_dist = {}

        for c in corrections:
            # By reason
            corrections_by_reason[c.correction_reason] = (
                corrections_by_reason.get(c.correction_reason, 0) + 1
            )

            # By type
            corrections_by_type[c.correction_type] = (
                corrections_by_type.get(c.correction_type, 0) + 1
            )

            # By user
            user_email = c.corrected_by.email if c.corrected_by else "unknown"  # type: ignore
            corrections_by_user[user_email] = (
                corrections_by_user.get(user_email, 0) + 1
            )

            # Feedback
            if c.feedback_sentiment:
                feedback_dist[c.feedback_sentiment] = (
                    feedback_dist.get(c.feedback_sentiment, 0) + 1
                )

        # Calculate metrics
        unique_documents = len(set(c.extracted_field.document_id for c in corrections if c.extracted_field))  # type: ignore
        unique_fields = len(
            set(c.extracted_field_id for c in corrections)
        )

        return CorrectionStatisticsResponse(
            period=f"last_{days}_days",
            total_corrections=len(corrections),
            total_corrected_fields=unique_fields,
            unique_documents=unique_documents,
            unique_users=len(corrections_by_user),
            corrections_by_reason=corrections_by_reason,
            corrections_by_type=corrections_by_type,
            corrections_by_user=corrections_by_user,
            avg_corrections_per_document=len(corrections) / max(1, unique_documents),
            correction_rate_by_field={},  # TODO: calculate
            feedback_coverage=len([
                c for c in corrections if c.feedback_sentiment
            ]) / max(1, len(corrections)),
            feedback_sentiment_distribution=feedback_dist,
            daily_corrections={},  # TODO: calculate
        )

    # ====== HELPERS ======

    def _determine_correction_type(
        self, original: Any, corrected: Any
    ) -> CorrectionType:
        """Determine the type of correction made."""
        if original is None and corrected is not None:
            return CorrectionType.VALUE_ADDED
        elif original is not None and corrected is None:
            return CorrectionType.VALUE_CLEARED
        else:
            return CorrectionType.VALUE_CHANGE

    def _assess_severity(
        self, corrections: list[FieldCorrectionRecord]
    ) -> str:
        """Assess severity of corrections."""
        critical_count = sum(1 for c in corrections if c.is_critical)
        if critical_count > 0:
            return "critical"
        elif len(corrections) > 2:
            return "high"
        elif len(corrections) > 0:
            return "medium"
        return "low"

    def _get_user_db_id(self) -> Optional[int]:
        """Get database user ID from current user identifier."""
        if not self.user_id:
            return None
        # TODO: Look up user by email or ID
        return None
