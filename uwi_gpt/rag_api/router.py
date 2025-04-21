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
from typing import Optional, List, Dict, Any, Tuple # Added Tuple
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# --- Authentication Imports ---
# Import the dependency function to get the current user
try:
    from auth.utils import get_current_user
except ImportError:
    # Fallback if auth module structure is different
    try:
        from ..auth.utils import get_current_user
    except ImportError:
        logging.error("Could not import get_current_user dependency. Auth will not work.")
        # Define a placeholder dependency that raises an error if auth is required but missing
        async def get_current_user():
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication module not configured correctly.")

# Import the User model and related models for type hinting and context extraction
try:
    from user_db.models import User, EnrolledCourse, CourseGrade, Term, Course # Ensure these are correct
except ImportError:
     logging.warning("Could not import User model or related DB models. Type hinting may be affected.")
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
    from .models import QueryRequest, QueryResponse, SwitchLLMRequest
    from .initialize import (
        get_ensemble_retriever,
        get_llm,
        rerank_with_crossencoder,
        switch_llm_backend,
        get_model_info
    )
    from .prompts import get_prompts_dict # Load prompts function
    from .retrievers import get_doc_id as get_consistent_doc_id # Consistent ID helper
except ImportError as e:
    logging.error(f"Error importing RAG components or prompts: {e}. Check module paths.", exc_info=True)
    # Define placeholders or raise error if critical components missing
    get_ensemble_retriever = lambda: None
    get_llm = lambda: None
    rerank_with_crossencoder = lambda query, docs: docs # Passthrough
    get_prompts_dict = lambda: {"default_prompt": "Context: {context}\nQuestion: {question}\nAnswer:"} # Basic fallback
    get_consistent_doc_id = lambda doc: getattr(doc, 'id', id(doc))
    # Define placeholder models if needed, or let it fail on endpoint definition
    class QueryRequest(BaseModel): query: str
    # Ensure QueryResponse expects the Dict for user_context
    class QueryResponse(BaseModel): answer: str; processing_time: float; context: str; user_context: Dict[str, Any]
    class SwitchLLMRequest(BaseModel): backend: str


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
    if not docs: return "No relevant documents found."
    formatted_docs = []
    for i, doc in enumerate(docs):
        try:
            metadata = getattr(doc, 'metadata', {})
            # Try standard metadata keys, fallback to generic naming
            source_filename = metadata.get("source", metadata.get("source_file", f"Unknown_Source_{i+1}"))
            doc_header = f"\n--- SOURCE [{source_filename}] ---\n"
            # Define keys you expect/want to show from metadata
            metadata_keys_to_show = [
                "title", "heading", "department", "faculty", "doc_type",
                "course_codes", "credits", "level", "semester",
                "requirement_type", "policy_area", "chunk_index", "chunk_count",
                # Add any other relevant metadata keys here
            ]
            for key in metadata_keys_to_show:
                if key in metadata:
                    value = metadata[key]
                    # Format list values nicely
                    value_str = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
                    # Only add if value has content and isn't just placeholder/empty
                    if value_str and value_str.strip() and value_str.lower() not in ["n/a", "none", ""]:
                         doc_header += f"{key.upper().replace('_', ' ')}: {value_str}\n"

            doc_header += "CONTENT:\n"
            # Get page content, default to empty string if missing
            page_content = str(getattr(doc, 'page_content', ''))
            formatted_docs.append(f"{doc_header}{page_content.strip()}\n")
        except Exception as e:
            source_display = metadata.get('source_file', f"Unknown_Source_{i+1}") # Fallback source display
            logger.error(f"Error formatting doc from {source_display} (idx {i}): {e}", exc_info=True)
            formatted_docs.append(f"\n--- SOURCE [{source_display}] --- (Error formatting document) ---\n")
    return "".join(formatted_docs)

