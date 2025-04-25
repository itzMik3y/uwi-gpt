from pydantic import BaseModel, EmailStr
from typing import Optional


class UserCreate(BaseModel):
    firstname: str
    lastname: str
    email: EmailStr
    student_id: str
    password: str
    majors: Optional[str] = None  # Comma-separated list
    minors: Optional[str] = None  # Comma-separated list
    faculty: Optional[str] = None


class UserOut(BaseModel):
    id: int
    firstname: str
    lastname: str
    email: EmailStr
    student_id: str
    majors: Optional[str] = None
    minors: Optional[str] = None
    faculty: Optional[str] = None

    class Config:
        from_attributes = True


class CourseCreate(BaseModel):
    id: int
    fullname: str
    shortname: str
    idnumber: str
    summary: Optional[str] = ""
    summaryformat: int
    startdate: int
    enddate: int
    visible: bool
    showactivitydates: bool
    showcompletionconditions: bool
    fullnamedisplay: str
    viewurl: Optional[str] = ""
    coursecategory: Optional[str] = ""


class CourseOut(CourseCreate):
    class Config:
        from_attributes = True


class TermCreate(BaseModel):
    term_code: str
    user_id: int
    semester_gpa: Optional[float] = None
    cumulative_gpa: Optional[float] = None
    degree_gpa: Optional[float] = None
    credits_earned_to_date: Optional[int] = None


class TermOut(TermCreate):
    id: int

    class Config:
        from_attributes = True


class EnrollmentCreate(BaseModel):
    user_id: int
    course_id: int
    term_id: int
    course_code: str
    course_title: str
    credit_hours: float


class EnrollmentOut(EnrollmentCreate):
    id: int

    class Config:
        from_attributes = True


class CourseGradeCreate(BaseModel):
    user_id: int
    course_id: int
    term_id: int
    course_code: str
    course_title: str
    credit_hours: float
    grade_earned: Optional[str] = None
    whatif_grade: Optional[str] = None
    is_historical: bool = True
    earned_date: Optional[int] = None


class CourseGradeOut(CourseGradeCreate):
    id: int

    class Config:
        from_attributes = True

class UserTokenCreate(BaseModel):
    user_id: int
    token_type: str
    token_key: str
    token_hash: str
    expires_at: int
    device_info: Optional[str] = None
    ip_address: Optional[str] = None

class UserTokenOut(BaseModel):
    id: int
    user_id: int
    token_type: str
    created_at: int
    expires_at: int
    is_blacklisted: bool
    device_info: Optional[str] = None
    
    class Config:
        from_attributes = True