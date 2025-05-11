# academic/router.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from auth.utils import get_current_account
from user_db.database import get_db
from user_db.models import Admin, User
import io, sys
from pydantic import BaseModel, Field
from typing import Dict, Any
from .credit_check import (
    fst_schema_standardized,
    fss_schema_standardized,
    fhe_schema_standardized,
    major_schema_comp,
    major_schema_swen,
    minor_schema_mgmt,
    minor_schema_math,
    check_all_requirements,
    check_potential_graduation_standardized,
    print_report_header,
    print_credit_summary,
    print_foundation_report,
    print_language_requirement_report,
    print_major_requirements_report,
    print_minor_requirements_report,
    print_potential_graduation_report,
    print_final_status,
)
from .utils import build_course_query, serialize_course
from typing import List, Optional

router = APIRouter(prefix="/academic", tags=["Academic"])

# 1) Dictionaries for schema lookup
FACULTY_SCHEMAS = {
    "Science and Technology": fst_schema_standardized,
    "FSS": fss_schema_standardized,
    "HE": fhe_schema_standardized,
}

MAJOR_SCHEMAS = {
    "Computer Science": (major_schema_comp, "COMP"),
    "Software Engineering": (major_schema_swen, "SWEN"),
    # add more majors here...
}

MINOR_SCHEMAS = {
    "Management Studies": (minor_schema_mgmt,),
    "Mathematics": (minor_schema_math,),
    # add more minors here...
}

class CourseInputModel(BaseModel):
    course_code: str
    course_title: str
    credit_hours: float
    grade_earned: str
    whatif_grade: Optional[str] = "NA"

class TermInputModel(BaseModel):
    term_code: str # e.g., "202320"
    courses: List[CourseInputModel]
    semester_gpa: float
    cumulative_gpa: float
    degree_gpa: Optional[float] = None # Can be null for some terms
    credits_earned_to_date: float

class UserTranscriptInput(BaseModel):
    terms: List[TermInputModel] = Field(..., description="List of academic terms with course details.")
    # student_info can be used for FSS language exemptions, etc.
    # Example: {'is_native_english': True, 'has_language_qualification': False, 'is_international': False}
    student_info: Optional[Dict[str, Any]] = Field(None, description="Optional student information for exemption processing.", examples=[{"is_native_english": True, "has_language_qualification": False, "is_international": True}])

