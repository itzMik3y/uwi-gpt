#!/usr/bin/env python
"""
rag_api/initialize.py - Module for initializing and managing RAG components
"""

import os
import time
import logging
import json
from typing import Optional, Tuple, Dict, List, Any

# Import custom LLM classes and other components
from langchain.llms.base import LLM
from langchain_qdrant import QdrantVectorStore, RetrievalMode
from langchain.schema import BaseRetriever
from sentence_transformers import CrossEncoder
from dotenv import load_dotenv

# Global variables to store initialized components
docs = None
vector_store = None
dense_embeddings = None
sparse_embeddings = None
ensemble_retriever = None 
hybrid_retriever = None
llm = None
selected_llm_backend = "ollama"  # Default LLM backend
cross_encoder = None

# New global variables for course data
course_docs = None
course_vector_store = None
dual_retriever = None

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --------------------------------------------------------------------------
# Resource Initialization
# --------------------------------------------------------------------------
def initialize_rag_resources():
    """
    Initialize all RAG-related resources during application startup.
    This includes documents, vector stores, embeddings, retrievers, and LLMs.
    Uses adaptive ensemble retrieval with optimized k values and enhanced BM25.
    """
    load_dotenv() 
    global docs, vector_store, dense_embeddings, sparse_embeddings, ensemble_retriever
    global hybrid_retriever, llm, cross_encoder, selected_llm_backend
    global course_docs, course_vector_store, dual_retriever
    
    startup_start = time.perf_counter()
    
    try:
        # Initialize CrossEncoder for reranking
        cross_encoder = CrossEncoder("BAAI/bge-reranker-v2-m3")
        
        # Load Qdrant store with existing documents
        from .ingestion import load_existing_qdrant_store, initialize_documents_and_vector_store
        load_start = time.perf_counter()
        
        try:
            # First try to load with force_recreate=False
            docs, vector_store, dense_embeddings, sparse_embeddings = initialize_documents_and_vector_store(
                doc_folder=os.path.join(BASE_DIR, "rag_api", "docs"),
                collection_name="my_collection",
                docs_cache_path=os.path.join(BASE_DIR, "rag_api", "docs_cache.joblib"),
                state_cache_path=os.path.join(BASE_DIR, "rag_api", "docs_state.json")
            )
            load_end = time.perf_counter()
            logger.info(f"Successfully loaded existing Qdrant store in {load_end - load_start:.2f} seconds")
        except Exception as e:
            if "does not contain sparse vectors" in str(e):
                logger.warning(f"Collection exists but doesn't support hybrid search: {e}")
                logger.info("Recreating collection with hybrid search support...")
                
                # Try again with force_recreate=True
                docs, vector_store, dense_embeddings, sparse_embeddings = initialize_documents_and_vector_store(
                    doc_folder=os.path.join(BASE_DIR, "rag_api", "docs"),
                    collection_name="my_collection",
                    docs_cache_path=os.path.join(BASE_DIR, "rag_api", "docs_cache.joblib"),
                    state_cache_path=os.path.join(BASE_DIR, "rag_api", "docs_state.json")
                )
                load_end = time.perf_counter()
                logger.info(f"Successfully recreated Qdrant store with hybrid search in {load_end - load_start:.2f} seconds")
            else:
                # If it's a different error, fall back to full initialization
                raise e
    except Exception as e:
        # If there's any error loading the store, initialize from scratch
        fallback_start = time.perf_counter()
        logger.warning(f"Could not load existing store ({str(e)}). Running full initialization...")
        
        from .ingestion import initialize_documents_and_vector_store
        docs, vector_store, dense_embeddings, sparse_embeddings = initialize_documents_and_vector_store(
            doc_folder=os.path.join(BASE_DIR, "rag_api", "docs"),
            collection_name="my_collection",
            docs_cache_path=os.path.join(BASE_DIR, "rag_api", "docs_cache.joblib"),
            state_cache_path=os.path.join(BASE_DIR, "rag_api", "docs_state.json")
        )
        fallback_end = time.perf_counter()
        logger.info(f"Full initialization took {fallback_end - fallback_start:.2f} seconds")

    # Initialize retrievers with the loaded resources
    retriever_init_start = time.perf_counter()
    
    # Import enhanced retrievers
    from .retrievers import EnhancedBM25Retriever, create_adaptive_ensemble_retriever
    
    # Standard semantic retriever (dense embeddings only) with reduced k
    vector_store.retrieval_mode = RetrievalMode.DENSE
    semantic_retriever = vector_store.as_retriever(search_kwargs={"k": 20})
    
    # Enhanced BM25 retriever with lemmatization
    bm25_retriever = EnhancedBM25Retriever(
        docs, 
        k=20,
        use_lemmatization=True  # Enable lemmatization for better matching
    )
    
    # Hybrid retriever that combines dense and sparse embeddings
    vector_store.retrieval_mode = RetrievalMode.HYBRID
    hybrid_retriever = vector_store.as_retriever(search_kwargs={"k": 20})

    # Create adaptive ensemble retriever that adjusts weights based on query type
    ensemble_retriever = create_adaptive_ensemble_retriever(
        hybrid_retriever=hybrid_retriever,
        semantic_retriever=semantic_retriever,
        bm25_retriever=bm25_retriever
    )
    
    # Initialize the course vector store
    course_init_start = time.perf_counter()
    try:
        from .ingestion import initialize_course_vector_store
        course_docs, course_vector_store = initialize_course_vector_store(
            course_data_dir=os.path.join(BASE_DIR, "rag_api", "course_data"),
            collection_name="course_collection",
            course_cache_path=os.path.join(BASE_DIR, "rag_api", "course_cache.joblib"),
            state_cache_path=os.path.join(BASE_DIR, "rag_api", "course_state.json"),
            url=os.environ.get("QDRANT_URL", "http://localhost:6333")
        )
        course_init_end = time.perf_counter()
        if course_vector_store:
            logger.info(f"Successfully initialized course vector store with {len(course_docs) if course_docs else 0} documents in {course_init_end - course_init_start:.2f} seconds")
        else:
            logger.warning("Course vector store initialization returned None. Using only primary retriever.")
    except Exception as e:
        logger.error(f"Error initializing course vector store: {e}", exc_info=True)
        course_docs, course_vector_store = None, None

    # Create dual retriever if course_vector_store is available
    if course_vector_store:
        # Create course retriever
        course_retriever = course_vector_store.as_retriever(search_kwargs={"k": 10})
        
        # Import DualCollectionRetriever from retrievers.py
        from .retrievers import DualCollectionRetriever
        
        # Create dual retriever
        dual_retriever = DualCollectionRetriever(
            primary_retriever=ensemble_retriever,
            course_retriever=course_retriever,
            use_reranking=True,
            max_documents=15,
            max_course_documents=5,
            cross_encoder=cross_encoder
        )
        logger.info("Dual retriever configured with primary and course collections")
    else:
        logger.info("Course vector store not available. Using only primary retriever.")
        dual_retriever = ensemble_retriever  # Fall back to ensemble retriever if course store not available
    
    # Initialize the LLM based on selected backend
    llm = initialize_llm()
    
    retriever_init_end = time.perf_counter()
    logger.info(f"Retriever and LLM initialization took {retriever_init_end - retriever_init_start:.2f} seconds")

    # Log which retrievers are active
    retriever_config = {
        "hybrid_retriever": "Enabled, k=20",
        "semantic_retriever": "Enabled, k=20",
        "bm25_retriever": f"Enabled, k=20, lemmatization={'Enabled' if bm25_retriever._use_lemmatization else 'Disabled'}",
        "ensemble_retriever": "Adaptive (query-dependent weights)",
        "course_retriever": "Enabled, k=10" if course_vector_store else "Disabled",
        "dual_retriever": "Enabled (max_docs=15, max_course_docs=5)" if course_vector_store else "Disabled (using ensemble_retriever)",
        "cross_encoder": "BAAI/bge-reranker-v2-m3"
    }
    logger.info(f"Retriever configuration: {retriever_config}")

    startup_end = time.perf_counter()
    logger.info(f"RAG resources initialized in {startup_end - startup_start:.2f} seconds.")
    
    return {
        "docs_count": len(docs),
        "course_docs_count": len(course_docs) if course_docs else 0,
        "retrievers": retriever_config,
        "llm_backend": selected_llm_backend
    }

