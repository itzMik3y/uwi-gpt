# auth/router.py (Combined Login/Register with Synchronous Data Saving)

import logging
import asyncio
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status, Request, Body
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# --- Required Auth Imports ---
from jose import jwt, JWTError
from .config import jwt_settings

# --- Database and User DB Components ---
from user_db.database import get_db
from user_db.models import User, Admin

# v-- Import DB Schemas from user_db.schemas --v
from user_db.schemas import (
    AdminTokenOut,
    UserOut,
    UserTokenOut,
    UserCreate,
)
from user_db.services import (
    blacklist_admin_token,
    blacklist_all_admin_tokens,
    create_user,
    get_admin_active_tokens,
    verify_admin_token,
    verify_token as db_verify_token,
    blacklist_token,
    get_user_active_tokens,
    blacklist_all_user_tokens,
)

# --- Auth Models & Utils ---
# v-- Import Auth/Response Models from auth.models --v
from .models import (
    AdminInfoOut,
    AdminMeResponse,
    BookingOut,
    SlotOut,
    StudentOut,
    Token,
    RefreshRequest,
    TokenPayload,
    LoginRequest,  # Auth workflow models
    MeResponse,
    MoodleDataOut,
    GradesDataOut,
    GradesStatusOut,  # Complex response models
    UserInfoOut,
    MoodleCoursesWrapperOut,
    TermGradesOut,
    CourseOutMinimal,
    CourseGradeOutMinimal,
)

# v-- Import Auth Utils --v
from .utils import (
    create_access_token,
    create_refresh_token,
    get_current_account,
    get_refresh_token_subject,
    verify_password,
    # authenticate_user, # Removed as requested
    oauth2_scheme,
)

# --- Moodle/SAS Components ---
from moodle_api.service import (
    fetch_moodle_details,
    fetch_uwi_sas_details,
    save_initial_scraped_data,
)
from moodle_api.models import MoodleCredentials, SASCredentials

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)

# OAuth2 scheme instance specifically for logout dependency if needed directly
oauth2_scheme_direct = OAuth2PasswordBearer(tokenUrl="/auth/token")  # Use relative path

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Tuple
from .utils import verify_password


# --- Helper: Check Admin Credentials ---
async def check_admin_credentials(
    db: AsyncSession, login_id_or_email: str, password: str
) -> Tuple[Optional[Admin], str]:
    """
    Checks credentials against Admin table.
    Returns: (Admin, "SUCCESS"), (None, "NOT_FOUND_LOGIN_ID"),
             (Admin, "WRONG_PASSWORD"), (None, "NOT_FOUND_EMAIL")
    """
    admin: Optional[Admin] = None
    is_email_lookup = "@" in login_id_or_email

    if is_email_lookup:
        result = await db.execute(select(Admin).where(Admin.email == login_id_or_email))
        admin = result.scalar_one_or_none()
    else:
        result = await db.execute(
            select(Admin).where(Admin.login_id == int(login_id_or_email))
        )
        admin = result.scalar_one_or_none()

    if not admin:
        return None, "NOT_FOUND_LOGIN_ID" if not is_email_lookup else "NOT_FOUND_EMAIL"

    if not verify_password(password, admin.password_hash):
        return admin, "WRONG_PASSWORD"

    return admin, "SUCCESS"


# --- Helper: Check DB Credentials (Defined Locally) ---
async def check_user_credentials(
    db: AsyncSession, username: str, password: str
) -> Tuple[Optional[User], str]:
    """
    Checks credentials against DB.
    Returns: (User, "SUCCESS"), (None, "NOT_FOUND_STUDENT_ID"),
             (User, "WRONG_PASSWORD"), (None, "NOT_FOUND_EMAIL")
    """
    user: Optional[User] = None
    is_email_lookup = "@" in username

    if is_email_lookup:
        result = await db.execute(select(User).where(User.email == username))
        user = result.scalar_one_or_none()
    else:
        result = await db.execute(select(User).where(User.student_id == username))
        user = result.scalar_one_or_none()

    if not user:
        return None, (
            "NOT_FOUND_STUDENT_ID" if not is_email_lookup else "NOT_FOUND_EMAIL"
        )

    # verify_password should be imported from .utils
    if not verify_password(password, user.password_hash):
        return user, "WRONG_PASSWORD"

    return user, "SUCCESS"


