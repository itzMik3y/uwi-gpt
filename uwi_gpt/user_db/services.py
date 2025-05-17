from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from dateutil import parser as date_parser
from fastapi import APIRouter, HTTPException, Depends
from collections import defaultdict
from auth.models import (
    CalendarCourseOut,
    CourseSchedule,
    CourseScheduleOut,
    SessionDBOut,
)
from .models import (
    Admin,
    AdminToken,
    AvailabilitySlot,
    Booking,
    Calendar_Course,
    Calendar_Section,
    Calendar_Session,
    Course,
    EnrolledCourse,
    Term,
    User,
    CourseGrade,
    User_Session,
)
from .schemas import (
    AdminCreate,
    AdminTokenCreate,
    AdminUpdate,
    CourseCreate,
    EnrollmentCreate,
    SlotBulkCreate,
    TermCreate,
    UserCreate,
    CourseGradeCreate,
)
from sqlalchemy.orm import selectinload
from sqlalchemy import or_, and_, select, delete

import hashlib
from typing import Dict, Optional, List
from .models import UserToken
import time
from .schemas import UserTokenCreate

import logging # Add this if not already there
logger = logging.getLogger(__name__) # Add this
from sqlalchemy.orm import selectinload # Ensure selectinload is imported if used, though not directly in this func

def hash_token(token: str) -> str:
    """Create a secure hash of a token for storage"""
    return hashlib.sha256(token.encode()).hexdigest()


# Keep create_token_record - it's used by store_token_in_db in auth/utils.py
async def create_token_record(
    db: AsyncSession, token_data: UserTokenCreate
) -> UserToken:
    token = UserToken(**token_data.dict())
    db.add(token)
    print(
        f"DEBUG: About to commit token record for user {token_data.user_id}, JTI {token_data.token_key}"
    )  # DEBUG LOG
    try:
        await db.commit()
        print(f"DEBUG: Commit successful for JTI {token_data.token_key}")  # DEBUG LOG
    except Exception as e:
        print(f"ERROR: Commit failed in create_token_record: {e}")  # DEBUG LOG
        raise  # Re-raise the exception
    await db.refresh(token)
    return token


# Keep create_admin_token_record - it's used by store_token_in_db in auth/utils.py
async def create_admin_token_record(
    db: AsyncSession, token_data: AdminTokenCreate
) -> AdminToken:
    token = AdminToken(**token_data.dict())
    db.add(token)
    print(
        f"DEBUG: About to commit token record for user {token_data.user_id}, JTI {token_data.token_key}"
    )  # DEBUG LOG
    try:
        await db.commit()
        print(f"DEBUG: Commit successful for JTI {token_data.token_key}")  # DEBUG LOG
    except Exception as e:
        print(f"ERROR: Commit failed in create_admin_token_record: {e}")  # DEBUG LOG
        raise  # Re-raise the exception
    await db.refresh(token)
    return token


# REMOVE the old get_token_by_key function
# async def get_token_by_key(db: AsyncSession, token_key: str, token_type: str) -> Optional[UserToken]:
#     """Find a token by its key and type"""
#     # ... (implementation removed) ...


# MODIFY verify_token to use JTI
async def verify_token(
    db: AsyncSession, token_jti: str, token_type: str
) -> Optional[UserToken]:  # Signature changed
    """
    Verify token exists in DB, is not blacklisted, and not expired, using JTI.
    Finds the token record based on its JTI stored in the token_key column.
    """
    # Removed: token_key = token[:8] if len(token) >= 8 else token
    # Removed: token_record = await get_token_by_key(db, token_key, token_type)

    # Directly query using JTI (assuming JTI is stored in token_key column)
    current_time = int(time.time())
    stmt = select(UserToken).where(
        UserToken.token_key == token_jti,  # Query by JTI stored in token_key
        UserToken.token_type == token_type,
        UserToken.is_blacklisted == False,
        UserToken.expires_at > current_time,
    )
    result = await db.execute(stmt)
    token_record = result.scalar_one_or_none()  # Expect 0 or 1 result

    # Removed: Hash check (usually redundant when looking up by unique JTI)
    # if not token_record:
    #     return None
    # # To perform hash check, the original 'token' string would need to be passed in again
    # token_hash = hash_token(token)
    # if token_record.token_hash != token_hash:
    #     print(f"Token hash mismatch for JTI: {token_jti}") # Debugging log
    #     return None

    return token_record  # Return the found record (or None)


