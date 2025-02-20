import os
import re
import subprocess
import concurrent.futures
import hashlib
import json
import logging
import numpy as np
import pickle
import uuid
from typing import Optional, List, Union

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
domain_classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")

from sentence_transformers import CrossEncoder
cross_encoder = CrossEncoder("BAAI/bge-reranker-base")

# =============================================================================
# Global Document Class (with unique id)
# =============================================================================
class Document:
    def __init__(self, page_content: str, metadata: dict, id: Optional[str] = None):
        self.page_content = page_content
        self.metadata = metadata
        self.id = id or str(uuid.uuid4())

    def __repr__(self):
        return f"Document(source={self.metadata.get('source_file', 'N/A')}, length={len(self.page_content)})"

# =============================================================================
# Example structured data for degree programs (metadata)
# =============================================================================
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
# Cache configuration for PDF extraction
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
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f)
    except Exception as e:
        logging.error(f"Error saving cache: {e}")

# =============================================================================
# Custom LLM class for Ollama
# =============================================================================
class OllamaLLM(LLM):
    model_name: str = "deepseek-r1:14b"
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
# Custom PDF Loader with Table Extraction and Fallback
# =============================================================================
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

# =============================================================================
# Helper function to process individual files (PDF or TXT) with caching
# =============================================================================
def process_file(file_path: str, filename: str, cache: dict):
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

