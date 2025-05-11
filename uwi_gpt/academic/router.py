# academic/router.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth.utils import get_current_account
from user_db.database import get_db
from user_db.models import Admin, User
import io, sys

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
