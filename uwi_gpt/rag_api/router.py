#!/usr/bin/env python
"""
rag_api/router.py - Router for the RAG-based QA system API endpoints
"""

import logging
import time
from typing import Optional, List, Dict, Any # Added Dict, Any
# Import custom exceptions if you define them
# from .exceptions import RAGError, LLMError, RetrieverError

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import re
# Import RAG components
# Ensure these imports are correct relative to your project structure
try:
    from .models import QueryRequest, QueryResponse, SwitchLLMRequest
    from .initialize import (
        get_ensemble_retriever,
        get_llm,
        get_documents, # May not be needed directly in router
        rerank_with_crossencoder,
        switch_llm_backend,
        get_model_info
    )
    # Recommended: Move prompts to a separate file like prompts.py
    # from .prompts import get_default_prompt, get_credit_prompt, get_course_prompt
except ImportError as e:
     # Handle import errors gracefully during startup if possible
     logging.error(f"Error importing RAG components: {e}. Check module paths.")
     # Depending on severity, you might raise an error or disable endpoints

# Set up router
router = APIRouter(
    prefix="/rag",
    tags=["RAG"],
    responses={404: {"description": "Not found"}},
)

# Configure logger for this module
logger = logging.getLogger(__name__)
# Ensure root logger is configured elsewhere, e.g., in your main app setup
# logging.basicConfig(level=logging.INFO) # Example basic config


# --- Helper Functions ---

def format_documents_for_llm(docs: List[Any]) -> str:
    """
    Format a list of documents with enhanced metadata for better LLM context.
    Uses the source filename as the primary identifier within the context block.
    Uses LangChain Document structure (page_content, metadata).
    """
    if not docs:
        return "No relevant documents found."

    formatted_docs = []
    # Keep track of source counts if needed for disambiguation (optional)
    # source_counts = {}

    # Use enumerate to get an index 'i' for potential fallback or logging
    for i, doc in enumerate(docs):
        try:
            # Safely access metadata
            metadata = getattr(doc, 'metadata', {})
            # --- MODIFICATION START ---
            # Get the source filename, default to "Unknown_Source"
            source_filename = metadata.get("source_file", f"Unknown_Source_{i+1}")
            # Optional: Clean up filename (remove path, keep base name)
            # source_filename = os.path.basename(source_filename)

            # Create the header using the filename
            # You could add the index if filenames might not be unique: f"[{source_filename} - Part {i+1}]"
            # Or keep it simple if filenames are expected to be unique *within the context*:
            doc_header = f"\n--- SOURCE [{source_filename}] ---\n"
            # --- MODIFICATION END ---

            # Add other metadata if present (excluding source_file as it's in the header now)
            # Also, ensure 'source' key itself isn't duplicated if it exists separately
            metadata_keys_to_show = ["title", "heading", "department", "faculty", "doc_type", "course_codes", "credits", "level", "semester", "requirement_type", "policy_area", "chunk_index", "chunk_count"] # Add chunk info?

            for key in metadata_keys_to_show:
                 if key in metadata:
                     # Simple formatting, adjust if needed (e.g., list for course_codes)
                     value = metadata[key]
                     if isinstance(value, list):
                         value_str = ", ".join(map(str, value))
                     else:
                         value_str = str(value)
                     # Only add if value is meaningful (not just 'N/A' or empty)
                     if value_str and value_str.strip() and value_str != "N/A":
                         doc_header += f"{key.upper().replace('_', ' ')}: {value_str}\n"

            # Content Separator
            doc_header += "CONTENT:\n"

            # Page Content (ensure it's a string)
            page_content = getattr(doc, 'page_content', '')
            if not isinstance(page_content, str):
                 page_content = str(page_content) # Force to string if not already

            formatted_docs.append(f"{doc_header}{page_content.strip()}\n") # Strip whitespace from content

        except Exception as e:
            source_display = metadata.get('source_file', f"Unknown_Source_{i+1}")
            logger.error(f"Error formatting document chunk from {source_display} (index {i}): {e}", exc_info=True)
            # Optionally append an error message to the context using the filename
            formatted_docs.append(f"\n--- SOURCE [{source_display}] --- (Error formatting document) ---\n")

    return "".join(formatted_docs)

