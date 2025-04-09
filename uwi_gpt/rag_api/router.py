#!/usr/bin/env python
"""
rag_api/router.py - Router for the RAG-based QA system API endpoints
"""

import logging
import time
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import re
# Import RAG components
from .models import QueryRequest, QueryResponse, SwitchLLMRequest
from .initialize import get_ensemble_retriever, get_llm, get_documents, rerank_with_crossencoder
# Assuming ingestion functions might be needed if re-running ingestion is part of the flow
# from .ingestion import load_existing_qdrant_store

# Set up router
router = APIRouter(
    prefix="/rag",
    tags=["RAG"],
    responses={404: {"description": "Not found"}},
)

logger = logging.getLogger(__name__) # Ensure logger is configured elsewhere in your app setup

# --- Helper Functions ---
# (Keep format_documents_for_llm, classify_and_enrich_documents,
#  expand_query, filter_documents_by_metadata functions as they are)
def format_documents_for_llm(docs):
    """
    Format a list of documents with enhanced metadata for better LLM context.
    """
    if not docs:
        return "No relevant documents found."

    formatted_docs = []

    for i, doc in enumerate(docs):
        # Extract metadata
        source = doc.metadata.get("source_file", "Unknown")
        heading = doc.metadata.get("heading", "N/A")
        doc_format = doc.metadata.get("format", "text") # Note: doc_format isn't used below

        # Create document header with metadata
        doc_header = f"\n--- DOCUMENT [{i+1}] ---\n"
        doc_header += f"SOURCE: {source}\n"

        # Include TITLE if available (from previous context)
        if "title" in doc.metadata:
            doc_header += f"TITLE: {doc.metadata['title']}\n"
        if heading != "N/A":
            doc_header += f"HEADING: {heading}\n"

        # Add any other useful metadata found during enrichment
        if "department" in doc.metadata:
            doc_header += f"DEPARTMENT: {doc.metadata['department']}\n"
        if "faculty" in doc.metadata:
            doc_header += f"FACULTY: {doc.metadata['faculty']}\n"
        # Add doc_type as requested by prompts
        if "doc_type" in doc.metadata:
             doc_header += f"DOC_TYPE: {doc.metadata['doc_type']}\n"


        # Add content separator
        doc_header += "CONTENT:\n"

        # Combine header with content
        formatted_content = f"{doc_header}{doc.page_content}\n"
        formatted_docs.append(formatted_content)

    # Join all formatted documents with separators
    return "\n".join(formatted_docs)

def classify_and_enrich_documents(docs, query):
    """
    Classify documents by type and add rich metadata to help the LLM understand context.
    """
    import re # Keep import here if only used here

    if not docs:
        return []

    # Extract query keywords for targeted enrichment
    query_keywords = set(query.lower().split())

    # Common patterns for document classification
    course_code_pattern = re.compile(r'\b[A-Z]{4}\d{4}\b')  # e.g., COMP3456
    credit_pattern = re.compile(r'\b(\d+)\s*credits?\b', re.IGNORECASE)
    level_pattern = re.compile(r'\blevel\s*(\d+)\b', re.IGNORECASE)

    for doc in docs:
        # Ensure metadata exists
        if not hasattr(doc, 'metadata') or doc.metadata is None:
            doc.metadata = {}

        content = doc.page_content if hasattr(doc, 'page_content') else ""
        content_lower = content.lower()

        # Initialize metadata fields if not present
        if "doc_type" not in doc.metadata:
            doc.metadata["doc_type"] = "general"

        if "keywords" not in doc.metadata:
            doc.metadata["keywords"] = []

        # Document type classification (add safety checks)
        if course_code_pattern.search(content):
            doc.metadata["doc_type"] = "course_description"
            course_codes = course_code_pattern.findall(content)
            if course_codes:
                doc.metadata["course_codes"] = course_codes
            credit_matches = credit_pattern.findall(content)
            if credit_matches:
                doc.metadata["credits"] = credit_matches[0]
            level_matches = level_pattern.findall(content)
            if level_matches:
                doc.metadata["level"] = level_matches[0]

        elif any(term in content_lower for term in ["requirement", "mandatory", "compulsory", "must complete"]):
            doc.metadata["doc_type"] = "requirement"
            if "prerequisite" in content_lower:
                doc.metadata["requirement_type"] = "prerequisite"
            elif "graduate" in content_lower or "graduation" in content_lower:
                doc.metadata["requirement_type"] = "graduation"
            elif "assessment" in content_lower:
                doc.metadata["requirement_type"] = "assessment"

        elif any(term in content_lower for term in ["policy", "regulation", "rule", "procedure"]):
            doc.metadata["doc_type"] = "policy"
            if "academic" in content_lower and "integrity" in content_lower:
                doc.metadata["policy_area"] = "academic_integrity"
            elif "examination" in content_lower:
                doc.metadata["policy_area"] = "examination"
            elif "registration" in content_lower:
                doc.metadata["policy_area"] = "registration"

        # Extract semester information if available
        semester_pattern = re.compile(r'\b(semester\s*[1-3]|summer)\b', re.IGNORECASE)
        semester_matches = semester_pattern.findall(content_lower)
        if semester_matches:
            doc.metadata["semester"] = semester_matches[0].title()

        # Extract relevant keywords that match the query
        for keyword in query_keywords:
            if len(keyword) > 3 and keyword in content_lower:
                if keyword not in doc.metadata["keywords"]:
                    doc.metadata["keywords"].append(keyword)

        # Calculate a document relevance score (keep as before)
        keyword_count = len(doc.metadata["keywords"])
        course_code_bonus = 5 if "course_codes" in doc.metadata else 0
        type_bonus = 3 if doc.metadata["doc_type"] != "general" else 0
        relevance = min(100, (keyword_count * 10) + course_code_bonus + type_bonus)
        doc.metadata["relevance_score"] = relevance

    # Sort documents by relevance score (highest first)
    docs.sort(key=lambda x: x.metadata.get("relevance_score", 0), reverse=True)

    return docs

