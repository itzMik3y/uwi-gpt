#!/usr/bin/env python
import os
import re
import subprocess
import time
import logging
import numpy as np
import joblib
import json
import platform

from typing import Optional, List, ClassVar, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, PrivateAttr
from pathlib import Path
import nltk
from langchain.prompts import PromptTemplate
from langchain.llms.base import LLM
from langchain.schema import BaseRetriever
import ollama
# Import for Gemini
import google.generativeai as genai

# --- Import the Qdrant-based ingestion function ---
from ingestion import initialize_documents_and_vector_store, load_existing_qdrant_store
from langchain_qdrant import RetrievalMode

# Import your custom Document class.
from document import Document
Document.__module__ = "document"  # Ensures joblib can unpickle Document consistently.

from sentence_transformers import CrossEncoder
cross_encoder = CrossEncoder("BAAI/bge-reranker-v2-m3")

from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-large-en-v1.5")

# Configure logging.
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --------------------------------------------------------------------------
# Prompt Templates
# --------------------------------------------------------------------------
default_template = """
You are a university AI assistant that answers questions based only on the provided context from university documents.
The context contains multiple documents with METADATA in caps and CONTENT sections.

When forming your answer:
1. Pay close attention to the SOURCE, HEADING, and other metadata provided for each document.
2. Documents are sorted by relevance, so earlier documents are generally more important.
3. Look for specific document types (in doc_type metadata) that might be most relevant:
   - course_description: Information about specific courses
   - requirement: Mandatory program requirements
   - policy: Official university policies
4. If there are conflicts between documents, prefer information from:
   - More recent documents (check dates if available)
   - Official policy documents over general information
   - Department-specific information over general faculty information

Please provide your answer in markdown format with clear headings, bullet points, or numbered lists as appropriate.
Include citations to specific documents by referring to their document numbers when appropriate.

**Context:**
{context}

**Question:**
{question}

**Answer:**
"""

default_prompt = PromptTemplate(
    input_variables=["context", "question"],
    template=default_template
)

# Enhanced credit template with improved metadata handling
credit_template = """
You are a university AI assistant that answers questions about degree requirements based on the provided context from official university documents.
The context contains multiple documents with METADATA in caps and CONTENT sections.

When answering questions about credit requirements:
1. Pay special attention to documents with "requirement" or "course_description" in their doc_type metadata.
2. When calculating total credits:
   - Distinguish between Level 1, 2, and 3 course requirements
   - Note that foundation courses typically give 6 credits instead of 3
   - Look for both minimum requirements and maximum allowed credits
3. Check for specific faculty or department requirements in the relevant metadata fields
4. Explicitly mention the source documents you're basing your calculations on

Please perform the following steps in your answer:
1. Identify the number of credits required at Level 1.
2. Identify the number of credits required at Levels 2/3.
3. Identify the foundation course details.
4. Sum these values appropriately.
5. Format your final answer in markdown with a clear summary and bullet points.

**Context:**
{context}

**Question:**
{question}

**Answer:**
"""

credit_prompt = PromptTemplate(
    input_variables=["context", "question"],
    template=credit_template
)

# Add a new prompt template for course-specific questions
course_template = """
You are a university AI assistant that answers questions about specific courses based on the provided context from official university documents.
The context contains multiple documents with METADATA in caps and CONTENT sections.

When answering questions about courses:
1. Pay special attention to documents with "course_description" in their doc_type metadata.
2. For each relevant course mentioned, provide:
   - Course code and title
   - Number of credits
   - Prerequisites (if mentioned)
   - Course level (1, 2, or 3)
   - Whether it's required or elective
3. If the course is part of a specific program, note which department or faculty offers it
4. Mention when the course is typically offered (semester) if this information is available

Ensure your answer is well-structured with clear headings for each course discussed.
Use tables if presenting information about multiple courses.

**Context:**
{context}

**Question:**
{question}

**Answer:**
"""

