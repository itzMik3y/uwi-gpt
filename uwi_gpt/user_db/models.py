from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    ForeignKey,
    DateTime,
    Table,
    UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func
import datetime
import time


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    firstname = Column(String, nullable=False)
    lastname = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    student_id = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

    terms = relationship("Term", back_populates="user")
    enrollments = relationship("EnrolledCourse", back_populates="user")
    grades = relationship("CourseGrade", back_populates="user")
    courses = relationship("Course", secondary="enrolled_courses", viewonly=True)
    majors = Column(String, nullable=True)  # Comma-separated list of majors
    minors = Column(String, nullable=True)  # Comma-separated list of minors
    faculty = Column(String, nullable=True)  # Faculty/College
    tokens = relationship(
        "UserToken", back_populates="user", cascade="all, delete-orphan"
    )

    bookings = relationship("Booking", back_populates="student")


class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True)
    login_id = Column(Integer, unique=True, nullable=False, index=True)
    firstname = Column(String, nullable=False)
    lastname = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)

    is_superadmin = Column(Boolean, default=False)  # <-- New field!

    slots = relationship("AvailabilitySlot", back_populates="admin")
    tokens = relationship(
        "AdminToken", back_populates="admin", cascade="all, delete-orphan"
    )


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True)  # Moodle course ID
    fullname = Column(String)
    shortname = Column(String)
    idnumber = Column(String)
    summary = Column(String)
    summaryformat = Column(Integer)
    startdate = Column(Integer)  # Unix timestamp
    enddate = Column(Integer)
    visible = Column(Boolean)
    showactivitydates = Column(Boolean)
    showcompletionconditions = Column(Boolean)
    fullnamedisplay = Column(String)
    viewurl = Column(String)
    coursecategory = Column(String)

    enrollments = relationship("EnrolledCourse", back_populates="course")
    grades = relationship("CourseGrade", back_populates="course")


class Term(Base):
    __tablename__ = "terms"

    id = Column(Integer, primary_key=True)
    term_code = Column(String, nullable=False)  # e.g. "202420"
    user_id = Column(Integer, ForeignKey("users.id"))

    semester_gpa = Column(Float)
    cumulative_gpa = Column(Float)
    degree_gpa = Column(Float)
    credits_earned_to_date = Column(Integer)

    user = relationship("User", back_populates="terms")
    enrolled_courses = relationship("EnrolledCourse", back_populates="term")
    grades = relationship("CourseGrade", back_populates="term")