def classify_and_enrich_documents(docs: List[Any], query: str) -> List[Any]:
    """
    Classify documents by type and add rich metadata to help the LLM understand context.
    Uses LangChain Document structure. Modifies metadata in place.
    """
    # --- Keep this function as is ---
    import re # Keep import here if only used here

    if not docs:
        return []

    # Extract query keywords for targeted enrichment
    query_keywords = set(query.lower().split())

    # Common patterns for document classification
    course_code_pattern = re.compile(r'\b([A-Z]{4}\d{4})\b') # Capture group for the code
    credit_pattern = re.compile(r'\b(\d+)\s*credits?\b', re.IGNORECASE)
    level_pattern = re.compile(r'\blevel\s*(\d+)\b', re.IGNORECASE)
    # Pattern for potential course descriptions (heuristic)
    course_desc_keywords = ["course description", "aims", "objectives", "learning outcomes", "topics covered", "course content"]


    for doc in docs:
        # Ensure metadata exists and is a dictionary
        if not hasattr(doc, 'metadata') or not isinstance(doc.metadata, dict):
            doc.metadata = {}

        # Ensure page_content exists and is a string
        content = getattr(doc, 'page_content', '')
        if not isinstance(content, str):
             content = str(content) # Force to string
        content_lower = content.lower()

        # --- Classification Logic ---
        doc_type = "general" # Default
        course_codes_found = course_code_pattern.findall(content) # Find all codes

        # Check for policy first (often contains other terms)
        if any(term in content_lower for term in ["policy", "regulation", "rule", "procedure", "ordinance", "statute"]):
             doc_type = "policy"
             if "academic" in content_lower and "integrity" in content_lower:
                 doc.metadata["policy_area"] = "academic_integrity"
             elif "examination" in content_lower:
                 doc.metadata["policy_area"] = "examination"
             elif "registration" in content_lower:
                 doc.metadata["policy_area"] = "registration"
             # Add more policy areas as needed

        # Check for requirements
        elif any(term in content_lower for term in ["requirement", "mandatory", "compulsory", "must complete", "eligible for", "eligibility"]):
             doc_type = "requirement"
             # Use robust regex check for prerequisite variations
             prereq_pattern = r'\b(?:pre[- ]?requisites?|anti[- ]?requisites?|co[- ]?requisites?)\b'
             if re.search(prereq_pattern, content_lower):
                 doc.metadata["requirement_type"] = "prerequisite" # Or more specific based on term
             elif "graduate" in content_lower or "graduation" in content_lower:
                 doc.metadata["requirement_type"] = "graduation"
             elif "assessment" in content_lower or "examination" in content_lower:
                 doc.metadata["requirement_type"] = "assessment"
             # Add more requirement types

        # Check for course descriptions (can overlap with requirements)
        # Prioritize if course codes AND descriptive keywords are present
        elif course_codes_found and any(keyword in content_lower for keyword in course_desc_keywords):
             doc_type = "course_description"

        # Fallback if only course codes are found
        elif course_codes_found and doc_type == "general":
             doc_type = "course_listing" # Or maybe still 'course_description' if context implies it


        # Assign final doc_type
        doc.metadata["doc_type"] = doc_type

        # --- Enrichment Logic ---
        if course_codes_found:
             # Store unique codes found in this chunk
             doc.metadata["course_codes"] = sorted(list(set(course_codes_found)))

        credit_matches = credit_pattern.findall(content) # Find all credit numbers
        if credit_matches:
             # Store as list if multiple found, or single value if one
             unique_credits = sorted(list(set(map(int, credit_matches)))) # Convert to int, get unique
             doc.metadata["credits"] = unique_credits[0] if len(unique_credits) == 1 else unique_credits

        level_matches = level_pattern.findall(content)
        if level_matches:
             unique_levels = sorted(list(set(map(int, level_matches))))
             doc.metadata["level"] = unique_levels[0] if len(unique_levels) == 1 else unique_levels

        semester_pattern = re.compile(r'\b(semester\s*[1-3]|year|summer)\b', re.IGNORECASE)
        semester_matches = semester_pattern.findall(content_lower)
        if semester_matches:
             # Normalize and store unique semesters
             normalized_semesters = []
             for sem in semester_matches:
                  s = sem.lower().replace(" ", "")
                  if "1" in s: normalized_semesters.append("Semester 1")
                  elif "2" in s: normalized_semesters.append("Semester 2")
                  elif "3" in s: normalized_semesters.append("Semester 3")
                  elif "summer" in s: normalized_semesters.append("Summer")
                  elif "year" in s: normalized_semesters.append("Year Long")
             if normalized_semesters:
                  doc.metadata["semester"] = sorted(list(set(normalized_semesters)))


        # Extract relevant keywords from query that are present in content
        doc_keywords = doc.metadata.get("keywords", []) # Get existing or init empty
        for keyword in query_keywords:
             if len(keyword) > 3 and keyword in content_lower:
                 if keyword not in doc_keywords:
                     doc_keywords.append(keyword)
        if doc_keywords: # Only update if keywords were added
             doc.metadata["keywords"] = doc_keywords


        # Calculate a simple relevance score (heuristic for sorting before re-ranking)
        # This is less critical now due to cross-encoder, but can help initial ordering
        keyword_count = len(doc.metadata.get("keywords", []))
        course_code_bonus = 5 if "course_codes" in doc.metadata else 0
        type_bonus = 3 if doc.metadata.get("doc_type", "general") not in ["general", "policy"] else 0 # Boost course/req types
        relevance = min(100, (keyword_count * 5) + course_code_bonus + type_bonus) # Adjusted weights
        doc.metadata["relevance_score"] = relevance

    return docs

