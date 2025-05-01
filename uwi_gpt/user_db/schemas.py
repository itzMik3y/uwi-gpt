from datetime import datetime
from pydantic import BaseModel, EmailStr
from typing import Optional


class UserCreate(BaseModel):
    firstname: str
    lastname: str
    email: EmailStr
    student_id: str
    password: str


class UserOut(BaseModel):
    id: int
    firstname: str
    lastname: str
    email: EmailStr
    student_id: str

    class Config:
        from_attributes = True


class AdminIn(BaseModel):
    requesting_admin_id: int
    firstname: str
    lastname: str
    email: EmailStr
    password: str
    is_superadmin: Optional[bool] = False
    login_id: int


class AdminCreate(
    BaseModel
):  # probably adjust for superadmin, making it different from normal admin
    firstname: str
    lastname: str
    email: EmailStr
    password: str
    is_superadmin: Optional[bool] = False
    login_id: int


class AdminUpdate(BaseModel):
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    login_id: Optional[int] = None


class AdminOut(BaseModel):
    id: int
    firstname: str
    lastname: str
    email: EmailStr
    is_superadmin: bool
    login_id: int

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


# class SlotCreate(BaseModel):
#     admin_id: int
#     start_time: datetime
#     end_time: datetime


# class SlotOut(BaseModel):
#     id: int
#     admin_id: int
#     start_time: datetime
#     end_time: datetime

#     class Config:
#         from_attributes = True


class SlotSummary(BaseModel):
    start_time: datetime
    end_time: datetime


class SlotBulkCreate(BaseModel):
    admin_id: int
    slots: list[SlotSummary]

    class Config:
        from_attributes = True


class SlotOut(BaseModel):
    id: int
    admin_id: int
    start_time: datetime
    end_time: datetime
    is_booked: bool

    class Config:
        from_attributes = True


class BookingCreate(BaseModel):
    student_id: int
    slot_id: int