def classify_and_enrich_documents(docs: List[Any], query: str) -> List[Any]:
    """Classifies documents based on content and adds metadata."""
    if not docs: return []

    # Simple keyword/regex based classification - adapt as needed
    query_keywords = set(query.lower().split())
    course_code_pattern = re.compile(r'\b([A-Z]{4}\d{4})\b') # Example: ABCD1234
    prereq_pattern = r'\b(?:pre[- ]?requisites?|requirements?|mandatory|must have)\b'
    policy_pattern = r'\b(?:policy|policies|regulation|rules|guidelines?)\b'
    description_pattern = r'\b(?:description|aims?|objectives?|outline|syllabus)\b'

    for doc in docs:
        # Ensure metadata exists and is a dict
        if not hasattr(doc, 'metadata') or not isinstance(doc.metadata, dict):
            doc.metadata = {}

        content = str(getattr(doc, 'page_content', ''))
        content_lower = content.lower()

        # Determine document type
        doc_type = "general" # Default type
        course_codes_found = course_code_pattern.findall(content) # Find all course codes

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
        return None # Or raise an error

    default_prompt = prompts.get("default_prompt")
    if not default_prompt:
         logger.error("Default prompt is missing from prompts dictionary!")
         # Try to grab *any* prompt as a last resort
         return next(iter(prompts.values()), None) if prompts else None

    query_lower = query.lower()
    doc_types = [doc.metadata.get("doc_type", "general") for doc in docs] if docs else []

    # --- Prompt Selection Logic (Customize extensively based on your prompts) ---

    # Example: Prioritize requirement/credit related prompts
    prereq_pattern = r'\b(?:pre[- ]?requisites?|requirements?)\b'
    is_prereq_query = bool(re.search(prereq_pattern, query_lower))
    if any(k in query_lower for k in ["credit", "graduate", "requirement", "gpa"]) \
       or "requirement" in doc_types \
       or is_prereq_query:
        chosen = prompts.get("credit_prompt", default_prompt)
        logger.debug(f"Choosing prompt: {'credit_prompt' if chosen != default_prompt else 'default_prompt (fallback)'}")
        return chosen

    # Example: Course related prompts
    has_course_code = bool(re.search(r'\b[A-Z]{4}\d{4}\b', query, re.IGNORECASE))
    if has_course_code \
       or any(k in query_lower for k in ["course", "class", "subject", "module", "offering"]) \
       or any(dt in doc_types for dt in ["course_description", "course_listing"]):
        chosen = prompts.get("course_prompt", default_prompt)
        logger.debug(f"Choosing prompt: {'course_prompt' if chosen != default_prompt else 'default_prompt (fallback)'}")
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
from datetime import datetime # Keep if used for anything else, not strictly needed in this function now

# Assuming User, EnrolledCourse, CourseGrade, Term, Course models are imported
# and have the necessary attributes and relationships defined (e.g., grade.term, grade.course)
try:
    from user_db.models import User, EnrolledCourse, CourseGrade, Term, Course # Ensure these are correct
except ImportError:
     logging.warning("Could not import User model or related DB models. Type hinting may be affected.")
     # Define placeholder types if models aren't available
     User = Any
     EnrolledCourse = Any
     CourseGrade = Any
     Term = Any
     Course = Any

logger = logging.getLogger(__name__)