class EnrolledCourse(Base):
    __tablename__ = "enrolled_courses"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    course_id = Column(Integer, ForeignKey("courses.id"))
    term_id = Column(Integer, ForeignKey("terms.id"))

    course_code = Column(String)
    course_title = Column(String)
    credit_hours = Column(Float)

    # No longer storing grades here - just current enrollments

    user = relationship("User", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")
    term = relationship("Term", back_populates="enrolled_courses")


class CourseGrade(Base):
    __tablename__ = "course_grades"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    course_id = Column(Integer, ForeignKey("courses.id"))
    term_id = Column(Integer, ForeignKey("terms.id"))

    course_code = Column(String)
    course_title = Column(String)
    credit_hours = Column(Float)
    grade_earned = Column(String)
    whatif_grade = Column(String)

    # Additional fields that might be useful
    is_historical = Column(Boolean, default=True)  # Flag to distinguish past courses
    earned_date = Column(Integer)  # Unix timestamp when grade was earned

    user = relationship("User", back_populates="grades")
    course = relationship("Course", back_populates="grades")
    term = relationship("Term", back_populates="grades")


class UserToken(Base):
    __tablename__ = "user_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_type = Column(String, nullable=False)  # 'access' or 'refresh'
    token_key = Column(
        String, nullable=False, index=True
    )  # First 8 chars of the token as lookup key
    token_hash = Column(String, nullable=False)  # Hashed token for security
    expires_at = Column(Integer, nullable=False)  # Unix timestamp for expiration
    created_at = Column(Integer, nullable=False, default=lambda: int(time.time()))
    is_blacklisted = Column(Boolean, nullable=False, default=False)
    device_info = Column(
        String, nullable=True
    )  # Optional device info (user agent, etc.)
    ip_address = Column(String, nullable=True)  # Optional IP address of the client

    # Relationships
    user = relationship("User", back_populates="tokens")


class AdminToken(Base):
    __tablename__ = "admin_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("admins.id"), nullable=False, index=True)
    # role = Column(String, nullable=False)  # Role of the admin (e.g., 'admin')
    token_type = Column(String, nullable=False)  # 'access' or 'refresh'
    token_key = Column(
        String, nullable=False, index=True
    )  # First 8 characters of the token
    token_hash = Column(String, nullable=False)  # Securely hashed full token
    expires_at = Column(
        Integer, nullable=False
    )  # Unix timestamp (e.g., time.time() + ttl)
    created_at = Column(Integer, nullable=False, default=lambda: int(time.time()))
    is_blacklisted = Column(Boolean, nullable=False, default=False)
    device_info = Column(String, nullable=True)  # Optional user-agent/device info
    ip_address = Column(String, nullable=True)  # Optional client IP address

    # Relationship to admin
    admin = relationship("Admin", back_populates="tokens")


class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"
    id = Column(Integer, primary_key=True)
    admin_id = Column(Integer, ForeignKey("admins.id"), nullable=False, index=True)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    is_booked = Column(Boolean, default=False)

    admin = relationship("Admin", back_populates="slots")
    booking = relationship("Booking", uselist=False, back_populates="slot")


class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    slot_id = Column(
        Integer, ForeignKey("availability_slots.id"), nullable=False, index=True
    )
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True), default=func.now()
    )  # Automatically gets current UTC time

    slot = relationship("AvailabilitySlot", back_populates="booking")
    student = relationship("User", back_populates="bookings")

class CatalogCourse(Base):
    __tablename__ = "catalog_courses"

    # surrogate primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    # BAN system course ID (from scraped JSON; e.g., 5777)
    ban_id = Column(Integer, unique=True, nullable=False, index=True)
    term_effective = Column(String, nullable=False)   # e.g., "200410"
    subject_code = Column(String, nullable=False)     # e.g. "BIOC"
    course_number = Column(String, nullable=False)    # e.g. "3203"
    # Combined field for easy lookups and unique constraint
    course_code = Column(String, nullable=False, index=True)
    college           = Column(String, nullable=True, index=True)
    department        = Column(String, nullable=True, index=True)
    college_code     = Column(String)
    course_title     = Column(String)
    credit_hour_low  = Column(Integer)
    credit_hour_high = Column(Integer)
    # other metadata fields...

    # One-to-many to prereqs
    prerequisites = relationship(
        "CatalogPrerequisite",
        back_populates="course",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # ensure uniqueness of this combination
        UniqueConstraint('subject_code', 'course_number', name='uq_subject_course'),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # auto-generate course_code if not provided
        if not getattr(self, 'course_code', None):
            self.course_code = f"{self.subject_code}{self.course_number}"

class CatalogPrerequisite(Base):
    __tablename__ = "catalog_prerequisites"
    id = Column(Integer, primary_key=True, autoincrement=True)
    course_id = Column(Integer, ForeignKey("catalog_courses.id"), nullable=False)

    # "And" / "Or" relationship
    and_or  = Column(String)
    # e.g. "MICR - Microbiology"
    subject = Column(String, nullable=False)
    number  = Column(String, nullable=False)
    level   = Column(String)
    grade   = Column(String)

    course = relationship("CatalogCourse", back_populates="prerequisites")
    course_code = Column(String, nullable=False, index=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # auto‐compute on new instances
        if not getattr(self, "course_code", None):
            subj_code = self.subject.split(" - ")[0]
            self.course_code = f"{subj_code}{self.number}"

    def __repr__(self):
        return (
            f"<Prereq {self.and_or or ''} {self.subject}"  
            f" {self.number} level={self.level} grade={self.grade}>"
        )