def get_chosen_prompt(query, docs, prompts):
    """Select the appropriate prompt template based on the query and documents"""
    query_lower = query.lower()
    # Ensure docs list is not empty before accessing metadata
    doc_types = [doc.metadata.get("doc_type", "general") for doc in docs] if docs else []

    # Check for credit-related keywords or requirement doc types
    if any(keyword in query_lower for keyword in ["credit", "graduate", "bsc", "degree", "study"]) or "requirement" in doc_types:
        return prompts["credit_prompt"]
    # Check for course-related keywords or course_description doc types
    elif any(keyword in query_lower for keyword in ["course", "class", "subject", "lecture"]) or "course_description" in doc_types:
        # Added check for course code pattern in query itself as strong indicator
        if re.search(r'\b[A-Z]{4}\d{4}\b', query, re.IGNORECASE):
             return prompts["course_prompt"]
        # Existing condition:
        elif any(keyword in query_lower for keyword in ["course", "class", "subject", "lecture"]) or "course_description" in doc_types:
             return prompts["course_prompt"]
    # Default case
    return prompts["default_prompt"]

def expand_query(query: str):
    """Simple query expansion function"""
    expanded = [
        query,
        query + " courses",
        query.replace("student", "learner")
    ]
    # Make expansion slightly more robust for codes
    if re.match(r'^[A-Z]{4}\d{4}$', query, re.IGNORECASE):
        expanded.append(f"information about {query}")
        expanded.append(f"{query} prerequisites")

    return list(set(expanded)) # Return unique expansions

def filter_documents_by_metadata(docs, query):
    """Filter documents based on metadata and query"""
    # Example: Filter for UWI docs if query mentions UWI
    if "uwi" in query.lower():
        # Ensure metadata source_file exists before lowercasing
        filtered = [
            doc for doc in docs
            if "uwi" in doc.metadata.get("source_file", "").lower()
        ]
        # Only replace if filtering actually found something
        if filtered:
            logger.info(f"Filtered for 'UWI', keeping {len(filtered)} docs.")
            return filtered
        else:
            logger.info("Query mentioned 'UWI' but no source files matched.")
            return docs # Return original if filter yields empty
    return docs