def get_chosen_prompt(query: str, docs: List[Any], prompts: Dict[str, Any]):
    """Select the appropriate prompt template based on the query and documents."""
    # --- Keep this function as is ---
    query_lower = query.lower()
    # Ensure docs list is not empty before accessing metadata
    doc_types = [doc.metadata.get("doc_type", "general") for doc in docs] if docs else []
    # Check for prerequisite variations using regex
    prereq_pattern = r'\b(?:pre[- ]?requisites?|requirements?)\b'
    is_prereq_query = bool(re.search(prereq_pattern, query_lower))

    # Check for credit-related keywords or requirement doc types OR is_prereq_query
    # Added "requirement" to keywords, check doc_type 'requirement' and the regex flag
    if any(keyword in query_lower for keyword in ["credit", "graduate", "bsc", "degree", "study", "requirement"]) or "requirement" in doc_types or is_prereq_query:
        logger.debug("Choosing credit/requirement prompt.")
        return prompts["credit_prompt"]

    # Check for course-related keywords or course_description/course_listing doc types
    course_keywords = ["course", "class", "subject", "lecture", "module"]
    course_doc_types = ["course_description", "course_listing"]
    # Use regex to check for course code pattern IN QUERY as strong indicator
    has_course_code_in_query = bool(re.search(r'\b[A-Z]{4}\d{4}\b', query, re.IGNORECASE))

    if has_course_code_in_query or any(keyword in query_lower for keyword in course_keywords) or any(dt in doc_types for dt in course_doc_types):
        logger.debug("Choosing course prompt.")
        return prompts["course_prompt"]

    # Default case
    logger.debug("Choosing default prompt.")
    return prompts["default_prompt"]

