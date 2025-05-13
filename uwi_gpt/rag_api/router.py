#!/usr/bin/env python
"""
rag_api/router.py - Router for the RAG-based QA system API endpoints
(Enhanced user context integration, with response context mirroring /auth/me)
"""

import logging
import time
import json
import asyncio
import re
from typing import Optional, List, Dict, Any, Tuple  # Added Tuple
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from user_db.models import Admin
from .initialize import get_dual_retriever
# --- Authentication Imports ---
# Import the dependency function to get the current user
try:
    from auth.utils import get_current_account
except ImportError:
    # Fallback if auth module structure is different
    try:
        from ..auth.utils import get_current_account
    except ImportError:
        logging.error(
            "Could not import get_current_current dependency. Auth will not work."
        )

        # Define a placeholder dependency that raises an error if auth is required but missing
        async def get_current_account():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication module not configured correctly.",
            )


# Import the User model and related models for type hinting and context extraction
try:
    from user_db.models import (
        User,
        EnrolledCourse,
        CourseGrade,
        Term,
        Course,
    )  # Ensure these are correct
except ImportError:
    logging.warning(
        "Could not import User model or related DB models. Type hinting may be affected."
    )
    # Define placeholder types if models aren't available
    User = Any
    EnrolledCourse = Any
    CourseGrade = Any
    Term = Any
    Course = Any


# --- RAG Component Imports ---
# Ensure these imports are correct relative to your project structure
try:
    # Assuming models.py defines these Pydantic models
    from .models import QueryRequest, QueryResponse, SwitchLLMRequest, MessageModel
    from .initialize import (
        get_ensemble_retriever,
        get_llm,
        rerank_with_crossencoder,
        switch_llm_backend,
        get_model_info,
    )
    from .prompts import get_prompts_dict  # Load prompts function
    from .retrievers import get_doc_id as get_consistent_doc_id  # Consistent ID helper
except ImportError as e:
    logging.error(
        f"Error importing RAG components or prompts: {e}. Check module paths.",
        exc_info=True,
    )
    # Define placeholders or raise error if critical components missing
    get_ensemble_retriever = lambda: None
    get_llm = lambda: None
    rerank_with_crossencoder = lambda query, docs: docs  # Passthrough
    get_prompts_dict = lambda: {
        "default_prompt": "Context: {context}\nQuestion: {question}\nAnswer:"
    }  # Basic fallback
    get_consistent_doc_id = lambda doc: getattr(doc, "id", id(doc))

    # Define placeholder models if needed, or let it fail on endpoint definition
    class QueryRequest(BaseModel):
        query: str

    # Ensure QueryResponse expects the Dict for user_context
    class QueryResponse(BaseModel):
        answer: str
        processing_time: float
        context: str
        user_context: Dict[str, Any]

    class SwitchLLMRequest(BaseModel):
        backend: str


# --- Router Setup ---
router = APIRouter(
    prefix="/rag",
    tags=["RAG QA"],
    responses={
        404: {"description": "Not found"},
        401: {"description": "Unauthorized"},
    },
)

logger = logging.getLogger(__name__)

# --- Helper Functions ---


def format_documents_for_llm(docs: List[Any]) -> str:
    """Formats documents, extracting source and key metadata."""
    if not docs:
        return "No relevant documents found."
    formatted_docs = []
    for i, doc in enumerate(docs):
        try:
            metadata = getattr(doc, "metadata", {})
            # Try standard metadata keys, fallback to generic naming
            source_filename = metadata.get(
                "source", metadata.get("source_file", f"Unknown_Source_{i+1}")
            )
            doc_header = f"\n--- SOURCE [{source_filename}] ---\n"
            # Define keys you expect/want to show from metadata
            metadata_keys_to_show = [
                "title",
                "heading",
                "department",
                "faculty",
                "doc_type",
                "course_codes",
                "credits",
                "level",
                "semester",
                "requirement_type",
                "policy_area",
                "chunk_index",
                "chunk_count",
                # Add any other relevant metadata keys here
            ]
            for key in metadata_keys_to_show:
                if key in metadata:
                    value = metadata[key]
                    # Format list values nicely
                    value_str = (
                        ", ".join(map(str, value))
                        if isinstance(value, list)
                        else str(value)
                    )
                    # Only add if value has content and isn't just placeholder/empty
                    if (
                        value_str
                        and value_str.strip()
                        and value_str.lower() not in ["n/a", "none", ""]
                    ):
                        doc_header += f"{key.upper().replace('_', ' ')}: {value_str}\n"

            doc_header += "CONTENT:\n"
            # Get page content, default to empty string if missing
            page_content = str(getattr(doc, "page_content", ""))
            formatted_docs.append(f"{doc_header}{page_content.strip()}\n")
        except Exception as e:
            source_display = metadata.get(
                "source_file", f"Unknown_Source_{i+1}"
            )  # Fallback source display
            logger.error(
                f"Error formatting doc from {source_display} (idx {i}): {e}",
                exc_info=True,
            )
            formatted_docs.append(
                f"\n--- SOURCE [{source_display}] --- (Error formatting document) ---\n"
            )
    return "".join(formatted_docs)

def format_message_history_for_llm(history: Optional[List[MessageModel]]) -> str:
    """Formats chat history into a string for the LLM prompt."""
    if not history:
        return "No previous conversation history."
    
    formatted_history = []
    for msg in history:
        role = "User" if msg.sender.lower() == "user" else "Assistant"
        formatted_history.append(f"{role}: {msg.content}")
    return "\n".join(formatted_history)

def classify_and_enrich_documents(docs: List[Any], query: str) -> List[Any]:
    """Classifies documents based on content and adds metadata."""
    if not docs:
        return []

    # Simple keyword/regex based classification - adapt as needed
    query_keywords = set(query.lower().split())
    course_code_pattern = re.compile(r"\b([A-Z]{4}\d{4})\b")  # Example: ABCD1234
    prereq_pattern = r"\b(?:pre[- ]?requisites?|requirements?|mandatory|must have)\b"
    policy_pattern = r"\b(?:policy|policies|regulation|rules|guidelines?)\b"
    description_pattern = r"\b(?:description|aims?|objectives?|outline|syllabus)\b"

    for doc in docs:
        # Ensure metadata exists and is a dict
        if not hasattr(doc, "metadata") or not isinstance(doc.metadata, dict):
            doc.metadata = {}

        content = str(getattr(doc, "page_content", ""))
        content_lower = content.lower()

        # Determine document type
        doc_type = "general"  # Default type
        course_codes_found = course_code_pattern.findall(
            content
        )  # Find all course codes

        # Classification logic (priority matters)
        if re.search(policy_pattern, content_lower):
            doc_type = "policy"
        elif re.search(prereq_pattern, content_lower):
            doc_type = "requirement"
        elif course_codes_found and re.search(description_pattern, content_lower):
            doc_type = "course_description"
        elif course_codes_found:
            # Could be a listing, schedule, etc. if not clearly a description
            doc_type = "course_listing"
        # Add more rules as needed (e.g., faculty info, contact pages)

        doc.metadata["doc_type"] = doc_type

        # Add found course codes to metadata if any
        if course_codes_found:
            # Store unique, sorted codes
            doc.metadata["course_codes"] = sorted(list(set(course_codes_found)))

    return docs


def get_chosen_prompt(query: str, docs: List[Any], prompts: Dict[str, Any]):
    """Selects an appropriate prompt template based on query/document analysis."""
    if not prompts:
        logger.error("Prompts dictionary is empty!")
        return None  # Or raise an error

    default_prompt = prompts.get("default_prompt")
    if not default_prompt:
        logger.error("Default prompt is missing from prompts dictionary!")
        # Try to grab *any* prompt as a last resort
        return next(iter(prompts.values()), None) if prompts else None

    query_lower = query.lower()
    doc_types = (
        [doc.metadata.get("doc_type", "general") for doc in docs] if docs else []
    )

    # --- Prompt Selection Logic (Customize extensively based on your prompts) ---

    # Example: Prioritize requirement/credit related prompts
    prereq_pattern = r"\b(?:pre[- ]?requisites?|requirements?)\b"
    is_prereq_query = bool(re.search(prereq_pattern, query_lower))
    if (
        any(k in query_lower for k in ["credit", "graduate", "requirement", "gpa"])
        or "requirement" in doc_types
        or is_prereq_query
    ):
        chosen = prompts.get("credit_prompt", default_prompt)
        logger.debug(
            f"Choosing prompt: {'credit_prompt' if chosen != default_prompt else 'default_prompt (fallback)'}"
        )
        return chosen

    # Example: Course related prompts
    has_course_code = bool(re.search(r"\b[A-Z]{4}\d{4}\b", query, re.IGNORECASE))
    if (
        has_course_code
        or any(
            k in query_lower
            for k in ["course", "class", "subject", "module", "offering"]
        )
        or any(dt in doc_types for dt in ["course_description", "course_listing"])
    ):
        chosen = prompts.get("course_prompt", default_prompt)
        logger.debug(
            f"Choosing prompt: {'course_prompt' if chosen != default_prompt else 'default_prompt (fallback)'}"
        )
        return chosen

    # Add more specific prompt selection rules here based on keywords or doc_types

    # Fallback to default
    logger.debug("Choosing prompt: default_prompt")
    return default_prompt


