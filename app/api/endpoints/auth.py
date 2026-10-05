from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_current_user
from app.schemas.user import UserCreate, UserResponse, UserLogin
from app.schemas.token import Token
from app.services import auth as auth_service
from app.core.security import create_access_token
from app.models.user import User

router = APIRouter()

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register New User",
    responses={
        201: {"description": "User successfully registered."},
        409: {"description": "A user with this email address already exists."},
        422: {"description": "Validation error (e.g. empty name/password or invalid email)."},
    },
)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Registers a new platform user with normalized (trimmed, lowercase) email address
    and bcrypt-hashed password. Assigns the default global role `USER`.
    """
    user = auth_service.get_user_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The user with this email already exists in the system.",
        )
    user = auth_service.create_user(db, user_in=user_in)
    return user

@router.post(
    "/login",
    response_model=Token,
    summary="Authenticate User & Obtain JWT",
    responses={
        200: {"description": "Authentication successful. Returns JWT bearer access token."},
        401: {"description": "Invalid email or password."},
        403: {"description": "User account is deactivated."},
        422: {"description": "Validation error in request payload."},
    },
)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    """
    Authenticates a user via JSON credentials (`email` and `password`).
    Returns an encoded JWT Bearer token valid for platform API requests.
    """
    user = auth_service.authenticate_user(db, email=user_in.email, password=user_in.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active or user.deleted_at is not None:
        raise HTTPException(status_code=403, detail="Inactive user")
    
    access_token = create_access_token(subject=user.id)
    return {"access_token": access_token, "token_type": "bearer"}

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get Current Authenticated User (Auth Alias)",
    responses={
        200: {"description": "Profile details of the currently authenticated user."},
        401: {"description": "Missing, invalid, or expired JWT Bearer token."},
        403: {"description": "User account is deactivated."},
    },
)
def read_users_me(current_user: User = Depends(get_current_user)):
    """
    Retrieves the identity and profile information of the currently authenticated user.
    """
    return current_user