course_prompt = PromptTemplate(
    input_variables=["context", "question"],
    template=course_template
)
# --------------------------------------------------------------------------
# Custom LLM Classes
# --------------------------------------------------------------------------
class OllamaLLM(LLM):
    model_name: str = "gemma3:12b "
    temperature: float = 0.0
    # Make _chat_history a regular instance variable instead of a ClassVar
    
    def __init__(self, model_name: str = "gemma3:12b", temperature: float = 0.0):
        super().__init__()
        self.model_name = model_name
        self.temperature = temperature
        self._chat_history = []  # Initialize as an instance variable
    
    @property
    def _llm_type(self) -> str:
        return "ollama"
    
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        try:
            # Add the user's message to the chat history
            self._chat_history.append({"role": "user", "content": prompt})
            
            # Use ollama.chat to maintain context across calls
            response = ollama.chat(
                model=self.model_name,
                messages=self._chat_history,
                options={
                    "temperature": self.temperature,
                    # Add other options as needed
                    # "num_predict": 128,
                    # "top_k": 40,
                    # "top_p": 0.9,
                }
            )
            
            # Extract the assistant's message from the response
            assistant_message = response.get('message', {}).get('content', '')
            
            # Add the assistant's response to the chat history
            self._chat_history.append({"role": "assistant", "content": assistant_message})
            
            # Keep chat history to a reasonable size to prevent context overflow
            if len(self._chat_history) > 20:  # Adjust this limit as needed
                # Remove oldest messages but keep the most recent ones
                self._chat_history = self._chat_history[-20:]
            
            return assistant_message
        except Exception as e:
            logging.error(f"Error calling Ollama chat: {str(e)}")
            return f"Error generating response: {str(e)}"
    
    def clear_history(self):
        """Clear the chat history."""
        self._chat_history = []
    
    @property
    def _identifying_params(self):
        return {"model_name": self.model_name, "temperature": self.temperature}

class GeminiLLM(LLM):
    """LLM wrapper for Google's Gemini API."""
    
    model_name: str = "models/gemini-2.0-flash-lite"
    temperature: float = 0.0
    top_p: float = 0.95
    top_k: int = 40
    max_output_tokens: int = 2048
    
    def __init__(self, api_key: str, model_name: str = "models/gemini-2.0-flash-lite", 
                 temperature: float = 0.0, top_p: float = 0.95, top_k: int = 40,
                 max_output_tokens: int = 2048):
        """Initialize with parameters."""
        super().__init__()
        self._api_key = api_key  # Store as private attribute to avoid Pydantic validation issues
        self.model_name = model_name
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.max_output_tokens = max_output_tokens
        self._chat_history = []  # Initialize chat history
        
        # Configure the Gemini API
        genai.configure(api_key=self._api_key)
    
    @property
    def _llm_type(self) -> str:
        """Return type of LLM."""
        return "gemini"
    
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """Call the Gemini API."""
        try:
            # Add the user's message to the chat history
            self._chat_history.append({"role": "user", "content": prompt})
            
            # Initialize the model
            model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "top_k": self.top_k,
                    "max_output_tokens": self.max_output_tokens,
                }
            )
            
            # Convert chat history to Gemini's format
            chat_history = []
            for msg in self._chat_history:
                if msg["role"] == "user":
                    chat_history.append({"role": "user", "parts": [msg["content"]]})
                elif msg["role"] == "assistant":
                    chat_history.append({"role": "model", "parts": [msg["content"]]})
            
            # Start a chat session based on history
            chat = model.start_chat(history=chat_history[:-1] if len(chat_history) > 1 else [])
            
            # Get response for the last message
            response = chat.send_message(chat_history[-1]["parts"][0])
            
            # Extract content
            assistant_message = response.text
            
            # Add the assistant's response to the chat history
            self._chat_history.append({"role": "assistant", "content": assistant_message})
            
            # Keep chat history to a reasonable size to prevent context overflow
            if len(self._chat_history) > 20:  # Adjust this limit as needed
                self._chat_history = self._chat_history[-20:]
            
            return assistant_message
        except Exception as e:
            logging.error(f"Error calling Gemini API: {str(e)}")
            return f"Error generating response: {str(e)}"
    
    def clear_history(self):
        """Clear the chat history."""
        self._chat_history = []
    
    @property
    def _identifying_params(self):
        # Don't include the API key in the identifying parameters
        return {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "max_output_tokens": self.max_output_tokens
        }

# --------------------------------------------------------------------------
# BM25 Retriever
# --------------------------------------------------------------------------
from rank_bm25 import BM25Okapi

