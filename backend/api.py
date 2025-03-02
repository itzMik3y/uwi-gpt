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

from typing import Optional, List, ClassVar
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, PrivateAttr
from pathlib import Path
import nltk
from langchain.prompts import PromptTemplate
from langchain.llms.base import LLM
from langchain.schema import BaseRetriever
import ollama
# --- Import the Qdrant-based ingestion function ---
from ingestion import initialize_documents_and_vector_store, load_existing_qdrant_store
from langchain_qdrant import RetrievalMode

# Import your custom Document class.
from document import Document
Document.__module__ = "document"  # Ensures joblib can unpickle Document consistently.

from sentence_transformers import CrossEncoder
cross_encoder = CrossEncoder("BAAI/bge-large-en-v1.5")

from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-large-en-v1.5")

# Configure logging.
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# --------------------------------------------------------------------------
# Prompt Templates
# --------------------------------------------------------------------------
default_template = """
You are an AI assistant that answers questions based only on the provided context.
Please provide your answer in markdown format with clear bullet points or numbered lists if appropriate.

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

credit_template = """
You are an AI assistant that answers questions based only on the provided context from a faculty handbook.
The context includes details about credit requirements for a BSc in Computer Science.
Please perform the following steps in your answer:
1. Identify the number of credits required at Level 1.
2. Identify the number of credits required at Levels 2/3.
3. Identify the foundation course details (note that one foundation course gives 6 credits instead of 3).
4. Sum these values appropriately. If there are two possibilities (e.g., 93 or 96), provide both.
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

# --------------------------------------------------------------------------
# Custom LLM Class (Ollama)
# --------------------------------------------------------------------------
class OllamaLLM(LLM):
    model_name: str = "llama3:8b"
    temperature: float = 0.0
    _chat_history: ClassVar[List[dict]] = []
    
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

CACHE_DIR = Path("./cache")
DOCS_CACHE = CACHE_DIR / "docs.joblib"
VECTORS_CACHE = CACHE_DIR / "vectors.joblib"
EMBEDDINGS_CACHE = CACHE_DIR / "embeddings.joblib"
@app.on_event("startup")
async def startup_event():
    global docs, vector_store, embedding_model, sparse_embeddings, ensemble_ret, hybrid_ret, llm

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
    # mmr_retriever = vector_store.as_retriever(
    #     search_type="mmr", search_kwargs={"k": 25, "fetch_k": 30, "lambda_mult": 0.5}
    # )
    
    # Hybrid retriever that combines dense and sparse embeddings
    vector_store.retrieval_mode = RetrievalMode.HYBRID
    hybrid_ret = vector_store.as_retriever(search_kwargs={"k": 25})

    # Ensemble retriever that combines multiple retrievers with different weights
    ensemble_ret = EnsembleRetriever(
        retrievers=[hybrid_ret, semantic_retriever, bm25_retriever],
        weights=[1.2, 1.0, 0.9],  # Give higher weight to hybrid retriever
        threshold=0.1
    )
    
    # Initialize the LLM
    embedding_model = dense_embeddings  # For compatibility with the rest of the code
    llm = OllamaLLM(model_name="llama3:8b", temperature=0.0)
    
    retriever_init_end = time.perf_counter()
    logging.info(f"Retriever and LLM initialization took {retriever_init_end - retriever_init_start:.2f} seconds")

    startup_end = time.perf_counter()
    logging.info(f"API Startup: All resources initialized in {startup_end - startup_start:.2f} seconds.")

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    answer: str
    processing_time: float

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

        # 5. Choose prompt and format
        combined_context = "\n".join([doc.page_content for doc in reranked_docs[:10]])
        if any(keyword in user_query.lower() for keyword in ["credit", "graduate", "bsc", "degree", "study"]):
            chosen_prompt = credit_prompt
            logging.info("Using custom credit prompt.")
        else:
            chosen_prompt = default_prompt
            logging.info("Using default prompt.")

        prompt_str = chosen_prompt.format(context=combined_context, question=user_query)

        # 6. Call the LLM
        answer = llm._call(prompt_str)
        processing_time = time.perf_counter() - start_time

        return QueryResponse(answer=answer, processing_time=processing_time)
    except Exception as e:
        logging.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
