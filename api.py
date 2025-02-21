import os
import re
import subprocess
import concurrent.futures
import hashlib
import json
import logging
import numpy as np
import uuid
import time  # For timing logs
from typing import Optional, List
from document import Document

import joblib

# Configure logging.
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_chroma import Chroma
from langchain.chains import RetrievalQA
from langchain.llms.base import LLM
from langchain.prompts import PromptTemplate
from langchain.schema import BaseRetriever
from pydantic import PrivateAttr

os.environ["HF_TRUST_REMOTE_CODE"] = "true"

from rank_bm25 import BM25Okapi
import pdfplumber
import nltk

from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-large-en-v1.5")

try:
    import fitz
except ModuleNotFoundError:
    fitz = None
    logging.warning("PyMuPDF (fitz) not found. Install it with 'pip install PyMuPDF' for fallback extraction.")

from transformers import pipeline
# domain_classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")

from sentence_transformers import CrossEncoder
cross_encoder = CrossEncoder("BAAI/bge-large-en-v1.5")


# # =============================================================================
# # Document Class and Helpers
# # =============================================================================
# class Document:
#     def __init__(self, page_content: str, metadata: dict, id: Optional[str] = None):
#         self.page_content = page_content
#         self.metadata = metadata
#         self.id = id or str(uuid.uuid4())

#     def __repr__(self):
#         return f"Document(source={self.metadata.get('source_file', 'N/A')}, length={len(self.page_content)})"

# Example structured data for degree programs (metadata)
degree_programs_data = [
    {
        "title": "B.Sc. Computer Science",
        "department": "Department of Computing",
        "faculty": "Faculty of Science and Technology",
        "description": "Four-year program covering core Computer Science topics..."
    },
    {
        "title": "B.Sc. Computer Systems Engineering",
        "department": "Department of Computing",
        "faculty": "Faculty of Science and Technology",
        "description": "Four-year program focusing on hardware, software, and system design..."
    },
    # ... add more as needed
]

def create_documents_from_data(data_list: List[dict]) -> List[Document]:
    docs = []
    for item in data_list:
        doc = Document(
            page_content=item["description"],
            metadata={
                "title": item["title"],
                "department": item["department"],
                "faculty": item["faculty"]
            }
        )
        docs.append(doc)
    return docs

# =============================================================================
# PDF Caching and Extraction Helpers
# =============================================================================
CACHE_FILE = "pdf_cache.json"

def compute_checksum(filepath: str) -> str:
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            try:
                return json.load(f)
            except Exception as e:
                logging.error(f"Error loading cache: {e}")
                return {}
    return {}

def save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        logging.error(f"Error saving cache: {e}")

def load_pdf_with_tables(filepath: str) -> str:
    texts = []
    table_settings = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "intersection_tolerance": 5,
    }
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                table_texts = []
                tables = page.extract_tables(table_settings=table_settings)
                if tables:
                    for table in tables:
                        if not any(cell and cell.strip() for row in table for cell in row):
                            continue
                        header = [str(cell).strip() if cell else "" for cell in table[0]]
                        rows = table[1:]
                        md_table = "| " + " | ".join(header) + " |\n"
                        md_table += "| " + " | ".join(["---"] * len(header)) + " |\n"
                        for row in rows:
                            row = [str(cell).strip() if cell else "" for cell in row]
                            md_table += "| " + " | ".join(row) + " |\n"
                        table_texts.append(md_table)
                combined = page_text.strip()
                if table_texts:
                    combined = (combined + "\n" if combined else "") + "\n".join(table_texts)
                if combined:
                    texts.append(combined)
        full_text = "\n\n".join(texts)
        if not full_text.strip() and fitz is not None:
            logging.info(f"pdfplumber extracted no text for {filepath}. Using PyMuPDF fallback.")
            doc = fitz.open(filepath)
            full_text = "\n\n".join(page.get_text("text") for page in doc)
        return full_text
    except Exception as e:
        logging.error(f"Error reading PDF {filepath}: {e}")
        return ""

