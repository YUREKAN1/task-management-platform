from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database.session import get_db

router = APIRouter()

@router.get(
    "/health",
    summary="API Liveness Probe",
    responses={
        200: {"description": "API service is alive and healthy."},
    },
)
def health_check():
    """
    Basic health check endpoint returning 200 OK if the FastAPI process is responsive.
    """
    return {"status": "ok"}

@router.get(
    "/health/db",
    summary="Database Connectivity Probe",
    responses={
        200: {"description": "Database connectivity check result."},
    },
)
def db_health_check(db: Session = Depends(get_db)):
    """
    Executes a test query (`SELECT 1`) to verify database connectivity.
    """
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}
