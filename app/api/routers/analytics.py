from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from typing import List, Dict, Any

from app.db.session import get_session
from app.api.deps import get_current_user
from app.models import User
from app.services.learning_service import LearningService

router = APIRouter()

@router.get("/accuracy-report")
async def get_accuracy_report(
    days: int = 30,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get extraction accuracy metrics based on user corrections."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
        
    service = LearningService(session)
    return service.get_field_accuracy_report(days=days)

@router.get("/calibration-suggestions")
async def get_calibration_suggestions(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get suggestions for adjusting confidence thresholds."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    service = LearningService(session)
    return service.suggest_heuristic_adjustments()

@router.post("/calibrate")
async def apply_calibration(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Trigger automatic threshold calibration based on historical data."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    service = LearningService(session)
    return service.apply_auto_calibration()