def extract_user_context(current_user: User) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Extracts user context by RECONSTRUCTING grades data from DB relationships
    to ensure freshness. Formats one part to mirror /auth/me and another
    part with flat fields for prompt formatting.

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
            "courses": {"courses": [], "nextoffset": None}
        },
        "grades_status": {"fetched": False, "success": False, "error": "Initialization error."},
        "grades_data": {
            "student_name": "",
            "student_id": "",
            "terms": [],
            "overall": {
                "cumulative_gpa": None,
                "degree_gpa": None,
                "total_credits_earned": None
            }
        }
    }

    # Initialize the dictionary for prompt formatting fields
    prompt_fields = {
        "user_name": "N/A",
        "student_id": "N/A",
        "user_gpa": "N/A",
        "total_credits": "N/A",
        "user_courses_summary": "N/A",
        "current_courses": [],
        "grade_history": [],
        "grades_data_raw": None
    }

    try:
        # --- Populate User Info ---
        user_name = f"{getattr(current_user, 'firstname', '')} {getattr(current_user, 'lastname', '')}".strip()
        student_id = getattr(current_user, 'student_id', 'N/A')
        email = getattr(current_user, 'email', 'N/A')

        auth_me_like_context["moodle_data"]["user_info"] = {
            "name": user_name,
            "email": email,
            "student_id": student_id
        }
        prompt_fields["user_name"] = user_name
        prompt_fields["student_id"] = student_id

        # --- Populate Moodle Courses (from enrollments relationship) ---
        current_courses_list_for_prompt = []
        if hasattr(current_user, 'enrollments') and current_user.enrollments:
            for enrollment in current_user.enrollments:
                 if hasattr(enrollment, 'course') and enrollment.course:
                    course = enrollment.course
                    # Map Course object fields to the MoodleDataOut structure
                    course_data_auth = {
                        "id": getattr(course, 'id', None),
                        "fullname": getattr(course, 'fullname', "Unknown Course Name"),
                        "shortname": getattr(course, 'shortname', None),
                        "idnumber": getattr(course, 'idnumber', None),
                        "summary": getattr(course, 'summary', None),
                        "summaryformat": getattr(course, 'summaryformat', 1),
                        "startdate": int(getattr(course, 'startdate', 0)),
                        "enddate": int(getattr(course, 'enddate', 0)),
                        "visible": getattr(course, 'visible', True),
                        "showactivitydates": getattr(course, 'showactivitydates', False),
                        "showcompletionconditions": getattr(course, 'showcompletionconditions', None),
                        "fullnamedisplay": getattr(course, 'fullname', "Unknown Course Name"),
                        "viewurl": f"/course/view.php?id={getattr(course, 'id', '')}",
                        "coursecategory": getattr(course, 'coursecategory', "Unknown") # Check attribute name on Course model
                    }
                    auth_me_like_context["moodle_data"]["courses"]["courses"].append(course_data_auth)

                    # Populate prompt_fields["current_courses"]
                    shortname = getattr(course, 'shortname', "Unknown")
                    code = shortname.split()[0] if shortname != "Unknown" else "Unknown" # Basic code extraction
                    prompt_course_data = {
                         "code": code,
                         "name": getattr(course, 'fullname', "Unknown Course Name"),
                         "id": getattr(course, 'id', None),
                         "full_shortname": shortname,
                         "idnumber": getattr(course, 'idnumber', None),
                         "status": getattr(enrollment, 'status', 'Enrolled') # Assuming status on enrollment
                     }
                    current_courses_list_for_prompt.append(prompt_course_data)

        prompt_fields["current_courses"] = current_courses_list_for_prompt
        if current_courses_list_for_prompt:
             prompt_fields["user_courses_summary"] = ", ".join([c.get("code", "Unknown") for c in current_courses_list_for_prompt])

        # --- Populate Grades Data & Status ---
        # Always reconstruct from relationships to ensure freshness and correct details.
        grades_available = False
        if hasattr(current_user, 'grades') and current_user.grades:
            logger.info("Reconstructing grades_data from user DB relationships (terms/grades).")
            grades_available = True
            auth_me_like_context["grades_data"]["student_name"] = user_name
            auth_me_like_context["grades_data"]["student_id"] = student_id
            terms_dict = {} # To hold reconstructed terms {term_code: term_data}

            # Pre-process terms if available to get term-level stats
            if hasattr(current_user, 'terms') and current_user.terms:
                for term in current_user.terms:
                    term_code = getattr(term, 'term_code', 'UnknownTerm')
                    terms_dict[term_code] = {
                        "term_code": term_code, "courses": [],
                        "semester_gpa": getattr(term, 'semester_gpa', None),
                        "cumulative_gpa": getattr(term, 'cumulative_gpa', None),
                        "degree_gpa": getattr(term, 'degree_gpa', None),
                        "credits_earned_to_date": getattr(term, 'credits_earned_to_date', None)
                    }

            # --- Process Grades ---
            grade_history_for_prompt = []
            for grade in current_user.grades: # 'grade' is an instance of CourseGrade model
                # Get Term Code from the relationship
                term_obj = getattr(grade, 'term', None)
                term_code = getattr(term_obj, 'term_code', 'UnknownTerm') if term_obj else 'UnknownTerm'

                # --- FIXED SECTION ---
                # Get code, title, and credits DIRECTLY from the CourseGrade object itself
                # using the column names defined in the CourseGrade SQLAlchemy model
                course_code = getattr(grade, 'course_code', "Unknown")
                course_title = getattr(grade, 'course_title', "Unknown Title")
                credit_hours = getattr(grade, 'credit_hours', 3.0) # Use 3.0 as default if null/missing

                # --- End FIXED SECTION ---

                # Create course entry for the nested grades_data structure
                course_entry_auth = {
                     "course_code": course_code,
                     "course_title": course_title,
                     "credit_hours": credit_hours,
                     "grade_earned": getattr(grade, 'grade_earned', "NA"), # Get the actual grade earned
                     "whatif_grade": getattr(grade, 'whatif_grade', None)  # Get the what-if grade
                }

                # Add course entry to the corresponding term in terms_dict
                if term_code not in terms_dict:
                     # Create term entry if it wasn't pre-loaded (e.g., only grades are available)
                     terms_dict[term_code] = {
                         "term_code": term_code, "courses": [],
                         "semester_gpa": None, "cumulative_gpa": None,
                         "degree_gpa": None, "credits_earned_to_date": None
                     }
                terms_dict[term_code]["courses"].append(course_entry_auth)

                # --- Add to flat grade_history for prompt_fields ---
                grade_history_for_prompt.append({
                    "term": term_code,
                    "course_code": course_code,
                    "course_title": course_title,
                    "credit_hours": credit_hours,
                    "grade": course_entry_auth["grade_earned"] # Reflect the earned grade here
                })

            # Finalize the reconstructed grades_data for auth_me_like_context
            auth_me_like_context["grades_data"]["terms"] = list(terms_dict.values())
            # Sort terms consistently (e.g., reverse chronological, CURRENT first)
            auth_me_like_context["grades_data"]["terms"].sort(
                key=lambda t: ("0" if t.get("term_code") == "CURRENT" else str(t.get("term_code", "Z"))),
                reverse=True
            )

            # Update prompt_fields with reconstructed data
            prompt_fields["grade_history"] = grade_history_for_prompt
            prompt_fields["grades_data_raw"] = auth_me_like_context["grades_data"] # Pass full structure

            # Update status to reflect successful reconstruction
            auth_me_like_context["grades_status"] = {"fetched": True, "success": True, "error": None}

            # Extract overall GPA/Credits from the *most recent reconstructed term* for prompt_fields
            reconstructed_non_current = [
                t for t in auth_me_like_context["grades_data"]["terms"]
                if t.get("term_code") != "CURRENT" and t.get("cumulative_gpa") is not None
            ]
            if reconstructed_non_current: # Already sorted, take the first one
                recent_reconstructed_term = reconstructed_non_current[0]
                prompt_fields["user_gpa"] = str(recent_reconstructed_term["cumulative_gpa"])
                if recent_reconstructed_term.get("credits_earned_to_date") is not None:
                     prompt_fields["total_credits"] = str(recent_reconstructed_term["credits_earned_to_date"])
            else:
                logger.warning(f"Could not determine overall GPA/Credits from reconstructed terms for user {student_id}.")


        else: # No grade relationships found for reconstruction
            logger.warning(f"No grade data relationships found for user {student_id}. Grades context will be empty.")
            auth_me_like_context["grades_status"] = {"fetched": False, "success": False, "error": "No grade data available for user in DB relationships."}
            auth_me_like_context["grades_data"]["student_name"] = user_name
            auth_me_like_context["grades_data"]["student_id"] = student_id
            prompt_fields["grades_data_raw"] = auth_me_like_context["grades_data"] # Pass empty structure


    except Exception as e:
        logger.error(f"Error during user context extraction for user {student_id}: {e}", exc_info=True)
        # Set error status, but try to return basic structure
        auth_me_like_context["grades_status"] = {"fetched": False, "success": False, "error": f"Internal server error during context extraction: {e}"}
        # Ensure basic info is populated even on error
        if not auth_me_like_context["moodle_data"]["user_info"]:
             auth_me_like_context["moodle_data"]["user_info"] = {"name": "Error", "email": "Error", "student_id": "Error"}
        if not auth_me_like_context["grades_data"]["student_name"]:
             auth_me_like_context["grades_data"]["student_name"] = user_name if 'user_name' in locals() else "Error"
             auth_me_like_context["grades_data"]["student_id"] = student_id if 'student_id' in locals() else "Error"

    # Return both the /auth/me structured data and the flat fields for prompt formatting
    return auth_me_like_context, prompt_fields