class BM25Retriever(BaseRetriever):
    _documents: list = PrivateAttr()
    _tokenized: list = PrivateAttr()
    _k: int = PrivateAttr()
    _bm25 = PrivateAttr()

    def __init__(self, documents: list, k: int = 10):
        super().__init__()
        self._documents = documents
        self._tokenized = [doc.page_content.lower().split() for doc in documents]
        self._k = k
        self._bm25 = BM25Okapi(self._tokenized)

    def _get_relevant_documents(self, query: str, **kwargs) -> list:
        tokens = query.lower().split()
        scores = self._bm25.get_scores(tokens)
        scored_docs = sorted(zip(self._documents, scores), key=lambda x: x[1], reverse=True)
        return [doc for doc, s in scored_docs][:self._k]

    get_relevant_documents = _get_relevant_documents

# --------------------------------------------------------------------------
# Ensemble Retriever
# --------------------------------------------------------------------------
class EnsembleRetriever(BaseRetriever):
    _retrievers: list = PrivateAttr()
    _weights: list = PrivateAttr()
    _threshold: float = PrivateAttr()

    def __init__(self, retrievers: list, weights: list, threshold: float = 0.1):
        super().__init__()
        if len(retrievers) != len(weights):
            raise ValueError("The number of retrievers must match the number of weights.")
        self._retrievers = retrievers
        self._weights = weights
        self._threshold = threshold

    def _get_relevant_documents(self, query: str, **kwargs) -> list:
        doc_scores = {}
        for retriever, weight in zip(self._retrievers, self._weights):
            docs = retriever.get_relevant_documents(query, **kwargs)
            for rank, doc in enumerate(docs):
                score = weight * (1.0 / (rank + 1))
                # Slightly boost if there's a heading
                if doc.metadata.get("heading", "N/A") != "N/A":
                    score *= 1.1
                doc_id = doc.metadata.get("source_file", doc.id)
                if doc_id in doc_scores:
                    doc_scores[doc_id]["score"] += score
                else:
                    doc_scores[doc_id] = {"doc": doc, "score": score}
        # Filter out docs below threshold
        filtered = [item["doc"] for item in doc_scores.values() if item["score"] >= self._threshold]
        # Sort by final ensemble score
        sorted_docs = sorted(
            filtered,
            key=lambda d: doc_scores[d.metadata.get("source_file", d.id)]["score"],
            reverse=True
        )
        return sorted_docs

    get_relevant_documents = _get_relevant_documents

# --------------------------------------------------------------------------
# Cross-Encoder Re-ranking
# --------------------------------------------------------------------------
def rerank_with_crossencoder(query: str, docs: list) -> list:
    if not docs:
        return []
    start = time.perf_counter()
    pairs = [(query, doc.page_content) for doc in docs]
    scores = cross_encoder.predict(pairs)
    ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
    end = time.perf_counter()
    logging.info(f"Cross-encoder re-ranking took {end - start:.2f} seconds")
    return [doc for doc, score in ranked]

# --------------------------------------------------------------------------
# Query Expansion / Metadata Filtering
# --------------------------------------------------------------------------
def expand_query(query: str, llm: LLM) -> list:
    start = time.perf_counter()
    expanded = [
        query,
        query + " courses",
        query.replace("student", "learner")
    ]
    result = list(set(expanded))
    end = time.perf_counter()
    logging.info(f"Query expansion took {end - start:.2f} seconds")
    return result

def filter_documents_by_metadata(docs: list, query: str) -> list:
    start = time.perf_counter()
    if "uwi" in query.lower():
        filtered = [doc for doc in docs if "uwi" in doc.metadata.get("source_file", "").lower()]
        if filtered:
            docs = filtered
    end = time.perf_counter()
    logging.info(f"Metadata filtering took {end - start:.2f} seconds")
    return docs

# --------------------------------------------------------------------------
# FastAPI App
# --------------------------------------------------------------------------
app = FastAPI(title="Document QA API")

docs = None
vector_store = None
embedding_model = None
ensemble_ret = None
llm = None
selected_llm_backend = "ollama"  # Can be "ollama" or "gemini"

