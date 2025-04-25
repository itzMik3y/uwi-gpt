# auth/utils.py (Fixed get_current_user with eager loading)

import hashlib
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt # Import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload # <<< IMPORT selectinload

from user_db.database import get_db
# Import related models for eager loading hints
from user_db.models import User, EnrolledCourse, CourseGrade, Term, Course
from user_db.schemas import UserTokenCreate
from user_db.services import (
    blacklist_token,
    create_token_record,
    get_user_by_id, # Keep this if used elsewhere (e.g., refresh)
    hash_token,
    verify_token # verify_token now expects jti
)

from .config import jwt_settings
from .models import TokenData, TokenPayload


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

# --- ADDED verify_password helper ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against stored hash using SHA256.
    """
    password_hash = hashlib.sha256(plain_password.encode()).hexdigest()
    return password_hash == hashed_password

# --- create_token (Corrected to return JTI) ---
def create_token(data: Dict[str, Any], expires_delta: int, token_type: str) -> Tuple[str, str]:
    to_encode = data.copy()
    jti = secrets.token_hex(16)
    to_encode["jti"] = jti
    expire = datetime.utcnow() + timedelta(seconds=expires_delta)
    to_encode.update({"exp": int(expire.timestamp()), "type": token_type})
    encoded_jwt = jwt.encode(to_encode, jwt_settings.jwt_secret_key, algorithm=jwt_settings.jwt_algorithm)
    return encoded_jwt, jti

# --- store_token_in_db (Corrected to use JTI) ---
async def store_token_in_db(db: AsyncSession, user_id: int, token_jti: str, token_hash: str, token_type: str, expires_at: int, request: Optional[Request] = None) -> int:
    device_info = None; ip_address = None
    if request:
        user_agent = request.headers.get("User-Agent", "Unknown"); device_info = user_agent[:255] if user_agent else None
        forwarded = request.headers.get("X-Forwarded-For");
        if forwarded: ip_address = forwarded.split(",")[0].strip()
        else: client_host = request.client.host if request.client else None; ip_address = client_host if client_host else None
    token_data = UserTokenCreate(user_id=user_id, token_type=token_type, token_key=token_jti, token_hash=token_hash, expires_at=expires_at, device_info=device_info, ip_address=ip_address)
    token_record = await create_token_record(db, token_data)
    return token_record.id

# --- create_access_token (Corrected) ---
async def create_access_token(data: Dict[str, Any], db: AsyncSession, request: Optional[Request] = None) -> Tuple[str, int, int]:
    expires = jwt_settings.access_token_expire_seconds
    token_string, token_jti = create_token(data, expires, "access")
    expires_at = int(time.time() + expires)
    token_id = await store_token_in_db(db=db, user_id=int(data["sub"]), token_jti=token_jti, token_hash=hash_token(token_string), token_type="access", expires_at=expires_at, request=request)
    print(f"DEBUG: Stored access token record, DB ID: {token_id}, JTI: {token_jti}")
    return token_string, expires_at, token_id


async def create_refresh_token(data: Dict[str, Any], db: AsyncSession, request: Optional[Request] = None) -> Tuple[str, int, int]:
    expires = jwt_settings.refresh_token_expire_seconds
    token_string, token_jti = create_token(data, expires, "refresh")
    expires_at = int(time.time() + expires)
    token_id = await store_token_in_db(db=db, user_id=int(data["sub"]), token_jti=token_jti, token_hash=hash_token(token_string), token_type="refresh", expires_at=expires_at, request=request)
    print(f"DEBUG: Stored refresh token record, DB ID: {token_id}, JTI: {token_jti}")
    return token_string, expires_at, token_id



async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Validate access token, fetch user from DB WITH related data loaded eagerly.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            jwt_settings.jwt_secret_key,
            algorithms=[jwt_settings.jwt_algorithm]
        )
        token_payload = TokenPayload(**payload)

        if token_payload.type != "access": raise credentials_exception

        user_id_str: Optional[str] = token_payload.sub
        token_jti: Optional[str] = token_payload.jti
        if user_id_str is None or token_jti is None: raise credentials_exception
        user_id = int(user_id_str) # Convert sub to int

        # Verify token is valid in DB
        token_record = await verify_token(db=db, token_jti=token_jti, token_type="access")
        if not token_record:
            print(f"DEBUG: No valid token record found for JTI: {token_jti}")
            raise credentials_exception
        # Verify user associated with token matches the 'sub' claim
        if token_record.user_id != user_id:
            print(f"ERROR: Token user ID ({token_record.user_id}) does not match subject claim ({user_id})")
            raise credentials_exception

        # --- Fetch User with Eager Loading Options ---
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(
                # Load enrollments and the course associated with each enrollment
                selectinload(User.enrollments).selectinload(EnrolledCourse.course),
                # Load grades and the term/course associated with each grade
                selectinload(User.grades).selectinload(CourseGrade.term),
                selectinload(User.grades).selectinload(CourseGrade.course),
                # Load terms directly associated with the user
                selectinload(User.terms)
            )
        )
        result = await db.execute(stmt)
        # Use unique() before scalar to handle potential duplicate root entities from joins (good practice)
        user = result.unique().scalar_one_or_none()
        # --- End Fetch User ---

        if user is None:
            # Should not happen if token record is valid, but check defensively
            print(f"ERROR: Token record found but User ID {user_id} not in users table.")
            raise credentials_exception

        # Optional: Add debug logging to check if relationships were loaded
        print(f"DEBUG: User {user.id} fetched. Enrollments loaded: {len(user.enrollments) if hasattr(user, 'enrollments') else 'N/A'}")
        print(f"DEBUG: User {user.id} fetched. Grades loaded: {len(user.grades) if hasattr(user, 'grades') else 'N/A'}")
        print(f"DEBUG: User {user.id} fetched. Terms loaded: {len(user.terms) if hasattr(user, 'terms') else 'N/A'}")

        return user # Return the user object with relationships populated

    except jwt.ExpiredSignatureError:
        raise HTTPException( status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired", headers={"WWW-Authenticate": "Bearer"})
    except jwt.JWTError as e:
        print(f"DEBUG: JWTError in get_current_user: {e}")
        raise credentials_exception
    except Exception as e:
        # Catch potential int conversion error or other issues
        print(f"DEBUG: Unexpected error in get_current_user: {e}", exc_info=True) # Log traceback
        raise credentials_exception


# --- get_refresh_token_user (Corrected to use JTI) ---
async def get_refresh_token_user(
    token: str,
    db: AsyncSession # Removed Depends(get_db), assuming db is passed from route
) -> Tuple[User, int]:
    credentials_exception = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, jwt_settings.jwt_secret_key, algorithms=[jwt_settings.jwt_algorithm])
        token_payload = TokenPayload(**payload)
        if token_payload.type != "refresh": raise credentials_exception
        user_id_str: Optional[str] = token_payload.sub
        token_jti: Optional[str] = token_payload.jti
        if user_id_str is None or token_jti is None: raise credentials_exception
        user_id = int(user_id_str)

        token_record = await verify_token(db=db, token_jti=token_jti, token_type="refresh")
        if not token_record: print(f"DEBUG: No valid refresh token record found for JTI: {token_jti}"); raise credentials_exception
        if token_record.user_id != user_id: print(f"ERROR: Refresh token user ID mismatch"); raise credentials_exception

        # Fetch user - no eager loading needed typically for refresh
        user = await get_user_by_id(db, user_id)
        if user is None: raise credentials_exception
        return user, token_record.id

    except jwt.ExpiredSignatureError: raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has expired", headers={"WWW-Authenticate": "Bearer"})
    except jwt.JWTError as e: print(f"DEBUG: JWTError in get_refresh_token_user: {e}"); raise credentials_exception
    except Exception as e: print(f"DEBUG: Unexpected error in get_refresh_token_user: {e}", exc_info=True); raise credentials_exception


# --- get_user_by_id (Defined here if not reliably imported/used by services) ---
# Note: Keep the one imported from user_db.services if preferred
# async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
#     result = await db.execute(select(User).where(User.id == user_id))
#     return result.scalar_one_or_none()