def expand_query(query: str) -> List[str]:
    """Simple query expansion function."""
    # --- Keep this function as is ---
    expanded = {query} # Use set for auto-deduplication
    query_lower = query.lower()

    # General expansions
    if " course" not in query_lower:
         expanded.add(query + " courses")
    if " requirement" not in query_lower and " prerequisite" not in query_lower:
        expanded.add(query + " requirements")
    if "student" in query_lower:
         expanded.add(query.replace("student", "learner"))


    # Expansion for course codes
    course_code_match = re.search(r'\b([A-Z]{4}\d{4})\b', query, re.IGNORECASE)
    if course_code_match:
         code = course_code_match.group(1).upper()
         expanded.add(f"information about {code}")
         expanded.add(f"details for course {code}")
         expanded.add(f"{code} prerequisites")
         expanded.add(f"{code} course description")
         expanded.add(f"{code} credits")

    # Expansion for prerequisite queries
    prereq_pattern = r'\b(?:pre[- ]?requisites?|requirements?)\b'
    if re.search(prereq_pattern, query_lower):
         # Try to extract course name/code if possible
         parts = re.split(r' for | of ', query, maxsplit=1)
         if len(parts) > 1:
              subject = parts[1].strip('? ')
              expanded.add(f"{subject} course details")
              expanded.add(f"what is needed before {subject}")

    return list(expanded)

# ** REMOVED filter_documents_by_metadata function **