async def verify_admin_token(
    db: AsyncSession, token_jti: str, token_type: str
) -> Optional[AdminToken]:  # Signature changed
    """
    Verify token exists in DB, is not blacklisted, and not expired, using JTI.
    Finds the token record based on its JTI stored in the token_key column.
    """

    # Directly query using JTI (assuming JTI is stored in token_key column)
    current_time = int(time.time())
    stmt = select(AdminToken).where(
        AdminToken.token_key == token_jti,  # Query by JTI stored in token_key
        AdminToken.token_type == token_type,
        AdminToken.is_blacklisted == False,
        AdminToken.expires_at > current_time,
    )
    result = await db.execute(stmt)
    token_record = result.scalar_one_or_none()  # Expect 0 or 1 result

    print(
        f"DEBUG: Verifying admin token with JTI: {token_jti}, found: {token_record is not None}"
    )

    return token_record  # Return the found record (or None)


# Keep blacklist_token as is
async def blacklist_token(db: AsyncSession, token_id: int) -> bool:
    """Blacklist a token to prevent its use"""
    result = await db.execute(select(UserToken).where(UserToken.id == token_id))
    token = result.scalar_one_or_none()

    if not token:
        return False

    token.is_blacklisted = True
    await db.commit()
    return True


async def blacklist_admin_token(db: AsyncSession, token_id: int) -> bool:
    """Blacklist a token to prevent its use"""
    result = await db.execute(select(AdminToken).where(AdminToken.id == token_id))
    token = result.scalar_one_or_none()

    if not token:
        return False

    token.is_blacklisted = True
    await db.commit()
    return True


# Keep get_user_active_tokens as is
async def get_user_active_tokens(db: AsyncSession, user_id: int) -> List[UserToken]:
    """Get all active (non-blacklisted, non-expired) tokens for a user"""
    current_time = int(time.time())
    result = await db.execute(
        select(UserToken).where(
            UserToken.user_id == user_id,
            UserToken.is_blacklisted == False,
            UserToken.expires_at > current_time,
        )
    )
    return result.scalars().all()


async def get_admin_active_tokens(db: AsyncSession, user_id: int) -> List[AdminToken]:
    """Get all active (non-blacklisted, non-expired) tokens for an admin"""
    current_time = int(time.time())
    result = await db.execute(
        select(AdminToken).where(
            AdminToken.user_id == user_id,
            AdminToken.is_blacklisted == False,
            AdminToken.expires_at > current_time,
        )
    )
    return result.scalars().all()


# Keep blacklist_all_user_tokens as is
async def blacklist_all_user_tokens(db: AsyncSession, user_id: int) -> int:
    """Blacklist all tokens for a user, returns count of blacklisted tokens"""
    tokens = await get_user_active_tokens(db, user_id)
    count = 0

    for token in tokens:
        token.is_blacklisted = True
        count += 1

    if count > 0:
        await db.commit()

    return count


async def blacklist_all_admin_tokens(db: AsyncSession, user_id: int) -> int:
    """Blacklist all tokens for an admin, returns count of blacklisted tokens"""
    tokens = await get_admin_active_tokens(db, user_id)
    count = 0

    for token in tokens:
        token.is_blacklisted = True
        count += 1

    if count > 0:
        await db.commit()

    return count