# --- API Endpoints ---
@router.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    """
    Process a natural language query against the document store and return a response.
    """
    start_time = time.perf_counter()
    user_query = request.query
    logger.info(f"Received query: {user_query}")

    try:
        # Get necessary components
        ensemble_ret = get_ensemble_retriever()
        llm = get_llm()
        # Get prompt templates (assuming these functions are defined below or imported)
        prompts = {
            "default_prompt": get_default_prompt(),
            "credit_prompt": get_credit_prompt(),
            "course_prompt": get_course_prompt(),
        }
        if not all(prompts.values()):
             raise ValueError("One or more prompt templates failed to load.")


        # 1. Expand the query
        expanded_queries = expand_query(user_query)
        logger.info(f"Expanded queries: {expanded_queries}")

        # 2. Retrieve documents for each expanded query
        all_initial_docs = []
        if ensemble_ret: # Check if retriever exists
            for eq in expanded_queries:
                docs_for_eq = ensemble_ret.get_relevant_documents(eq)
                all_initial_docs.extend(docs_for_eq)
        else:
            logger.error("Ensemble retriever is not initialized.")
            raise HTTPException(status_code=500, detail="Retriever not available.")


        # 3. Deduplicate and filter documents
        # Use a robust way to get a unique ID, fallback to object id if needed
        unique_docs_map = {}
        for doc in all_initial_docs:
             doc_id = doc.metadata.get("source_file", id(doc)) # Use object id as last resort
             if doc_id not in unique_docs_map:
                  unique_docs_map[doc_id] = doc
        initial_docs = list(unique_docs_map.values())
        logger.info(f"Retrieved {len(initial_docs)} unique documents initially.")

        initial_docs = filter_documents_by_metadata(initial_docs, user_query)
        logger.info(f"Kept {len(initial_docs)} docs after metadata filtering.")


        # 4. Re-rank with cross-encoder
        reranked_docs = rerank_with_crossencoder(user_query, initial_docs)
        logger.info(f"Re-ranked documents, top score likely relates to query relevance.")

        # Limit number of documents passed to LLM (use 15 as in original code example)
        # Make this configurable?
        CONTEXT_DOC_COUNT = 15
        top_docs = reranked_docs[:CONTEXT_DOC_COUNT]
        logger.info(f"Selected top {len(top_docs)} documents for LLM context.")


        # 5. Classify and enrich documents with metadata
        enriched_docs = classify_and_enrich_documents(top_docs, user_query)
        # Log doc types found in enriched context
        doc_type_counts_context = {}
        for doc in enriched_docs:
             doc_type = doc.metadata.get("doc_type", "general")
             doc_type_counts_context[doc_type] = doc_type_counts_context.get(doc_type, 0) + 1
        logger.info(f"Document type distribution in context: {doc_type_counts_context}")


        # 6. Format documents with enhanced metadata
        formatted_context = format_documents_for_llm(enriched_docs)
        # Optionally log context length (beware of large logs)
        # logger.debug(f"Formatted Context for LLM:\n{formatted_context[:500]}...")


        # 7. Choose prompt based on query and document types
        chosen_prompt_object = get_chosen_prompt(user_query, enriched_docs, prompts)

        # --- ADD LOGGING HERE ---
        prompt_name = "unknown"
        # Compare object identity to find the name
        if chosen_prompt_object is prompts["credit_prompt"]:
            prompt_name = "credit_prompt"
        elif chosen_prompt_object is prompts["course_prompt"]:
            prompt_name = "course_prompt"
        elif chosen_prompt_object is prompts["default_prompt"]:
            prompt_name = "default_prompt"
        logger.info(f"Using prompt template: {prompt_name}") # Log which prompt was chosen
        # --- END LOGGING ADDITION ---

        prompt_str = chosen_prompt_object.format(context=formatted_context, question=user_query)
        # Optionally log prompt string length or start (beware of large logs)
        # logger.debug(f"Final prompt string for LLM (start):\n{prompt_str[:500]}...")


        # 8. Call the LLM
        if llm: # Check if LLM exists
             answer = llm(prompt_str) # Use __call__ or _call depending on Langchain version/base
             # answer = llm._call(prompt_str) # Use this if using the older _call directly
        else:
             logger.error("LLM is not initialized.")
             raise HTTPException(status_code=500, detail="LLM not available.")

        processing_time = time.perf_counter() - start_time
        logger.info(f"LLM generated answer in {processing_time:.2f} seconds total.")


        # Return response (keep context in response as before)
        return QueryResponse(answer=answer, processing_time=processing_time, context=formatted_context)

    except Exception as e:
        logger.error(f"Error processing query '{user_query}': {e}", exc_info=True) # Log traceback
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

# Keep other endpoints (/switch_llm, /model_info) and prompt template functions
# (get_default_prompt, get_credit_prompt, get_course_prompt) as they are.

@router.post("/switch_llm")
async def switch_llm(request: SwitchLLMRequest):
    """
    Switch the LLM backend between Ollama and Gemini
    """
    # Assuming switch_llm_backend is imported correctly
    from .initialize import switch_llm_backend

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
async def model_info():
    """Return information about the currently selected model."""
     # Assuming get_model_info is imported correctly
    from .initialize import get_model_info

    try:
        info = get_model_info()
        return info
    except Exception as e:
        logger.error(f"Error getting model info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error getting model info: {str(e)}")