def process_file(file_path: str, filename: str, cache: dict) -> List[Document]:
    docs = []
    if filename.lower().endswith('.pdf'):
        checksum = compute_checksum(file_path)
        if checksum in cache:
            text = cache[checksum]
            logging.info(f"Loaded cached text for {filename}")
        else:
            text = load_pdf_with_tables(file_path)
            cache[checksum] = text
            logging.info(f"Cached text for {filename}")
        if not text.strip():
            logging.warning(f"Skipping {filename} as no text was extracted.")
            return []
        doc = Document(page_content=text, metadata={"source_file": filename})
        docs.append(doc)
    elif filename.lower().endswith('.txt'):
        loader = TextLoader(file_path)
        docs = loader.load()
    return docs

def get_docs_folder_state(doc_folder: str) -> dict:
    """
    Return a dictionary of {filename: modification_time} for each PDF/TXT file in doc_folder.
    """
    state = {}
    for filename in os.listdir(doc_folder):
        if filename.lower().endswith(('.pdf', '.txt')):
            full_path = os.path.join(doc_folder, filename)
            state[filename] = os.path.getmtime(full_path)
    return state

def load_and_clean_documents(doc_folder: str) -> List[Document]:
    start_time = time.perf_counter()
    heading_regex = re.compile(r"^(?:[A-Z0-9 .-]+)$")
    documents = []
    cache = load_cache()

    file_list = [
        filename for filename in os.listdir(doc_folder)
        if filename.lower().endswith(('.pdf', '.txt'))
    ]

    chunk_size = 3
    for i in range(0, len(file_list), chunk_size):
        batch = file_list[i:i + chunk_size]
        with concurrent.futures.ProcessPoolExecutor() as executor:
            futures = {
                executor.submit(process_file, os.path.join(doc_folder, filename), filename, cache): filename
                for filename in batch
            }
            for future in concurrent.futures.as_completed(futures):
                filename = futures[future]
                try:
                    docs = future.result()
                except Exception as exc:
                    logging.error(f"Error processing {filename}: {exc}")
                    continue

                for doc in docs:
                    cleaned = re.sub(r'[ \t]{2,}', ' ', doc.page_content).strip()
                    if not cleaned:
                        continue
                    doc.page_content = cleaned
                    possible_heading = cleaned.split('\n', 1)[0].strip()
                    doc.metadata["heading"] = (
                        possible_heading if heading_regex.match(possible_heading) else "N/A"
                    )
                    if "source_file" not in doc.metadata:
                        doc.metadata["source_file"] = filename
                    documents.append(doc)

    save_cache(cache)
    end_time = time.perf_counter()
    logging.info(f"Document loading and cleaning took {end_time - start_time:.2f} seconds")
    return documents

def simple_split(documents: List[Document], target_chunk_size: int = 512) -> List[Document]:
    start_time = time.perf_counter()
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt')
        
    new_docs = []
    header_regex = re.compile(r'^(?:[A-Z\s]{3,}|[A-Z][a-z]+(?:\s[A-Z][a-z]+)*)$')
    
    for doc in documents:
        sentences = nltk.sent_tokenize(doc.page_content)
        current_chunk = []
        current_token_count = 0
        for sentence in sentences:
            if header_regex.match(sentence.strip()):
                if current_chunk:
                    new_docs.append(Document(page_content=" ".join(current_chunk), metadata=doc.metadata.copy()))
                    current_chunk = []
                    current_token_count = 0
            tokens = tokenizer.tokenize(sentence)
            sentence_token_count = len(tokens)
            if current_token_count + sentence_token_count > target_chunk_size and current_chunk:
                new_docs.append(Document(page_content=" ".join(current_chunk), metadata=doc.metadata.copy()))
                current_chunk = [sentence]
                current_token_count = sentence_token_count
            else:
                current_chunk.append(sentence)
                current_token_count += sentence_token_count
        if current_chunk:
            new_docs.append(Document(page_content=" ".join(current_chunk), metadata=doc.metadata.copy()))
    end_time = time.perf_counter()
    logging.info(f"Simple splitting took {end_time - start_time:.2f} seconds")
    return new_docs