CACHE_DIR = Path("./cache")
DOCS_CACHE = CACHE_DIR / "docs.joblib"
VECTORS_CACHE = CACHE_DIR / "vectors.joblib"
EMBEDDINGS_CACHE = CACHE_DIR / "embeddings.joblib"
@app.on_event("startup")
async def startup_event():
    global docs, vector_store, embedding_model, sparse_embeddings, ensemble_ret, hybrid_ret, llm, selected_llm_backend

    startup_start = time.perf_counter()
    try:
        load_start = time.perf_counter()
        logging.info("Attempting to load existing Qdrant store...")
        try:
            # First try to load with force_recreate=False
            docs, vector_store, dense_embeddings, sparse_embeddings = load_existing_qdrant_store(
                collection_name="my_collection",
                docs_cache_path="docs_cache.joblib",
                qdrant_url="http://localhost:6333",
                force_recreate=False
            )
            load_end = time.perf_counter()
            logging.info(f"Successfully loaded existing Qdrant store in {load_end - load_start:.2f} seconds")
        except Exception as e:
            if "does not contain sparse vectors" in str(e):
                logging.warning(f"Collection exists but doesn't support hybrid search: {e}")
                logging.info("Recreating collection with hybrid search support...")
                
                # Try again with force_recreate=True
                docs, vector_store, dense_embeddings, sparse_embeddings = load_existing_qdrant_store(
                    collection_name="my_collection",
                    docs_cache_path="docs_cache.joblib",
                    qdrant_url="http://localhost:6333",
                    force_recreate=True
                )
                load_end = time.perf_counter()
                logging.info(f"Successfully recreated Qdrant store with hybrid search in {load_end - load_start:.2f} seconds")
            else:
                # If it's a different error, fall back to full initialization
                raise e
    except Exception as e:
        fallback_start = time.perf_counter()
        logging.warning(f"Could not load existing store ({str(e)}). Running full initialization...")
        docs, vector_store, dense_embeddings, sparse_embeddings = initialize_documents_and_vector_store(
            doc_folder="./docs",
            collection_name="my_collection"
        )
        fallback_end = time.perf_counter()
        logging.info(f"Full initialization took {fallback_end - fallback_start:.2f} seconds")

    # Initialize retrievers with the loaded resources
    retriever_init_start = time.perf_counter()
    
    # Standard semantic retriever (dense embeddings only)
    vector_store.retrieval_mode = RetrievalMode.DENSE
    semantic_retriever = vector_store.as_retriever(search_kwargs={"k": 25})
    
    # BM25 retriever for traditional keyword search
    bm25_retriever = BM25Retriever(docs, k=25)
    
    # MMR retriever for diversifying results
    mmr_retriever = vector_store.as_retriever(
        search_type="mmr", search_kwargs={"k": 25, "fetch_k": 30, "lambda_mult": 0.5}
    )
    
    # Hybrid retriever that combines dense and sparse embeddings
    vector_store.retrieval_mode = RetrievalMode.HYBRID
    hybrid_ret = vector_store.as_retriever(search_kwargs={"k": 25})

    # Ensemble retriever that combines multiple retrievers with different weights
    ensemble_ret = EnsembleRetriever(
        retrievers=[hybrid_ret,semantic_retriever, bm25_retriever],
        weights=[1.0, 0.8, 0.8,],  # Give higher weight to hybrid retriever
        threshold=0.1
    )
    
    # Initialize the LLM based on selected backend
    embedding_model = dense_embeddings  # For compatibility with the rest of the code
    
    # Initialize the LLM based on selected backend
    if selected_llm_backend == "gemini":
        gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
        if not gemini_api_key or gemini_api_key.strip() == "":
            logging.warning("GEMINI_API_KEY not found in environment variables. Falling back to Ollama.")
            llm = OllamaLLM(model_name="gemma3:12b", temperature=0.0)
            selected_llm_backend = "ollama"
        else:
            try:
                llm = GeminiLLM(api_key=gemini_api_key, temperature=0.0)
                logging.info("Successfully initialized Gemini LLM.")
            except Exception as e:
                logging.error(f"Failed to initialize Gemini LLM: {e}. Falling back to Ollama.")
                llm = OllamaLLM(model_name="gemma3:12b", temperature=0.0)
                selected_llm_backend = "ollama"
    else:
        llm = OllamaLLM(model_name="gemma3:12b", temperature=0.0)
        logging.info("Initialized Ollama LLM.")
    
    retriever_init_end = time.perf_counter()
    logging.info(f"Retriever and LLM initialization took {retriever_init_end - retriever_init_start:.2f} seconds")

    startup_end = time.perf_counter()
    logging.info(f"API Startup: All resources initialized in {startup_end - startup_start:.2f} seconds.")

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    answer: str
    processing_time: float
    context: str

