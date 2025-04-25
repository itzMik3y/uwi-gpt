from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    ForeignKey,
    DateTime,
    Table,
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase
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
    faculty = Column(String, nullable=True) # Faculty/College
    tokens = relationship("UserToken", back_populates="user", cascade="all, delete-orphan")
    

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
    token_key = Column(String, nullable=False, index=True)  # First 8 chars of the token as lookup key
    token_hash = Column(String, nullable=False)  # Hashed token for security
    expires_at = Column(Integer, nullable=False)  # Unix timestamp for expiration
    created_at = Column(Integer, nullable=False, default=lambda: int(time.time()))
    is_blacklisted = Column(Boolean, nullable=False, default=False)
    device_info = Column(String, nullable=True)  # Optional device info (user agent, etc.)
    ip_address = Column(String, nullable=True)   # Optional IP address of the client

    # Relationships
    user = relationship("User", back_populates="tokens")