# =============================================================================
# Prompt Templates
# =============================================================================
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

# =============================================================================
# Query Expansion and Metadata Filtering
# =============================================================================
def expand_query(query: str, llm: LLM) -> List[str]:
    expand_start = time.perf_counter()
    expanded = [
        query,
        query + " courses",
        query.replace("student", "learner")
    ]
    result = list(set(expanded))
    expand_end = time.perf_counter()
    logging.info(f"Query expansion took {expand_end - expand_start:.2f} seconds")
    return result

def filter_documents_by_metadata(docs: List[Document], query: str) -> List[Document]:
    filter_start = time.perf_counter()
    if "uwi" in query.lower():
        filtered = [doc for doc in docs if "uwi" in doc.metadata.get("source_file", "").lower()]
        if filtered:
            docs = filtered
    filter_end = time.perf_counter()
    logging.info(f"Metadata filtering took {filter_end - filter_start:.2f} seconds")
    return docs

# =============================================================================
# Custom LLM Class for Ollama
# =============================================================================
class OllamaLLM(LLM):
    model_name: str = "llama3:8b"  # Updated model name
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

# =============================================================================
# BM25 Retriever
# =============================================================================
class BM25Retriever(BaseRetriever):
    _documents: List[Document] = PrivateAttr()
    _tokenized: List[List[str]] = PrivateAttr()
    _k: int = PrivateAttr()
    _bm25: BM25Okapi = PrivateAttr()

    def __init__(self, documents: List[Document], k: int = 10):
        super().__init__()
        self._documents = documents
        self._tokenized = [doc.page_content.lower().split() for doc in documents]
        self._k = k
        self._bm25 = BM25Okapi(self._tokenized)

    def _get_relevant_documents(self, query: str, **kwargs) -> List[Document]:
        tokens = query.lower().split()
        scores = self._bm25.get_scores(tokens)
        scored_docs = sorted(zip(self._documents, scores), key=lambda x: x[1], reverse=True)
        return [doc for doc, s in scored_docs][:self._k]

    get_relevant_documents = _get_relevant_documents

# =============================================================================
# Cosine Similarity Retriever
# =============================================================================
class CosineSimilarityRetriever(BaseRetriever):
    _documents: List[Document] = PrivateAttr()
    _embedding_model = PrivateAttr()
    _k: int = PrivateAttr()
    _doc_embeddings: List[np.ndarray] = PrivateAttr()

    def __init__(self, documents: List[Document], embedding_model, k: int = 5):
        super().__init__()
        self._documents = documents
        self._embedding_model = embedding_model
        self._k = k
        self._doc_embeddings = [
            np.array(embedding_model.embed_query(doc.page_content))
            for doc in documents
        ]
    
    def _get_relevant_documents(self, query: str, **kwargs) -> List[Document]:
        retrieval_start = time.perf_counter()
        query_embedding = np.array(self._embedding_model.embed_query(query))
        query_norm = query_embedding / np.linalg.norm(query_embedding)
        scores = []
        for doc_emb in self._doc_embeddings:
            doc_norm = doc_emb / np.linalg.norm(doc_emb)
            similarity = np.dot(query_norm, doc_norm)
            scores.append(similarity)
        ranked_docs = sorted(zip(self._documents, scores), key=lambda x: x[1], reverse=True)
        top_docs = [doc for doc, score in ranked_docs][:self._k]
        retrieval_end = time.perf_counter()
        logging.info(f"Cosine similarity retrieval took {retrieval_end - retrieval_start:.2f} seconds")
        return top_docs

    get_relevant_documents = _get_relevant_documents

