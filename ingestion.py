#!/usr/bin/env python
"""
ingestion.py

This script:
- Loads and cleans documents from a folder.
- Splits documents into chunks.
- Uses a JSON file for caching extracted PDF text.
- Uses joblib for caching processed document chunks.
- Builds or incrementally updates a persistent Qdrant vector store.
- Uses an incremental update strategy to add only new/changed documents.
"""

import os
import re
import concurrent.futures
import hashlib
import json
import logging
import time
from typing import List, Dict, Any

import joblib
import nltk
import pdfplumber
from transformers import AutoTokenizer
from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import SentenceTransformerEmbeddings
# Use the new import per deprecation warning:
from langchain_community.vectorstores import Qdrant

from document import Document

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Paths and configuration.
DOC_FOLDER = "./docs"
PERSIST_COLLECTION = "my_collection"  # Qdrant collection name
# When using URL only, we do not supply a local "path".
STATE_CACHE_PATH = "docs_state.json"
PDF_CACHE_PATH = "pdf_cache.json"      # JSON file for caching PDF extraction results
DOCS_CACHE_PATH = "docs_cache.joblib"    # Joblib cache for processed document chunks

tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-large-en-v1.5")

try:
    import fitz
except ModuleNotFoundError:
    fitz = None
    logging.warning("PyMuPDF (fitz) not found. Install it with 'pip install PyMuPDF' for fallback extraction.")

# Example structured data for degree programs.
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
]

def create_documents_from_data(data_list: List[Dict[str, Any]]) -> List[Document]:
    docs = []
    for item in data_list:
        docs.append(Document(
            page_content=item["description"],
            metadata={
                "title": item["title"],
                "department": item["department"],
                "faculty": item["faculty"]
            }
        ))
    return docs