class SwitchLLMRequest(BaseModel):
    backend: str  # "ollama" or "gemini"
    api_key: Optional[str] = None  # Optional API key for Gemini

@app.post("/switch_llm")
async def switch_llm(request: SwitchLLMRequest):
    global llm, selected_llm_backend
    
    if request.backend not in ["ollama", "gemini"]:
        raise HTTPException(status_code=400, detail="Invalid backend. Must be 'ollama' or 'gemini'.")
    
    try:
        if request.backend == "gemini":
            # Use provided API key or get from environment
            api_key = request.api_key or os.environ.get("GEMINI_API_KEY", "")
            
            # Explicit check for empty API key
            if not api_key or api_key.strip() == "":
                raise HTTPException(
                    status_code=400, 
                    detail="Gemini API key not provided. Please provide an API key in the request or set the GEMINI_API_KEY environment variable."
                )
                
            # Initialize Gemini LLM with the API key
            try:
                llm = GeminiLLM(api_key=api_key, temperature=0.0)
                selected_llm_backend = "gemini"
                
                # Store API key in environment variable for future use
                if request.api_key:
                    os.environ["GEMINI_API_KEY"] = request.api_key
                    
                return {"message": "Successfully switched to Gemini LLM", "backend": "gemini"}
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to initialize Gemini LLM: {str(e)}"
                )
        else:
            llm = OllamaLLM(model_name="gemma3:12b", temperature=0.0)
            selected_llm_backend = "ollama"
            return {"message": "Successfully switched to Ollama LLM", "backend": "ollama"}
    except HTTPException:
        # Re-raise HTTP exceptions as is
        raise
    except Exception as e:
        # Handle any other unexpected errors
        raise HTTPException(status_code=500, detail=f"Error switching LLM: {str(e)}")

