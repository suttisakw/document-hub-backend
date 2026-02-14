from typing import List, Dict, Any, Optional
from app.schemas.confidence import ConfidenceScore, ExtractedSource, ExtractionStage

class ConfidenceService:
    """Centralized service for confidence scoring and weighting."""

    @staticmethod
    def calculate_header_score(
        base_value: float,
        value_text: str,
        field_importance: float = 1.0,
        proximity: float = 1.0,
        completeness: float = 1.0
    ) -> float:
        """
        Calculate confidence for a header field.
        
        Args:
            base_value: Base confidence from extraction method (e.g., 0.95 for template)
            value_text: The extracted text
            field_importance: Weighting for field criticality
            proximity: Spatial or structural proximity to expected location
            completeness: How much of the expected pattern was matched
        """
        score = base_value * proximity * completeness
        
        # Penalize short or empty values
        if not value_text or len(value_text.strip()) < 2:
            score *= 0.5
            
        return min(1.0, max(0.0, score))

    @staticmethod
    def calculate_table_score(
        cell_confidences: List[float],
        validation_pass_rate: float = 1.0,
        row_count_quality: float = 1.0
    ) -> float:
        """
        Calculate aggregate confidence for a table.
        """
        if not cell_confidences:
            return 0.0
            
        avg_cell_conf = sum(cell_confidences) / len(cell_confidences)
        return min(1.0, max(0.0, avg_cell_conf * validation_pass_rate * row_count_quality))

    @staticmethod
    def adjust_for_validation(
        current_score: ConfidenceScore,
        penalty: float = 0.15,
        is_valid: bool = True,
        reason: str = ""
    ) -> ConfidenceScore:
        """
        Adjust confidence score based on validation results.
        """
        if is_valid:
            return current_score

        new_value = max(0.0, current_score.value - penalty)
        
        # Create a new instance to keep history
        new_history = current_score.history + [new_value]
        
        updated_evidence = current_score.evidence.copy()
        if reason:
            updated_evidence["validation_penalty_reason"] = reason

        return ConfidenceScore(
            value=new_value,
            source=current_score.source,
            stage=current_score.stage,
            evidence=updated_evidence,
            validation_adjusted=True,
            history=new_history
        )

    @staticmethod
    def aggregate_document_confidence(field_confidences: List[float]) -> float:
        """
        Calculate overall document confidence.
        Standardizes on weighted average if needed in future.
        """
        if not field_confidences:
            return 0.0
        return sum(field_confidences) / len(field_confidences)