def expand_query(query: str) -> List[str]:
    """Basic query expansion (stub). Implement more sophisticated expansion if needed."""
    expanded = {query}
    query_lower = query.lower()
    # Example: Add "courses" if not present
    if " course" not in query_lower and not query_lower.endswith(" course"):
        expanded.add(query + " courses")
    # Add more expansion logic here (synonyms, acronyms, etc.)
    return list(expanded)


import logging
from typing import Tuple, Dict, Any, List, Optional
from datetime import (
    datetime,
)  # Keep if used for anything else, not strictly needed in this function now

# Assuming User, EnrolledCourse, CourseGrade, Term, Course models are imported
# and have the necessary attributes and relationships defined (e.g., grade.term, grade.course)
try:
    from user_db.models import (
        User,
        EnrolledCourse,
        CourseGrade,
        Term,
        Course,
    )  # Ensure these are correct
except ImportError:
    logging.warning(
        "Could not import User model or related DB models. Type hinting may be affected."
    )
    # Define placeholder types if models aren't available
    User = Any
    EnrolledCourse = Any
    CourseGrade = Any
    Term = Any
    Course = Any

logger = logging.getLogger(__name__)

import logging
import json
from typing import Tuple, Dict, Any, List, Optional
from datetime import datetime
import asyncio

# Assuming User, EnrolledCourse, CourseGrade, Term, Course models are imported
try:
    from user_db.models import User, EnrolledCourse, CourseGrade, Term, Course
except ImportError:
    logging.warning(
        "Could not import User model or related DB models. Type hinting may be affected."
    )
    # Define placeholder types if models aren't available
    User = Any
    EnrolledCourse = Any
    CourseGrade = Any
    Term = Any
    Course = Any

# Import credit check function
try:
    from academic.router import credit_check
    from user_db.database import get_db, AsyncSession
except ImportError:
    logging.warning(
        "Could not import credit_check function. Graduation analysis will be unavailable."
    )
    credit_check = None
    get_db = None
    AsyncSession = Any

logger = logging.getLogger(__name__)


# Define the custom JSON encoder (add this at the top of the file with other imports)
class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return super().default(obj)


