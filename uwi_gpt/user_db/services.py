from sqlalchemy.ext.asyncio import AsyncSession
from .models import Course, EnrolledCourse, Term, User
from .schemas import CourseCreate, EnrollmentCreate, TermCreate, UserCreate
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select
import hashlib


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
    course = Course(**data.dict())
    db.add(course)
    await db.commit()
    await db.refresh(course)
    return course


async def list_courses(db: AsyncSession):
    result = await db.execute(select(Course))
    return result.scalars().all()


# Term
async def create_term(db: AsyncSession, data: TermCreate):
    term = Term(**data.dict())
    db.add(term)
    await db.commit()
    await db.refresh(term)
    return term


async def get_terms_by_user(db: AsyncSession, user_id: int):
    result = await db.execute(select(Term).where(Term.user_id == user_id))
    return result.scalars().all()


# Enrollment
async def enroll_user_in_course(db: AsyncSession, data: EnrollmentCreate):
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
