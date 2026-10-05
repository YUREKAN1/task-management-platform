from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user
from app.schemas.user import UserResponse, UserUpdate
from app.services import user as user_service
from app.models.user import User

router = APIRouter()

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get Current User Profile",
    responses={
        200: {"description": "Profile information of the authenticated user."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "User account is deactivated."},
    },
)
def read_users_me(current_user: User = Depends(get_current_user)):
    """
    Returns the profile and role metadata of the authenticated user.
    """
    return current_user

@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update Current User Profile",
    responses={
        200: {"description": "User profile successfully updated."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "User account is deactivated."},
        409: {"description": "The requested email address is already in use by another user."},
        422: {"description": "Validation error (e.g. empty name string)."},
    },
)
def update_users_me(
    user_in: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Updates the authenticated user's name or email. If email is modified, it is normalized
    and verified against duplicate usage. Sending an empty payload `{}` acts as a no-op.
    """
    updated_user = user_service.update_user_profile(db, user=current_user, user_in=user_in)
    return updated_user

@router.post(
    "/me/deactivate",
    response_model=UserResponse,
    summary="Deactivate Current User Account",
    responses={
        200: {"description": "User account successfully deactivated (`is_active: false`)."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "User account is already deactivated."},
    },
)
def deactivate_users_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Deactivates the authenticated user's account. Subsequent login attempts or authenticated
    operations will be rejected with 403 Forbidden. Generates a `USER_DEACTIVATED` audit log.
    """
    return user_service.deactivate_user(db, user=current_user, actor=current_user)