# Keep cleanup_expired_tokens as is (optional utility)
async def cleanup_expired_tokens(db: AsyncSession) -> int:
    """Delete expired tokens from the database"""
    current_time = int(time.time())
    # Select tokens to delete (safer to select IDs first if needed)
    stmt = select(UserToken).where(UserToken.expires_at < current_time)
    result = await db.execute(stmt)
    expired_tokens = result.scalars().all()
    count = 0
    for token in expired_tokens:
        await db.delete(token)
        count += 1

    if count > 0:
        await db.commit()

    return count


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# User
async def create_user(db: AsyncSession, data: UserCreate):
    hashed_pw = hash_password(data.password)
    user = User(
        firstname=data.firstname,
        lastname=data.lastname,
        email=data.email,
        student_id=data.student_id,
        password_hash=hashed_pw,
        majors=data.majors,
        minors=data.minors,
        faculty=data.faculty,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: int):
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_admin_by_id(db: AsyncSession, admin_id: int):
    result = await db.execute(select(Admin).where(Admin.id == admin_id))
    return result.scalar_one_or_none()


# Course
async def create_course(db: AsyncSession, data: CourseCreate):
    # Check if the course already exists first
    result = await db.execute(select(Course).where(Course.id == data.id))
    existing_course = result.scalar_one_or_none()

    if existing_course:
        return existing_course  # Return the existing course

    # Otherwise create a new course
    course = Course(**data.dict())
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return course


async def get_course_by_id(db: AsyncSession, course_id: int):
    result = await db.execute(select(Course).where(Course.id == course_id))
    return result.scalar_one_or_none()


async def list_courses(db: AsyncSession):
    result = await db.execute(select(Course))
    return result.scalars().all()


# Term
async def get_term_by_user_and_code(
    db: AsyncSession, user_id: int, term_code: str
) -> Optional[Term]:
    """
    Get a term by user_id and term_code.
    If multiple terms exist (which shouldn't happen but might), returns the first one.
    """
    result = await db.execute(
        select(Term)
        .where(Term.user_id == user_id, Term.term_code == term_code)
        .order_by(Term.id)  # Order to ensure consistent results if multiple exist
    )
    # Use first() instead of scalar_one_or_none() to avoid MultipleResultsFound error
    return result.scalars().first()


async def create_term(db: AsyncSession, data: TermCreate):
    """Create a new term. Use get_term_by_user_and_code first to avoid duplicates."""
    term = Term(**data.dict())
    db.add(term)
    await db.commit()
    await db.refresh(term)
    return term


async def get_terms_by_user(db: AsyncSession, user_id: int) -> List[Term]:
    result = await db.execute(
        select(Term).where(Term.user_id == user_id).order_by(Term.term_code.desc())
    )
    return result.scalars().all()


# Enrollment (Current courses only - no grades)
async def enroll_user_in_course(db: AsyncSession, data: EnrollmentCreate):
    # Check if enrollment already exists
    result = await db.execute(
        select(EnrolledCourse).where(
            EnrolledCourse.user_id == data.user_id,
            EnrolledCourse.course_id == data.course_id,
            EnrolledCourse.term_id == data.term_id,
        )
    )
    existing_enrollment = result.scalar_one_or_none()

    if existing_enrollment:
        # Update existing enrollment
        if data.credit_hours is not None:
            existing_enrollment.credit_hours = data.credit_hours
        if data.course_code is not None:
            existing_enrollment.course_code = data.course_code
        if data.course_title is not None:
            existing_enrollment.course_title = data.course_title

        await db.commit()
        await db.refresh(existing_enrollment)
        return existing_enrollment

    # Create new enrollment
    enrollment = EnrolledCourse(**data.dict())
    db.add(enrollment)
    await db.commit()
    await db.refresh(enrollment)
    return enrollment


async def get_enrollments_by_user(db: AsyncSession, user_id: int):
    result = await db.execute(
        select(EnrolledCourse)
        .where(EnrolledCourse.user_id == user_id)
        .options(selectinload(EnrolledCourse.course), selectinload(EnrolledCourse.term))
    )
    return result.scalars().all()