# =============================================================================
# Document Loading and Cleaning (Parallelized)
# =============================================================================
def load_and_clean_documents(doc_folder: str) -> List[Document]:
    heading_regex = re.compile(r"^(?:[A-Z0-9 .-]+)$")
    documents = []
    cache = load_cache()
    file_list = [filename for filename in os.listdir(doc_folder) if filename.lower().endswith(('.pdf', '.txt'))]

    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {
            executor.submit(process_file, os.path.join(doc_folder, filename), filename, cache): filename 
            for filename in file_list
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
                doc.metadata["heading"] = possible_heading if heading_regex.match(possible_heading) else "N/A"
                if "source_file" not in doc.metadata:
                    doc.metadata["source_file"] = filename
                documents.append(doc)
    save_cache(cache)
    return documents

# =============================================================================
# Enhanced Hierarchical Splitting with Semantic Boundaries
# =============================================================================
def simple_split(documents: List[Document], target_chunk_size: int = 512) -> List[Document]:
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
# Query Expansion/Reformulation
# =============================================================================
def expand_query(query: str, llm: LLM) -> List[str]:
    expanded = [query,
                query + " courses",
                query.replace("student", "learner")]
    return list(set(expanded))

# =============================================================================
# Metadata Filtering
# =============================================================================
def filter_documents_by_metadata(docs: List[Document], query: str) -> List[Document]:
    if "uwi" in query.lower():
        filtered = [doc for doc in docs if "uwi" in doc.metadata.get("source_file", "").lower()]
        if filtered:
            return filtered
    return docs

# =============================================================================
# BM25 Retriever (subclassing BaseRetriever)
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
        query_embedding = np.array(self._embedding_model.embed_query(query))
        query_norm = query_embedding / np.linalg.norm(query_embedding)
        scores = []
        for doc_emb in self._doc_embeddings:
            doc_norm = doc_emb / np.linalg.norm(doc_emb)
            similarity = np.dot(query_norm, doc_norm)
            scores.append(similarity)
        ranked_docs = sorted(zip(self._documents, scores), key=lambda x: x[1], reverse=True)
        return [doc for doc, score in ranked_docs][:self._k]

    get_relevant_documents = _get_relevant_documents

class KeywordRetriever(BaseRetriever):
    _documents: List[Document] = PrivateAttr()
    _k: int = PrivateAttr()

    def __init__(self, documents: List[Document], k: int = 10):
        super().__init__()
        self._documents = documents
        self._k = k

    def _get_relevant_documents(self, query: str, **kwargs) -> List[Document]:
        query_lower = query.lower()
        matched = [doc for doc in self._documents if query_lower in doc.page_content.lower()]
        return matched[:self._k]

    get_relevant_documents = _get_relevant_documents

# =============================================================================
# Weighted Ensemble Retriever with Reciprocal Rank Fusion
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
    pairs = [(query, doc.page_content) for doc in docs]
    scores = cross_encoder.predict(pairs)
    ranked = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
    return [doc for doc, score in ranked]

# =============================================================================
# Initialization Helper: Documents, Vector Store & Embedding Model
# =============================================================================
def initialize_documents_and_vector_store(doc_folder: str = "./docs",
                                          persist_directory: str = "./chroma_db_bilingual",
                                          docs_cache_path: str = "docs_cache.pkl"):
    embedding_model = SentenceTransformerEmbeddings(
        model_name="BAAI/bge-large-en-v1.5",
        model_kwargs={"trust_remote_code": True}
    )
    
    # If vector store exists, load it along with cached docs.
    if os.path.exists(persist_directory) and os.listdir(persist_directory):
        logging.info("Persistent vector store found. Loading from disk...")
        vector_store = Chroma(persist_directory=persist_directory, embedding_function=embedding_model)
        if os.path.exists(docs_cache_path):
            with open(docs_cache_path, "rb") as f:
                docs = pickle.load(f)
            logging.info(f"Loaded {len(docs)} cached document chunks.")
        else:
            logging.warning("No document cache found. Rebuilding documents from source...")
            documents = load_and_clean_documents(doc_folder)
            logging.info(f"Loaded {len(documents)} documents.")
            metadata_docs = create_documents_from_data(degree_programs_data)
            documents.extend(metadata_docs)
            docs = simple_split(documents, target_chunk_size=512)
            logging.info(f"Created {len(docs)} document chunks after splitting.")
            with open(docs_cache_path, "wb") as f:
                pickle.dump(docs, f)
    else:
        logging.info("No persistent vector store found. Loading and cleaning documents...")
        documents = load_and_clean_documents(doc_folder)
        logging.info(f"Loaded {len(documents)} documents.")
        metadata_docs = create_documents_from_data(degree_programs_data)
        documents.extend(metadata_docs)
        docs = simple_split(documents, target_chunk_size=512)
        logging.info(f"Created {len(docs)} document chunks after splitting.")
        logging.info("Building new vector store...")
        # Pass embedding_model as a positional argument to avoid duplicate keyword
        vector_store = Chroma.from_documents(docs, embedding_model, persist_directory=persist_directory)
        with open(docs_cache_path, "wb") as f:
            pickle.dump(docs, f)
    
    return docs, vector_store, embedding_model

# =============================================================================
# Main Execution
# =============================================================================
def main():
    docs, vector_store, embedding_model = initialize_documents_and_vector_store()
    
    semantic_retriever = vector_store.as_retriever(search_kwargs={"k": 50})
    bm25_retriever = BM25Retriever(docs, k=50)
    cosine_retriever = CosineSimilarityRetriever(docs, embedding_model, k=50)

    ensemble_ret = EnsembleRetriever(
        retrievers=[semantic_retriever, bm25_retriever, cosine_retriever],
        weights=[1.0, 0.5, 0.9],
        threshold=1.0
    )

    llm = OllamaLLM(model_name="deepseek-r1:14b", temperature=0.0)
    user_query = "What are some level 1 courses on statistics i could do?"
    logging.info(f"User Query: {user_query}")

    expanded_queries = expand_query(user_query, llm)
    logging.info(f"Expanded queries: {expanded_queries}")

    # Parallelize retrieval for expanded queries.
    all_initial_docs = []
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(ensemble_ret.invoke, eq): eq for eq in expanded_queries}
        for future in concurrent.futures.as_completed(futures):
            eq = futures[future]
            try:
                docs_for_eq = future.result()
                all_initial_docs.extend(docs_for_eq)
            except Exception as exc:
                logging.error(f"Error retrieving docs for query '{eq}': {exc}")

    unique_docs = {doc.metadata.get("source_file", doc.id): doc for doc in all_initial_docs}.values()
    initial_docs = list(unique_docs)
    logging.info(f"Initial retrieval returned {len(initial_docs)} unique docs.")

    initial_docs = filter_documents_by_metadata(initial_docs, user_query)
    logging.info(f"After metadata filtering, {len(initial_docs)} docs remain.")

    reranked_docs = rerank_with_crossencoder(user_query, initial_docs)
    logging.info("Documents re-ranked with cross-encoder.")

    combined_context = "\n".join([doc.page_content for doc in reranked_docs[:8]])
    
    if any(keyword in user_query.lower() for keyword in ["credit", "graduate", "bsc", "degree", "study"]):
        chosen_prompt = credit_prompt
        logging.info("Using custom credit prompt.")
    else:
        chosen_prompt = default_prompt
        logging.info("Using default prompt.")

    prompt_str = chosen_prompt.format(context=combined_context, question=user_query)
    answer = llm._call(prompt_str)
    logging.info("=== Final Answer ===")
    logging.info(answer)

if __name__ == "__main__":
    main()