# ----- PDF Caching and Extraction Helpers -----
def compute_checksum(filepath: str) -> str:
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def load_pdf_cache() -> Dict[str, str]:
    if os.path.exists(PDF_CACHE_PATH):
        try:
            with open(PDF_CACHE_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Error loading PDF cache: {e}")
            return {}
    return {}

def save_pdf_cache(cache: Dict[str, str]):
    try:
        with open(PDF_CACHE_PATH, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        logging.error(f"Error saving PDF cache: {e}")

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

def process_file(file_path: str, filename: str, cache: Dict[str, str]) -> List[Document]:
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
        docs.append(Document(page_content=text, metadata={"source_file": filename}))
    elif filename.lower().endswith('.txt'):
        loader = TextLoader(file_path)
        docs = loader.load()
    return docs

def get_docs_folder_state(doc_folder: str) -> Dict[str, float]:
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
    pdf_cache = load_pdf_cache()
    file_list = [fn for fn in os.listdir(doc_folder) if fn.lower().endswith(('.pdf', '.txt'))]
    chunk_size = 3
    for i in range(0, len(file_list), chunk_size):
        batch = file_list[i:i + chunk_size]
        with concurrent.futures.ProcessPoolExecutor() as executor:
            futures = {
                executor.submit(process_file, os.path.join(doc_folder, filename), filename, pdf_cache): filename
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
                    doc.metadata["heading"] = possible_heading if heading_regex.match(possible_heading) else "N/A"
                    if "source_file" not in doc.metadata:
                        doc.metadata["source_file"] = filename
                    documents.append(doc)
    save_pdf_cache(pdf_cache)
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

def incremental_update(doc_folder: str, state_cache_path: str) -> List[Document]:
    current_state = get_docs_folder_state(doc_folder)
    if os.path.exists(state_cache_path):
        with open(state_cache_path, "r") as f:
            previous_state = json.load(f)
    else:
        previous_state = {}
    new_files = [fname for fname, mtime in current_state.items()
                 if fname not in previous_state or mtime > previous_state.get(fname, 0)]
    logging.info(f"Found {len(new_files)} new/modified files.")
    new_docs = []
    pdf_cache = load_pdf_cache()
    for filename in new_files:
        full_path = os.path.join(doc_folder, filename)
        docs_from_file = process_file(full_path, filename, pdf_cache)
        new_docs.extend(docs_from_file)
    if new_docs:
        new_docs = simple_split(new_docs, target_chunk_size=512)
    with open(state_cache_path, "w") as f:
        json.dump(current_state, f)
    save_pdf_cache(pdf_cache)
    return new_docs

def initialize_documents_and_vector_store(doc_folder: str = "./docs",
                                          collection_name: str = "my_collection",
                                          docs_cache_path: str = "docs_cache.joblib",
                                          state_cache_path: str = "docs_state.json"):
    init_start = time.perf_counter()
    # 1. Initialize the embedding model.
    embedding_model = SentenceTransformerEmbeddings(
        model_name="BAAI/bge-large-en-v1.5",
        model_kwargs={"trust_remote_code": True, "device": "cuda"}
    )
    # 2. Compute current state of docs folder.
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
    
    if os.path.exists(collection_name) and not reprocess:
        logging.info("Persistent vector store found. Loading from Qdrant...")
        vector_store = Qdrant.from_existing_collection(
            embedding_model, 
            collection_name=collection_name, 
            url="http://localhost:6333"
        )
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
        logging.info("Building new vector store using Qdrant...")
        vector_store = Qdrant.from_documents(
            docs, 
            embedding_model, 
            collection_name=collection_name, 
            url="http://localhost:6333",
            force_recreate=True      # <-- This parameter forces the recreation of the collection.
        )
        joblib.dump(docs, docs_cache_path)
    
    try:
        with open(state_cache_path, "w") as f:
            json.dump(current_state, f)
    except Exception as e:
        logging.error(f"Error saving state cache: {e}")
    
    init_end = time.perf_counter()
    logging.info(f"Initialization took {init_end - init_start:.2f} seconds")
    return docs, vector_store, embedding_model

def load_existing_qdrant_store(
    collection_name: str = "my_collection",
    docs_cache_path: str = "docs_cache.joblib",
    qdrant_url: str = "http://localhost:6333"
):
    """
    Loads the existing Qdrant vector store and cached documents.
    """
    from langchain_community.embeddings import SentenceTransformerEmbeddings
    from langchain_community.vectorstores import Qdrant
    from qdrant_client import QdrantClient
    import joblib

    embedding_model = SentenceTransformerEmbeddings(
        model_name="BAAI/bge-large-en-v1.5",
        model_kwargs={"trust_remote_code": True, "device": "cuda"}
    )

    # Create Qdrant client
    client = QdrantClient(url=qdrant_url)

    # Initialize vector store with client
    vector_store = Qdrant(
        client=client,
        collection_name=collection_name,
        embeddings=embedding_model
    )

    if not os.path.exists(docs_cache_path):
        raise FileNotFoundError(f"Document cache not found: {docs_cache_path}. Please run ingestion first.")
    docs = joblib.load(docs_cache_path)
    return docs, vector_store, embedding_model

def load_vector_store(persist_url: str = "http://localhost:6333", 
                      collection_name: str = "my_collection", 
                      embedding_model=None,
                      path: str = "./qdrant_db"):
    """
    Helper to load the Qdrant vector store without rebuilding it.
    """
    from langchain_community.vectorstores import Qdrant
    from langchain_community.embeddings import SentenceTransformerEmbeddings
    if embedding_model is None:
        embedding_model = SentenceTransformerEmbeddings(
            model_name="BAAI/bge-large-en-v1.5",
            model_kwargs={"trust_remote_code": True, "device": "cuda"}
        )
    return Qdrant.from_existing_collection(
        embedding_model,
        collection_name=collection_name,
        path=path,
        url=persist_url
    )

if __name__ == "__main__":
    docs, vector_store, embedding_model = initialize_documents_and_vector_store(
        doc_folder=DOC_FOLDER,
        collection_name="my_collection"
    )