# =============================================================================
# Keyword Retriever
# =============================================================================
class KeywordRetriever(BaseRetriever):
    _documents: List[Document] = PrivateAttr()
    _k: int = PrivateAttr()

    def __init__(self, documents: List[Document], k: int = 10):
        super().__init__()
        self._documents = documents
        self._k = k

    def _get_relevant_documents(self, query: str, **kwargs) -> List[Document]:
        retrieve_start = time.perf_counter()
        query_lower = query.lower()
        matched = [doc for doc in self._documents if query_lower in doc.page_content.lower()]
        retrieved_docs = matched[:self._k]
        retrieve_end = time.perf_counter()
        logging.info(f"Keyword retrieval took {retrieve_end - retrieve_start:.2f} seconds")
        return retrieved_docs

    get_relevant_documents = _get_relevant_documents

# =============================================================================
# Ensemble Retriever
# =============================================================================
class EnsembleRetriever(BaseRetriever):
    _retrievers: List[BaseRetriever] = PrivateAttr()
    _weights: List[float] = PrivateAttr()
    _threshold: float = PrivateAttr()

    def __init__(self, retrievers: List[BaseRetriever], weights: List[float], threshold: float = 0.1):
        super().__init__()
        if len(retrievers) != len(weights):
            raise ValueError("The number of retrievers must match the number of weights.")
        self._retrievers = retrievers
        self._weights = weights
        self._threshold = threshold

    def _get_relevant_documents(self, query: str, **kwargs) -> List[Document]:
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

# =============================================================================
# Diversity Re-ranking using Cross-Encoder
# =============================================================================
def rerank_with_crossencoder(query: str, docs: List[Document]) -> List[Document]:
    if not docs:
        return []
    re_rank_start = time.perf_counter()
    pairs = [(query, doc.page_content) for doc in docs]
    scores = cross_encoder.predict(pairs)
    ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
    re_rank_end = time.perf_counter()
    logging.info(f"Cross-encoder re-ranking took {re_rank_end - re_rank_start:.2f} seconds")
    return [doc for doc, score in ranked]

# =============================================================================
# Initialization Helper: Documents, Vector Store & Embedding Model
# =============================================================================
def initialize_documents_and_vector_store(doc_folder: str = "./docs",
                                          persist_directory: str = "./chroma_db_bilingual",
                                          docs_cache_path: str = "docs_cache.joblib",
                                          state_cache_path: str = "docs_state.json"):
    init_start = time.perf_counter()
    # 1. Initialize the embedding model (using GPU if available)
    embedding_model = SentenceTransformerEmbeddings(
        model_name="BAAI/bge-large-en-v1.5",
        model_kwargs={"trust_remote_code": True, "device": "cuda"}
    )
    # 2. Compute the current state of the docs folder
    current_state = get_docs_folder_state(doc_folder)
    
    # 3. Load previous state if available.
    previous_state = {}
    if os.path.exists(state_cache_path):
        try:
            with open(state_cache_path, "r") as f:
                previous_state = json.load(f)
        except Exception as e:
            logging.error(f"Error loading state cache: {e}")
    
    # 4. Determine if reprocessing is needed.
    reprocess = (current_state != previous_state)
    
    if os.path.exists(persist_directory) and os.listdir(persist_directory) and not reprocess:
        logging.info("Persistent vector store found. Loading from disk...")
        vector_store = Chroma(persist_directory=persist_directory, embedding_function=embedding_model)
        if os.path.exists(docs_cache_path):
            docs = joblib.load(docs_cache_path)
            logging.info(f"Loaded {len(docs)} cached document chunks.")
        else:
            logging.warning("No document cache found. Rebuilding documents from source...")
            documents = load_and_clean_documents(doc_folder)
            logging.info(f"Loaded {len(documents)} documents.")
            metadata_docs = create_documents_from_data(degree_programs_data)
            documents.extend(metadata_docs)
            docs = simple_split(documents, target_chunk_size=512)
            logging.info(f"Created {len(docs)} document chunks after splitting.")
            joblib.dump(docs, docs_cache_path)
    else:
        logging.info("No persistent vector store found or documents have changed. Loading and cleaning documents...")
        documents = load_and_clean_documents(doc_folder)
        logging.info(f"Loaded {len(documents)} documents.")
        metadata_docs = create_documents_from_data(degree_programs_data)
        documents.extend(metadata_docs)
        docs = simple_split(documents, target_chunk_size=512)
        logging.info(f"Created {len(docs)} document chunks after splitting.")
        logging.info("Building new vector store...")
        vector_store = Chroma.from_documents(docs, embedding_model, persist_directory=persist_directory)
        joblib.dump(docs, docs_cache_path)
    
    # 5. Save the current folder state for future incremental updates.
    try:
        with open(state_cache_path, "w") as f:
            json.dump(current_state, f)
    except Exception as e:
        logging.error(f"Error saving state cache: {e}")
    
    init_end = time.perf_counter()
    logging.info(f"Initialization took {init_end - init_start:.2f} seconds")
    return docs, vector_store, embedding_model

