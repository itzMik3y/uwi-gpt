from sqlalchemy.ext.asyncio import AsyncSession
from .models import Course, EnrolledCourse, Term, User, CourseGrade
from .schemas import CourseCreate, EnrollmentCreate, TermCreate, UserCreate, CourseGradeCreate
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select
import hashlib
from typing import Optional, List
from .models import UserToken
import time
from .schemas import UserTokenCreate

def hash_token(token: str) -> str:
    """Create a secure hash of a token for storage"""
    return hashlib.sha256(token.encode()).hexdigest()

# Keep create_token_record - it's used by store_token_in_db in auth/utils.py
async def create_token_record(db: AsyncSession, token_data: UserTokenCreate) -> UserToken:
    token = UserToken(**token_data.dict())
    db.add(token)
    print(f"DEBUG: About to commit token record for user {token_data.user_id}, JTI {token_data.token_key}") # DEBUG LOG
    try:
        await db.commit()
        print(f"DEBUG: Commit successful for JTI {token_data.token_key}") # DEBUG LOG
    except Exception as e:
        print(f"ERROR: Commit failed in create_token_record: {e}") # DEBUG LOG
        raise # Re-raise the exception
    await db.refresh(token)
    return token

# REMOVE the old get_token_by_key function
# async def get_token_by_key(db: AsyncSession, token_key: str, token_type: str) -> Optional[UserToken]:
#     """Find a token by its key and type"""
#     # ... (implementation removed) ...


# MODIFY verify_token to use JTI
async def verify_token(db: AsyncSession, token_jti: str, token_type: str) -> Optional[UserToken]: # Signature changed
    """
    Verify token exists in DB, is not blacklisted, and not expired, using JTI.
    Finds the token record based on its JTI stored in the token_key column.
    """
    # Removed: token_key = token[:8] if len(token) >= 8 else token
    # Removed: token_record = await get_token_by_key(db, token_key, token_type)

    # Directly query using JTI (assuming JTI is stored in token_key column)
    current_time = int(time.time())
    stmt = select(UserToken).where(
        UserToken.token_key == token_jti, # Query by JTI stored in token_key
        UserToken.token_type == token_type,
        UserToken.is_blacklisted == False,
        UserToken.expires_at > current_time
    )
    result = await db.execute(stmt)
    token_record = result.scalar_one_or_none() # Expect 0 or 1 result

    # Removed: Hash check (usually redundant when looking up by unique JTI)
    # if not token_record:
    #     return None
    # # To perform hash check, the original 'token' string would need to be passed in again
    # token_hash = hash_token(token)
    # if token_record.token_hash != token_hash:
    #     print(f"Token hash mismatch for JTI: {token_jti}") # Debugging log
    #     return None

    return token_record # Return the found record (or None)


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

# Keep get_user_active_tokens as is
async def get_user_active_tokens(db: AsyncSession, user_id: int) -> List[UserToken]:
    """Get all active (non-blacklisted, non-expired) tokens for a user"""
    current_time = int(time.time())
    result = await db.execute(
        select(UserToken)
        .where(
            UserToken.user_id == user_id,
            UserToken.is_blacklisted == False,
            UserToken.expires_at > current_time
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
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_id(db: AsyncSession, user_id: int):
    result = await db.execute(select(User).where(User.id == user_id))
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
async def get_term_by_user_and_code(db: AsyncSession, user_id: int, term_code: str) -> Optional[Term]:
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
            EnrolledCourse.term_id == data.term_id
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
            CourseGrade.term_id == data.term_id
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