# --- Combined Login/Register Token Endpoint (Synchronous Data Saving) ---
@router.post(
    "/token", response_model=Token, summary="Login or Register (Populates Data Sync)"
)
async def login_or_register_token(
    request: Request,
    # background_tasks: BackgroundTasks, # REMOVED
    db: AsyncSession = Depends(get_db),
    login_data: LoginRequest = Body(...),
):
    """
    Authenticates against DB. If user not found by student_id,
    scrapes Moodle/SAS, creates user, SAVES scraped data synchronously,
    and returns JWT tokens. Can be slow on first login.
    """
    username = login_data.username
    password = login_data.password
    user_for_token: Optional[User] = None

    # --- Step 1: Try DB Authentication ---
    user, auth_status = await check_user_credentials(db, username, password)

    if auth_status == "SUCCESS":
        logger.info(f"DB Authentication successful for user: {username}")
        user_for_token = user

    elif auth_status in ["WRONG_PASSWORD", "NOT_FOUND_EMAIL"]:
        logger.warning(f"DB Authentication failed ({auth_status}) for user: {username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    elif auth_status == "NOT_FOUND_STUDENT_ID":
        logger.info(
            f"User student_id {username} not found. Starting scrape, registration, and data population."
        )
        # --- Step 2: Scrape, Create User, Save Data ---
        moodle_payload = None
        sas_payload = None
        try:
            if "@" in username:
                # This state should ideally not be reached if check_user_credentials works
                logger.error(
                    "Logic error: Trying Moodle auth with email when user not found by student ID"
                )
                raise HTTPException(
                    status_code=500, detail="Internal Server Error: Invalid state."
                )

            # --- Run Scrapes Concurrently ---
            moodle_creds = MoodleCredentials(username=username, password=password)
            sas_creds = SASCredentials(username=username, password=password)
            logger.info(f"Starting concurrent Moodle and SAS scrape for {username}")
            moodle_task = asyncio.to_thread(fetch_moodle_details, moodle_creds)
            sas_task = asyncio.to_thread(fetch_uwi_sas_details, sas_creds)
            results = await asyncio.gather(
                moodle_task, sas_task, return_exceptions=True
            )
            logger.info(f"Finished concurrent scrape for {username}")

            moodle_payload = (
                results[0] if not isinstance(results[0], Exception) else None
            )
            sas_payload = results[1] if not isinstance(results[1], Exception) else None

            # --- Handle Moodle Failure (Critical) ---
            if (
                isinstance(results[0], Exception)
                or not moodle_payload
                or not moodle_payload.get("user_info")
            ):
                err_info = (
                    results[0]
                    if isinstance(results[0], Exception)
                    else "Missing user_info"
                )
                logger.error(
                    f"Moodle fetch failed or missing user_info for {username}",
                    exc_info=err_info if isinstance(err_info, Exception) else None,
                )
                if isinstance(results[0], HTTPException):
                    # Re-raise specific HTTP errors (like 401 from Moodle)
                    raise HTTPException(
                        status_code=results[0].status_code,
                        detail=f"External authentication failed: {results[0].detail}",
                    )
                # Generic error for other Moodle exceptions or missing info
                raise HTTPException(
                    status_code=502,
                    detail="Failed to fetch required data from external service (Moodle).",
                )

            # --- Handle SAS Failure (Non-critical, just log warning) ---
            if isinstance(results[1], Exception):
                logger.warning(
                    f"SAS fetch failed for {username} during registration: {results[1]}",
                    exc_info=results[1],
                )
                sas_payload = None
            elif sas_payload and not sas_payload.get("success"):
                logger.warning(
                    f"SAS fetch unsuccessful for {username} during registration: {sas_payload.get('message')}"
                )
                sas_payload = None

            # --- Create User ---
            user_info = moodle_payload["user_info"]
            scraped_student_id = user_info.get("student_id", username)
            email = user_info.get("email")
            full_name = user_info.get("name", "")
            first_name = full_name.split(" ", 1)[0] if full_name else "Unknown"
            last_name = full_name.split(" ", 1)[1] if " " in full_name else ""
            if not email:
                raise HTTPException(
                    status_code=502,
                    detail="Could not retrieve email from external service.",
                )

            # Check concurrent creation again
            result_check = await db.execute(
                select(User).where(
                    (User.student_id == scraped_student_id) | (User.email == email)
                )
            )
            if result_check.scalar_one_or_none():
                raise HTTPException(
                    status_code=409,
                    detail="Account conflict. Please try logging in again.",
                )

            user_create_data = UserCreate(
                firstname=first_name,
                lastname=last_name,
                email=email,
                student_id=scraped_student_id,
                password=password,
            )
            # Assumes create_user adds to session, commit happens later via Depends(get_db) or explicitly
            new_user = await create_user(db, user_create_data)
            logger.info(f"User {new_user.student_id} created (pending commit).")

            # --- SAVE SCRAPED DATA (Synchronously) ---
            logger.info(
                f"Attempting to save initial scraped data for new user {new_user.id}"
            )
            # Pass the *same db session* to the saving function
            await save_initial_scraped_data(
                db, new_user.id, moodle_payload, sas_payload
            )
            logger.info(
                f"Successfully processed initial scraped data for new user {new_user.id} (pending commit)."
            )

            user_for_token = new_user  # Ready for token generation

        except (
            HTTPException
        ) as http_exc:  # Catch errors from scrape or user creation checks
            await db.rollback()  # Rollback the transaction on any HTTP error
            raise http_exc
        except (
            ValueError
        ) as data_save_exc:  # Catch specific error from save_initial_scraped_data
            logger.error(
                f"Data saving failed for new user {username}: {data_save_exc}",
                exc_info=True,
            )
            await db.rollback()  # Rollback transaction (including user creation)
            raise HTTPException(
                status_code=500,
                detail=f"Account created but failed to save initial data: {data_save_exc}",
            )
        except Exception as ext_exc:  # Catch other unexpected errors
            logger.error(
                f"Error during external auth/scrape/create/save for {username}: {ext_exc}",
                exc_info=True,
            )
            await db.rollback()  # Rollback transaction
            raise HTTPException(
                status_code=502,
                detail="An error occurred processing external information or saving initial data.",
            )
    else:
        # Should be unreachable
        logger.error(f"Invalid auth_status encountered: {auth_status}")
        await db.rollback()  # Rollback just in case
        raise HTTPException(
            status_code=500, detail="Internal Server Error during authentication."
        )

    # --- Step 3: Generate Tokens ---
    if not user_for_token:
        # This ensures user_for_token is assigned if flow continues
        logger.error(
            f"Token generation step reached without a user object for {username}"
        )
        raise HTTPException(
            status_code=500, detail="Internal server error during authentication flow."
        )

    access_token_payload = {"sub": str(user_for_token.id)}
    access_token, expires_at, _ = await create_access_token(
        access_token_payload, db=db, request=request
    )
    refresh_token_payload = {"sub": str(user_for_token.id)}
    refresh_token, _, _ = await create_refresh_token(
        refresh_token_payload, db=db, request=request
    )

    # Final commit is handled by Depends(get_db) context manager upon successful function exit
    logger.info(f"Tokens generated successfully for user {user_for_token.student_id}")
    return Token(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


@router.post(
    "/admin/token", response_model=Token, summary="Admin Login (No External Scraping)"
)
async def admin_login_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
    login_data: LoginRequest = Body(...),
):
    """
    Authenticates an admin via login_id or email.
    If successful, returns access and refresh tokens.
    """
    login_id_or_email = login_data.username
    password = login_data.password

    admin, auth_status = await check_admin_credentials(db, login_id_or_email, password)

    if auth_status == "SUCCESS":
        logger.info(f"Admin login successful for: {login_id_or_email}")
    elif auth_status in ["WRONG_PASSWORD", "NOT_FOUND_EMAIL", "NOT_FOUND_LOGIN_ID"]:
        logger.warning(f"Admin login failed ({auth_status}) for: {login_id_or_email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    else:
        logger.error(f"Unhandled admin auth status: {auth_status}")
        raise HTTPException(
            status_code=500, detail="Internal Server Error during admin authentication."
        )

    # Generate tokens
    access_token_payload = {"sub": f"admin-{admin.id}"}
    access_token, expires_at, _ = await create_access_token(
        access_token_payload, db=db, request=request
    )

    refresh_token_payload = {"sub": f"admin-{admin.id}"}
    refresh_token, _, _ = await create_refresh_token(
        refresh_token_payload, db=db, request=request
    )

    logger.info(f"Tokens issued for admin {admin.login_id}")
    return Token(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


# --- Other Authentication Routes (/refresh, /logout, /me, etc.) ---
# Keep these as previously corrected (using JTI logic)


@router.post(
    "/refresh", response_model=Token, summary="Refresh Access Token (User/Admin)"
)
async def refresh_access_token(
    request: Request, refresh_data: RefreshRequest, db: AsyncSession = Depends(get_db)
):
    # This function should parse the refresh token and return (user_or_admin, token_id_to_blacklist)
    subject, token_id_to_blacklist, role = await get_refresh_token_subject(
        refresh_data.refresh_token, db
    )

    if role == "admin":
        await blacklist_admin_token(db, token_id_to_blacklist)
    else:
        # Assuming this is a user token
        await blacklist_token(db, token_id_to_blacklist)

    # Distinguish admin vs user based on subject prefix
    if role == "admin":
        result = await db.execute(select(Admin).where(Admin.id == subject.id))
        admin = result.scalar_one_or_none()
        if not admin:
            raise HTTPException(status_code=404, detail="Admin not found")

        access_token_payload = {"sub": f"admin-{admin.id}"}
        refresh_token_payload = {"sub": f"admin-{admin.id}"}

    else:
        result = await db.execute(select(User).where(User.id == subject.id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        access_token_payload = {"sub": str(user.id)}
        refresh_token_payload = {"sub": str(user.id)}

    new_access_token, new_expires_at, _ = await create_access_token(
        access_token_payload, db=db, request=request
    )
    new_refresh_token, _, _ = await create_refresh_token(
        refresh_token_payload, db=db, request=request
    )

    return Token(
        access_token=new_access_token,
        token_type="bearer",
        refresh_token=new_refresh_token,
        expires_at=new_expires_at,
    )


@router.post("/logout")
async def logout(
    db: AsyncSession = Depends(get_db),
    current_user: User | Admin = Depends(get_current_account),
    token: str = Depends(oauth2_scheme_direct),
):
    try:
        payload = jwt.decode(
            token, jwt_settings.jwt_secret_key, algorithms=[jwt_settings.jwt_algorithm]
        )
        token_payload = TokenPayload(**payload)
        token_jti = token_payload.jti
        if token_jti:
            is_admin = token_payload.sub.startswith("admin-")

            if is_admin:
                print(f"Admin token JTI: {token_jti}")
                token_record = await verify_admin_token(
                    db=db, token_jti=token_jti, token_type="access"
                )
            else:
                token_record = await db_verify_token(
                    db=db, token_jti=token_jti, token_type="access"
                )  # Use renamed import

            if token_record:
                if is_admin:
                    await blacklist_admin_token(db, token_record.id)
                    logger.info(f"Admin {current_user.id} logged out.")

                else:
                    await blacklist_token(db, token_record.id)
                    logger.info(f"User {current_user.id} logged out.")
                return {"message": "Successfully logged out"}
            else:
                logger.warning(
                    f"Logout user {current_user.id}, token record not found JTI {token_jti}"
                )
                return {"message": "Logout processed (token invalid)."}
        else:
            logger.error(f"Logout user {current_user.id}, token JTI missing.")
            raise HTTPException(status_code=400, detail="Invalid token format.")
    except JWTError as e:
        logger.error(f"JWTError logout user {current_user.id}: {e}")
        raise HTTPException(status_code=401, detail="Invalid token.")


@router.post("/logout-all")
async def logout_all_devices(
    db: AsyncSession = Depends(get_db),
    current_user: User | Admin = Depends(get_current_account),
):
    if isinstance(current_user, Admin):
        count = await blacklist_all_admin_tokens(db, current_user.id)
        logger.info(
            f"Admin {current_user.id} logged out all devices ({count} sessions)."
        )

    else:
        count = await blacklist_all_user_tokens(db, current_user.id)
        logger.info(
            f"User {current_user.id} logged out all devices ({count} sessions)."
        )
    return {"message": f"Successfully logged out ({count} sessions)."}


@router.get(
    "/me", response_model=MeResponse, summary="Get Authenticated User's DB Data"
)
async def read_users_me_structured(
    # get_current_account now loads relations
    current_user: User | Admin = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),  # Keep db if needed for extra queries
):
    """
    Get database-stored details for the currently authenticated user,
    structured similarly to the /moodle/login response.

    NOTE: Does NOT include live data like Moodle calendar events or auth tokens.
    """
    try:
        # 1. Prepare moodle_data structure
        user_info = UserInfoOut(
            name=f"{current_user.firstname} {current_user.lastname}",
            email=current_user.email,
            student_id=current_user.student_id,
            majors=current_user.majors,
            minors=current_user.minors,
            faculty=current_user.faculty,
        )
        # Extract current courses from enrollments relationship
        # Assumes enrollments linked to "CURRENT" term are the ones to show here
        # Or adjust logic based on how you store/identify current Moodle courses
        moodle_courses_list = []
        for enrollment in current_user.enrollments:
            # You might add a filter here, e.g., if enrollment.term.term_code == "CURRENT":
            if enrollment.course:  # Check if course data was loaded
                moodle_courses_list.append(CourseOutMinimal.from_orm(enrollment.course))

        moodle_courses_wrapper = MoodleCoursesWrapperOut(
            courses=moodle_courses_list, nextoffset=None
        )

        moodle_data = MoodleDataOut(
            user_info=user_info,
            courses=moodle_courses_wrapper,
            # Exclude calendar_events and auth_tokens
        )

        # 2. Prepare grades_data structure
        terms_payload = []
        # Sort terms if necessary (e.g., reverse chronologically)
        # Assuming terms are already loaded via relationship, sort them here if needed
        sorted_terms = sorted(
            current_user.terms, key=lambda t: t.term_code, reverse=True
        )

        # Group grades by term_id for easier lookup
        grades_by_term_id = {}
        for grade in current_user.grades:
            if grade.term_id not in grades_by_term_id:
                grades_by_term_id[grade.term_id] = []
            # Ensure grade data is suitable for CourseGradeOutMinimal
            grades_by_term_id[grade.term_id].append(
                CourseGradeOutMinimal.from_orm(grade)
            )

        for term in sorted_terms:
            term_courses = grades_by_term_id.get(term.id, [])
            terms_payload.append(
                TermGradesOut(
                    term_code=term.term_code,
                    courses=term_courses,
                    semester_gpa=term.semester_gpa,
                    cumulative_gpa=term.cumulative_gpa,
                    degree_gpa=term.degree_gpa,
                    credits_earned_to_date=term.credits_earned_to_date,
                )
            )

        # Calculate overall GPA/Credits from the most recent term found
        overall = {}
        if terms_payload:
            # Assumes terms_payload[0] is the most recent due to sorting
            recent = terms_payload[0]
            overall = {
                "cumulative_gpa": recent.cumulative_gpa,
                "degree_gpa": recent.degree_gpa,
                "total_credits_earned": recent.credits_earned_to_date,
            }

        grades_data = GradesDataOut(
            student_name=user_info.name,
            student_id=user_info.student_id,
            terms=terms_payload,
            overall=overall,
        )

        # 3. Prepare grades_status (Indicates data is from DB, not fresh scrape)
        grades_status = GradesStatusOut(
            fetched=False,  # False because we didn't fetch live from SAS here
            success=True,  # True because we successfully retrieved DB data
            error=None,
        )

        # 4. Combine into the final response
        return MeResponse(
            moodle_data=moodle_data,
            grades_status=grades_status,
            grades_data=grades_data,
        )
    except Exception as e:
        logger.error(
            f"Error structuring /me response for user {current_user.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Error processing user data.")


@router.get(
    "/admin/me",
    response_model=AdminMeResponse,
    summary="Get Authenticated Admin's DB Data",
)
async def read_admin_me(
    current_admin: User | Admin = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """
    Get structured admin data including slots, bookings, and student info.
    """
    try:
        # 1. Admin basic info
        admin_info = AdminInfoOut(
            name=f"{current_admin.firstname} {current_admin.lastname}",
            email=current_admin.email,
            is_superadmin=current_admin.is_superadmin,
        )

        # 2. Prepare slot + booking data
        slots_payload = []
        for slot in current_admin.slots:
            booking = None
            if slot.booking and slot.booking.student:
                student = slot.booking.student
                booking = BookingOut(
                    id=slot.booking.id,
                    created_at=slot.booking.created_at,
                    student=StudentOut(
                        id=student.id,
                        name=f"{student.firstname} {student.lastname}",
                        email=student.email,
                        student_id=student.student_id,
                    ),
                )

            slots_payload.append(
                SlotOut(
                    id=slot.id,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                    is_booked=slot.is_booked,
                    booking=booking,
                )
            )

        return AdminMeResponse(
            admin_info=admin_info,
            slots=slots_payload,
        )
    except Exception as e:
        logger.error(
            f"Error structuring /admin/me response for admin {current_admin.id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Error processing admin data.")


@router.get("/sessions", response_model=List[UserTokenOut])
async def get_active_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User | Admin = Depends(get_current_account),
):
    sessions = await get_user_active_tokens(db, current_user.id)
    return sessions


@router.get("/admin/sessions", response_model=List[AdminTokenOut])
async def get_active_admin_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User | Admin = Depends(get_current_account),
):
    sessions = await get_admin_active_tokens(db, current_user.id)
    return sessions