# Course Grades (Historical grades)
async def create_or_update_course_grade(db: AsyncSession, data: CourseGradeCreate):
    """Create or update a course grade"""
    result = await db.execute(
        select(CourseGrade).where(
            CourseGrade.user_id == data.user_id,
            CourseGrade.course_id == data.course_id,
            CourseGrade.term_id == data.term_id,
        )
    )
    existing_grade = result.scalar_one_or_none()

    if existing_grade:
        # Update existing grade
        if data.grade_earned is not None:
            existing_grade.grade_earned = data.grade_earned
        if data.whatif_grade is not None:
            existing_grade.whatif_grade = data.whatif_grade
        if data.credit_hours is not None:
            existing_grade.credit_hours = data.credit_hours
        if data.course_code is not None:
            existing_grade.course_code = data.course_code
        if data.course_title is not None:
            existing_grade.course_title = data.course_title
        if data.earned_date is not None:
            existing_grade.earned_date = data.earned_date

        await db.commit()
        await db.refresh(existing_grade)
        return existing_grade

    # Create new grade record
    grade = CourseGrade(**data.dict())
    db.add(grade)
    await db.commit()
    await db.refresh(grade)
    return grade


async def get_course_grades_by_user(db: AsyncSession, user_id: int):
    """Get all course grades for a user, ordered by term"""
    result = await db.execute(
        select(CourseGrade)
        .join(Term)
        .where(CourseGrade.user_id == user_id)
        .order_by(Term.term_code.desc())
        .options(selectinload(CourseGrade.course), selectinload(CourseGrade.term))
    )
    return result.scalars().all()


async def get_course_grades_by_term(db: AsyncSession, user_id: int, term_id: int):
    """Get all course grades for a user in a specific term"""
    result = await db.execute(
        select(CourseGrade)
        .where(CourseGrade.user_id == user_id, CourseGrade.term_id == term_id)
        .options(selectinload(CourseGrade.course))
    )
    return result.scalars().all()


##SCHEDULER SERVICES


# async def create_availability_slot(
#     db: AsyncSession, admin_id: int, start_time: datetime, end_time: datetime
# ):

#     result = await db.execute(select(Admin).where(Admin.id == admin_id))
#     admin = result.scalars().first()

#     if not admin:
#         raise ValueError("Admin not found")

#     if start_time >= end_time:
#         raise ValueError("Start time must be before end time")

#     slot = AvailabilitySlot(
#         admin_id=admin_id, start_time=start_time, end_time=end_time, is_booked=False
#     )

#     db.add(slot)
#     await db.commit()  # ✅ async commit
#     await db.refresh(slot)  # ✅ async refresh
#     return slot


async def create_bulk_availability_slots(
    db: AsyncSession,
    data: SlotBulkCreate,
    admin_id: int,
):
    # Ensure admin_id is set (should be set from the token by the route handler)
    if not data.admin_id:
        raise HTTPException(status_code=400, detail="Admin ID is required")
    
    # Check if admin exists
    result = await db.execute(select(Admin).where(Admin.id == admin_id))
    admin = result.scalars().first()

    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")

    # 1. Get existing slots from DB
    existing_slots_result = await db.execute(
        select(AvailabilitySlot).where(AvailabilitySlot.admin_id == admin_id)
    )
    existing_slots = existing_slots_result.scalars().all()

    # 2. Check for conflicts within the payload
    for i, slot in enumerate(data.slots):
        if slot.start_time >= slot.end_time:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid time range: {slot.start_time} >= {slot.end_time}",
            )

        for j, other_slot in enumerate(data.slots):
            if i != j:
                # Check internal conflict within payload
                if not (
                    slot.end_time <= other_slot.start_time
                    or slot.start_time >= other_slot.end_time
                ):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Time conflict within submitted slots: {slot.start_time} - {slot.end_time} overlaps with {other_slot.start_time} - {other_slot.end_time}",
                    )

        # 3. Check for conflicts against existing DB slots
        for existing in existing_slots:
            if not (
                slot.end_time <= existing.start_time
                or slot.start_time >= existing.end_time
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"Slot {slot.start_time} - {slot.end_time} conflicts with existing slot {existing.start_time} - {existing.end_time}",
                )

    # 4. No conflicts — proceed with creation
    created_slots: List[AvailabilitySlot] = []

    for slot in data.slots:
        new_slot = AvailabilitySlot(
            admin_id=admin_id,
            start_time=slot.start_time,
            end_time=slot.end_time,
            is_booked=False,
        )
        db.add(new_slot)
        created_slots.append(new_slot)

    await db.commit()

    for slot in created_slots:
        await db.refresh(slot)

    return created_slots