# =============================================================================
# FastAPI Integration
# =============================================================================
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Document QA API")

# Global variables for pipeline resources.
docs = None
vector_store = None
embedding_model = None
ensemble_ret = None
llm = None

@app.on_event("startup")
async def startup_event():
    global docs, vector_store, embedding_model, ensemble_ret, llm
    # Initialize documents, vector store, and embedding model.
    docs, vector_store, embedding_model = initialize_documents_and_vector_store(doc_folder="./docs",
                                                                                  persist_directory="./chroma_db_bilingual")
    # Build retrievers concurrently (using simplified logic here).
    semantic_retriever = vector_store.as_retriever(search_kwargs={"k": 25})
    bm25_retriever = BM25Retriever(docs, k=25)
    chroma_mmr_retriever = vector_store.as_retriever(
        search_type="mmr", search_kwargs={"k": 25, "fetch_k": 30, "lambda_mult": 0.5}
    )
    ensemble_ret = EnsembleRetriever(
        retrievers=[semantic_retriever, bm25_retriever, chroma_mmr_retriever],
        weights=[1.0, 0.9, 0.9],
        threshold=1.0
    )
    llm = OllamaLLM(model_name="llama3:8b", temperature=0.0)
    logging.info("API Startup: Resources initialized.")

# Request and response models.
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
        # 1. Expand Query
        expanded_queries = expand_query(user_query, llm)

        # 2. Retrieve documents for each expanded query.
        all_initial_docs = []
        for eq in expanded_queries:
            docs_for_eq = ensemble_ret.get_relevant_documents(eq)
            all_initial_docs.extend(docs_for_eq)

        # 3. Deduplicate and filter documents.
        unique_docs = {doc.metadata.get("source_file", doc.id): doc for doc in all_initial_docs}.values()
        initial_docs = list(unique_docs)
        initial_docs = filter_documents_by_metadata(initial_docs, user_query)

        # 4. Rerank using Cross-Encoder.
        reranked_docs = rerank_with_crossencoder(user_query, initial_docs)

        # 5. Combine context and choose prompt.
        combined_context = "\n".join([doc.page_content for doc in reranked_docs[:10]])
        if any(keyword in user_query.lower() for keyword in ["credit", "graduate", "bsc", "degree", "study"]):
            chosen_prompt = credit_prompt
            logging.info("Using custom credit prompt.")
        else:
            chosen_prompt = default_prompt
            logging.info("Using default prompt.")
            
        prompt_str = chosen_prompt.format(context=combined_context, question=user_query)
        
        # 6. Call the LLM to get the answer.
        answer = llm._call(prompt_str)
        
        processing_time = time.perf_counter() - start_time
        return QueryResponse(answer=answer, processing_time=processing_time)
    except Exception as e:
        logging.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# Main Entry Point
# =============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