# --- UPDATED: /rag/query Endpoint ---
@router.post("/query", response_model=QueryResponse)
async def query_endpoint(
    request: QueryRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Process a natural language query against the document store,
    inject full user context (including grade_history_json),
    and return the LLM answer plus context & user_context.
    """
    start_time = time.perf_counter()
    user_query = request.query.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    logger.info(f"Received query from user {current_user.id} ({getattr(current_user,'student_id','UNKNOWN')}): '{user_query}'")

    # 1. Load retriever, LLM, prompts
    ensemble_ret = get_ensemble_retriever()
    llm          = get_llm()
    if not ensemble_ret:
        raise HTTPException(status_code=503, detail="Retriever service unavailable.")
    if not llm:
        raise HTTPException(status_code=503, detail="LLM service unavailable.")
    prompts = get_prompts_dict()

    # 2. Query analysis & expansion
    analysis_start = time.perf_counter()
    is_course_code_query = bool(re.search(r'\b[A-Z]{4}\d{4}\b', user_query, re.IGNORECASE))
    is_complex_query     = len(user_query.split()) >= 10
    prereq_pattern       = r'\b(?:pre[- ]?requisites?|requirements?)\b'
    is_requirement_query = bool(re.search(prereq_pattern, user_query.lower())) \
                            or any(w in user_query.lower() for w in ["credit","graduate","policy","rule","eligible"])
    should_expand = True
    if is_course_code_query and any(kw in user_query.lower() for kw in ["credit","title","name","number"]):
        should_expand = False
        logger.info("Specific course‐info query detected; skipping expansion.")
    expanded_queries = expand_query(user_query) if should_expand else [user_query]
    analysis_time = time.perf_counter() - analysis_start
    logger.info(f"Query analysis took {analysis_time:.2f}s → {expanded_queries}")

    # 3. Retrieval
    retrieval_start = time.perf_counter()
    all_initial_docs = []
    for eq in expanded_queries:
        try:
            docs_for_eq = ensemble_ret.get_relevant_documents(eq)
            all_initial_docs.extend(docs_for_eq)
        except Exception as e:
            logger.error(f"Error retrieving for '{eq}': {e}")
    retrieval_time = time.perf_counter() - retrieval_start
    logger.info(f"Retrieved {len(all_initial_docs)} docs in {retrieval_time:.2f}s")

    # 4. Deduplication
    dedup_start = time.perf_counter()
    try:
        from .retrievers import get_doc_id as get_consistent_doc_id
    except ImportError:
        get_consistent_doc_id = lambda d: getattr(d, 'id', id(d))
    unique_docs_map = {}
    for doc in all_initial_docs:
        doc_id = get_consistent_doc_id(doc)
        unique_docs_map.setdefault(doc_id, doc)
    initial_docs = list(unique_docs_map.values())
    dedup_time = time.perf_counter() - dedup_start
    logger.info(f"Deduplicated to {len(initial_docs)} docs in {dedup_time:.2f}s")

    if not initial_docs:
        # No docs → early return, include user_context
        auth_ctx, _ = extract_user_context(current_user)
        return QueryResponse(
            answer="I could not find any relevant documents based on your query.",
            processing_time=time.perf_counter() - start_time,
            context="No relevant documents found.",
            user_context=auth_ctx
        )

    # 5. Extract & serialize user context
    auth_me_like_context, prompt_fields = extract_user_context(current_user)
    prompt_fields["grade_history_json"] = json.dumps(
        prompt_fields.get("grade_history", []), ensure_ascii=False
    )

    # 6. Re‑ranking
    rerank_start = time.perf_counter()
    try:
        reranked_docs = rerank_with_crossencoder(user_query, initial_docs)
    except Exception:
        reranked_docs = initial_docs
    rerank_time = time.perf_counter() - rerank_start
    logger.info(f"Re-ranked in {rerank_time:.2f}s")

    # 7. Dynamic context size selection
    context_doc_count = 10
    if is_course_code_query:
        context_doc_count = 8
    elif is_complex_query or is_requirement_query:
        context_doc_count = 15
    logger.info(f"Using context_doc_count={context_doc_count}")

    # 8. Smart document selection (diversity)
    selection_start = time.perf_counter()
    candidates_count = min(context_doc_count * 2, len(reranked_docs))
    top_candidates   = reranked_docs[:candidates_count]
    selected_docs    = []
    seen_sources     = set()
    for doc in top_candidates:
        if len(selected_docs) >= context_doc_count:
            break
        source = doc.metadata.get("source_file", "unknown")
        if source not in seen_sources or len(selected_docs) < (context_doc_count // 2):
            selected_docs.append(doc)
            seen_sources.add(source)
    if len(selected_docs) < context_doc_count:
        needed = context_doc_count - len(selected_docs)
        current_ids = {get_consistent_doc_id(d) for d in selected_docs}
        for doc in top_candidates:
            if needed == 0:
                break
            did = get_consistent_doc_id(doc)
            if did not in current_ids:
                selected_docs.append(doc)
                needed -= 1
    top_docs = sorted(selected_docs, key=lambda d: reranked_docs.index(d))
    selection_time = time.perf_counter() - selection_start
    logger.info(f"Selected {len(top_docs)} docs in {selection_time:.2f}s")

    # 9. Classify & enrich
    enrichment_start = time.perf_counter()
    enriched_docs = classify_and_enrich_documents(top_docs, user_query)
    enrichment_time = time.perf_counter() - enrichment_start
    logger.info(f"Enriched docs in {enrichment_time:.2f}s")

    # 10. Format for LLM
    formatting_start = time.perf_counter()
    formatted_context = format_documents_for_llm(enriched_docs)
    formatting_time = time.perf_counter() - formatting_start
    logger.info(f"Formatted context in {formatting_time:.2f}s")

    # 11. Choose & build prompt
    prompt_selection_start = time.perf_counter()
    chosen_prompt_object = get_chosen_prompt(user_query, enriched_docs, prompts)
    if not chosen_prompt_object:
        chosen_prompt_object = prompts.get("default_prompt")
    prompt_name = next((n for n,p in prompts.items() if p is chosen_prompt_object), "unknown")
    prompt_selection_time = time.perf_counter() - prompt_selection_start
    logger.info(f"Using prompt '{prompt_name}' ({prompt_selection_time:.2f}s)")

    # Prepare format_args
    format_args = {
        "context": formatted_context,
        "question": user_query,
        "current_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z"),
        **prompt_fields
    }

    try:
        if hasattr(chosen_prompt_object, 'input_variables'):
            valid = {k: format_args[k] for k in chosen_prompt_object.input_variables if k in format_args}
            for var in chosen_prompt_object.input_variables:
                valid.setdefault(var, "N/A")
            prompt_str = chosen_prompt_object.format(**valid)
        else:
            prompt_str = chosen_prompt_object.format(**format_args)
    except KeyError as e:
        logger.error(f"Missing key {e} in prompt formatting")
        raise HTTPException(status_code=500, detail=f"Internal error: missing key {e}")
    except Exception as e:
        logger.error(f"Error formatting prompt: {e}")
        raise HTTPException(status_code=500, detail="Internal error formatting prompt")

    # 12. Call LLM
    llm_start = time.perf_counter()
    try:
        answer_obj = llm.invoke(prompt_str)
        final_answer = getattr(answer_obj, 'content', str(answer_obj))
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise HTTPException(status_code=503, detail=f"LLM service error: {e}")
    llm_time = time.perf_counter() - llm_start
    logger.info(f"LLM generation took {llm_time:.2f}s")

    # 13. Return response
    total_time = time.perf_counter() - start_time
    logger.info(f"Total processing time: {total_time:.2f}s")
    return QueryResponse(
        answer=final_answer.strip(),
        processing_time=total_time,
        context=formatted_context,
        user_context=auth_me_like_context
    )


# --- UPDATED: /rag/stream_query Endpoint ---
@router.post("/stream_query")
async def stream_query_endpoint(
    request: QueryRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Stream a query using the same RAG pipeline as /query
    (including full grade_history_json), streaming back chunks
    then a final ‘end’ event with processing_time and user_context.
    """
    user_query = request.query.strip()
    if not user_query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    async def stream_generator():
        start_time = time.perf_counter()

        # 1. Load components
        ensemble_ret = get_ensemble_retriever()
        llm          = get_llm()
        if not ensemble_ret or not llm or not hasattr(llm, "stream"):
            yield f"event: error\ndata: {{\"detail\":\"Retriever or LLM unavailable/doesn't support streaming.\"}}\n\n"
            return
        prompts = get_prompts_dict()

        # 2→8. Use the identical pipeline up through formatting
        # (copy the same steps 2–10 from the /query handler above)
        # ------------ expand, retrieve, dedupe ------------
        # analysis
        is_course_code_query = bool(re.search(r'\b[A-Z]{4}\d{4}\b', user_query, re.IGNORECASE))
        is_complex_query     = len(user_query.split()) >= 10
        prereq_pattern       = r'\b(?:pre[- ]?requisites?|requirements?)\b'
        is_requirement_query = bool(re.search(prereq_pattern, user_query.lower())) or any(
            w in user_query.lower() for w in ["credit","graduate","policy","rule","eligible"]
        )
        should_expand = not (is_course_code_query and any(
            kw in user_query.lower() for kw in ["credit","title","name","number"]
        ))
        expanded_queries = expand_query(user_query) if should_expand else [user_query]

        all_docs = []
        for eq in expanded_queries:
            try:
                all_docs.extend(ensemble_ret.get_relevant_documents(eq))
            except:
                pass

        try:
            from .retrievers import get_doc_id as get_consistent_doc_id
        except ImportError:
            get_consistent_doc_id = lambda d: getattr(d,'id',id(d))
        unique_map = {}
        for d in all_docs:
            unique_map.setdefault(get_consistent_doc_id(d), d)
        initial_docs = list(unique_map.values())
        if not initial_docs:
            auth_ctx, _ = extract_user_context(current_user)
            payload = {
                "answer": "",
                "processing_time": time.perf_counter()-start_time,
                "context": "No relevant documents found.",
                "user_context": auth_ctx
            }
            yield f"event: end\ndata: {json.dumps(payload)}\n\n"
            return

        # extract user context
        auth_ctx, prompt_fields = extract_user_context(current_user)
        prompt_fields["grade_history_json"] = json.dumps(
            prompt_fields.get("grade_history", []), ensure_ascii=False
        )

        # rerank
        try:
            reranked_docs = rerank_with_crossencoder(user_query, initial_docs)
        except:
            reranked_docs = initial_docs

        # dynamic size
        N = 10
        if is_course_code_query:    N = 8
        elif is_complex_query:      N = 15
        elif is_requirement_query:  N = 15

        # diversity selection
        candidates = reranked_docs[: min(len(reranked_docs), N*2) ]
        selected = []
        seen = set()
        for d in candidates:
            if len(selected) >= N: break
            src = d.metadata.get("source_file","unknown")
            if src not in seen or len(selected) < (N//2):
                selected.append(d)
                seen.add(src)
        if len(selected) < N:
            needed = N - len(selected)
            current_ids = {get_consistent_doc_id(d) for d in selected}
            for d in candidates:
                if needed == 0: break
                did = get_consistent_doc_id(d)
                if did not in current_ids:
                    selected.append(d)
                    needed -= 1
        top_docs = sorted(selected, key=lambda d: reranked_docs.index(d))

        # classify, enrich, format
        enriched = classify_and_enrich_documents(top_docs, user_query)
        formatted_context = format_documents_for_llm(enriched)

        # build prompt
        chosen = get_chosen_prompt(user_query, enriched, prompts)
        format_args = {
            "context": formatted_context,
            "question": user_query,
            "current_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z"),
            **prompt_fields
        }
        if hasattr(chosen, "input_variables"):
            valid = {k:format_args[k] for k in chosen.input_variables if k in format_args}
            for v in chosen.input_variables: valid.setdefault(v, "N/A")
            prompt_str = chosen.format(**valid)
        else:
            prompt_str = chosen.format(**format_args)

        # 9. Stream LLM
        for chunk in llm.stream(prompt_str):
            text = getattr(chunk, "content", chunk if isinstance(chunk, str) else chunk.get("text",""))
            if text:
                sse = json.dumps({"text": text, "type": "chunk"})
                yield f"event: message\ndata: {sse}\n\n"
                await asyncio.sleep(0.001)

        # 10. End event
        total = time.perf_counter() - start_time
        yield f"event: end\ndata: {json.dumps({'processing_time': total, 'user_context': auth_ctx})}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")



