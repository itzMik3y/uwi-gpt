#!/usr/bin/env python
"""
rag_api/initialize.py - Module for initializing and managing RAG components
"""

import os
import time
import logging
from typing import Optional, Tuple, Dict

# Import custom LLM classes and other components
from langchain.llms.base import LLM
from langchain_qdrant import QdrantVectorStore, RetrievalMode
from langchain.schema import BaseRetriever
from sentence_transformers import CrossEncoder

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

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# --------------------------------------------------------------------------
# Resource Initialization
# --------------------------------------------------------------------------
def initialize_rag_resources():
    """
    Initialize all RAG-related resources during application startup.
    This includes documents, vector stores, embeddings, retrievers, and LLMs.
    """
    global docs, vector_store, dense_embeddings, sparse_embeddings, ensemble_retriever
    global hybrid_retriever, llm, cross_encoder, selected_llm_backend
    
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
                    doc_folder=os.path.join(BASE_DIR, "rag_api", "docs"),  # Use absolute path
                    collection_name="my_collection",
                    docs_cache_path=os.path.join(BASE_DIR, "rag_api", "docs_cache.joblib"),  # Add this
                    state_cache_path=os.path.join(BASE_DIR, "rag_api", "docs_state.json")  # Add this
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
            doc_folder=os.path.join(BASE_DIR, "rag_api", "docs"),  # Use absolute path
            collection_name="my_collection",
            docs_cache_path=os.path.join(BASE_DIR, "rag_api", "docs_cache.joblib"),  # Add this
            state_cache_path=os.path.join(BASE_DIR, "rag_api", "docs_state.json")  # Add this
        )
        fallback_end = time.perf_counter()
        logger.info(f"Full initialization took {fallback_end - fallback_start:.2f} seconds")

    # Initialize retrievers with the loaded resources
    retriever_init_start = time.perf_counter()
    
    # Import BM25Retriever and EnsembleRetriever
    from .retrievers import BM25Retriever, EnsembleRetriever
    
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
    hybrid_retriever = vector_store.as_retriever(search_kwargs={"k": 25})

    # Ensemble retriever that combines multiple retrievers with different weights
    ensemble_retriever = EnsembleRetriever(
        retrievers=[hybrid_retriever, semantic_retriever, bm25_retriever],
        weights=[1.0, 0.8, 0.8],  # Give higher weight to hybrid retriever
        threshold=0.1
    )
    
    # Initialize the LLM based on selected backend
    llm = initialize_llm()
    
    retriever_init_end = time.perf_counter()
    logger.info(f"Retriever and LLM initialization took {retriever_init_end - retriever_init_start:.2f} seconds")

    startup_end = time.perf_counter()
    logger.info(f"RAG resources initialized in {startup_end - startup_start:.2f} seconds.")

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
    
    if backend not in ["ollama", "gemini"]:
        raise ValueError("Invalid backend. Must be 'ollama' or 'gemini'.")
    
    if backend == "gemini":
        # Use provided API key or get from environment
        api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        
        # Explicit check for empty API key
        if not api_key or api_key.strip() == "":
            raise ValueError("Gemini API key not provided. Please provide an API key in the request or set the GEMINI_API_KEY environment variable.")
            
        # Initialize Gemini LLM with the API key
        try:
            from .llm_classes import GeminiLLM
            llm = GeminiLLM(api_key=api_key, temperature=0.0)
            selected_llm_backend = "gemini"
            
            # Store API key in environment variable for future use
            if api_key:
                os.environ["GEMINI_API_KEY"] = api_key
                
            return "gemini"
        except Exception as e:
            raise ValueError(f"Failed to initialize Gemini LLM: {str(e)}")
    else:
        from .llm_classes import OllamaLLM
        llm = OllamaLLM(model_name="gemma3:12b", temperature=0.0)
        selected_llm_backend = "ollama"
        return "ollama"

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