def rerank_with_crossencoder(query: str, docs: list) -> list:
    """Re-rank documents using a cross-encoder model"""
    global cross_encoder
    
    if not docs:
        return []
    
    if cross_encoder is None:
        cross_encoder = CrossEncoder("BAAI/bge-reranker-v2-m3")
    
    start = time.perf_counter()
    pairs = [(query, doc.page_content) for doc in docs]
    scores = cross_encoder.predict(pairs)
    ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
    end = time.perf_counter()
    logger.info(f"Cross-encoder re-ranking took {end - start:.2f} seconds")
    return [doc for doc, score in ranked]

def initialize_llm():
    """Initialize the LLM based on the selected backend"""
    global selected_llm_backend
    
    if selected_llm_backend == "gemini":
        try:
            # Import GeminiLLM
            from .llm_classes import GeminiLLM
            
            gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
            if not gemini_api_key or gemini_api_key.strip() == "":
                logger.warning("GEMINI_API_KEY not found in environment variables. Falling back to Ollama.")
                selected_llm_backend = "ollama"
                return initialize_ollama_llm()
            else:
                try:
                    llm = GeminiLLM(api_key=gemini_api_key, temperature=0.0)
                    logger.info("Successfully initialized Gemini LLM.")
                    return llm
                except Exception as e:
                    logger.error(f"Failed to initialize Gemini LLM: {e}. Falling back to Ollama.")
                    selected_llm_backend = "ollama"
                    return initialize_ollama_llm()
        except ImportError:
            logger.warning("Gemini dependencies not available. Falling back to Ollama.")
            selected_llm_backend = "ollama"
            return initialize_ollama_llm()
    else:
        return initialize_ollama_llm()