@router.get("/credit-check")
async def credit_check(
    current_user: User | Admin = Depends(get_current_account),
    db: AsyncSession = Depends(get_db),
):
    # 1) Pick faculty schema
    faculty_key = current_user.faculty
    faculty_schema = FACULTY_SCHEMAS.get(faculty_key)
    if not faculty_schema:
        raise HTTPException(400, f"Unknown faculty: {faculty_key}")

    # 2) Pick major
    declared_majors = (current_user.majors or "").split(",")
    if not declared_majors or declared_majors[0] not in MAJOR_SCHEMAS:
        raise HTTPException(400, f"Unsupported or missing major: {declared_majors}")
    major_name, (major_schema, student_major_code) = (
        declared_majors[:1],
        MAJOR_SCHEMAS[declared_majors[0]],
    )

    # 3) Pick minor if any
    minor_schema = None
    declared_minors = (current_user.minors or "").split(",")
    if declared_minors and declared_minors[0] in MINOR_SCHEMAS:
        minor_schema = MINOR_SCHEMAS[declared_minors[0]][0]

    # 4) Rebuild transcript dict
    transcript = {"data": {"terms": [], "overall": {}}}
    # sort terms reverse‑chronological
    for term in sorted(current_user.terms, key=lambda t: t.term_code, reverse=True):
        courses = [
            {
                "course_code": g.course_code,
                "course_title": g.course_title,
                "credit_hours": g.credit_hours,
                "grade_earned": g.grade_earned,
                "whatif_grade": g.whatif_grade,
            }
            for g in current_user.grades
            if g.term_id == term.id
        ]
        transcript["data"]["terms"].append(
            {
                "term_code": term.term_code,
                "courses": courses,
                "semester_gpa": term.semester_gpa,
                "cumulative_gpa": term.cumulative_gpa,
                "degree_gpa": term.degree_gpa,
                "credits_earned_to_date": term.credits_earned_to_date,
            }
        )
    if transcript["data"]["terms"]:
        recent = transcript["data"]["terms"][0]
        transcript["data"]["overall"] = {
            "cumulative_gpa": recent["cumulative_gpa"],
            "degree_gpa": recent["degree_gpa"],
            "total_credits_earned": recent["credits_earned_to_date"],
        }

    # 5) Run the analysis
    result = check_all_requirements(
        transcript,
        faculty_schema,
        major_schema,
        student_major_code,
        minor_schema,
        student_info=None,
    )
    potential = check_potential_graduation_standardized(result, student_info=None)
    result["potentially_eligible_for_graduation"] = potential["potential_graduate"]
    result["potential_all_requirements_satisfied"] = potential[
        "potential_all_requirements_satisfied"
    ]
    # 6) Capture all of your formatted reports
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf

    # optional header:
    print_report_header(
        faculty_schema.get("faculty_name", faculty_key),
        major_schema.get("major", major_name),
        student_major_code,
        minor_schema.get("minor") if minor_schema else None,
    )
    print_credit_summary(result["faculty_result"]["credits_earned"], faculty_schema)
    print_foundation_report(result["faculty_result"]["foundation_status"])
    if result["faculty_result"].get("language_status"):
        print_language_requirement_report(result["faculty_result"]["language_status"])
    print_major_requirements_report(result["major_result"])
    if result.get("minor_result"):
        print_minor_requirements_report(result["minor_result"])

    # potential‐status
    potential = check_potential_graduation_standardized(result, student_info=None)
    print_potential_graduation_report(potential)

    print_final_status(result)

    sys.stdout = old_stdout
    reports_text = buf.getvalue()

    return {"analysis": result, "reports": reports_text}