# --- Other Endpoints ---
@router.post("/switch_llm")
async def switch_llm_endpoint(request: SwitchLLMRequest):
    """Switches the backend LLM used by the RAG service."""
    if request.backend not in ["ollama", "gemini"]: # Add other valid backends as needed
        raise HTTPException(status_code=400, detail="Invalid backend specified. Valid options: ollama, gemini.")
    try:
        # Assuming switch_llm_backend handles the logic and returns the new backend name
        result = switch_llm_backend(request.backend)
        logger.info(f"Switched LLM backend to: {result}")
        return {"message": f"Successfully switched LLM backend to {result}", "backend": result}
    except Exception as e:
        logger.error(f"Failed to switch LLM backend to {request.backend}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to switch LLM backend: {e}")


@router.get("/model_info")
async def model_info_endpoint():
    """Returns information about the currently active LLM model."""
    try:
        # Assuming get_model_info retrieves details about the current LLM
        info = get_model_info()
        return info
    except Exception as e:
        logger.error(f"Failed to get model info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve model info: {e}")


@router.get("/user_context_info", response_model=Dict[str, Any])
async def user_context_endpoint(current_user: User = Depends(get_current_user)):
    """
    Returns the extracted user context structured like the /auth/me response.
    Useful for debugging what data is being prepared for the RAG response context.
    """
    try:
        # Call extract_user_context and return only the first part (the /auth/me structure)
        auth_me_like_context, _ = extract_user_context(current_user)
        return auth_me_like_context
    except Exception as e:
        logger.error(f"Error extracting user context for info endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error extracting user context")

# --- End of Router Definition ---