def initialize_ollama_llm():
    """Initialize the Ollama LLM"""
    from .llm_classes import OllamaLLM
    llm = OllamaLLM(model_name="gemma3:12b", temperature=0.0)
    logger.info("Initialized Ollama LLM.")
    return llm

def switch_llm_backend(backend: str, api_key: Optional[str] = None):
    """Switch the LLM backend between Ollama and Gemini"""
    global llm, selected_llm_backend

    try:
        from .llm_classes import OllamaLLM, GeminiLLM
    except ImportError as e:
        logger.error(f"Failed to import LLM classes: {e}")
        raise ValueError(f"Internal server error: Could not load LLM classes.") from e

    if backend not in ["ollama", "gemini"]:
        raise ValueError("Invalid backend. Must be 'ollama' or 'gemini'.")

    if backend == "gemini":
        effective_api_key = api_key if api_key and api_key.strip() else os.environ.get("GEMINI_API_KEY")

        if not effective_api_key or not effective_api_key.strip():
            logger.warning("Gemini API key not found in request or environment variable GEMINI_API_KEY.")
            raise ValueError("Gemini API key not provided. Please provide an API key in the request or set the GEMINI_API_KEY environment variable.")

        try:
            llm = GeminiLLM(api_key=effective_api_key, temperature=0.0)
            selected_llm_backend = "gemini"
            logger.info(f"Switched LLM to Gemini.")
            return "gemini"
        except Exception as e:
            logger.error(f"Failed to initialize Gemini LLM: {e}", exc_info=True)
            raise ValueError(f"Failed to initialize Gemini LLM: {e}") from e
    else:
        try:
            llm = OllamaLLM(model_name="gemma3:12b", temperature=0.0)
            selected_llm_backend = "ollama"
            logger.info(f"Switched LLM to Ollama.")
            return "ollama"
        except Exception as e:
            logger.error(f"Failed to initialize Ollama LLM: {e}", exc_info=True)
            raise ValueError(f"Failed to initialize Ollama LLM: {e}") from e

def get_model_info():
    """Get information about the currently selected model"""
    global llm, selected_llm_backend
    
    if llm is None:
        llm = initialize_llm()
    
    model_params = llm._identifying_params
    return {
        "backend": selected_llm_backend,
        "model_params": model_params
    }

# Getter functions for components
def get_llm():
    """Get the current LLM instance"""
    global llm
    if llm is None:
        llm = initialize_llm()
    return llm

def get_ensemble_retriever():
    """Get the ensemble retriever"""
    global ensemble_retriever
    return ensemble_retriever

def get_hybrid_retriever():
    """Get the hybrid retriever"""
    global hybrid_retriever
    return hybrid_retriever

def get_documents():
    """Get the documents"""
    global docs
    return docs

def get_vector_store():
    """Get the vector store"""
    global vector_store
    return vector_store

def get_dual_retriever():
    """Get the dual retriever that queries both collections"""
    global dual_retriever
    return dual_retriever

def get_course_retriever():
    """Get the course retriever"""
    global course_vector_store
    if course_vector_store:
        return course_vector_store.as_retriever(search_kwargs={"k": 10})
    return None