@router.get(
    "/course",
    response_model=List[dict],
    summary="Search courses by free‐text query",
)
async def search_courses(
    q: str = Query(..., description="Search term (matches code OR title)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Free‐text search on course_code OR course_title.
    Returns all matching courses (with prerequisites).
    """
    stmt = build_course_query(q)
    result = await db.execute(stmt)
    courses = result.scalars().all()

    if not courses:
        raise HTTPException(404, f"No courses found matching '{q}'")

    return [serialize_course(c) for c in courses]

@router.post("/credit-check-transcript", summary="Perform credit check using a user-provided transcript")
async def credit_check_with_transcript(
    transcript_input: UserTranscriptInput,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db), # db dependency for get_current_user
):
    # 1) Pick faculty schema based on current_user
    faculty_key = current_user.faculty
    faculty_schema_definition = FACULTY_SCHEMAS.get(faculty_key)
    if not faculty_schema_definition:
        raise HTTPException(status_code=400, detail=f"Unknown faculty for user: {faculty_key}")
    
    # Deepcopy to prevent modification of global schema if student_major_code is added
    faculty_schema = faculty_schema_definition.copy()


    # 2) Pick major schema based on current_user
    declared_majors = (current_user.majors or "").split(",")
    if not declared_majors or not declared_majors[0] or declared_majors[0] not in MAJOR_SCHEMAS:
        raise HTTPException(status_code=400, detail=f"Unsupported or missing major for user: {declared_majors}")
    major_name_from_user = declared_majors[0]
    major_schema_definition, student_major_code = MAJOR_SCHEMAS[major_name_from_user]
    major_schema = major_schema_definition.copy()


    # 3) Pick minor schema if any, based on current_user
    minor_schema_definition = None
    minor_schema = None
    declared_minors = (current_user.minors or "").split(",")
    if declared_minors and declared_minors[0] and declared_minors[0] in MINOR_SCHEMAS:
        minor_schema_definition = MINOR_SCHEMAS[declared_minors[0]][0]
        minor_schema = minor_schema_definition.copy()

    # 4) Construct transcript dict from user input
    transcript_for_analysis = {"data": {"terms": [], "overall": {}}}
    
    processed_terms = []
    for term_model in transcript_input.terms:
        # Convert Pydantic model to dict. `model_dump()` is the V2 equivalent of `dict()`.
        term_dict = term_model.model_dump() 
        processed_terms.append(term_dict)

    # Sort terms reverse-chronologically by term_code
    sorted_terms = sorted(processed_terms, key=lambda t: t["term_code"], reverse=True)
    transcript_for_analysis["data"]["terms"] = sorted_terms

    # Populate overall from the most recent term (if terms exist)
    if sorted_terms:
        recent_term = sorted_terms[0]
        transcript_for_analysis["data"]["overall"] = {
            "cumulative_gpa": recent_term.get("cumulative_gpa"),
            "degree_gpa": recent_term.get("degree_gpa"),
            "total_credits_earned": recent_term.get("credits_earned_to_date"),
        }
    else: # Handle empty terms list from input
        transcript_for_analysis["data"]["overall"] = {
            "cumulative_gpa": 0.0,
            "degree_gpa": None,
            "total_credits_earned": 0.0,
        }

    # Use student_info from input if provided, otherwise None or a default.
    # The check_all_requirements function expects this.
    student_info_for_check = transcript_input.student_info
    # If student_info is None and your logic requires a default dict:
    # if student_info_for_check is None:
    #     student_info_for_check = {'is_native_english': True, ... }


    # 5) Run the analysis
    # Ensure schemas are deepcopied if they are modified by the checking functions
    # (e.g., if student_major_code is added to faculty_schema inside check_faculty_requirements)
    # The .copy() above for schemas is a shallow copy. If check_all_requirements modifies nested dicts,
    # a deepcopy would be safer: import copy; faculty_schema = copy.deepcopy(FACULTY_SCHEMAS.get(faculty_key))

    result = check_all_requirements(
        transcript_for_analysis,
        faculty_schema, # Pass the (potentially shallow) copied schema
        major_schema,   # Pass the (potentially shallow) copied schema
        student_major_code,
        minor_schema,   # Pass the (potentially shallow) copied schema
        student_info=student_info_for_check 
    )
    
    # The check_potential_graduation_standardized function expects the result from check_all_requirements,
    # which includes the schemas.
    potential = check_potential_graduation_standardized(result, student_info=student_info_for_check)
    result["potentially_eligible_for_graduation"] = potential["potential_graduate"]
    result["potential_all_requirements_satisfied"] = potential["potential_all_requirements_satisfied"]
    
    # 6) Capture all of your formatted reports
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf

    print_report_header(
        faculty_schema.get("faculty_name", faculty_key),
        major_schema.get("major", major_name_from_user),
        student_major_code,
        minor_schema.get("minor") if minor_schema else None
    )
    
    # The faculty_schema within 'result' (result['faculty_schema']) would have student_major_code if added by check_all_reqs
    print_credit_summary(result["faculty_result"]["credits_earned"], result["faculty_schema"])
    print_foundation_report(result["faculty_result"]["foundation_status"])
    if result["faculty_result"].get("language_status"):
        print_language_requirement_report(result["faculty_result"]["language_status"])
    print_major_requirements_report(result["major_result"])
    if result.get("minor_result"):
        print_minor_requirements_report(result["minor_result"])

    print_potential_graduation_report(potential) # Use the 'potential' dictionary from its calculation
    print_final_status(result)

    sys.stdout = old_stdout
    reports_text = buf.getvalue()

    return {
        "analysis": result,
        "reports": reports_text
    }