def format_documents_for_llm(docs):
    """
    Format a list of documents with enhanced metadata for better LLM context.
    This function creates a formatted string with special markers and metadata
    that helps the LLM understand the structure and relevance of each document.
    
    Args:
        docs: List of Document objects
        
    Returns:
        str: Formatted string with metadata-enhanced context
    """
    if not docs:
        return "No relevant documents found."
    
    formatted_docs = []
    
    for i, doc in enumerate(docs):
        # Extract metadata
        source = doc.metadata.get("source_file", "Unknown")
        heading = doc.metadata.get("heading", "N/A")
        doc_format = doc.metadata.get("format", "text")
        
        # Create document header with metadata
        doc_header = f"\n--- DOCUMENT [{i+1}] ---\n"
        doc_header += f"SOURCE: {source}\n"
        
        if heading != "N/A":
            doc_header += f"HEADING: {heading}\n"
        
        # Add any other useful metadata
        if "department" in doc.metadata:
            doc_header += f"DEPARTMENT: {doc.metadata['department']}\n"
        if "faculty" in doc.metadata:
            doc_header += f"FACULTY: {doc.metadata['faculty']}\n"
        if "title" in doc.metadata:
            doc_header += f"TITLE: {doc.metadata['title']}\n"
            
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
    
    Args:
        docs: List of Document objects
        query: Original user query
        
    Returns:
        List of Document objects with enriched metadata
    """
    if not docs:
        return []
    
    # Extract query keywords for targeted enrichment
    query_keywords = set(query.lower().split())
    
    # Common patterns for document classification
    course_code_pattern = re.compile(r'\b[A-Z]{4}\d{4}\b')  # e.g., COMP3456
    credit_pattern = re.compile(r'\b(\d+)\s*credits?\b', re.IGNORECASE)
    level_pattern = re.compile(r'\blevel\s*(\d+)\b', re.IGNORECASE)
    
    for doc in docs:
        content = doc.page_content
        content_lower = content.lower()
        
        # Initialize metadata fields if not present
        if "doc_type" not in doc.metadata:
            doc.metadata["doc_type"] = "general"
            
        if "keywords" not in doc.metadata:
            doc.metadata["keywords"] = []
        
        # Document type classification
        if course_code_pattern.search(content):
            doc.metadata["doc_type"] = "course_description"
            
            # Extract course codes
            course_codes = course_code_pattern.findall(content)
            if course_codes:
                doc.metadata["course_codes"] = course_codes
                
            # Extract credit information if available
            credit_matches = credit_pattern.findall(content)
            if credit_matches:
                doc.metadata["credits"] = credit_matches[0]
                
            # Extract level information
            level_matches = level_pattern.findall(content)
            if level_matches:
                doc.metadata["level"] = level_matches[0]
                
        elif any(term in content_lower for term in ["requirement", "mandatory", "compulsory", "must complete"]):
            doc.metadata["doc_type"] = "requirement"
            
            # Check for specific requirement types
            if "prerequisite" in content_lower:
                doc.metadata["requirement_type"] = "prerequisite"
            elif "graduate" in content_lower or "graduation" in content_lower:
                doc.metadata["requirement_type"] = "graduation"
            elif "assessment" in content_lower:
                doc.metadata["requirement_type"] = "assessment"
                
        elif any(term in content_lower for term in ["policy", "regulation", "rule", "procedure"]):
            doc.metadata["doc_type"] = "policy"
            
            # Identify specific policy areas
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
        
        # Calculate a document relevance score based on keyword matches
        keyword_count = len(doc.metadata["keywords"])
        course_code_bonus = 5 if "course_codes" in doc.metadata else 0
        type_bonus = 3 if doc.metadata["doc_type"] != "general" else 0
        
        # Add a basic relevance score (0-100)
        relevance = min(100, (keyword_count * 10) + course_code_bonus + type_bonus)
        doc.metadata["relevance_score"] = relevance
    
    # Sort documents by relevance score (highest first)
    docs.sort(key=lambda x: x.metadata.get("relevance_score", 0), reverse=True)
    
    return docs

# Update your query_endpoint function:
@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    start_time = time.perf_counter()
    user_query = request.query
    logging.info(f"Received query: {user_query}")

    try:
        # 1. Expand the query
        expanded_queries = expand_query(user_query, llm)

        # 2. Retrieve documents for each expanded query
        all_initial_docs = []
        for eq in expanded_queries:
            docs_for_eq = ensemble_ret.get_relevant_documents(eq)
            all_initial_docs.extend(docs_for_eq)

        # 3. Deduplicate and filter documents
        unique_docs = {doc.metadata.get("source_file", doc.id): doc for doc in all_initial_docs}.values()
        initial_docs = list(unique_docs)
        initial_docs = filter_documents_by_metadata(initial_docs, user_query)

        # 4. Re-rank with cross-encoder
        reranked_docs = rerank_with_crossencoder(user_query, initial_docs)
        
        # Limit to top 15 documents for context
        top_docs = reranked_docs[:15]
        
        # 5. Classify and enrich documents with metadata
        enriched_docs = classify_and_enrich_documents(top_docs, user_query)

        # 6. Format documents with enhanced metadata
        formatted_context = format_documents_for_llm(enriched_docs)

        # 7. Choose prompt based on query and document types
        query_lower = user_query.lower()
        doc_types = [doc.metadata.get("doc_type", "general") for doc in enriched_docs]
        
        if any(keyword in query_lower for keyword in ["credit", "graduate", "bsc", "degree", "study"]) or "requirement" in doc_types:
            chosen_prompt = credit_prompt
            logging.info("Using credit requirements prompt.")
        elif any(keyword in query_lower for keyword in ["course", "class", "subject", "lecture"]) or "course_description" in doc_types:
            chosen_prompt = course_prompt
            logging.info("Using course-specific prompt.")
        else:
            chosen_prompt = default_prompt
            logging.info("Using default prompt.")

        prompt_str = chosen_prompt.format(context=formatted_context, question=user_query)

        # 8. Call the LLM
        answer = llm._call(prompt_str)
        processing_time = time.perf_counter() - start_time

        # For debugging: log document counts and types
        doc_type_counts = {}
        for doc in enriched_docs:
            doc_type = doc.metadata.get("doc_type", "general")
            doc_type_counts[doc_type] = doc_type_counts.get(doc_type, 0) + 1
            
        logging.info(f"Document type distribution: {doc_type_counts}")
        logging.info(f"Processing time: {processing_time:.2f} seconds")

        return QueryResponse(answer=answer, processing_time=processing_time, context=formatted_context)
    except Exception as e:
        logging.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/model_info")
async def model_info():
    """Return information about the currently selected model."""
    global llm, selected_llm_backend
    
    try:
        model_params = llm._identifying_params
        return {
            "backend": selected_llm_backend,
            "model_params": model_params
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting model info: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)