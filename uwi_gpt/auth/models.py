# auth/models.py
from datetime import datetime, time as dtime
from pydantic import BaseModel, EmailStr, ConfigDict, RootModel
from typing import Dict, List, Optional


class RefreshRequest(BaseModel):
    refresh_token: str


class Token(BaseModel):
    """Response model for token endpoints"""

    access_token: str
    token_type: str
    refresh_token: str
    expires_at: int  # Unix timestamp


class TokenPayload(BaseModel):
    """Internal model for JWT payload validation"""

    sub: Optional[str] = None  # subject (user_id)
    exp: Optional[int] = None  # expiration time
    type: str  # token type: "access" or "refresh"
    jti: Optional[str] = None  # JWT ID for tracking


class TokenData(BaseModel):
    """Internal model for token data after validation"""

    user_id: int
    is_refresh: bool = False


class LoginRequest(BaseModel):
    username: str
    password: str


class CourseOutMinimal(BaseModel):  # Simplified for this example
    id: int
    fullname: str
    shortname: Optional[str] = None
    # Add other fields matching your example:
    idnumber: Optional[str] = None
    summary: Optional[str] = None
    summaryformat: Optional[int] = None
    startdate: Optional[int] = None
    enddate: Optional[int] = None
    visible: Optional[bool] = None
    showactivitydates: Optional[bool] = None
    showcompletionconditions: Optional[bool] = None
    fullnamedisplay: Optional[str] = None
    viewurl: Optional[str] = None
    coursecategory: Optional[str] = None

    class Config:
        from_attributes = True


class CourseGradeOutMinimal(BaseModel):  # Simplified
    course_code: Optional[str] = None
    course_title: Optional[str] = None
    credit_hours: Optional[float] = None
    grade_earned: Optional[str] = None
    whatif_grade: Optional[str] = None  # Usually null from DB

    class Config:
        from_attributes = True


class TermGradesOut(BaseModel):  # Represents one term in the grades_data
    term_code: str
    courses: List[CourseGradeOutMinimal]
    semester_gpa: Optional[float] = None
    cumulative_gpa: Optional[float] = None
    degree_gpa: Optional[float] = None
    credits_earned_to_date: Optional[int] = None

    class Config:
        from_attributes = True


class GradesDataOut(BaseModel):  # The structure for grades_data
    student_name: str
    student_id: str
    terms: List[TermGradesOut]
    overall: dict  # Keep simple dict or define schema


class GradesStatusOut(BaseModel):  # Matches your example
    fetched: bool
    success: bool
    error: Optional[str] = None


class UserInfoOut(BaseModel):  # Matches user_info structure
    name: str
    email: EmailStr
    student_id: str
    majors: Optional[str] = None
    minors: Optional[str] = None
    faculty: Optional[str] = None


class MoodleCoursesWrapperOut(BaseModel):  # Matches courses structure
    courses: List[CourseOutMinimal]
    nextoffset: Optional[int] = None  # Or appropriate type


class MoodleDataOut(BaseModel):  # Matches moodle_data structure
    user_info: UserInfoOut
    courses: MoodleCoursesWrapperOut
    # Exclude calendar_events and auth_tokens as they aren't available from /me
    # calendar_events: dict
    # auth_tokens: dict


class AdminInfoOut(BaseModel):
    name: str
    email: str
    is_superadmin: bool


class StudentOut(BaseModel):
    id: int
    name: str
    email: str
    student_id: str


class BookingOut(BaseModel):
    id: int
    student: StudentOut
    created_at: datetime


class SlotOut(BaseModel):
    id: int
    start_time: datetime
    end_time: datetime
    is_booked: bool
    booking: Optional[BookingOut] = None


# Calendar SAS schemas
class Calendar_Session_Schema(BaseModel):
    instructor: str
    level: str
    session_type: str
    campus: str
    where: str
    date_range: str
    time: str


class Calendar_Section_Schema(BaseModel):
    # A section is a list of session entries (e.g., multiple lectures in M11)
    sessions: List[Calendar_Session_Schema]


class Calendar_Course_Schema(BaseModel):
    title: str
    sections: Dict[str, List[Calendar_Session_Schema]]  # Keys like "B01", "M11", etc.


class CourseSchedule(BaseModel):
    data: Dict[str, Calendar_Course_Schema]  # Keys like "COMP 3162", "INFO 3180", etc.
    # might need to adjust to take out data property since the data outputted does not contain a data property


### calendar output
class SessionOut(BaseModel):
    instructor: str
    level: str
    session_type: str
    campus: str
    where: str
    date_range: str
    start_date: datetime
    end_date: datetime
    time: str
    start_time: dtime  # now a real datetime.time
    end_time: dtime

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
    )


class SessionDBOut(BaseModel):
    instructor: str
    level: str
    session_type: str
    campus: str
    location: str
    date_range: str
    start_date: datetime
    end_date: datetime
    time: str
    start_time: dtime  # now a real datetime.time
    end_time: dtime

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
    )


class CalendarCourseOut(BaseModel):
    title: str
    sections: Dict[str, List[SessionOut]]

    class Config:
        from_attributes = True


class CourseScheduleOut(RootModel[Dict[str, CalendarCourseOut]]):
    """
    A root‐model whose “root” is Dict[str, CourseOut],
    i.e. { "COMP 3162": { … }, "COMP 3901": { … } }
    """

    pass


# --- The final response model for /auth/admin/me ---

###


class AdminMeResponse(BaseModel):
    admin_info: AdminInfoOut
    slots: List[SlotOut]

    class Config:
        from_attributes = True


# --- The final response model for /auth/me ---
class MeResponse(BaseModel):
    moodle_data: MoodleDataOut
    grades_status: GradesStatusOut
    grades_data: GradesDataOut
    calendar_course_schedule: CourseScheduleOut