# --- Prompt Templates (ensure these functions are defined correctly) ---
# Assuming get_default_prompt, get_credit_prompt, get_course_prompt
# are defined exactly as you provided previously.

def get_default_prompt():
    from langchain.prompts import PromptTemplate

    default_template = """
    You are a university AI assistant that answers questions based only on the provided context from university documents.
    The context contains multiple documents with METADATA in caps and CONTENT sections.

    When forming your answer:
    1. Pay close attention to the SOURCE, HEADING, TITLE, DOC_TYPE and other metadata provided for each document.
    2. Documents are sorted by relevance, so earlier documents are generally more important.
    3. Look for specific document types (in DOC_TYPE metadata) that might be most relevant:
        - course_description: Information about specific courses
        - requirement: Mandatory program requirements
        - policy: Official university policies
    4. If there are conflicts between documents, prefer information from:
        - More recent documents (check dates if available in SOURCE or TITLE)
        - Official policy documents over general information
        - Department-specific information over general faculty information

    Please provide your answer in markdown format with clear headings, bullet points, or numbered lists as appropriate.
    Include citations to specific documents by referring to their document numbers like [Doc 1], [Doc 3, Doc 4] when appropriate.

    **Context:**
    {context}

    **Question:**
    {question}

    **Answer:**
    """

    return PromptTemplate(
        input_variables=["context", "question"],
        template=default_template
    )

def get_credit_prompt():
    from langchain.prompts import PromptTemplate

    credit_template = """
    You are a university AI assistant that answers questions about degree requirements based on the provided context from official university documents.
    The context contains multiple documents with METADATA in caps and CONTENT sections.

    When answering questions about credit requirements:
    1. Pay special attention to documents with "requirement" or "course_description" in their DOC_TYPE metadata.
    2. When calculating total credits:
        - Distinguish between Level 1, 2, and 3 course requirements if levels are mentioned.
        - Note if foundation courses give different credits (e.g., 6 instead of 3).
        - Look for both minimum requirements and maximum allowed credits.
    3. Check for specific faculty or department requirements in the relevant metadata fields.
    4. Explicitly mention the source documents you're basing your calculations on, using citations like [Doc 1], [Doc 2].

    Please perform the following steps in your answer:
    1. Identify the number of credits required at Level 1 (if specified).
    2. Identify the number of credits required at Levels 2/3 (if specified).
    3. Identify any foundation course details (credits, codes) if relevant.
    4. Sum these values appropriately based on the question asked.
    5. Format your final answer in markdown with a clear summary and bullet points. Use citations.

    **Context:**
    {context}

    **Question:**
    {question}

    **Answer:**
    """

    return PromptTemplate(
        input_variables=["context", "question"],
        template=credit_template
    )

def get_course_prompt():
    # Using the improved version suggested previously
    from langchain.prompts import PromptTemplate

    course_template = """
    You are a university AI assistant that answers questions about specific courses based only on the provided context from university documents.
    The context contains multiple documents with METADATA in caps (SOURCE, TITLE, HEADING, DOC_TYPE, etc.) and CONTENT sections.

    When answering questions about courses:
    1. Search all provided documents carefully. Pay attention to tables and course description sections (DOC_TYPE 'course_description'), but also scan general text, including prerequisite lists for other courses, for mentions of the course code and its title.
    2. Try to provide the following details for the course mentioned in the question:
        - Course code and title
        - Number of credits
        - Prerequisites (if mentioned)
        - Course level (1, 2, or 3)
        - Whether it's required or elective
        - Semester offered (if mentioned)
    3. **Crucially:** If you can find the course code directly associated with its **full title** (e.g., in the format 'CODE - Title' or listed nearby) anywhere in the context, **state that title clearly**, even if other details like credits or level are missing for that specific course entry. Mention the source document using citation format like [Doc 1].
    4. If you find multiple pieces of information across documents, synthesize them, but prioritize information from documents that seem like official course listings or descriptions if available. Note any conflicts if necessary.
    5. If, after careful searching, you cannot find the course code or its associated title in the context, state that the course information is not available in the provided documents.
    6. Structure your answer clearly, using headings or bullet points. Use tables if presenting information about multiple courses. Use citations like [Doc 1], [Doc 5] where appropriate.

    **Context:**
    {context}

    **Question:**
    {question}

    **Answer:**
    """

    return PromptTemplate(
        input_variables=["context", "question"],
        template=course_template
    )