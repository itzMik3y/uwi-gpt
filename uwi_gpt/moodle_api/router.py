# moodle_api/router.py
from datetime import datetime
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from user_db.schemas import (
    AdminCreate,
    AdminIn,
    AdminOut,
    AdminUpdate,
    BookingCreate,
    CourseCreate,
    CourseOut,
    EnrollmentCreate,
    EnrollmentOut,
    SlotBulkCreate,
    SlotOut,
    TermCreate,
    TermOut,
    UnbookRequest,
    UnbookResponse,
    UserCreate,
    UserOut,
    CourseGradeCreate,
    CourseGradeOut,
)
from user_db.services import (
    book_stu_slot,
    create_admin,
    create_bulk_availability_slots,
    create_course,
    create_term,
    create_user,
    delete_admin,
    enroll_user_in_course,
    get_admin_avail_slots,
    get_admin_by_id,
    get_all_admins,
    get_enrollments_by_user,
    get_stu_available_slots,
    get_terms_by_user,
    get_user_by_id,
    get_user_calendar_schedule,
    list_courses,
    get_course_by_id,
    get_term_by_user_and_code,
    create_or_update_course_grade,
    get_course_grades_by_user,
    get_course_grades_by_term,
    save_course_schedule,
    superadmin_required,
    unbook_stu_slot,
    update_admin,
)
from auth.utils import get_current_account
from auth.models import CourseScheduleOut
from .models import MoodleCredentials, SASCredentials
from .service import (
    # fetch_calendar_sas_info,
    fetch_calendar_sas_info,
    fetch_moodle_details,
    fetch_uwi_sas_details,
    fetch_extra_sas_info,
)
from sqlalchemy.orm import selectinload
from user_db.database import AsyncSessionLocal, get_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from user_db.models import Admin, User, Course, Term, EnrolledCourse, CourseGrade
import asyncio
from sqlalchemy import text
from user_db.models import Admin
from auth.utils import get_current_account
from fastapi import status
from user_db.schemas import (
    BookingWithStudentOut,
    SlotWithStudentOut,
    StudentOut,
    StudentBookingOut,
    AdminWithBookingOut,
)
from sqlalchemy.orm import joinedload
from user_db.services import get_student_bookings, get_admin_bookings
from pydantic import BaseModel
from typing import Any

# Optional: configure a logger specific to this module
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/moodle",  # All routes here will start with /moodle
    tags=["Moodle"],  # Group endpoints in Swagger UI
)


# Helper function to get or create a course
async def get_or_create_course(db: AsyncSession, course_data: CourseCreate) -> Course:
    """Check if a course exists by ID, if not create it"""
    # First check if the course exists
    existing_course = await get_course_by_id(db, course_data.id)
    if existing_course:
        return existing_course

    # If not, create it
    try:
        return await create_course(db, course_data)
    except Exception as e:
        # If there's an error (likely a duplicate key), try to get it again
        # This handles race conditions where course was created between our check and insert
        existing_course = await get_course_by_id(db, course_data.id)
        if existing_course:
            return existing_course
        raise e  # Re-raise if it's another issue


# Helper function to update or create a term
async def update_or_create_term(db: AsyncSession, term_data: TermCreate) -> Term:
    """Update existing term or create a new one"""
    try:
        existing_term = await get_term_by_user_and_code(
            db, term_data.user_id, term_data.term_code
        )

        if existing_term:
            # Update fields if provided
            if term_data.semester_gpa is not None:
                existing_term.semester_gpa = term_data.semester_gpa
            if term_data.cumulative_gpa is not None:
                existing_term.cumulative_gpa = term_data.cumulative_gpa
            if term_data.degree_gpa is not None:
                existing_term.degree_gpa = term_data.degree_gpa
            if term_data.credits_earned_to_date is not None:
                existing_term.credits_earned_to_date = term_data.credits_earned_to_date

            await db.commit()
            await db.refresh(existing_term)
            return existing_term
        else:
            # Create new term
            term = Term(**term_data.dict())
            db.add(term)
            await db.commit()
            await db.refresh(term)
            return term
    except Exception as e:
        logger.error(f"Error updating/creating term: {e}")
        # Rollback in case of error
        await db.rollback()
        raise e


# Helper function to check if enrollment exists
async def get_enrollment(
    db: AsyncSession, user_id: int, course_id: int, term_id: int
) -> Optional[EnrolledCourse]:
    """Check if enrollment exists"""
    result = await db.execute(
        select(EnrolledCourse).where(
            EnrolledCourse.user_id == user_id,
            EnrolledCourse.course_id == course_id,
            EnrolledCourse.term_id == term_id,
        )
    )
    return result.scalar_one_or_none()


