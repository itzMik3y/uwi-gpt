# ingestion.py
import os
import re
import concurrent.futures
import hashlib
import json
import logging
import time
from typing import List

import joblib
import nltk
import pdfplumber
from transformers import AutoTokenizer
from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_chroma import Chroma

# Import your custom Document class
from document import Document

# Initialize tokenizer
tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-large-en-v1.5")

try:
    import fitz
except ModuleNotFoundError:
    fitz = None
    logging.warning("PyMuPDF (fitz) not found. Install it with 'pip install PyMuPDF' for fallback extraction.")

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

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

# PDF Caching and Extraction Helpers
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

def initialize_documents_and_vector_store(doc_folder: str = "./docs",
                                          persist_directory: str = "./chroma_db_bilingual",
                                          docs_cache_path: str = "docs_cache.joblib",
                                          state_cache_path: str = "docs_state.json"):
    init_start = time.perf_counter()
    # Initialize the embedding model (using GPU if available)
    embedding_model = SentenceTransformerEmbeddings(
        model_name="BAAI/bge-large-en-v1.5",
        model_kwargs={"trust_remote_code": True, "device": "cuda"}
    )
    # Compute current state of docs folder
    current_state = get_docs_folder_state(doc_folder)
    
    # Load previous state if available
    previous_state = {}
    if os.path.exists(state_cache_path):
        try:
            with open(state_cache_path, "r") as f:
                previous_state = json.load(f)
        except Exception as e:
            logging.error(f"Error loading state cache: {e}")
    
    # Determine if reprocessing is needed
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
    
    # Save current folder state for future incremental updates.
    try:
        with open(state_cache_path, "w") as f:
            json.dump(current_state, f)
    except Exception as e:
        logging.error(f"Error saving state cache: {e}")
    
    init_end = time.perf_counter()
    logging.info(f"Initialization took {init_end - init_start:.2f} seconds")
    return docs, vector_store, embedding_model

def load_vector_store(persist_directory: str, embedding_model=None):
    """
    Helper to load the vector store without rebuilding it.
    """
    from langchain_chroma import Chroma
    from langchain_community.embeddings import SentenceTransformerEmbeddings
    if embedding_model is None:
        embedding_model = SentenceTransformerEmbeddings(
            model_name="BAAI/bge-large-en-v1.5",
            model_kwargs={"trust_remote_code": True, "device": "cuda"}
        )
    return Chroma(persist_directory=persist_directory, embedding_function=embedding_model)