async def book_stu_slot(db: AsyncSession, slot_id: str, student_id: str):

    result = await db.execute(select(User).where(User.id == student_id))
    student = result.scalars().first()

    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Fetch the slot
    result = await db.execute(
        select(AvailabilitySlot).where(AvailabilitySlot.id == slot_id)
    )
    slot = result.scalar_one_or_none()

    if not slot:
        raise ValueError("Slot not found")
    if slot.is_booked:
        raise ValueError("Slot already booked")

    # Check for overlapping bookings
    overlapping_stmt = (
        select(Booking)
        .join(AvailabilitySlot)
        .where(
            Booking.student_id == student_id,
            or_(
                and_(
                    AvailabilitySlot.start_time <= slot.start_time,
                    AvailabilitySlot.end_time > slot.start_time,
                ),
                and_(
                    AvailabilitySlot.start_time < slot.end_time,
                    AvailabilitySlot.end_time >= slot.end_time,
                ),
                and_(
                    AvailabilitySlot.start_time >= slot.start_time,
                    AvailabilitySlot.end_time <= slot.end_time,
                ),
            ),
        )
    )

    overlapping_result = await db.execute(overlapping_stmt)
    overlapping = overlapping_result.scalar_one_or_none()

    if overlapping:
        raise ValueError("Student already has a conflicting booking")

    # Create booking
    booking = Booking(slot_id=slot_id, student_id=student_id)

    slot.is_booked = True

    db.add_all([booking, slot])
    await db.commit()
    await db.refresh(booking)
    return booking


async def unbook_stu_slot(db: AsyncSession, slot_id: int, student_id: int):
    logger.info(f"Service: unbook_stu_slot called with slot_id: {slot_id}, student_id: {student_id}")

    # Find the booking
    result = await db.execute(
        select(Booking).where(
            Booking.slot_id == slot_id, Booking.student_id == student_id
        )
    )
    booking = result.scalar_one_or_none()
    logger.info(f"Service: Found booking: {booking.id if booking else 'None'}")

    if not booking:
        logger.warning(f"Service: Booking not found for slot_id: {slot_id}, student_id: {student_id}")
        raise HTTPException(status_code=404, detail="Booking not found")

    # Update the slot to mark it as not booked
    # Ensure you are querying AvailabilitySlot by its primary key (slot_id which is booking.slot_id)
    slot_to_update_id = booking.slot_id # or directly use the passed slot_id if it's guaranteed to be the AvailabilitySlot PK

    result_slot = await db.execute(
        select(AvailabilitySlot).where(AvailabilitySlot.id == slot_to_update_id) # Use slot_to_update_id or the passed slot_id
    )
    slot = result_slot.scalar_one_or_none()
    logger.info(f"Service: Found slot: {slot.id if slot else 'None'} to update (ID: {slot_to_update_id})")

    if not slot:
        # This case should ideally not happen if a booking existed for the slot_id,
        # but good to have a check.
        logger.error(f"Service: Slot not found (ID: {slot_to_update_id}) for an existing booking (ID: {booking.id}). Data integrity issue?")
        raise HTTPException(status_code=404, detail="Associated slot not found, though booking exists.")

    slot.is_booked = False
    logger.info(f"Service: Slot {slot.id} marked as not booked.")

    # Delete the booking
    booking_id_to_delete = booking.id
    await db.delete(booking)
    logger.info(f"Service: Booking {booking_id_to_delete} deleted from database.")

    await db.commit()
    logger.info(f"Service: Commit successful for unbooking slot_id: {slot_id}, student_id: {student_id}")

    return {"message": "Booking successfully cancelled", "slot_id": slot_id} # slot_id here is the original one passed


async def get_admin_avail_slots(db: AsyncSession, admin_id: int):
    stmt = select(AvailabilitySlot).where(AvailabilitySlot.admin_id == admin_id)
    result = await db.execute(stmt)
    return result.scalars().all()  # Returns a list of AvailabilitySlot objects


async def get_stu_available_slots(db: AsyncSession):
    stmt = select(AvailabilitySlot).where(AvailabilitySlot.is_booked == False)
    result = await db.execute(stmt)
    return result.scalars().all()


