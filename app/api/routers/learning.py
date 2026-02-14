from fastapi import APIRouter, Depends, Query
from sqlmodel import Session
from app.db.session import get_session
from app.api.deps import get_current_user
from app.models import User
from app.services.learning_service import LearningService
from typing import List, Dict, Any

router = APIRouter(prefix="/learning", tags=["learning"])

@router.get("/report", summary="Get field accuracy report")
def get_learning_report(
    days: int = Query(30, ge=1, le=365),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get accuracy metrics for extracted fields based on corrections."""
    service = LearningService(session)
    return service.get_field_accuracy_report(days=days)

@router.get("/suggestions", summary="Get improvement suggestions")
def get_learning_suggestions(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> List[str]:
    """Get heuristic suggestions for improving extraction accuracy."""
    service = LearningService(session)
    return service.suggest_heuristic_adjustments()

@router.post("/calibrate", summary="Apply auto-calibration")
def apply_calibration(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Automatically adjust extraction thresholds based on recent accuracy."""
    service = LearningService(session)
    return service.apply_auto_calibration()

@router.get("/templates/suggest", summary="Suggest new templates")
def suggest_templates(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Suggest new document templates based on recurring field patterns."""
    service = LearningService(session)
    return service.suggest_new_templates()
