# academic/utils.py

from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from user_db.models import CatalogCourse
from sqlalchemy import select, or_

def build_course_query(query: str):
    """
    Return a SQLAlchemy selectable that loads CatalogCourse and its prerequisites,
    filtering where course_code ILIKE %query% OR course_title ILIKE %query%.
    """
    return (
        select(CatalogCourse)
        .options(selectinload(CatalogCourse.prerequisites))
        .where(
            or_(
                CatalogCourse.course_code.ilike(f"%{query}%"),
                CatalogCourse.course_title.ilike(f"%{query}%"),
            )
        )
    )

def serialize_course(course: CatalogCourse) -> dict:
    return {
        "ban_id":           course.ban_id,
        "term_effective":   course.term_effective,
        "subject_code":     course.subject_code,
        "course_number":    course.course_number,
        "course_code":      course.course_code,
        "college":          course.college,        # ← here
        "department":       course.department,     # ← and here
        "course_title":     course.course_title,
        "credit_hour_low":  course.credit_hour_low,
        "credit_hour_high": course.credit_hour_high,
        "prerequisites": [
            {
                "and_or":     p.and_or,
                "subject":    p.subject,
                "number":     p.number,
                "course_code":p.course_code,
                "level":      p.level,
                "grade":      p.grade,
            }
            for p in course.prerequisites
        ],
    }

