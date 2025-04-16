# moodle_api/router.py
import logging
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from user_db.schemas import (
    CourseCreate,
    CourseOut,
    EnrollmentCreate,
    EnrollmentOut,
    TermCreate,
    TermOut,
    UserCreate,
    UserOut,
)
from user_db.services import (
    create_course,
    create_term,
    create_user,
    enroll_user_in_course,
    get_enrollments_by_user,
    get_terms_by_user,
    get_user_by_id,
    list_courses,
)
from .models import MoodleCredentials, SASCredentials
from .service import fetch_moodle_details, fetch_uwi_sas_details

from user_db.database import AsyncSessionLocal, get_db
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import text


# Optional: configure a logger specific to this module
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/moodle",  # All routes here will start with /moodle
    tags=["Moodle"],  # Group endpoints in Swagger UI
)


@router.post("/data", summary="Fetch Moodle Courses and Calendar Events")
async def get_moodle_data_endpoint(credentials: MoodleCredentials):
    """
    Logs into the UWI Mona VLE using provided credentials and retrieves:
    - User's name and email
    - Enrolled courses
    - Calendar events within the specified time range (defaults provided)
    """
    try:
        # Because fetch_moodle_details is synchronous but involves I/O,
        # FastAPI runs it in a threadpool when called from an async route.
        # No need to explicitly use run_in_threadpool here.
        data = fetch_moodle_details(credentials)
        logger.info(
            f"Successfully retrieved Moodle data for user {credentials.username[:3]}***"
        )
        return data
    except HTTPException as e:
        logger.warning(
            f"HTTPException fetching Moodle data for {credentials.username[:3]}***: {e.detail} (Status: {e.status_code})"
        )
        raise e  # Re-raise exceptions from the service layer
    except Exception as e:
        logger.exception(
            f"Unexpected error in /moodle/data endpoint for {credentials.username[:3]}***"
        )  # Log stack trace
        raise HTTPException(
            status_code=500, detail="Internal server error retrieving Moodle data."
        )


@router.post("/data-sas")
async def get_sas_data_endpoint(credentials: SASCredentials):
    """
    Logs into the UWI Mona SAS using provided credentials and retrieves:
    - Enrolled courses and their respective letter grades
    - GPA details - Semester GPA, Cumulative GPA To Date, Degree GPA To Date
    - Credits Earned To Date
    """
    try:
        data = fetch_uwi_sas_details(credentials)
        logger.info(
            f"Successfully retrieved Moodle data from SAS for user {credentials.username}***"
        )
        return data
    except HTTPException as e:
        logger.warning(
            f"HTTPException fetching Moodle data from SAS for {credentials.username}***: {e.detail} (Status: {e.status_code})"
        )
        raise e  # Re-raise exceptions from the service layer
    except Exception as e:
        logger.exception(
            f"Unexpected error in /moodle/data-sas endpoint for {credentials.username}***"
        )  # Log stack trace
        raise HTTPException(
            status_code=500, detail="Internal server error retrieving Moodle data."
        )


@router.get("/test-db")
async def test_db(session: AsyncSession = Depends(get_db)):
    result = await session.execute(text("SELECT 1"))
    return {"result": result.scalar()}


@router.post("/db/user", response_model=UserOut)
async def create_user_route(user: UserCreate, db: AsyncSession = Depends(get_db)):
    return await create_user(db, user)


@router.get("/db/user/{user_id}", response_model=UserOut)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/db/course", response_model=CourseOut)
async def create_course_route(course: CourseCreate, db: AsyncSession = Depends(get_db)):
    return await create_course(db, course)


@router.get("/db/course", response_model=List[CourseOut])
async def list_courses_route(db: AsyncSession = Depends(get_db)):
    return await list_courses(db)


@router.post("/db/term", response_model=TermOut)
async def create_term_route(term: TermCreate, db: AsyncSession = Depends(get_db)):
    return await create_term(db, term)


@router.get("/db/term/user/{user_id}", response_model=List[TermOut])
async def get_terms_route(user_id: int, db: AsyncSession = Depends(get_db)):
    return await get_terms_by_user(db, user_id)


@router.post("/db/enrollment", response_model=EnrollmentOut)
async def enroll_course_route(
    enroll: EnrollmentCreate, db: AsyncSession = Depends(get_db)
):
    return await enroll_user_in_course(db, enroll)


@router.get("/db/enrollment/user/{user_id}", response_model=List[EnrollmentOut])
async def list_user_enrollments(user_id: int, db: AsyncSession = Depends(get_db)):
    return await get_enrollments_by_user(db, user_id)