# Now the updated extract_user_context function
async def extract_user_context(
    current_user: User,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Extracts user context by RECONSTRUCTING grades data from DB relationships
    to ensure freshness. Formats one part to mirror /auth/me and another
    part with flat fields for prompt formatting. Includes credit check report
    and enrollment year.

    Accesses course_code, course_title, credit_hours directly from the
    CourseGrade object based on the latest model information.

    Returns:
        Tuple[Dict[str, Any], Dict[str, Any]]:
            - auth_me_like_context: Dictionary structured like the /auth/me response.
            - prompt_fields: Dictionary with flat fields for LLM prompt formatting.
    """
    # Initialize the structure mirroring /auth/me
    auth_me_like_context = {
        "moodle_data": {
            "user_info": {},
            "courses": {"courses": [], "nextoffset": None},
        },
        "grades_status": {
            "fetched": False,
            "success": False,
            "error": "Initialization error.",
        },
        "grades_data": {
            "student_name": "",
            "student_id": "",
            "terms": [],
            "overall": {
                "cumulative_gpa": None,
                "degree_gpa": None,
                "total_credits_earned": None,
            },
        },
        "credit_check": {
            "status": "not_fetched",
            "error": None,
            "analysis": None,
            "reports": None,
        },
    }

    # Initialize the dictionary for prompt formatting fields
    prompt_fields = {
        "user_name": "N/A",
        "student_id": "N/A",
        "enrollment_year": "N/A", # <-- ADDED ENROLLMENT YEAR
        "user_gpa": "N/A",
        "total_credits": "N/A",
        "user_courses_summary": "N/A",
        "current_courses": [],
        "grade_history": [],
        "grades_data_raw": None,
        "graduation_status_json": "{}",
        "graduation_report_text": "No credit check analysis available.",
        "graduation_summary": "Unknown",
        "potential_graduation_json": "{}",
        "potential_summary": "Unknown",
    }

    try:
        # --- Populate User Info ---
        user_name = f"{getattr(current_user, 'firstname', '')} {getattr(current_user, 'lastname', '')}".strip()
        student_id = getattr(current_user, "student_id", "N/A")
        email = getattr(current_user, "email", "N/A")

        auth_me_like_context["moodle_data"]["user_info"] = {
            "name": user_name,
            "email": email,
            "student_id": student_id,
        }
        prompt_fields["user_name"] = user_name
        prompt_fields["student_id"] = student_id

        # --- Populate Moodle Courses (from enrollments relationship) ---
        # ... (rest of this section remains the same)
        current_courses_list_for_prompt = []
        if hasattr(current_user, "enrollments") and current_user.enrollments:
            for enrollment in current_user.enrollments:
                if hasattr(enrollment, "course") and enrollment.course:
                    course = enrollment.course
                    course_data_auth = {
                        "id": getattr(course, "id", None),
                        "fullname": getattr(course, "fullname", "Unknown Course Name"),
                        "shortname": getattr(course, "shortname", None),
                        "idnumber": getattr(course, "idnumber", None),
                        "summary": getattr(course, "summary", None),
                        "summaryformat": getattr(course, "summaryformat", 1),
                        "startdate": int(getattr(course, "startdate", 0)),
                        "enddate": int(getattr(course, "enddate", 0)),
                        "visible": getattr(course, "visible", True),
                        "showactivitydates": getattr(
                            course, "showactivitydates", False
                        ),
                        "showcompletionconditions": getattr(
                            course, "showcompletionconditions", None
                        ),
                        "fullnamedisplay": getattr(
                            course, "fullname", "Unknown Course Name"
                        ),
                        "viewurl": f"/course/view.php?id={getattr(course, 'id', '')}",
                        "coursecategory": getattr(
                            course, "coursecategory", "Unknown"
                        ),
                    }
                    auth_me_like_context["moodle_data"]["courses"]["courses"].append(
                        course_data_auth
                    )
                    shortname = getattr(course, "shortname", "Unknown")
                    code = (
                        shortname.split()[0] if shortname != "Unknown" else "Unknown"
                    )
                    prompt_course_data = {
                        "code": code,
                        "name": getattr(course, "fullname", "Unknown Course Name"),
                        "id": getattr(course, "id", None),
                        "full_shortname": shortname,
                        "idnumber": getattr(course, "idnumber", None),
                        "status": getattr(
                            enrollment, "status", "Enrolled"
                        ),
                    }
                    current_courses_list_for_prompt.append(prompt_course_data)
        prompt_fields["current_courses"] = current_courses_list_for_prompt
        if current_courses_list_for_prompt:
            prompt_fields["user_courses_summary"] = ", ".join(
                [c.get("code", "Unknown") for c in current_courses_list_for_prompt]
            )


        # --- Populate Grades Data & Status ---
        grades_available = False
        all_term_codes_for_enrollment_year = [] # For enrollment year calculation

        if hasattr(current_user, "grades") and current_user.grades:
            logger.info(
                "Reconstructing grades_data from user DB relationships (terms/grades)."
            )
            grades_available = True
            auth_me_like_context["grades_data"]["student_name"] = user_name
            auth_me_like_context["grades_data"]["student_id"] = student_id
            terms_dict = {}

            if hasattr(current_user, "terms") and current_user.terms:
                for term in current_user.terms:
                    term_code = getattr(term, "term_code", "UnknownTerm")
                    if term_code and term_code != "CURRENT" and term_code.isdigit() and len(term_code) >= 4:
                        all_term_codes_for_enrollment_year.append(term_code)
                    terms_dict[term_code] = {
                        "term_code": term_code,
                        "courses": [],
                        "semester_gpa": getattr(term, "semester_gpa", None),
                        "cumulative_gpa": getattr(term, "cumulative_gpa", None),
                        "degree_gpa": getattr(term, "degree_gpa", None),
                        "credits_earned_to_date": getattr(
                            term, "credits_earned_to_date", None
                        ),
                    }

            grade_history_for_prompt = []
            for grade in current_user.grades:
                term_obj = getattr(grade, "term", None)
                term_code = (
                    getattr(term_obj, "term_code", "UnknownTerm")
                    if term_obj
                    else "UnknownTerm"
                )
                # Also collect term codes from grades if not already present from terms relationship
                if term_code and term_code != "CURRENT" and term_code.isdigit() and len(term_code) >=4 and term_code not in all_term_codes_for_enrollment_year:
                    all_term_codes_for_enrollment_year.append(term_code)


                course_code = getattr(grade, "course_code", "Unknown")
                course_title = getattr(grade, "course_title", "Unknown Title")
                credit_hours = getattr(
                    grade, "credit_hours", 3.0
                )

                course_entry_auth = {
                    "course_code": course_code,
                    "course_title": course_title,
                    "credit_hours": credit_hours,
                    "grade_earned": getattr(
                        grade, "grade_earned", "NA"
                    ),
                    "whatif_grade": getattr(
                        grade, "whatif_grade", None
                    ),
                }

                if term_code not in terms_dict:
                    terms_dict[term_code] = {
                        "term_code": term_code,
                        "courses": [],
                        "semester_gpa": None,
                        "cumulative_gpa": None,
                        "degree_gpa": None,
                        "credits_earned_to_date": None,
                    }
                terms_dict[term_code]["courses"].append(course_entry_auth)

                grade_history_for_prompt.append(
                    {
                        "term": term_code,
                        "course_code": course_code,
                        "course_title": course_title,
                        "credit_hours": credit_hours,
                        "grade": course_entry_auth[
                            "grade_earned"
                        ],
                    }
                )

            auth_me_like_context["grades_data"]["terms"] = list(terms_dict.values())
            auth_me_like_context["grades_data"]["terms"].sort(
                key=lambda t: (
                    "0"
                    if t.get("term_code") == "CURRENT"
                    else str(t.get("term_code", "Z"))
                ),
                reverse=True,
            )

            prompt_fields["grade_history"] = grade_history_for_prompt
            prompt_fields["grades_data_raw"] = auth_me_like_context[
                "grades_data"
            ]
            auth_me_like_context["grades_status"] = {
                "fetched": True,
                "success": True,
                "error": None,
            }

            reconstructed_non_current = [
                t
                for t in auth_me_like_context["grades_data"]["terms"]
                if t.get("term_code") != "CURRENT"
                and t.get("cumulative_gpa") is not None
            ]
            if reconstructed_non_current:
                recent_reconstructed_term = reconstructed_non_current[0]
                prompt_fields["user_gpa"] = str(
                    recent_reconstructed_term["cumulative_gpa"]
                )
                if recent_reconstructed_term.get("credits_earned_to_date") is not None:
                    prompt_fields["total_credits"] = str(
                        recent_reconstructed_term["credits_earned_to_date"]
                    )
            else:
                logger.warning(
                    f"Could not determine overall GPA/Credits from reconstructed terms for user {student_id}."
                )
            
            # --- Calculate Enrollment Year ---
            if all_term_codes_for_enrollment_year:
                # Filter out any non-numeric or malformed codes just in case, though previous checks help
                valid_year_codes = [tc for tc in all_term_codes_for_enrollment_year if tc.isdigit() and len(tc) >= 4]
                if valid_year_codes:
                    earliest_term_code = min(valid_year_codes)
                    prompt_fields["enrollment_year"] = earliest_term_code[:4]
                    # Optionally, add to auth_me_like_context if useful elsewhere
                    # auth_me_like_context["moodle_data"]["user_info"]["enrollment_year"] = earliest_term_code[:4]
                else:
                    logger.warning(f"No valid numeric term codes found to determine enrollment year for user {student_id}.")
            else:
                logger.warning(f"No term codes found to determine enrollment year for user {student_id}.")


        else:
            logger.warning(
                f"No grade data relationships found for user {student_id}. Grades context will be empty."
            )
            auth_me_like_context["grades_status"] = {
                "fetched": False,
                "success": False,
                "error": "No grade data available for user in DB relationships.",
            }
            auth_me_like_context["grades_data"]["student_name"] = user_name
            auth_me_like_context["grades_data"]["student_id"] = student_id
            prompt_fields["grades_data_raw"] = auth_me_like_context[
                "grades_data"
            ]

        # --- Run Credit Check Analysis if Available ---
        # ... (rest of this section remains the same) ...
        if credit_check and get_db and grades_available:
            try:
                async_session = None
                db_iterator = get_db()
                try:
                    async_session = (
                        await anext(db_iterator)
                        if hasattr(db_iterator, "__anext__")
                        else next(db_iterator)
                    )
                except (StopAsyncIteration, StopIteration):
                    logger.error("Failed to get database session for credit check")

                if async_session:
                    credit_check_result = await credit_check(
                        current_user, async_session
                    )
                    auth_me_like_context["credit_check"] = {
                        "status": "fetched",
                        "error": None,
                        "analysis": credit_check_result["analysis"],
                        "reports": credit_check_result["reports"],
                    }
                    prompt_fields["graduation_status_json"] = json.dumps(
                        credit_check_result["analysis"],
                        ensure_ascii=False,
                        cls=SetEncoder,
                    )
                    prompt_fields["graduation_report_text"] = credit_check_result[
                        "reports"
                    ]
                    eligible = credit_check_result["analysis"][
                        "eligible_for_graduation"
                    ]
                    prompt_fields["graduation_summary"] = (
                        "Eligible for graduation"
                        if eligible
                        else "Not eligible for graduation"
                    )
                    potential_result = credit_check_result["analysis"].get(
                        "potential_graduation", {}
                    )
                    if not potential_result:
                        try:
                            from academic.credit_check import (
                                check_potential_graduation_standardized,
                            )
                            potential_result = check_potential_graduation_standardized(
                                credit_check_result["analysis"], student_info=None
                            )
                        except ImportError:
                            logger.warning(
                                "Could not import potential graduation check function"
                            )
                            potential_result = {}
                    prompt_fields["potential_graduation_json"] = json.dumps(
                        potential_result, ensure_ascii=False, cls=SetEncoder
                    )
                    potential_eligible = potential_result.get(
                        "potential_graduate", False
                    )
                    prompt_fields["potential_summary"] = (
                        "Potentially eligible for graduation"
                        if potential_eligible
                        else "Not potentially eligible for graduation"
                    )
                else:
                    logger.error("No database session available for credit check")
                    auth_me_like_context["credit_check"][
                        "error"
                    ] = "Database session unavailable"
            except Exception as e:
                logger.error(
                    f"Error during credit check for user {student_id}: {e}",
                    exc_info=True,
                )
                auth_me_like_context["credit_check"] = {
                    "status": "error",
                    "error": str(e),
                    "analysis": None,
                    "reports": None,
                }
        else:
            reason = (
                "Credit check function unavailable"
                if not credit_check
                else "No grade data available"
            )
            auth_me_like_context["credit_check"]["error"] = reason
            logger.info(f"Credit check not performed: {reason}")

    except Exception as e:
        logger.error(
            f"Error during user context extraction for user {student_id}: {e}",
            exc_info=True,
        )
        auth_me_like_context["grades_status"] = {
            "fetched": False,
            "success": False,
            "error": f"Internal server error during context extraction: {e}",
        }
        auth_me_like_context["credit_check"]["error"] = f"Context extraction error: {e}"
        if not auth_me_like_context["moodle_data"]["user_info"]:
            auth_me_like_context["moodle_data"]["user_info"] = {
                "name": "Error",
                "email": "Error",
                "student_id": "Error",
            }
        if not auth_me_like_context["grades_data"]["student_name"]:
            auth_me_like_context["grades_data"]["student_name"] = (
                user_name if "user_name" in locals() else "Error"
            )
            auth_me_like_context["grades_data"]["student_id"] = (
                student_id if "student_id" in locals() else "Error"
            )

    prompt_fields["grade_history_json"] = json.dumps(
        prompt_fields.get("grade_history", []), ensure_ascii=False, cls=SetEncoder
    )
    return auth_me_like_context, prompt_fields


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(
    request: QueryRequest, current_user: User | Admin = Depends(get_current_account) # type: ignore
):
    start_time = time.perf_counter()
    user_query = request.query.strip()
    chat_history_messages = request.history 
    filters = request.filters # Assuming filters are handled by retriever if passed

    if not user_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    logger.info(
        f"Received query from user {getattr(current_user, 'id', 'UNKNOWN_USER_ID')} "
        f"({getattr(current_user,'student_id','UNKNOWN_STUDENT_ID')}): '{user_query}' "
        f"with {len(chat_history_messages) if chat_history_messages else 0} history messages."
    )

    # 1. Load retriever, LLM, prompts - USING DUAL RETRIEVER
    retriever = get_dual_retriever()  # Use dual retriever instead of ensemble_retriever
    llm = get_llm()
    if not retriever:
        raise HTTPException(status_code=503, detail="Retriever service unavailable.")
    if not llm:
        raise HTTPException(status_code=503, detail="LLM service unavailable.")
    prompts = get_prompts_dict()

    # 2. Query analysis & expansion
    analysis_start = time.perf_counter()
    is_course_code_query = bool(re.search(r"\b[A-Z]{4}\d{4}\b", user_query, re.IGNORECASE))
    is_complex_query = len(user_query.split()) >= 10 # Example threshold
    prereq_pattern = r"\b(?:pre[- ]?requisites?|requirements?)\b"
    is_requirement_query = bool(re.search(prereq_pattern, user_query.lower())) or any(
        w in user_query.lower() for w in ["credit", "graduate", "policy", "rule", "eligible"]
    )
    should_expand = True # Default to expand
    if is_course_code_query and any(kw in user_query.lower() for kw in ["credit", "title", "name", "number", "description", "lecturer"]):
        # If it's a specific info request about a known course code, maybe don't expand.
        should_expand = False 
        logger.info("Specific course-info query detected; skipping broad expansion.")
    
    expanded_queries = expand_query(user_query) if should_expand else [user_query]
    analysis_time = time.perf_counter() - analysis_start
    logger.info(f"Query analysis & expansion took {analysis_time:.4f}s. Queries: {expanded_queries}")

    # 3. Retrieval - USING DUAL RETRIEVER
    retrieval_start = time.perf_counter()
    all_initial_docs = []
    for eq in expanded_queries:
        try:
            # Using dual retriever here
            docs_for_eq = retriever.get_relevant_documents(eq) 
            all_initial_docs.extend(docs_for_eq)
        except Exception as e_ret:
            logger.error(f"Error retrieving documents for query '{eq}': {e_ret}", exc_info=True)
    retrieval_time = time.perf_counter() - retrieval_start
    logger.info(f"Initial retrieval of {len(all_initial_docs)} documents took {retrieval_time:.4f}s")

    # 4. Deduplication
    dedup_start = time.perf_counter()
    unique_docs_map: Dict[str, Any] = {}
    for doc in all_initial_docs:
        doc_id = get_consistent_doc_id(doc) # Ensure this helper is robust
        if doc_id not in unique_docs_map: # Keep first encountered
            unique_docs_map[doc_id] = doc
    initial_docs = list(unique_docs_map.values())
    dedup_time = time.perf_counter() - dedup_start
    logger.info(f"Deduplicated to {len(initial_docs)} documents in {dedup_time:.4f}s")

    # 5. Extract & serialize user context
    auth_me_like_context, prompt_fields = await extract_user_context(current_user)

    if not initial_docs:
        logger.info("No relevant documents found after retrieval and deduplication.")
        return QueryResponse(
            answer="I could not find any relevant documents based on your query. Please try rephrasing or check your filters.",
            processing_time=time.perf_counter() - start_time,
            context="No relevant documents found.",
            user_context=auth_me_like_context, # Return user context even if no docs
        )

    # 6. Re-ranking
    rerank_start = time.perf_counter()
    try:
        # Pass the original user_query for reranking, not expanded ones individually
        reranked_docs = rerank_with_crossencoder(user_query, initial_docs) 
    except Exception as e_rerank:
        logger.error(f"Re-ranking failed: {e_rerank}. Using initial docs.", exc_info=True)
        reranked_docs = initial_docs # Fallback to non-reranked if error
    rerank_time = time.perf_counter() - rerank_start
    logger.info(f"Re-ranking {len(initial_docs)} docs took {rerank_time:.4f}s. Resulted in {len(reranked_docs)} docs.")

    # 7. Dynamic context size selection
    context_doc_count = 10 # Default
    if is_course_code_query and not is_complex_query: # Specific course, simple question
        context_doc_count = 8
    elif is_complex_query or is_requirement_query: # Complex or requirement based
        context_doc_count = 15
    # Ensure it doesn't exceed available docs
    context_doc_count = min(context_doc_count, len(reranked_docs))
    logger.info(f"Dynamic context size selected: {context_doc_count} documents.")

    # 8. Smart document selection for diversity
    selection_start = time.perf_counter()
    # Consider top N candidates for diversity selection, e.g., twice the context_doc_count
    candidates_for_diversity_count = min(context_doc_count * 2, len(reranked_docs))
    top_candidates = reranked_docs[:candidates_for_diversity_count]
    
    selected_docs_for_context = []
    seen_sources: set[str] = set()
    # Prioritize unique sources for the first half of the context
    half_context_count = context_doc_count // 2

    for doc in top_candidates:
        if len(selected_docs_for_context) >= context_doc_count:
            break
        source = str(doc.metadata.get("source", doc.metadata.get("source_file", "unknown_source")))
        
        if source not in seen_sources or len(selected_docs_for_context) < half_context_count:
            selected_docs_for_context.append(doc)
            if source != "unknown_source":
                seen_sources.add(source)
    
    # If still need more docs, fill from top_candidates, allowing duplicates from same source
    if len(selected_docs_for_context) < context_doc_count:
        needed_more = context_doc_count - len(selected_docs_for_context)
        current_selected_ids = {get_consistent_doc_id(d) for d in selected_docs_for_context}
        
        for doc in top_candidates: # Iterate again over candidates
            if needed_more == 0:
                break
            doc_id = get_consistent_doc_id(doc)
            if doc_id not in current_selected_ids:
                selected_docs_for_context.append(doc)
                current_selected_ids.add(doc_id) # Track added IDs
                needed_more -= 1
    
    # Final list of documents for context, sorted by original reranked score
    # This ensures the most relevant (by reranker) are still generally at the top
    # if they made it through diversity selection.
    final_top_docs = sorted(selected_docs_for_context, key=lambda d: reranked_docs.index(d))
    selection_time = time.perf_counter() - selection_start
    logger.info(f"Smart selection of {len(final_top_docs)} docs from {len(top_candidates)} candidates took {selection_time:.4f}s.")

    # 9. Classify & enrich
    enrichment_start = time.perf_counter()
    enriched_docs = classify_and_enrich_documents(final_top_docs, user_query)
    enrichment_time = time.perf_counter() - enrichment_start
    logger.info(f"Document enrichment took {enrichment_time:.4f}s.")

    # 10. Format for LLM
    formatting_start = time.perf_counter()
    formatted_retrieved_context = format_documents_for_llm(enriched_docs)
    formatting_time = time.perf_counter() - formatting_start
    logger.info(f"Context formatting for LLM took {formatting_time:.4f}s.")

    # Format chat history
    formatted_chat_history = format_message_history_for_llm(chat_history_messages)

    # 11. Choose & build prompt
    prompt_selection_start = time.perf_counter()
    chosen_prompt_object = get_chosen_prompt(user_query, enriched_docs, prompts)
    if not chosen_prompt_object: # Fallback if selection fails
        logger.warning("Failed to get a chosen prompt, falling back to default.")
        chosen_prompt_object = prompts.get("default_prompt")
    
    # Identify prompt name for logging (handle if not a LangChain PromptTemplate)
    prompt_name = "unknown_prompt"
    if isinstance(chosen_prompt_object, str): # Simple string prompt
        # Try to find its key in the prompts dict
        prompt_name = next((name for name, tmpl in prompts.items() if tmpl == chosen_prompt_object), "custom_string_prompt")
    elif hasattr(chosen_prompt_object, 'template'): # LangChain PromptTemplate
         prompt_name = next((name for name, tmpl in prompts.items() if tmpl is chosen_prompt_object), "langchain_prompt")

    prompt_selection_time = time.perf_counter() - prompt_selection_start
    logger.info(f"Using prompt '{prompt_name}' (Selection took {prompt_selection_time:.4f}s)")
    
    # Prepare format_args including chat_history
    format_args = {
        "context": formatted_retrieved_context,
        "question": user_query,
        "chat_history": formatted_chat_history, 
        "current_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z"),
        **prompt_fields, 
    }
    
    try:
        if hasattr(chosen_prompt_object, "input_variables"): # LangChain PromptTemplate
            # Ensure all input_variables are present in format_args, defaulting to "N/A"
            final_format_args = {
                key: format_args.get(key, "N/A") 
                for key in chosen_prompt_object.input_variables
            }
            # Log if any expected variables were missing from format_args and defaulted
            missing_vars = [k for k in chosen_prompt_object.input_variables if k not in format_args]
            if missing_vars:
                logger.warning(f"Prompt '{prompt_name}' missing variables, defaulted to 'N/A': {missing_vars}")
            
            prompt_str = chosen_prompt_object.format(**final_format_args)
        elif isinstance(chosen_prompt_object, str): # Simple f-string like template
            # Use format_map for safety with f-strings if some keys might be missing
            # This requires a dictionary where missing keys don't raise KeyError
            class DefaultDict(dict):
                def __missing__(self, key: Any) -> str:
                    logger.warning(f"Prompt formatting: Key '{key}' not found in format_args, using 'N/A'.")
                    return "N/A"
            prompt_str = chosen_prompt_object.format_map(DefaultDict(format_args))
        else:
            logger.error(f"Chosen prompt object is of unexpected type: {type(chosen_prompt_object)}")
            raise HTTPException(status_code=500, detail="Internal error: Invalid prompt object.")

    except KeyError as e_key:
        logger.error(f"Missing key {e_key} in prompt formatting for '{prompt_name}'. Available keys: {list(format_args.keys())}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: missing key {e_key} for prompt.")
    except Exception as e_fmt:
        logger.error(f"Error formatting prompt '{prompt_name}': {e_fmt}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error formatting prompt.")

    # 12. Call LLM
    llm_start = time.perf_counter()
    try:
        answer_obj = llm.invoke(prompt_str)
        final_answer = getattr(answer_obj, "content", str(answer_obj))
    except Exception as e_llm:
        logger.error(f"LLM call failed: {e_llm}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"LLM service error: {str(e_llm)}")
    llm_time = time.perf_counter() - llm_start
    logger.info(f"LLM generation took {llm_time:.4f}s")

    # 13. Return response
    total_time = time.perf_counter() - start_time
    logger.info(f"Total processing time for query: {total_time:.4f}s")
    return QueryResponse(
        answer=final_answer.strip(),
        processing_time=total_time,
        context=formatted_retrieved_context, 
        user_context=auth_me_like_context,
    )
# @router.post("/query", response_model=QueryResponse)
# async def query_endpoint(
#     request: QueryRequest, current_user: User | Admin = Depends(get_current_account) # type: ignore
# ):
#     start_time = time.perf_counter()
#     user_query = request.query.strip()
#     chat_history_messages = request.history 
#     filters = request.filters # Assuming filters are handled by retriever if passed

#     if not user_query:
#         raise HTTPException(status_code=400, detail="Query cannot be empty.")

#     logger.info(
#         f"Received query from user {getattr(current_user, 'id', 'UNKNOWN_USER_ID')} "
#         f"({getattr(current_user,'student_id','UNKNOWN_STUDENT_ID')}): '{user_query}' "
#         f"with {len(chat_history_messages) if chat_history_messages else 0} history messages."
#     )

#     # 1. Load retriever, LLM, prompts
#     ensemble_ret = get_ensemble_retriever()
#     llm = get_llm()
#     if not ensemble_ret:
#         raise HTTPException(status_code=503, detail="Retriever service unavailable.")
#     if not llm:
#         raise HTTPException(status_code=503, detail="LLM service unavailable.")
#     prompts = get_prompts_dict()

#     # 2. Query analysis & expansion (Restored from user's original)
#     analysis_start = time.perf_counter()
#     is_course_code_query = bool(re.search(r"\b[A-Z]{4}\d{4}\b", user_query, re.IGNORECASE))
#     is_complex_query = len(user_query.split()) >= 10 # Example threshold
#     prereq_pattern = r"\b(?:pre[- ]?requisites?|requirements?)\b"
#     is_requirement_query = bool(re.search(prereq_pattern, user_query.lower())) or any(
#         w in user_query.lower() for w in ["credit", "graduate", "policy", "rule", "eligible"]
#     )
#     should_expand = True # Default to expand
#     if is_course_code_query and any(kw in user_query.lower() for kw in ["credit", "title", "name", "number", "description", "lecturer"]):
#         # If it's a specific info request about a known course code, maybe don't expand.
#         should_expand = False 
#         logger.info("Specific course-info query detected; skipping broad expansion.")
    
#     expanded_queries = expand_query(user_query) if should_expand else [user_query]
#     analysis_time = time.perf_counter() - analysis_start
#     logger.info(f"Query analysis & expansion took {analysis_time:.4f}s. Queries: {expanded_queries}")

#     # 3. Retrieval (Restored from user's original)
#     retrieval_start = time.perf_counter()
#     all_initial_docs = []
#     # Pass filters to retriever if your retriever supports it.
#     # For example: ensemble_ret.get_relevant_documents(eq, filters=filters)
#     for eq in expanded_queries:
#         try:
#             # Assuming retriever handles filters if provided, else modify call
#             docs_for_eq = ensemble_ret.get_relevant_documents(eq) 
#             all_initial_docs.extend(docs_for_eq)
#         except Exception as e_ret:
#             logger.error(f"Error retrieving documents for query '{eq}': {e_ret}", exc_info=True)
#     retrieval_time = time.perf_counter() - retrieval_start
#     logger.info(f"Initial retrieval of {len(all_initial_docs)} documents took {retrieval_time:.4f}s")

#     # 4. Deduplication (Restored from user's original)
#     dedup_start = time.perf_counter()
#     unique_docs_map: Dict[str, Any] = {}
#     for doc in all_initial_docs:
#         doc_id = get_consistent_doc_id(doc) # Ensure this helper is robust
#         if doc_id not in unique_docs_map: # Keep first encountered
#             unique_docs_map[doc_id] = doc
#     initial_docs = list(unique_docs_map.values())
#     dedup_time = time.perf_counter() - dedup_start
#     logger.info(f"Deduplicated to {len(initial_docs)} documents in {dedup_time:.4f}s")

#     # 5. Extract & serialize user context (This was correctly placed)
#     auth_me_like_context, prompt_fields = await extract_user_context(current_user)
#     # Ensure grade_history_json is in prompt_fields from extract_user_context
#     # It's added at the end of extract_user_context

#     if not initial_docs:
#         logger.info("No relevant documents found after retrieval and deduplication.")
#         return QueryResponse(
#             answer="I could not find any relevant documents based on your query. Please try rephrasing or check your filters.",
#             processing_time=time.perf_counter() - start_time,
#             context="No relevant documents found.",
#             user_context=auth_me_like_context, # Return user context even if no docs
#         )

#     # 6. Re-ranking (Restored from user's original)
#     rerank_start = time.perf_counter()
#     try:
#         # Pass the original user_query for reranking, not expanded ones individually
#         reranked_docs = rerank_with_crossencoder(user_query, initial_docs) 
#     except Exception as e_rerank:
#         logger.error(f"Re-ranking failed: {e_rerank}. Using initial docs.", exc_info=True)
#         reranked_docs = initial_docs # Fallback to non-reranked if error
#     rerank_time = time.perf_counter() - rerank_start
#     logger.info(f"Re-ranking {len(initial_docs)} docs took {rerank_time:.4f}s. Resulted in {len(reranked_docs)} docs.")


#     # 7. Dynamic context size selection (Restored from user's original)
#     context_doc_count = 10 # Default
#     if is_course_code_query and not is_complex_query: # Specific course, simple question
#         context_doc_count = 8
#     elif is_complex_query or is_requirement_query: # Complex or requirement based
#         context_doc_count = 15
#     # Ensure it doesn't exceed available docs
#     context_doc_count = min(context_doc_count, len(reranked_docs))
#     logger.info(f"Dynamic context size selected: {context_doc_count} documents.")

#     # 8. Smart document selection for diversity (Restored from user's original)
#     selection_start = time.perf_counter()
#     # Consider top N candidates for diversity selection, e.g., twice the context_doc_count
#     candidates_for_diversity_count = min(context_doc_count * 2, len(reranked_docs))
#     top_candidates = reranked_docs[:candidates_for_diversity_count]
    
#     selected_docs_for_context = []
#     seen_sources: set[str] = set()
#     # Prioritize unique sources for the first half of the context
#     half_context_count = context_doc_count // 2

#     for doc in top_candidates:
#         if len(selected_docs_for_context) >= context_doc_count:
#             break
#         source = str(doc.metadata.get("source", doc.metadata.get("source_file", "unknown_source")))
        
#         if source not in seen_sources or len(selected_docs_for_context) < half_context_count:
#             selected_docs_for_context.append(doc)
#             if source != "unknown_source":
#                 seen_sources.add(source)
    
#     # If still need more docs, fill from top_candidates, allowing duplicates from same source
#     if len(selected_docs_for_context) < context_doc_count:
#         needed_more = context_doc_count - len(selected_docs_for_context)
#         current_selected_ids = {get_consistent_doc_id(d) for d in selected_docs_for_context}
        
#         for doc in top_candidates: # Iterate again over candidates
#             if needed_more == 0:
#                 break
#             doc_id = get_consistent_doc_id(doc)
#             if doc_id not in current_selected_ids:
#                 selected_docs_for_context.append(doc)
#                 current_selected_ids.add(doc_id) # Track added IDs
#                 needed_more -= 1
    
#     # Final list of documents for context, sorted by original reranked score
#     # This ensures the most relevant (by reranker) are still generally at the top
#     # if they made it through diversity selection.
#     final_top_docs = sorted(selected_docs_for_context, key=lambda d: reranked_docs.index(d))
#     selection_time = time.perf_counter() - selection_start
#     logger.info(f"Smart selection of {len(final_top_docs)} docs from {len(top_candidates)} candidates took {selection_time:.4f}s.")


#     # 9. Classify & enrich (Restored from user's original)
#     enrichment_start = time.perf_counter()
#     enriched_docs = classify_and_enrich_documents(final_top_docs, user_query)
#     enrichment_time = time.perf_counter() - enrichment_start
#     logger.info(f"Document enrichment took {enrichment_time:.4f}s.")

#     # 10. Format for LLM (Restored from user's original)
#     formatting_start = time.perf_counter()
#     formatted_retrieved_context = format_documents_for_llm(enriched_docs)
#     formatting_time = time.perf_counter() - formatting_start
#     logger.info(f"Context formatting for LLM took {formatting_time:.4f}s.")

#     # New: Format chat history
#     formatted_chat_history = format_message_history_for_llm(chat_history_messages)

#     # 11. Choose & build prompt (Restored from user's original)
#     prompt_selection_start = time.perf_counter()
#     chosen_prompt_object = get_chosen_prompt(user_query, enriched_docs, prompts)
#     if not chosen_prompt_object: # Fallback if selection fails
#         logger.warning("Failed to get a chosen prompt, falling back to default.")
#         chosen_prompt_object = prompts.get("default_prompt")
    
#     # Identify prompt name for logging (handle if not a LangChain PromptTemplate)
#     prompt_name = "unknown_prompt"
#     if isinstance(chosen_prompt_object, str): # Simple string prompt
#         # Try to find its key in the prompts dict
#         prompt_name = next((name for name, tmpl in prompts.items() if tmpl == chosen_prompt_object), "custom_string_prompt")
#     elif hasattr(chosen_prompt_object, 'template'): # LangChain PromptTemplate
#          prompt_name = next((name for name, tmpl in prompts.items() if tmpl is chosen_prompt_object), "langchain_prompt")

#     prompt_selection_time = time.perf_counter() - prompt_selection_start
#     logger.info(f"Using prompt '{prompt_name}' (Selection took {prompt_selection_time:.4f}s)")
    
#     # Prepare format_args including chat_history
#     format_args = {
#         "context": formatted_retrieved_context,
#         "question": user_query,
#         "chat_history": formatted_chat_history, 
#         "current_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z"),
#         **prompt_fields, 
#     }
    
#     try:
#         if hasattr(chosen_prompt_object, "input_variables"): # LangChain PromptTemplate
#             # Ensure all input_variables are present in format_args, defaulting to "N/A"
#             final_format_args = {
#                 key: format_args.get(key, "N/A") 
#                 for key in chosen_prompt_object.input_variables
#             }
#             # Log if any expected variables were missing from format_args and defaulted
#             missing_vars = [k for k in chosen_prompt_object.input_variables if k not in format_args]
#             if missing_vars:
#                 logger.warning(f"Prompt '{prompt_name}' missing variables, defaulted to 'N/A': {missing_vars}")
            
#             prompt_str = chosen_prompt_object.format(**final_format_args)
#         elif isinstance(chosen_prompt_object, str): # Simple f-string like template
#             # Use format_map for safety with f-strings if some keys might be missing
#             # This requires a dictionary where missing keys don't raise KeyError
#             class DefaultDict(dict):
#                 def __missing__(self, key: Any) -> str:
#                     logger.warning(f"Prompt formatting: Key '{key}' not found in format_args, using 'N/A'.")
#                     return "N/A"
#             prompt_str = chosen_prompt_object.format_map(DefaultDict(format_args))
#         else:
#             logger.error(f"Chosen prompt object is of unexpected type: {type(chosen_prompt_object)}")
#             raise HTTPException(status_code=500, detail="Internal error: Invalid prompt object.")

#     except KeyError as e_key:
#         logger.error(f"Missing key {e_key} in prompt formatting for '{prompt_name}'. Available keys: {list(format_args.keys())}", exc_info=True)
#         raise HTTPException(status_code=500, detail=f"Internal error: missing key {e_key} for prompt.")
#     except Exception as e_fmt:
#         logger.error(f"Error formatting prompt '{prompt_name}': {e_fmt}", exc_info=True)
#         raise HTTPException(status_code=500, detail="Internal error formatting prompt.")

#     # 12. Call LLM
#     llm_start = time.perf_counter()
#     try:
#         answer_obj = llm.invoke(prompt_str)
#         final_answer = getattr(answer_obj, "content", str(answer_obj))
#     except Exception as e_llm:
#         logger.error(f"LLM call failed: {e_llm}", exc_info=True)
#         raise HTTPException(status_code=503, detail=f"LLM service error: {str(e_llm)}")
#     llm_time = time.perf_counter() - llm_start
#     logger.info(f"LLM generation took {llm_time:.4f}s")

#     # 13. Return response
#     total_time = time.perf_counter() - start_time
#     logger.info(f"Total processing time for query: {total_time:.4f}s")
#     return QueryResponse(
#         answer=final_answer.strip(),
#         processing_time=total_time,
#         context=formatted_retrieved_context, 
#         user_context=auth_me_like_context,
#     )


@router.post("/stream_query")
async def stream_query_endpoint(
    request: QueryRequest, current_user: User | Admin = Depends(get_current_account) # type: ignore
):
    user_query = request.query.strip()
    chat_history_messages = request.history
    filters = request.filters

    if not user_query:
        async def error_stream_no_query():
            error_payload = {"detail": "Query cannot be empty."}
            yield f'event: error\ndata: {json.dumps(error_payload)}\n\n'
        return StreamingResponse(error_stream_no_query(), media_type="text/event-stream", status_code=400)

    logger.info(
        f"Streaming query from user {getattr(current_user, 'id', 'UNKNOWN_USER_ID')} "
        f"({getattr(current_user,'student_id','UNKNOWN_STUDENT_ID')}): '{user_query}' "
        f"with {len(chat_history_messages) if chat_history_messages else 0} history messages."
    )
    
    async def stream_generator():
        start_time = time.perf_counter()

        # 1. Load components - use dual retriever
        retriever = get_dual_retriever()  # Use dual retriever
        llm = get_llm()
        if not retriever or not llm or not hasattr(llm, "stream"):
            error_payload = {"detail": "Retriever or LLM unavailable/doesn't support streaming."}
            yield f'event: error\ndata: {json.dumps(error_payload)}\n\n'
            return
        prompts = get_prompts_dict()

        # 2. Query analysis & expansion
        is_course_code_query = bool(re.search(r"\b[A-Z]{4}\d{4}\b", user_query, re.IGNORECASE))
        is_complex_query = len(user_query.split()) >= 10
        prereq_pattern = r"\b(?:pre[- ]?requisites?|requirements?)\b"
        is_requirement_query = bool(re.search(prereq_pattern, user_query.lower())) or any(
            w in user_query.lower() for w in ["credit", "graduate", "policy", "rule", "eligible"]
        )
        should_expand = True
        if is_course_code_query and any(kw in user_query.lower() for kw in ["credit", "title", "name", "number"]):
            should_expand = False
        expanded_queries = expand_query(user_query) if should_expand else [user_query]
        logger.debug(f"Stream: Expanded queries: {expanded_queries}")

        # 3. Retrieval
        all_initial_docs = []
        for eq in expanded_queries:
            try:
                docs_for_eq = retriever.get_relevant_documents(eq)
                all_initial_docs.extend(docs_for_eq)
            except Exception as e_ret_stream:
                logger.warning(f"Stream: Error retrieving for '{eq}': {e_ret_stream}")
        logger.debug(f"Stream: Retrieved {len(all_initial_docs)} initial docs.")
        
        # 4. Deduplication
        unique_docs_map: Dict[str, Any] = {}
        for doc in all_initial_docs:
            doc_id = get_consistent_doc_id(doc)
            if doc_id not in unique_docs_map:
                unique_docs_map[doc_id] = doc
        initial_docs = list(unique_docs_map.values())
        logger.debug(f"Stream: Deduplicated to {len(initial_docs)} docs.")

        # 5. Extract user context
        auth_me_like_context, prompt_fields = await extract_user_context(current_user)

        if not initial_docs:
            logger.info("Stream: No relevant documents found.")
            no_docs_message_payload = {"text": "I could not find any relevant documents based on your query. Please try rephrasing."}
            yield f'event: message\ndata: {json.dumps(no_docs_message_payload)}\n\n'
            
            end_payload_no_docs = {
                "processing_time": time.perf_counter() - start_time,
                "user_context": auth_me_like_context,
            }
            yield f'event: end\ndata: {json.dumps(end_payload_no_docs, cls=SetEncoder)}\n\n'
            return

        # 6. Re-ranking
        try:
            reranked_docs = rerank_with_crossencoder(user_query, initial_docs)
        except Exception as e_rerank_stream:
            logger.warning(f"Stream: Re-ranking failed: {e_rerank_stream}. Using initial docs.")
            reranked_docs = initial_docs
        logger.debug(f"Stream: Reranked to {len(reranked_docs)} docs.")

        # 7. Dynamic context size & 8. Smart selection
        context_doc_count = 10
        if is_course_code_query and not is_complex_query: context_doc_count = 8
        elif is_complex_query or is_requirement_query: context_doc_count = 15
        context_doc_count = min(context_doc_count, len(reranked_docs))

        candidates_for_diversity_count = min(context_doc_count * 2, len(reranked_docs))
        top_candidates = reranked_docs[:candidates_for_diversity_count]
        selected_docs_for_context = []
        seen_sources_stream: set[str] = set()
        half_context_count = context_doc_count // 2
        for doc in top_candidates:
            if len(selected_docs_for_context) >= context_doc_count: break
            source = str(doc.metadata.get("source", doc.metadata.get("source_file", "unknown_source")))
            if source not in seen_sources_stream or len(selected_docs_for_context) < half_context_count:
                selected_docs_for_context.append(doc)
                if source != "unknown_source": seen_sources_stream.add(source)
        if len(selected_docs_for_context) < context_doc_count:
            needed_more = context_doc_count - len(selected_docs_for_context)
            current_selected_ids = {get_consistent_doc_id(d) for d in selected_docs_for_context}
            for doc in top_candidates:
                if needed_more == 0: break
                doc_id = get_consistent_doc_id(doc)
                if doc_id not in current_selected_ids:
                    selected_docs_for_context.append(doc)
                    current_selected_ids.add(doc_id)
                    needed_more -= 1
        final_top_docs = sorted(selected_docs_for_context, key=lambda d: reranked_docs.index(d))
        logger.debug(f"Stream: Selected {len(final_top_docs)} docs for context.")

        # 9. Classify & enrich, 10. Format for LLM
        enriched_docs = classify_and_enrich_documents(final_top_docs, user_query)
        formatted_retrieved_context = format_documents_for_llm(enriched_docs)
        
        # Format chat history
        formatted_chat_history = format_message_history_for_llm(chat_history_messages)

        # 11. Choose & build prompt
        chosen_prompt_object = get_chosen_prompt(user_query, enriched_docs, prompts)
        if not chosen_prompt_object: chosen_prompt_object = prompts.get("default_prompt")
        
        prompt_name_stream = "unknown_prompt_stream" # For logging
        if isinstance(chosen_prompt_object, str):
            prompt_name_stream = next((name for name, tmpl in prompts.items() if tmpl == chosen_prompt_object), "custom_string_prompt_stream")
        elif hasattr(chosen_prompt_object, 'template'):
            prompt_name_stream = next((name for name, tmpl in prompts.items() if tmpl is chosen_prompt_object), "langchain_prompt_stream")
        logger.debug(f"Stream: Using prompt '{prompt_name_stream}'.")

        format_args = {
            "context": formatted_retrieved_context, "question": user_query,
            "chat_history": formatted_chat_history,
            "current_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z"),
            **prompt_fields,
        }

        try:
            if hasattr(chosen_prompt_object, "input_variables"):
                final_format_args = {key: format_args.get(key, "N/A") for key in chosen_prompt_object.input_variables}
                missing_vars_stream = [k for k in chosen_prompt_object.input_variables if k not in format_args]
                if missing_vars_stream: logger.warning(f"Stream Prompt '{prompt_name_stream}' missing vars: {missing_vars_stream}")
                prompt_str = chosen_prompt_object.format(**final_format_args)
            elif isinstance(chosen_prompt_object, str):
                class DefaultDictStream(dict):
                    def __missing__(self, key: Any) -> str:
                        logger.warning(f"Stream Prompt formatting: Key '{key}' not found, using 'N/A'.")
                        return "N/A"
                prompt_str = chosen_prompt_object.format_map(DefaultDictStream(format_args))
            else:
                raise ValueError("Invalid prompt object for streaming.")

        except Exception as e_fmt_stream:
            logger.error(f"Stream: Error formatting prompt '{prompt_name_stream}': {e_fmt_stream}", exc_info=True)
            error_payload = {"detail": f"Internal error formatting prompt for streaming: {str(e_fmt_stream)}"}
            yield f'event: error\ndata: {json.dumps(error_payload)}\n\n'
            return
            
        # 12. Stream LLM
        try:
            for chunk_obj in llm.stream(prompt_str):
                text_chunk = getattr(chunk_obj, "content", str(chunk_obj)) 
                if text_chunk:
                    sse_event_data = json.dumps({"text": text_chunk})
                    yield f"event: message\ndata: {sse_event_data}\n\n"
                    await asyncio.sleep(0.001) 
        except Exception as e_llm_stream:
            logger.error(f"Stream: LLM streaming failed: {e_llm_stream}", exc_info=True)
            error_payload = {"detail": f"LLM service streaming error: {str(e_llm_stream)}"}
            yield f'event: error\ndata: {json.dumps(error_payload)}\n\n'
            return

        # 13. End event
        total_time = time.perf_counter() - start_time
        logger.info(f"Total processing time for stream: {total_time:.4f}s")
        
        end_payload = {
            "processing_time": total_time,
            "user_context": auth_me_like_context,
        }
        yield f"event: end\ndata: {json.dumps(end_payload, cls=SetEncoder)}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")
# # --- /rag/stream_query Endpoint ---
# @router.post("/stream_query")
# async def stream_query_endpoint(
#     request: QueryRequest, current_user: User | Admin = Depends(get_current_account) # type: ignore
# ):
#     user_query = request.query.strip()
#     chat_history_messages = request.history
#     filters = request.filters # Assuming filters are handled by retriever if passed

#     if not user_query:
#         # For streaming, we should still yield valid SSE events for errors
#         async def error_stream_no_query():
#             error_payload = {"detail": "Query cannot be empty."}
#             yield f'event: error\ndata: {json.dumps(error_payload)}\n\n'
#             # Optionally, send an 'end' event to signal client-side to stop expecting more.
#             # end_payload = {"processing_time": 0.0, "user_context": None}
#             # yield f'event: end\ndata: {json.dumps(end_payload)}\n\n'
#         return StreamingResponse(error_stream_no_query(), media_type="text/event-stream", status_code=400)


#     logger.info(
#         f"Streaming query from user {getattr(current_user, 'id', 'UNKNOWN_USER_ID')} "
#         f"({getattr(current_user,'student_id','UNKNOWN_STUDENT_ID')}): '{user_query}' "
#         f"with {len(chat_history_messages) if chat_history_messages else 0} history messages."
#     )
    
#     async def stream_generator():
#         start_time = time.perf_counter()
#         # full_response_content = [] # If you need to assemble the full response for some reason

#         # 1. Load components
#         ensemble_ret = get_ensemble_retriever()
#         llm = get_llm()
#         if not ensemble_ret or not llm or not hasattr(llm, "stream"):
#             error_payload = {"detail": "Retriever or LLM unavailable/doesn't support streaming."}
#             yield f'event: error\ndata: {json.dumps(error_payload)}\n\n'
#             # Consider sending an end event here as well if the client expects it
#             # end_payload_err = {"processing_time": time.perf_counter() - start_time, "user_context": None}
#             # yield f'event: end\ndata: {json.dumps(end_payload_err, cls=SetEncoder)}\n\n'
#             return
#         prompts = get_prompts_dict()

#         # --- Pipeline steps (mirroring /query but with yields) ---
#         # 2. Query analysis & expansion
#         # (Using the same detailed logic as in /query)
#         is_course_code_query = bool(re.search(r"\b[A-Z]{4}\d{4}\b", user_query, re.IGNORECASE))
#         is_complex_query = len(user_query.split()) >= 10
#         prereq_pattern = r"\b(?:pre[- ]?requisites?|requirements?)\b"
#         is_requirement_query = bool(re.search(prereq_pattern, user_query.lower())) or any(
#             w in user_query.lower() for w in ["credit", "graduate", "policy", "rule", "eligible"]
#         )
#         should_expand = True
#         if is_course_code_query and any(kw in user_query.lower() for kw in ["credit", "title", "name", "number"]):
#             should_expand = False
#         expanded_queries = expand_query(user_query) if should_expand else [user_query]
#         logger.debug(f"Stream: Expanded queries: {expanded_queries}")

#         # 3. Retrieval
#         all_initial_docs = []
#         for eq in expanded_queries:
#             try:
#                 docs_for_eq = ensemble_ret.get_relevant_documents(eq)
#                 all_initial_docs.extend(docs_for_eq)
#             except Exception as e_ret_stream:
#                 logger.warning(f"Stream: Error retrieving for '{eq}': {e_ret_stream}")
#         logger.debug(f"Stream: Retrieved {len(all_initial_docs)} initial docs.")
        
#         # 4. Deduplication
#         unique_docs_map: Dict[str, Any] = {}
#         for doc in all_initial_docs:
#             doc_id = get_consistent_doc_id(doc)
#             if doc_id not in unique_docs_map:
#                 unique_docs_map[doc_id] = doc
#         initial_docs = list(unique_docs_map.values())
#         logger.debug(f"Stream: Deduplicated to {len(initial_docs)} docs.")

#         # 5. Extract user context
#         auth_me_like_context, prompt_fields = await extract_user_context(current_user)

#         if not initial_docs:
#             logger.info("Stream: No relevant documents found.")
#             # Send a message indicating no documents, then the end event
#             no_docs_message_payload = {"text": "I could not find any relevant documents based on your query. Please try rephrasing."}
#             yield f'event: message\ndata: {json.dumps(no_docs_message_payload)}\n\n'
            
#             end_payload_no_docs = {
#                 "processing_time": time.perf_counter() - start_time,
#                 "user_context": auth_me_like_context,
#                 # "context": "No relevant documents found." # Optional: client might expect context in end event
#             }
#             yield f'event: end\ndata: {json.dumps(end_payload_no_docs, cls=SetEncoder)}\n\n'
#             return

#         # 6. Re-ranking
#         try:
#             reranked_docs = rerank_with_crossencoder(user_query, initial_docs)
#         except Exception as e_rerank_stream:
#             logger.warning(f"Stream: Re-ranking failed: {e_rerank_stream}. Using initial docs.")
#             reranked_docs = initial_docs
#         logger.debug(f"Stream: Reranked to {len(reranked_docs)} docs.")

#         # 7. Dynamic context size & 8. Smart selection
#         context_doc_count = 10
#         if is_course_code_query and not is_complex_query: context_doc_count = 8
#         elif is_complex_query or is_requirement_query: context_doc_count = 15
#         context_doc_count = min(context_doc_count, len(reranked_docs))

#         candidates_for_diversity_count = min(context_doc_count * 2, len(reranked_docs))
#         top_candidates = reranked_docs[:candidates_for_diversity_count]
#         selected_docs_for_context = []
#         seen_sources_stream: set[str] = set()
#         half_context_count = context_doc_count // 2
#         for doc in top_candidates:
#             if len(selected_docs_for_context) >= context_doc_count: break
#             source = str(doc.metadata.get("source", doc.metadata.get("source_file", "unknown_source")))
#             if source not in seen_sources_stream or len(selected_docs_for_context) < half_context_count:
#                 selected_docs_for_context.append(doc)
#                 if source != "unknown_source": seen_sources_stream.add(source)
#         if len(selected_docs_for_context) < context_doc_count:
#             needed_more = context_doc_count - len(selected_docs_for_context)
#             current_selected_ids = {get_consistent_doc_id(d) for d in selected_docs_for_context}
#             for doc in top_candidates:
#                 if needed_more == 0: break
#                 doc_id = get_consistent_doc_id(doc)
#                 if doc_id not in current_selected_ids:
#                     selected_docs_for_context.append(doc)
#                     current_selected_ids.add(doc_id)
#                     needed_more -= 1
#         final_top_docs = sorted(selected_docs_for_context, key=lambda d: reranked_docs.index(d))
#         logger.debug(f"Stream: Selected {len(final_top_docs)} docs for context.")

#         # 9. Classify & enrich, 10. Format for LLM
#         enriched_docs = classify_and_enrich_documents(final_top_docs, user_query)
#         formatted_retrieved_context = format_documents_for_llm(enriched_docs)
        
#         # Format chat history
#         formatted_chat_history = format_message_history_for_llm(chat_history_messages)

#         # 11. Choose & build prompt
#         chosen_prompt_object = get_chosen_prompt(user_query, enriched_docs, prompts)
#         if not chosen_prompt_object: chosen_prompt_object = prompts.get("default_prompt")
        
#         prompt_name_stream = "unknown_prompt_stream" # For logging
#         if isinstance(chosen_prompt_object, str):
#             prompt_name_stream = next((name for name, tmpl in prompts.items() if tmpl == chosen_prompt_object), "custom_string_prompt_stream")
#         elif hasattr(chosen_prompt_object, 'template'):
#             prompt_name_stream = next((name for name, tmpl in prompts.items() if tmpl is chosen_prompt_object), "langchain_prompt_stream")
#         logger.debug(f"Stream: Using prompt '{prompt_name_stream}'.")

#         format_args = {
#             "context": formatted_retrieved_context, "question": user_query,
#             "chat_history": formatted_chat_history,
#             "current_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z"),
#             **prompt_fields,
#         }

#         try:
#             if hasattr(chosen_prompt_object, "input_variables"):
#                 final_format_args = {key: format_args.get(key, "N/A") for key in chosen_prompt_object.input_variables}
#                 missing_vars_stream = [k for k in chosen_prompt_object.input_variables if k not in format_args]
#                 if missing_vars_stream: logger.warning(f"Stream Prompt '{prompt_name_stream}' missing vars: {missing_vars_stream}")
#                 prompt_str = chosen_prompt_object.format(**final_format_args)
#             elif isinstance(chosen_prompt_object, str):
#                 class DefaultDictStream(dict):
#                     def __missing__(self, key: Any) -> str:
#                         logger.warning(f"Stream Prompt formatting: Key '{key}' not found, using 'N/A'.")
#                         return "N/A"
#                 prompt_str = chosen_prompt_object.format_map(DefaultDictStream(format_args))
#             else:
#                 raise ValueError("Invalid prompt object for streaming.")

#         except Exception as e_fmt_stream:
#             logger.error(f"Stream: Error formatting prompt '{prompt_name_stream}': {e_fmt_stream}", exc_info=True)
#             error_payload = {"detail": f"Internal error formatting prompt for streaming: {str(e_fmt_stream)}"}
#             yield f'event: error\ndata: {json.dumps(error_payload)}\n\n'
#             # Consider end event
#             return
            
#         # 12. Stream LLM
#         try:
#             for chunk_obj in llm.stream(prompt_str):
#                 text_chunk = getattr(chunk_obj, "content", str(chunk_obj)) 
#                 if text_chunk:
#                     # full_response_content.append(text_chunk) # If needed
#                     sse_event_data = json.dumps({"text": text_chunk})
#                     yield f"event: message\ndata: {sse_event_data}\n\n"
#                     await asyncio.sleep(0.001) 
#         except Exception as e_llm_stream:
#             logger.error(f"Stream: LLM streaming failed: {e_llm_stream}", exc_info=True)
#             error_payload = {"detail": f"LLM service streaming error: {str(e_llm_stream)}"}
#             yield f'event: error\ndata: {json.dumps(error_payload)}\n\n'
#             # Consider end event
#             return

#         # 13. End event
#         total_time = time.perf_counter() - start_time
#         logger.info(f"Total processing time for stream: {total_time:.4f}s")
        
#         end_payload = {
#             "processing_time": total_time,
#             "user_context": auth_me_like_context,
#             # "context": formatted_retrieved_context, # Optionally include the context used
#         }
#         yield f"event: end\ndata: {json.dumps(end_payload, cls=SetEncoder)}\n\n"

#     return StreamingResponse(stream_generator(), media_type="text/event-stream")


# --- Other Endpoints ---
@router.post("/switch_llm")
async def switch_llm_endpoint(request: SwitchLLMRequest):
    """Switches the backend LLM used by the RAG service."""
    if request.backend not in [
        "ollama",
        "gemini",
    ]:  # Add other valid backends as needed
        raise HTTPException(
            status_code=400,
            detail="Invalid backend specified. Valid options: ollama, gemini.",
        )
    try:
        # Assuming switch_llm_backend handles the logic and returns the new backend name
        result = switch_llm_backend(request.backend)
        logger.info(f"Switched LLM backend to: {result}")
        return {
            "message": f"Successfully switched LLM backend to {result}",
            "backend": result,
        }
    except Exception as e:
        logger.error(
            f"Failed to switch LLM backend to {request.backend}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to switch LLM backend: {e}"
        )


@router.get("/model_info")
async def model_info_endpoint():
    """Returns information about the currently active LLM model."""
    try:
        # Assuming get_model_info retrieves details about the current LLM
        info = get_model_info()
        return info
    except Exception as e:
        logger.error(f"Failed to get model info: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve model info: {e}"
        )


@router.get("/user_context_info", response_model=Dict[str, Any])
async def user_context_endpoint(
    current_user: User | Admin = Depends(get_current_account),
):
    """
    Returns the extracted user context structured like the /auth/me response.
    Useful for debugging what data is being prepared for the RAG response context.
    """
    try:
        # Call extract_user_context and return only the first part (the /auth/me structure)
        auth_me_like_context, _ = await extract_user_context(current_user)
        return auth_me_like_context
    except Exception as e:
        logger.error(
            f"Error extracting user context for info endpoint: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail="Error extracting user context")


# --- End of Router Definition ---