# SUPERADMIN


# superadmin check
async def superadmin_required(db: AsyncSession, admin_id: str):
    result = await db.execute(select(Admin).where(Admin.id == admin_id))
    admin = result.scalars().first()

    if not admin or not admin.is_superadmin:
        raise HTTPException(status_code=403, detail="SuperAdmin privileges required")

    return admin


# superadmin create
async def seed_superadmin(db: AsyncSession):
    # Check if a superadmin already exists
    result = await db.execute(select(Admin).where(Admin.is_superadmin == True))
    superadmin = result.scalars().first()

    if superadmin:
        print("[Seeder] SuperAdmin already exists, skipping seed.")
        return

    # If no superadmin, create one
    await create_super_admin(
        db=db,
        data=AdminCreate(
            firstname="Default",
            lastname="SuperAdmin",
            email="superadmin@uwi.edu",
            password=hash_password("superadmin123"),
            is_superadmin=True,
            login_id=999123456,
        ),
    )
    print("[Seeder] SuperAdmin created successfully!")


# ADMIN CRUD OPERATIONS


# create admin
async def create_admin(
    db: AsyncSession,
    data: AdminCreate,
):
    existing_admin = await db.execute(select(Admin).where(Admin.email == data.email))
    if existing_admin.scalars().first():
        raise ValueError("Admin with this email already exists.")

    admin = Admin(
        firstname=data.firstname,
        lastname=data.lastname,
        email=data.email,
        password_hash=hash_password(data.password),
        is_superadmin=False,
        login_id=data.login_id,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


async def create_super_admin(
    db: AsyncSession,
    data: AdminCreate,
):
    existing_admin = await db.execute(select(Admin).where(Admin.email == data.email))
    if existing_admin.scalars().first():
        raise ValueError("Admin with this email already exists.")

    admin = Admin(
        firstname=data.firstname,
        lastname=data.lastname,
        email=data.email,
        password_hash=hash_password(data.password),
        is_superadmin=True,
        login_id=data.login_id,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


# Get all Admins
async def get_all_admins(db: AsyncSession):
    result = await db.execute(select(Admin))
    return result.scalars().all()


# Get one Admin by ID
async def get_admin_by_id(db: AsyncSession, admin_id: int):
    result = await db.execute(select(Admin).where(Admin.id == admin_id))
    return result.scalars().first()


# Update an Admin
async def update_admin(
    db: AsyncSession,
    data: AdminUpdate,
    admin_id: int,
):
    result = await db.execute(select(Admin).where(Admin.id == admin_id))
    admin: Admin = result.scalars().first()

    if not admin:
        return None

    if data.firstname:
        admin.firstname = data.firstname
    if data.lastname:
        admin.lastname = data.lastname
    if data.email:
        admin.email = data.email
    if data.password:
        admin.password_hash = hash_password(data.password)
    if data.login_id:
        admin.login_id = data.login_id

    await db.commit()
    await db.refresh(admin)
    return admin


# Delete an Admin
async def delete_admin(db: AsyncSession, admin_id: int):
    result = await db.execute(select(Admin).where(Admin.id == admin_id))
    admin = result.scalars().first()

    if not admin:
        return None

    await db.delete(admin)
    await db.commit()
    return admin


async def save_course_schedule(
    db: AsyncSession, user_id: int, schedule: CourseSchedule
) -> None:
    """
    1) Upsert master courses, sections, sessions.
    2) Rebuild the user_sessions links so the user only has the imported sessions.
    """
    imported_session_ids = []

    # 1) Upsert master data
    for course_code, course_obj in schedule.items():
        # -- Course --
        result = await db.execute(select(Calendar_Course).filter_by(code=course_code))
        course = result.scalar_one_or_none()
        if course is None:
            course = Calendar_Course(code=course_code, title=course_obj["title"])
            db.add(course)
            await db.flush()
        else:
            course.title = course_obj["title"]

        # -- Sections & Sessions --
        for section_code, sessions_list in course_obj["sections"].items():
            # upsert section
            result = await db.execute(
                select(Calendar_Section).filter_by(
                    course_id=course.id, section_code=section_code
                )
            )
            section = result.scalar_one_or_none()
            if section is None:
                section = Calendar_Section(
                    course_id=course.id, section_code=section_code
                )
                db.add(section)
                await db.flush()

            # upsert each session
            for sess in sessions_list:
                # parse dates
                try:
                    start_str, end_str = [
                        p.strip() for p in sess["date_range"].split(" - ", 1)
                    ]
                    start_date = date_parser.parse(start_str)
                    end_date = date_parser.parse(end_str)
                except Exception:
                    start_date = end_date = None

                # parse times
                try:
                    tstart, tend = [t.strip() for t in sess["time"].split(" - ", 1)]
                    start_time = date_parser.parse(tstart).time()
                    end_time = date_parser.parse(tend).time()
                except Exception:
                    start_time = end_time = None

                # look for an existing identical session
                stmt = select(Calendar_Session).filter_by(
                    section_id=section.id,
                    instructor=sess["instructor"],
                    level=sess["level"],
                    session_type=sess["session_type"],
                    campus=sess["campus"],
                    location=sess["where"],
                    date_range=sess["date_range"],
                    time=sess["time"],
                )
                result = await db.execute(stmt)
                session_obj = result.scalar_one_or_none()

                if session_obj is None:
                    session_obj = Calendar_Session(
                        section_id=section.id,
                        instructor=sess["instructor"],
                        level=sess["level"],
                        session_type=sess["session_type"],
                        campus=sess["campus"],
                        location=sess["where"],
                        date_range=sess["date_range"],
                        start_date=start_date,
                        end_date=end_date,
                        time=sess["time"],
                        start_time=start_time,
                        end_time=end_time,
                    )
                    db.add(session_obj)
                    await db.flush()

                imported_session_ids.append(session_obj.id)

    # 2) Rebuild user→session links
    # a) remove any old links the user no longer has
    await db.execute(
        delete(User_Session).where(
            User_Session.user_id == user_id,
            User_Session.session_id.not_in(imported_session_ids),
        )
    )

    # b) insert missing links
    for sid in set(imported_session_ids):
        # skip if already linked
        stmt = select(User_Session).filter_by(user_id=user_id, session_id=sid)
        result = await db.execute(stmt)
        link = result.scalar_one_or_none()
        if link is None:
            db.add(User_Session(user_id=user_id, session_id=sid))

    # 3) persist all changes
    await db.commit()


async def get_user_calendar_schedule(
    user_id: int, db: AsyncSession
) -> CourseScheduleOut:
    # Query all sessions subscribed by the user
    stmt = (
        select(Calendar_Session)
        .join(Calendar_Session.subscribed_users)
        .where(User.id == user_id)
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    schedule: Dict[str, CalendarCourseOut] = {}

    for session in sessions:
        course = session.section.course
        course_code = course.code
        section_code = session.section.section_code

        # Initialize course entry if not yet in the schedule
        if course_code not in schedule:
            schedule[course_code] = CalendarCourseOut(title=course.title, sections={})

        # Append the session
        session_out = SessionDBOut.model_validate(session)
        if section_code not in schedule[course_code].sections:
            schedule[course_code].sections[section_code] = []

        schedule[course_code].sections[section_code].append(session_out)

    return CourseScheduleOut(schedule)

async def get_student_bookings(db: AsyncSession, student_id: int):
    stmt = (
        select(Booking)
        .join(Booking.slot)  # Explicitly join the slot relation
        .options(
            selectinload(Booking.slot)
            .selectinload(AvailabilitySlot.admin)
        )
        .where(Booking.student_id == student_id)
        .order_by(AvailabilitySlot.start_time.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_admin_bookings(db: AsyncSession, admin_id: int):
    """Get all bookings for slots owned by a specific admin with student details"""
    stmt = (
        select(AvailabilitySlot)
        .options(
            selectinload(AvailabilitySlot.booking)
            .selectinload(Booking.student)
        )
        .where(
            AvailabilitySlot.admin_id == admin_id,
            AvailabilitySlot.is_booked == True
        )
        .order_by(AvailabilitySlot.start_time.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()