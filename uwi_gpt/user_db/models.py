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


class EnrolledCourse(Base):
    __tablename__ = "enrolled_courses"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    course_id = Column(Integer, ForeignKey("courses.id"))
    term_id = Column(Integer, ForeignKey("terms.id"))

    course_code = Column(String)
    course_title = Column(String)
    credit_hours = Column(Float)
    grade_earned = Column(String)
    whatif_grade = Column(String)

    user = relationship("User", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")
    term = relationship("Term", back_populates="enrolled_courses")