# --- API Endpoints ---
@router.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    """
    Process a natural language query against the document store and return a response.
    Uses adaptive retrieval and dynamic document selection for optimal context.
    """
    start_time = time.perf_counter()
    user_query = request.query.strip()
    if not user_query:
         raise HTTPException(status_code=400, detail="Query cannot be empty.")

    logger.info(f"Received query: '{user_query}'")

    try:
        # Get necessary components
        ensemble_ret = get_ensemble_retriever()
        llm = get_llm()
        if not ensemble_ret:
             logger.error("Ensemble retriever is not initialized.")
             raise HTTPException(status_code=503, detail="Retriever service unavailable.")
        if not llm:
             logger.error("LLM is not initialized.")
             raise HTTPException(status_code=503, detail="LLM service unavailable.")

        # Get prompt templates
        # If prompts are moved to prompts.py: from .prompts import get_prompts_dict
        prompts = {
            "default_prompt": get_default_prompt(),
            "credit_prompt": get_credit_prompt(),
            "course_prompt": get_course_prompt(),
        }
        if not all(prompts.values()):
            raise ValueError("One or more prompt templates failed to load.")


        # === RAG Pipeline Stages ===

        # 1. Query Analysis & Expansion
        analysis_start = time.perf_counter()
        is_course_code_query = bool(re.search(r'\b[A-Z]{4}\d{4}\b', user_query, re.IGNORECASE))
        is_complex_query = len(user_query.split()) >= 10
        prereq_pattern = r'\b(?:pre[- ]?requisites?|requirements?)\b'
        is_requirement_query = bool(re.search(prereq_pattern, user_query.lower())) or \
                               any(word in user_query.lower() for word in ["credit", "graduate", "policy", "rule", "eligible"])

        should_expand = True
        if is_course_code_query and any(kw in user_query.lower() for kw in ["credit", "title", "name", "number"]):
             should_expand = False
             logger.info("Specific course info query detected, using exact query.")

        if should_expand:
             expanded_queries = expand_query(user_query)
             logger.info(f"Using expanded queries: {expanded_queries}")
        else:
             expanded_queries = [user_query]
        analysis_time = time.perf_counter() - analysis_start


        # 2. Retrieval
        retrieval_start = time.perf_counter()
        all_initial_docs = []
        # Consider using ThreadPoolExecutor for concurrent retrieval if needed
        for eq in expanded_queries:
            try:
                docs_for_eq = ensemble_ret.get_relevant_documents(eq)
                all_initial_docs.extend(docs_for_eq)
                # Reduced logging verbosity for retrieval per query
                # logger.info(f"Retrieved {len(docs_for_eq)} documents for expanded query: '{eq}'")
            except Exception as e:
                 logger.error(f"Error retrieving documents for specific query '{eq}': {e}", exc_info=True)
        retrieval_time = time.perf_counter() - retrieval_start
        logger.info(f"Retrieval phase took {retrieval_time:.2f}s for {len(expanded_queries)} queries.")


        # 3. Deduplication
        dedup_start = time.perf_counter()
        unique_docs_map = {}
        try:
            # Import the helper function if moved to retrievers.py
            from .retrievers import get_doc_id as get_consistent_doc_id
        except ImportError:
            # Fallback or define locally if needed
            def get_consistent_doc_id(doc):
                doc_metadata = getattr(doc, 'metadata', {})
                doc_id = getattr(doc, 'id', None) or doc_metadata.get('id', None)
                if not doc_id:
                     source_file = doc_metadata.get("source_file", "unknown")
                     chunk_index = doc_metadata.get("chunk_index", -1)
                     doc_id = f"{source_file}_{chunk_index}" if chunk_index != -1 else id(doc)
                return doc_id

        for doc in all_initial_docs:
            doc_id = get_consistent_doc_id(doc)
            if doc_id not in unique_docs_map:
                unique_docs_map[doc_id] = doc
        initial_docs = list(unique_docs_map.values())
        dedup_time = time.perf_counter() - dedup_start
        logger.info(f"Retrieved {len(initial_docs)} unique documents initially (dedup took {dedup_time:.2f}s).")

        if not initial_docs:
             logger.warning("No documents found after initial retrieval and deduplication.")
             return QueryResponse(
                  answer="I could not find any relevant documents based on your query.",
                  processing_time=time.perf_counter() - start_time,
                  context="No relevant documents found."
             )

        # ** Step 4 Removed (Metadata Filtering) **
        # initial_docs now flows directly to re-ranking

        # 5. Re-ranking with Cross-Encoder
        rerank_start = time.perf_counter()
        try:
             # Pass initial_docs directly to the re-ranker
             reranked_docs = rerank_with_crossencoder(user_query, initial_docs)
        except Exception as e:
            logger.error(f"Error during cross-encoder reranking: {e}. Skipping reranking.", exc_info=True)
            reranked_docs = initial_docs # Fallback to deduplicated list
        rerank_time = time.perf_counter() - rerank_start
        logger.info(f"Cross-encoder reranking took {rerank_time:.2f} seconds. Reranked {len(reranked_docs)} docs.")


        # 6. Dynamic Context Size Selection
        context_doc_count = 10
        if is_course_code_query:
            context_doc_count = 8
            logger.info(f"Using document count {context_doc_count} for course code query")
        elif is_complex_query:
            context_doc_count = 15
            logger.info(f"Using document count {context_doc_count} for complex query")
        elif is_requirement_query:
            context_doc_count = 15
            logger.info(f"Using document count {context_doc_count} for requirement query")
        else:
             logger.info(f"Using default document count {context_doc_count}")


        # 7. Smart Document Selection (Keep Diversity Logic)
        selection_start = time.perf_counter()
        # Select final docs based on reranked order and diversity logic
        candidates_count = min(context_doc_count * 2, len(reranked_docs))
        top_candidates = reranked_docs[:candidates_count]

        selected_docs = []
        if top_candidates:
             # Simplified diversity selection - take top N unique sources up to limit
             # This might be less diverse than previous but simpler
             seen_sources = set()
             for doc in top_candidates:
                  if len(selected_docs) >= context_doc_count: break
                  source = doc.metadata.get("source_file", "unknown")
                  if source not in seen_sources or len(selected_docs) < (context_doc_count // 2): # Prefer new sources or fill half
                       selected_docs.append(doc)
                       seen_sources.add(source)

             # If still not enough, fill remaining slots by rank
             if len(selected_docs) < context_doc_count:
                  needed = context_doc_count - len(selected_docs)
                  current_ids = {get_consistent_doc_id(d) for d in selected_docs}
                  for doc in top_candidates:
                       if needed == 0: break
                       if get_consistent_doc_id(doc) not in current_ids:
                            selected_docs.append(doc)
                            needed -= 1

        # Ensure final list is sorted by original reranked order
        top_docs = sorted(selected_docs, key=lambda d: reranked_docs.index(d) if d in reranked_docs else float('inf'))

        selection_time = time.perf_counter() - selection_start
        logger.info(f"Smart document selection took {selection_time:.2f} seconds.")
        logger.info(f"Selected {len(top_docs)} documents for LLM context.")


        # 8. Classify and Enrich Final Documents
        enrichment_start = time.perf_counter()
        enriched_docs = classify_and_enrich_documents(top_docs, user_query)
        doc_type_counts_context = {}
        for doc in enriched_docs:
            doc_type = doc.metadata.get("doc_type", "general")
            doc_type_counts_context[doc_type] = doc_type_counts_context.get(doc_type, 0) + 1
        enrichment_time = time.perf_counter() - enrichment_start
        logger.info(f"Document enrichment took {enrichment_time:.2f} seconds")
        logger.info(f"Final context document type distribution: {doc_type_counts_context}")


        # 9. Format Context for LLM
        formatting_start = time.perf_counter()
        formatted_context = format_documents_for_llm(enriched_docs)
        formatting_time = time.perf_counter() - formatting_start
        logger.info(f"Document formatting took {formatting_time:.2f} seconds")
        context_tokens = len(formatted_context.split())
        logger.info(f"Formatted context size: approx {context_tokens} tokens.")


        # 10. Choose Prompt Template
        prompt_selection_start = time.perf_counter()
        chosen_prompt_object = get_chosen_prompt(user_query, enriched_docs, prompts)
        prompt_name = "unknown"
        for name, prompt_obj in prompts.items():
             if prompt_obj is chosen_prompt_object:
                  prompt_name = name
                  break
        prompt_selection_time = time.perf_counter() - prompt_selection_start
        logger.info(f"Using prompt template: '{prompt_name}' (selection took {prompt_selection_time:.2f} seconds)")

        try:
            prompt_str = chosen_prompt_object.format(context=formatted_context, question=user_query)
        except KeyError as e:
             logger.error(f"Error formatting prompt '{prompt_name}'. Missing key: {e}")
             raise HTTPException(status_code=500, detail="Internal error formatting LLM prompt.")
        prompt_tokens = len(prompt_str.split())
        logger.info(f"Final prompt size: approx {prompt_tokens} tokens.")


        # 11. Call the LLM
        llm_start = time.perf_counter()
        try:
            # Use invoke for LangChain interface consistency if applicable
            # answer = llm.invoke(prompt_str)
            # If using older callable interface:
            answer = llm.invoke(prompt_str)
        except Exception as e:
             logger.error(f"Error calling LLM: {e}", exc_info=True)
             raise HTTPException(status_code=503, detail=f"LLM service generated an error: {e}")
        llm_time = time.perf_counter() - llm_start
        logger.info(f"LLM generation took {llm_time:.2f} seconds")


        # 12. Prepare Response
        total_processing_time = time.perf_counter() - start_time
        logger.info(f"Total processing time for query '{user_query}': {total_processing_time:.2f} seconds")

        # Optionally capture debug weights
        debug_weights = {}
        # Ensure correct import path for AdaptiveEnsembleRetriever
        try:
             from .retrievers import AdaptiveEnsembleRetriever
             if isinstance(ensemble_ret, AdaptiveEnsembleRetriever):
                  debug_weights = ensemble_ret._get_weights_for_query(user_query)
        except (ImportError, AttributeError, Exception) as e:
             logger.warning(f"Could not capture debug weights: {e}")


        # 13. Return Final Response
        return QueryResponse(
            answer=answer.strip(),
            processing_time=total_processing_time,
            context=formatted_context,
            # Add debug weights if your model includes it and you want it
            # debug_weights=debug_weights
        )

    except HTTPException:
         raise # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Unexpected error processing query '{user_query}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected internal error occurred.")


# Keep other endpoints (/switch_llm, /model_info)
@router.post("/switch_llm")
async def switch_llm_endpoint(request: SwitchLLMRequest):
     """Switch the LLM backend between Ollama and Gemini"""
     # --- Keep this endpoint as is ---
     if request.backend not in ["ollama", "gemini"]:
          raise HTTPException(status_code=400, detail="Invalid backend. Must be 'ollama' or 'gemini'.")
     try:
          result = switch_llm_backend(request.backend, request.api_key)
          logger.info(f"Switched LLM backend to: {result}")
          return {"message": f"Successfully switched to {result} LLM", "backend": result}
     except ValueError as e:
          logger.warning(f"Failed to switch LLM backend: {e}")
          raise HTTPException(status_code=400, detail=str(e))
     except Exception as e:
          logger.error(f"Error switching LLM: {e}", exc_info=True)
          raise HTTPException(status_code=500, detail=f"Error switching LLM: {str(e)}")

@router.get("/model_info")
async def model_info_endpoint():
     """Return information about the currently selected model."""
     # --- Keep this endpoint as is ---
     try:
          info = get_model_info()
          return info
     except Exception as e:
          logger.error(f"Error getting model info: {e}", exc_info=True)
          raise HTTPException(status_code=500, detail=f"Error getting model info: {str(e)}")


# --- Prompt Templates ---
# It is strongly recommended to move these functions to a separate 'prompts.py' file
# and import them using: from .prompts import get_default_prompt, ...

def get_default_prompt():
    """Returns the PromptTemplate for default queries."""
    from langchain.prompts import PromptTemplate
    # ** Updated default_template with filename citation instructions **
    default_template = """
You are a university AI assistant. Your task is to answer questions based *only* on the provided context from university documents.
The context contains multiple document sources, each marked with `--- SOURCE [filename] ---` followed by METADATA and then the CONTENT.

**Instructions for Answering:**
1.  **Strict Grounding:** Base your entire answer *only* on the information explicitly stated in the provided documents' CONTENT sections. Do not add outside knowledge or make assumptions.
2.  **Verify Relevance:** Before using information from a document, check its METADATA (especially TITLE, HEADING, DOC_TYPE, COURSE_CODES if present) to ensure it is relevant to the specific subject of the Question.
3.  **Handle Irrelevant Docs:** If a document's content is clearly about a different topic, course code, or subject than the Question asks for, **you MUST ignore that document source** when forming your answer for the specific Question subject. Do not mix information from irrelevant documents.
4.  **Cite Sources:** When you use information from a document source, cite the **source filename** in square brackets, like `[handbook.pdf]` or `[policy_update_2024.pdf, course_catalog.pdf]`. Cite all relevant source filenames that support a specific piece of information.
5.  **Synthesize Information:** If multiple relevant document sources provide information, synthesize it concisely. Note any discrepancies if necessary, prioritizing official policy or course description documents if available.
6.  **Acknowledge Missing Information:** If the answer to the Question cannot be found within the relevant provided document sources, state that clearly. For example: "Based on the provided documents, information regarding X is not available."
7.  **Formatting:** Present your answer clearly using Markdown (headings, lists, bullet points).

**Context:**
{context}

**Question:**
{question}

**Answer:**
"""
    # ... (rest of the function) ...
    try:
        return PromptTemplate(
            input_variables=["context", "question"],
            template=default_template
        )
    except Exception as e:
        logger.error(f"Error creating default_prompt: {e}")
        return None # Or raise error

def get_credit_prompt():
    """Returns the PromptTemplate for credit/requirement queries."""
    from langchain.prompts import PromptTemplate
    # ** Updated credit_template with filename citation instructions **
    credit_template = """
You are a university AI assistant answering questions about degree requirements, credits, and prerequisites based *only* on the provided context from university documents.
The context contains multiple document sources, each marked with `--- SOURCE [filename] ---` followed by METADATA and CONTENT.

**Instructions for Answering Credit/Requirement Questions:**
1.  **Strict Grounding & Relevance:** Answer *only* using the relevant document sources provided. Verify that a document's content and metadata (check DOC_TYPE 'requirement' or 'course_description', and any listed COURSE_CODES) directly relate to the Question before using its information. Ignore document sources about unrelated subjects or policies.
2.  **Focus on Key Details:** Look specifically for credit values, course levels (Level 1, 2, 3), foundation courses, prerequisites (courses required before taking another), corequisites (taken concurrently), anti-requisites (cannot take if credit already received for another), and total credit requirements for programs/majors/minors mentioned.
3.  **Calculations:** If the question requires calculating total credits, clearly show how you arrived at the total based *only* on the numbers found in the relevant document sources. Specify credits per level if possible.
4.  **Cite Sources Accurately:** Cite the specific source **filename(s)** `[filename.pdf]` supporting *each* piece of information (e.g., "Level 1 requires 24 credits [ug_handbook_fst.pdf]. Foundation courses FOUN1013 and FOUN1101 are required [foundation_courses.pdf].").
5.  **Handle Missing/Conflicting Info:** If information is missing from relevant document sources, state that. If relevant sources conflict, state the conflict and prioritize information from more official sources (e.g., a 'requirement' document over a general handbook mention) if possible.
6.  **Formatting:** Use Markdown lists or bullet points for clarity.

**Context:**
{context}

**Question:**
{question}

**Answer:**
"""
    # ... (rest of the function) ...
    try:
        return PromptTemplate(
            input_variables=["context", "question"],
            template=credit_template
        )
    except Exception as e:
        logger.error(f"Error creating credit_prompt: {e}")
        return None

def get_course_prompt():
    """Returns the PromptTemplate for specific course queries."""
    from langchain.prompts import PromptTemplate
    # ** Updated course_template with filename citation instructions **
    course_template = """
You are a university AI assistant answering questions about specific courses based *only* on the provided context from university documents.
The context contains multiple document sources, each marked with `--- SOURCE [filename] ---` followed by METADATA and CONTENT.

**Instructions for Answering Course-Specific Questions:**
1.  **Identify Target Course:** Determine the specific course code (e.g., COMP3220) or title the Question is asking about.
2.  **Strict Grounding & Relevance Check:** Carefully examine *each* provided document source. Use information *only* from sources whose METADATA or CONTENT explicitly mentions the target course code or title identified in step 1. Pay close attention to DOC_TYPE 'course_description' or 'course_listing'.
3.  **Ignore Irrelevant Documents:** If a document source's content clearly describes a *different* course code or subject (e.g., digital painting [art_courses.pdf] when the Question is about Artificial Intelligence [comp_catalog.pdf, ai_syllabus.pdf]), **you MUST completely ignore that document source's description and content** when answering about the target course. Do not attribute information from unrelated sources.
4.  **Extract Key Details (from Relevant Sources Only):** For the target course, try to find and report:
    * Course code and full title.
    * Number of credits.
    * Prerequisites, corequisites, or anti-requisites.
    * Course level (e.g., Level 1, 2, 3).
    * Semester(s) offered.
    * A brief description or list of topics covered (if available *in relevant sources*).
5.  **Prioritize Title:** If you find the target course code associated with its full title in *any* relevant document source, state that title clearly.
6.  **Synthesize & Cite:** Combine information found across *multiple relevant* document sources. Cite the source **filename(s)** `[filename.pdf]` for *each* detail provided.
7.  **Handle Missing Information:** If specific details (like the description, prerequisites, or credits) for the target course are not found within the *relevant* document sources, explicitly state that the information is not available in the provided context. For example: "The description for COMP3220 was not found in the relevant documents provided [comp_catalog.pdf, ai_syllabus.pdf]." Do not invent information or use descriptions from irrelevant sources.
8.  **Formatting:** Use clear headings, bullet points, or tables.

**Context:**
{context}

**Question:**
{question}

**Answer:**
"""
    # ... (rest of the function) ...
    try:
        return PromptTemplate(
            input_variables=["context", "question"],
            template=course_template
        )
    except Exception as e:
        logger.error(f"Error creating course_prompt: {e}")
        return None