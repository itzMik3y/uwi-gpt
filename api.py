#!/usr/bin/env python
import os
import re
import subprocess
import time
import logging
import numpy as np
import joblib
import json

from typing import Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, PrivateAttr
from pathlib import Path
import nltk
from langchain.prompts import PromptTemplate
from langchain.llms.base import LLM
from langchain.schema import BaseRetriever

# --- Import the Qdrant-based ingestion function ---
from ingestion import initialize_documents_and_vector_store, load_existing_qdrant_store

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

    @property
    def _llm_type(self) -> str:
        return "ollama"

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        command = ["ollama", "run", self.model_name, "p"]
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8"
        )
        out, err = process.communicate(prompt)
        if err:
            logging.error(f"Ollama stderr: {err}")
        return out

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
    global docs, vector_store, embedding_model, ensemble_ret, llm

    startup_start = time.perf_counter()
    try:
        load_start = time.perf_counter()
        logging.info("Attempting to load existing Qdrant store...")
        docs, vector_store, embedding_model = load_existing_qdrant_store(
            collection_name="my_collection",
            docs_cache_path="docs_cache.joblib",
            qdrant_url="http://localhost:6333"
        )
        load_end = time.perf_counter()
        logging.info(f"Successfully loaded existing Qdrant store in {load_end - load_start:.2f} seconds")
    except Exception as e:
        fallback_start = time.perf_counter()
        logging.warning(f"Could not load existing store ({str(e)}). Running full initialization...")
        docs, vector_store, embedding_model = initialize_documents_and_vector_store(
            doc_folder="./docs",
            collection_name="my_collection"
        )
        fallback_end = time.perf_counter()
        logging.info(f"Full initialization took {fallback_end - fallback_start:.2f} seconds")

    # Initialize retrievers with the loaded resources
    retriever_init_start = time.perf_counter()
    semantic_retriever = vector_store.as_retriever(search_kwargs={"k": 25})
    bm25_retriever = BM25Retriever(docs, k=25)
    mmr_retriever = vector_store.as_retriever(
        search_type="mmr", search_kwargs={"k": 25, "fetch_k": 30, "lambda_mult": 0.5}
    )

    ensemble_ret = EnsembleRetriever(
        retrievers=[semantic_retriever, bm25_retriever, mmr_retriever],
        weights=[1.0, 0.9, 0.9],
        threshold=1.0
    )
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
    total_start = time.perf_counter()
    user_query = request.query
    logging.info(f"Received query: {user_query}")

    try:
        # 1. Expand the query
        expand_start = time.perf_counter()
        expanded_queries = expand_query(user_query, llm)
        expand_end = time.perf_counter()
        logging.info(f"Query expansion step took {expand_end - expand_start:.2f} seconds")

        # 2. Retrieve documents for each expanded query
        retrieve_start = time.perf_counter()
        all_initial_docs = []
        for eq in expanded_queries:
            docs_for_eq = ensemble_ret.get_relevant_documents(eq)
            all_initial_docs.extend(docs_for_eq)
        retrieve_end = time.perf_counter()
        logging.info(f"Document retrieval step took {retrieve_end - retrieve_start:.2f} seconds")

        # 3. Deduplicate and filter documents
        dedup_start = time.perf_counter()
        unique_docs = {doc.metadata.get("source_file", doc.id): doc for doc in all_initial_docs}.values()
        initial_docs = list(unique_docs)
        initial_docs = filter_documents_by_metadata(initial_docs, user_query)
        dedup_end = time.perf_counter()
        logging.info(f"Deduplication and metadata filtering took {dedup_end - dedup_start:.2f} seconds")

        # 4. Re-rank with cross-encoder
        rerank_start = time.perf_counter()
        reranked_docs = rerank_with_crossencoder(user_query, initial_docs)
        rerank_end = time.perf_counter()
        logging.info(f"Re-ranking step took {rerank_end - rerank_start:.2f} seconds")

        # 5. Choose prompt and format
        prompt_start = time.perf_counter()
        combined_context = "\n".join([doc.page_content for doc in reranked_docs[:10]])
        if any(keyword in user_query.lower() for keyword in ["credit", "graduate", "bsc", "degree", "study"]):
            chosen_prompt = credit_prompt
            logging.info("Using custom credit prompt.")
        else:
            chosen_prompt = default_prompt
            logging.info("Using default prompt.")
        prompt_str = chosen_prompt.format(context=combined_context, question=user_query)
        prompt_end = time.perf_counter()
        logging.info(f"Prompt selection and formatting took {prompt_end - prompt_start:.2f} seconds")

        # 6. Call the LLM
        llm_start = time.perf_counter()
        answer = llm._call(prompt_str)
        llm_end = time.perf_counter()
        logging.info(f"LLM call took {llm_end - llm_start:.2f} seconds")

        total_end = time.perf_counter()
        processing_time = total_end - total_start
        logging.info(f"Total processing time: {processing_time:.2f} seconds")

        return QueryResponse(answer=answer, processing_time=processing_time)
    except Exception as e:
        logging.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