@router.post("/login", summary="Fetch Moodle Courses and optionally SAS Grades")
async def get_moodle_data_endpoint(
    credentials: MoodleCredentials,
    fetch_grades: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """
    If the user exists, return their stored courses & grades & calendar_info.
    Otherwise, scrape Moodle (+ SAS) in parallel, upsert to the DB, and return everything.
    """

    # 1) Short‑circuit: try to load user + all relations in one go
    q = (
        select(User)
        .where(User.student_id == credentials.username)
        .options(
            selectinload(User.enrollments).selectinload(EnrolledCourse.course),
            selectinload(User.grades).selectinload(CourseGrade.course),
            selectinload(User.terms),
        )
    )
    result = await db.execute(q)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        # build moodle_data from enrollments
        courses = [
            {
                "id": e.course.id,
                "fullname": e.course.fullname,
                "shortname": e.course.shortname,
                "idnumber": e.course.idnumber,
                "summary": e.course.summary,
                "summaryformat": e.course.summaryformat,
                "startdate": e.course.startdate,
                "enddate": e.course.enddate,
                "visible": e.course.visible,
                "showactivitydates": e.course.showactivitydates,
                "showcompletionconditions": e.course.showcompletionconditions,
                "fullnamedisplay": e.course.fullnamedisplay,
                "viewurl": e.course.viewurl,
                "coursecategory": e.course.coursecategory,
            }
            for e in existing_user.enrollments
        ]
        moodle_data = {
            "user_info": {
                "name": f"{existing_user.firstname} {existing_user.lastname}",
                "email": existing_user.email,
                "student_id": existing_user.student_id,
            },
            "courses": {"courses": courses, "nextoffset": None},
            "calendar_events": {"events": [], "firstid": None, "lastid": None},
            "auth_tokens": {},
        }

        # build grades_data from historical grades
        terms_payload = []
        all_grades = existing_user.grades
        for t in existing_user.terms:
            term_courses = [
                {
                    "course_code": g.course_code,
                    "course_title": g.course_title,
                    "credit_hours": g.credit_hours,
                    "grade_earned": g.grade_earned,
                    "whatif_grade": g.whatif_grade,
                }
                for g in all_grades
                if g.term_id == t.id
            ]
            terms_payload.append(
                {
                    "term_code": t.term_code,
                    "courses": term_courses,
                    "semester_gpa": t.semester_gpa,
                    "cumulative_gpa": t.cumulative_gpa,
                    "degree_gpa": t.degree_gpa,
                    "credits_earned_to_date": t.credits_earned_to_date,
                }
            )

        overall = {}
        if terms_payload:
            recent = terms_payload[0]
            overall = {
                "cumulative_gpa": recent["cumulative_gpa"],
                "degree_gpa": recent["degree_gpa"],
                "total_credits_earned": recent["credits_earned_to_date"],
            }

        grades_data = {
            "success": True,
            "data": {
                "student_name": moodle_data["user_info"]["name"],
                "student_id": moodle_data["user_info"]["student_id"],
                "terms": terms_payload,
                "overall": overall,
            },
        }
        grades_status = {"fetched": False, "success": True, "error": None}

        return {
            "moodle_data": moodle_data,
            "grades_status": grades_status,
            "grades_data": grades_data,
        }

    # 2) First‑time user: scrape Moodle & SAS in parallel
    try:
        moodle_task = asyncio.to_thread(fetch_moodle_details, credentials)
        sas_task = None
        if fetch_grades:
            sas_creds = SASCredentials(
                username=credentials.username, password=credentials.password
            )
            sas_task = asyncio.to_thread(fetch_uwi_sas_details, sas_creds)

        if sas_task:
            moodle_payload, sas_payload = await asyncio.gather(moodle_task, sas_task)
        else:
            moodle_payload = await moodle_task
            sas_payload = None

        # a) create user
        u = moodle_payload["user_info"]
        new_user = await create_user(
            db,
            UserCreate(
                firstname=u["name"].split(" ", 1)[0],
                lastname=(u["name"].split(" ", 1)[1] if " " in u["name"] else ""),
                email=u["email"],
                student_id=u["student_id"],
                password=credentials.password,
            ),
        )
        user_id = new_user.id

        # b) placeholder “CURRENT” term
        current_term = await update_or_create_term(
            db,
            TermCreate(
                term_code="CURRENT",
                user_id=user_id,
                semester_gpa=None,
                cumulative_gpa=None,
                degree_gpa=None,
                credits_earned_to_date=None,
            ),
        )

        # c) upsert courses & enrollments
        for c in moodle_payload["courses"]["courses"]:
            course = await get_or_create_course(
                db,
                CourseCreate(
                    id=c["id"],
                    fullname=c["fullname"],
                    shortname=c.get("shortname", ""),
                    idnumber=c.get("idnumber", ""),
                    summary=c.get("summary", ""),
                    summaryformat=c.get("summaryformat", 1),
                    startdate=c.get("startdate", 0),
                    enddate=c.get("enddate", 0),
                    visible=bool(c.get("visible", False)),
                    showactivitydates=bool(c.get("showactivitydates", False)),
                    showcompletionconditions=bool(
                        c.get("showcompletionconditions", False)
                    ),
                    fullnamedisplay=c.get("fullnamedisplay", c["fullname"]),
                    viewurl=c.get("viewurl", ""),
                    coursecategory=c.get("coursecategory", ""),
                ),
            )
            if not await enroll_user_in_course(
                db,
                EnrollmentCreate(
                    user_id=user_id,
                    course_id=course.id,
                    term_id=current_term.id,
                    course_code=c.get("shortname", ""),
                    course_title=c["fullname"],
                    credit_hours=3.0,
                ),
            ):
                # create if not exists
                pass

        # d) upsert SAS grades
        grades_payload = None
        if sas_payload and sas_payload.get("success"):
            grades_payload = sas_payload
            for term in sas_payload["data"]["terms"]:
                term_rec = await update_or_create_term(
                    db,
                    TermCreate(
                        term_code=term["term_code"],
                        user_id=user_id,
                        semester_gpa=term.get("semester_gpa"),
                        cumulative_gpa=term.get("cumulative_gpa"),
                        degree_gpa=term.get("degree_gpa"),
                        credits_earned_to_date=term.get("credits_earned_to_date"),
                    ),
                )
                for g in term["courses"]:
                    cid = -abs(hash(g["course_code"]) % 1_000_000)
                    course = await get_or_create_course(
                        db,
                        CourseCreate(
                            id=cid,
                            fullname=g.get("course_title", ""),
                            shortname=g.get("course_code", ""),
                            idnumber=g.get("course_code", ""),
                            summary="Imported from SAS",
                            summaryformat=1,
                            startdate=0,
                            enddate=0,
                            visible=True,
                            showactivitydates=False,
                            showcompletionconditions=False,
                            fullnamedisplay=g.get("course_title", ""),
                            viewurl="",
                            coursecategory="",
                        ),
                    )
                    await create_or_update_course_grade(
                        db,
                        CourseGradeCreate(
                            user_id=user_id,
                            course_id=course.id,
                            term_id=term_rec.id,
                            course_code=g.get("course_code", ""),
                            course_title=g.get("course_title", ""),
                            credit_hours=g.get("credit_hours", 0.0),
                            grade_earned=g.get("grade_earned"),
                            whatif_grade=g.get("whatif_grade"),
                            is_historical=True,
                            earned_date=None,
                        ),
                    )

        # e) return CombinedLoginResponse shape
        return {
            "moodle_data": moodle_payload,
            "grades_status": {
                "fetched": fetch_grades,
                "success": bool(grades_payload),
                "error": None if grades_payload else "No grades fetched",
            },
            "grades_data": grades_payload,
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in first‑time /moodle/login flow")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/db/grades/user/{user_id}", response_model=List[CourseGradeOut])
async def get_user_grades(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get all historical course grades for a user"""
    return await get_course_grades_by_user(db, user_id)


@router.get(
    "/db/grades/user/{user_id}/term/{term_id}", response_model=List[CourseGradeOut]
)
async def get_user_term_grades(
    user_id: int, term_id: int, db: AsyncSession = Depends(get_db)
):
    """Get all historical course grades for a user for a specific term"""
    return await get_course_grades_by_term(db, user_id, term_id)


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


@router.post("/extra-sas", summary="Fetch extra sas info")
async def get_extra_sas_info_endpoint(
    credentials: SASCredentials,
):
    """
    Fetch extra SAS info using the provided credentials.
    """
    try:
        data = fetch_extra_sas_info(credentials)
        return {
            "data": data,
        }
    except Exception as e:
        logger.error(f"Error fetching extra SAS info: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/calendar-sas", summary="Fetch course calendar from SAS")
async def get_calendar_info_sas_endpoint(
    credentials: SASCredentials,
):
    """
    Fetch calendar SAS info using the provided credentials.
    """
    try:
        data = fetch_calendar_sas_info(credentials)
        return {
            "data": data,
        }
    except Exception as e:
        logger.error(f"Error fetching calendar SAS info: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# SCHEDULING ROUTES
@router.post("/scheduler/slots", response_model=List[SlotOut])
async def create_slot(
    data: SlotBulkCreate,
    current_account: Admin = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
    current_admin: User | Admin = Depends(get_current_account),
):
    # Verify that the current account is an admin
    if not isinstance(current_account, Admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can create availability slots",
        )

    # Automatically set the admin_id from the authenticated account
    data.admin_id = current_account.id

    return await create_bulk_availability_slots(db, data, current_admin.id)


@router.post("/scheduler/bookings")
async def book_slot(
    data: BookingCreate,
    db: AsyncSession = Depends(get_db),
    current_student: User | Admin = Depends(get_current_account),
):
    try:

        return await book_stu_slot(db, data.slot_id, current_student.id)
    except ValueError as e:
        # Catch the ValueError and return it as an HTTP exception with the message
        logger.error(f"Error booking slot: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error booking slot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/scheduler/bookings", response_model=UnbookResponse)
async def unbook_slot(data: UnbookRequest, db: AsyncSession = Depends(get_db)):
    return await unbook_stu_slot(db, data.slot_id, data.student_id)


@router.get("/scheduler/slots/available")
async def available_slots(db: AsyncSession = Depends(get_db)):
    return await get_stu_available_slots(db)


@router.get("/scheduler/admin/slots", response_model=List[SlotOut])
async def admin_slots(
    current_account: Admin = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    # Verify that the current account is an admin
    if not isinstance(current_account, Admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view their availability slots",
        )

    # Use the admin_id from the authenticated account
    return await get_admin_avail_slots(db, current_account.id)


# SUPERADMIN ROUTE
@router.post("/admin/create_admin")
async def create_superadmin_for_db(
    adminData: AdminIn,
    db: AsyncSession = Depends(get_db),
):
    await superadmin_required(db, adminData.requesting_admin_id)
    return await create_admin(
        db,
        AdminCreate(
            firstname=adminData.firstname,
            lastname=adminData.lastname,
            email=adminData.email,
            password=adminData.password,
            is_superadmin=adminData.is_superadmin,
            login_id=adminData.login_id,
        ),
    )


# ADMIN CRUD ROUTES


# Create an Admin
@router.post("/admin", response_model=AdminOut)
async def create_admin_for_db(admin: AdminCreate, db: AsyncSession = Depends(get_db)):
    try:
        created_admin = await create_admin(db, admin)
        return created_admin
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Get all Admins
@router.get("/admin", response_model=List[AdminOut])
async def list_admins(db: AsyncSession = Depends(get_db)):
    return await get_all_admins(db)


# Get one Admin
@router.get("/admin/{admin_id}", response_model=AdminOut)
async def get_admin(admin_id: int, db: AsyncSession = Depends(get_db)):
    admin = await get_admin_by_id(db, admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    return admin


# Update an Admin
@router.put("/admin/{admin_id}", response_model=AdminOut)
async def update_admin_to_db(
    admin_id: int, updates: AdminUpdate, db: AsyncSession = Depends(get_db)
):
    updated_admin = await update_admin(db, updates, admin_id)
    if not updated_admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    return updated_admin


# Delete an Admin
@router.delete("/admin/{admin_id}")
async def delete_admin_from_db(admin_id: int, db: AsyncSession = Depends(get_db)):
    deleted_admin = await delete_admin(db, admin_id)
    if not deleted_admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    return {"message": "Admin deleted successfully"}


# CALENDAR ROUTES
@router.get(
    "/calendar-courses",
    response_model=CourseScheduleOut,
    summary="Get course schedule from DB",
)
async def get_my_schedule(
    current_user: User | Admin = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    return await get_user_calendar_schedule(current_user.id, db)


@router.get("/scheduler/bookings/student", response_model=List[StudentBookingOut])
async def get_student_booking_slots(
    current_user: User | Admin = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """Get all bookings made by the current student"""
    # Verify that this is a student (User instance, not Admin)
    if isinstance(current_user, Admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is for students only",
        )

    return await get_student_bookings(db, current_user.id)


@router.get("/scheduler/bookings/admin", response_model=List[SlotWithStudentOut])
async def get_admin_booking_details(
    current_user: User | Admin = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    """Get all booked slots with student details for an admin"""
    # Verify that this is an admin
    if not isinstance(current_user, Admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is for admins only",
        )

    return await get_admin_bookings(db, current_user.id)


class UnbookSlotClientRequest(BaseModel):
    slot_id: int


# replace your existing DELETE /scheduler/bookings
@router.delete(
    "/scheduler/bookings/{slot_id}",
    response_model=UnbookResponse,
    summary="Cancel a student booking",
)
async def unbook_slot(
    slot_id: int,
    current_student: User = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    return await unbook_stu_slot(db, slot_id, current_student.id)
