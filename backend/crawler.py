# api.py
import os
import re
import subprocess
import time
import logging
import numpy as np
import joblib
import json

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, PrivateAttr

import nltk
from langchain.prompts import PromptTemplate
from langchain.llms.base import LLM
from langchain.schema import BaseRetriever

# Import the vector store loader from ingestion
from ingestion import load_vector_store
# Import your custom Document class
from document import Document

from sentence_transformers import CrossEncoder
cross_encoder = CrossEncoder("BAAI/bge-large-en-v1.5")

from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-large-en-v1.5")

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Define prompt templates
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

# Custom LLM class for Ollama
class OllamaLLM(LLM):
    model_name: str = "llama3:8b"  # Updated model name
    temperature: float = 0.0

    @property
    def _llm_type(self) -> str:
        return "ollama"

    def _call(self, prompt: str, stop: list = None) -> str:
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

# BM25 Retriever
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
        from rank_bm25 import BM25Okapi
        self._bm25 = BM25Okapi(self._tokenized)

    def _get_relevant_documents(self, query: str, **kwargs) -> list:
        tokens = query.lower().split()
        scores = self._bm25.get_scores(tokens)
        scored_docs = sorted(zip(self._documents, scores), key=lambda x: x[1], reverse=True)
        return [doc for doc, s in scored_docs][:self._k]

    get_relevant_documents = _get_relevant_documents

# Ensemble Retriever
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
                if doc.metadata.get("heading", "N/A") != "N/A":
                    score *= 1.1
                doc_id = doc.metadata.get("source_file", doc.id)
                if doc_id in doc_scores:
                    doc_scores[doc_id]["score"] += score
                else:
                    doc_scores[doc_id] = {"doc": doc, "score": score}
        filtered = [item["doc"] for item in doc_scores.values() if item["score"] >= self._threshold]
        sorted_docs = sorted(
            filtered,
            key=lambda d: doc_scores[d.metadata.get("source_file", d.id)]["score"],
            reverse=True
        )
        return sorted_docs

    get_relevant_documents = _get_relevant_documents

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

app = FastAPI(title="Document QA API")

# Global variables for pipeline resources.
docs = None
vector_store = None
ensemble_ret = None
llm = None

@app.on_event("startup")
async def startup_event():
    global docs, vector_store, ensemble_ret, llm
    # Load the vector store from persistent storage using the ingestion helper.
    vector_store = load_vector_store(persist_directory="./chroma_db_bilingual")
    # Load document chunks from cache.
    if os.path.exists("docs_cache.joblib"):
        docs = joblib.load("docs_cache.joblib")
        logging.info(f"Loaded {len(docs)} document chunks from cache.")
    else:
        logging.error("Document cache not found. Please run the ingestion script.")
    # Build retrievers.
    semantic_retriever = vector_store.as_retriever(search_kwargs={"k": 25})
    bm25_retriever = BM25Retriever(docs, k=25)
    ensemble_ret = EnsembleRetriever(
        retrievers=[semantic_retriever, bm25_retriever],
        weights=[1.0, 0.9],
        threshold=1.0
    )
    # Initialize the LLM.
    llm = OllamaLLM(model_name="llama3:8b", temperature=0.0)
    logging.info("API Startup: Resources initialized.")

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
        # 1. Expand the query.
        expanded_queries = expand_query(user_query, llm)
        all_initial_docs = []
        for eq in expanded_queries:
            docs_for_eq = ensemble_ret.get_relevant_documents(eq)
            all_initial_docs.extend(docs_for_eq)
        # 2. Deduplicate and filter.
        unique_docs = {doc.metadata.get("source_file", doc.id): doc for doc in all_initial_docs}.values()
        initial_docs = list(unique_docs)
        initial_docs = filter_documents_by_metadata(initial_docs, user_query)
        # 3. Rerank using cross-encoder.
        reranked_docs = rerank_with_crossencoder(user_query, initial_docs)
        # 4. Combine context and choose prompt.
        combined_context = "\n".join([doc.page_content for doc in reranked_docs[:10]])
        if any(keyword in user_query.lower() for keyword in ["credit", "graduate", "bsc", "degree", "study"]):
            chosen_prompt = credit_prompt
            logging.info("Using custom credit prompt.")
        else:
            chosen_prompt = default_prompt
            logging.info("Using default prompt.")
        prompt_str = chosen_prompt.format(context=combined_context, question=user_query)
        # 5. Call the LLM to get the answer.
        answer = llm._call(prompt_str)
        processing_time = time.perf_counter() - start_time
        return QueryResponse(answer=answer, processing_time=processing_time)
    except Exception as e:
        logging.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
