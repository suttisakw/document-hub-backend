"""
Confidence Routing Service

Routes documents based on confidence scores:
- confidence > 0.85 → auto approve
- 0.6–0.85 → flag for review
- < 0.6 → force manual review

Applies to: header fields, table rows, whole document
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime
from uuid import uuid4
import logging

from app.schemas.confidence_routing import (
    RoutingStatus,
    ConfidenceLevel,
    RoutingRule,
    FieldConfidence,
    TableRowConfidence,
    HeaderConfidence,
    DocumentConfidenceScore,
    ConfidenceRoutingRequest,
    ConfidenceRoutingResponse,
    RoutingStatistics,
    BulkRoutingResponse,
    RoutingConfiguration,
)

logger = logging.getLogger(__name__)


class ConfidenceRoutingService:
    """Service for routing documents based on confidence scores."""
    
    def __init__(self):
        """Initialize confidence routing service."""
        self.rules: Dict[str, RoutingRule] = self._init_default_rules()
        self.routing_history: List[Dict] = []
        self.statistics: Dict[RoutingStatus, int] = {
            RoutingStatus.APPROVED: 0,
            RoutingStatus.REVIEW_REQUIRED: 0,
            RoutingStatus.REJECTED: 0,
        }
    
    def _init_default_rules(self) -> Dict[str, RoutingRule]:
        """Initialize default routing rules."""
        return {
            "default": RoutingRule(
                name="default",
                high_confidence_threshold=0.85,
                medium_confidence_threshold=0.6,
                low_confidence_action="review",
                apply_to_header=True,
                apply_to_rows=True,
                apply_to_document=True,
                require_all_approved=False,
            ),
            "strict": RoutingRule(
                name="strict",
                high_confidence_threshold=0.9,
                medium_confidence_threshold=0.7,
                low_confidence_action="reject",
                apply_to_header=True,
                apply_to_rows=True,
                apply_to_document=True,
                require_all_approved=True,
            ),
            "lenient": RoutingRule(
                name="lenient",
                high_confidence_threshold=0.75,
                medium_confidence_threshold=0.5,
                low_confidence_action="review",
                apply_to_header=True,
                apply_to_rows=True,
                apply_to_document=True,
                require_all_approved=False,
            ),
        }
    
    def _get_confidence_level(
        self,
        confidence: float,
        rule: RoutingRule
    ) -> ConfidenceLevel:
        """Determine confidence level from score and rule."""
        if confidence > rule.high_confidence_threshold:
            return ConfidenceLevel.HIGH
        elif confidence >= rule.medium_confidence_threshold:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW
    
    def _get_routing_status_for_field(
        self,
        confidence: float,
        confidence_level: ConfidenceLevel,
        rule: RoutingRule
    ) -> RoutingStatus:
        """Determine routing status for a single field."""
        if confidence_level == ConfidenceLevel.HIGH:
            return RoutingStatus.APPROVED
        elif confidence_level == ConfidenceLevel.MEDIUM:
            return RoutingStatus.REVIEW_REQUIRED
        else:  # LOW
            if rule.low_confidence_action == "reject":
                return RoutingStatus.REJECTED
            else:
                return RoutingStatus.REVIEW_REQUIRED
    
    def route_header_fields(
        self,
        extracted_fields: Dict[str, any],
        field_confidences: Dict[str, float],
        rule: RoutingRule,
        is_corrected_fields: Optional[Dict[str, bool]] = None,
        correction_versions: Optional[Dict[str, int]] = None,
    ) -> HeaderConfidence:
        """
        Route header fields based on confidence scores.
        
        Args:
            extracted_fields: Header field values
            field_confidences: Confidence scores per field
            rule: Routing rule to apply
            is_corrected_fields: Whether fields are corrected
            correction_versions: Correction versions per field
            
        Returns:
            HeaderConfidence with routing status
        """
        field_confidences_list = []
        total_confidence = 0.0
        min_confidence = 1.0
        max_confidence = 0.0
        
        for field_name, value in extracted_fields.items():
            confidence = field_confidences.get(field_name, 0.0)
            confidence_level = self._get_confidence_level(confidence, rule)
            routing_status = self._get_routing_status_for_field(
                confidence, confidence_level, rule
            )
            
            is_corrected = False
            correction_version = None
            if is_corrected_fields:
                is_corrected = is_corrected_fields.get(field_name, False)
            if correction_versions:
                correction_version = correction_versions.get(field_name)
            
            field_conf = FieldConfidence(
                field_name=field_name,
                field_value=value,
                confidence=confidence,
                confidence_level=confidence_level,
                routing_status=routing_status,
                is_corrected=is_corrected,
                correction_version=correction_version,
            )
            field_confidences_list.append(field_conf)
            
            total_confidence += confidence
            min_confidence = min(min_confidence, confidence)
            max_confidence = max(max_confidence, confidence)
        
        # Calculate average confidence
        avg_confidence = (
            total_confidence / len(field_confidences) if field_confidences else 0.0
        )
        
        # Determine overall header status
        header_confidence_level = self._get_confidence_level(avg_confidence, rule)
        header_routing_status = self._get_routing_status_for_field(
            avg_confidence, header_confidence_level, rule
        )
        
        # Check if all fields are approved
        all_approved = all(
            fc.routing_status == RoutingStatus.APPROVED
            for fc in field_confidences_list
        )
        
        # Generate flags
        flags = self._generate_flags(
            field_confidences_list, avg_confidence, rule, "header"
        )
        
        return HeaderConfidence(
            field_confidences=field_confidences_list,
            average_confidence=avg_confidence,
            confidence_level=header_confidence_level,
            routing_status=header_routing_status,
            min_field_confidence=min_confidence,
            max_field_confidence=max_confidence,
            all_fields_approved=all_approved,
            flags=flags,
        )
    
    def route_table_rows(
        self,
        table_rows: List[Dict[str, any]],
        row_confidences: List[Dict[str, float]],
        rule: RoutingRule,
    ) -> List[TableRowConfidence]:
        """
        Route table rows based on confidence scores.
        
        Args:
            table_rows: Rows of data
            row_confidences: Confidence scores per row and field
            rule: Routing rule to apply
            
        Returns:
            List of TableRowConfidence objects
        """
        table_route_results = []
        
        for row_idx, row_data in enumerate(table_rows):
            row_conf = row_confidences[row_idx] if row_idx < len(row_confidences) else {}
            
            field_confidences_list = []
            total_confidence = 0.0
            min_confidence = 1.0
            max_confidence = 0.0
            
            for field_name, value in row_data.items():
                confidence = row_conf.get(field_name, 0.0)
                confidence_level = self._get_confidence_level(confidence, rule)
                routing_status = self._get_routing_status_for_field(
                    confidence, confidence_level, rule
                )
                
                field_conf = FieldConfidence(
                    field_name=field_name,
                    field_value=value,
                    confidence=confidence,
                    confidence_level=confidence_level,
                    routing_status=routing_status,
                )
                field_confidences_list.append(field_conf)
                
                total_confidence += confidence
                min_confidence = min(min_confidence, confidence)
                max_confidence = max(max_confidence, confidence)
            
            # Calculate average confidence for row
            avg_confidence = (
                total_confidence / len(row_data) if row_data else 0.0
            )
            
            # Determine row routing status
            row_confidence_level = self._get_confidence_level(avg_confidence, rule)
            row_routing_status = self._get_routing_status_for_field(
                avg_confidence, row_confidence_level, rule
            )
            
            # Generate flags
            flags = self._generate_flags(
                field_confidences_list, avg_confidence, rule, f"row_{row_idx}"
            )
            
            row_conf_obj = TableRowConfidence(
                row_index=row_idx,
                row_data=row_data,
                average_confidence=avg_confidence,
                field_confidences=field_confidences_list,
                confidence_level=row_confidence_level,
                routing_status=row_routing_status,
                min_field_confidence=min_confidence,
                max_field_confidence=max_confidence,
                flags=flags,
            )
            table_route_results.append(row_conf_obj)
        
        return table_route_results
    
    def _generate_flags(
        self,
        field_confidences: List[FieldConfidence],
        avg_confidence: float,
        rule: RoutingRule,
        component: str,
    ) -> List[str]:
        """Generate flags for low-confidence fields."""
        flags = []
        
        # Check for very low individual field confidences
        for field_conf in field_confidences:
            if field_conf.confidence < 0.3:
                flags.append(
                    f"VERY_LOW_CONFIDENCE: {field_conf.field_name} "
                    f"({field_conf.confidence:.2f})"
                )
            elif field_conf.routing_status == RoutingStatus.REVIEW_REQUIRED:
                flags.append(
                    f"REVIEW_NEEDED: {field_conf.field_name} "
                    f"({field_conf.confidence:.2f})"
                )
        
        # Check for low average confidence
        if avg_confidence < rule.medium_confidence_threshold:
            flags.append(
                f"LOW_AVERAGE_CONFIDENCE: {component} ({avg_confidence:.2f})"
            )
        
        # Check for high variance in confidence
        if field_confidences:
            min_conf = min(fc.confidence for fc in field_confidences)
            max_conf = max(fc.confidence for fc in field_confidences)
            confidence_variance = max_conf - min_conf
            
            if confidence_variance > 0.4:
                flags.append(
                    f"HIGH_CONFIDENCE_VARIANCE: {component} "
                    f"(range: {min_conf:.2f}-{max_conf:.2f})"
                )
        
        return flags
    
    def _determine_document_status(
        self,
        header_status: RoutingStatus,
        row_statuses: List[RoutingStatus],
        document_confidence: float,
        rule: RoutingRule,
    ) -> Tuple[RoutingStatus, str]:
        """
        Determine final document routing status.
        
        Logic:
        - If any component is REJECTED → REJECTED
        - If require_all_approved and any is REVIEW → REVIEW
        - If document_confidence is low → override
        - Otherwise combine statuses
        
        Returns:
            Tuple of (final_status, reason)
        """
        # Check for any rejections
        statuses = [header_status] + row_statuses
        
        if any(s == RoutingStatus.REJECTED for s in statuses):
            return (
                RoutingStatus.REJECTED,
                "One or more components have low confidence (< medium threshold)"
            )
        
        # If require_all_approved, all must be approved
        if rule.require_all_approved:
            if not all(s == RoutingStatus.APPROVED for s in statuses):
                return (
                    RoutingStatus.REVIEW_REQUIRED,
                    "Not all components approved (strict rule)"
                )
        
        # Check document confidence
        doc_confidence_level = self._get_confidence_level(document_confidence, rule)
        
        if doc_confidence_level == ConfidenceLevel.HIGH:
            return (
                RoutingStatus.APPROVED,
                "Overall document confidence is high"
            )
        elif doc_confidence_level == ConfidenceLevel.MEDIUM:
            return (
                RoutingStatus.REVIEW_REQUIRED,
                "Overall document confidence is medium"
            )
        else:  # LOW
            if rule.low_confidence_action == "reject":
                return (
                    RoutingStatus.REJECTED,
                    "Overall document confidence is low"
                )
            else:
                return (
                    RoutingStatus.REVIEW_REQUIRED,
                    "Overall document confidence is low"
                )
    
    def route_document(
        self,
        request: ConfidenceRoutingRequest
    ) -> ConfidenceRoutingResponse:
        """
        Route a document based on confidence scores.
        
        Args:
            request: Document with confidence scores
            
        Returns:
            Routing decision response
        """
        # Get routing rule
        rule = self.rules.get(request.routing_rule)
        if not rule:
            logger.warning(
                f"Unknown routing rule: {request.routing_rule}, using default"
            )
            rule = self.rules["default"]
        
        # Track which components to route
        header_confidence = None
        row_confidences = []
        
        # Route header fields if requested
        if rule.apply_to_header:
            header_confidence = self.route_header_fields(
                request.extracted_fields,
                request.field_confidences,
                rule
            )
        
        # Route table rows if requested
        if rule.apply_to_rows and request.table_rows:
            row_confidences = self.route_table_rows(
                request.table_rows,
                request.row_confidences or [],
                rule
            )
        
        # Get component statuses for document decision
        header_status = header_confidence.routing_status if header_confidence else None
        row_statuses = [r.routing_status for r in row_confidences]
        
        # Apply document-level confidence if requested
        document_status = None
        if rule.apply_to_document:
            document_status, status_reason = self._determine_document_status(
                header_status or RoutingStatus.APPROVED,
                row_statuses,
                request.document_confidence,
                rule,
            )
        else:
            # Combine component statuses without document confidence
            if any(s == RoutingStatus.REJECTED for s in [header_status] + row_statuses if s):
                document_status = RoutingStatus.REJECTED
                status_reason = "One or more components rejected"
            elif any(s == RoutingStatus.REVIEW_REQUIRED for s in [header_status] + row_statuses if s):
                document_status = RoutingStatus.REVIEW_REQUIRED
                status_reason = "One or more components require review"
            else:
                document_status = RoutingStatus.APPROVED
                status_reason = "All components approved"
        
        # Collect all scores
        confidence_scores_dict = {
            "overall_confidence": request.document_confidence,
            **request.field_confidences
        }
        
        # Calculate average component confidence
        all_confidences = [request.document_confidence] + list(request.field_confidences.values())
        average_component_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
        
        # Find low confidence fields
        low_confidence_fields = [
            field_name for field_name, conf in request.field_confidences.items()
            if conf < rule.medium_confidence_threshold
        ]
        
        # Generate flags
        flags = []
        if document_status == RoutingStatus.REJECTED:
            flags.append("DOCUMENT_REJECTED")
        if document_status == RoutingStatus.REVIEW_REQUIRED:
            flags.append("REQUIRES_HUMAN_REVIEW")
        if len(low_confidence_fields) > 0:
            flags.append(f"LOW_CONFIDENCE_FIELDS: {len(low_confidence_fields)}")
        
        # Identify problem fields and rows
        attention_fields = low_confidence_fields
        attention_rows = [
            r.row_index for r in row_confidences
            if r.routing_status in (RoutingStatus.REVIEW_REQUIRED, RoutingStatus.REJECTED)
        ]
        
        # Generate recommended actions
        recommended_actions = self._generate_recommended_actions(
            document_status,
            header_status,
            row_statuses,
            low_confidence_fields,
            rule
        )
        
        # Create confidence score object
        confidence_score = DocumentConfidenceScore(
            document_id=request.document_id,
            document_type=request.document_type,
            overall_confidence=request.document_confidence,
            confidence_level=self._get_confidence_level(
                request.document_confidence, rule
            ),
            routing_status=document_status,
            header_confidence=header_confidence,
            row_confidences=row_confidences,
            document_confidence_details=confidence_scores_dict,
            average_component_confidence=average_component_confidence,
            has_low_confidence_fields=len(low_confidence_fields) > 0,
            low_confidence_fields=low_confidence_fields,
            flags=flags,
        )
        
        # Create response
        response = ConfidenceRoutingResponse(
            document_id=request.document_id,
            routing_status=document_status,
            confidence_score=confidence_score,
            routing_reason=status_reason,
            requires_attention=(
                document_status != RoutingStatus.APPROVED
                or len(low_confidence_fields) > 0
            ),
            attention_fields=attention_fields,
            attention_rows=attention_rows,
            recommended_actions=recommended_actions,
        )
        
        # Update statistics
        self.statistics[document_status] += 1
        
        # Log routing decision
        self._log_routing_decision(
            request.document_id,
            document_status,
            request.document_confidence,
            rule.name,
            confidence_scores_dict
        )
        
        logger.info(
            f"Document {request.document_id} routed to {document_status.value} "
            f"(confidence: {request.document_confidence:.2f})"
        )
        
        return response
    
    def _generate_recommended_actions(
        self,
        document_status: RoutingStatus,
        header_status: Optional[RoutingStatus],
        row_statuses: List[RoutingStatus],
        low_confidence_fields: List[str],
        rule: RoutingRule,
    ) -> List[str]:
        """Generate recommended actions based on routing status."""
        actions = []
        
        if document_status == RoutingStatus.APPROVED:
            actions.append("Document automatically approved - proceed to processing")
        
        elif document_status == RoutingStatus.REVIEW_REQUIRED:
            actions.append("Flag document for human review")
            if header_status == RoutingStatus.REVIEW_REQUIRED:
                actions.append("Review header fields with low confidence")
            if any(s == RoutingStatus.REVIEW_REQUIRED for s in row_statuses):
                actions.append("Review table rows with low confidence")
            if low_confidence_fields:
                actions.append(
                    f"Focus review on fields: {', '.join(low_confidence_fields[:5])}"
                )
        
        elif document_status == RoutingStatus.REJECTED:
            actions.append("Return document for reprocessing or manual data entry")
            if rule.low_confidence_action == "reject":
                actions.append("Low confidence threshold failed - re-extract or manually correct")
        
        actions.append("Check and correct any identified errors in extracted data")
        
        return actions
    
    def _log_routing_decision(
        self,
        document_id: str,
        status: RoutingStatus,
        confidence: float,
        rule_name: str,
        confidence_scores: Dict[str, float],
    ) -> None:
        """Log routing decision to history."""
        entry = {
            "document_id": document_id,
            "status": status,
            "confidence": confidence,
            "rule_name": rule_name,
            "timestamp": datetime.utcnow(),
            "confidence_scores": confidence_scores,
        }
        self.routing_history.append(entry)
    
    def route_bulk_documents(
        self,
        requests: List[ConfidenceRoutingRequest],
        rule_name: str = "default"
    ) -> BulkRoutingResponse:
        """
        Route multiple documents at once.
        
        Args:
            requests: List of routing requests
            rule_name: Routing rule to apply
            
        Returns:
            Bulk routing response
        """
        batch_id = f"batch_{uuid4().hex[:8]}"
        results = []
        counts = {
            RoutingStatus.APPROVED: 0,
            RoutingStatus.REVIEW_REQUIRED: 0,
            RoutingStatus.REJECTED: 0,
        }
        
        for request in requests:
            request.routing_rule = rule_name
            response = self.route_document(request)
            results.append(response)
            counts[response.routing_status] += 1
        
        return BulkRoutingResponse(
            batch_id=batch_id,
            total_documents=len(requests),
            processed_documents=len(results),
            approved=counts[RoutingStatus.APPROVED],
            review_required=counts[RoutingStatus.REVIEW_REQUIRED],
            rejected=counts[RoutingStatus.REJECTED],
            results=results,
        )
    
    def get_statistics(self, days: Optional[int] = None) -> Dict[str, any]:
        """Get routing statistics."""
        total = sum(self.statistics.values())
        
        return {
            "total_documents_routed": total,
            "approved": self.statistics[RoutingStatus.APPROVED],
            "review_required": self.statistics[RoutingStatus.REVIEW_REQUIRED],
            "rejected": self.statistics[RoutingStatus.REJECTED],
            "approval_rate": (
                self.statistics[RoutingStatus.APPROVED] / total if total > 0 else 0.0
            ),
            "review_rate": (
                self.statistics[RoutingStatus.REVIEW_REQUIRED] / total if total > 0 else 0.0
            ),
            "rejection_rate": (
                self.statistics[RoutingStatus.REJECTED] / total if total > 0 else 0.0
            ),
        }
    
    def get_routing_rules(self) -> Dict[str, RoutingRule]:
        """Get all routing rules."""
        return self.rules
    
    def add_or_update_rule(self, rule: RoutingRule) -> None:
        """Add or update a routing rule."""
        self.rules[rule.name] = rule
        logger.info(f"Routing rule '{rule.name}' added/updated")
    
    def delete_rule(self, rule_name: str) -> bool:
        """Delete a routing rule."""
        if rule_name in self.rules:
            del self.rules[rule_name]
            logger.info(f"Routing rule '{rule_name}' deleted")
            return True
        return False
